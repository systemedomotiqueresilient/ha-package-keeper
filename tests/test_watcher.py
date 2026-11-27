"""Surveillance inotify (0.5.2) et délai minimal de 30 secondes."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.package_keeper import git_sync, watcher as watcher_module
from custom_components.package_keeper.admin_phone import CONF_ADMIN_NOTIFY_TARGET
from custom_components.package_keeper.const import DOMAIN
from custom_components.package_keeper.git_sync import debounce_seconds
from custom_components.package_keeper.watcher import PackagesWatcher, list_dirs, relevant

OTHER = "input_boolean:\n  lampe:\n    name: Lampe\n"


async def _wait_for(predicate, timeout: float = 3.0) -> None:
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("délai dépassé")


def test_debounce_never_below_30() -> None:
    assert debounce_seconds({}) == 30
    assert debounce_seconds({"git_debounce": 5}) == 30
    assert debounce_seconds({"git_debounce": "x"}) == 30
    assert debounce_seconds({"git_debounce": 90}) == 90
    assert debounce_seconds({"git_debounce": 99999}) == 3600


def test_relevant() -> None:
    assert relevant("salon.yaml")
    assert not relevant(".salon.yaml.pk-tmp")
    assert not relevant(".salon.yaml")  # fichier caché d'éditeur
    assert not relevant("salon.yaml~") and not relevant("notes.txt")


async def test_watcher_debounces(tmp_path: Path) -> None:
    calls: list[int] = []
    loop = asyncio.get_running_loop()
    folders = await loop.run_in_executor(None, list_dirs, tmp_path)
    watcher = PackagesWatcher(loop, 0.3, lambda: calls.append(1))
    watcher.start(folders)
    try:
        for i in range(3):  # trois enregistrements rapprochés = un seul rappel
            (tmp_path / "salon.yaml").write_text(f"a: {i}\n", encoding="utf-8")
            await asyncio.sleep(0.05)
        (tmp_path / ".salon.yaml.pk-tmp").write_text("x", encoding="utf-8")
        await _wait_for(lambda: calls)
        await asyncio.sleep(0.5)
        assert calls == [1]

        # Un sous-dossier créé après coup est surveillé lui aussi
        (tmp_path / "rdc").mkdir()
        await _wait_for(lambda: len(calls) == 2)
        await asyncio.sleep(0.2)
        (tmp_path / "rdc" / "cuisine.yaml").write_text("b: 1\n", encoding="utf-8")
        await _wait_for(lambda: len(calls) == 3)

        # Un fichier non .yaml ne déclenche rien
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
        await asyncio.sleep(0.6)
        assert len(calls) == 3
    finally:
        watcher.stop()
    assert watcher.watched == 0


async def test_external_edit_is_committed(
    hass: HomeAssistant, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Modification par Samba : commit « hors Package Keeper » après le délai, sans action."""
    monkeypatch.setattr(git_sync, "MIN_GIT_DEBOUNCE", 0)
    (config_dir / "packages" / "lampe.yaml").write_text(OTHER, encoding="utf-8")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADMIN_NOTIFY_TARGET: None},
        options={
            "notify_changes": False,
            "backups_kept": 3,
            "git_mode": "local",
            "git_debounce": 0.3,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    git = entry.runtime_data.git
    await git.async_wait_idle()
    assert git.watch == "inotify"
    repo = config_dir / ".package_keeper" / "git"

    def log() -> list[str]:
        return subprocess.run(
            ["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True, check=False
        ).stdout.splitlines()

    assert len(log()) == 1
    (config_dir / "packages" / "lampe.yaml").write_text(OTHER + "# Samba\n", encoding="utf-8")
    await _wait_for(lambda: len(log()) == 2)
    assert log()[0] in ("Modifications hors Package Keeper", "Changes made outside Package Keeper")
    assert (repo / "lampe.yaml").read_text(encoding="utf-8").endswith("# Samba\n")

    # Un enregistrement depuis le panneau garde son propre message, sans commit en double
    assert (await entry.runtime_data.async_save("lampe", OTHER)).ok
    await git.async_wait_idle()
    await asyncio.sleep(0.6)
    await git.async_wait_idle()
    assert log()[0].startswith("lampe") and len(log()) == 3
    await hass.config_entries.async_unload(entry.entry_id)


async def test_poll_fallback(
    hass: HomeAssistant, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(self, folders) -> None:
        raise watcher_module.WatchUnavailable("test")

    monkeypatch.setattr(PackagesWatcher, "start", unavailable)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADMIN_NOTIFY_TARGET: None},
        options={"notify_changes": False, "backups_kept": 3, "git_mode": "local"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    git = entry.runtime_data.git
    await git.async_wait_idle()
    assert git.watch == "poll"
    (config_dir / "packages" / "lampe.yaml").write_text(OTHER, encoding="utf-8")
    await git._async_poll()
    await git.async_wait_idle()
    assert (config_dir / ".package_keeper" / "git" / "lampe.yaml").is_file()


async def test_options_refuse_below_30(hass: HomeAssistant, config_dir: Path) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADMIN_NOTIFY_TARGET: None}, options={"backups_kept": 3}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "general"}
    )
    with pytest.raises(InvalidData, match="git_debounce"):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"notify_changes": True, "backups_kept": 3, "git_debounce": 10}
        )
    done = await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_changes": True, "backups_kept": 3, "git_debounce": 120}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["git_debounce"] == 120
