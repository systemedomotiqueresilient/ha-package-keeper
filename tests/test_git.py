"""Synchronisation Git (0.5.0) : dépôt miroir, commits, envoi, branchement, visibilité."""

from __future__ import annotations

from pathlib import Path
import subprocess

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er, issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.package_keeper import git_sync
from custom_components.package_keeper.admin_phone import CONF_ADMIN_NOTIFY_TARGET
from custom_components.package_keeper.const import DOMAIN
from custom_components.package_keeper.git_sync import (
    GitError,
    async_visibility,
    redact,
    validate_branch,
    validate_remote,
)

GOOD = "# Fenêtre\ninput_boolean:\n  fenetre_salon:\n    name: Fenêtre salon\n"
OTHER = "input_boolean:\n  lampe_cuisine:\n    name: Lampe cuisine\n"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _bare(path: Path) -> str:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "--bare", "-b", "main")
    return f"file://{path}"


def _log(repo: Path, ref: str = "HEAD") -> list[str]:
    done = subprocess.run(
        ["git", "log", "--format=%s", ref], cwd=repo, capture_output=True, text=True, check=False
    )
    return done.stdout.splitlines() if done.returncode == 0 else []


@pytest.fixture
def local_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Le « dépôt distant » local est accepté sous tmp_path (à la place de /share)."""
    root = tmp_path / "share"
    monkeypatch.setattr(git_sync, "_LOCAL_ROOTS", (f"{root}/",))
    return root


async def _entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        data={CONF_ADMIN_NOTIFY_TARGET: "notify.mobile_app_pixel_9"},
        options={"notify_changes": False, "backups_kept": 3, **options},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.git.async_wait_idle()
    return entry


def _phone(hass: HomeAssistant) -> list[ServiceCall]:
    calls: list[ServiceCall] = []
    hass.services.async_register("notify", "mobile_app_pixel_9", calls.append)
    return calls


async def _settle(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.git.async_wait_idle()
    await hass.async_block_till_done()


def _sensor(hass: HomeAssistant, entry: MockConfigEntry):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_git_sync"
    )
    return hass.states.get(entity_id)


# --- Validation --------------------------------------------------------------


def test_validate_remote(local_roots: Path) -> None:
    assert validate_remote(" https://github.com/a/b.git/ ") == "https://github.com/a/b.git"
    assert validate_remote(f"file://{local_roots}/pk") == f"file://{local_roots}/pk"
    for bad, code in [
        ("http://github.com/a/b", "invalid_url"),
        ("https://github.com/seul", "invalid_url"),
        ("https://moi:secret@github.com/a/b", "url_with_credentials"),
        ("file:///config/packages", "invalid_url"),
        (f"file://{local_roots}/../config", "invalid_url"),
        ("git@github.com:a/b.git", "invalid_url"),
    ]:
        with pytest.raises(GitError) as err:
            validate_remote(bad)
        assert err.value.code == code, bad
    assert validate_branch("main") == "main"
    for bad in ("", "-x", "a..b", "a b", "/main"):
        with pytest.raises(GitError):
            validate_branch(bad)


def test_redact() -> None:
    text = "fatal: Authorization: Basic Z2l0OnNlY3JldA== failed for secret"
    cleaned = redact(text, "secret")
    assert "secret" not in cleaned and "Z2l0" not in cleaned


async def test_visibility(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get("https://api.github.com/repos/moi/prive", json={"private": True})
    aioclient_mock.get("https://api.github.com/repos/moi/public", json={"private": False})
    aioclient_mock.get("https://api.github.com/repos/moi/refuse", status=401)
    aioclient_mock.get(
        "https://forge.example/api/v1/repos/moi/pk",
        json={"full_name": "moi/pk", "private": True, "internal": False},
    )
    aioclient_mock.get("https://lab.example/api/v1/repos/moi/pk", status=404)
    aioclient_mock.get(
        "https://lab.example/api/v4/projects/moi%2Fpk", json={"visibility": "internal"}
    )
    aioclient_mock.get("https://autre.example/api/v1/repos/moi/pk", status=404)
    aioclient_mock.get("https://autre.example/api/v4/projects/moi%2Fpk", status=404)

    assert await async_visibility(hass, "https://github.com/moi/prive.git", "git", "t") == "private"
    assert await async_visibility(hass, "https://github.com/moi/public", "git", "t") == "public"
    with pytest.raises(GitError) as err:
        await async_visibility(hass, "https://github.com/moi/refuse", "git", "t")
    assert err.value.code == "auth_failed"
    assert await async_visibility(hass, "https://forge.example/moi/pk", "git", "t") == "private"
    assert await async_visibility(hass, "https://lab.example/moi/pk", "git", "t") == "public"
    assert await async_visibility(hass, "https://autre.example/moi/pk", "git", "t") == "unknown"
    assert await async_visibility(hass, "file:///share/pk", "git", "") == "local"
    # Le jeton part dans un en-tête, jamais dans l'adresse
    assert all("t@" not in str(call[1]) for call in aioclient_mock.mock_calls)


# --- Mode local ----------------------------------------------------------------


async def test_local_mode_commits(hass: HomeAssistant, config_dir: Path) -> None:
    (config_dir / "packages" / "existant.yaml").write_text(OTHER, encoding="utf-8")
    entry = await _entry(hass, git_mode="local")
    repo = config_dir / ".package_keeper" / "git"
    assert _log(repo) == ["État initial des packages"] or _log(repo) == [
        "Initial state of the packages"
    ]
    assert (repo / "existant.yaml").read_text(encoding="utf-8") == OTHER

    manager = entry.runtime_data
    assert (await manager.async_save("salon", GOOD)).ok
    await _settle(hass, entry)
    assert (repo / "salon.yaml").read_text(encoding="utf-8") == GOOD

    # Une modification faite hors Package Keeper est commitée à part
    (config_dir / "packages" / "existant.yaml").write_text(OTHER + "# Samba\n", encoding="utf-8")
    assert (await manager.async_rename("salon", "rdc/salon")).ok
    await _settle(hass, entry)
    assert (repo / "rdc" / "salon.yaml").is_file() and not (repo / "salon.yaml").exists()
    log = _log(repo)
    assert log[0].startswith("salon → rdc/salon")
    assert log[1] in ("Modifications hors Package Keeper", "Changes made outside Package Keeper")

    assert (await manager.async_delete("rdc/salon")).ok
    await _settle(hass, entry)
    assert not (repo / "rdc").exists()
    assert "rdc/salon" in _log(repo)[0]
    assert _sensor(hass, entry).state == "ok"


async def test_rollback_is_never_committed(hass: HomeAssistant, config_dir: Path) -> None:
    entry = await _entry(hass, git_mode="local")
    repo = config_dir / ".package_keeper" / "git"
    before = _log(repo)
    broken = "input_boolean:\n  x:\n    nom_inconnu: 3\n    name: [a]\n"
    outcome = await entry.runtime_data.async_save("casse", broken)
    assert outcome.rolled_back
    await _settle(hass, entry)
    assert _log(repo) == before
    assert not (repo / "casse.yaml").exists()


async def test_disabled_by_default(hass: HomeAssistant, config_dir: Path) -> None:
    entry = await _entry(hass)
    assert (await entry.runtime_data.async_save("salon", GOOD)).ok
    await _settle(hass, entry)
    assert not (config_dir / ".package_keeper" / "git").exists()
    assert _sensor(hass, entry).state == "disabled"
    overview = await entry.runtime_data.async_overview()
    assert overview["git"]["status"] == "disabled"


async def test_git_missing(hass: HomeAssistant, config_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(git_sync, "git_available", lambda: False)
    entry = await _entry(hass, git_mode="local")
    assert _sensor(hass, entry).state == "unavailable"


# --- Mode distant (dépôt local file://) ---------------------------------------


async def test_empty_remote_gets_initial_push(
    hass: HomeAssistant, config_dir: Path, local_roots: Path
) -> None:
    (config_dir / "packages" / "existant.yaml").write_text(OTHER, encoding="utf-8")
    url = _bare(local_roots / "pk.git")
    entry = await _entry(hass, git_mode="remote", git_url=url, git_branch="main")
    remote = local_roots / "pk.git"
    assert len(_log(remote, "main")) == 1
    assert _sensor(hass, entry).state == "ok"

    assert (await entry.runtime_data.async_save("salon", GOOD)).ok
    await _settle(hass, entry)
    assert _log(remote, "main")[0].startswith("salon")
    state = _sensor(hass, entry)
    assert state.state == "ok" and state.attributes["pending_commits"] == 0
    assert state.attributes["last_push"]


async def test_identical_remote_is_adopted(
    hass: HomeAssistant, config_dir: Path, local_roots: Path, tmp_path: Path
) -> None:
    (config_dir / "packages" / "existant.yaml").write_text(OTHER, encoding="utf-8")
    url = _bare(local_roots / "pk.git")
    work = tmp_path / "ailleurs"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    (work / "existant.yaml").write_text(OTHER, encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "-m", "ancien")
    _git(work, "push", "-q", url, "main")

    entry = await _entry(hass, git_mode="remote", git_url=url, git_branch="main")
    repo = config_dir / ".package_keeper" / "git"
    assert _log(repo) == ["ancien"]  # historique repris, rien de nouveau
    assert _sensor(hass, entry).state == "ok"


async def test_non_empty_remote_pauses(
    hass: HomeAssistant, config_dir: Path, local_roots: Path, tmp_path: Path
) -> None:
    calls = _phone(hass)
    url = _bare(local_roots / "pk.git")
    work = tmp_path / "ailleurs"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    (work / "README.md").write_text("autre projet\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "-m", "autre")
    _git(work, "push", "-q", url, "main")

    entry = await _entry(hass, git_mode="remote", git_url=url, git_branch="main")
    await hass.async_block_till_done()
    assert _sensor(hass, entry).state == "paused"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "git_not_empty")
    assert len(calls) == 1 and "pause" in calls[0].data["title"]

    # Pendant la pause : rien n'est commité ni envoyé, et une seule notification
    assert (await entry.runtime_data.async_save("salon", GOOD)).ok
    await _settle(hass, entry)
    assert _log(local_roots / "pk.git", "main") == ["autre"]
    assert len(calls) == 1

    # Le dépôt est vidé (nouvelle branche vide côté distant) : la reprise envoie l'état actuel
    _git(local_roots / "pk.git", "update-ref", "-d", "refs/heads/main")
    await entry.runtime_data.git._async_retry()
    await _settle(hass, entry)
    assert _sensor(hass, entry).state == "ok"
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "git_not_empty")
    assert (await entry.runtime_data.async_read("salon")) == GOOD
    files = _git(local_roots / "pk.git", "ls-tree", "-r", "--name-only", "main").split()
    assert files == ["salon.yaml"]


async def test_unreachable_remote_errors_once(
    hass: HomeAssistant, config_dir: Path, local_roots: Path
) -> None:
    calls = _phone(hass)
    entry = await _entry(
        hass, git_mode="remote", git_url=f"file://{local_roots}/absent.git", git_branch="main"
    )
    await hass.async_block_till_done()
    state = _sensor(hass, entry)
    assert state.state == "error" and state.attributes["error"]
    await entry.runtime_data.git._async_retry()
    await _settle(hass, entry)
    assert len(calls) == 1  # une seule fois par cause


# --- Options ------------------------------------------------------------------


async def test_options_remote_refuses_public(
    hass: HomeAssistant, config_dir: Path, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get("https://api.github.com/repos/moi/public", json={"private": False})
    aioclient_mock.get("https://api.github.com/repos/moi/prive", json={"private": True})
    entry = await _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_changes": True, "backups_kept": 3, "git_mode": "remote"}
    )
    assert result["step_id"] == "git"
    fields = {"git_branch": "main", "git_username": "git"}

    bad = await hass.config_entries.options.async_configure(
        result["flow_id"], {**fields, "git_url": "https://github.com/moi/public"}
    )
    assert bad["errors"] == {"base": "token_required"}
    bad = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**fields, "git_url": "https://github.com/moi/public", "git_token": "jeton-secret"},
    )
    assert bad["errors"] == {"base": "public_repo"}

    done = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**fields, "git_url": "https://github.com/moi/prive", "git_token": "jeton-secret"},
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["git_url"] == "https://github.com/moi/prive"
    assert entry.data["git_token"] == "jeton-secret"
    assert "jeton-secret" not in str(dict(entry.options))


async def test_options_git_missing(hass: HomeAssistant, config_dir: Path, monkeypatch) -> None:
    from custom_components.package_keeper import config_flow

    monkeypatch.setattr(config_flow, "git_available", lambda: False)
    entry = await _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_changes": True, "backups_kept": 3, "git_mode": "local"}
    )
    assert result["errors"] == {"git_mode": "git_missing"}


async def test_options_back_to_off_forgets_token(hass: HomeAssistant, config_dir: Path) -> None:
    entry = await _entry(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, "git_token": "x"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_changes": True, "backups_kept": 3, "git_mode": "off"}
    )
    await hass.async_block_till_done()
    assert "git_token" not in entry.data


async def test_turned_public_pauses(hass: HomeAssistant, config_dir: Path, monkeypatch) -> None:
    """Un dépôt devenu public entre deux envois : pause, réparation, rien n'est envoyé."""
    calls = _phone(hass)
    entry = await _entry(hass, git_mode="local")
    git = entry.runtime_data.git
    git.mode, git.url = "remote", "https://github.com/moi/pk"

    async def public(*_args) -> str:
        return "public"

    monkeypatch.setattr(git_sync, "async_visibility", public)
    with pytest.raises(GitError):
        await git._check_visibility()
    await hass.async_block_till_done()
    assert git.status == "paused" and git.error == "public_repo"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "git_public_repo")
    assert len(calls) == 1


async def test_token_only_in_environment(hass: HomeAssistant, config_dir: Path) -> None:
    entry = await _entry(hass, git_mode="local")
    git = entry.runtime_data.git
    git.url, git._token, git.username = "https://github.com/moi/pk", "jeton-secret", "git"
    env = git._env(network=True)
    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert env["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ")
    assert "jeton-secret" not in env["GIT_CONFIG_VALUE_0"]  # encodé, et jamais dans argv
    assert "GIT_CONFIG_KEY_0" not in git._env(network=False)
    assert env["GIT_CONFIG_GLOBAL"] and env["GIT_TERMINAL_PROMPT"] == "0"
