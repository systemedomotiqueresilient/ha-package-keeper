"""Package Keeper : enregistrer les packages YAML proposés par une IA, sans File Editor."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend as ha_frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .const import (
    DOMAIN,
    FRONTEND_URL,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_URL_PATH,
    VERSION,
)
from .manager import PackageManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type PackageKeeperConfigEntry = ConfigEntry[PackageManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    websocket.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PackageKeeperConfigEntry) -> bool:
    entry.runtime_data = PackageManager(hass, entry)
    await _async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PackageKeeperConfigEntry) -> bool:
    if "frontend" in hass.config.components:
        ha_frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """1.1 = première version publiée : rien à migrer, une version plus récente est refusée."""
    return entry.version <= 1


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Panneau latéral réservé aux administrateurs (côté serveur, l'API l'est aussi)."""
    if "frontend" not in hass.config.components:
        _LOGGER.warning("Interface web absente : panneau Package Keeper non ajouté")
        return
    if not hass.data.get(f"{DOMAIN}_static"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, str(Path(__file__).parent / "frontend"), False)]
        )
        hass.data[f"{DOMAIN}_static"] = True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="Package Keeper",
        sidebar_icon=PANEL_ICON,
        module_url=f"{FRONTEND_URL}/package-keeper-panel.js?v={VERSION}",
        require_admin=True,
        config={},
    )
