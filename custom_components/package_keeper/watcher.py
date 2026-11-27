"""Surveillance du dossier des packages par inotify (0.5.2).

Sert à commiter sans attendre les modifications faites HORS de Package Keeper
(Samba, File Editor, VS Code…). inotify est un mécanisme du noyau Linux : il
voit une écriture quel que soit le programme ou le conteneur qui la fait, tant
que le disque est local (pas un partage réseau monté).

Aucune dépendance : appel direct à la libc par ctypes (glibc comme musl,
l'image officielle de Home Assistant étant basée sur Alpine). Si inotify est
indisponible, l'appelant se rabat sur une relecture périodique.

Un délai de calme regroupe les écritures : un éditeur enregistre souvent en
plusieurs étapes (fichier temporaire, renommage), et l'on peut enregistrer
plusieurs fois de suite. Le rappel part une seule fois, après le délai écoulé
depuis la DERNIÈRE écriture.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import ctypes
import logging
import os
from pathlib import Path
import struct

_LOGGER = logging.getLogger(__name__)

# Constantes de <sys/inotify.h>
IN_MODIFY = 0x00000002
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ONLYDIR = 0x01000000
IN_ISDIR = 0x40000000
IN_NONBLOCK = 0o4000
IN_CLOEXEC = 0o2000000

_MASK = (
    IN_CLOSE_WRITE
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
    | IN_ONLYDIR
)
_EVENT = struct.Struct("iIII")  # wd, mask, cookie, len


class WatchUnavailable(Exception):
    """inotify absent ou refusé (limite de surveillances atteinte…)."""


def _libc() -> ctypes.CDLL:
    libc = ctypes.CDLL(None, use_errno=True)  # symboles du processus : glibc ou musl
    if not hasattr(libc, "inotify_init1"):
        raise WatchUnavailable("inotify_init1")
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    return libc


def list_dirs(root: Path) -> list[Path]:
    """Le dossier et tous ses sous-dossiers (hors liens symboliques). À lancer dans l'executor."""
    if not root.is_dir():
        return []
    return [root, *(p for p in root.rglob("*") if p.is_dir() and not p.is_symlink())]


def relevant(name: str) -> bool:
    """Un fichier de package : .yaml, pas caché (temporaires de Package Keeper et des éditeurs)."""
    return name.endswith(".yaml") and not name.startswith(".")


class PackagesWatcher:
    """Appelle `on_change` après `delay` secondes sans nouvelle écriture dans le dossier."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        delay: float,
        on_change: Callable[[], None],
    ) -> None:
        self._loop = loop
        self._delay = delay
        self._on_change = on_change
        self._fd = -1
        self._libc: ctypes.CDLL | None = None
        self._watches: dict[int, Path] = {}
        self._timer: asyncio.TimerHandle | None = None

    def start(self, folders: list[Path]) -> None:
        """Ouvre inotify et surveille ces dossiers (list_dirs). Lève WatchUnavailable."""
        try:
            self._libc = _libc()
        except OSError as err:
            raise WatchUnavailable(str(err)) from err
        fd = self._libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if fd < 0:
            raise WatchUnavailable(os.strerror(ctypes.get_errno()))
        self._fd = fd
        try:
            for folder in folders:
                self._add(folder)
        except WatchUnavailable:
            self.stop()
            raise
        self._loop.add_reader(self._fd, self._read)

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._fd >= 0:
            self._loop.remove_reader(self._fd)
            os.close(self._fd)
            self._fd = -1
        self._watches.clear()

    @property
    def watched(self) -> int:
        return len(self._watches)

    def _add_tree(self, root: Path) -> None:
        """Nouveau sous-dossier : on liste son contenu hors de la boucle, puis on le surveille."""
        task = self._loop.run_in_executor(None, list_dirs, root)
        task.add_done_callback(self._add_listed)

    def _add_listed(self, task: asyncio.Future) -> None:
        if self._fd < 0 or task.cancelled() or task.exception():
            return
        for folder in task.result():
            try:
                self._add(folder)
            except WatchUnavailable as err:
                _LOGGER.debug("Sous-dossier non surveillé : %s", err)

    def _add(self, folder: Path) -> None:
        assert self._libc is not None
        wd = self._libc.inotify_add_watch(self._fd, os.fsencode(folder), _MASK)
        if wd < 0:
            raise WatchUnavailable(os.strerror(ctypes.get_errno()))
        self._watches[wd] = folder

    def _read(self) -> None:
        try:
            data = os.read(self._fd, 64 * 1024)
        except BlockingIOError:
            return
        except OSError as err:
            _LOGGER.debug("Lecture inotify impossible : %s", err)
            return
        changed = False
        offset = 0
        while offset + _EVENT.size <= len(data):
            wd, mask, _cookie, length = _EVENT.unpack_from(data, offset)
            offset += _EVENT.size
            name = data[offset : offset + length].rstrip(b"\0").decode(errors="replace")
            offset += length
            if mask & IN_Q_OVERFLOW:
                changed = True  # événements perdus : on relit tout, par prudence
                continue
            if mask & IN_IGNORED:
                self._watches.pop(wd, None)  # dossier supprimé ou déplacé
                continue
            folder = self._watches.get(wd)
            if mask & IN_ISDIR:
                if mask & (IN_CREATE | IN_MOVED_TO) and folder is not None:
                    self._add_tree(folder / name)
                    changed = True
                elif mask & (IN_DELETE | IN_MOVED_FROM):
                    changed = True
                continue
            if relevant(name):
                changed = True
        if changed:
            self._arm()

    def _arm(self) -> None:
        """(Re)lance le délai de calme : seule la dernière écriture compte."""
        if self._timer:
            self._timer.cancel()
        self._timer = self._loop.call_later(self._delay, self._fire)

    def _fire(self) -> None:
        self._timer = None
        self._on_change()
