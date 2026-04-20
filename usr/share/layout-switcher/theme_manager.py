# SPDX-License-Identifier: MIT
"""
theme_manager.py — Gerenciamento de temas GTK, ícones e Shell.

Aplica temas em tempo real via gsettings sem necessidade de logout.
GTK e ícones propagam imediatamente para todas as janelas abertas.
Shell requer a extensão User Themes habilitada.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

from pathlib import Path
from typing import List, Tuple

from constants import DBUS_EXT_IFACE, DBUS_EXT_PATH, DBUS_SHELL_NAME
from extension_manager import ExtMgr
from utils import gsettings_get, gsettings_set, run_cmd


class ThemeMgr:
    """
    Gerencia temas GTK, ícones e Shell do GNOME.

    Todos os métodos apply_* propagam mudanças em tempo real
    sem encerrar a sessão.
    """

    # ── Listar temas disponíveis ──────────────────────────────────────────────

    @staticmethod
    def _is_valid_theme(d: Path, kind: str) -> bool:
        """Check if directory d contains a valid theme of given kind."""
        if kind == "gtk":
            return any((d / sub).exists() for sub in ("gtk-4.0", "gtk-3.0", "gtk-2.0"))
        if kind == "icons":
            return (d / "index.theme").exists()
        if kind == "shell":
            sd = d / "gnome-shell"
            return sd.is_dir() and any(
                (sd / f).exists() for f in ("gnome-shell.css", "gnome-shell.gresource")
            )
        return False

    @staticmethod
    def _theme_roots(kind: str) -> List[Path]:
        """Return search directories for theme kind."""
        if kind in ("gtk", "shell"):
            return [
                Path.home() / ".themes",
                Path("/usr/local/share/themes"),
                Path("/usr/share/themes"),
            ]
        return [
            Path.home() / ".icons",
            Path("/usr/local/share/icons"),
            Path("/usr/share/icons"),
        ]

    @staticmethod
    def list_themes(kind: str) -> List[str]:
        """
        Lista temas instalados do tipo especificado.
        kind: "gtk" | "icons" | "shell"
        """
        seen: dict = {}
        for root in ThemeMgr._theme_roots(kind):
            if not root.is_dir():
                continue
            try:
                entries = list(root.iterdir())
            except PermissionError:
                continue
            for d in entries:
                if not d.is_dir() or d.name.startswith(".") or d.name in seen:
                    continue
                if ThemeMgr._is_valid_theme(d, kind):
                    seen[d.name] = True

        return sorted(seen.keys(), key=str.lower)

    # ── Aplicar tema ──────────────────────────────────────────────────────────

    @staticmethod
    def apply(kind: str, name: str) -> Tuple[bool, str]:
        """
        Aplica o tema especificado em tempo real via gsettings.

        Para GTK/ícones: propaga imediatamente para todas as janelas abertas.
        Para Shell: requer User Themes extension habilitada; recarrega via D-Bus.

        Retorna (True, "") ou (False, código_erro).
        """
        if kind == "gtk":
            return gsettings_set("org.gnome.desktop.interface", "gtk-theme", name)

        if kind == "icons":
            return gsettings_set("org.gnome.desktop.interface", "icon-theme", name)

        if kind == "shell":
            uid = "user-theme@gnome-shell-extensions.gcampax.github.com"
            if not ExtMgr.is_installed(uid):
                return False, "user-theme-not-installed"
            if not ExtMgr.is_enabled(uid):
                return False, "user-theme-not-enabled"

            ok, msg = gsettings_set("org.gnome.shell.extensions.user-theme", "name", name)
            if ok:
                # Recarrega shell theme via D-Bus (sem logout)
                run_cmd(
                    [
                        "gdbus",
                        "call",
                        "--session",
                        "--dest",
                        DBUS_SHELL_NAME,
                        "--object-path",
                        DBUS_EXT_PATH,
                        "--method",
                        f"{DBUS_EXT_IFACE}.ReloadExtension",
                        uid,
                    ],
                    timeout=5,
                )
            return ok, msg

        return False, f"unknown theme kind: {kind!r}"

    # ── Esquema de cores ──────────────────────────────────────────────────────

    @staticmethod
    def set_color_scheme(dark: bool) -> Tuple[bool, str]:
        """
        Define esquema de cores claro/escuro.
        Propaga imediatamente para todas as janelas GTK4/libadwaita abertas
        e notifica o Adw.StyleManager em processo.
        """
        scheme = "prefer-dark" if dark else "prefer-light"
        ok, msg = gsettings_set("org.gnome.desktop.interface", "color-scheme", scheme)
        if ok:
            # Notifica o StyleManager do processo atual
            try:
                import gi

                gi.require_version("Adw", "1")
                from gi.repository import Adw

                mgr = Adw.StyleManager.get_default()
                if dark:
                    mgr.set_color_scheme(Adw.ColorScheme.PREFER_DARK)
                else:
                    mgr.set_color_scheme(Adw.ColorScheme.PREFER_LIGHT)
            except Exception:
                pass
        return ok, msg

    # ── Consultas ─────────────────────────────────────────────────────────────

    @staticmethod
    def current(kind: str) -> str:
        """Retorna o nome do tema atualmente ativo para o tipo informado."""
        key_map = {
            "gtk": ("org.gnome.desktop.interface", "gtk-theme"),
            "icons": ("org.gnome.desktop.interface", "icon-theme"),
            "shell": ("org.gnome.shell.extensions.user-theme", "name"),
        }
        schema, key = key_map.get(kind, ("", ""))
        if not schema:
            return ""
        return gsettings_get(schema, key) or ""

    @staticmethod
    def color_scheme() -> str:
        """Retorna o esquema de cores atual: 'prefer-dark' ou 'prefer-light'."""
        return gsettings_get("org.gnome.desktop.interface", "color-scheme") or "prefer-light"
