# SPDX-License-Identifier: MIT
"""
ui/page_fonts.py — Pagina de Fontes.

Secoes:
  * Fontes do sistema    : 4 seletores (Interface, Document, Monospace,
                           Window titles legacy).
  * Aparencia            : Hinting e Antialiasing.
  * Fontes instaladas    : lista rolavel com preview e busca.
  * Instalar mais        : abre fonts.google.com no navegador.
  * Reset                : volta aos defaults do sistema.

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import subprocess
from typing import List, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, GLib, Gtk, Pango

from constants import tr
from utils import gsettings_get, gsettings_set, run_cmd

# Defaults GNOME se nao conseguirmos ler o schema padrao
_FALLBACK_DEFAULTS = {
    "font-name": "Cantarell 11",
    "document-font-name": "Cantarell 11",
    "monospace-font-name": "Source Code Pro 10",
    "titlebar-font": "Cantarell Bold 11",
}


def _list_installed_families() -> List[str]:
    """Lista familias de fontes via fc-list (sem duplicatas, ordenada)."""
    try:
        result = subprocess.run(
            ["fc-list", ":", "family"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        families = set()
        for line in result.stdout.splitlines():
            # fc-list returns "Family1,Family2,..." when a font has aliases
            for part in line.split(","):
                name = part.strip()
                if name:
                    families.add(name)
        return sorted(families, key=str.lower)
    except Exception:
        return []


class FontsPage(Gtk.Box):
    """Pagina de gerenciamento de fontes."""

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool = pool
        self._toast = toast_cb
        self._all_families: List[str] = []
        self._build()

    # ── UI raiz ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(820)
        clamp.set_tightening_threshold(600)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        outer.set_margin_start(22)
        outer.set_margin_end(22)
        outer.set_margin_top(8)
        outer.set_margin_bottom(24)

        outer.append(self._build_system_fonts_group())
        outer.append(self._build_appearance_group())
        outer.append(self._build_installed_group())
        outer.append(self._build_more_fonts_group())
        outer.append(self._build_reset_row())

        clamp.set_child(outer)
        sc.set_child(clamp)
        self.append(sc)

    # ── Grupo: Fontes do sistema ─────────────────────────────────────────────

    def _build_system_fonts_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("System fonts"))
        grp.set_description(tr("Fonts used by the GNOME interface"))

        self._interface_btn = self._make_font_row(
            grp,
            title=tr("Interface"),
            schema="org.gnome.desktop.interface",
            key="font-name",
        )
        self._document_btn = self._make_font_row(
            grp,
            title=tr("Document"),
            schema="org.gnome.desktop.interface",
            key="document-font-name",
        )
        self._monospace_btn = self._make_font_row(
            grp,
            title=tr("Monospace"),
            schema="org.gnome.desktop.interface",
            key="monospace-font-name",
        )
        self._titlebar_btn = self._make_font_row(
            grp,
            title=tr("Window titles (legacy)"),
            schema="org.gnome.desktop.wm.preferences",
            key="titlebar-font",
        )
        return grp

    def _make_font_row(
        self,
        group: Adw.PreferencesGroup,
        title: str,
        schema: str,
        key: str,
    ) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(title)

        current = gsettings_get(schema, key) or ""
        row.set_subtitle(current or tr("(not set)"))

        btn = Gtk.Button(label=tr("Choose…"))
        btn.add_css_class("flat")
        btn.set_valign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda b, _s=schema, _k=key, _r=row: self._pick_font(_s, _k, _r),
        )
        row.add_suffix(btn)
        group.add(row)
        return row

    def _pick_font(self, schema: str, key: str, row: Adw.ActionRow) -> None:
        """Abre FontDialog e grava a selecao em gsettings."""
        dialog = Gtk.FontDialog()
        dialog.set_title(tr("Choose font"))

        current = gsettings_get(schema, key) or ""
        initial_desc = Pango.FontDescription.from_string(current) if current else None

        def on_chosen(_src, result):
            try:
                font_desc = dialog.choose_font_finish(result)
            except GLib.Error:
                return
            if font_desc is None:
                return
            new_font = font_desc.to_string()
            ok, err = gsettings_set(schema, key, new_font)
            if ok:
                row.set_subtitle(new_font)
                self._toast(tr("Font updated"))
            else:
                self._toast(tr("Update failed") + f": {err}")

        parent = self.get_root()
        dialog.choose_font(parent, initial_desc, None, on_chosen)

    # ── Grupo: Aparencia (hinting/antialiasing) ──────────────────────────────

    def _build_appearance_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("Appearance"))
        grp.set_description(tr("How fonts are rendered on screen"))

        self._hinting_row = self._make_combo_row(
            grp,
            title=tr("Hinting"),
            schema="org.gnome.desktop.interface",
            key="font-hinting",
            options=[
                ("none", tr("None")),
                ("slight", tr("Slight")),
                ("medium", tr("Medium")),
                ("full", tr("Full")),
            ],
        )

        self._aa_row = self._make_combo_row(
            grp,
            title=tr("Antialiasing"),
            schema="org.gnome.desktop.interface",
            key="font-antialiasing",
            options=[
                ("none", tr("None")),
                ("grayscale", tr("Grayscale")),
                ("rgba", tr("Subpixel (RGBA)")),
            ],
        )
        return grp

    def _make_combo_row(
        self,
        group: Adw.PreferencesGroup,
        title: str,
        schema: str,
        key: str,
        options: List[Tuple[str, str]],
    ) -> Adw.ComboRow:
        row = Adw.ComboRow()
        row.set_title(title)

        model = Gtk.StringList.new([label for _val, label in options])
        row.set_model(model)

        current_val = (gsettings_get(schema, key) or "").strip("'\"")
        values = [v for v, _l in options]
        try:
            idx = values.index(current_val)
        except ValueError:
            idx = 0
        row.set_selected(idx)

        def on_changed(r, _pspec, _values=values, _schema=schema, _key=key):
            i = r.get_selected()
            if 0 <= i < len(_values):
                ok, err = gsettings_set(_schema, _key, _values[i])
                if not ok:
                    self._toast(tr("Update failed") + f": {err}")

        row.connect("notify::selected", on_changed)
        group.add(row)
        return row

    # ── Grupo: Fontes instaladas ─────────────────────────────────────────────

    def _build_installed_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("Installed fonts"))
        grp.set_description(tr("Browse font families installed on your system"))

        # Barra: busca + botao refresh
        bar_row = Adw.ActionRow()
        bar_row.set_activatable(False)

        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text(tr("Search fonts…"))
        self._search.set_hexpand(True)
        self._search.connect("search-changed", self._on_search_changed)
        bar_row.add_prefix(self._search)

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.add_css_class("flat")
        refresh_btn.set_tooltip_text(tr("Refresh font list"))
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.connect("clicked", lambda _b: self._load_installed_async())
        bar_row.add_suffix(refresh_btn)
        grp.add(bar_row)

        # Container da lista — limitamos altura via ScrolledWindow
        list_holder = Adw.ActionRow()
        list_holder.set_activatable(False)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(260)
        sw.set_max_content_height(420)
        sw.set_hexpand(True)

        self._fonts_list = Gtk.ListBox()
        self._fonts_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._fonts_list.add_css_class("boxed-list")
        sw.set_child(self._fonts_list)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner.set_hexpand(True)
        inner.append(sw)
        list_holder.set_child(inner)
        grp.add(list_holder)

        self._count_lbl = Gtk.Label(label="")
        self._count_lbl.add_css_class("caption")
        self._count_lbl.add_css_class("dim-label")
        self._count_lbl.set_halign(Gtk.Align.END)
        self._count_lbl.set_margin_top(4)
        count_row = Adw.ActionRow()
        count_row.set_activatable(False)
        count_row.add_suffix(self._count_lbl)
        grp.add(count_row)

        self._load_installed_async()
        return grp

    def _load_installed_async(self) -> None:
        """Carrega fontes em background e popula a lista."""
        # Placeholder enquanto carrega
        self._clear_list()
        loading = Gtk.Label(label=tr("Loading fonts…"))
        loading.add_css_class("dim-label")
        loading.set_margin_top(20)
        loading.set_margin_bottom(20)
        ph_row = Gtk.ListBoxRow()
        ph_row.set_activatable(False)
        ph_row.set_child(loading)
        self._fonts_list.append(ph_row)

        def task():
            families = _list_installed_families()
            GLib.idle_add(self._populate_list, families)

        self._pool.submit(task)

    def _populate_list(self, families: List[str]) -> None:
        self._all_families = families
        self._render_filtered(families)

    def _on_search_changed(self, entry) -> None:
        q = entry.get_text().strip().lower()
        if not q:
            self._render_filtered(self._all_families)
            return
        filtered = [f for f in self._all_families if q in f.lower()]
        self._render_filtered(filtered)

    def _render_filtered(self, families: List[str]) -> None:
        self._clear_list()
        if not families:
            empty = Gtk.Label(label=tr("No fonts match your search"))
            empty.add_css_class("dim-label")
            empty.set_margin_top(20)
            empty.set_margin_bottom(20)
            r = Gtk.ListBoxRow()
            r.set_activatable(False)
            r.set_child(empty)
            self._fonts_list.append(r)
            self._count_lbl.set_label("")
            return

        # Limita renderizacao a 200 itens para nao travar UI em sistemas com
        # milhares de fontes; search filtra a lista real toda.
        RENDER_CAP = 200
        for family in families[:RENDER_CAP]:
            self._fonts_list.append(self._make_font_row_preview(family))

        total = len(families)
        shown = min(total, RENDER_CAP)
        if total > RENDER_CAP:
            self._count_lbl.set_label(f"{shown}/{total} " + tr("(refine search to see more)"))
        else:
            self._count_lbl.set_label(f"{total} " + tr("fonts"))

    def _make_font_row_preview(self, family: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.set_margin_start(12)
        inner.set_margin_end(12)
        inner.set_margin_top(8)
        inner.set_margin_bottom(8)

        name_lbl = Gtk.Label(label=family)
        name_lbl.add_css_class("caption")
        name_lbl.add_css_class("dim-label")
        name_lbl.set_halign(Gtk.Align.START)
        inner.append(name_lbl)

        preview = Gtk.Label(label="The quick brown fox jumps over the lazy dog 0123")
        preview.set_halign(Gtk.Align.START)
        preview.set_ellipsize(Pango.EllipsizeMode.END)
        # Aplica a familia via Pango markup/attribute
        attrs = Pango.AttrList()
        desc = Pango.FontDescription.from_string(f"{family} 14")
        attrs.insert(Pango.attr_font_desc_new(desc))
        preview.set_attributes(attrs)
        inner.append(preview)

        row.set_child(inner)
        return row

    def _clear_list(self) -> None:
        child = self._fonts_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._fonts_list.remove(child)
            child = nxt

    # ── Grupo: Instalar mais fontes ──────────────────────────────────────────

    def _build_more_fonts_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("Install more fonts"))

        row = Adw.ActionRow()
        row.set_title(tr("Browse Google Fonts"))
        row.set_subtitle(tr("Opens fonts.google.com in your browser"))
        btn = Gtk.Button.new_from_icon_name("web-browser-symbolic")
        btn.add_css_class("flat")
        btn.set_valign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda _b: run_cmd(["xdg-open", "https://fonts.google.com"], timeout=5),
        )
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        grp.add(row)

        tip = Adw.ActionRow()
        tip.set_title(tr("How to install"))
        tip.set_subtitle(
            tr(
                "Place .ttf/.otf files in ~/.local/share/fonts/ then run "
                "'fc-cache -f -v' and refresh this list."
            )
        )
        grp.add(tip)
        return grp

    # ── Reset ────────────────────────────────────────────────────────────────

    def _build_reset_row(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_halign(Gtk.Align.CENTER)
        btn = Gtk.Button(label=tr("Reset to system defaults"))
        btn.add_css_class("destructive-action")
        btn.connect("clicked", self._on_reset)
        box.append(btn)
        return box

    def _on_reset(self, _btn) -> None:
        parent = self.get_root()
        d = Adw.AlertDialog(
            heading=tr("Reset all font settings?"),
            body=tr(
                "Interface, document, monospace and window-title fonts will "
                "return to system defaults. Hinting and antialiasing reset too."
            ),
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("reset", tr("Reset"))
        d.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_close_response("cancel")

        def on_r(_dlg, r):
            if r != "reset":
                return
            keys = [
                ("org.gnome.desktop.interface", "font-name"),
                ("org.gnome.desktop.interface", "document-font-name"),
                ("org.gnome.desktop.interface", "monospace-font-name"),
                ("org.gnome.desktop.interface", "font-hinting"),
                ("org.gnome.desktop.interface", "font-antialiasing"),
                ("org.gnome.desktop.wm.preferences", "titlebar-font"),
            ]
            for schema, key in keys:
                run_cmd(["gsettings", "reset", schema, key], timeout=5)

            # Refresh subtitles
            self._refresh_current_values()
            self._toast(tr("Fonts reset to defaults"))

        d.connect("response", on_r)
        d.present(parent)

    def _refresh_current_values(self) -> None:
        mapping = [
            (self._interface_btn, "org.gnome.desktop.interface", "font-name"),
            (self._document_btn, "org.gnome.desktop.interface", "document-font-name"),
            (self._monospace_btn, "org.gnome.desktop.interface", "monospace-font-name"),
            (self._titlebar_btn, "org.gnome.desktop.wm.preferences", "titlebar-font"),
        ]
        for row, schema, key in mapping:
            val = gsettings_get(schema, key) or ""
            row.set_subtitle(val or tr("(not set)"))
