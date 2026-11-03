"""DataUpdateCoordinator for NaturaBuy with persistent cache, adaptive turbo mode, outbid tracking and ThinkPhone actions."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ACTION_MUTE,
    ACTION_REFRESH,
    CONF_ALERT_MINUTES,
    CONF_BRAND,
    CONF_CONDITION,
    CONF_DEPARTMENT,
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
    CONF_TURBO_MODE,
    CONF_URL,
    DEFAULT_ALERT_MINUTES,
    DEFAULT_BRAND,
    DEFAULT_CONDITION,
    DEFAULT_DEPARTMENT,
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
    DEFAULT_TURBO_MODE,
    DOMAIN,
    EVENT_AUCTION_BUDGET_EXCEEDED,
    EVENT_AUCTION_ENDING_SOON,
    EVENT_AUCTION_EXTENDED,
    EVENT_AUCTION_OUTBID,
    EVENT_NEW_LISTING,
    TURBO_SCAN_INTERVAL,
)
from .scraper import (
    NaturaBuyItem,
    async_fetch_naturabuy_page,
    build_search_url,
    matches_keywords,
)

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


class NaturaBuyCoordinator(DataUpdateCoordinator[list[NaturaBuyItem]]):
    """Coordinator to fetch and monitor NaturaBuy data with persistence and turbo mode."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.normal_scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"NaturaBuy {entry.data.get(CONF_NAME, entry.title)}",
            update_interval=timedelta(minutes=self.normal_scan_interval),
        )
        self.session = async_get_clientsession(hass)
        self.store = Store(hass, STORAGE_VERSION, f"naturabuy_{entry.entry_id}")
        self.seen_item_ids: set[str] = set()
        self.alerted_ending_ids: set[str] = set()
        self.muted_item_ids: set[str] = set()
        self.last_known_bids: dict[str, float] = {}
        self.last_remaining_seconds: dict[str, int] = {}
        self.initial_fetch_done = False
        self.is_turbo_active = False

    @property
    def base_url(self) -> str:
        """Return base search URL."""
        return self.entry.options.get(CONF_URL, self.entry.data[CONF_URL])

    @property
    def department(self) -> str:
        """Return department filter."""
        return self.entry.options.get(
            CONF_DEPARTMENT,
            self.entry.data.get(CONF_DEPARTMENT, DEFAULT_DEPARTMENT),
        )

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
    def brand(self) -> str:
        """Return brand filter."""
        return self.entry.options.get(
            CONF_BRAND,
            self.entry.data.get(CONF_BRAND, DEFAULT_BRAND),
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
    def turbo_mode(self) -> bool:
        """Return whether turbo polling is enabled during end-of-auction sprint."""
        return bool(
            self.entry.options.get(
                CONF_TURBO_MODE,
                self.entry.data.get(CONF_TURBO_MODE, DEFAULT_TURBO_MODE),
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
            self.entry.data.get(CONF_NOTIFY_TARGETS, ["notify.mobile_app_thinkphone_by_motorola"]),
        )
        if isinstance(targets, str):
            return [targets]
        return list(targets)

    async def async_load_storage(self) -> None:
        """Load persisted cache from disk."""
        stored = await self.store.async_load()
        if stored and isinstance(stored, dict):
            self.seen_item_ids = set(stored.get("seen_ids", []))
            self.alerted_ending_ids = set(stored.get("alerted_ending_ids", []))
            self.muted_item_ids = set(stored.get("muted_ids", []))
            self.last_known_bids = stored.get("last_known_bids", {})
            self.initial_fetch_done = True
            _LOGGER.debug(
                "Restored NaturaBuy cache for %s (%d seen items, %d muted)",
                self.name,
                len(self.seen_item_ids),
                len(self.muted_item_ids),
            )

    async def async_save_storage(self) -> None:
        """Persist cache to disk."""
        await self.store.async_save(
            {
                "seen_ids": list(self.seen_item_ids),
                "alerted_ending_ids": list(self.alerted_ending_ids),
                "muted_ids": list(self.muted_item_ids),
                "last_known_bids": self.last_known_bids,
            }
        )

    async def async_reset_cache(self) -> None:
        """Reset seen cache to rediscover all items (preserving muted items)."""
        self.seen_item_ids.clear()
        self.alerted_ending_ids.clear()
        self.last_known_bids.clear()
        self.last_remaining_seconds.clear()
        self.initial_fetch_done = False
        await self.async_save_storage()
        await self.async_request_refresh()

    async def async_mute_item(self, item_id: str) -> None:
        """Mute an item so it never triggers alerts or appears in active list."""
        self.muted_item_ids.add(str(item_id))
        await self.async_save_storage()
        _LOGGER.info("Item %s muted for %s", item_id, self.name)
        # Clear notification from ThinkPhone if currently active
        targets = self.notify_targets
        for target in targets:
            service_name = target.replace("notify.", "")
            try:
                await self.hass.services.async_call(
                    "notify",
                    service_name,
                    {
                        "message": "clear_notification",
                        "data": {"tag": f"naturabuy_{item_id}"},
                    },
                )
            except Exception as err:
                _LOGGER.debug("Could not clear notification for %s: %s", item_id, err)
        await self.async_request_refresh()

    async def async_unmute_item(self, item_id: str) -> None:
        """Unmute an item."""
        self.muted_item_ids.discard(str(item_id))
        await self.async_save_storage()
        _LOGGER.info("Item %s unmuted for %s", item_id, self.name)
        await self.async_request_refresh()

    async def async_set_max_price(self, new_price: float) -> None:
        """Dynamically update maximum price budget and trigger a refresh."""
        new_options = dict(self.entry.options)
        new_options[CONF_MAX_PRICE] = float(new_price)
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        _LOGGER.info("Updated max budget to %.2f € for %s", new_price, self.name)
        await self.async_request_refresh()

    async def _async_update_data(self) -> list[NaturaBuyItem]:
        """Fetch items across pages, manage turbo mode and process smart notifications."""
        try:
            if not self.initial_fetch_done:
                await self.async_load_storage()

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
                    brand=self.brand,
                    department=self.department,
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
                    brand=self.brand,
                    department=self.department,
                    page=page,
                )
                items_starts = await async_fetch_naturabuy_page(self.session, starts_url)
                for item in items_starts:
                    if item.id not in unique_items:
                        unique_items[item.id] = item

                await asyncio.sleep(0.3)

            # Apply muted and keyword exclusion/inclusion filters
            filtered_items: list[NaturaBuyItem] = []
            for item in unique_items.values():
                if item.id in self.muted_item_ids:
                    continue
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

            # Check for Adaptive Polling (Turbo Mode):
            # If an auction is ending within 30 min and under max price, accelerate polling to 2 min
            has_imminent_auction = any(
                it.is_auction
                and it.remaining_seconds is not None
                and 0 < it.remaining_seconds <= 1800
                and (self.max_price <= 0 or it.price <= self.max_price)
                for it in filtered_items
            )

            if self.turbo_mode and has_imminent_auction and not self.is_turbo_active:
                _LOGGER.info("Activating Turbo Polling Mode (2 min interval) for %s", self.name)
                self.update_interval = timedelta(minutes=TURBO_SCAN_INTERVAL)
                self.is_turbo_active = True
            elif self.is_turbo_active and not has_imminent_auction:
                _LOGGER.info("Restoring normal scan interval (%d min) for %s", self.normal_scan_interval, self.name)
                self.update_interval = timedelta(minutes=self.normal_scan_interval)
                self.is_turbo_active = False

            # Process notifications
            await self._process_notifications(filtered_items)

            # Persist updated cache
            await self.async_save_storage()

            return filtered_items

        except Exception as err:
            _LOGGER.error("Failed to update NaturaBuy data for %s: %s", self.name, err)
            raise UpdateFailed(f"Error communicating with NaturaBuy: {err}") from err

    async def _process_notifications(self, items: list[NaturaBuyItem]) -> None:
        """Check items for new listings, ending auctions, and outbids."""
        alert_seconds = self.alert_minutes * 60

        for item in items:
            # Price bounds check
            if self.max_price > 0 and item.price > self.max_price:
                # If an auction previously tracked now exceeds max_price in the final hour
                if (
                    item.id in self.alerted_ending_ids
                    and item.is_auction
                    and item.remaining_seconds is not None
                    and 0 < item.remaining_seconds <= alert_seconds
                ):
                    last_bid = self.last_known_bids.get(item.id, 0.0)
                    if last_bid <= self.max_price:
                        _LOGGER.info("NaturaBuy auction exceeded budget: %s (%s)", item.title, item.price_str)
                        await self._send_notification(
                            title=f"❌ [Budget dépassé] {item.title[:30]}",
                            message=(
                                f"L'enchère a grimpé à {item.price_str} et dépasse votre plafond de {self.max_price:.0f} €.\n"
                                f"Fin dans : {item.remaining_time_str}"
                            ),
                            item=item,
                            event_type=EVENT_AUCTION_BUDGET_EXCEEDED,
                            tag=f"naturabuy_{item.id}",
                            high_priority=False,
                        )
                        self.last_known_bids[item.id] = item.price
                continue

            if self.min_price > 0 and item.price < self.min_price:
                continue

            # 1. New listing check
            if self.initial_fetch_done and self.notify_new:
                if item.id not in self.seen_item_ids:
                    _LOGGER.info("New NaturaBuy listing detected: %s (%s)", item.title, item.price_str)
                    badge = "🎯 Enchère" if item.is_auction else "⚡ Achat Immédiat"
                    shipping_txt = " | 📦 Port gratuit" if item.free_shipping else ""
                    reserve_txt = " (Sans réserve)" if item.has_no_reserve else ""
                    reviews_txt = f" | ⭐ Vendeur ({item.seller_reviews} avis)" if item.seller_reviews else ""
                    nego_txt = " | 💬 Prix négociable" if item.is_negotiable else ""

                    await self._send_notification(
                        title=f"🆕 [NaturaBuy] {item.title[:36]}",
                        message=(
                            f"Prix : {item.price_str} ({badge}{reserve_txt})\n"
                            f"État : {item.condition or 'Occasion'} ({item.seller_type or 'Vendeur'}){shipping_txt}{reviews_txt}{nego_txt}"
                        ),
                        item=item,
                        event_type=EVENT_NEW_LISTING,
                        tag=f"naturabuy_{item.id}",
                    )

            # 2. Auction ending soon check & outbid tracking
            if self.notify_ending and item.is_auction and item.remaining_seconds is not None:
                if 0 < item.remaining_seconds <= alert_seconds:
                    bids_txt = f"{item.bids_count} offre(s)" if item.bids_count > 0 else "0 offre"
                    reserve_txt = " (Sans réserve)" if item.has_no_reserve else ""

                    if item.id not in self.alerted_ending_ids:
                        _LOGGER.info("NaturaBuy auction ending soon: %s (in %s)", item.title, item.remaining_time_str)
                        await self._send_notification(
                            title=f"⏳ [Fin dans {item.remaining_time_str}] {item.title[:28]}",
                            message=(
                                f"Enchère en cours : {item.price_str} ({bids_txt}{reserve_txt})\n"
                                f"Plafond : {self.max_price:.0f} € | Cliquez pour enchérir."
                            ),
                            item=item,
                            event_type=EVENT_AUCTION_ENDING_SOON,
                            tag=f"naturabuy_{item.id}",
                            high_priority=True,
                        )
                        self.alerted_ending_ids.add(item.id)
                        self.last_known_bids[item.id] = item.price

                    elif item.id in self.last_known_bids:
                        last_bid = self.last_known_bids[item.id]
                        if item.price > last_bid:
                            _LOGGER.info("NaturaBuy auction outbid update: %s -> %s", item.title, item.price_str)
                            await self._send_notification(
                                title=f"📈 [Surenchère !] {item.title[:30]}",
                                message=(
                                    f"Nouvelle offre : {item.price_str} (était {last_bid:.2f} €)\n"
                                    f"Temps restant : {item.remaining_time_str} ({bids_txt})\n"
                                    f"Reste sous votre budget ({self.max_price:.0f} €)."
                                ),
                                item=item,
                                event_type=EVENT_AUCTION_OUTBID,
                                tag=f"naturabuy_{item.id}",
                                high_priority=True,
                            )
                            self.last_known_bids[item.id] = item.price

                    # Anti-sniping prolongation check: if remaining seconds jumped back up
                    prev_rem = self.last_remaining_seconds.get(item.id)
                    if (
                        prev_rem is not None
                        and prev_rem <= 330
                        and item.remaining_seconds is not None
                        and item.remaining_seconds > prev_rem + 120
                    ):
                        _LOGGER.info("NaturaBuy anti-sniping extension for %s: +%ds", item.title, item.remaining_seconds - prev_rem)
                        await self._send_notification(
                            title=f"⏱️ [Prolongation Anti-Sniping !] {item.title[:24]}",
                            message=(
                                f"L'enchère a été prolongée de 5 min suite à une enchère de dernière minute !\n"
                                f"Nouveau temps : {item.remaining_time_str} | Prix : {item.price_str} ({bids_txt})"
                            ),
                            item=item,
                            event_type=EVENT_AUCTION_EXTENDED,
                            tag=f"naturabuy_{item.id}",
                            high_priority=True,
                        )

                    if item.remaining_seconds is not None:
                        self.last_remaining_seconds[item.id] = item.remaining_seconds

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
        """Send actionable notification tailored for ThinkPhone and fire event."""
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
                    "title": "🎯 Voir l'annonce",
                    "uri": item.url,
                },
                {
                    "action": ACTION_REFRESH,
                    "title": "🔄 Actualiser",
                },
                {
                    "action": ACTION_MUTE,
                    "title": "🔕 Ignorer",
                },
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
