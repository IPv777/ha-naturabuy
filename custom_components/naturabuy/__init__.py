"""The NaturaBuy integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall

from .const import (
    ACTION_MUTE,
    ACTION_REFRESH,
    DOMAIN,
    SERVICE_MUTE_ITEM,
    SERVICE_REFRESH,
    SERVICE_RESET_CACHE,
    SERVICE_UNMUTE_ITEM,
)
from .coordinator import NaturaBuyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NaturaBuy from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = NaturaBuyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register refresh service if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        async def handle_refresh(call: ServiceCall) -> None:
            """Handle manual refresh service call."""
            _LOGGER.debug("Manual refresh requested for NaturaBuy")
            for coord in hass.data.get(DOMAIN, {}).values():
                if isinstance(coord, NaturaBuyCoordinator):
                    await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH,
            handle_refresh,
        )

    # Register reset cache service if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_RESET_CACHE):
        async def handle_reset_cache(call: ServiceCall) -> None:
            """Handle reset cache service call."""
            _LOGGER.info("Reset cache requested for NaturaBuy")
            for coord in hass.data.get(DOMAIN, {}).values():
                if isinstance(coord, NaturaBuyCoordinator):
                    await coord.async_reset_cache()

        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_CACHE,
            handle_reset_cache,
        )

    # Register mute item service if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_MUTE_ITEM):
        async def handle_mute_item(call: ServiceCall) -> None:
            """Handle mute item service call."""
            item_id = str(call.data.get("item_id", "")).strip()
            if item_id:
                _LOGGER.info("Mute item service called for %s", item_id)
                for coord in hass.data.get(DOMAIN, {}).values():
                    if isinstance(coord, NaturaBuyCoordinator):
                        await coord.async_mute_item(item_id)

        hass.services.async_register(
            DOMAIN,
            SERVICE_MUTE_ITEM,
            handle_mute_item,
        )

    # Register unmute item service if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_UNMUTE_ITEM):
        async def handle_unmute_item(call: ServiceCall) -> None:
            """Handle unmute item service call."""
            item_id = str(call.data.get("item_id", "")).strip()
            if item_id:
                _LOGGER.info("Unmute item service called for %s", item_id)
                for coord in hass.data.get(DOMAIN, {}).values():
                    if isinstance(coord, NaturaBuyCoordinator):
                        await coord.async_unmute_item(item_id)

        hass.services.async_register(
            DOMAIN,
            SERVICE_UNMUTE_ITEM,
            handle_unmute_item,
        )

    # Register actionable notification listener
    if f"{DOMAIN}_action_listener" not in hass.data[DOMAIN]:
        async def handle_notification_action(event: Event) -> None:
            """Handle actionable notification tap from ThinkPhone."""
            action = event.data.get("action")
            if action == ACTION_REFRESH:
                _LOGGER.info("Received ThinkPhone action: NATURABUY_REFRESH")
                for coord in hass.data.get(DOMAIN, {}).values():
                    if isinstance(coord, NaturaBuyCoordinator):
                        await coord.async_request_refresh()
            elif action == ACTION_MUTE:
                tag = str(event.data.get("tag", ""))
                item_id = tag.replace("naturabuy_", "") if "naturabuy_" in tag else event.data.get("item_id")
                if item_id:
                    _LOGGER.info("Received ThinkPhone action: NATURABUY_MUTE for item %s", item_id)
                    for coord in hass.data.get(DOMAIN, {}).values():
                        if isinstance(coord, NaturaBuyCoordinator):
                            await coord.async_mute_item(str(item_id))

        hass.data[DOMAIN][f"{DOMAIN}_action_listener"] = hass.bus.async_listen(
            "mobile_app_notification_action",
            handle_notification_action,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
