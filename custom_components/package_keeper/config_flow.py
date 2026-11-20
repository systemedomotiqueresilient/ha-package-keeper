"""Config flow et options flow de Package Keeper."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .admin_phone import (
    CONF_ADMIN_NOTIFY_TARGET,
    is_valid_target,
    normalize_target,
    suggest_admin_target,
)
from .const import (
    CONF_BACKUPS_KEPT,
    CONF_NOTIFY_CHANGES,
    DEFAULT_BACKUPS_KEPT,
    DEFAULT_NOTIFY_CHANGES,
    DOMAIN,
)


def _schema(hass: HomeAssistant, options: dict[str, Any], target: str | None) -> vol.Schema:
    suggested, choices = suggest_admin_target(hass, target)
    return vol.Schema(
        {
            vol.Optional(
                CONF_ADMIN_NOTIFY_TARGET, description={"suggested_value": suggested}
            ): SelectSelector(
                SelectSelectorConfig(
                    options=choices, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(
                CONF_NOTIFY_CHANGES,
                default=options.get(CONF_NOTIFY_CHANGES, DEFAULT_NOTIFY_CHANGES),
            ): BooleanSelector(),
            vol.Required(
                CONF_BACKUPS_KEPT,
                default=options.get(CONF_BACKUPS_KEPT, DEFAULT_BACKUPS_KEPT),
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=50, step=1, mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _split(user_input: dict[str, Any]) -> tuple[dict[str, Any], str | None, dict[str, str]]:
    """(options, téléphone admin pour entry.data, erreurs)."""
    values = dict(user_input)
    raw = values.pop(CONF_ADMIN_NOTIFY_TARGET, None)
    errors: dict[str, str] = {}
    if raw and str(raw).strip() and not is_valid_target(raw):
        errors[CONF_ADMIN_NOTIFY_TARGET] = "invalid_target"
    values[CONF_BACKUPS_KEPT] = int(values.get(CONF_BACKUPS_KEPT, DEFAULT_BACKUPS_KEPT))
    return values, normalize_target(raw), errors


class PackageKeeperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout depuis l'interface (une seule instance)."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options, target, errors = _split(user_input)
            if not errors:
                return self.async_create_entry(
                    title="Package Keeper",
                    data={CONF_ADMIN_NOTIFY_TARGET: target},
                    options=options,
                )
        return self.async_show_form(
            step_id="user", data_schema=_schema(self.hass, {}, None), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PackageKeeperOptionsFlow()


class PackageKeeperOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        target = normalize_target(entry.data.get(CONF_ADMIN_NOTIFY_TARGET))
        errors: dict[str, str] = {}
        if user_input is not None:
            options, target, errors = _split(user_input)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_ADMIN_NOTIFY_TARGET: target}
                )
                return self.async_create_entry(data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(self.hass, dict(entry.options), target),
            errors=errors,
        )
