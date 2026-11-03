"""Sensor platform for NaturaBuy integration with rich card grids, hunting filters and metrics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN
from .coordinator import NaturaBuyCoordinator
from .scraper import NaturaBuyItem

_LOGGER = logging.getLogger(__name__)


def build_cards_grid_html(items: list[NaturaBuyItem], empty_message: str = "") -> str:
    """Build a modern, responsive HTML/CSS grid of weapon product cards for Lovelace."""
    if not items:
        msg = empty_message or "Aucune carabine sous le budget actuellement"
        return (
            "<div style='padding: 24px 16px; text-align: center; background: var(--card-background-color, rgba(255,255,255,0.04)); "
            "border: 1px dashed var(--divider-color, rgba(255,255,255,0.15)); border-radius: 12px; margin-top: 8px;'>"
            "<div style='font-size: 28px; margin-bottom: 6px;'>🎯</div>"
            f"<div style='font-size: 15px; font-weight: 600; color: var(--primary-text-color, #fff);'>{msg}</div>"
            "<div style='font-size: 12px; color: var(--secondary-text-color, #aaa); margin-top: 4px;'>"
            "Le radar est en veille active et alertera immédiatement votre ThinkPhone dès publication.</div>"
            "</div>"
        )

    cards = []
    for it in items[:24]:
        title_clean = it.title.replace('"', "&quot;")
        short_title = it.title[:45] + ("..." if len(it.title) > 45 else "")
        img_src = it.image_url or "https://static.naturabuy.fr/themes/common/img/logo.svg"

        # Caliber & mechanism
        cal_str = it.caliber or ("30-06" if ("30-06" in it.url or "152850" in it.url or "1329" in it.url) else ".308 Win")
        type_bg = "#ff7000" if it.is_auction else "#183f33"
        type_txt = f"⚡ Enchère ({it.bids_count})" if it.is_auction else "🛒 Achat Immédiat"

        # Urgency chip
        urgency_chip = ""
        if it.is_auction and it.remaining_time_str:
            if it.urgency_level == "critical":
                urg_bg = "#d32f2f"
                urg_icon = "🚨"
            elif it.urgency_level == "warning":
                urg_bg = "#f57c00"
                urg_icon = "⏳"
            else:
                urg_bg = "rgba(0,0,0,0.65)"
                urg_icon = "⏱️"
            urgency_chip = (
                f"<span style='background: {urg_bg}; color: #fff; font-size: 10.5px; font-weight: 700; "
                f"padding: 2px 7px; border-radius: 6px; backdrop-filter: blur(4px); box-shadow: 0 2px 4px rgba(0,0,0,0.3);'>"
                f"{urg_icon} {it.remaining_time_str}</span>"
            )

        # Feature pills
        pills = []
        if it.has_optic:
            optic_lbl = it.optic_name or "Optique"
            pills.append(f"<span style='background: rgba(0, 150, 136, 0.18); color: #26a69a; border: 1px solid rgba(38,166,154,0.35); font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 4px;'>🔭 {optic_lbl}</span>")
        if it.is_threaded:
            pills.append("<span style='background: rgba(63, 81, 181, 0.18); color: #7986cb; border: 1px solid rgba(121,134,203,0.35); font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 4px;'>🔩 Canon Fileté</span>")
        if it.has_silencer:
            pills.append("<span style='background: rgba(76, 175, 80, 0.18); color: #81c784; border: 1px solid rgba(129,199,132,0.35); font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 4px;'>🤫 Modérateur</span>")
        if it.is_left_handed:
            pills.append("<span style='background: rgba(244, 67, 54, 0.22); color: #e57373; border: 1px solid rgba(229,115,115,0.45); font-size: 10.5px; font-weight: 700; padding: 1px 6px; border-radius: 4px;'>⚠️ GAUCHER</span>")
        if it.is_stainless:
            pills.append("<span style='background: rgba(158, 158, 158, 0.18); color: #e0e0e0; border: 1px solid rgba(224,224,224,0.35); font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 4px;'>⚙️ Inox</span>")
        if it.free_shipping:
            pills.append("<span style='background: rgba(255, 152, 0, 0.18); color: #ffb74d; border: 1px solid rgba(255,183,77,0.35); font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 4px;'>📦 Port Gratuit</span>")
        if it.has_no_reserve and it.is_auction:
            pills.append("<span style='background: rgba(156, 39, 176, 0.18); color: #ba68c8; border: 1px solid rgba(186,104,200,0.35); font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 4px;'>🎯 Sans PR</span>")
        if it.is_negotiable:
            pills.append("<span style='background: rgba(33, 150, 243, 0.18); color: #64b5f6; border: 1px solid rgba(100,181,246,0.35); font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 4px;'>💬 Négociable</span>")

        pills_html = " ".join(pills) if pills else "<span style='font-size: 10.5px; color: var(--secondary-text-color, #888);'>Carabine nue</span>"
        seller_label = f"⭐ ({it.seller_reviews} avis)" if it.seller_reviews else (f"👤 {it.seller_type or 'Vendeur'}")

        card_html = f"""<div style="background: var(--card-background-color, #1e1e24); border: 1px solid var(--divider-color, rgba(255,255,255,0.08)); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 3px 10px rgba(0,0,0,0.18);">
  <div style="position: relative; width: 100%; height: 135px; background: #121214; overflow: hidden;">
    <a href="{it.url}" target="_blank" style="display: block; width: 100%; height: 100%;">
      <img src="{img_src}" alt="{title_clean}" style="width: 100%; height: 100%; object-fit: cover;" loading="lazy">
    </a>
    <div style="position: absolute; top: 8px; left: 8px; display: flex; gap: 4px; flex-wrap: wrap;">
      <span style="background: rgba(24,63,51,0.9); color: #fff; font-size: 10.5px; font-weight: 700; padding: 2px 7px; border-radius: 6px; backdrop-filter: blur(4px);">{cal_str}</span>
      <span style="background: {type_bg}; color: #fff; font-size: 10.5px; font-weight: 700; padding: 2px 7px; border-radius: 6px; backdrop-filter: blur(4px);">{type_txt}</span>
    </div>
    <div style="position: absolute; top: 8px; right: 8px;">
      {urgency_chip}
    </div>
  </div>
  <div style="padding: 11px 12px; display: flex; flex-direction: column; flex-grow: 1; justify-content: space-between;">
    <div>
      <a href="{it.url}" target="_blank" style="text-decoration: none; color: var(--primary-text-color, #fff); font-size: 13px; font-weight: 700; line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;" title="{title_clean}">
        {short_title}
      </a>
      <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 7px;">
        {pills_html}
      </div>
    </div>
    <div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--divider-color, rgba(255,255,255,0.08)); display: flex; align-items: center; justify-content: space-between;">
      <div>
        <div style="font-size: 18px; font-weight: 800; color: #ff7000; line-height: 1;">{it.price_str}</div>
        <div style="font-size: 11px; color: var(--secondary-text-color, #aaa); margin-top: 3px;">{seller_label}</div>
      </div>
      <a href="{it.url}" target="_blank" style="display: inline-flex; align-items: center; gap: 4px; background: #183f33; color: #fff; text-decoration: none; font-size: 11.5px; font-weight: 700; padding: 6px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);">
        Voir 🎯
      </a>
    </div>
  </div>
</div>"""
        cards.append(card_html)

    joined_cards = "\n".join(cards)
    return f'<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 14px; margin-top: 8px;">\n{joined_cards}\n</div>'


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
        NaturaBuyMinPriceSensor(coordinator, entry),
        NaturaBuyEquippedItemsSensor(coordinator, entry),
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
    """Sensor showing total matching items with visual cards grid and full item attributes."""

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
        """Return top items attributes, full items array, and visual card grid."""
        items = self.coordinator.data or []

        # Equipped items subset
        equipped = [it for it in items if it.has_optic or it.is_threaded or it.has_silencer]

        # Cheapest item
        cheapest_dict = min(items, key=lambda x: x.price).to_display_dict() if items else {}

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
            "items": [item.to_display_dict() for item in items[:18]],
            "cheapest_item": cheapest_dict,
            "equipped_count": len(equipped),
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
            "auctions": [a.to_display_dict() for a in auctions[:10]],
        }


class NaturaBuyNextEndingAuctionSensor(NaturaBuyBaseSensor):
    """Sensor showing the next ending auction."""

    def __init__(self, coordinator: NaturaBuyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "next_ending_auction")
        self._attr_name = "Prochaine fin d'enchère"
        self._attr_icon = "mdi:clock-alert-outline"

    def _next_auction(self) -> NaturaBuyItem | None:
        """Find the auction with the smallest remaining seconds."""
        auctions = [it for it in (self.coordinator.data or []) if it.is_auction and it.remaining_seconds is not None]
        if not auctions:
            return None
        return min(auctions, key=lambda x: x.remaining_seconds or 999999999)

    @property
    def native_value(self) -> str:
        """Return title of next ending auction."""
        next_it = self._next_auction()
        return next_it.title if next_it else "Aucune enchère en cours"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the next ending auction."""
        next_it = self._next_auction()
        if not next_it:
            return {}
        attrs = next_it.to_display_dict()
        if next_it.remaining_seconds is not None:
            ends_dt = datetime.now(timezone.utc) + timedelta(seconds=next_it.remaining_seconds)
            attrs["ends_at_utc"] = ends_dt.isoformat()
        return attrs


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
        return items[0].to_display_dict()


class NaturaBuyMinPriceSensor(NaturaBuyBaseSensor):
    """Sensor reporting the lowest price available in the category."""

    def __init__(self, coordinator: NaturaBuyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "prix_minimum")
        self._attr_name = "Prix minimum"
        self._attr_icon = "mdi:tag-outline"
        self._attr_native_unit_of_measurement = "€"
        self._attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_value(self) -> float | None:
        """Return the lowest price among active items."""
        items = self.coordinator.data or []
        if not items:
            return None
        return min(it.price for it in items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the cheapest item."""
        items = self.coordinator.data or []
        if not items:
            return {}
        cheapest = min(items, key=lambda x: x.price)
        return cheapest.to_dict()


class NaturaBuyEquippedItemsSensor(NaturaBuyBaseSensor):
    """Sensor reporting the number of equipped rifles (optics, threaded barrel, silencer)."""

    def __init__(self, coordinator: NaturaBuyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "annonces_equipees")
        self._attr_name = "Carabines équipées"
        self._attr_icon = "mdi:crosshairs"
        self._attr_native_unit_of_measurement = "armes"

    @property
    def native_value(self) -> int:
        """Return count of equipped rifles."""
        items = self.coordinator.data or []
        return sum(1 for it in items if it.has_optic or it.is_threaded or it.has_silencer)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return sample of equipped rifles."""
        items = self.coordinator.data or []
        equipped = [it.to_display_dict() for it in items if it.has_optic or it.is_threaded or it.has_silencer]
        return {
            "equipped_count": len(equipped),
            "equipped_items": equipped[:12],
        }
