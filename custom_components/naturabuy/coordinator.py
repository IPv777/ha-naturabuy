"""DataUpdateCoordinator for NaturaBuy integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALERT_MINUTES,
    CONF_MAX_PRICE,
    CONF_MIN_PRICE,
    CONF_NAME,
    CONF_NOTIFY_ENDING,
    CONF_NOTIFY_NEW,
    CONF_NOTIFY_TARGETS,
    CONF_SALE_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DEFAULT_ALERT_MINUTES,
    DEFAULT_MAX_PRICE,
    DEFAULT_MIN_PRICE,
    DEFAULT_NOTIFY_ENDING,
    DEFAULT_NOTIFY_NEW,
    DEFAULT_SALE_TYPE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_AUCTION_ENDING_SOON,
    EVENT_NEW_LISTING,
)
from .scraper import NaturaBuyItem, async_fetch_naturabuy_page, build_search_url

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
        """Fetch items from NaturaBuy and process notifications."""
        try:
            # 1. Fetch ending soonest
            ends_url = build_search_url(
                self.base_url,
                max_price=self.max_price,
                min_price=self.min_price,
                sort="ends",
                sale_type=self.sale_type,
            )
            # 2. Fetch newly listed
            starts_url = build_search_url(
                self.base_url,
                max_price=self.max_price,
                min_price=self.min_price,
                sort="starts",
                sale_type=self.sale_type,
            )

            items_ends = await async_fetch_naturabuy_page(self.session, ends_url)
            items_starts = await async_fetch_naturabuy_page(self.session, starts_url)

            # Combine items uniquely
            unique_items: dict[str, NaturaBuyItem] = {}
            for item in items_ends + items_starts:
                if item.id not in unique_items:
                    unique_items[item.id] = item

            items_list = list(unique_items.values())

            # Process notifications
            await self._process_notifications(items_list)

            return items_list

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
                    await self._send_notification(
                        title=f"🆕 [NaturaBuy] {item.title[:35]}",
                        message=(
                            f"Prix : {item.price_str}\n"
                            f"Type : {'Enchère' if item.is_auction else 'Achat Immédiat'}\n"
                            f"État : {item.condition or 'Non spécifié'}"
                        ),
                        item=item,
                        event_type=EVENT_NEW_LISTING,
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
                        await self._send_notification(
                            title=f"⏳ [NaturaBuy] Enchère se terminant : {item.title[:30]}",
                            message=(
                                f"Enchère en cours : {item.price_str}\n"
                                f"Temps restant : {item.remaining_time_str}\n"
                                f"Limite : sous {self.max_price} €"
                            ),
                            item=item,
                            event_type=EVENT_AUCTION_ENDING_SOON,
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
    ) -> None:
        """Send notification to targets and fire HA event."""
        # 1. Fire Home Assistant Bus event
        event_payload = item.to_dict()
        event_payload["watch_name"] = self.name
        self.hass.bus.async_fire(event_type, event_payload)

        # 2. Send notifications to targets
        targets = self.notify_targets
        if not targets:
            # Fallback to persistent notification if no target configured
            targets = ["notify.persistent_notification"]

        notification_data: dict[str, Any] = {
            "title": title,
            "message": message,
            "data": {
                "url": item.url,
                "clickAction": item.url,
            },
        }
        if item.image_url:
            notification_data["data"]["image"] = item.image_url

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
