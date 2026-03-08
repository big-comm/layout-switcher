# SPDX-License-Identifier: MIT
"""
ui/page_layouts.py — Página de Layouts do aplicativo.

Exibe grid de cards de layout; ao clicar aplica via dconf + reload em tempo real.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from backup_manager import BackupManager
from constants import ICONS_DIR, LAYOUTS, tr
from layout_applier import LayoutApplier
from utils import find_file


class LayoutsPage(Gtk.Box):
    """
    Página de Layouts.
    Exibe todos os layouts disponíveis em um FlowBox de cards clicáveis.
    """

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool     = pool
        self._toast    = toast_cb
        self._active_layout: Optional[str] = None

        self._build()

    def _build(self) -> None:
        # ── Cabeçalho ─────────────────────────────────────────────────────────
        hbox = Gtk.Box()
        hbox.set_margin_start(26)
        hbox.set_margin_top(22)
        hbox.set_margin_bottom(4)
        title = Gtk.Label(label=tr("Layouts"))
        title.add_css_class("title-1")
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        hbox.append(title)
        self.append(hbox)

        self._status_lbl = Gtk.Label(label=tr("Click a layout to apply"))
        self._status_lbl.add_css_class("dim-label")
        self._status_lbl.set_halign(Gtk.Align.START)
        self._status_lbl.set_margin_start(26)
        self._status_lbl.set_margin_top(4)
        self._status_lbl.set_margin_bottom(12)
        self.append(self._status_lbl)

        # ── Grid de layouts ───────────────────────────────────────────────────
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        self._flow = Gtk.FlowBox()
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_max_children_per_line(4)
        self._flow.set_min_children_per_line(2)
        self._flow.set_row_spacing(12)
        self._flow.set_column_spacing(12)
        self._flow.set_margin_start(22)
        self._flow.set_margin_end(22)
        self._flow.set_margin_bottom(22)
        self._flow.set_homogeneous(True)

        self.rebuild_grid()
        sc.set_child(self._flow)
        self.append(sc)

    # ── Grid ──────────────────────────────────────────────────────────────────

    def rebuild_grid(self) -> None:
        child = self._flow.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._flow.remove(child)
            child = nxt
        for name, cfg, icon_file, fallback in LAYOUTS:
            card = self._make_card(name, cfg, icon_file, fallback)
            self._flow.append(card)

    def _make_card(self, name, cfg, icon_file, fallback) -> Gtk.Box:
        is_on = name == self._active_layout
        card  = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("layout-card")
        card.add_css_class("card")
        if is_on:
            card.add_css_class("layout-on")
        card.set_size_request(158, 132)

        # Faixa "Ativo"
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        if is_on:
            rb = Gtk.Label(label=tr("Active"))
            rb.add_css_class("layout-ribbon")
            rb.add_css_class("caption")
            rb.set_halign(Gtk.Align.END)
            rb.set_hexpand(True)
            top.append(rb)
        else:
            top.set_size_request(-1, 22)
        card.append(top)

        # Imagem / ícone
        wrap = Gtk.Box()
        wrap.add_css_class("frame")
        wrap.set_margin_start(10)
        wrap.set_margin_end(10)
        wrap.set_margin_bottom(6)
        wrap.set_vexpand(True)
        wrap.set_valign(Gtk.Align.CENTER)
        wrap.set_size_request(-1, 64)
        icon_path = find_file(icon_file, [ICONS_DIR])
        if icon_path:
            pic = Gtk.Picture.new_for_filename(str(icon_path))
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            pic.set_hexpand(True)
            wrap.append(pic)
        else:
            ico = Gtk.Image.new_from_icon_name(fallback)
            ico.set_pixel_size(36)
            ico.set_hexpand(True)
            ico.set_halign(Gtk.Align.CENTER)
            wrap.append(ico)
        card.append(wrap)

        lbl = Gtk.Label(label=name)
        lbl.add_css_class("heading")
        lbl.set_halign(Gtk.Align.CENTER)
        lbl.set_margin_bottom(10)
        card.append(lbl)

        gest = Gtk.GestureClick()
        gest.connect(
            "released",
            lambda g, n, x, y, _n=name, _c=cfg: self._on_click(_n, _c),
        )
        card.add_controller(gest)

        accessible_name = name
        if is_on:
            accessible_name = f"{name} ({tr('Active')})"
        card.update_property(
            [Gtk.AccessibleProperty.LABEL], [accessible_name]
        )
        card.set_focusable(True)
        return card

    # ── Interação ─────────────────────────────────────────────────────────────

    def _on_click(self, name: str, cfg: str) -> None:
        if name == self._active_layout:
            self._toast(tr("This layout is already active"))
            return

        parent = self.get_root()
        d = Adw.AlertDialog(
            heading=name,
            body=tr("Apply this layout?"),
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("apply",  tr("Apply"))
        d.add_response("backup", tr("Backup & Apply"))
        d.set_response_appearance("backup", Adw.ResponseAppearance.SUGGESTED)

        def on_r(dlg, r):
            if r == "cancel":
                return
            if r == "backup":
                ok, info = BackupManager.create()
                self._toast(tr("Backup saved") if ok else tr("Backup failed") + f": {info}")
            self._apply(name, cfg)

        d.connect("response", on_r)
        d.present(parent)

    def _apply(self, name: str, cfg: str) -> None:
        self._set_status(f"{tr('Applying')} {name}…", "dim-label")

        def task():
            path = find_file(cfg, ["layouts"])
            if not path:
                GLib.idle_add(self._done, name, False, tr("Layout file not found"))
                return
            ok, err = LayoutApplier.apply(path)
            GLib.idle_add(self._done, name, ok, err)

        self._pool.submit(task)

    def _done(self, name: str, ok: bool, msg: str) -> None:
        if ok:
            self._active_layout = name
            self._set_status(f"{name} {tr('applied')}", "ok-col")
            self.rebuild_grid()
        else:
            self._set_status(f"{tr('Error')}: {msg}", "err-col")

    def _set_status(self, text: str, css: str) -> None:
        for c in ("ok-col", "err-col", "dim-label"):
            self._status_lbl.remove_css_class(c)
        self._status_lbl.set_label(text)
        self._status_lbl.add_css_class(css)
