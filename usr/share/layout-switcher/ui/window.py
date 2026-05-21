# SPDX-License-Identifier: MIT
"""
ui/window.py — Janela principal do aplicativo.

Monta a estrutura de sidebar + stack de páginas.
Gerencia o monitor de GSettings para detectar mudanças externas.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import concurrent.futures
from typing import Callable, Dict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

import update_checker
from constants import APP_VERSION, ICON_NAME, UPDATE_CHECK_INTERVAL, tr
from settings_store import GSettingsMonitor, Settings
from ui.dialog_backups import BackupsDialog
from ui.page_effects import EffectsPage
from ui.page_extensions import ExtensionsPage
from ui.page_fonts import FontsPage
from ui.page_layouts import LayoutsPage
from ui.page_themes import ThemesPage
from ui.styles import APP_CSS


class NavRow(Gtk.ListBoxRow):
    """Sidebar navigation row with a typed page_key property."""

    def __init__(self, page_key: str) -> None:
        super().__init__()
        self._page_key = page_key

    @property
    def page_key(self) -> str:
        return self._page_key


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
        self._prefs = Settings()
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="cls")
        self._monitor = GSettingsMonitor()
        self._timeout_ids: list = []
        self._pages: Dict[str, Gtk.Widget] = {}
        self._page_factories: Dict[str, Callable[[], Gtk.Widget]] = {}
        self._pending_updates: Dict = {}

        self.set_title(tr("Layout Switcher"))
        self.set_default_size(1080, 700)
        self.set_size_request(860, 560)

        # Registra a pasta ./icons/ local como fonte de ícones.
        # Isso garante que layout-switcher.svg apareça na janela About
        # e na barra de tarefas mesmo antes de instalar no sistema.
        self._register_local_icons()

        self._apply_css()
        self._build_window()
        self._setup_monitors()

        self.connect("destroy", self._on_destroy)

    def _register_local_icons(self) -> None:
        """
        Adiciona o diretório ./icons/ (relativo ao pacote) ao tema de ícones
        padrão do GTK. Funciona tanto em desenvolvimento quanto após instalação,
        pois o install.sh já copia o SVG para hicolor/scalable/apps.
        """
        from pathlib import Path

        icons_dir = Path(__file__).parent.parent / "icons"
        if icons_dir.is_dir():
            display = Gdk.Display.get_default()
            if display:
                theme = Gtk.IconTheme.get_for_display(display)
                theme.add_search_path(str(icons_dir))

        # Diretório usr/share/icons/ (contém hicolor/) — necessário
        # em dev para encontrar ícones customizados (como desktop-cube-symbolic)
        share_icons = Path(__file__).parent.parent.parent / "icons"
        if share_icons.is_dir() and share_icons != icons_dir:
            display = Gdk.Display.get_default()
            if display:
                theme = Gtk.IconTheme.get_for_display(display)
                theme.add_search_path(str(share_icons))

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def _on_destroy(self, win) -> None:
        for tid in self._timeout_ids:
            try:
                GLib.source_remove(tid)
            except Exception:
                pass
        self._timeout_ids.clear()
        self._monitor.disconnect_all()
        self._pool.shutdown(wait=False)

    # ── CSS ───────────────────────────────────────────────────────────────────

    def _apply_css(self) -> None:
        prov = Gtk.CssProvider()
        prov.load_from_string(APP_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── Monitor de mudanças externas ─────────────────────────────────────────

    def _setup_monitors(self) -> None:
        """
        Registra watchers para detectar mudanças feitas por outros programas
        e atualizar a UI automaticamente (sem reiniciar o app).
        """
        self._monitor.watch(
            "org.gnome.shell",
            "enabled-extensions",
            lambda: GLib.idle_add(self._on_ext_changed),
        )
        self._monitor.watch(
            "org.gnome.desktop.interface",
            "gtk-theme",
            lambda: GLib.idle_add(self._on_theme_changed),
        )
        self._monitor.watch(
            "org.gnome.desktop.interface",
            "icon-theme",
            lambda: GLib.idle_add(self._on_theme_changed),
        )

    def _on_ext_changed(self) -> None:
        """Atualiza páginas de extensões/efeitos quando estado muda externamente."""
        ext_page = self._pages.get("extensions")
        if ext_page is not None:
            ext_page.refresh_installed()
        effects_page = self._pages.get("effects")
        if effects_page is not None:
            effects_page.rebuild()

    def _on_theme_changed(self) -> None:
        """Refresh theme UI only if the page has already been created."""
        themes_page = self._pages.get("themes")
        if themes_page is not None:
            themes_page.refresh_themes()

    # ── Estrutura da janela ───────────────────────────────────────────────────

    def _build_window(self) -> None:
        # Toast overlay wraps everything
        self._toast_overlay = Adw.ToastOverlay()

        # ── OverlaySplitView ──────────────────────────────────────────────────
        self._split_view = Adw.OverlaySplitView()
        self._split_view.set_min_sidebar_width(260)
        self._split_view.set_max_sidebar_width(320)
        self._split_view.set_sidebar_width_fraction(0.32)

        # ── Sidebar pane ──────────────────────────────────────────────────────
        self._split_view.set_sidebar(self._build_sidebar())

        # ── Content pane ──────────────────────────────────────────────────────
        content_toolbar = Adw.ToolbarView()

        # Content header — shows window buttons at end
        self._content_hdr = Adw.HeaderBar()
        self._content_hdr.set_show_start_title_buttons(False)

        # Sidebar toggle button (visible only when sidebar is collapsed)
        self._sidebar_btn = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")
        self._sidebar_btn.set_tooltip_text(tr("Show Sidebar"))
        self._sidebar_btn.update_property([Gtk.AccessibleProperty.LABEL], [tr("Show Sidebar")])
        self._sidebar_btn.set_visible(False)
        self._sidebar_btn.connect("toggled", self._on_sidebar_toggled)
        self._content_hdr.pack_start(self._sidebar_btn)

        # Title widget — updated on page switch
        self._title_widget = Adw.WindowTitle(title=tr("Layouts"))
        self._content_hdr.set_title_widget(self._title_widget)

        # Menu button (right)
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_tooltip_text(tr("Menu"))
        menu_btn.update_property([Gtk.AccessibleProperty.LABEL], [tr("Main menu")])

        menu = Gio.Menu()
        ext_section = Gio.Menu()
        ext_section.append(tr("Check for updates"), "app.check-updates")
        ext_section.append(tr("Auto-update extensions"), "app.toggle-auto-update")
        menu.append_section(None, ext_section)
        menu.append(tr("Backups…"), "app.backups")
        menu.append(tr("About"), "app.about")
        menu_btn.set_menu_model(menu)
        self._content_hdr.pack_end(menu_btn)

        content_toolbar.add_top_bar(self._content_hdr)

        # ── First-run welcome banner ─────────────────────────────────────────
        if not self._prefs.get("intro_shown"):
            banner = Adw.Banner(
                title=tr("Welcome! Choose a desktop layout below to get started."),
                button_label=tr("Got it"),
            )
            banner.set_revealed(True)

            def on_dismiss(_b):
                banner.set_revealed(False)
                self._prefs.set("intro_shown", True)

            banner.connect("button-clicked", on_dismiss)
            content_toolbar.add_top_bar(banner)

        # Stack with pages
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(130)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)

        self._page_factories = {
            "layouts": lambda: LayoutsPage(self._pool, self._toast),
            "fonts": lambda: FontsPage(self._pool, self._toast),
            "themes": lambda: ThemesPage(self._pool, self._toast),
            "effects": lambda: EffectsPage(self._pool, self._toast),
            "extensions": lambda: ExtensionsPage(self._pool, self._toast),
        }
        self._ensure_page("layouts")

        content_toolbar.set_content(self._stack)

        self._split_view.set_content(content_toolbar)

        self._toast_overlay.set_child(self._split_view)

        # Loading overlay: dimmed backdrop + centered spinner card.
        # Always in widget tree; visibility toggled via CSS class for fade.
        self._loading_overlay = Gtk.Overlay()
        self._loading_overlay.set_child(self._toast_overlay)
        self._build_loading()
        self.set_content(self._loading_overlay)

        # Show/hide sidebar toggle button when split view collapses/expands
        self._split_view.connect("notify::collapsed", self._on_split_collapsed)

        # Register about action
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", lambda a, p: self._show_about())
        self.get_application().add_action(about_action)

        # Register backups action
        backups_action = Gio.SimpleAction.new("backups", None)
        backups_action.connect("activate", lambda a, p: self._show_backups())
        self.get_application().add_action(backups_action)

        # Register check-updates action (manual trigger)
        check_action = Gio.SimpleAction.new("check-updates", None)
        check_action.connect("activate", lambda a, p: self._run_update_check(manual=True))
        self.get_application().add_action(check_action)

        # Register stateful auto-update toggle (matches Settings 'ext_auto_update')
        auto_state = GLib.Variant.new_boolean(bool(self._prefs.get("ext_auto_update", False)))
        auto_action = Gio.SimpleAction.new_stateful("toggle-auto-update", None, auto_state)
        auto_action.connect("activate", self._on_toggle_auto_update)
        self.get_application().add_action(auto_action)

        GLib.idle_add(self._nav.select_row, self._nav_rows["layouts"])

        # Run a non-blocking update check shortly after the window is built.
        self._timeout_ids.append(GLib.timeout_add_seconds(5, self._initial_update_check))
        # And periodically every UPDATE_CHECK_INTERVAL seconds while the app is open.
        self._timeout_ids.append(
            GLib.timeout_add_seconds(UPDATE_CHECK_INTERVAL, self._periodic_update_check)
        )

    def _ensure_page(self, key: str) -> Gtk.Widget:
        """Create stack pages on first use to keep startup fast."""
        page = self._pages.get(key)
        if page is not None:
            return page

        factory = self._page_factories.get(key)
        if factory is None:
            raise KeyError(key)

        page = factory()
        self._pages[key] = page
        self._stack.add_named(page, key)

        if key == "extensions" and self._pending_updates:
            page.set_updates(self._pending_updates)
        return page

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> Gtk.Widget:
        toolbar = Adw.ToolbarView()

        # Sidebar header bar — no end buttons, content header has them
        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(False)

        # Centered app name
        title_lbl = Gtk.Label(label=tr("Layout Switcher"))
        title_lbl.add_css_class("heading")
        hdr.set_title_widget(title_lbl)

        toolbar.add_top_bar(hdr)

        # Scrollable nav content
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        sb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sb.set_margin_start(6)
        sb.set_margin_end(6)
        sb.set_margin_top(6)
        sb.set_margin_bottom(12)

        self._nav = Gtk.ListBox()
        self._nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._nav.add_css_class("navigation-sidebar")
        self._nav.connect("row-selected", self._on_nav_selected)

        self._nav_rows: Dict[str, NavRow] = {}
        nav_items = [
            ("layouts", tr("Layouts"), "view-grid-symbolic"),
            ("fonts", tr("Fonts"), "font-x-generic-symbolic"),
            ("themes", tr("Themes"), "applications-graphics-symbolic"),
            ("effects", tr("Effects"), "view-paged-symbolic"),
            ("extensions", tr("Extensions"), "application-x-addon-symbolic"),
        ]
        for key, label, icon in nav_items:
            row = self._make_nav_row(key, label, icon)
            self._nav.append(row)
            self._nav_rows[key] = row

        sb.append(self._nav)

        scroll.set_child(sb)
        toolbar.set_content(scroll)
        return toolbar

    def _make_nav_row(self, key: str, label: str, icon: str) -> NavRow:
        row = NavRow(page_key=key)
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
        row.update_property([Gtk.AccessibleProperty.LABEL], [label])
        return row

    # ── Sidebar toggle (collapsed) ────────────────────────────────────────────

    def _on_split_collapsed(self, split_view, _pspec) -> None:
        collapsed = split_view.get_collapsed()
        self._sidebar_btn.set_visible(collapsed)
        # Show start title buttons when collapsed (no sidebar header visible)
        self._content_hdr.set_show_start_title_buttons(collapsed)
        if not collapsed:
            self._sidebar_btn.set_active(False)

    def _on_sidebar_toggled(self, btn) -> None:
        self._split_view.set_show_sidebar(btn.get_active())

    def _on_nav_selected(self, lb, row) -> None:
        if row is None:
            return
        key = row.page_key
        for k, r in self._nav_rows.items():
            if k == key:
                r.add_css_class("nav-sel")
            else:
                r.remove_css_class("nav-sel")
        if key == "extensions":
            page = self._ensure_page("extensions")
            GLib.idle_add(page.refresh_installed)
        elif key == "effects":
            page = self._ensure_page("effects")
            GLib.idle_add(page.rebuild)
        else:
            self._ensure_page(key)
        self._stack.set_visible_child_name(key)

        # Update header title
        titles = {
            "layouts": tr("Layouts"),
            "fonts": tr("Fonts"),
            "themes": tr("Themes"),
            "effects": tr("Effects"),
            "extensions": tr("Extensions"),
        }
        self._title_widget.set_title(titles.get(key, ""))

        # Auto-close sidebar overlay on mobile
        if self._split_view.get_collapsed():
            self._split_view.set_show_sidebar(False)
            self._sidebar_btn.set_active(False)

    # ── Backups ───────────────────────────────────────────────────────────────

    def _show_backups(self) -> None:
        dlg = BackupsDialog(
            pool=self._pool,
            toast_cb=self._toast,
            on_restored=self._on_backup_restored,
        )
        dlg.present(self)

    def _on_backup_restored(self) -> None:
        """Após um restore, reconstrói páginas para refletir estado."""
        layouts_page = self._pages.get("layouts")
        if layouts_page is not None:
            layouts_page.rebuild_grid()
        ext_page = self._pages.get("extensions")
        if ext_page is not None:
            ext_page.refresh_installed()
        effects_page = self._pages.get("effects")
        if effects_page is not None:
            effects_page.rebuild()

    # ── About ─────────────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name=tr("Community Layout Switcher"),
            application_icon=ICON_NAME,
            version=APP_VERSION,
            developer_name="Big Community & Ari Novais",
            license_type=Gtk.License.MIT_X11,
            comments=tr("Layouts, effects and themes for your GNOME desktop."),
            website="https://communitybig.org/",
            issue_url="https://github.com/BigCommunity/layout-switcher/issues",
            copyright="© 2022–2026 Big Community & Contributors",
            developers=["Big Community", "Ari Novais"],
        )
        about.present(self)

    # ── Loading overlay ───────────────────────────────────────────────────────

    def _build_loading(self) -> None:
        # Backdrop dims the entire window.
        self._loading_backdrop = Gtk.Box()
        self._loading_backdrop.add_css_class("loading-backdrop")
        self._loading_backdrop.set_can_target(False)
        self._loading_overlay.add_overlay(self._loading_backdrop)

        # Centered card with spinner + label.
        self._loading_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._loading_card.add_css_class("loading-card")
        self._loading_card.set_halign(Gtk.Align.CENTER)
        self._loading_card.set_valign(Gtk.Align.CENTER)
        self._loading_card.set_can_target(False)

        spinner_cls = getattr(Adw, "Spinner", None)
        if spinner_cls is not None:
            spinner = spinner_cls()
        else:
            spinner = Gtk.Spinner()
            spinner.set_spinning(True)
        spinner.set_size_request(56, 56)
        spinner.set_halign(Gtk.Align.CENTER)
        self._loading_card.append(spinner)

        self._loading_label = Gtk.Label(label="")
        self._loading_label.add_css_class("title-4")
        self._loading_label.add_css_class("loading-label")
        self._loading_label.set_halign(Gtk.Align.CENTER)
        self._loading_label.set_justify(Gtk.Justification.CENTER)
        self._loading_label.set_wrap(True)
        self._loading_label.set_max_width_chars(42)
        self._loading_card.append(self._loading_label)

        self._loading_overlay.add_overlay(self._loading_card)

    def show_loading(self, text: str = "") -> None:
        self._loading_label.set_label(text or tr("Applying…"))
        self._loading_backdrop.add_css_class("loading-show")
        self._loading_card.add_css_class("loading-show")
        self._loading_backdrop.set_can_target(True)
        self._loading_card.set_can_target(True)

    def hide_loading(self) -> None:
        self._loading_backdrop.remove_css_class("loading-show")
        self._loading_card.remove_css_class("loading-show")
        self._loading_backdrop.set_can_target(False)
        self._loading_card.set_can_target(False)

    # ── Toast ─────────────────────────────────────────────────────────────────

    def _toast(self, msg: str) -> None:
        t = Adw.Toast.new(msg)
        t.set_timeout(5)
        self._toast_overlay.add_toast(t)

    # ── Verificação de atualizações ───────────────────────────────────────────

    def _initial_update_check(self) -> bool:
        """One-shot disparado 5s após a janela abrir."""
        if update_checker.time_since_last_check(self._prefs) >= UPDATE_CHECK_INTERVAL:
            self._run_update_check(manual=False)
        return False  # GLib.SOURCE_REMOVE

    def _periodic_update_check(self) -> bool:
        """Re-checa periodicamente enquanto a janela estiver aberta."""
        self._run_update_check(manual=False)
        return True  # GLib.SOURCE_CONTINUE

    def _run_update_check(self, manual: bool) -> None:
        """
        Roda a verificação de updates fora da UI thread; aplica auto-update se
        `ext_auto_update` estiver habilitado, do contrário só notifica.
        """

        def task():
            try:
                updates = update_checker.check_all()
            except Exception:
                updates = {}
            update_checker.mark_checked(self._prefs)
            GLib.idle_add(self._on_update_check_done, updates, manual)

        self._pool.submit(task)

    def _on_update_check_done(self, updates: Dict, manual: bool) -> bool:
        self._pending_updates = dict(updates or {})
        ext_page = self._pages.get("extensions")
        if ext_page is not None:
            ext_page.set_updates(self._pending_updates)
        if not updates:
            if manual:
                self._toast(tr("All extensions up to date"))
            return False
        if self._prefs.get("ext_auto_update", False):
            # Aplica em background; o page_extensions já sabe re-renderizar via
            # set_updates({}) quando termina, então delegamos.
            def apply_task():
                values = list(updates.values())
                results = update_checker.apply_all(values)
                ok_count = sum(1 for _, ok, _ in results if ok)
                self._pending_updates = {}
                ext_page = self._pages.get("extensions")
                if ext_page is not None:
                    GLib.idle_add(ext_page.set_updates, {})
                GLib.idle_add(
                    self._toast,
                    tr("Auto-updated {n} extensions").format(n=ok_count),
                )

            self._pool.submit(apply_task)
        else:
            self._toast(tr("{n} update(s) available").format(n=len(updates)))
        return False

    def _on_toggle_auto_update(self, action, _param) -> None:
        new_val = not action.get_state().get_boolean()
        action.set_state(GLib.Variant.new_boolean(new_val))
        self._prefs.set("ext_auto_update", new_val)
        self._toast(tr("Auto-update enabled") if new_val else tr("Auto-update disabled"))
