"""Constantes de Package Keeper."""

from typing import Final

DOMAIN: Final = "package_keeper"
VERSION: Final = "0.5.2"  # identique à manifest.json et au fichier VERSION

# Panneau latéral
PANEL_URL_PATH: Final = "package-keeper"
PANEL_ELEMENT: Final = "package-keeper-panel"
FRONTEND_URL: Final = "/package_keeper_static"
PANEL_ICON: Final = "mdi:package-variant-closed"

# Fichiers
PACKAGES_DIR_DEFAULT: Final = "packages"
BACKUP_DIR: Final = ".package_keeper/backups"  # relatif à /config
GIT_DIR: Final = ".package_keeper/git"  # dépôt miroir (0.5.0)
MAX_PACKAGE_BYTES: Final = 256 * 1024

# Options
CONF_BACKUPS_KEPT: Final = "backups_kept"
DEFAULT_BACKUPS_KEPT: Final = 10
CONF_NOTIFY_CHANGES: Final = "notify_changes"
DEFAULT_NOTIFY_CHANGES: Final = True

# Synchronisation Git (0.5.0)
CONF_GIT_MODE: Final = "git_mode"
GIT_MODE_OFF: Final = "off"
GIT_MODE_LOCAL: Final = "local"
GIT_MODE_REMOTE: Final = "remote"
CONF_GIT_URL: Final = "git_url"
CONF_GIT_BRANCH: Final = "git_branch"
DEFAULT_GIT_BRANCH: Final = "main"
CONF_GIT_USERNAME: Final = "git_username"
DEFAULT_GIT_USERNAME: Final = "git"
CONF_GIT_TOKEN: Final = "git_token"  # dans entry.data, jamais affiché
# Délai de calme avant de commiter une modification faite hors Package Keeper (0.5.2).
# 30 s minimum, non contournable : voir l'explication dans les traductions (options).
CONF_GIT_DEBOUNCE: Final = "git_debounce"
DEFAULT_GIT_DEBOUNCE: Final = 30
MIN_GIT_DEBOUNCE: Final = 30
MAX_GIT_DEBOUNCE: Final = 3600
