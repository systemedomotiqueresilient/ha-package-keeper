"""API WebSocket (administrateurs seulement), config flow, capteur, panneau, versions."""

from __future__ import annotations

import hashlib
import re
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

import custom_components.package_keeper as pk
from custom_components.package_keeper import admin_phone
from custom_components.package_keeper.admin_phone import (
    ATTR_NOTIFY_SERVICE,
    CONF_ADMIN_NOTIFY_TARGET,
)
from custom_components.package_keeper.const import DOMAIN, PANEL_URL_PATH, VERSION

GOOD = "input_boolean:\n  test_pk:\n    name: Test\n"
MOBILE = "notify.mobile_app_pixel_9"


# --- WebSocket ---------------------------------------------------------------


async def test_ws_full_cycle(hass: HomeAssistant, entry, hass_ws_client) -> None:
    client = await hass_ws_client(hass)

    async def ws(**msg):
        await client.send_json_auto_id(msg)
        return await client.receive_json()

    reply = await ws(type=f"{DOMAIN}/overview")
    assert reply["success"] and reply["result"]["enabled"] and reply["result"]["packages"] == []
    assert reply["result"]["version"] == VERSION

    reply = await ws(type=f"{DOMAIN}/save", name="test_pk", text=GOOD, dry_run=True)
    assert reply["result"]["ok"] and reply["result"]["action"] == "checked"

    reply = await ws(type=f"{DOMAIN}/save", name="test_pk", text=GOOD)
    assert reply["result"]["ok"] and reply["result"]["action"] == "saved"

    reply = await ws(type=f"{DOMAIN}/read", name="test_pk")
    assert reply["result"]["text"] == GOOD

    reply = await ws(type=f"{DOMAIN}/save", name="test_pk", text=GOOD + "# v2\n")
    assert reply["result"]["ok"]
    backups = (await ws(type=f"{DOMAIN}/backups", name="test_pk"))["result"]["backups"]
    assert len(backups) == 1
    reply = await ws(type=f"{DOMAIN}/read_backup", name="test_pk", backup=backups[0]["id"])
    assert reply["result"]["text"] == GOOD
    reply = await ws(type=f"{DOMAIN}/restore", name="test_pk", backup=backups[0]["id"])
    assert reply["result"]["ok"] and reply["result"]["action"] == "restored"

    reply = await ws(type=f"{DOMAIN}/rename", name="test_pk", new_name="essais/test_pk")
    assert reply["result"]["ok"] and reply["result"]["renamed_from"] == "test_pk"
    reply = await ws(type=f"{DOMAIN}/rename", name="essais/test_pk", new_name="test_pk")
    assert reply["result"]["ok"] and reply["result"]["name"] == "test_pk"

    # Suppression : confirmation obligatoire dans l'API elle-même
    reply = await ws(type=f"{DOMAIN}/delete", name="test_pk")
    assert not reply["success"] and reply["error"]["code"] == "invalid_format"
    reply = await ws(type=f"{DOMAIN}/delete", name="test_pk", confirm=True)
    assert reply["result"]["ok"]

    reply = await ws(type=f"{DOMAIN}/read", name="test_pk")
    assert not reply["success"] and reply["error"]["code"] == "not_found"
    reply = await ws(type=f"{DOMAIN}/read", name="../secrets")
    assert reply["error"]["code"] == "invalid_name"

    reply = await ws(type=f"{DOMAIN}/save", name="test_pk", text=GOOD)
    reply = await ws(type=f"{DOMAIN}/dependents", name="test_pk")
    assert reply["result"] == {"name": "test_pk", "dependents": {}}

    reply = await ws(type=f"{DOMAIN}/reload", services=["light.turn_off"])
    assert reply["result"] == {"reloaded": [], "orphans": []}


async def test_ws_refused_to_non_admin(
    hass: HomeAssistant, entry, hass_ws_client, hass_read_only_access_token
) -> None:
    client = await hass_ws_client(hass, hass_read_only_access_token)
    for msg in (
        {"type": f"{DOMAIN}/overview"},
        {"type": f"{DOMAIN}/save", "name": "x", "text": GOOD},
        {"type": f"{DOMAIN}/delete", "name": "x", "confirm": True},
    ):
        await client.send_json_auto_id(msg)
        reply = await client.receive_json()
        assert not reply["success"] and reply["error"]["code"] == "unauthorized"


async def test_ws_not_loaded(hass: HomeAssistant, entry, hass_ws_client) -> None:
    await hass.config_entries.async_unload(entry.entry_id)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/overview"})
    reply = await client.receive_json()
    assert reply["error"]["code"] == "not_loaded"


# --- Config flow et téléphone admin -----------------------------------------


def _sibling(hass: HomeAssistant, platform: str, value: str) -> None:
    entity = er.async_get(hass).async_get_or_create(
        "sensor", platform, "s_admin_notify_target", suggested_object_id=f"{platform}_admin"
    )
    hass.states.async_set(entity.entity_id, value, {ATTR_NOTIFY_SERVICE: value})


def _suggested(result: dict) -> str | None:
    for key in result["data_schema"].schema:
        if key == CONF_ADMIN_NOTIFY_TARGET:
            return (key.description or {}).get("suggested_value")
    raise AssertionError


async def test_config_flow_prefilled_from_sibling(hass: HomeAssistant, config_dir: Path) -> None:
    _sibling(hass, "entity_inventory", MOBILE)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert _suggested(result) == MOBILE

    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADMIN_NOTIFY_TARGET: "telephone", "notify_changes": True, "backups_kept": 5},
    )
    assert bad["errors"] == {CONF_ADMIN_NOTIFY_TARGET: "invalid_target"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADMIN_NOTIFY_TARGET: MOBILE, "notify_changes": True, "backups_kept": 5},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data == {CONF_ADMIN_NOTIFY_TARGET: MOBILE}
    assert entry.options == {"notify_changes": True, "backups_kept": 5}
    await hass.async_block_till_done()

    sensor_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_admin_notify_target"
    )
    reg = er.async_get(hass).async_get(sensor_id)
    assert reg.entity_category is EntityCategory.DIAGNOSTIC
    state = hass.states.get(sensor_id)
    assert state.state == MOBILE and state.attributes[ATTR_NOTIFY_SERVICE] == MOBILE
    assert state.attributes["admin_phone_convention"] == 1

    # Options : la valeur reste dans entry.data, le capteur suit
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert _suggested(result) == MOBILE
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_changes": False, "backups_kept": 3}
    )
    await hass.async_block_till_done()
    assert entry.data[CONF_ADMIN_NOTIFY_TARGET] is None
    assert entry.options == {"notify_changes": False, "backups_kept": 3, "git_mode": "off"}
    assert hass.states.get(sensor_id).state == "unknown"


async def test_unlisted_platform_not_suggested(hass: HomeAssistant, config_dir: Path) -> None:
    _sibling(hass, "spook", MOBILE)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert _suggested(result) is None


async def test_future_version_refused(hass: HomeAssistant, config_dir: Path) -> None:
    entry = MockConfigEntry(domain=DOMAIN, version=2)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.MIGRATION_ERROR


# --- Panneau -----------------------------------------------------------------


async def test_panel_registered_admin_only(hass: HomeAssistant, config_dir: Path) -> None:
    hass.config.components.add("frontend")
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=1, data={})
    entry.add_to_hass(hass)
    with (
        patch.object(pk.panel_custom, "async_register_panel", AsyncMock()) as register,
        patch.object(hass.http, "async_register_static_paths", AsyncMock()) as static,
        patch.object(pk.ha_frontend, "async_remove_panel") as remove,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert await hass.config_entries.async_unload(entry.entry_id)
    kwargs = register.call_args.kwargs
    assert kwargs["require_admin"] is True
    assert kwargs["frontend_url_path"] == PANEL_URL_PATH
    assert static.call_count == 1
    remove.assert_called_once()

    panel = Path(__file__).parents[1] / "custom_components" / DOMAIN / "frontend"
    js = (panel / "package-keeper-panel.js").read_text(encoding="utf-8")
    assert 'customElements.define("package-keeper-panel"' in js
    # Aucun contenu de fichier inséré en HTML : innerHTML ne sert qu'à vider
    assert all(v == '""' for v in re.findall(r'innerHTML\s*=\s*(\S{2})', js))


# --- Module commun et versions ------------------------------------------------


def test_module_copy_and_versions() -> None:
    root = Path(__file__).parents[1]
    module = root / "custom_components" / DOMAIN / "admin_phone.py"
    assert admin_phone.MODULE_VERSION == "1.3.0"
    assert hashlib.sha256(module.read_bytes()).hexdigest() == (
        "38f74609b319ceb0c56395ff13454d8bbdc72246b1dc02bcf6ad4babf768ddf8"
    )
    manifest = json.loads((root / "custom_components" / DOMAIN / "manifest.json").read_text())
    assert manifest["version"] == VERSION == (root / "VERSION").read_text().strip()
    js = (root / "custom_components" / DOMAIN / "frontend" / "package-keeper-panel.js").read_text()
    assert f'const PANEL_VERSION = "{VERSION}";' in js  # sinon le panneau se croit périmé
