# SPDX-License-Identifier: MIT
"""
ui/page_fonts.py - Font preferences and Google Fonts installer.

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

from typing import Dict, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, GLib, Gtk, Pango

import google_fonts
from constants import tr
from utils import gsettings_get, gsettings_set, run_cmd

_SCALE_MIN = 0.75
_SCALE_MAX = 1.50
_SCALE_STEP = 0.05
_GOOGLE_PAGE_SIZE = 10
_GOOGLE_DEFAULT_LIMIT = 100


class FontsPage(Gtk.Box):
    """GNOME font preferences plus user Google Fonts installation."""

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool = pool
        self._toast = toast_cb
        self._font_value_labels: Dict[str, Gtk.Label] = {}
        self._google_buttons: Dict[str, Gtk.Button] = {}
        self._google_catalog: List[google_fonts.FontFamily] = google_fonts.fallback_catalog()
        self._google_catalog_loaded = False
        self._google_catalog_error = ""
        self._google_query = ""
        self._google_page = 1
        self._build()

    # -- UI root -------------------------------------------------------------

    def _build(self) -> None:
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(820)
        clamp.set_tightening_threshold(600)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        outer.set_margin_start(22)
        outer.set_margin_end(22)
        outer.set_margin_top(8)
        outer.set_margin_bottom(24)

        outer.append(self._build_preferred_fonts_group())
        outer.append(self._build_hinting_group())
        outer.append(self._build_smoothing_group())
        outer.append(self._build_size_group())
        outer.append(self._build_google_fonts_group())
        outer.append(self._build_reset_row())

        clamp.set_child(outer)
        sc.set_child(clamp)
        self.append(sc)

    # -- Preferred fonts -----------------------------------------------------

    def _build_preferred_fonts_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("Preferred fonts"))

        self._make_font_row(
            grp,
            title=tr("Interface text"),
            schema="org.gnome.desktop.interface",
            key="font-name",
        )
        self._make_font_row(
            grp,
            title=tr("Document text"),
            schema="org.gnome.desktop.interface",
            key="document-font-name",
        )
        self._make_font_row(
            grp,
            title=tr("Monospace text"),
            schema="org.gnome.desktop.interface",
            key="monospace-font-name",
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
        row.set_activatable(True)

        current = gsettings_get(schema, key) or tr("(not set)")
        value = Gtk.Label(label=current)
        value.add_css_class("dim-label")
        value.set_ellipsize(Pango.EllipsizeMode.END)
        value.set_max_width_chars(34)
        value.set_xalign(1)
        row.add_suffix(value)
        self._font_value_labels[key] = value

        icon = Gtk.Image.new_from_icon_name("go-next-symbolic")
        icon.add_css_class("dim-label")
        row.add_suffix(icon)

        row.connect("activated", lambda _row: self._pick_font(schema, key, value))
        group.add(row)
        return row

    def _pick_font(self, schema: str, key: str, value_label: Gtk.Label) -> None:
        """Open FontDialog and write selection to gsettings."""
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
                value_label.set_label(new_font)
                self._toast(tr("Font updated"))
            else:
                self._toast(tr("Update failed") + f": {err}")

        dialog.choose_font(self.get_root(), initial_desc, None, on_chosen)

    # -- Rendering -----------------------------------------------------------

    def _build_hinting_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("Hinting"))
        current = (gsettings_get("org.gnome.desktop.interface", "font-hinting") or "").strip("'\"")
        self._add_radio_rows(
            grp,
            schema="org.gnome.desktop.interface",
            key="font-hinting",
            current=current or "slight",
            options=[
                ("full", tr("Full")),
                ("medium", tr("Medium")),
                ("slight", tr("Slight")),
                ("none", tr("None")),
            ],
        )
        return grp

    def _build_smoothing_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("Smoothing"))
        current = (
            gsettings_get("org.gnome.desktop.interface", "font-antialiasing") or ""
        ).strip("'\"")
        self._add_radio_rows(
            grp,
            schema="org.gnome.desktop.interface",
            key="font-antialiasing",
            current=current or "grayscale",
            options=[
                ("rgba", tr("Subpixel (for LCD screens)")),
                ("grayscale", tr("Standard (grayscale)")),
                ("none", tr("None")),
            ],
        )
        return grp

    def _add_radio_rows(
        self,
        group: Adw.PreferencesGroup,
        schema: str,
        key: str,
        current: str,
        options: List[Tuple[str, str]],
    ) -> None:
        first_button: Optional[Gtk.CheckButton] = None
        for value, label in options:
            row = Adw.ActionRow()
            row.set_title(label)
            row.set_activatable(True)

            btn = Gtk.CheckButton()
            btn.set_valign(Gtk.Align.CENTER)
            if first_button is None:
                first_button = btn
            else:
                btn.set_group(first_button)
            btn.set_active(value == current)

            def on_toggled(button, val=value) -> None:
                if button.get_active():
                    ok, err = gsettings_set(schema, key, val)
                    if not ok:
                        self._toast(tr("Update failed") + f": {err}")

            btn.connect("toggled", on_toggled)
            row.connect("activated", lambda _row, b=btn: b.set_active(True))
            row.add_prefix(btn)
            row.set_activatable_widget(btn)
            group.add(row)

    # -- Size ----------------------------------------------------------------

    def _build_size_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("Size"))

        row = Adw.ActionRow()
        row.set_title(tr("Scale factor"))

        self._scale_value = Gtk.Label(label=self._format_scale(self._current_scale()))
        self._scale_value.add_css_class("dim-label")
        row.add_suffix(self._scale_value)

        minus = Gtk.Button(icon_name="list-remove-symbolic")
        minus.add_css_class("flat")
        minus.set_tooltip_text(tr("Decrease"))
        minus.set_valign(Gtk.Align.CENTER)
        minus.connect("clicked", lambda _btn: self._change_scale(-_SCALE_STEP))
        row.add_suffix(minus)

        plus = Gtk.Button(icon_name="list-add-symbolic")
        plus.add_css_class("flat")
        plus.set_tooltip_text(tr("Increase"))
        plus.set_valign(Gtk.Align.CENTER)
        plus.connect("clicked", lambda _btn: self._change_scale(_SCALE_STEP))
        row.add_suffix(plus)

        group_label = tr("Scale factor")
        row.update_property([Gtk.AccessibleProperty.LABEL], [group_label])
        grp.add(row)
        return grp

    @staticmethod
    def _format_scale(value: float) -> str:
        return f"{value:.2f}".replace(".", ",")

    @staticmethod
    def _current_scale() -> float:
        raw = (gsettings_get("org.gnome.desktop.interface", "text-scaling-factor") or "1.0").strip(
            "'\""
        )
        try:
            return float(raw)
        except ValueError:
            return 1.0

    def _change_scale(self, delta: float) -> None:
        current = self._current_scale()
        new_value = max(_SCALE_MIN, min(_SCALE_MAX, round(current + delta, 2)))
        ok, err = gsettings_set(
            "org.gnome.desktop.interface",
            "text-scaling-factor",
            f"{new_value:.2f}",
        )
        if ok:
            self._scale_value.set_label(self._format_scale(new_value))
        else:
            self._toast(tr("Update failed") + f": {err}")

    # -- Google Fonts --------------------------------------------------------

    def _build_google_fonts_group(self) -> Adw.PreferencesGroup:
        grp = Adw.PreferencesGroup()
        grp.set_title(tr("Google Fonts"))

        search_row = Adw.ActionRow()
        search_row.set_activatable(False)
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        search_box.set_margin_start(14)
        search_box.set_margin_end(14)
        search_box.set_margin_top(7)
        search_box.set_margin_bottom(7)
        self._google_search = Gtk.SearchEntry()
        self._google_search.set_placeholder_text(tr("Search Google Fonts…"))
        self._google_search.set_hexpand(True)
        self._google_search.set_size_request(-1, 38)
        self._google_search.add_css_class("google-font-search")
        self._google_search.connect("search-changed", self._on_google_search_changed)
        search_box.append(self._google_search)
        search_row.set_child(search_box)
        grp.add(search_row)

        self._google_status_row = Adw.ActionRow()
        self._google_status_row.set_activatable(False)
        self._google_status_row.set_title(tr("Loading Google Fonts…"))
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.add_css_class("flat")
        refresh.set_valign(Gtk.Align.CENTER)
        refresh.set_tooltip_text(tr("Refresh Google Fonts list"))
        refresh.connect("clicked", lambda _btn: self._load_google_catalog_async(force=True))
        self._google_status_row.add_suffix(refresh)
        grp.add(self._google_status_row)

        holder = Adw.ActionRow()
        holder.set_activatable(False)
        self._google_list = Gtk.ListBox()
        self._google_list.add_css_class("boxed-list")
        self._google_list.set_selection_mode(Gtk.SelectionMode.NONE)
        holder.set_child(self._google_list)
        grp.add(holder)

        pager = Adw.ActionRow()
        pager.set_activatable(False)
        pager_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pager_box.set_halign(Gtk.Align.CENTER)
        pager_box.set_margin_top(2)
        pager_box.set_margin_bottom(2)

        self._google_prev = Gtk.Button(icon_name="go-previous-symbolic")
        self._google_prev.add_css_class("flat")
        self._google_prev.set_tooltip_text(tr("Previous page"))
        self._google_prev.connect("clicked", lambda _btn: self._change_google_page(-1))
        pager_box.append(self._google_prev)

        self._google_page_label = Gtk.Label()
        self._google_page_label.add_css_class("caption")
        self._google_page_label.set_width_chars(16)
        self._google_page_label.set_xalign(0.5)
        pager_box.append(self._google_page_label)

        self._google_next = Gtk.Button(icon_name="go-next-symbolic")
        self._google_next.add_css_class("flat")
        self._google_next.set_tooltip_text(tr("Next page"))
        self._google_next.connect("clicked", lambda _btn: self._change_google_page(1))
        pager_box.append(self._google_next)

        pager.set_child(pager_box)
        grp.add(pager)

        self._render_google_fonts()
        self._load_google_catalog_async()
        return grp

    def _on_google_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._google_query = entry.get_text().strip()
        self._google_page = 1
        self._render_google_fonts()

    def _load_google_catalog_async(self, force: bool = False) -> None:
        self._google_status_row.set_title(tr("Loading Google Fonts…"))

        def task() -> None:
            ok, entries, err = google_fonts.load_catalog(force_refresh=force)
            GLib.idle_add(self._on_google_catalog_loaded, ok, entries, err)

        self._pool.submit(task)

    def _on_google_catalog_loaded(
        self,
        ok: bool,
        entries: List[google_fonts.FontFamily],
        err: str,
    ) -> bool:
        self._google_catalog = entries or google_fonts.fallback_catalog()
        self._google_catalog_loaded = ok
        self._google_catalog_error = err
        self._google_page = 1
        self._render_google_fonts()
        return False

    def _change_google_page(self, delta: int) -> None:
        rows = self._filtered_google_fonts()
        pages = max(1, (len(rows) + _GOOGLE_PAGE_SIZE - 1) // _GOOGLE_PAGE_SIZE)
        self._google_page = max(1, min(pages, self._google_page + delta))
        self._render_google_fonts()

    def _filtered_google_fonts(self) -> List[google_fonts.FontFamily]:
        q = self._google_query.lower()
        if q:
            rows = [entry for entry in self._google_catalog if q in entry.family.lower()]
            known = {entry.family.lower() for entry in rows}
            if q not in known:
                rows.insert(0, google_fonts.FontFamily(self._google_query, "custom"))
            return rows
        return self._google_catalog[:_GOOGLE_DEFAULT_LIMIT]

    def _render_google_fonts(self) -> None:
        child = self._google_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._google_list.remove(child)
            child = nxt

        self._google_buttons.clear()
        rows = self._filtered_google_fonts()
        total = len(rows)
        pages = max(1, (total + _GOOGLE_PAGE_SIZE - 1) // _GOOGLE_PAGE_SIZE)
        self._google_page = max(1, min(pages, self._google_page))
        start = (self._google_page - 1) * _GOOGLE_PAGE_SIZE
        shown = rows[start : start + _GOOGLE_PAGE_SIZE]

        if shown:
            for entry in shown:
                self._google_list.append(self._make_google_row(entry.family, entry.category))
        else:
            self._google_list.append(self._make_google_empty_row())

        self._google_prev.set_sensitive(self._google_page > 1)
        self._google_next.set_sensitive(self._google_page < pages)
        self._google_page_label.set_label(
            tr("Page {page} of {pages}").format(page=self._google_page, pages=pages)
        )
        self._update_google_status(total)

    def _update_google_status(self, total: int) -> None:
        if not self._google_catalog_loaded and self._google_catalog_error == "network":
            self._google_status_row.set_title(
                tr("Internet connection is required to load the Google Fonts list.")
            )
            return
        if self._google_query:
            self._google_status_row.set_title(
                tr("{n} fonts found").format(n=total)
            )
            return
        loaded = len(self._google_catalog)
        shown = min(loaded, _GOOGLE_DEFAULT_LIMIT)
        self._google_status_row.set_title(
            tr("Showing top {shown} of {total} Google Fonts").format(
                shown=shown,
                total=loaded,
            )
        )

    def _make_google_empty_row(self) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        label = Gtk.Label(label=tr("No fonts found"))
        label.add_css_class("dim-label")
        label.set_halign(Gtk.Align.CENTER)
        label.set_margin_top(14)
        label.set_margin_bottom(14)
        row.set_child(label)
        return row

    def _make_google_row(self, family: str, category: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        inner.set_margin_start(12)
        inner.set_margin_end(10)
        inner.set_margin_top(8)
        inner.set_margin_bottom(8)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)
        name = Gtk.Label(label=family)
        name.add_css_class("body")
        name.set_halign(Gtk.Align.START)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        text_box.append(name)

        category_label = Gtk.Label(label=self._category_label(category))
        category_label.add_css_class("caption")
        category_label.add_css_class("dim-label")
        category_label.set_halign(Gtk.Align.START)
        text_box.append(category_label)
        inner.append(text_box)

        btn = Gtk.Button()
        btn.set_valign(Gtk.Align.CENTER)
        btn.add_css_class("pill")
        installed = google_fonts.is_installed(family)
        if installed:
            btn.set_label(tr("Installed"))
            btn.set_sensitive(False)
        else:
            btn.set_label(tr("Install"))
            btn.add_css_class("suggested-action")
            btn.connect("clicked", lambda _btn, f=family, b=btn: self._install_google_font(f, b))
        btn.update_property([Gtk.AccessibleProperty.LABEL], [f"{tr('Install')} {family}"])
        self._google_buttons[family] = btn
        inner.append(btn)

        row.set_child(inner)
        return row

    def _category_label(self, category: str) -> str:
        labels = {
            "sans-serif": tr("Sans serif"),
            "serif": tr("Serif"),
            "monospace": tr("Monospace"),
            "display": tr("Display"),
            "handwriting": tr("Handwriting"),
            "custom": tr("Exact Google Fonts family name"),
        }
        return labels.get(category, category)

    def _install_google_font(self, family: str, button: Gtk.Button) -> None:
        button.set_sensitive(False)
        button.set_label(tr("Installing…"))

        def task() -> None:
            ok, info = google_fonts.install_for_user(family)
            GLib.idle_add(self._on_google_font_installed, family, button, ok, info)

        self._pool.submit(task)

    def _on_google_font_installed(
        self,
        family: str,
        button: Gtk.Button,
        ok: bool,
        info: str,
    ) -> bool:
        if ok:
            button.set_label(tr("Installed"))
            button.set_sensitive(False)
            self._toast(tr("{family} installed").format(family=family))
            return False

        button.set_label(tr("Install"))
        button.set_sensitive(True)
        errors = {
            "network": tr("Internet connection is required to install Google Fonts."),
            "not-found": tr("Font not found on Google Fonts."),
            "download-failed": tr("Font download failed."),
            "too-large": tr("The font download is too large."),
            "write-failed": tr("Could not install the font."),
            "empty": tr("Enter a font family name."),
        }
        self._toast(errors.get(info, tr("Font installation failed.")))
        return False

    # -- Reset ---------------------------------------------------------------

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
                "Interface, document and monospace fonts will return to system defaults. "
                "Rendering and scale settings will reset too."
            ),
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("reset", tr("Reset"))
        d.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_close_response("cancel")

        def on_r(_dlg, response):
            if response != "reset":
                return
            keys = [
                ("org.gnome.desktop.interface", "font-name"),
                ("org.gnome.desktop.interface", "document-font-name"),
                ("org.gnome.desktop.interface", "monospace-font-name"),
                ("org.gnome.desktop.interface", "font-hinting"),
                ("org.gnome.desktop.interface", "font-antialiasing"),
                ("org.gnome.desktop.interface", "text-scaling-factor"),
                ("org.gnome.desktop.wm.preferences", "titlebar-font"),
            ]
            for schema, key in keys:
                run_cmd(["gsettings", "reset", schema, key], timeout=5)
            self._refresh_current_values()
            self._toast(tr("Fonts reset to defaults"))

        d.connect("response", on_r)
        d.present(parent)

    def _refresh_current_values(self) -> None:
        mapping = [
            ("font-name", "org.gnome.desktop.interface"),
            ("document-font-name", "org.gnome.desktop.interface"),
            ("monospace-font-name", "org.gnome.desktop.interface"),
        ]
        for key, schema in mapping:
            label = self._font_value_labels.get(key)
            if label is not None:
                label.set_label(gsettings_get(schema, key) or tr("(not set)"))
        self._scale_value.set_label(self._format_scale(self._current_scale()))
