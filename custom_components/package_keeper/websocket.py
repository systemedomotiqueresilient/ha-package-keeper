"""API WebSocket du panneau : toutes les commandes sont réservées aux administrateurs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .const import DOMAIN
from .manager import PackageManager
from .store import PackageError

_NAME = vol.All(str, vol.Length(min=1, max=200))


def _manager(hass: HomeAssistant) -> PackageManager | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0].runtime_data if entries else None


def _handler(
    func: Callable[[PackageManager, dict[str, Any]], Awaitable[Any]],
) -> Callable:
    """Trouve le gestionnaire, traduit les refus en erreurs WebSocket lisibles."""

    async def wrapped(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        manager = _manager(hass)
        if manager is None:
            connection.send_error(msg["id"], "not_loaded", "Package Keeper n'est pas chargé")
            return
        try:
            result = await func(manager, msg)
        except PackageError as err:
            connection.send_error(msg["id"], err.code, err.detail or err.code)
            return
        connection.send_result(msg["id"], result)

    return wrapped


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/overview"})
@websocket_api.async_response
@_handler
async def ws_overview(manager: PackageManager, msg: dict[str, Any]) -> dict:
    return await manager.async_overview()


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/read", vol.Required("name"): _NAME}
)
@websocket_api.async_response
@_handler
async def ws_read(manager: PackageManager, msg: dict[str, Any]) -> dict:
    return {"name": msg["name"], "text": await manager.async_read(msg["name"])}


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/save",
        vol.Required("name"): _NAME,
        vol.Required("text"): str,
        vol.Optional("dry_run", default=False): bool,
    }
)
@websocket_api.async_response
@_handler
async def ws_save(manager: PackageManager, msg: dict[str, Any]) -> dict:
    outcome = await manager.async_save(msg["name"], msg["text"], dry_run=msg["dry_run"])
    return outcome.as_dict()


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/delete",
        vol.Required("name"): _NAME,
        # Le panneau demande confirmation ; l'API l'exige aussi
        vol.Required("confirm"): True,
    }
)
@websocket_api.async_response
@_handler
async def ws_delete(manager: PackageManager, msg: dict[str, Any]) -> dict:
    return (await manager.async_delete(msg["name"])).as_dict()


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/backups", vol.Required("name"): _NAME}
)
@websocket_api.async_response
@_handler
async def ws_backups(manager: PackageManager, msg: dict[str, Any]) -> dict:
    return {"name": msg["name"], "backups": await manager.async_backups(msg["name"])}


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/read_backup",
        vol.Required("name"): _NAME,
        vol.Required("backup"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_read_backup(manager: PackageManager, msg: dict[str, Any]) -> dict:
    return {"text": await manager.async_read_backup(msg["name"], msg["backup"])}


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/restore",
        vol.Required("name"): _NAME,
        vol.Required("backup"): str,
    }
)
@websocket_api.async_response
@_handler
async def ws_restore(manager: PackageManager, msg: dict[str, Any]) -> dict:
    return (await manager.async_restore(msg["name"], msg["backup"])).as_dict()


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/dependents", vol.Required("name"): _NAME}
)
@websocket_api.async_response
@_handler
async def ws_dependents(manager: PackageManager, msg: dict[str, Any]) -> dict:
    return {"name": msg["name"], "dependents": await manager.async_dependents(msg["name"])}


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/reload",
        vol.Required("services"): [str],
        # Entités retirées par la modification : on dit lesquelles ne sont plus fournies
        vol.Optional("entities", default=[]): [str],
    }
)
@websocket_api.async_response
@_handler
async def ws_reload(manager: PackageManager, msg: dict[str, Any]) -> dict:
    reloaded = await manager.async_reload(msg["services"])
    await asyncio.sleep(0)  # laisse les entités retirées passer « non fournies »
    return {"reloaded": reloaded, "orphans": manager.async_orphans(msg["entities"])}


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in (
        ws_overview,
        ws_read,
        ws_save,
        ws_delete,
        ws_backups,
        ws_read_backup,
        ws_restore,
        ws_dependents,
        ws_reload,
    ):
        websocket_api.async_register_command(hass, command)
