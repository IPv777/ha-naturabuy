"""Binary sensor platform for NaturaBuy integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN
from .coordinator import NaturaBuyCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NaturaBuy binary sensor entities based on a config entry."""
    coordinator: NaturaBuyCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([NaturaBuyEndingAlertBinarySensor(coordinator, entry)])


class NaturaBuyEndingAlertBinarySensor(
    CoordinatorEntity[NaturaBuyCoordinator], BinarySensorEntity
):
    """Binary sensor turned ON when an auction is ending soon under max price."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NaturaBuyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_ending_alert"
        self._attr_name = "Alerte fin imminente"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"NaturaBuy - {entry.data.get(CONF_NAME, entry.title)}",
            "manufacturer": "NaturaBuy",
            "model": "Search Monitor",
            "configuration_url": coordinator.base_url,
        }

    @property
    def _urgent_auctions(self) -> list[Any]:
        """Find auctions ending within the alert lead time."""
        threshold = self.coordinator.alert_minutes * 60
        max_p = self.coordinator.max_price
        urgent = []
        for it in self.coordinator.data or []:
            if (
                it.is_auction
                and it.remaining_seconds is not None
                and 0 < it.remaining_seconds <= threshold
                and (max_p <= 0 or it.price <= max_p)
            ):
                urgent.append(it)
        return urgent

    @property
    def is_on(self) -> bool:
        """Return true if at least one auction ends soon under budget."""
        return len(self._urgent_auctions) > 0

    @property
    def icon(self) -> str:
        """Return dynamic icon."""
        return "mdi:alarm-light" if self.is_on else "mdi:alarm-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of urgent auctions."""
        urgent = self._urgent_auctions
        return {
            "urgent_count": len(urgent),
            "urgent_auctions": [a.to_dict() for a in urgent],
        }
