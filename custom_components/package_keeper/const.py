"""Constantes de Package Keeper."""

from typing import Final

DOMAIN: Final = "package_keeper"
VERSION: Final = "0.1.0"  # identique à manifest.json et au fichier VERSION

# Panneau latéral
PANEL_URL_PATH: Final = "package-keeper"
PANEL_ELEMENT: Final = "package-keeper-panel"
FRONTEND_URL: Final = "/package_keeper_static"
PANEL_ICON: Final = "mdi:package-variant-closed"

# Fichiers
PACKAGES_DIR_DEFAULT: Final = "packages"
BACKUP_DIR: Final = ".package_keeper/backups"  # relatif à /config
MAX_PACKAGE_BYTES: Final = 256 * 1024

# Options
CONF_BACKUPS_KEPT: Final = "backups_kept"
DEFAULT_BACKUPS_KEPT: Final = 10
CONF_NOTIFY_CHANGES: Final = "notify_changes"
DEFAULT_NOTIFY_CHANGES: Final = True
