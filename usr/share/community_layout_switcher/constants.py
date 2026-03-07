# SPDX-License-Identifier: MIT
"""
constants.py — Constantes globais, dados de configuração e setup de i18n.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
`tr = gettext.gettext` is the translation function. Use named throwaway
variables: ok, err, out, val, raw, data, info, etc.
"""

import gettext
from pathlib import Path
from typing import Dict, List, Tuple

# ── i18n ──────────────────────────────────────────────────────────────────────
_LOCALE_DIR = Path(__file__).parent.parent / "locale"
gettext.bindtextdomain("community-layout-switcher", str(_LOCALE_DIR))
gettext.textdomain("community-layout-switcher")
tr = gettext.gettext      # purposely NOT named `_`

# ── Aplicação ─────────────────────────────────────────────────────────────────
APP_ID       = "org.bigappearance.app"
APP_VERSION  = "2.2.0"
APP_LICENSE  = "MIT"
APP_NAME     = "Community Layout Switcher"
ICON_NAME    = "comm-layout-switcher"   # SVG em icons/comm-layout-switcher.svg

# ── Diretórios de dados ───────────────────────────────────────────────────────
# Instalação em /usr/share ou ~/.local/share
_SHARE_DIRS = [
    Path(__file__).parent.parent,                          # desenvolvimento local
    Path.home() / ".local" / "share" / "community-layout-switcher",
    Path("/usr/share/community-layout-switcher"),
    Path("/usr/local/share/community-layout-switcher"),
]

CONFIG_DIR    = Path.home() / ".config" / "big-appearance"
BACKUP_DIR    = CONFIG_DIR / "backups"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

LAYOUTS_DIR = "layouts"
ICONS_DIR   = "icons"

# ── Diretórios de extensões GNOME ─────────────────────────────────────────────
EXT_USER_DIR = Path.home() / ".local" / "share" / "gnome-shell" / "extensions"
EXT_SYS_DIR  = Path("/usr/share/gnome-shell/extensions")

# ── D-Bus ─────────────────────────────────────────────────────────────────────
DBUS_SHELL_NAME = "org.gnome.Shell"
DBUS_SHELL_PATH = "/org/gnome/Shell"
DBUS_EXT_IFACE  = "org.gnome.Shell.Extensions"
DBUS_EVAL_IFACE = "org.gnome.Shell.Eval"   # legacy, ainda funciona GS < 46
DBUS_EXT_PATH   = "/org/gnome/Shell"

# ── Mapa de cores para temas ──────────────────────────────────────────────────
COLOR_MAP: Dict[str, str] = {
    "blue":       "#3584e4",
    "green":      "#26a269",
    "yellow":     "#cd9309",
    "orange":     "#e66100",
    "red":        "#c01c28",
    "purple":     "#9141ac",
    "pink":       "#d16d9e",
    "teal":       "#2190a4",
    "grey":       "#5e5c64",
    "gray":       "#5e5c64",
    "black":      "#241f31",
    "white":      "#f6f5f4",
    "dark":       "#241f31",
    "light":      "#deddda",
    "brown":      "#865e3c",
    "cyan":       "#00b4c8",
    "magenta":    "#c061cb",
    "lime":       "#2ec27e",
    "indigo":     "#1c71d8",
    "nord":       "#5e81ac",
    "dracula":    "#bd93f9",
    "catppuccin": "#cba6f7",
    "gruvbox":    "#d79921",
    "solarized":  "#268bd2",
    "arc":        "#5294e2",
    "materia":    "#2196f3",
    "numix":      "#f05542",
    "pop":        "#48b9c7",
    "yaru":       "#e95420",
    "breeze":     "#3daee9",
    "adwaita":    "#3584e4",
    "gnome":      "#4a86cf",
    "ubuntu":     "#e95420",
    "fedora":     "#3c6eb4",
}

# ── Extensões em destaque ─────────────────────────────────────────────────────
FEATURED_EXTENSIONS: List[Dict] = [
    {
        "name":         "Desktop Cube",
        "description":  "Rotate workspaces on a 3D cube",
        "uuid":         "desktop-cube@schneegans.github.com",
        "ego_id":       4648,
        "pkg":          "gnome-shell-extension-desktop-cube",
        "icon":         "view-3d-symbolic",
        "has_settings": False,
    },
    {
        "name":         "Magic Lamp",
        "description":  "Genie effect when minimizing windows",
        "uuid":         "compiz-alike-magic-lamp-effect@hermes83.github.com",
        "ego_id":       3740,
        "pkg":          "gnome-shell-extension-compiz-alike-magic-lamp-effect",
        "icon":         "view-paged-symbolic",
        "has_settings": False,
    },
    {
        "name":         "Compiz Windows",
        "description":  "Wobbly windows and extra animations",
        "uuid":         "compiz-windows-effect@hermes83.github.com",
        "ego_id":       3210,
        "pkg":          "gnome-shell-extension-compiz-windows-effect",
        "icon":         "window-symbolic",
        "has_settings": False,
    },
    {
        "name":         "Desktop Icons NG",
        "description":  "Files and folders on your desktop",
        "uuid":         "ding@rastersoft.com",
        "ego_id":       2087,
        "pkg":          "gnome-shell-extension-desktop-icons-ng",
        "icon":         "user-desktop-symbolic",
        "has_settings": True,
    },
]

# ── Layouts disponíveis: (nome, arquivo_config, ícone_svg, ícone_fallback) ────
LAYOUTS: List[Tuple[str, str, str, str]] = [
    ("Classic",    "classic.txt",    "classic.svg",    "view-continuous-symbolic"),
    ("Vanilla",    "vanilla.txt",    "vanilla.svg",    "view-grid-symbolic"),
    ("G-Unity",    "g-unity.txt",    "g-unity.svg",    "view-app-grid-symbolic"),
    ("New",        "new.txt",        "new.svg",        "view-paged-symbolic"),
    ("Next GNOME", "next-gnome.txt", "next-gnome.svg", "view-paged-symbolic"),
    ("Modern",     "modern.txt",     "modern.svg",     "view-grid-symbolic"),
]
