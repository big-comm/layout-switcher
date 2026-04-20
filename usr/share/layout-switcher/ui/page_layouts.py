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
from gi.repository import Adw, Gdk, GLib, Gtk

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
        self._pool = pool
        self._toast = toast_cb
        self._active_layout: Optional[str] = None

        self._build()

    def _build(self) -> None:
        self._status_lbl = Gtk.Label(label=tr("Click a layout to apply"))
        self._status_lbl.add_css_class("dim-label")
        self._status_lbl.set_halign(Gtk.Align.START)
        self._status_lbl.set_margin_start(26)
        self._status_lbl.set_margin_top(4)
        self._status_lbl.set_margin_bottom(12)
        # a11y: announce status changes to screen readers
        self._status_lbl.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [tr("Layout status")],
        )
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
        for name, cfg, icon_file, fallback, desc in LAYOUTS:
            card = self._make_card(name, cfg, icon_file, fallback, desc)
            self._flow.append(card)

    def _make_card(self, name, cfg, icon_file, fallback, desc) -> Gtk.Box:
        is_on = name == self._active_layout
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("layout-card")
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
        card.append(lbl)

        if desc:
            dl = Gtk.Label(label=desc)
            dl.add_css_class("caption")
            dl.add_css_class("dim-label")
            dl.set_halign(Gtk.Align.CENTER)
            dl.set_wrap(True)
            dl.set_max_width_chars(22)
            card.append(dl)
            card.set_tooltip_text(desc)

        lbl.set_margin_bottom(4 if desc else 10)
        if desc:
            dl.set_margin_bottom(10)

        gest = Gtk.GestureClick()
        gest.connect(
            "released",
            lambda _g, _n, _x, _y, __n=name, __c=cfg: self._on_click(__n, __c),
        )
        card.add_controller(gest)

        # keyboard activate: Enter / Space
        key_ctl = Gtk.EventControllerKey()
        key_ctl.connect(
            "key-pressed",
            lambda _ctl, kv, _kc, _mod, __n=name, __c=cfg: (
                (self._on_click(__n, __c) or True)
                if kv in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space)
                else False
            ),
        )
        card.add_controller(key_ctl)

        accessible_name = name
        if is_on:
            accessible_name = f"{name} ({tr('Active')})"
        card.update_property([Gtk.AccessibleProperty.LABEL], [accessible_name])
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
        d.add_response("apply", tr("Apply"))
        d.add_response("backup", tr("Backup & Apply"))
        d.set_response_appearance("backup", Adw.ResponseAppearance.SUGGESTED)

        def on_r(_dlg, r):
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
            prev = self._active_layout
            self._active_layout = name
            self._set_status(f"{name} {tr('applied')}", "ok-col")
            self.rebuild_grid()
            # undo toast → restore latest backup
            latest = BackupManager.latest()
            if latest:
                t = Adw.Toast(title=f"{name} {tr('applied')}", timeout=15)
                t.set_button_label(tr("Undo"))
                t.connect(
                    "button-clicked",
                    lambda _t: self._undo_layout(prev, latest),
                )
                root = self.get_root()
                overlay = getattr(root, "_toast_overlay", None)
                if overlay:
                    overlay.add_toast(t)
            else:
                self._toast(f"{name} {tr('applied')}")
        else:
            self._set_status(f"{tr('Error')}: {msg}", "err-col")

    def _undo_layout(self, prev_name, backup_path) -> None:
        """Restore previous layout from backup."""

        def task():
            ok, info = BackupManager.restore(backup_path)
            if ok:
                GLib.idle_add(self._done_undo, prev_name)
            else:
                GLib.idle_add(
                    self._set_status,
                    f"{tr('Error')}: {info}",
                    "err-col",
                )

        self._pool.submit(task)

    def _done_undo(self, prev_name) -> None:
        self._active_layout = prev_name
        self._set_status(tr("Layout restored"), "ok-col")
        self.rebuild_grid()
        self._toast(tr("Previous layout restored"))

    def _set_status(self, text: str, css: str) -> None:
        for c in ("ok-col", "err-col", "dim-label"):
            self._status_lbl.remove_css_class(c)
        # text prefix → not color-only
        if css == "ok-col":
            text = f"✓ {text}"
        elif css == "err-col":
            text = f"✗ {text}"
        self._status_lbl.add_css_class(css)
        self._status_lbl.set_label(text)
        self._status_lbl.add_css_class(css)
