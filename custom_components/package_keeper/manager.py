"""Enregistrer, supprimer, restaurer un package : contrôles et retour arrière automatique."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import check_config, entity_registry as er
from homeassistant.util.yaml.loader import Secrets, load_yaml_dict

from . import deep_checks, store
from .admin_phone import CONF_ADMIN_NOTIFY_TARGET, async_notify_admin
from .const import (
    CONF_BACKUPS_KEPT,
    CONF_NOTIFY_CHANGES,
    DEFAULT_BACKUPS_KEPT,
    DEFAULT_NOTIFY_CHANGES,
    DOMAIN,
    VERSION,
)
from .store import PackageError, PackagesSetup

_LOGGER = logging.getLogger(__name__)

_INCLUDE_RE = re.compile(r"!include\w*\s+[\"']?([^\s\"'#]+)")
# Domaines rechargés par une action dédiée, même sans action « <domaine>.reload »
_SPECIAL_RELOAD = {"homeassistant": "homeassistant.reload_core_config"}

# Textes envoyés au téléphone admin : (titre, message)
_PHONE = {
    "saved": ("Package Keeper", "Package « {name} » enregistré."),
    "deleted": ("Package Keeper", "Package « {name} » supprimé (sauvegarde conservée)."),
    "restored": ("Package Keeper", "Package « {name} » restauré depuis une sauvegarde."),
    "rolled_back": (
        "Package Keeper : modification annulée",
        "Le package « {name} » cassait la configuration : l'ancienne version a été remise.",
    ),
}
_PHONE_EN = {
    "saved": ("Package Keeper", "Package “{name}” saved."),
    "deleted": ("Package Keeper", "Package “{name}” deleted (backup kept)."),
    "restored": ("Package Keeper", "Package “{name}” restored from a backup."),
    "rolled_back": (
        "Package Keeper: change cancelled",
        "Package “{name}” broke the configuration: the previous version was put back.",
    ),
}


@dataclass
class Outcome:
    """Résultat renvoyé au panneau."""

    ok: bool
    name: str
    action: str  # checked | saved | deleted | restored
    rolled_back: bool = False
    error: str | None = None  # code traduit dans le panneau
    detail: str | None = None  # message brut (YAML, contrôle de configuration)
    advice: dict[str, list[str]] = field(default_factory=dict)  # avis d'Entity Inventory
    backup: str | None = None
    reload: list[str] = field(default_factory=list)
    restart: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)  # entités qui ne seront plus fournies

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], {})} | {
            "ok": self.ok,
            "rolled_back": self.rolled_back,
        }


class PackageManager:
    """Une seule modification à la fois ; chaque modification est réversible."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config_dir = hass.config.config_dir
        self._lock = asyncio.Lock()

    # --- lecture -----------------------------------------------------------

    async def _run(self, func: Callable, *args: Any) -> Any:
        return await self.hass.async_add_executor_job(func, *args)

    async def async_setup_info(self) -> PackagesSetup:
        return await self._run(store.detect_setup, self.config_dir)

    async def async_overview(self) -> dict[str, Any]:
        setup = await self.async_setup_info()
        packages = await self._run(store.list_packages, setup) if setup.enabled else []
        deleted = await self._run(store.list_deleted, self.config_dir, setup)
        return {
            "enabled": setup.enabled,
            "mode": setup.mode,
            "directory": _display_dir(self.config_dir, setup.directory),
            "packages": packages,
            "deleted": deleted,
            "entity_inventory": self.hass.services.has_service("entity_inventory", "validate"),
            "version": VERSION,  # le panneau compare avec la sienne (mise à jour sans rechargement)
        }

    async def async_read(self, name: str) -> str:
        setup = await self._enabled_setup()
        return await self._run(store.read_package, setup, name)

    async def async_backups(self, name: str) -> list[dict]:
        return await self._run(store.list_backups, self.config_dir, name)

    async def async_read_backup(self, name: str, backup_id: str) -> str:
        return await self._run(store.read_backup, self.config_dir, name, backup_id)

    # --- écriture ----------------------------------------------------------

    async def async_save(
        self, name: str, text: str, *, dry_run: bool = False, action: str = "saved"
    ) -> Outcome:
        """Vérifie puis (sauf dry_run) enregistre ; annule si la configuration casse."""
        outcome = Outcome(ok=False, name=name, action="checked" if dry_run else action)
        try:
            setup = await self._enabled_setup()
            data = store.check_text(text)
            await self._run(self._check_includes, setup, name, text)  # nom et !include
        except PackageError as err:
            outcome.error, outcome.detail = err.code, err.detail or None
            return outcome

        async with self._lock:
            tmp = await self._run(store.stage, setup, name, data)
            try:
                content = await self._run(_load, tmp, self.config_dir)
            except PackageError as err:
                await self._run(store.discard, tmp)
                outcome.error, outcome.detail = err.code, err.detail or None
                return outcome

            body = _body(content, setup.mode)
            problems = await self._deep_problems(setup, name, body)
            if problems:
                await self._run(store.discard, tmp)
                outcome.error, outcome.detail = "invalid_content", "\n".join(problems)
                outcome.advice = await self._advice(text)
                return outcome

            outcome.advice = await self._advice(text)
            old_body = await self._current_body(setup, name)
            outcome.reload, outcome.restart = self._reload_plan(body, old_body)
            if old_body is not None:
                outcome.removed = sorted(
                    deep_checks.defined_entities(self.hass, old_body)
                    - deep_checks.defined_entities(self.hass, body)
                )
            if dry_run:
                await self._run(store.discard, tmp)
                outcome.ok = True
                return outcome

            before = await _config_problems(self.hass)
            previous = await self._run(store.current_bytes, setup, name)
            outcome.backup = await self._run(
                store.backup, self.config_dir, setup, name, self._keep, "before_" + action
            )
            await self._run(store.commit, setup, name, tmp)
            if await self._broken_after(before, setup, name, previous, outcome):
                return outcome

        outcome.ok = True
        await self._phone(action, name)
        return outcome

    async def async_delete(self, name: str) -> Outcome:
        outcome = Outcome(ok=False, name=name, action="deleted")
        try:
            setup = await self._enabled_setup()
            previous = await self._run(store.current_bytes, setup, name)
        except PackageError as err:
            outcome.error = err.code
            return outcome
        if previous is None:
            outcome.error = "not_found"
            return outcome

        async with self._lock:
            try:
                path = await self._run(store.package_path, setup, name)
                body = _body(await self._run(_load, path, self.config_dir), setup.mode)
                outcome.reload, outcome.restart = self._reload_plan(body)
                outcome.removed = sorted(deep_checks.defined_entities(self.hass, body))
            except PackageError:
                pass  # un package illisible se supprime quand même
            before = await _config_problems(self.hass)
            outcome.backup = await self._run(
                store.backup, self.config_dir, setup, name, max(self._keep, 1), "deleted"
            )
            await self._run(store.remove, setup, name)
            if await self._broken_after(before, setup, name, previous, outcome):
                return outcome

        outcome.ok = True
        await self._phone("deleted", name)
        return outcome

    async def async_restore(self, name: str, backup_id: str) -> Outcome:
        try:
            text = await self.async_read_backup(name, backup_id)
        except PackageError as err:
            return Outcome(ok=False, name=name, action="restored", error=err.code)
        return await self.async_save(name, text, action="restored")

    async def async_dependents(self, name: str) -> dict[str, list[str]]:
        """Autres packages qui citent les entités créées par celui-ci (avant suppression)."""
        setup = await self._enabled_setup()
        path = await self._run(store.package_path, setup, name)
        try:
            content = _body(await self._run(_load, path, self.config_dir), setup.mode)
        except PackageError:
            return {}
        defined = deep_checks.defined_entities(self.hass, content)
        if not defined:
            return {}
        _, texts = await self._run(_load_others, setup, name, self.config_dir)
        return deep_checks.citing(defined, texts)

    @callback
    def async_orphans(self, entity_ids: list[str]) -> list[str]:
        """Parmi ces entités, celles que plus rien ne fournit (« non fournie » dans HA).

        Home Assistant les garde dans le registre, indisponibles, avec l'attribut
        restored: true. On les signale ; seul l'occupant les supprime.
        """
        registry = er.async_get(self.hass)
        orphans = []
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if registry.async_get(entity_id) is None:
                continue  # déjà supprimée du registre
            if state is None or state.attributes.get("restored"):
                orphans.append(entity_id)
        return sorted(orphans)

    async def async_reload(self, services: list[str]) -> list[str]:
        """Appelle les actions de rechargement proposées ; renvoie celles appelées."""
        done = []
        for service in services:
            domain, _, action = service.partition(".")
            allowed = action == "reload" or service in _SPECIAL_RELOAD.values()
            if not allowed or not self.hass.services.has_service(domain, action):
                continue
            await self.hass.services.async_call(domain, action, blocking=True)
            done.append(service)
        return done

    # --- interne -----------------------------------------------------------

    @property
    def _keep(self) -> int:
        return int(self.entry.options.get(CONF_BACKUPS_KEPT, DEFAULT_BACKUPS_KEPT))

    async def _enabled_setup(self) -> PackagesSetup:
        setup = await self.async_setup_info()
        if not setup.enabled:
            raise PackageError("packages_disabled")
        return setup

    async def _deep_problems(
        self, setup: PackagesSetup, name: str, body: dict[str, Any]
    ) -> list[str]:
        """Templates, automatisations, scripts, doublons d'identifiants."""
        problems = deep_checks.template_errors(self.hass, body)
        problems += await deep_checks.automation_script_errors(self.hass, body)
        contents, _ = await self._run(_load_others, setup, name, self.config_dir)
        others = {other: _body(content, setup.mode) for other, content in contents.items()}
        problems += deep_checks.duplicate_errors(body, others)
        return problems

    def _check_includes(self, setup: PackagesSetup, name: str, text: str) -> None:
        """Un !include ne doit pas aller chercher un fichier hors de /config."""
        base = store.package_path(setup, name).parent
        config = Path(self.config_dir).resolve()
        for target in _INCLUDE_RE.findall(text):
            resolved = (base / target).resolve()
            if config not in resolved.parents or ".storage" in resolved.parts:
                raise PackageError("include_outside", target)

    async def _broken_after(
        self,
        before: set[str],
        setup: PackagesSetup,
        name: str,
        previous: bytes | None,
        outcome: Outcome,
    ) -> bool:
        """Contrôle la configuration ; remet l'ancien état si un NOUVEAU problème apparaît.

        Les erreurs ET les avertissements comptent : pour Home Assistant, une
        intégration mal configurée n'est qu'un avertissement, mais elle ne
        démarre plus (tous les input_boolean disparaissent, par exemple). Un
        problème déjà présent avant la modification ne bloque pas : sinon une
        configuration déjà cassée ailleurs empêcherait toute correction.
        """
        new = sorted((await _config_problems(self.hass)) - before)
        if not new:
            return False
        await self._run(store.restore_bytes, setup, name, previous)
        outcome.rolled_back = True
        outcome.error = "config_invalid"
        outcome.detail = "\n\n".join(new)
        _LOGGER.warning("Package %s annulé : la configuration ne passait plus le contrôle", name)
        await self._phone("rolled_back", name, always=True)
        return True

    async def _advice(self, text: str) -> dict[str, list[str]]:
        """Avis d'Entity Inventory (entités, actions, syntaxe), s'il est installé.

        Indicatif seulement : une entité créée par le package lui-même n'existe
        pas encore et peut être signalée.
        """
        if not self.hass.services.has_service("entity_inventory", "validate"):
            return {}
        try:
            result = await self.hass.services.async_call(
                "entity_inventory",
                "validate",
                {"yaml": text},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug("Avis d'Entity Inventory indisponible : %s", err)
            return {}
        result = result or {}
        if not result.get("entities_checked") and not result.get("actions_checked"):
            # Package qui ne cite aucune entité ni action (ex. un input_boolean) :
            # Entity Inventory répond « rien à vérifier », ce n'est pas une erreur.
            return {}
        return {
            key: [str(item) for item in result.get(key) or []]
            for key in ("errors", "warnings")
            if result.get(key)
        }

    async def _current_body(self, setup: PackagesSetup, name: str) -> dict[str, Any] | None:
        """Contenu actuel du package (avant modification), ou None s'il n'existe pas."""
        path = await self._run(store.package_path, setup, name)
        if not await self._run(path.is_file):
            return None
        try:
            return _body(await self._run(_load, path, self.config_dir), setup.mode)
        except PackageError:
            return None  # illisible : on retombe sur le plan complet

    def _reload_plan(
        self, content: dict[str, Any], previous: dict[str, Any] | None = None
    ) -> tuple[list[str], list[str]]:
        """(actions de rechargement possibles, domaines qui exigent un redémarrage).

        Avec `previous`, seuls les domaines qui ont réellement changé (ajoutés,
        modifiés ou retirés) sont pris en compte.
        """
        if previous is not None:
            changed = {
                key for key in set(content) | set(previous) if content.get(key) != previous.get(key)
            }
            # Un domaine retiré se recharge aussi : ses entités doivent disparaître
            content = {key: _merge_items(content.get(key), previous.get(key)) for key in changed}
        services = self.hass.services
        reload: set[str] = set()
        restart: set[str] = set()
        for domain, value in content.items():
            domain = str(domain)
            if domain in _SPECIAL_RELOAD:
                reload.add(_SPECIAL_RELOAD[domain])
                continue
            platforms = {
                str(item["platform"])
                for item in (value if isinstance(value, list) else [])
                if isinstance(item, dict) and isinstance(item.get("platform"), str)
            }
            if platforms:  # sensor: - platform: derivative → derivative.reload ?
                for platform in sorted(platforms):
                    if services.has_service(platform, "reload"):
                        reload.add(f"{platform}.reload")
                    else:
                        restart.add(f"{domain} ({platform})")
                continue
            if services.has_service(domain, "reload"):
                reload.add(f"{domain}.reload")
            else:
                restart.add(domain)
        return sorted(reload), sorted(restart)

    async def _phone(self, key: str, name: str, *, always: bool = False) -> None:
        target = self.entry.data.get(CONF_ADMIN_NOTIFY_TARGET)
        notify = self.entry.options.get(CONF_NOTIFY_CHANGES, DEFAULT_NOTIFY_CHANGES)
        if not target or not (always or notify):
            return
        texts = _PHONE if (self.hass.config.language or "").startswith("fr") else _PHONE_EN
        title, message = texts[key]
        self.entry.async_create_task(
            self.hass,
            async_notify_admin(self.hass, target, title, message.format(name=name)),
            f"{DOMAIN} téléphone admin",
        )


async def _config_problems(hass: HomeAssistant) -> set[str]:
    """Erreurs et avertissements du contrôle de configuration (celui du bouton « Vérifier »)."""
    result = await check_config.async_check_ha_config_file(hass)
    return {err.message for err in (*result.errors, *result.warnings)}


def _load(path: Path, config_dir: str) -> dict[str, Any]:
    """Lecture avec le chargeur de Home Assistant (même !secret, même !include)."""
    try:
        content = load_yaml_dict(path, Secrets(Path(config_dir)))
    except HomeAssistantError as err:
        raise PackageError("yaml_error", _short(str(err), path)) from err
    if not content:
        raise PackageError("empty")
    return dict(content)


def _merge_items(new: Any, old: Any) -> Any:
    """Valeur d'un domaine modifié, en gardant les plateformes de l'ancienne et de la nouvelle."""
    if isinstance(new, list) or isinstance(old, list):
        return [*(new if isinstance(new, list) else []), *(old if isinstance(old, list) else [])]
    return new if new is not None else old


def _body(content: dict[str, Any], mode: str | None) -> dict[str, Any]:
    """Contenu « domaines » d'un fichier ; en mode merge_named, ses packages fusionnés."""
    if mode != "include_dir_merge_named":
        return content
    merged: dict[str, Any] = {}
    for value in content.values():
        if isinstance(value, dict):
            merged.update(value)
    return merged


def _load_others(
    setup: PackagesSetup, exclude: str, config_dir: str
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Contenu chargé et texte brut des AUTRES packages (les illisibles sont ignorés)."""
    contents: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    for item in store.list_packages(setup):
        other = item["name"]
        if other == exclude:
            continue
        path = store.package_path(setup, other)
        try:
            texts[other] = path.read_text(encoding="utf-8")
            contents[other] = _load(path, config_dir)
        except (OSError, UnicodeDecodeError, PackageError):
            continue
    return contents, texts


def _short(message: str, path: Path) -> str:
    """Retire le chemin du fichier temporaire du message d'erreur."""
    return message.replace(str(path), path.name.removeprefix(".").removesuffix(".pk-tmp"))


def _display_dir(config_dir: str, directory: Path) -> str:
    try:
        return "/config/" + directory.relative_to(Path(config_dir).resolve()).as_posix()
    except ValueError:
        return str(directory)
