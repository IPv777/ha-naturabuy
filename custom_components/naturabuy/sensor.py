"""Sensor platform for NaturaBuy integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN
from .coordinator import NaturaBuyCoordinator
from .scraper import NaturaBuyItem

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NaturaBuy sensor entities based on a config entry."""
    coordinator: NaturaBuyCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        NaturaBuyTotalItemsSensor(coordinator, entry),
        NaturaBuyActiveAuctionsSensor(coordinator, entry),
        NaturaBuyNextEndingAuctionSensor(coordinator, entry),
        NaturaBuyLatestItemSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class NaturaBuyBaseSensor(CoordinatorEntity[NaturaBuyCoordinator], SensorEntity):
    """Base sensor for NaturaBuy entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NaturaBuyCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the base sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"NaturaBuy - {entry.data.get(CONF_NAME, entry.title)}",
            "manufacturer": "NaturaBuy",
            "model": "Search Monitor",
            "configuration_url": coordinator.base_url,
        }


class NaturaBuyTotalItemsSensor(NaturaBuyBaseSensor):
    """Sensor showing total matching items with Markdown table for Lovelace."""

    def __init__(self, coordinator: NaturaBuyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "total_items")
        self._attr_name = "Total annonces"
        self._attr_icon = "mdi:tag-search"
        self._attr_native_unit_of_measurement = "annonces"

    @property
    def native_value(self) -> int:
        """Return total items count."""
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return top items attributes and markdown summary."""
        items = self.coordinator.data or []

        # Generate rich markdown table with ratings and badges
        md_lines = ["| Arme | Prix | Type | Fin | Vendeur |", "| :--- | :---: | :---: | :---: | :---: |"]
        for it in items[:12]:
            title_clean = it.title.replace("|", "-")
            link = f"[{title_clean[:28]}]({it.url})"
            type_badge = "Enchère" if it.is_auction else "Achat Immd."
            if it.has_no_reserve and it.is_auction:
                type_badge += " (Sans PR)"
            if it.free_shipping:
                type_badge += " 📦"
            if it.is_negotiable:
                type_badge += " 💬"
            rem = it.remaining_time_str or "En vente"
            seller_str = f"⭐ ({it.seller_reviews})" if it.seller_reviews else (it.seller_type or "N/A")
            md_lines.append(f"| {link} | **{it.price_str}** | {type_badge} | {rem} | {seller_str} |")

        markdown_summary = "\n".join(md_lines)

        return {
            "max_price": self.coordinator.max_price,
            "min_price": self.coordinator.min_price,
            "sale_type": self.coordinator.sale_type,
            "no_reserve": self.coordinator.no_reserve,
            "brand": self.coordinator.brand,
            "department": self.coordinator.department,
            "muted_items_count": len(self.coordinator.muted_item_ids),
            "is_turbo_active": self.coordinator.is_turbo_active,
            "url": self.coordinator.base_url,
            "markdown_table": markdown_summary,
            "items_sample": [item.to_dict() for item in items[:8]],
        }


class NaturaBuyActiveAuctionsSensor(NaturaBuyBaseSensor):
    """Sensor showing active auctions count."""

    def __init__(self, coordinator: NaturaBuyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "active_auctions")
        self._attr_name = "Enchères actives"
        self._attr_icon = "mdi:gavel"
        self._attr_native_unit_of_measurement = "enchères"

    @property
    def native_value(self) -> int:
        """Return active auctions count."""
        items = self.coordinator.data or []
        return sum(1 for it in items if it.is_auction)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details on active auctions."""
        auctions = [it for it in (self.coordinator.data or []) if it.is_auction]
        return {
            "auctions_count": len(auctions),
            "no_reserve_count": sum(1 for a in auctions if a.has_no_reserve),
            "auctions": [a.to_dict() for a in auctions[:5]],
        }


class NaturaBuyNextEndingAuctionSensor(NaturaBuyBaseSensor):
    """Sensor showing the next ending auction."""

    def __init__(self, coordinator: NaturaBuyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "next_ending_auction")
        self._attr_name = "Prochaine fin d'enchère"
        self._attr_icon = "mdi:clock-alert-outline"

    @property
    def _next_auction(self) -> NaturaBuyItem | None:
        """Find the auction with the smallest remaining seconds."""
        auctions = [it for it in (self.coordinator.data or []) if it.is_auction and it.remaining_seconds is not None]
        if not auctions:
            return None
        return min(auctions, key=lambda x: x.remaining_seconds or 999999999)

    @property
    def native_value(self) -> str:
        """Return title of next ending auction."""
        next_it = self._next_auction
        return next_it.title if next_it else "Aucune enchère en cours"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the next ending auction."""
        next_it = self._next_auction
        if not next_it:
            return {}
        return next_it.to_dict()


class NaturaBuyLatestItemSensor(NaturaBuyBaseSensor):
    """Sensor showing the latest listed item."""

    def __init__(self, coordinator: NaturaBuyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "latest_item")
        self._attr_name = "Dernière annonce"
        self._attr_icon = "mdi:new-box"

    @property
    def native_value(self) -> str:
        """Return title of the latest item."""
        items = self.coordinator.data or []
        return items[0].title if items else "Aucune annonce"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the latest item."""
        items = self.coordinator.data or []
        if not items:
            return {}
        return items[0].to_dict()
