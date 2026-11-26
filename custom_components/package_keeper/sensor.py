"""Capteur « Téléphone admin » : convention commune des intégrations SDR (admin_phone)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .admin_phone import (
    ADMIN_TARGET_SUFFIX,
    CONF_ADMIN_NOTIFY_TARGET,
    admin_sensor_attributes,
    normalize_target,
)
from .const import DOMAIN, VERSION
from .git_sync import SIGNAL_GIT_UPDATED, STATUSES


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AdminPhoneSensor(entry), GitSyncSensor(entry)])


def _device(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Package Keeper",
        entry_type=DeviceEntryType.SERVICE,
        sw_version=VERSION,
    )


class AdminPhoneSensor(SensorEntity):
    """Cible de notification de l'administrateur, lue dans entry.data."""

    _attr_has_entity_name = True
    _attr_translation_key = "admin_phone"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}{ADMIN_TARGET_SUFFIX}"
        self._attr_device_info = _device(entry)

    @property
    def _target(self) -> str | None:
        return normalize_target(self._entry.data.get(CONF_ADMIN_NOTIFY_TARGET))

    @property
    def native_value(self) -> str | None:
        return self._target

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return admin_sensor_attributes(self._target)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._entry.add_update_listener(self._async_entry_updated))

    async def _async_entry_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.async_write_ha_state()


class GitSyncSensor(SensorEntity):
    """État de la synchronisation Git (0.5.0) : désactivée, à jour, en attente, en pause…"""

    _attr_has_entity_name = True
    _attr_translation_key = "git_sync"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_git_sync"
        self._attr_device_info = _device(entry)

    @property
    def native_value(self) -> str:
        git = self._entry.runtime_data.git
        return git.status if git else "disabled"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        git = self._entry.runtime_data.git
        if git is None:
            return {}
        info = git.as_dict()
        return {
            "error": info["error"],
            "pending_commits": info["pending"],
            "last_commit": info["last_commit"],
            "last_push": info["last_push"],
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_GIT_UPDATED, self._async_updated)
        )

    @callback
    def _async_updated(self) -> None:
        self.async_write_ha_state()
