"""Fichiers de packages : chemins sûrs, sauvegardes, écriture atomique, restauration.

Tout ce module est synchrone (accès disque) : il s'exécute dans l'executor.
Package Keeper n'écrit QUE dans le dossier des packages et dans son dossier de
sauvegardes ; il ne modifie jamais configuration.yaml.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import shutil

from .const import BACKUP_DIR, MAX_PACKAGE_BYTES, PACKAGES_DIR_DEFAULT

# Nom de package valide pour Home Assistant (clé « slug ») ; idem pour les sous-dossiers
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")
# homeassistant: … packages: !include_dir_named packages  (ou _merge_named)
_PACKAGES_RE = re.compile(
    r"^\s*packages\s*:\s*!(include_dir_named|include_dir_merge_named)\s+[\"']?([^\s\"'#]+)",
    re.MULTILINE,
)
_COMMENT_RE = re.compile(r"^\s*#\s?(.*\S)\s*$")
_STAMP_FORMAT = "%Y%m%d-%H%M%S"


class PackageError(Exception):
    """Refus explicite ; `code` est traduit dans le panneau."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PackagesSetup:
    """Comment configuration.yaml charge les packages."""

    enabled: bool
    mode: str | None  # include_dir_named | include_dir_merge_named
    directory: Path


def detect_setup(config_dir: str) -> PackagesSetup:
    """Lit configuration.yaml (texte brut, aucun secret résolu)."""
    default = Path(config_dir) / PACKAGES_DIR_DEFAULT
    try:
        text = (Path(config_dir) / "configuration.yaml").read_text(encoding="utf-8")
    except OSError:
        return PackagesSetup(False, None, default)
    for match in _PACKAGES_RE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        if text[line_start : match.start()].lstrip().startswith("#"):
            continue
        directory = (Path(config_dir) / match.group(2)).resolve()
        return PackagesSetup(True, match.group(1), directory)
    return PackagesSetup(False, None, default)


def validate_name(name: str) -> tuple[str, ...]:
    """« chauffage/derivee_wc » ou « derivee_wc.yaml » → ('chauffage', 'derivee_wc').

    Refuse tout ce qui pourrait sortir du dossier des packages.
    """
    if not isinstance(name, str):
        raise PackageError("invalid_name")
    name = name.strip().removesuffix(".yaml")
    parts = tuple(name.split("/"))
    if not name or len(parts) > 4 or not all(_SLUG_RE.match(p) for p in parts):
        raise PackageError("invalid_name")
    if parts[-1] == "secrets":
        # !include_dir_named ignore tout fichier secrets.yaml : le package ne serait jamais chargé
        raise PackageError("invalid_name")
    return parts


def canonical(name: str) -> str:
    """Nom normalisé : « chauffage/derivee_wc.yaml » → « chauffage/derivee_wc »."""
    return "/".join(validate_name(name))


def stem_conflict(setup: PackagesSetup, name: str, ignore: str | None = None) -> str | None:
    """Autre package qui porterait le même nom pour Home Assistant (0.4.0).

    Avec !include_dir_named, le nom du package est le nom du fichier SANS son
    dossier : « salon/lumieres » et « cuisine/lumieres » s'écrasent l'un l'autre
    sans erreur. Sans objet en mode include_dir_merge_named.
    """
    if setup.mode != "include_dir_named":
        return None
    stem = validate_name(name)[-1]
    for item in list_packages(setup):
        other = item["name"]
        if other in (canonical(name), ignore):
            continue
        if other.rsplit("/", 1)[-1] == stem:
            return other
    return None


def package_path(setup: PackagesSetup, name: str) -> Path:
    parts = validate_name(name)
    path = setup.directory.joinpath(*parts[:-1], f"{parts[-1]}.yaml")
    # Ceinture et bretelles : aucun lien symbolique, rien hors du dossier
    resolved = path.resolve()
    if setup.directory.resolve() not in resolved.parents:
        raise PackageError("invalid_name")
    for parent in (path, *path.parents):
        if parent == setup.directory:
            break
        if parent.is_symlink():
            raise PackageError("symlink")
    return path


def name_of(setup: PackagesSetup, path: Path) -> str:
    return path.relative_to(setup.directory).with_suffix("").as_posix()


def description(text: str) -> str | None:
    """Première ligne de commentaire qui ressemble à une phrase (pas à du code)."""
    for line in text.splitlines()[:40]:
        match = _COMMENT_RE.match(line)
        if match is None:
            if line.strip():
                return None
            continue
        value = match.group(1).strip(" =-#*")
        if value and not re.match(r"^(?:-\s|[a-z0-9_]+:(?:\s|$)|\S*(?:/|\.ya?ml)\S*$)", value):
            return value
    return None


def list_packages(setup: PackagesSetup) -> list[dict]:
    """Packages présents (y compris dans des sous-dossiers), triés par nom."""
    if not setup.directory.is_dir():
        return []
    result = []
    for path in sorted(setup.directory.rglob("*.yaml")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            name = name_of(setup, path)
            validate_name(name)
        except (ValueError, PackageError):
            continue  # nom que Package Keeper ne gère pas : visible dans File Editor
        stat = path.stat()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        result.append(
            {
                "name": name,
                "description": description(text),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            }
        )
    return result


def read_package(setup: PackagesSetup, name: str) -> str:
    """Texte brut du fichier : les « !secret x » restent des références, jamais des valeurs."""
    path = package_path(setup, name)
    if not path.is_file():
        raise PackageError("not_found")
    return path.read_text(encoding="utf-8")


def check_text(text: str) -> bytes:
    if not isinstance(text, str) or not text.strip():
        raise PackageError("empty")
    data = text.replace("\r\n", "\n")
    if not data.endswith("\n"):
        data += "\n"
    encoded = data.encode("utf-8")
    if len(encoded) > MAX_PACKAGE_BYTES:
        raise PackageError("too_large")
    return encoded


# --- Sauvegardes -------------------------------------------------------------


def backup_dir(config_dir: str) -> Path:
    return Path(config_dir) / BACKUP_DIR


def _backup_folder(config_dir: str, name: str) -> Path:
    return backup_dir(config_dir) / name.replace("/", "__")


def backup(config_dir: str, setup: PackagesSetup, name: str, keep: int, reason: str) -> str | None:
    """Copie la version actuelle (si elle existe) ; renvoie l'identifiant de la sauvegarde."""
    path = package_path(setup, name)
    if not path.is_file():
        return None
    folder = _backup_folder(config_dir, name)
    folder.mkdir(parents=True, exist_ok=True)
    # Microsecondes : l'ordre alphabétique reste l'ordre chronologique
    stamp = datetime.now(UTC).strftime(f"{_STAMP_FORMAT}-%f")
    target = folder / f"{stamp}_{reason}.yaml"
    shutil.copy2(path, target)
    _prune(folder, keep)
    return target.name


def _prune(folder: Path, keep: int) -> None:
    files = sorted(folder.glob("*.yaml"), reverse=True)
    for old in files[max(keep, 1) :]:
        old.unlink(missing_ok=True)


def list_backups(config_dir: str, name: str) -> list[dict]:
    validate_name(name)
    folder = _backup_folder(config_dir, name)
    if not folder.is_dir():
        return []
    result = []
    for path in sorted(folder.glob("*.yaml"), reverse=True):
        stamp, _, reason = path.stem.partition("_")
        try:
            when = datetime.strptime(stamp[:15], _STAMP_FORMAT).replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue
        size = path.stat().st_size
        result.append({"id": path.name, "date": when, "reason": reason, "size": size})
    return result


def read_backup(config_dir: str, name: str, backup_id: str) -> str:
    validate_name(name)
    if not re.match(r"^[0-9-]+_[a-z_]+\.yaml$", backup_id or ""):
        raise PackageError("not_found")
    path = _backup_folder(config_dir, name) / backup_id
    if not path.is_file():
        raise PackageError("not_found")
    return path.read_text(encoding="utf-8")


def move_backups(config_dir: str, old: str, new: str) -> list[str]:
    """Déplace l'historique d'un package renommé ; renvoie les fichiers déplacés (0.4.0)."""
    source = _backup_folder(config_dir, old)
    if not source.is_dir():
        return []
    target = _backup_folder(config_dir, new)
    target.mkdir(parents=True, exist_ok=True)
    moved = []
    for path in sorted(source.glob("*.yaml")):
        os.replace(path, target / path.name)
        moved.append(path.name)
    _remove_if_empty(source)
    return moved


def unmove_backups(config_dir: str, old: str, new: str, moved: list[str]) -> None:
    """Annule move_backups (retour arrière d'un renommage)."""
    if not moved:
        return
    source = _backup_folder(config_dir, old)
    target = _backup_folder(config_dir, new)
    source.mkdir(parents=True, exist_ok=True)
    for name in moved:
        if (target / name).is_file():
            os.replace(target / name, source / name)
    _remove_if_empty(target)


def _remove_if_empty(folder: Path) -> None:
    with contextlib.suppress(OSError):  # pas vide (ou déjà absent)
        folder.rmdir()


def remove_empty_dirs(setup: PackagesSetup, name: str) -> None:
    """Après un déplacement, retire les sous-dossiers devenus vides (jamais le dossier racine)."""
    folder = package_path(setup, name).parent
    while folder != setup.directory and setup.directory in folder.parents:
        if folder.is_symlink() or any(folder.iterdir()):
            return
        folder.rmdir()
        folder = folder.parent


def list_deleted(config_dir: str, setup: PackagesSetup) -> list[str]:
    """Packages supprimés (sauvegardes sans fichier actuel), restaurables."""
    root = backup_dir(config_dir)
    if not root.is_dir():
        return []
    names = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        name = folder.name.replace("__", "/")
        try:
            if not package_path(setup, name).exists() and any(folder.glob("*.yaml")):
                names.append(name)
        except PackageError:
            continue
    return names


# --- Écriture ----------------------------------------------------------------


def temp_path(path: Path) -> Path:
    """Fichier temporaire à côté de la cible : ignoré par !include_dir_* (pas en .yaml)."""
    return path.with_name(f".{path.name}.pk-tmp")


def stage(setup: PackagesSetup, name: str, data: bytes) -> Path:
    """Écrit le contenu dans un fichier temporaire, à côté de sa destination."""
    path = package_path(setup, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = temp_path(path)
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return tmp


def commit(setup: PackagesSetup, name: str, tmp: Path) -> None:
    """Remplacement atomique de la destination par le fichier temporaire."""
    os.replace(tmp, package_path(setup, name))


def discard(tmp: Path) -> None:
    tmp.unlink(missing_ok=True)


def restore_bytes(setup: PackagesSetup, name: str, previous: bytes | None) -> None:
    """Remet l'état d'avant : ancien contenu, ou absence du fichier."""
    path = package_path(setup, name)
    if previous is None:
        path.unlink(missing_ok=True)
        return
    tmp = stage(setup, name, previous)
    os.replace(tmp, path)


def current_bytes(setup: PackagesSetup, name: str) -> bytes | None:
    path = package_path(setup, name)
    return path.read_bytes() if path.is_file() else None


def remove(setup: PackagesSetup, name: str) -> None:
    package_path(setup, name).unlink()
