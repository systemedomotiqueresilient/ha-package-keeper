"""Fixtures : un /config temporaire avec les packages activés."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant

from custom_components.package_keeper.admin_phone import CONF_ADMIN_NOTIFY_TARGET
from custom_components.package_keeper.const import DOMAIN

CONFIGURATION = """\
homeassistant:
  name: Test
  packages: !include_dir_named packages
"""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def config_dir(hass: HomeAssistant, tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    (cfg / "packages").mkdir(parents=True)
    (cfg / "configuration.yaml").write_text(CONFIGURATION, encoding="utf-8")
    (cfg / "secrets.yaml").write_text("mot_de_passe: ne-doit-jamais-sortir\n", encoding="utf-8")
    hass.config.config_dir = str(cfg)
    return cfg


@pytest.fixture
async def entry(hass: HomeAssistant, config_dir: Path) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        data={CONF_ADMIN_NOTIFY_TARGET: None},
        options={"notify_changes": True, "backups_kept": 3},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
