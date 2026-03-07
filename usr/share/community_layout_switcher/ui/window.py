# SPDX-License-Identifier: MIT
"""
ui/window.py — Janela principal do aplicativo.

Monta a estrutura de sidebar + stack de páginas.
Gerencia o monitor de GSettings para detectar mudanças externas.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import concurrent.futures
import datetime
from typing import Dict

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk

from ..backup_manager import BackupManager
from ..constants import APP_ID, APP_LICENSE, APP_VERSION, ICON_NAME, tr
from ..extension_manager import ExtMgr
from ..settings_store import GSettingsMonitor, Settings
from ..theme_manager import ThemeMgr
from ..utils import is_wayland
from .page_extensions import ExtensionsPage
from .page_layouts import LayoutsPage
from .page_themes import ThemesPage
from .styles import APP_CSS


class MainWindow(Adw.ApplicationWindow):
    """
    Janela principal do Community Layout Switcher.

    Layout:
      ┌──────────┬─────────────────────────────┐
      │  Sidebar │  Stack (Layouts/Ext/Themes)  │
      └──────────┴─────────────────────────────┘
    """

    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)
        self._prefs   = Settings()
        self._pool    = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="cls"
        )
        self._monitor = GSettingsMonitor()

        self.set_title(tr("Layout Switcher"))
        self.set_default_size(1080, 700)
        self.set_size_request(860, 560)

        # Registra a pasta ./icons/ local como fonte de ícones.
        # Isso garante que comm-layout-switcher.svg apareça na janela About
        # e na barra de tarefas mesmo antes de instalar no sistema.
        self._register_local_icons()

        self._apply_css()
        self._build_window()
        self._setup_monitors()

        self.connect("destroy", self._on_destroy)

        if not self._prefs.get("intro_shown"):
            GLib.idle_add(self._show_intro)

    def _register_local_icons(self) -> None:
        """
        Adiciona o diretório ./icons/ (relativo ao pacote) ao tema de ícones
        padrão do GTK. Funciona tanto em desenvolvimento quanto após instalação,
        pois o install.sh já copia o SVG para hicolor/scalable/apps.
        """
        from pathlib import Path
        icons_dir = Path(__file__).parent.parent.parent / "icons"
        if icons_dir.is_dir():
            display = Gdk.Display.get_default()
            if display:
                theme = Gtk.IconTheme.get_for_display(display)
                theme.add_search_path(str(icons_dir))

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def _on_destroy(self, win) -> None:
        self._monitor.disconnect_all()
        self._pool.shutdown(wait=False)

    # ── CSS ───────────────────────────────────────────────────────────────────

    def _apply_css(self) -> None:
        prov = Gtk.CssProvider()
        prov.load_from_data(APP_CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── Monitor de mudanças externas ─────────────────────────────────────────

    def _setup_monitors(self) -> None:
        """
        Registra watchers para detectar mudanças feitas por outros programas
        e atualizar a UI automaticamente (sem reiniciar o app).
        """
        self._monitor.watch(
            "org.gnome.shell", "enabled-extensions",
            lambda: GLib.idle_add(self._on_ext_changed),
        )
        self._monitor.watch(
            "org.gnome.desktop.interface", "gtk-theme",
            lambda: GLib.idle_add(self._themes_page.refresh_themes),
        )
        self._monitor.watch(
            "org.gnome.desktop.interface", "icon-theme",
            lambda: GLib.idle_add(self._themes_page.refresh_themes),
        )
        self._monitor.watch(
            "org.gnome.desktop.interface", "color-scheme",
            lambda: GLib.idle_add(self._themes_page.update_scheme_from_external),
        )

    def _on_ext_changed(self) -> None:
        """Atualiza abas de extensões quando estado muda externamente."""
        self._ext_page.rebuild_featured()
        self._ext_page.refresh_installed()

    # ── Estrutura da janela ───────────────────────────────────────────────────

    def _build_window(self) -> None:
        toolbar = Adw.ToolbarView()

        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(True)
        title_w = Gtk.Label(label="Layout Switcher")
        title_w.add_css_class("heading")
        hdr.set_title_widget(title_w)

        # Botão restaurar backup (esquerda)
        restore_btn = Gtk.Button(icon_name="edit-undo-symbolic")
        restore_btn.set_tooltip_text(tr("Restore Backup"))
        restore_btn.add_css_class("flat")
        restore_btn.connect("clicked", lambda b: self._do_restore_backup())
        hdr.pack_start(restore_btn)

        # Botão about (direita)
        about_btn = Gtk.Button(icon_name="help-about-symbolic")
        about_btn.set_tooltip_text(tr("About"))
        about_btn.add_css_class("flat")
        about_btn.connect("clicked", lambda b: self._show_about())
        hdr.pack_end(about_btn)

        toolbar.add_top_bar(hdr)

        # ── Corpo: sidebar | stack ────────────────────────────────────────────
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.append(self._build_sidebar())

        self._toast_overlay = Adw.ToastOverlay()
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(130)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)

        # Instancia páginas com referência ao pool e callback de toast
        self._layouts_page  = LayoutsPage(self._pool, self._toast)
        self._ext_page      = ExtensionsPage(self._pool, self._toast)
        self._themes_page   = ThemesPage(self._pool, self._toast)

        self._stack.add_named(self._layouts_page,  "layouts")
        self._stack.add_named(self._ext_page,      "extensions")
        self._stack.add_named(self._themes_page,   "themes")

        self._toast_overlay.set_child(self._stack)
        body.append(self._toast_overlay)

        toolbar.set_content(body)
        self.set_content(toolbar)

        GLib.idle_add(self._nav.select_row, self._nav_rows["layouts"])

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> Gtk.Widget:
        sb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sb.add_css_class("main-sidebar")
        sb.set_vexpand(True)

        # Marca
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.set_margin_start(14)
        brand.set_margin_top(16)
        brand.set_margin_bottom(10)
        bico = Gtk.Image.new_from_icon_name("preferences-desktop-symbolic")
        bico.set_pixel_size(22)
        brand.append(bico)
        blbl = Gtk.Label(label="Layouts")
        blbl.add_css_class("title-4")
        brand.append(blbl)
        sb.append(brand)

        sep = Gtk.Separator()
        sep.set_margin_start(10)
        sep.set_margin_end(10)
        sep.set_margin_bottom(6)
        sb.append(sep)

        self._nav = Gtk.ListBox()
        self._nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._nav.add_css_class("navigation-sidebar")
        self._nav.set_margin_start(5)
        self._nav.set_margin_end(5)
        self._nav.connect("row-selected", self._on_nav_selected)

        self._nav_rows: Dict[str, Gtk.ListBoxRow] = {}
        nav_items = [
            ("layouts",    tr("Layouts"),    "view-grid-symbolic"),
            ("extensions", tr("Extensions"), "application-x-addon-symbolic"),
            ("themes",     tr("Themes"),     "applications-graphics-symbolic"),
        ]
        for key, label, icon in nav_items:
            row = self._make_nav_row(key, label, icon)
            self._nav.append(row)
            self._nav_rows[key] = row

        sb.append(self._nav)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sb.append(spacer)

        # Indicador de sessão
        session_lbl = Gtk.Label(label="Wayland" if is_wayland() else "X11")
        session_lbl.add_css_class("caption")
        session_lbl.add_css_class("dim")
        session_lbl.set_margin_bottom(2)
        sb.append(session_lbl)

        ver_lbl = Gtk.Label(label=f"v{APP_VERSION}  {APP_LICENSE}")
        ver_lbl.add_css_class("caption")
        ver_lbl.add_css_class("dim")
        ver_lbl.set_margin_bottom(10)
        sb.append(ver_lbl)
        return sb

    def _make_nav_row(self, key: str, label: str, icon: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row._page_key = key     # type: ignore[attr-defined]
        row.add_css_class("nav-row")

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        inner.set_margin_start(10)
        inner.set_margin_end(10)
        inner.set_margin_top(9)
        inner.set_margin_bottom(9)

        ico = Gtk.Image.new_from_icon_name(icon)
        ico.set_pixel_size(18)
        inner.append(ico)

        lbl = Gtk.Label(label=label)
        lbl.add_css_class("nav-lbl")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        inner.append(lbl)

        row.set_child(inner)
        return row

    def _on_nav_selected(self, lb, row) -> None:
        if row is None:
            return
        key = row._page_key     # type: ignore[attr-defined]
        for k, r in self._nav_rows.items():
            if k == key:
                r.add_css_class("nav-sel")
            else:
                r.remove_css_class("nav-sel")
        if key == "extensions":
            GLib.idle_add(self._ext_page.refresh_installed)
        self._stack.set_visible_child_name(key)

    # ── Backup restore ────────────────────────────────────────────────────────

    def _do_restore_backup(self) -> None:
        backup = BackupManager.latest()
        if not backup:
            self._toast(tr("No backup found"))
            return

        mtime  = datetime.datetime.fromtimestamp(backup.stat().st_mtime)
        ts_str = mtime.strftime("%Y-%m-%d %H:%M")
        count  = len(BackupManager.list_all())

        d = Adw.MessageDialog(
            transient_for=self,
            heading=tr("Restore backup?"),
            body=f"{ts_str}  ({count} {tr('backup(s) available')})",
        )
        d.add_response("cancel",  tr("Cancel"))
        d.add_response("restore", tr("Restore"))
        d.set_response_appearance("restore", Adw.ResponseAppearance.SUGGESTED)

        def on_r(dlg, r):
            if r == "restore":
                def task():
                    ok, err = BackupManager.restore(backup)
                    msg = tr("Restored") if ok else tr("Restore failed") + f": {err}"
                    GLib.idle_add(self._toast, msg)
                    if ok:
                        GLib.idle_add(self._ext_page.rebuild_featured)
                        GLib.idle_add(self._ext_page.refresh_installed)
                        GLib.idle_add(self._themes_page.refresh_themes)
                        GLib.idle_add(self._layouts_page.rebuild_grid)
                self._pool.submit(task)
            dlg.destroy()

        d.connect("response", on_r)
        d.present()

    # ── About ─────────────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        about = Adw.AboutWindow(
            transient_for=self,
            application_name=tr("Community Layout Switcher"),
            application_icon=APP_ID,
            version=APP_VERSION,
            developer_name="Big Community & Ari Novais",
            license_type=Gtk.License.MIT_X11,
            comments=tr("Layouts, effects and themes for your GNOME desktop."),
            website="https://communitybig.org/",
            issue_url="https://github.com/big-comm/comm-layout-changer/issues",
            copyright="© 2022–2025 Big Community",
            developers=["Big Community", "Ari Novais"],
        )
        about.present()

    # ── Toast ─────────────────────────────────────────────────────────────────

    def _toast(self, msg: str) -> None:
        t = Adw.Toast.new(msg)
        t.set_timeout(3)
        self._toast_overlay.add_toast(t)

    # ── Intro ─────────────────────────────────────────────────────────────────

    def _show_intro(self) -> bool:
        d = Adw.MessageDialog(
            transient_for=self,
            heading=tr("Welcome"),
            body=tr(
                "Click any layout, effect or theme to apply instantly.\n"
                "Changes take effect immediately — no logout required.\n"
                "Backups are created automatically before layout changes."
            ),
        )
        d.add_response("go", tr("Let's go"))
        d.set_response_appearance("go", Adw.ResponseAppearance.SUGGESTED)
        check = Gtk.CheckButton(label=tr("Don't show again"))
        check.set_halign(Gtk.Align.CENTER)
        check.set_margin_top(8)
        d.set_extra_child(check)

        def on_r(dlg, r):
            if check.get_active():
                self._prefs.set("intro_shown", True)
            dlg.destroy()

        d.connect("response", on_r)
        d.present()
        return False
