# SPDX-License-Identifier: MIT
"""
ui/page_themes.py — Theme page (Shell, applications, icons).

Layout: conteúdo centralizado com Adw.Clamp — não estica em telas largas.
Usa Gtk.ListBox com boxed-list para aparência GNOME nativa e confortável.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

from typing import Dict, List

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, GLib, Gtk, Pango

from constants import tr
from theme_manager import ThemeMgr
from theme_preview import (
    extract_shell_panel_bg,
    extract_theme_color,
    find_theme_icons,
    is_dark_theme_name,
    is_light_theme_name,
)
from ui.widgets import IconStrip, MiniPanelPreview, MiniWindowPreview
from utils import color_from_name, run_cmd

# Wide enough for five compact theme cards at the default window size.
_LIST_MAX_WIDTH = 940


class ThemeRow(Gtk.ListBoxRow):
    """Theme list row with typed theme_name and theme_kind properties."""

    def __init__(self, theme_name: str, theme_kind: str) -> None:
        super().__init__()
        self._theme_name = theme_name
        self._theme_kind = theme_kind

    @property
    def theme_name(self) -> str:
        return self._theme_name

    @property
    def theme_kind(self) -> str:
        return self._theme_kind


class ThemeTile(Gtk.FlowBoxChild):
    """Theme grid tile with typed theme_name and theme_kind properties."""

    def __init__(self, theme_name: str, theme_kind: str) -> None:
        super().__init__()
        self._theme_name = theme_name
        self._theme_kind = theme_kind

    @property
    def theme_name(self) -> str:
        return self._theme_name

    @property
    def theme_kind(self) -> str:
        return self._theme_kind


class ThemesPage(Gtk.Box):
    """
    Página de Temas.
    Sub-tabs: Shell | Applications | Icons
    A lista de temas é limitada por Adw.Clamp para não esticar demais.
    """

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool = pool
        self._toast = toast_cb
        self._theme_kind = "shell"
        self._cached_names: List[str] = []
        self._cached_active: str = ""
        self._build()

    # ── Construção ────────────────────────────────────────────────────────────

    def _build(self) -> None:
        surface = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        surface.add_css_class("theme-surface")
        surface.set_margin_start(14)
        surface.set_margin_end(14)
        surface.set_margin_top(10)
        surface.set_margin_bottom(10)
        surface.set_vexpand(True)

        # ── Sub-abas de tipo ──────────────────────────────────────────────────
        surface.append(self._build_kind_tabs())

        # ── Search / filter ───────────────────────────────────────────────────
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text(tr("Filter themes…"))
        self._search_entry.set_margin_start(26)
        self._search_entry.set_margin_end(26)
        self._search_entry.set_margin_bottom(8)
        self._search_entry.connect("search-changed", self._on_search_changed)
        surface.append(self._search_entry)

        # ── Área de scroll com conteúdo centrado e limitado ───────────────────
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        # Adw.Clamp: centraliza e limita a largura — não estica em telas largas
        self._clamp = Adw.Clamp()
        self._clamp.set_maximum_size(_LIST_MAX_WIDTH)
        self._clamp.set_tightening_threshold(460)

        # Container interno (recriado a cada refresh_themes)
        self._list_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._list_container.set_margin_start(16)
        self._list_container.set_margin_end(16)
        self._list_container.set_margin_top(6)
        self._list_container.set_margin_bottom(24)

        self._clamp.set_child(self._list_container)
        sc.set_child(self._clamp)
        surface.append(sc)
        self.append(surface)

        self.refresh_themes()

    def _build_kind_tabs(self) -> Gtk.Widget:
        """Build Shell / Applications / Icons sub-tabs."""
        kb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        kb.add_css_class("linked")
        kb.set_margin_start(26)
        kb.set_margin_bottom(8)
        self._kind_btns: Dict[str, Gtk.Button] = {}
        for kind, label in [
            ("shell", tr("Shell")),
            ("gtk", tr("Applications")),
            ("icons", tr("Icons")),
        ]:
            btn = Gtk.Button(label=label)
            btn.add_css_class("kind-tab")
            btn.add_css_class("flat")
            is_default = kind == "shell"
            if is_default:
                btn.add_css_class("kind-on")
            btn.connect("clicked", lambda b, k=kind: self._switch_kind(k))
            kb.append(btn)
            self._kind_btns[kind] = btn
        return kb

    # ── Tipo de tema ──────────────────────────────────────────────────────────

    def _switch_kind(self, kind: str) -> None:
        self._theme_kind = kind
        for k, btn in self._kind_btns.items():
            selected = k == kind
            if selected:
                btn.add_css_class("kind-on")
            else:
                btn.remove_css_class("kind-on")
            # a11y: announce selected state to screen readers

        self.refresh_themes()

    # ── Lista de temas ────────────────────────────────────────────────────────

    def refresh_themes(self) -> None:
        """Reconstrói a lista de temas. Scan em thread para não bloquear UI."""
        # Limpa container
        child = self._list_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list_container.remove(child)
            child = nxt

        # Show spinner while scanning
        spinner = Gtk.Spinner(spinning=True)
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.set_valign(Gtk.Align.CENTER)
        spinner.set_margin_top(48)
        spinner.set_size_request(32, 32)
        self._list_container.append(spinner)

        kind = self._theme_kind

        def _scan() -> None:
            active = ThemeMgr.current(kind)
            names = ThemeMgr.list_themes(kind)
            GLib.idle_add(self._populate_themes, kind, active, names)

        self._pool.submit(_scan)

    def _populate_themes(self, kind: str, active: str, names: List[str]) -> None:
        """Popula a lista após o scan em thread."""
        self._cached_names = names
        self._cached_active = active
        self._filter_and_display(kind, active, names)

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        """Filter displayed themes based on search text."""
        query = entry.get_text().strip().lower()
        if query:
            filtered = [n for n in self._cached_names if query in n.lower()]
        else:
            filtered = self._cached_names
        self._filter_and_display(self._theme_kind, self._cached_active, filtered)

    def _filter_and_display(self, kind: str, active: str, names: List[str]) -> None:
        """Render theme list from pre-filtered names."""
        # clear container
        child = self._list_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list_container.remove(child)
            child = nxt

        if not names:
            ph = Adw.StatusPage(
                title=tr("No themes found"),
                description=tr("Install themes to ~/.themes or /usr/share/themes"),
                icon_name="preferences-desktop-theme-symbolic",
            )
            self._list_container.append(ph)
            return

        # Contador discreto
        count_lbl = Gtk.Label(label=tr("{n} themes available").format(n=len(names)))
        count_lbl.add_css_class("caption")
        count_lbl.add_css_class("dim-label")
        count_lbl.set_halign(Gtk.Align.START)
        count_lbl.set_margin_bottom(8)
        self._list_container.append(count_lbl)

        self._list_container.append(self._build_theme_grid(kind, active, names))

    def _build_theme_list(self, kind: str, active: str, names: List[str]) -> Gtk.Widget:
        """Lista boxed-list — usado para a aba Ícones (preview horizontal compacto)."""
        lb = Gtk.ListBox()
        lb.add_css_class("boxed-list")
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.connect(
            "row-activated",
            lambda _box, row: self._apply_theme(row.theme_name, row.theme_kind),
        )
        for name in names:
            lb.append(self._make_theme_row(name, kind, active))
        return lb

    def _build_theme_grid(self, kind: str, active: str, names: List[str]) -> Gtk.Widget:
        """FlowBox em grid — preview grande no topo, nome embaixo. Usado em GTK/Shell."""
        fb = Gtk.FlowBox()
        fb.set_selection_mode(Gtk.SelectionMode.NONE)
        fb.set_max_children_per_line(5)
        fb.set_min_children_per_line(1)
        fb.set_row_spacing(10)
        fb.set_column_spacing(10)
        fb.set_homogeneous(True)
        fb.connect(
            "child-activated",
            lambda _fb, tile: self._apply_theme(tile.theme_name, tile.theme_kind),
        )
        for name in names:
            fb.append(self._make_theme_tile(name, kind, active))
        return fb

    def _make_theme_row(self, name: str, kind: str, active: str) -> ThemeRow:
        """
        Linha de tema como ThemeRow.
        Altura compacta e fixa; dot de cor + nome + check quando ativo.
        """
        is_on = name == active

        row = ThemeRow(theme_name=name, theme_kind=kind)
        row.set_activatable(True)

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        inner.set_margin_start(14)
        inner.set_margin_end(14)
        inner.set_margin_top(10)
        inner.set_margin_bottom(10)

        # Preview: icon real para icons; cor extraida do CSS para gtk/shell
        preview = self._build_preview(name, kind)
        preview.set_valign(Gtk.Align.CENTER)
        inner.append(preview)

        # Nome
        lbl = Gtk.Label(label=name)
        lbl.add_css_class("body")
        if is_on:
            lbl.add_css_class("theme-name-active")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        inner.append(lbl)

        # Check de ativo / placeholder para manter alinhamento
        if is_on:
            chk = Gtk.Image.new_from_icon_name("object-select-symbolic")
            chk.set_pixel_size(16)
            chk.add_css_class("accent")
            inner.append(chk)
        else:
            sp = Gtk.Box()
            sp.set_size_request(16, 1)
            inner.append(sp)

        row.set_child(inner)

        a11y_label = tr("{name} theme").format(name=name)
        if is_on:
            a11y_label += " (" + tr("Active") + ")"
        row.update_property([Gtk.AccessibleProperty.LABEL], [a11y_label])
        return row

    def _make_theme_tile(self, name: str, kind: str, active: str) -> ThemeTile:
        """
        Tile de grid: preview grande no topo + nome embaixo (com check
        quando ativo). Usado para a visualizacao em grade dos temas GTK
        e Shell — preview pequeno de uma bolinha nao dava ideia do tema,
        agora cada tile mostra um mockup maior.
        """
        is_on = name == active

        tile = ThemeTile(theme_name=name, theme_kind=kind)
        tile.add_css_class("theme-tile")
        tile.set_size_request(142, -1)
        if is_on:
            tile.add_css_class("theme-tile-active")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.set_margin_start(7)
        box.set_margin_end(7)
        box.set_margin_top(7)
        box.set_margin_bottom(7)

        preview = self._build_preview_large(name, kind)
        preview.set_halign(Gtk.Align.CENTER)
        preview_overlay = Gtk.Overlay()
        preview_overlay.set_child(preview)

        if is_on:
            chk = Gtk.Image.new_from_icon_name("object-select-symbolic")
            chk.set_pixel_size(13)
            chk.add_css_class("theme-active-check")
            chk.set_halign(Gtk.Align.END)
            chk.set_valign(Gtk.Align.START)
            chk.set_margin_top(3)
            chk.set_margin_end(3)
            preview_overlay.add_overlay(chk)

        box.append(preview_overlay)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name_row.set_margin_start(2)
        name_row.set_margin_end(2)
        name_row.set_margin_top(2)

        lbl = Gtk.Label(label=name)
        lbl.add_css_class("body")
        if is_on:
            lbl.add_css_class("theme-name-active")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_xalign(0)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_row.append(lbl)

        box.append(name_row)
        tile.set_child(box)

        a11y_label = tr("{name} theme").format(name=name)
        if is_on:
            a11y_label += " (" + tr("Active") + ")"
        tile.update_property([Gtk.AccessibleProperty.LABEL], [a11y_label])
        return tile

    def _build_preview_large(self, name: str, kind: str) -> Gtk.Widget:
        """Versao grande do mockup — usada nos tiles de grid (GTK/Shell)."""
        if kind == "icons":
            frame = Gtk.Box()
            frame.add_css_class("theme-icon-preview")
            frame.set_size_request(128, 68)
            strip = IconStrip(find_theme_icons(name), slot_size=22)
            strip.set_halign(Gtk.Align.CENTER)
            strip.set_valign(Gtk.Align.CENTER)
            frame.append(strip)
            return frame

        accent = extract_theme_color(name, kind) or color_from_name(name)
        if kind == "gtk":
            return MiniWindowPreview(accent, dark=is_dark_theme_name(name), width=128, height=68)
        panel_bg = extract_shell_panel_bg(name)
        return MiniPanelPreview(
            panel_bg,
            accent,
            width=128,
            height=68,
            light=is_light_theme_name(name),
        )

    def _build_preview(self, name: str, kind: str) -> Gtk.Widget:
        """
        Constroi o widget de preview da linha de tema.

        * ``kind=icons`` → ``IconStrip`` com 5 icones reais do tema
          (folder, home, mime de texto, navegador, settings). Slots
          ausentes caem para symbolic do sistema com opacidade reduzida.
        * ``kind=gtk`` → ``MiniWindowPreview`` (mini janela com header
          bar + corpo + botao accent). Light/dark vem de heuristica do
          nome do tema; accent vem do CSS quando possivel.
        * ``kind=shell`` → ``MiniPanelPreview`` (mockup do panel +
          janela ativa). Panel bg extraido de ``#panel`` no
          gnome-shell.css; accent extraido do CSS.
        """
        if kind == "icons":
            icon_paths = find_theme_icons(name)
            return IconStrip(icon_paths, slot_size=18)

        accent = extract_theme_color(name, kind) or color_from_name(name)
        if kind == "gtk":
            return MiniWindowPreview(accent, dark=is_dark_theme_name(name))

        # kind == "shell"
        panel_bg = extract_shell_panel_bg(name)
        return MiniPanelPreview(panel_bg, accent, light=is_light_theme_name(name))

    def _apply_theme(self, name: str, kind: str) -> None:
        def task():
            ok, err = ThemeMgr.apply(kind, name)
            if ok:
                GLib.idle_add(self._toast, name)
                GLib.idle_add(self.refresh_themes)
            elif err == "user-theme-not-installed":
                GLib.idle_add(self._show_user_theme_dialog)
            else:
                GLib.idle_add(self._toast, tr("Error") + f": {err}")

        self._pool.submit(task)

    def _show_user_theme_dialog(self) -> None:
        parent = self.get_root()
        d = Adw.AlertDialog(
            heading=tr("User Themes required"),
            body=tr("Install the User Themes extension to apply shell themes."),
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("install", tr("Open Extensions Page"))
        d.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)

        def on_r(_dlg, r):
            if r == "install":
                run_cmd(
                    [
                        "xdg-open",
                        "https://extensions.gnome.org/extension/19/user-themes/",
                    ]
                )

        d.connect("response", on_r)
        d.present(parent)
