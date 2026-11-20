"""Capteur « Téléphone admin » : convention commune des intégrations SDR (admin_phone)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .admin_phone import (
    ADMIN_TARGET_SUFFIX,
    ATTR_NOTIFY_SERVICE,
    CONF_ADMIN_NOTIFY_TARGET,
    normalize_target,
)
from .const import DOMAIN, VERSION


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AdminPhoneSensor(entry)])


class AdminPhoneSensor(SensorEntity):
    """Cible de notification de l'administrateur, lue dans entry.data."""

    _attr_has_entity_name = True
    _attr_translation_key = "admin_phone"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}{ADMIN_TARGET_SUFFIX}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Package Keeper",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=VERSION,
        )

    @property
    def _target(self) -> str | None:
        return normalize_target(self._entry.data.get(CONF_ADMIN_NOTIFY_TARGET))

    @property
    def native_value(self) -> str | None:
        return self._target

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_NOTIFY_SERVICE: self._target}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._entry.add_update_listener(self._async_entry_updated))

    async def _async_entry_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.async_write_ha_state()
