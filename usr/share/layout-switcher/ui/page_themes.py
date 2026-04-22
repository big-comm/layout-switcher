# SPDX-License-Identifier: MIT
"""
ui/page_themes.py — Página de Temas (GTK, ícones, Shell).

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
from theme_preview import extract_theme_color, find_folder_icon
from ui.widgets import ColorDot
from utils import color_from_name, run_cmd

# Largura máxima confortável para a lista de temas
_LIST_MAX_WIDTH = 620


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


class ThemesPage(Gtk.Box):
    """
    Página de Temas.
    Sub-abas: GTK | Ícones | Shell  |  Toggle: Claro / Escuro
    A lista de temas é limitada por Adw.Clamp para não esticar demais.
    """

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool = pool
        self._toast = toast_cb
        self._theme_kind = "gtk"
        self._cached_names: List[str] = []
        self._cached_active: str = ""
        self._build()

    # ── Construção ────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Sub-abas de tipo ──────────────────────────────────────────────────
        self.append(self._build_kind_tabs())

        # ── Search / filter ───────────────────────────────────────────────────
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text(tr("Filter themes…"))
        self._search_entry.set_margin_start(26)
        self._search_entry.set_margin_end(26)
        self._search_entry.set_margin_bottom(8)
        self._search_entry.connect("search-changed", self._on_search_changed)
        self.append(self._search_entry)

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
        self.append(sc)

        self.refresh_themes()

    def _build_kind_tabs(self) -> Gtk.Widget:
        """Sub-abas GTK / Ícones / Shell."""
        kb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        kb.set_margin_start(26)
        kb.set_margin_bottom(8)
        self._kind_btns: Dict[str, Gtk.Button] = {}
        for kind, label in [("gtk", "GTK"), ("icons", tr("Icons")), ("shell", "Shell")]:
            btn = Gtk.Button(label=label)
            btn.add_css_class("kind-tab")
            btn.add_css_class("flat")
            is_default = kind == "gtk"
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
        count_lbl = Gtk.Label(label=f"{len(names)} {tr('themes available')}")
        count_lbl.add_css_class("caption")
        count_lbl.add_css_class("dim-label")
        count_lbl.set_halign(Gtk.Align.START)
        count_lbl.set_margin_bottom(8)
        self._list_container.append(count_lbl)

        # ListBox com estilo "boxed-list" — aparência nativa GNOME,
        # altura fixa por linha, sem esticar horizontalmente
        lb = Gtk.ListBox()
        lb.add_css_class("boxed-list")
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.connect(
            "row-activated",
            lambda _box, row: self._apply_theme(row.theme_name, row.theme_kind),
        )

        for name in names:
            row = self._make_theme_row(name, kind, active)
            lb.append(row)

        self._list_container.append(lb)

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

        a11y_label = f"{name} {tr('theme')}"
        if is_on:
            a11y_label += f" ({tr('Active')})"
        row.update_property([Gtk.AccessibleProperty.LABEL], [a11y_label])
        return row

    def _build_preview(self, name: str, kind: str) -> Gtk.Widget:
        """
        Constroi o widget de preview da linha de tema.

        * ``kind=icons`` → ``Gtk.Picture`` com o icone ``folder`` real do tema.
          Fallback para symbolic se o tema nao tiver folder.
        * ``kind=gtk|shell`` → ``ColorDot`` com a cor real extraida do CSS.
          Fallback para cor derivada do nome quando nao e possivel extrair.
        """
        if kind == "icons":
            folder_path = find_folder_icon(name)
            if folder_path:
                pic = Gtk.Picture.new_for_filename(str(folder_path))
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
                pic.set_size_request(26, 22)
                pic.set_can_shrink(True)
                return pic
            img = Gtk.Image.new_from_icon_name("folder-symbolic")
            img.set_pixel_size(22)
            return img

        # gtk ou shell: ColorDot com cor real do CSS quando possivel
        color = extract_theme_color(name, kind)
        if not color:
            color = color_from_name(name)
        return ColorDot(color, size=22)

    def _apply_theme(self, name: str, kind: str) -> None:
        def task():
            ok, err = ThemeMgr.apply(kind, name)
            if ok:
                GLib.idle_add(self._toast, name)
                GLib.idle_add(self.refresh_themes)
            elif err in ("user-theme-not-installed", "user-theme-not-enabled"):
                GLib.idle_add(self._show_user_theme_dialog)
            else:
                GLib.idle_add(self._toast, tr("Error") + f": {err}")

        self._pool.submit(task)

    def _show_user_theme_dialog(self) -> None:
        parent = self.get_root()
        d = Adw.AlertDialog(
            heading=tr("User Themes required"),
            body=tr("Install and enable the User Themes extension to apply shell themes."),
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
