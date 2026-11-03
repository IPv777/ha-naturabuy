"""DataUpdateCoordinator for NaturaBuy integration with advanced filtering and rich notifications."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALERT_MINUTES,
    CONF_CONDITION,
    CONF_KEYWORDS_EXCLUDE,
    CONF_KEYWORDS_INCLUDE,
    CONF_MAX_PAGES,
    CONF_MAX_PRICE,
    CONF_MIN_PRICE,
    CONF_NAME,
    CONF_NO_RESERVE,
    CONF_NOTIFY_ENDING,
    CONF_NOTIFY_NEW,
    CONF_NOTIFY_TARGETS,
    CONF_SALE_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_SELLER_TYPE,
    CONF_URL,
    DEFAULT_ALERT_MINUTES,
    DEFAULT_CONDITION,
    DEFAULT_KEYWORDS_EXCLUDE,
    DEFAULT_KEYWORDS_INCLUDE,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_PRICE,
    DEFAULT_MIN_PRICE,
    DEFAULT_NO_RESERVE,
    DEFAULT_NOTIFY_ENDING,
    DEFAULT_NOTIFY_NEW,
    DEFAULT_SALE_TYPE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SELLER_TYPE,
    DOMAIN,
    EVENT_AUCTION_ENDING_SOON,
    EVENT_NEW_LISTING,
)
from .scraper import (
    NaturaBuyItem,
    async_fetch_naturabuy_page,
    build_search_url,
    matches_keywords,
)

_LOGGER = logging.getLogger(__name__)


class NaturaBuyCoordinator(DataUpdateCoordinator[list[NaturaBuyItem]]):
    """Coordinator to fetch and monitor NaturaBuy data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        scan_interval_minutes = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"NaturaBuy {entry.data.get(CONF_NAME, entry.title)}",
            update_interval=timedelta(minutes=scan_interval_minutes),
        )
        self.session = async_get_clientsession(hass)
        self.seen_item_ids: set[str] = set()
        self.alerted_ending_ids: set[str] = set()
        self.initial_fetch_done = False

    @property
    def base_url(self) -> str:
        """Return base search URL."""
        return self.entry.options.get(CONF_URL, self.entry.data[CONF_URL])

    @property
    def max_price(self) -> float:
        """Return max price filter."""
        return float(
            self.entry.options.get(
                CONF_MAX_PRICE,
                self.entry.data.get(CONF_MAX_PRICE, DEFAULT_MAX_PRICE),
            )
        )

    @property
    def min_price(self) -> float:
        """Return min price filter."""
        return float(
            self.entry.options.get(
                CONF_MIN_PRICE,
                self.entry.data.get(CONF_MIN_PRICE, DEFAULT_MIN_PRICE),
            )
        )

    @property
    def sale_type(self) -> str:
        """Return sale type filter."""
        return self.entry.options.get(
            CONF_SALE_TYPE,
            self.entry.data.get(CONF_SALE_TYPE, DEFAULT_SALE_TYPE),
        )

    @property
    def no_reserve(self) -> bool:
        """Return whether to filter only auctions with no reserve price."""
        return bool(
            self.entry.options.get(
                CONF_NO_RESERVE,
                self.entry.data.get(CONF_NO_RESERVE, DEFAULT_NO_RESERVE),
            )
        )

    @property
    def condition(self) -> str:
        """Return condition filter."""
        return self.entry.options.get(
            CONF_CONDITION,
            self.entry.data.get(CONF_CONDITION, DEFAULT_CONDITION),
        )

    @property
    def seller_type(self) -> str:
        """Return seller type filter."""
        return self.entry.options.get(
            CONF_SELLER_TYPE,
            self.entry.data.get(CONF_SELLER_TYPE, DEFAULT_SELLER_TYPE),
        )

    @property
    def keywords_exclude(self) -> str:
        """Return keywords to exclude."""
        return self.entry.options.get(
            CONF_KEYWORDS_EXCLUDE,
            self.entry.data.get(CONF_KEYWORDS_EXCLUDE, DEFAULT_KEYWORDS_EXCLUDE),
        )

    @property
    def keywords_include(self) -> str:
        """Return keywords to include."""
        return self.entry.options.get(
            CONF_KEYWORDS_INCLUDE,
            self.entry.data.get(CONF_KEYWORDS_INCLUDE, DEFAULT_KEYWORDS_INCLUDE),
        )

    @property
    def max_pages(self) -> int:
        """Return max pages to scan."""
        return int(
            self.entry.options.get(
                CONF_MAX_PAGES,
                self.entry.data.get(CONF_MAX_PAGES, DEFAULT_MAX_PAGES),
            )
        )

    @property
    def notify_new(self) -> bool:
        """Return whether to notify on new listings."""
        return self.entry.options.get(
            CONF_NOTIFY_NEW,
            self.entry.data.get(CONF_NOTIFY_NEW, DEFAULT_NOTIFY_NEW),
        )

    @property
    def notify_ending(self) -> bool:
        """Return whether to notify on auctions ending soon."""
        return self.entry.options.get(
            CONF_NOTIFY_ENDING,
            self.entry.data.get(CONF_NOTIFY_ENDING, DEFAULT_NOTIFY_ENDING),
        )

    @property
    def alert_minutes(self) -> int:
        """Return alert threshold before auction end in minutes."""
        return int(
            self.entry.options.get(
                CONF_ALERT_MINUTES,
                self.entry.data.get(CONF_ALERT_MINUTES, DEFAULT_ALERT_MINUTES),
            )
        )

    @property
    def notify_targets(self) -> list[str]:
        """Return list of notify service names."""
        targets = self.entry.options.get(
            CONF_NOTIFY_TARGETS,
            self.entry.data.get(CONF_NOTIFY_TARGETS, []),
        )
        if isinstance(targets, str):
            return [targets]
        return list(targets)

    async def _async_update_data(self) -> list[NaturaBuyItem]:
        """Fetch items from NaturaBuy across pages and process notifications."""
        try:
            unique_items: dict[str, NaturaBuyItem] = {}

            # Scan pages for ending soon and newly listed
            for page in range(1, self.max_pages + 1):
                # 1. Ending soonest
                ends_url = build_search_url(
                    self.base_url,
                    max_price=self.max_price,
                    min_price=self.min_price,
                    sort="ends",
                    sale_type=self.sale_type,
                    no_reserve=self.no_reserve,
                    condition=self.condition,
                    seller_type=self.seller_type,
                    page=page,
                )
                items_ends = await async_fetch_naturabuy_page(self.session, ends_url)
                for item in items_ends:
                    if item.id not in unique_items:
                        unique_items[item.id] = item

                await asyncio.sleep(0.3)

                # 2. Newly listed
                starts_url = build_search_url(
                    self.base_url,
                    max_price=self.max_price,
                    min_price=self.min_price,
                    sort="starts",
                    sale_type=self.sale_type,
                    no_reserve=self.no_reserve,
                    condition=self.condition,
                    seller_type=self.seller_type,
                    page=page,
                )
                items_starts = await async_fetch_naturabuy_page(self.session, starts_url)
                for item in items_starts:
                    if item.id not in unique_items:
                        unique_items[item.id] = item

                await asyncio.sleep(0.3)

            # Apply keyword filters
            filtered_items: list[NaturaBuyItem] = []
            for item in unique_items.values():
                if matches_keywords(
                    item.title,
                    keywords_include=self.keywords_include,
                    keywords_exclude=self.keywords_exclude,
                ):
                    filtered_items.append(item)

            # Sort items: auctions ending soonest first, then newest
            filtered_items.sort(
                key=lambda x: (
                    0 if (x.is_auction and x.remaining_seconds is not None) else 1,
                    x.remaining_seconds if (x.is_auction and x.remaining_seconds is not None) else 999999999,
                )
            )

            # Process notifications
            await self._process_notifications(filtered_items)

            return filtered_items

        except Exception as err:
            _LOGGER.error("Failed to update NaturaBuy data for %s: %s", self.name, err)
            raise UpdateFailed(f"Error communicating with NaturaBuy: {err}") from err

    async def _process_notifications(self, items: list[NaturaBuyItem]) -> None:
        """Check items for new listings and ending auctions."""
        alert_seconds = self.alert_minutes * 60

        for item in items:
            # Filter check
            if self.max_price > 0 and item.price > self.max_price:
                continue
            if self.min_price > 0 and item.price < self.min_price:
                continue

            # 1. New listing check
            if self.initial_fetch_done and self.notify_new:
                if item.id not in self.seen_item_ids:
                    _LOGGER.info("New NaturaBuy listing detected: %s (%s)", item.title, item.price_str)
                    badge = "🎯 Enchère" if item.is_auction else "⚡ Achat Immédiat"
                    shipping_txt = " | 📦 Livraison gratuite" if item.free_shipping else ""
                    reserve_txt = " (Sans prix de réserve)" if item.has_no_reserve else ""

                    await self._send_notification(
                        title=f"🆕 [NaturaBuy] {item.title[:38]}",
                        message=(
                            f"Prix : {item.price_str} ({badge}{reserve_txt})\n"
                            f"État : {item.condition or 'Occasion'} ({item.seller_type or 'Vendeur'}){shipping_txt}"
                        ),
                        item=item,
                        event_type=EVENT_NEW_LISTING,
                        tag=f"naturabuy_new_{item.id}",
                    )

            # 2. Auction ending soon check
            if self.notify_ending and item.is_auction and item.remaining_seconds is not None:
                if 0 < item.remaining_seconds <= alert_seconds:
                    if item.id not in self.alerted_ending_ids:
                        _LOGGER.info(
                            "NaturaBuy auction ending soon: %s (in %s)",
                            item.title,
                            item.remaining_time_str,
                        )
                        bids_txt = f"{item.bids_count} offre(s)" if item.bids_count > 0 else "0 offre"
                        reserve_txt = " (Sans réserve)" if item.has_no_reserve else ""

                        await self._send_notification(
                            title=f"⏳ [NaturaBuy < {self.alert_minutes}m] {item.title[:32]}",
                            message=(
                                f"Enchère : {item.price_str} ({bids_txt}{reserve_txt})\n"
                                f"Temps restant : {item.remaining_time_str}\n"
                                f"Limite : sous votre budget de {self.max_price:.0f} €"
                            ),
                            item=item,
                            event_type=EVENT_AUCTION_ENDING_SOON,
                            tag=f"naturabuy_ending_{item.id}",
                            high_priority=True,
                        )
                        self.alerted_ending_ids.add(item.id)

            # Mark as seen
            self.seen_item_ids.add(item.id)

        self.initial_fetch_done = True

    async def _send_notification(
        self,
        title: str,
        message: str,
        item: NaturaBuyItem,
        event_type: str,
        tag: str | None = None,
        high_priority: bool = False,
    ) -> None:
        """Send rich notification tailored for ThinkPhone / Android Companion app and fire event."""
        # 1. Fire Home Assistant Bus event
        event_payload = item.to_dict()
        event_payload["watch_name"] = self.name
        self.hass.bus.async_fire(event_type, event_payload)

        # 2. Build rich Android Companion App notification payload
        targets = self.notify_targets
        if not targets:
            targets = ["notify.persistent_notification"]

        data_payload: dict[str, Any] = {
            "url": item.url,
            "clickAction": item.url,
            "tag": tag or f"naturabuy_{item.id}",
            "channel": "NaturaBuy Alertes",
            "color": "#27ae60",
            "actions": [
                {
                    "action": "URI",
                    "title": "🎯 Voir sur NaturaBuy",
                    "uri": item.url,
                }
            ],
        }

        if high_priority:
            data_payload["importance"] = "high"
            data_payload["priority"] = "high"
            data_payload["visibility"] = "public"
            data_payload["vibrationPattern"] = "100, 200, 100, 200"

        if item.image_url:
            data_payload["image"] = item.image_url

        notification_data: dict[str, Any] = {
            "title": title,
            "message": message,
            "data": data_payload,
        }

        for target in targets:
            try:
                if "." in target:
                    domain, service = target.split(".", 1)
                else:
                    domain, service = "notify", target

                await self.hass.services.async_call(
                    domain,
                    service,
                    notification_data,
                    blocking=False,
                )
            except Exception as err:
                _LOGGER.error("Failed to send NaturaBuy notification via %s: %s", target, err)
