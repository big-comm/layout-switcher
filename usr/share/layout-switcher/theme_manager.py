# SPDX-License-Identifier: MIT
"""
theme_manager.py — Gerenciamento de temas GTK, ícones e Shell.

Aplica temas em tempo real via gsettings sem necessidade de logout.
GTK e ícones propagam imediatamente para todas as janelas abertas.
Shell enables the User Themes extension on demand.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import ast
from pathlib import Path
from typing import List, Tuple

from constants import DBUS_EXT_IFACE, DBUS_EXT_PATH, DBUS_SHELL_NAME
from extension_manager import ExtMgr
from settings_store import Settings
from shell_reloader import ShellReloader
from theme_preview import is_icon_theme
from utils import gsettings_get, gsettings_set, run_cmd

_SHELL_SCHEMA = "org.gnome.shell"
_LIGHT_STYLE_UUID = "light-style@gnome-shell-extensions.gcampax.github.com"
_USER_THEME_UUID = "user-theme@gnome-shell-extensions.gcampax.github.com"
_SHELL_DARK_LAYOUTS = {"BigGnome", "G-Unity", "Minimal"}
_ORCHIS_SHELL_DARK = "Big-Blue"
_ORCHIS_SHELL_LIGHT = "Big-Blue-Light"


class ThemeMgr:
    """
    Gerencia temas GTK, ícones e Shell do GNOME.

    Todos os métodos apply_* propagam mudanças em tempo real
    sem encerrar a sessão.
    """

    SHELL_DEFAULT_THEME_LABEL = "Adwaita (Default)"

    @staticmethod
    def _layout_snapshot_marker() -> Path:
        """Return the marker for the last layout-managed settings snapshot."""
        return (
            Path.home()
            / ".config"
            / "dconf"
            / "settings.gnome.layout-switcher.sha256"
        )

    @staticmethod
    def _invalidate_layout_snapshot() -> None:
        """Mark live settings as user-modified for the next final dconf save."""
        try:
            ThemeMgr._layout_snapshot_marker().unlink(missing_ok=True)
        except OSError:
            # Theme application must not fail only because persistence
            # bookkeeping is temporarily unavailable.
            pass

    # ── Listar temas disponíveis ──────────────────────────────────────────────

    @staticmethod
    def _is_valid_theme(d: Path, kind: str) -> bool:
        """Check if directory d contains a valid theme of given kind."""
        if kind == "gtk":
            return any((d / sub).exists() for sub in ("gtk-4.0", "gtk-3.0", "gtk-2.0"))
        if kind == "icons":
            # ``index.theme`` sozinho aceita tambem temas de cursor (ex.: Bibata),
            # que so trazem ``cursors/``. Exige que o tema tenha pelo menos
            # uma categoria de icone para nao poluir a aba Icones.
            return (d / "index.theme").exists() and is_icon_theme(d.name)
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

        names = sorted(seen.keys(), key=str.lower)
        if kind == "shell":
            names = [n for n in names if n != ThemeMgr.SHELL_DEFAULT_THEME_LABEL]
            return [ThemeMgr.SHELL_DEFAULT_THEME_LABEL] + names
        return names

    # ── Aplicar tema ──────────────────────────────────────────────────────────

    @staticmethod
    def apply(kind: str, name: str) -> Tuple[bool, str]:
        """
        Aplica o tema especificado em tempo real via gsettings.

        Para GTK/ícones: propaga imediatamente para todas as janelas abertas.
        For Shell: enables User Themes when needed and reloads it over D-Bus.

        Retorna (True, "") ou (False, código_erro).
        """
        if kind == "gtk":
            ok, msg = gsettings_set(
                "org.gnome.desktop.interface", "gtk-theme", name
            )
            if ok:
                ThemeMgr._invalidate_layout_snapshot()
            return ok, msg

        if kind == "icons":
            ok, msg = gsettings_set(
                "org.gnome.desktop.interface", "icon-theme", name
            )
            if ok:
                ThemeMgr._invalidate_layout_snapshot()
            return ok, msg

        if kind == "shell":
            uid = "user-theme@gnome-shell-extensions.gcampax.github.com"
            settings_name = "" if name == ThemeMgr.SHELL_DEFAULT_THEME_LABEL else name
            settings_value = "''" if not settings_name else settings_name

            if not settings_name:
                if not ExtMgr.is_installed(uid):
                    return True, ""
                ok, msg = gsettings_set(
                    "org.gnome.shell.extensions.user-theme", "name", settings_value
                )
                if ok and ExtMgr.is_enabled(uid):
                    ThemeMgr._reload_shell_user_theme(uid)
                if ok:
                    ThemeMgr._invalidate_layout_snapshot()
                return ok, msg

            if not ExtMgr.is_installed(uid):
                return False, "user-theme-not-installed"

            ok, msg = gsettings_set(
                "org.gnome.shell.extensions.user-theme", "name", settings_value
            )
            if not ok:
                return False, msg

            if not ExtMgr.is_enabled(uid):
                enabled, enable_msg = ExtMgr.set_enabled(uid, True)
                if not enabled:
                    return False, enable_msg or "user-theme-enable-failed"

            # Reload after enabling so the selected CSS is also applied when
            # User Themes was previously disabled.
            ThemeMgr._reload_shell_user_theme(uid)
            ThemeMgr._invalidate_layout_snapshot()
            return True, ""

        return False, f"unknown theme kind: {kind!r}"

    @staticmethod
    def _reload_shell_user_theme(uid: str) -> None:
        """Reload User Themes so Shell CSS updates without logout."""
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
            active_layout = Settings().get("active_layout")
            shell_dark = dark or active_layout in _SHELL_DARK_LAYOUTS
            ThemeMgr._sync_shell_color_scheme(
                shell_dark,
                native_shell=active_layout in {"Classic", "Hybrid"},
                desk_ux_shell=active_layout in {"Desk UX", "Desk-UX"},
                fixed_shell=active_layout in _SHELL_DARK_LAYOUTS,
            )
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
            ThemeMgr._invalidate_layout_snapshot()
        return ok, msg

    @staticmethod
    def _string_list(value: str | None) -> List[str]:
        if not value:
            return []
        try:
            parsed = ast.literal_eval(value.strip())
        except (ValueError, SyntaxError):
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, str) and item]

    @staticmethod
    def _string_value(value: str | None) -> str:
        if not value:
            return ""
        try:
            parsed = ast.literal_eval(value.strip())
        except (ValueError, SyntaxError):
            return value.strip().strip("'\"")
        return parsed if isinstance(parsed, str) else ""

    @staticmethod
    def _sync_shell_color_scheme(
        dark: bool,
        *,
        native_shell: bool = False,
        desk_ux_shell: bool = False,
        fixed_shell: bool = False,
    ) -> None:
        enabled = ThemeMgr._string_list(gsettings_get(_SHELL_SCHEMA, "enabled-extensions"))
        disabled = ThemeMgr._string_list(gsettings_get(_SHELL_SCHEMA, "disabled-extensions"))
        user_theme_name = ""
        if dark or native_shell or desk_ux_shell:
            user_theme_name = ThemeMgr._string_value(
                gsettings_get("org.gnome.shell.extensions.user-theme", "name")
            )
        user_theme_enabled = (
            _USER_THEME_UUID in enabled and _USER_THEME_UUID not in disabled
        )
        light_style_enabled = (
            _LIGHT_STYLE_UUID in enabled and _LIGHT_STYLE_UUID not in disabled
        )

        # Fixed-shell layouts and explicit user overrides are authoritative.
        # Applying "Original" remains responsible for restoring layout defaults.
        if fixed_shell:
            return
        if native_shell and (user_theme_enabled or user_theme_name):
            return
        if desk_ux_shell and not (
            user_theme_enabled
            and not light_style_enabled
            and user_theme_name in {_ORCHIS_SHELL_DARK, _ORCHIS_SHELL_LIGHT}
        ):
            return

        if desk_ux_shell:
            target = _ORCHIS_SHELL_DARK if dark else _ORCHIS_SHELL_LIGHT
            if user_theme_name != target:
                gsettings_set(
                    "org.gnome.shell.extensions.user-theme",
                    "name",
                    repr(target),
                )
            user_theme_name = target

        def add_once(values: List[str], uuid: str) -> None:
            if uuid not in values:
                values.append(uuid)

        if dark or desk_ux_shell:
            enabled = [uuid for uuid in enabled if uuid != _LIGHT_STYLE_UUID]
            add_once(disabled, _LIGHT_STYLE_UUID)
            if user_theme_name:
                disabled = [uuid for uuid in disabled if uuid != _USER_THEME_UUID]
                add_once(enabled, _USER_THEME_UUID)
            else:
                enabled = [uuid for uuid in enabled if uuid != _USER_THEME_UUID]
                add_once(disabled, _USER_THEME_UUID)
        else:
            enabled = [uuid for uuid in enabled if uuid != _USER_THEME_UUID]
            disabled = [uuid for uuid in disabled if uuid != _LIGHT_STYLE_UUID]
            add_once(enabled, _LIGHT_STYLE_UUID)
            add_once(disabled, _USER_THEME_UUID)

        gsettings_set(_SHELL_SCHEMA, "disabled-extensions", repr(disabled))
        gsettings_set(_SHELL_SCHEMA, "enabled-extensions", repr(enabled))
        ShellReloader.reload_extension(_LIGHT_STYLE_UUID, timeout=5)
        if (dark or desk_ux_shell) and user_theme_name:
            ShellReloader.reload_extension(_USER_THEME_UUID, timeout=5)

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
        value = gsettings_get(schema, key) or ""
        if kind == "shell" and not value:
            return ThemeMgr.SHELL_DEFAULT_THEME_LABEL
        return value

    @staticmethod
    def color_scheme() -> str:
        """Retorna o esquema de cores atual: 'prefer-dark' ou 'prefer-light'."""
        return gsettings_get("org.gnome.desktop.interface", "color-scheme") or "prefer-light"
