# SPDX-License-Identifier: MIT
"""
community_layout_switcher — Pacote principal.

Exporta as classes e funções públicas do projeto.
"""

from .constants import (
    APP_ID,
    APP_LICENSE,
    APP_NAME,
    APP_VERSION,
    FEATURED_EXTENSIONS,
    LAYOUTS,
    tr,
)
from .backup_manager import BackupManager
from .extension_manager import ExtMgr
from .layout_applier import LayoutApplier
from .settings_store import GSettingsMonitor, Settings
from .shell_reloader import ShellReloader
from .theme_manager import ThemeMgr
from .utils import (
    color_from_name,
    dconf_read,
    dconf_write,
    find_file,
    gnome_shell_version,
    gsettings_get,
    gsettings_set,
    is_wayland,
    run_cmd,
)

__all__ = [
    # Meta
    "APP_ID", "APP_LICENSE", "APP_NAME", "APP_VERSION",
    "FEATURED_EXTENSIONS", "LAYOUTS", "tr",
    # Managers
    "BackupManager", "ExtMgr", "LayoutApplier",
    "Settings", "GSettingsMonitor",
    "ShellReloader", "ThemeMgr",
    # Utils
    "color_from_name", "dconf_read", "dconf_write",
    "find_file", "gnome_shell_version",
    "gsettings_get", "gsettings_set",
    "is_wayland", "run_cmd",
]
