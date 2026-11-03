"""Scraper for NaturaBuy listings and auctions."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    DEFAULT_USER_AGENT,
    SALE_TYPE_ALL,
    SALE_TYPE_AUCTION,
    SALE_TYPE_BUY_NOW,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class NaturaBuyItem:
    """Represents an item on NaturaBuy."""

    id: str
    title: str
    url: str
    image_url: str | None
    price: float
    price_str: str
    auction_price: float | None
    buy_now_price: float | None
    is_auction: bool
    is_buy_now: bool
    remaining_time_str: str | None
    remaining_seconds: int | None
    brand: str | None
    condition: str | None
    seller_type: str | None
    is_newly_added: bool
    date_detected: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert item to dictionary for sensor attributes and events."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "image_url": self.image_url,
            "price": self.price,
            "price_str": self.price_str,
            "auction_price": self.auction_price,
            "buy_now_price": self.buy_now_price,
            "is_auction": self.is_auction,
            "is_buy_now": self.is_buy_now,
            "remaining_time": self.remaining_time_str,
            "remaining_seconds": self.remaining_seconds,
            "brand": self.brand,
            "condition": self.condition,
            "seller_type": self.seller_type,
            "is_newly_added": self.is_newly_added,
            "date_detected": self.date_detected.isoformat(),
        }


def clean_price(text: str | None) -> float | None:
    """Clean and parse a price string to float."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d,\.]", "", text).replace(" ", "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_remaining_seconds(time_str: str | None) -> int | None:
    """Parse a remaining time string like 'reste 1h 05m' or 'reste 45m' into seconds."""
    if not time_str:
        return None
    time_str = time_str.lower().strip()
    if "reste" not in time_str and "fin" not in time_str:
        return None

    total = 0
    days = re.search(r"(\d+)\s*j", time_str)
    hours = re.search(r"(\d+)\s*h", time_str)
    minutes = re.search(r"(\d+)\s*m(?:in)?(?!\w)", time_str)
    seconds = re.search(r"(\d+)\s*s(?:ec)?(?!\w)", time_str)

    found = False
    if days:
        total += int(days.group(1)) * 86400
        found = True
    if hours:
        total += int(hours.group(1)) * 3600
        found = True
    if minutes:
        total += int(minutes.group(1)) * 60
        found = True
    if seconds:
        total += int(seconds.group(1))
        found = True

    return total if found else None


def build_search_url(
    base_url: str,
    max_price: float | None = None,
    min_price: float | None = None,
    sort: str = "ends",
    sale_type: str = SALE_TYPE_ALL,
) -> str:
    """Inject search/filter parameters into NaturaBuy URL."""
    parsed = urlparse(base_url)
    query_params = parse_qs(parsed.query)

    query_params["SortProperty"] = [sort]

    if max_price is not None and max_price > 0:
        query_params["maxprice"] = [str(int(max_price) if max_price.is_integer() else max_price)]

    if min_price is not None and min_price > 0:
        query_params["minprice"] = [str(int(min_price) if min_price.is_integer() else min_price)]

    if sale_type == SALE_TYPE_AUCTION:
        query_params["normal"] = ["y"]
        query_params.pop("buyitnowonly", None)
    elif sale_type == SALE_TYPE_BUY_NOW:
        query_params["buyitnowonly"] = ["y"]
        query_params.pop("normal", None)

    # Flatten single list values
    encoded_query = urlencode({k: v[0] for k, v in query_params.items()})
    return urlunparse(parsed._replace(query=encoded_query))


def parse_items_from_html(html: str) -> list[NaturaBuyItem]:
    """Parse NaturaBuy HTML page into a list of NaturaBuyItem objects."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".itemCard")
    items: list[NaturaBuyItem] = []
    now = datetime.now(timezone.utc)

    for card in cards:
        # Extract ID
        item_id = card.get("data-id")
        href = card.get("href", "")
        if not item_id:
            m = re.search(r"item-(\d+)\.html", href)
            if m:
                item_id = m.group(1)
            else:
                continue

        # Full URL
        if href.startswith("http"):
            full_url = href
        else:
            full_url = f"https://www.naturabuy.fr/{href.lstrip('/')}"

        # Title
        title = (
            card.get("title")
            or card.get("data-name")
            or (card.select_one(".lines-ellipsis").get_text(strip=True) if card.select_one(".lines-ellipsis") else "")
        ).strip()

        # Image URL
        img_elem = card.select_one("img")
        image_url = None
        if img_elem:
            image_url = img_elem.get("src") or img_elem.get("data-src")
            if image_url and not image_url.startswith("http"):
                image_url = f"https:{image_url}" if image_url.startswith("//") else f"https://www.naturabuy.fr/{image_url.lstrip('/')}"

        # Sale type descriptions
        type_elements = card.select(".txt-anthracite-light")
        type_text = " ".join(t.get_text(" ", strip=True) for t in type_elements).lower()

        is_auction = "ench" in type_text
        is_buy_now = "achat" in type_text or not is_auction

        # Prices: find bold elements containing euro symbol
        bold_prices: list[float] = []
        for b in card.select(".bold"):
            t = b.get_text(strip=True)
            if "€" in t:
                p = clean_price(t)
                if p is not None:
                    bold_prices.append(p)

        auction_price: float | None = None
        buy_now_price: float | None = None

        if is_auction and is_buy_now and len(bold_prices) >= 2:
            auction_price = bold_prices[0]
            buy_now_price = bold_prices[1]
        elif is_auction:
            auction_price = bold_prices[0] if bold_prices else clean_price(card.get("data-price"))
        elif is_buy_now:
            buy_now_price = bold_prices[0] if bold_prices else clean_price(card.get("data-price"))

        # Effective price for comparison
        main_price = auction_price if is_auction and auction_price is not None else (buy_now_price or 0.0)
        price_str = f"{main_price:.2f} €" if main_price else "Prix inconnu"

        # Time remaining
        rem_elem = card.select_one(".remaining-time")
        remaining_str = rem_elem.get_text(strip=True) if rem_elem else None
        remaining_seconds = parse_remaining_seconds(remaining_str)

        # Newly added check
        starts_elem = card.select_one(".starts-time")
        starts_str = starts_elem.get_text(strip=True) if starts_elem else ""
        is_newly_added = "ajout" in starts_str.lower()

        # Metadata
        brand = card.get("data-brand")
        condition = card.get("data-dimension4")
        seller_type = card.get("data-dimension6")

        items.append(
            NaturaBuyItem(
                id=str(item_id),
                title=title,
                url=full_url,
                image_url=image_url,
                price=main_price,
                price_str=price_str,
                auction_price=auction_price,
                buy_now_price=buy_now_price,
                is_auction=is_auction,
                is_buy_now=is_buy_now,
                remaining_time_str=remaining_str,
                remaining_seconds=remaining_seconds,
                brand=brand,
                condition=condition,
                seller_type=seller_type,
                is_newly_added=is_newly_added,
                date_detected=now,
            )
        )

    return items


async def async_fetch_naturabuy_page(
    session: aiohttp.ClientSession,
    url: str,
) -> list[NaturaBuyItem]:
    """Fetch and parse items from a NaturaBuy URL with resilient encoding handling."""
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                _LOGGER.error("Failed to fetch NaturaBuy page %s, status code: %s", url, resp.status)
                return []
            raw_data = await resp.read()
            # Try utf-8 first, fallback to latin-1 / windows-1252
            try:
                html = raw_data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    html = raw_data.decode("iso-8859-1")
                except UnicodeDecodeError:
                    html = raw_data.decode("utf-8", errors="replace")

            return parse_items_from_html(html)
    except Exception as err:
        _LOGGER.error("Error fetching NaturaBuy page %s: %s", url, err)
        return []
