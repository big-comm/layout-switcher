# SPDX-License-Identifier: MIT
"""
ui/page_effects.py — Pagina de Efeitos Visuais.

Mostra os cards em EFFECT_EXTENSIONS (Desktop Cube, Magic Lamp,
Compiz Windows) com install/toggle/remove.

A instalacao usa ``ExtMgr.install()`` que prefere ``pacman -S <pkg>``
(mais estavel e seguro em distros controladas) e cai para o EGO se o
pacote nao existir no repo.

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

from pathlib import Path
from typing import Dict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from constants import EFFECT_EXTENSIONS, tr
from extension_manager import ExtMgr
from shell_reloader import ShellReloader
from utils import run_cmd

_PREVIEW_DIR = Path(__file__).resolve().parent.parent / "effects"


class EffectsPage(Gtk.Box):
    """Grid de efeitos visuais destacados."""

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool = pool
        self._toast = toast_cb
        self._cards: Dict[str, Gtk.Box] = {}
        self._build()

    # ── UI raiz ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        intro = Gtk.Label(
            label=tr("Visual effects for your GNOME desktop"),
        )
        intro.add_css_class("dim-label")
        intro.set_halign(Gtk.Align.START)
        intro.set_margin_start(26)
        intro.set_margin_top(4)
        intro.set_margin_bottom(12)
        self.append(intro)

        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        self._flow = Gtk.FlowBox()
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_max_children_per_line(2)
        self._flow.set_min_children_per_line(2)
        self._flow.set_row_spacing(12)
        self._flow.set_column_spacing(12)
        self._flow.set_margin_start(22)
        self._flow.set_margin_end(22)
        self._flow.set_margin_bottom(22)
        self._flow.set_homogeneous(True)

        self.rebuild()
        sc.set_child(self._flow)
        self.append(sc)

    # ── Build cards ──────────────────────────────────────────────────────────

    def rebuild(self) -> None:
        child = self._flow.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._flow.remove(child)
            child = nxt
        self._cards.clear()
        for ext in EFFECT_EXTENSIONS:
            card = self._make_card(ext)
            self._flow.append(card)
            self._cards[ext["uuid"]] = card

    def _make_card(self, ext: Dict) -> Gtk.Box:
        installed = ExtMgr.is_installed(ext["uuid"])
        enabled = ExtMgr.is_enabled(ext["uuid"]) if installed else False

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("ext-card")
        card.add_css_class("card")
        if enabled:
            card.add_css_class("ext-on")
        card.set_size_request(300, -1)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_start(10)
        inner.set_margin_end(10)
        inner.set_margin_top(10)
        inner.set_margin_bottom(10)

        inner.append(self._make_preview(ext))
        inner.append(self._make_header(ext))

        if installed and not ExtMgr.is_user_dir(ext["uuid"]):
            sys_lbl = Gtk.Label(label=tr("System extension"))
            sys_lbl.add_css_class("caption")
            sys_lbl.add_css_class("dim-label")
            sys_lbl.set_halign(Gtk.Align.START)
            sys_lbl.set_margin_bottom(4)
            inner.append(sys_lbl)

        inner.append(Gtk.Separator())

        if installed:
            self._build_installed(inner, ext, card, enabled)
        else:
            self._build_not_installed(inner, ext, card)

        card.append(inner)

        if installed and enabled:
            card_label = tr("{name} (enabled)").format(name=ext["name"])
        elif installed:
            card_label = tr("{name} (disabled)").format(name=ext["name"])
        else:
            card_label = tr("{name} (not installed)").format(name=ext["name"])
        card.update_property([Gtk.AccessibleProperty.LABEL], [card_label])
        return card

    def _make_preview(self, ext: Dict) -> Gtk.Widget:
        filename = f"{ext.get('preview', 'wobbly')}.png"
        preview = Gtk.Picture.new_for_filename(str(_PREVIEW_DIR / filename))
        preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        preview.set_can_shrink(True)
        preview.set_hexpand(True)
        preview.set_size_request(300, 169)
        preview.set_overflow(Gtk.Overflow.HIDDEN)
        preview.add_css_class("effect-preview-image")
        preview.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [tr("{name} effect preview").format(name=ext["name"])],
        )
        preview.set_margin_bottom(2)
        return preview

    def _make_header(self, ext: Dict) -> Gtk.Box:
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        icon_frame = Gtk.CenterBox()
        icon_frame.add_css_class("effect-icon-frame")
        icon_frame.set_size_request(52, 52)
        icon_frame.set_halign(Gtk.Align.CENTER)
        icon_frame.set_valign(Gtk.Align.CENTER)
        ico = Gtk.Image.new_from_icon_name(ext.get("icon", "application-x-addon-symbolic"))
        ico.set_pixel_size(28)
        ico.set_halign(Gtk.Align.CENTER)
        ico.set_valign(Gtk.Align.CENTER)
        icon_frame.set_center_widget(ico)
        hdr.append(icon_frame)

        tc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        tc.set_hexpand(True)
        nl = Gtk.Label(label=ext["name"])
        nl.add_css_class("heading")
        nl.set_halign(Gtk.Align.START)
        tc.append(nl)
        dl = Gtk.Label(label=ext["description"])
        dl.add_css_class("caption")
        dl.add_css_class("dim-label")
        dl.set_halign(Gtk.Align.START)
        dl.set_wrap(True)
        dl.set_max_width_chars(30)
        tc.append(dl)
        author = ext.get("author", "")
        if author:
            al = Gtk.Label(label=tr("by {author}").format(author=author))
            al.add_css_class("caption")
            al.add_css_class("dim-label")
            al.set_halign(Gtk.Align.START)
            al.set_margin_top(2)
            tc.append(al)
        hdr.append(tc)
        return hdr

    def _build_installed(self, inner: Gtk.Box, ext: Dict, card: Gtk.Box, enabled: bool) -> None:
        btm = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        st = Gtk.Label(label=tr("On") if enabled else tr("Off"))
        st.add_css_class("ok-col" if enabled else "dim-label")
        st.set_hexpand(True)
        st.set_halign(Gtk.Align.START)
        btm.append(st)
        sw = Gtk.Switch()
        sw.set_active(enabled)
        sw.set_valign(Gtk.Align.CENTER)
        sw.update_property([Gtk.AccessibleProperty.LABEL], [f"{tr('Toggle')} {ext['name']}"])
        sw.connect(
            "notify::active",
            lambda s, p, _uuid=ext["uuid"], _sw=sw: self._toggle(_uuid, s.get_active(), _sw),
        )
        btm.append(sw)
        inner.append(btm)

        rm = Gtk.Button(label=tr("Remove"))
        rm.add_css_class("flat")
        rm.add_css_class("destructive-action")
        rm.set_halign(Gtk.Align.START)
        rm.update_property([Gtk.AccessibleProperty.LABEL], [f"{tr('Remove')} {ext['name']}"])
        rm.connect(
            "clicked",
            lambda b, _uuid=ext["uuid"], _name=ext["name"]: self._confirm_remove(_uuid, _name),
        )
        inner.append(rm)

        if ext.get("has_settings") and enabled:
            sb_btn = Gtk.Button(label=tr("Settings"))
            sb_btn.add_css_class("flat")
            sb_btn.set_halign(Gtk.Align.START)
            sb_btn.connect(
                "clicked",
                lambda b, _uuid=ext["uuid"]: ExtMgr.open_prefs(_uuid),
            )
            inner.append(sb_btn)

    def _build_not_installed(self, inner: Gtk.Box, ext: Dict, card: Gtk.Box) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nl2 = Gtk.Label(label=tr("Not installed"))
        nl2.add_css_class("dim-label")
        nl2.set_hexpand(True)
        row.append(nl2)
        ib = Gtk.Button(label=tr("Install"))
        ib.add_css_class("suggested-action")
        ib.add_css_class("pill")
        ib.connect(
            "clicked",
            lambda b, e=ext, _card=card: self._confirm_install(e, _card),
        )
        row.append(ib)
        inner.append(row)

        ego_id = ext.get("ego_id", 0)
        if ego_id > 0:
            ego_btn = Gtk.Button()
            ego_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            ego_ico = Gtk.Image.new_from_icon_name("web-browser-symbolic")
            ego_ico.set_pixel_size(14)
            ego_box.append(ego_ico)
            ego_lbl = Gtk.Label(label=tr("View on GNOME Extensions"))
            ego_lbl.add_css_class("caption")
            ego_box.append(ego_lbl)
            ego_btn.set_child(ego_box)
            ego_btn.add_css_class("flat")
            ego_btn.set_halign(Gtk.Align.START)
            ego_btn.set_margin_top(4)
            ego_btn.connect(
                "clicked",
                lambda b, _id=ego_id: run_cmd(
                    ["xdg-open", f"https://extensions.gnome.org/extension/{_id}/"],
                    timeout=5,
                ),
            )
            inner.append(ego_btn)

    # ── Acoes ────────────────────────────────────────────────────────────────

    def _toggle(self, uuid: str, enable: bool, switch: Gtk.Switch) -> None:
        def task():
            ok, err = ShellReloader.apply_extension_state(uuid, enable)
            if ok:
                GLib.idle_add(self.rebuild)
                short = uuid.split("@")[0]
                msg = f"{short} " + (tr("enabled") if enable else tr("disabled"))
                GLib.idle_add(self._toast, msg)
            else:
                GLib.idle_add(switch.set_active, not enable)
                GLib.idle_add(self._toast, tr("Error") + f": {err}")

        self._pool.submit(task)

    def _confirm_install(self, ext: Dict, card: Gtk.Box) -> None:
        parent = self.get_root()
        d = Adw.AlertDialog(
            heading=tr("Install effect?"),
            body=f"{ext['name']}\n{tr('Will try to install automatically.')}",
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("yes", tr("Install"))
        d.set_response_appearance("yes", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("yes")
        d.set_close_response("cancel")

        def on_r(_dlg, r):
            if r != "yes":
                return
            GLib.idle_add(self._show_spinner, card, tr("Installing…"))

            def task():
                ok, method = ExtMgr.install(
                    ext["uuid"],
                    ext.get("ego_id", 0),
                    ext.get("pkg", ""),
                )
                if ok:
                    ExtMgr.enable_after_install(ext["uuid"])
                    GLib.idle_add(self.rebuild)
                    GLib.idle_add(
                        self._toast,
                        tr("{name} installed and enabled. Restart the session to use it.").format(
                            name=ext["name"]
                        ),
                    )
                else:
                    GLib.idle_add(self.rebuild)
                    GLib.idle_add(self._toast, tr("Install failed") + f": {method}")

            self._pool.submit(task)

        d.connect("response", on_r)
        d.present(parent)

    def _confirm_remove(self, uuid: str, name: str) -> None:
        if not ExtMgr.is_user_dir(uuid):
            self._toast(tr("System extension — cannot remove"))
            return
        parent = self.get_root()
        d = Adw.AlertDialog(
            heading=tr("Remove effect?"),
            body=f"{name}\n{tr('This cannot be undone.')}",
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("remove", tr("Remove"))
        d.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        d.set_close_response("cancel")

        def on_r(_dlg, r):
            if r != "remove":
                return

            def task():
                ok, err = ExtMgr.remove(uuid)
                if ok:
                    GLib.idle_add(self.rebuild)
                    GLib.idle_add(self._toast, f"{name} {tr('removed')}")
                else:
                    GLib.idle_add(self._toast, tr("Remove failed") + f": {err}")

            self._pool.submit(task)

        d.connect("response", on_r)
        d.present(parent)

    def _show_spinner(self, card: Gtk.Box, msg: str) -> None:
        child = card.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            card.remove(child)
            child = nxt
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.add_css_class("spinner-row")
        row.set_margin_start(14)
        row.set_margin_end(14)
        row.set_margin_top(18)
        row.set_margin_bottom(18)
        sp = Gtk.Spinner()
        sp.start()
        sp.set_size_request(20, 20)
        row.append(sp)
        lbl = Gtk.Label(label=msg)
        lbl.add_css_class("dim-label")
        row.append(lbl)
        card.append(row)
