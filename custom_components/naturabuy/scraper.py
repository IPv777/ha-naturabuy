"""Scraper for NaturaBuy listings and auctions with enhanced filters, browser headers and seller analytics."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    CONDITION_NEW,
    CONDITION_USED,
    DEFAULT_HEADERS,
    SALE_TYPE_ALL,
    SALE_TYPE_AUCTION,
    SALE_TYPE_BUY_NOW,
    SELLER_PARTICULIER,
    SELLER_PRO,
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
    seller_reviews: int | None
    bids_count: int
    has_no_reserve: bool
    free_shipping: bool
    is_negotiable: bool
    is_newly_added: bool
    date_detected: datetime
    has_optic: bool = False
    optic_name: str | None = None
    is_threaded: bool = False
    has_silencer: bool = False
    is_left_handed: bool = False
    is_stainless: bool = False
    stock_material: str = "inconnu"
    urgency_level: str = "normal"
    caliber: str | None = None

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
            "seller_reviews": self.seller_reviews,
            "bids_count": self.bids_count,
            "has_no_reserve": self.has_no_reserve,
            "free_shipping": self.free_shipping,
            "is_negotiable": self.is_negotiable,
            "is_newly_added": self.is_newly_added,
            "date_detected": self.date_detected.isoformat(),
            "has_optic": self.has_optic,
            "optic_name": self.optic_name,
            "is_threaded": self.is_threaded,
            "has_silencer": self.has_silencer,
            "is_left_handed": self.is_left_handed,
            "is_stainless": self.is_stainless,
            "stock_material": self.stock_material,
            "urgency_level": self.urgency_level,
            "caliber": self.caliber,
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
    no_reserve: bool = False,
    condition: str = "all",
    seller_type: str = "all",
    brand: str | None = None,
    department: str | None = None,
    page: int = 1,
) -> str:
    """Inject search/filter parameters into NaturaBuy URL."""
    parsed = urlparse(base_url)
    query_params = parse_qs(parsed.query)

    query_params["SortProperty"] = [sort]

    # NaturaBuy router requires capital PAGE=N, lowercase page=N throws 404!
    if page > 1:
        query_params["PAGE"] = [str(page)]
    else:
        query_params.pop("PAGE", None)
        query_params.pop("page", None)

    if max_price is not None and max_price > 0:
        query_params["maxprice"] = [str(int(max_price) if max_price.is_integer() else max_price)]

    if min_price is not None and min_price > 0:
        query_params["minprice"] = [str(int(min_price) if min_price.is_integer() else min_price)]

    # Sale type
    if sale_type == SALE_TYPE_AUCTION:
        query_params["normal"] = ["y"]
        query_params.pop("buyitnowonly", None)
    elif sale_type == SALE_TYPE_BUY_NOW:
        query_params["buyitnowonly"] = ["y"]
        query_params.pop("normal", None)

    # No reserve price filter
    if no_reserve:
        query_params["PR"] = ["noPR"]

    # Condition: NaturaBuy requires occasions=y for used, occasions=n for new.
    # Passing occasions=occasions triggers a 404 router error!
    if condition == CONDITION_USED:
        query_params["occasions"] = ["y"]
    elif condition == CONDITION_NEW:
        query_params["occasions"] = ["n"]

    # Seller type
    if seller_type == SELLER_PARTICULIER:
        query_params["ispro"] = ["part"]
    elif seller_type == SELLER_PRO:
        query_params["ispro"] = ["pro"]

    # Brand filter if set
    if brand and brand.strip():
        query_params["brand"] = [brand.strip()]

    # Department filter if set (e.g. "57")
    if department and department.strip():
        query_params["dpt"] = [department.strip()]

    # Flatten single list values
    encoded_query = urlencode({k: v[0] for k, v in query_params.items()})
    return urlunparse(parsed._replace(query=encoded_query))


def parse_items_from_html(html: str, query_no_reserve: bool = False) -> list[NaturaBuyItem]:
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

        # Bids count
        bids_count = 0
        bids_match = re.search(r"(\d+)\s*ench", type_text)
        if bids_match:
            bids_count = int(bids_match.group(1))

        # Check for free shipping, reserve mentions, or negotiable offers
        all_card_text = card.get_text(" ", strip=True).lower()
        free_shipping = "livraison gratuite" in all_card_text or "port gratuit" in all_card_text
        has_no_reserve = (
            query_no_reserve
            or "sans reserve" in all_card_text
            or "sans réserve" in all_card_text
            or "sans prix de reserve" in all_card_text
            or "sans prix de réserve" in all_card_text
        )
        is_negotiable = "offre" in all_card_text or "négociable" in all_card_text

        # Seller reviews count
        seller_reviews: int | None = None
        rev_elem = card.select_one(".itemCard-reviews")
        if rev_elem:
            rev_match = re.search(r"\((\d+)\)", rev_elem.get_text(strip=True))
            if rev_match:
                seller_reviews = int(rev_match.group(1))

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

        # Hunting specific attribute extraction
        title_lower = title.lower()

        # Optics detection
        optics_keywords = [
            ("zeiss", "Zeiss"),
            ("aimpoint", "Aimpoint"),
            ("swarovski", "Swarovski"),
            ("kahles", "Kahles"),
            ("leupold", "Leupold"),
            ("meopta", "Meopta"),
            ("vortex", "Vortex"),
            ("steiner", "Steiner"),
            ("kite", "Kite"),
            ("weaver", "Weaver"),
            ("bushnell", "Bushnell"),
            ("burris", "Burris"),
            ("schmidt", "Schmidt & Bender"),
            ("nikko", "Nikko"),
            ("lunette", "Lunette"),
            ("point rouge", "Point Rouge"),
            ("optique", "Optique"),
        ]
        has_optic = False
        optic_name = None
        for kw, name in optics_keywords:
            if kw in title_lower:
                has_optic = True
                optic_name = name
                break

        # Threaded barrel
        threaded_keywords = ["fileté", "filetee", "filetage", "canon fileté", "5/8x24", "m14x1", "m15x1", "m14", "m15"]
        is_threaded = any(kw in title_lower for kw in threaded_keywords)

        # Silencer / sound moderator
        silencer_keywords = ["silencieux", "modérateur", "moderateur", "frein de bouche", "a-tec", "freyr", "hausken", "hertz"]
        has_silencer = any(kw in title_lower for kw in silencer_keywords)

        # Left-handed
        is_left_handed = "gaucher" in title_lower or "gauchère" in title_lower or "gauchere" in title_lower

        # Stainless
        is_stainless = "inox" in title_lower or "stainless" in title_lower

        # Stock material
        if any(kw in title_lower for kw in ["bois", "noyer", "wood"]):
            stock_material = "bois"
        elif any(kw in title_lower for kw in ["synthétique", "synthetique", "composite", "polymère", "polymere"]):
            stock_material = "synthétique"
        else:
            stock_material = "inconnu"

        # Caliber
        if "30-06" in title_lower or "30.06" in title_lower or "30/06" in title_lower:
            caliber = "30-06"
        elif "308" in title_lower:
            caliber = ".308 Win"
        else:
            caliber = None

        # Urgency level
        if is_auction and remaining_seconds is not None:
            if remaining_seconds <= 3600:
                urgency_level = "critical"
            elif remaining_seconds <= 21600:
                urgency_level = "warning"
            elif remaining_seconds <= 86400:
                urgency_level = "normal"
            else:
                urgency_level = "later"
        else:
            urgency_level = "buy_now"

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
                seller_reviews=seller_reviews,
                bids_count=bids_count,
                has_no_reserve=has_no_reserve,
                free_shipping=free_shipping,
                is_negotiable=is_negotiable,
                is_newly_added=is_newly_added,
                date_detected=now,
                has_optic=has_optic,
                optic_name=optic_name,
                is_threaded=is_threaded,
                has_silencer=has_silencer,
                is_left_handed=is_left_handed,
                is_stainless=is_stainless,
                stock_material=stock_material,
                urgency_level=urgency_level,
                caliber=caliber,
            )
        )

    return items


def matches_keywords(
    title: str,
    keywords_include: str | None = None,
    keywords_exclude: str | None = None,
) -> bool:
    """Filter item title by inclusion, exclusion keywords, and smart accessory heuristics."""
    title_lower = title.lower().strip()

    # Smart accessory detection: titles starting with accessory nouns
    accessory_starts = (
        "crosse ", "canon ", "chargeur ", "boitier ", "boîtier ",
        "châssis ", "chassis ", "culasse ", "kit ", "rail ",
        "embase ", "embases ", "douilles ", "etuis ", "étuis ",
        "ogives ", "amorces ", "silencieux ", "moderateur ", "modérateur "
    )
    if any(title_lower.startswith(prefix) for prefix in accessory_starts):
        return False

    # Specific phrases indicating an accessory sold separately
    accessory_patterns = (
        "crosse pour", "canon pour", "chargeur pour", "boitier pour", "boîtier pour",
        "chassis pour", "châssis pour", "conversion pour", "rail pour", "embase pour",
        "embases pour", "montage pour", "crosse seule", "canon seul", "boitier seul",
        "boîtier seul", "chargeur seul", "culasse seule", "lunette seule", "optique seule",
        "point rouge seul", "moderateur seul", "modérateur seul", "silencieux seul",
        "chassis mdt", "châssis mdt"
    )
    if any(pattern in title_lower for pattern in accessory_patterns):
        return False

    # Check exclusions
    if keywords_exclude:
        for kw in [k.strip().lower() for k in keywords_exclude.split(",") if k.strip()]:
            if kw in title_lower:
                return False

    # Check inclusions
    if keywords_include:
        include_list = [k.strip().lower() for k in keywords_include.split(",") if k.strip()]
        if include_list:
            if not any(kw in title_lower for kw in include_list):
                return False

    return True


async def async_fetch_naturabuy_page(
    session: aiohttp.ClientSession,
    url: str,
) -> list[NaturaBuyItem]:
    """Fetch and parse items from a NaturaBuy URL with resilient encoding handling and browser headers."""
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                _LOGGER.error("Failed to fetch NaturaBuy page %s, status code: %s", url, resp.status)
                return []
            raw_data = await resp.read()
            try:
                html = raw_data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    html = raw_data.decode("iso-8859-1")
                except UnicodeDecodeError:
                    html = raw_data.decode("utf-8", errors="replace")

            query_no_reserve = "PR=noPR" in url
            return parse_items_from_html(html, query_no_reserve=query_no_reserve)
    except Exception as err:
        _LOGGER.error("Error fetching NaturaBuy page %s: %s", url, err)
        return []
