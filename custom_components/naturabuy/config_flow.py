"""Config flow for NaturaBuy integration with advanced filters, turbo mode and brand selection."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONDITION_ALL,
    CONDITION_NEW,
    CONDITION_USED,
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
    DEFAULT_NAME,
    DEFAULT_NO_RESERVE,
    DEFAULT_NOTIFY_ENDING,
    DEFAULT_NOTIFY_NEW,
    DEFAULT_SALE_TYPE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SELLER_TYPE,
    DEFAULT_TURBO_MODE,
    DOMAIN,
    SALE_TYPE_ALL,
    SALE_TYPE_AUCTION,
    SALE_TYPE_BUY_NOW,
    SELLER_ALL,
    SELLER_PARTICULIER,
    SELLER_PRO,
)

_LOGGER = logging.getLogger(__name__)


def _get_notify_services(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """Get list of available notify services in Home Assistant."""
    services = hass.services.async_services().get("notify", {})
    options: list[selector.SelectOptionDict] = []
    for service_name in sorted(services.keys()):
        full_service = f"notify.{service_name}"
        options.append(
            selector.SelectOptionDict(
                value=full_service,
                label=full_service,
            )
        )
    if not options:
        options.append(
            selector.SelectOptionDict(
                value="notify.persistent_notification",
                label="notify.persistent_notification",
            )
        )
    return options


class NaturaBuyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NaturaBuy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].strip()
            if not url.startswith("http://") and not url.startswith("https://"):
                errors["base"] = "invalid_url"
            else:
                title = user_input.get(CONF_NAME, DEFAULT_NAME).strip()
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                )

        notify_options = _get_notify_services(self.hass)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Carabines 30-06"): str,
                vol.Required(
                    CONF_URL,
                    default="https://www.naturabuy.fr/Carabines-culasse-lineaire-30-06-critere-152850.html",
                ): str,
                vol.Required(CONF_MAX_PRICE, default=DEFAULT_MAX_PRICE): vol.Coerce(float),
                vol.Optional(CONF_MIN_PRICE, default=DEFAULT_MIN_PRICE): vol.Coerce(float),
                vol.Required(
                    CONF_SALE_TYPE,
                    default=DEFAULT_SALE_TYPE,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SALE_TYPE_ALL, label="Toutes (Enchères et Achat Immédiat)"),
                            selector.SelectOptionDict(value=SALE_TYPE_AUCTION, label="Enchères uniquement"),
                            selector.SelectOptionDict(value=SALE_TYPE_BUY_NOW, label="Achat Immédiat uniquement"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_NO_RESERVE, default=DEFAULT_NO_RESERVE): bool,
                vol.Optional(CONF_BRAND, default=DEFAULT_BRAND): str,
                vol.Optional(CONF_DEPARTMENT, default=DEFAULT_DEPARTMENT): str,
                vol.Required(
                    CONF_CONDITION,
                    default=DEFAULT_CONDITION,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=CONDITION_ALL, label="Tous états (Neuf et Occasion)"),
                            selector.SelectOptionDict(value=CONDITION_USED, label="Occasion uniquement"),
                            selector.SelectOptionDict(value=CONDITION_NEW, label="Neuf uniquement"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SELLER_TYPE,
                    default=DEFAULT_SELLER_TYPE,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SELLER_ALL, label="Tous vendeurs (Particuliers et Pros)"),
                            selector.SelectOptionDict(value=SELLER_PARTICULIER, label="Particuliers uniquement"),
                            selector.SelectOptionDict(value=SELLER_PRO, label="Professionnels uniquement"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_KEYWORDS_EXCLUDE, default=DEFAULT_KEYWORDS_EXCLUDE): str,
                vol.Optional(CONF_KEYWORDS_INCLUDE, default=DEFAULT_KEYWORDS_INCLUDE): str,
                vol.Required(CONF_MAX_PAGES, default=DEFAULT_MAX_PAGES): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=5, step=1, mode=selector.NumberSelectorMode.SLIDER)
                ),
                vol.Required(CONF_TURBO_MODE, default=DEFAULT_TURBO_MODE): bool,
                vol.Required(CONF_NOTIFY_NEW, default=DEFAULT_NOTIFY_NEW): bool,
                vol.Required(CONF_NOTIFY_ENDING, default=DEFAULT_NOTIFY_ENDING): bool,
                vol.Required(CONF_ALERT_MINUTES, default=DEFAULT_ALERT_MINUTES): vol.Coerce(int),
                vol.Optional(
                    CONF_NOTIFY_TARGETS,
                    default=["notify.mobile_app_thinkphone_by_motorola"],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=notify_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.Coerce(int),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NaturaBuyOptionsFlowHandler:
        """Get options flow."""
        return NaturaBuyOptionsFlowHandler(config_entry)


class NaturaBuyOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for NaturaBuy."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}
        notify_options = _get_notify_services(self.hass)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_URL,
                    default=current.get(CONF_URL),
                ): str,
                vol.Required(
                    CONF_MAX_PRICE,
                    default=current.get(CONF_MAX_PRICE, DEFAULT_MAX_PRICE),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_MIN_PRICE,
                    default=current.get(CONF_MIN_PRICE, DEFAULT_MIN_PRICE),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_SALE_TYPE,
                    default=current.get(CONF_SALE_TYPE, DEFAULT_SALE_TYPE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SALE_TYPE_ALL, label="Toutes (Enchères et Achat Immédiat)"),
                            selector.SelectOptionDict(value=SALE_TYPE_AUCTION, label="Enchères uniquement"),
                            selector.SelectOptionDict(value=SALE_TYPE_BUY_NOW, label="Achat Immédiat uniquement"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_NO_RESERVE,
                    default=current.get(CONF_NO_RESERVE, DEFAULT_NO_RESERVE),
                ): bool,
                vol.Optional(
                    CONF_BRAND,
                    default=current.get(CONF_BRAND, DEFAULT_BRAND),
                ): str,
                vol.Optional(
                    CONF_DEPARTMENT,
                    default=current.get(CONF_DEPARTMENT, DEFAULT_DEPARTMENT),
                ): str,
                vol.Required(
                    CONF_CONDITION,
                    default=current.get(CONF_CONDITION, DEFAULT_CONDITION),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=CONDITION_ALL, label="Tous états (Neuf et Occasion)"),
                            selector.SelectOptionDict(value=CONDITION_USED, label="Occasion uniquement"),
                            selector.SelectOptionDict(value=CONDITION_NEW, label="Neuf uniquement"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SELLER_TYPE,
                    default=current.get(CONF_SELLER_TYPE, DEFAULT_SELLER_TYPE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SELLER_ALL, label="Tous vendeurs (Particuliers et Pros)"),
                            selector.SelectOptionDict(value=SELLER_PARTICULIER, label="Particuliers uniquement"),
                            selector.SelectOptionDict(value=SELLER_PRO, label="Professionnels uniquement"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_KEYWORDS_EXCLUDE,
                    default=current.get(CONF_KEYWORDS_EXCLUDE, DEFAULT_KEYWORDS_EXCLUDE),
                ): str,
                vol.Optional(
                    CONF_KEYWORDS_INCLUDE,
                    default=current.get(CONF_KEYWORDS_INCLUDE, DEFAULT_KEYWORDS_INCLUDE),
                ): str,
                vol.Required(
                    CONF_MAX_PAGES,
                    default=current.get(CONF_MAX_PAGES, DEFAULT_MAX_PAGES),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=5, step=1, mode=selector.NumberSelectorMode.SLIDER)
                ),
                vol.Required(
                    CONF_TURBO_MODE,
                    default=current.get(CONF_TURBO_MODE, DEFAULT_TURBO_MODE),
                ): bool,
                vol.Required(
                    CONF_NOTIFY_NEW,
                    default=current.get(CONF_NOTIFY_NEW, DEFAULT_NOTIFY_NEW),
                ): bool,
                vol.Required(
                    CONF_NOTIFY_ENDING,
                    default=current.get(CONF_NOTIFY_ENDING, DEFAULT_NOTIFY_ENDING),
                ): bool,
                vol.Required(
                    CONF_ALERT_MINUTES,
                    default=current.get(CONF_ALERT_MINUTES, DEFAULT_ALERT_MINUTES),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_NOTIFY_TARGETS,
                    default=current.get(CONF_NOTIFY_TARGETS, ["notify.mobile_app_thinkphone_by_motorola"]),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=notify_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.Coerce(int),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
