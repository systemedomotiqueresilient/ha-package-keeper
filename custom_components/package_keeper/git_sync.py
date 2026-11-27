"""Synchronisation Git des packages (0.5.0).

Principe :
- un dépôt MIROIR dans /config/.package_keeper/git : le dossier des packages
  n'est jamais transformé en dépôt, et Package Keeper n'écrit toujours que
  dans le dossier des packages et dans /config/.package_keeper ;
- seuls les fichiers .yaml gérés par Package Keeper y sont copiés (jamais
  secrets.yaml, qui n'est pas dans le dossier des packages et dont le nom
  est refusé) ;
- un commit n'est fait qu'APRÈS l'acceptation définitive d'une modification
  (contrôle de configuration passé) ; une modification annulée n'est jamais
  commitée ;
- l'envoi part en tâche de fond, dans une file : le panneau n'attend pas ;
- dépôt distant PUBLIC : refus ferme, sans option (décision de Mathieu). Si la
  visibilité ne peut pas être vérifiée (hébergeur inconnu), refus aussi ;
- le jeton ne passe jamais sur la ligne de commande : il est donné à git par
  l'environnement (GIT_CONFIG_*), et retiré de tout message d'erreur.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from . import store
from .admin_phone import CONF_ADMIN_NOTIFY_TARGET, async_notify_admin
from .const import (
    CONF_GIT_BRANCH,
    CONF_GIT_MODE,
    CONF_GIT_TOKEN,
    CONF_GIT_URL,
    CONF_GIT_USERNAME,
    DEFAULT_GIT_BRANCH,
    DEFAULT_GIT_USERNAME,
    DOMAIN,
    GIT_DIR,
    GIT_MODE_LOCAL,
    GIT_MODE_OFF,
    GIT_MODE_REMOTE,
)

_LOGGER = logging.getLogger(__name__)

SIGNAL_GIT_UPDATED = f"{DOMAIN}_git_updated"
RETRY_INTERVAL = timedelta(minutes=15)
_GIT_TIMEOUT = 120
_API_TIMEOUT = aiohttp.ClientTimeout(total=15)
_AUTHOR = ("Package Keeper", "package_keeper@homeassistant.local")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
# Dépôt local accepté pour un « distant » file:// : jamais dans /config
_LOCAL_ROOTS = ("/share/", "/media/")

# États du capteur « Synchronisation Git »
STATUS_DISABLED = "disabled"
STATUS_UNAVAILABLE = "unavailable"  # git absent
STATUS_OK = "ok"
STATUS_PENDING = "pending"  # commits pas encore envoyés
STATUS_PAUSED = "paused"  # dépôt non vide ou devenu public : action de l'occupant requise
STATUS_ERROR = "error"  # échec d'envoi, nouvel essai plus tard
STATUSES = [
    STATUS_DISABLED,
    STATUS_UNAVAILABLE,
    STATUS_OK,
    STATUS_PENDING,
    STATUS_PAUSED,
    STATUS_ERROR,
]

# Textes du téléphone admin : (titre, message), une seule fois par cause
_PHONE = {
    "not_empty": (
        "Package Keeper : Git en pause",
        "Le dépôt Git distant n'est pas vide et ne contient pas vos packages actuels : "
        "rien n'a été envoyé. Une réparation vous attend : Paramètres → Système → Réparations.",
    ),
    "public_repo": (
        "Package Keeper : Git en pause",
        "Le dépôt Git distant est public : rien n'a été envoyé. Rendez-le privé ou choisissez "
        "un autre dépôt.",
    ),
    "error": (
        "Package Keeper : envoi Git impossible",
        "L'envoi vers le dépôt Git a échoué ({error}). Les commits sont gardés et seront "
        "renvoyés automatiquement.",
    ),
}
_PHONE_EN = {
    "not_empty": (
        "Package Keeper: Git paused",
        "The remote Git repository is not empty and does not hold your current packages: "
        "nothing was sent. A repair is waiting: Settings → System → Repairs.",
    ),
    "public_repo": (
        "Package Keeper: Git paused",
        "The remote Git repository is public: nothing was sent. Make it private or choose "
        "another repository.",
    ),
    "error": (
        "Package Keeper: Git push failed",
        "Pushing to the Git repository failed ({error}). Commits are kept and will be sent "
        "again automatically.",
    ),
}
_MESSAGES = {
    "fr": {
        "saved": "{name} : enregistré",
        "restored": "{name} : restauré",
        "deleted": "{name} : supprimé",
        "renamed": "{old} → {name} : renommé",
        "external": "Modifications hors Package Keeper",
        "initial": "État initial des packages",
    },
    "en": {
        "saved": "{name}: saved",
        "restored": "{name}: restored",
        "deleted": "{name}: deleted",
        "renamed": "{old} → {name}: renamed",
        "external": "Changes made outside Package Keeper",
        "initial": "Initial state of the packages",
    },
}


class GitError(Exception):
    """Échec git ; `code` est stable (traduit), `detail` est déjà nettoyé du jeton."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class _Job:
    message: str
    paths: list[str] = field(default_factory=list)  # fichiers concernés, relatifs (x/y.yaml)
    prepare: bool = False  # premier passage : dépôt miroir et branchement au distant


def git_available() -> bool:
    return shutil.which("git") is not None


def validate_remote(url: str) -> str:
    """Adresse du dépôt distant, nettoyée ; PackageError-like GitError sinon."""
    url = (url or "").strip()
    if url.startswith("file://"):
        path = url.removeprefix("file://")
        if not path.startswith(_LOCAL_ROOTS) or ".." in Path(path).parts:
            raise GitError("invalid_url")
        return url.rstrip("/")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise GitError("invalid_url")
    if parts.username or parts.password:
        raise GitError("url_with_credentials")  # le jeton va dans son propre champ
    path = parts.path.strip("/").removesuffix(".git")
    if path.count("/") < 1:
        raise GitError("invalid_url")
    return url.rstrip("/")


def validate_branch(branch: str) -> str:
    branch = (branch or "").strip()
    if not _BRANCH_RE.match(branch) or ".." in branch or branch.startswith(("-", "/")):
        raise GitError("invalid_branch")
    return branch


async def async_visibility(hass: HomeAssistant, url: str, username: str, token: str) -> str:
    """« private », « public », « local » ou « unknown » (hébergeur non reconnu).

    GitHub, Gitea, Forgejo (Codeberg…) et GitLab. Lève GitError("unreachable")
    ou GitError("auth_failed") si l'API répond mal.
    """
    if url.startswith("file://"):
        return "local"
    parts = urlsplit(url)
    host = parts.hostname or ""
    repo = parts.path.strip("/").removesuffix(".git")
    base = f"https://{parts.netloc}"
    session = async_get_clientsession(hass)
    candidates: list[tuple[str, dict[str, str], Callable[[dict], str | None]]]
    if host == "github.com":
        candidates = [
            (
                f"https://api.github.com/repos/{repo}",
                {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                _github_visibility,
            )
        ]
    else:
        candidates = [
            (f"{base}/api/v1/repos/{repo}", {"Authorization": f"token {token}"}, _gitea_visibility),
            (
                f"{base}/api/v4/projects/{quote(repo, safe='')}",
                {"PRIVATE-TOKEN": token},
                _gitlab_visibility,
            ),
        ]
    denied = False
    for api, headers, read in candidates:
        try:
            async with session.get(api, headers=headers, timeout=_API_TIMEOUT) as response:
                if response.status in (401, 403):
                    denied = True
                    continue
                if response.status != 200:
                    continue
                try:
                    data = await response.json(content_type=None)
                except ValueError:
                    continue
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GitError("unreachable", type(err).__name__) from err
        if isinstance(data, dict) and (visibility := read(data)):
            return visibility
    if denied:
        raise GitError("auth_failed")
    return "unknown"


def _github_visibility(data: dict) -> str | None:
    if isinstance(data.get("private"), bool):
        return "private" if data["private"] else "public"
    return None


def _gitea_visibility(data: dict) -> str | None:
    # Gitea / Forgejo : « private » ; un dépôt interne reste lisible par tout compte
    if isinstance(data.get("private"), bool) and "full_name" in data:
        if data.get("internal"):
            return "public"
        return "private" if data["private"] else "public"
    return None


def _gitlab_visibility(data: dict) -> str | None:
    visibility = data.get("visibility")
    if visibility == "private":
        return "private"
    if visibility in ("public", "internal"):  # internal : tout compte de l'instance
        return "public"
    return None


def redact(text: str, *secrets: str) -> str:
    """Retire le jeton (en clair et en base64) d'un message de git."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return re.sub(r"(Authorization:\s*\w+\s+)\S+", r"\1***", text)


def _classify(stderr: str) -> str:
    low = stderr.lower()
    if any(k in low for k in ("authentication failed", "401", "403", "permission", "denied")):
        return "auth_failed"
    if any(k in low for k in ("could not resolve", "unable to access", "timed out", "connect")):
        return "unreachable"
    if any(k in low for k in ("rejected", "non-fast-forward", "fetch first")):
        return "rejected"
    if "not found" in low or "does not appear to be a git repository" in low:
        return "not_found"
    return "git_failed"


# --- Miroir (synchrone, dans l'executor) -------------------------------------


def _wanted(setup: store.PackagesSetup) -> dict[str, Path]:
    if not setup.enabled:
        return {}
    return {
        f"{item['name']}.yaml": store.package_path(setup, item["name"])
        for item in store.list_packages(setup)
    }


def _tracked(repo: Path) -> set[str]:
    return {
        path.relative_to(repo).as_posix()
        for path in repo.rglob("*.yaml")
        if ".git" not in path.relative_to(repo).parts and path.is_file()
    }


def mirror(setup: store.PackagesSetup, repo: Path, only: set[str] | None, skip: set[str]) -> None:
    """Recopie les packages dans le dépôt miroir.

    only : seulement ces fichiers (None = tous) ; skip : ces fichiers restent tels
    qu'ils sont dans le miroir (ils feront l'objet de leur propre commit).
    """
    wanted = _wanted(setup)
    for rel in set(wanted) | _tracked(repo):
        if rel in skip or (only is not None and rel not in only):
            continue
        target = repo / rel
        source = wanted.get(rel)
        if source is None:
            target.unlink(missing_ok=True)
            folder = target.parent
            while folder != repo and folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
                folder = folder.parent
            continue
        data = source.read_bytes()
        if not target.is_file() or target.read_bytes() != data:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def local_blobs(setup: store.PackagesSetup) -> dict[str, str]:
    """Empreintes git (blob SHA-1) des packages actuels : chemin → sha."""
    blobs = {}
    for rel, path in _wanted(setup).items():
        data = path.read_bytes()
        # Empreinte d'objet git, pas un usage de sécurité
        blobs[rel] = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return blobs


# --- Synchronisation ---------------------------------------------------------


class GitSync:
    """Un dépôt miroir, une file de commits, un envoi en tâche de fond."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        setup_getter: Callable[[], Any],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._setup_getter = setup_getter
        self.repo = Path(hass.config.config_dir) / GIT_DIR
        self.mode: str = entry.options.get(CONF_GIT_MODE, GIT_MODE_OFF)
        self.url: str = entry.options.get(CONF_GIT_URL, "") or ""
        self.branch: str = entry.options.get(CONF_GIT_BRANCH, DEFAULT_GIT_BRANCH)
        self.username: str = entry.options.get(CONF_GIT_USERNAME, DEFAULT_GIT_USERNAME)
        self._token: str = entry.data.get(CONF_GIT_TOKEN, "") or ""
        self.status = STATUS_DISABLED
        self.error: str | None = None
        self.last_commit: str | None = None
        self.last_push: str | None = None
        self.pending = 0
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.git")
        self._state: dict[str, Any] = {}
        self._queue: asyncio.Queue[_Job] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._unsub_retry: Callable[[], None] | None = None

    # --- cycle de vie ------------------------------------------------------

    def settings_changed(self, entry: ConfigEntry) -> bool:
        """Vrai si les réglages Git de l'entrée ne sont plus ceux de cette instance."""
        options = entry.options
        return (
            options.get(CONF_GIT_MODE, GIT_MODE_OFF),
            options.get(CONF_GIT_URL, "") or "",
            options.get(CONF_GIT_BRANCH, DEFAULT_GIT_BRANCH),
            options.get(CONF_GIT_USERNAME, DEFAULT_GIT_USERNAME),
            entry.data.get(CONF_GIT_TOKEN, "") or "",
        ) != (self.mode, self.url, self.branch, self.username, self._token)

    @property
    def enabled(self) -> bool:
        return self.mode in (GIT_MODE_LOCAL, GIT_MODE_REMOTE)

    @property
    def remote(self) -> bool:
        return self.mode == GIT_MODE_REMOTE and bool(self.url)

    async def async_start(self) -> None:
        if not self.enabled:
            self._set(STATUS_DISABLED)
            return
        if not await self.hass.async_add_executor_job(git_available):
            self._set(STATUS_UNAVAILABLE, "git_missing")
            return
        self._state = await self._store.async_load() or {}
        if self._state.get("url") != (self.url if self.remote else ""):
            # Autre dépôt distant : on repart de zéro côté envoi
            self._state = {"url": self.url if self.remote else "", "alerted": []}
        self._queue.put_nowait(_Job("", prepare=True))
        self._worker = self.entry.async_create_background_task(
            self.hass, self._async_run(), f"{DOMAIN} git"
        )
        if self.remote:
            self._unsub_retry = async_track_time_interval(
                self.hass, self._async_retry, RETRY_INTERVAL
            )

    async def async_stop(self) -> None:
        if self._unsub_retry:
            self._unsub_retry()
            self._unsub_retry = None
        if self._worker:
            self._worker.cancel()
            self._worker = None

    @callback
    def async_queue(self, action: str, name: str, old: str | None = None) -> None:
        """À appeler après une modification ACCEPTÉE (enregistrée, supprimée…)."""
        if not self.enabled or self._worker is None:
            return
        paths = [f"{name}.yaml"] + ([f"{old}.yaml"] if old else [])
        self._queue.put_nowait(_Job(self._text(action).format(name=name, old=old), paths))

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "error": self.error,
            "pending": self.pending,
            "last_commit": self.last_commit,
            "last_push": self.last_push,
        }

    # --- tâche de fond -----------------------------------------------------

    async def _async_run(self) -> None:
        """Traite la file, une tâche à la fois (le premier élément prépare le dépôt)."""
        while True:
            job = await self._queue.get()
            try:
                if job.prepare:
                    await self._async_prepare()
                else:
                    await self._async_handle(job)
            except GitError as err:
                self._fail(err)
            except OSError as err:
                self._fail(GitError("git_failed", type(err).__name__))
            finally:
                self._queue.task_done()

    async def async_wait_idle(self) -> None:
        """Attend que la file soit vide (tests, et arrêt propre)."""
        await self._queue.join()

    async def _async_prepare(self) -> None:
        """Dépôt miroir prêt ; premier branchement au dépôt distant si besoin."""
        if not (self.repo / ".git").is_dir():
            await self.hass.async_add_executor_job(
                lambda: self.repo.mkdir(parents=True, exist_ok=True)
            )
            await self._git("init", "-q", "-b", self.branch)
        await self._git("config", "user.name", _AUTHOR[0])
        await self._git("config", "user.email", _AUTHOR[1])
        await self._git("config", "core.autocrlf", "false")
        if self.remote:
            await self._git("remote", "remove", "origin", check=False)
            await self._git("remote", "add", "origin", self.url)
            if not self._state.get("connected"):
                await self._async_connect()
                return
        else:
            await self._git("remote", "remove", "origin", check=False)
        # Rattrape ce qui a changé pendant l'arrêt (ou l'état initial)
        message = self._text("initial" if not await self._has_commits() else "external")
        await self._async_commit(message, only=None, skip=set())
        await self._async_push()

    async def _async_connect(self) -> None:
        """Premier envoi : dépôt vide → état initial ; contenu identique → reprise ; sinon pause."""
        await self._check_visibility()
        refs = (await self._git("ls-remote", "origin", network=True)).strip()
        if not refs:
            if not await self._has_commits():
                await self._async_commit(self._text("initial"), only=None, skip=set())
            else:
                await self._async_commit(self._text("external"), only=None, skip=set())
            self._state["connected"] = True
            await self._save_state()
            self._clear_issue("git_not_empty")
            await self._async_push()
            return
        if await self._remote_identical():
            await self._git("reset", "-q", "--hard", "FETCH_HEAD")
            self._state["connected"] = True
            self._state["pushed"] = (await self._git("rev-parse", "HEAD")).strip()
            await self._save_state()
            await self._refresh_counts()
            self._set(STATUS_OK)
            self._clear_issue("git_not_empty")
            return
        self._pause("not_empty")

    async def _remote_identical(self) -> bool:
        fetched = await self._git(
            "fetch", "-q", "origin", self.branch, check=False, network=True, raw=True
        )
        if fetched[0] != 0:
            return False  # branche absente : dépôt non vide mais sans nos packages
        listing = await self._git("ls-tree", "-r", "FETCH_HEAD")
        remote: dict[str, str] = {}
        for line in listing.splitlines():
            meta, _, path = line.partition("\t")
            remote[path] = meta.split()[2]
        setup = await self._setup_getter()
        local = await self.hass.async_add_executor_job(local_blobs, setup)
        return remote == local

    async def _async_handle(self, job: _Job) -> None:
        if self.status == STATUS_UNAVAILABLE:
            return
        if self.remote and not self._state.get("connected"):
            # Pas encore branché (dépôt non vide, réseau absent au démarrage…) : on réessaie.
            # Rien n'est commité pendant une pause : l'état actuel partira au branchement.
            await self._async_connect()
            return
        if self.status == STATUS_PAUSED:
            await self._check_visibility()  # dépôt rendu privé entre-temps ?
        # 1) ce qui a changé ailleurs (Samba, File Editor…), à part
        await self._async_commit(self._text("external"), only=None, skip=set(job.paths))
        # 2) la modification elle-même
        await self._async_commit(job.message, only=set(job.paths), skip=set())
        await self._async_push()

    async def _async_commit(self, message: str, *, only: set[str] | None, skip: set[str]) -> None:
        setup = await self._setup_getter()
        await self.hass.async_add_executor_job(mirror, setup, self.repo, only, skip)
        await self._git("add", "-A")
        changed, _, _ = await self._git("diff", "--cached", "--quiet", check=False, raw=True)
        if changed == 0:
            return
        await self._git("commit", "-q", "-m", message)
        self.last_commit = (await self._git("rev-parse", "--short", "HEAD")).strip()

    async def _async_push(self) -> None:
        await self._refresh_counts()
        if not self.remote:
            self._set(STATUS_OK)
            return
        if not self._state.get("connected"):
            return
        if self.pending:
            await self._check_visibility()
            await self._git("push", "-q", "origin", f"HEAD:refs/heads/{self.branch}", network=True)
            self._state["pushed"] = (await self._git("rev-parse", "HEAD")).strip()
            self.last_push = datetime.now(UTC).isoformat()
            await self._save_state()
            await self._refresh_counts()
        self._set(STATUS_OK)

    async def _async_retry(self, _now: datetime | None = None) -> None:
        """Nouvel essai : envoi en échec, dépôt vidé ou rendu privé entre-temps."""
        if self.status in (STATUS_ERROR, STATUS_PAUSED, STATUS_PENDING):
            self._queue.put_nowait(_Job(self._text("external")))

    async def _check_visibility(self) -> None:
        visibility = await async_visibility(self.hass, self.url, self.username, self._token)
        if visibility == "public":
            self._pause("public_repo")
            raise GitError("public_repo")
        if visibility == "unknown":
            raise GitError("visibility_unknown")
        self._clear_issue("git_public_repo")

    # --- état --------------------------------------------------------------

    async def _has_commits(self) -> bool:
        code, _, _ = await self._git("rev-parse", "--verify", "-q", "HEAD", check=False, raw=True)
        return code == 0

    async def _refresh_counts(self) -> None:
        if not await self._has_commits():
            self.pending = 0
            return
        self.last_commit = (await self._git("rev-parse", "--short", "HEAD")).strip()
        pushed = self._state.get("pushed")
        if not self.remote:
            self.pending = 0
            return
        span = f"{pushed}..HEAD" if pushed else "HEAD"
        code, out, _ = await self._git("rev-list", "--count", span, check=False, raw=True)
        self.pending = int(out.strip() or 0) if code == 0 else 0

    def _set(self, status: str, error: str | None = None) -> None:
        if status == STATUS_OK and self.pending:
            status = STATUS_PENDING
        self.status, self.error = status, error
        if status in (STATUS_OK, STATUS_PENDING) and self._state.get("alerted"):
            self._state["alerted"] = []
            self.hass.async_create_task(self._save_state())
        async_dispatcher_send(self.hass, SIGNAL_GIT_UPDATED)

    def _fail(self, err: GitError) -> None:
        if self.status == STATUS_PAUSED:
            async_dispatcher_send(self.hass, SIGNAL_GIT_UPDATED)
            return
        _LOGGER.info("Synchronisation Git : %s", err)  # attendu (réseau, jeton) : pas un bug
        self._set(STATUS_ERROR, err.code)
        self._phone_once("error", err.code)

    def _pause(self, reason: str) -> None:
        self._set(STATUS_PAUSED, reason)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"git_{reason}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"git_{reason}",
            translation_placeholders={"url": self.url, "branch": self.branch},
        )
        self._phone_once(reason, reason)

    def _clear_issue(self, issue_id: str) -> None:
        ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _phone_once(self, key: str, code: str) -> None:
        alerted: list[str] = self._state.setdefault("alerted", [])
        if code in alerted:
            return
        alerted.append(code)
        self.hass.async_create_task(self._save_state())
        target = self.entry.data.get(CONF_ADMIN_NOTIFY_TARGET)
        if not target:
            return
        texts = _PHONE if self._lang == "fr" else _PHONE_EN
        title, message = texts[key]
        self.entry.async_create_task(
            self.hass,
            async_notify_admin(self.hass, target, title, message.format(error=code)),
            f"{DOMAIN} git téléphone",
        )

    async def _save_state(self) -> None:
        await self._store.async_save(self._state)

    @property
    def _lang(self) -> str:
        return "fr" if (self.hass.config.language or "").startswith("fr") else "en"

    def _text(self, key: str) -> str:
        return _MESSAGES[self._lang][key]

    # --- git ---------------------------------------------------------------

    def _env(self, network: bool) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.repo.parent),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/false",
            "LC_ALL": "C",
        }
        if network and self.url.startswith("https://") and self._token:
            basic = base64.b64encode(f"{self.username}:{self._token}".encode()).decode()
            env |= {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
            }
        return env

    async def _git(
        self, *args: str, check: bool = True, network: bool = False, raw: bool = False
    ) -> Any:
        """Lance git dans le dépôt miroir. raw=True renvoie (code, stdout, stderr)."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=self.repo,
            env=self._env(network),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), _GIT_TIMEOUT)
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise GitError("unreachable", "timeout") from exc
        basic = base64.b64encode(f"{self.username}:{self._token}".encode()).decode()
        stdout = out.decode(errors="replace")
        stderr = redact(err.decode(errors="replace"), self._token, basic)
        if raw:
            return proc.returncode, stdout, stderr
        if check and proc.returncode:
            raise GitError(_classify(stderr), stderr.strip()[-300:])
        return stdout
