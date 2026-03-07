# SPDX-License-Identifier: MIT
"""
ui/page_extensions.py — Página de Extensões (sub-abas: Destaque e Instaladas).

Sub-aba Destaque: cards das extensões em FEATURED_EXTENSIONS com install/toggle/remove.
Sub-aba Instaladas: lista completa de extensões instaladas no sistema.
Botão global On/Off para desabilitar/habilitar todas as extensões de uma vez.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import shutil
from typing import Dict

import gi
gi.require_version("Gtk",   "4.0")
gi.require_version("Adw",   "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, GLib, Gtk, Pango

from ..constants import FEATURED_EXTENSIONS, tr
from ..extension_manager import ExtMgr
from ..shell_reloader import ShellReloader
from ..utils import run_cmd


class ExtensionsPage(Gtk.Box):
    """
    Página de Extensões com sub-abas Destaque e Instaladas.
    """

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool  = pool
        self._toast = toast_cb
        self._ext_sub = "featured"
        self._build()

    def _build(self) -> None:
        # ── Cabeçalho ─────────────────────────────────────────────────────────
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        hbox.set_margin_start(26)
        hbox.set_margin_end(22)
        hbox.set_margin_top(22)
        hbox.set_margin_bottom(8)

        title = Gtk.Label(label=tr("Extensions"))
        title.add_css_class("page-title")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        hbox.append(title)

        self._global_btn = Gtk.Button()
        self._global_btn.add_css_class("global-btn")
        self._global_btn.set_valign(Gtk.Align.CENTER)
        self._refresh_global_btn()
        self._global_btn.connect("clicked", self._on_global_toggle)
        hbox.append(self._global_btn)
        self.append(hbox)

        # ── Sub-abas ───────────────────────────────────────────────────────────
        tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tab_bar.set_margin_start(26)
        tab_bar.set_margin_bottom(10)

        self._tab_btns: Dict[str, Gtk.Button] = {}
        for key, label in [("featured", tr("Featured")), ("installed", tr("Installed"))]:
            btn = Gtk.Button(label=label)
            btn.add_css_class("sub-tab")
            btn.add_css_class("flat")
            if key == self._ext_sub:
                btn.add_css_class("sub-on")
            btn.connect("clicked", lambda b, k=key: self._switch_sub(k))
            tab_bar.append(btn)
            self._tab_btns[key] = btn
        self.append(tab_bar)

        # ── Stack de conteúdo ─────────────────────────────────────────────────
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(120)
        self._stack.set_vexpand(True)
        self._stack.add_named(self._build_featured_sub(), "featured")
        self._stack.add_named(self._build_installed_sub(), "installed")
        self.append(self._stack)

    def _switch_sub(self, key: str) -> None:
        self._ext_sub = key
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.add_css_class("sub-on")
            else:
                btn.remove_css_class("sub-on")
        if key == "installed":
            GLib.idle_add(self.refresh_installed)
        self._stack.set_visible_child_name(key)

    # ── Sub-aba Destaque ──────────────────────────────────────────────────────

    def _build_featured_sub(self) -> Gtk.Widget:
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        self._feat_flow = Gtk.FlowBox()
        self._feat_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._feat_flow.set_max_children_per_line(3)
        self._feat_flow.set_min_children_per_line(1)
        self._feat_flow.set_row_spacing(12)
        self._feat_flow.set_column_spacing(12)
        self._feat_flow.set_margin_start(22)
        self._feat_flow.set_margin_end(22)
        self._feat_flow.set_margin_bottom(22)
        self._feat_flow.set_homogeneous(True)

        self._feat_cards: Dict[str, Gtk.Box] = {}
        self.rebuild_featured()
        sc.set_child(self._feat_flow)
        return sc

    def rebuild_featured(self) -> None:
        child = self._feat_flow.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._feat_flow.remove(child)
            child = nxt
        self._feat_cards.clear()
        for ext in FEATURED_EXTENSIONS:
            card = self._make_feat_card(ext)
            self._feat_flow.append(card)
            self._feat_cards[ext["uuid"]] = card

    def _make_feat_card(self, ext: Dict) -> Gtk.Box:
        installed = ExtMgr.is_installed(ext["uuid"])
        enabled   = ExtMgr.is_enabled(ext["uuid"]) if installed else False

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("ext-card")
        card.add_css_class("card")
        if enabled:
            card.add_css_class("ext-on")
        card.set_size_request(200, -1)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_start(14)
        inner.set_margin_end(14)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        # Cabeçalho do card: ícone + nome + descrição
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ico = Gtk.Image.new_from_icon_name(ext.get("icon", "application-x-addon-symbolic"))
        ico.set_pixel_size(28)
        hdr.append(ico)

        tc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        tc.set_hexpand(True)
        nl = Gtk.Label(label=ext["name"])
        nl.add_css_class("heading")
        nl.set_halign(Gtk.Align.START)
        tc.append(nl)
        dl = Gtk.Label(label=ext["description"])
        dl.add_css_class("caption")
        dl.add_css_class("dim")
        dl.set_halign(Gtk.Align.START)
        dl.set_wrap(True)
        dl.set_max_width_chars(30)
        tc.append(dl)
        hdr.append(tc)
        inner.append(hdr)
        inner.append(Gtk.Separator())

        if installed:
            # Linha de toggle
            btm = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            st  = Gtk.Label(label=tr("On") if enabled else tr("Off"))
            st.add_css_class("ok-col" if enabled else "dim")
            st.set_hexpand(True)
            st.set_halign(Gtk.Align.START)
            btm.append(st)
            sw = Gtk.Switch()
            sw.set_active(enabled)
            sw.set_valign(Gtk.Align.CENTER)
            sw.connect(
                "notify::active",
                lambda s, p, _uuid=ext["uuid"], _card=card, _st=st, _sw=sw:
                    self._toggle_feat(_uuid, s.get_active(), _card, _st, _sw),
            )
            btm.append(sw)
            inner.append(btm)

            # Botão remover
            rm = Gtk.Button(label=tr("Remove"))
            rm.add_css_class("flat")
            rm.add_css_class("destructive-action")
            rm.set_halign(Gtk.Align.START)
            rm.connect(
                "clicked",
                lambda b, _uuid=ext["uuid"], _name=ext["name"]:
                    self._confirm_remove(_uuid, _name),
            )
            inner.append(rm)

            # Botão configurações (apenas quando habilitada)
            if ext.get("has_settings") and enabled:
                sb_btn = Gtk.Button(label=tr("Settings"))
                sb_btn.add_css_class("flat")
                sb_btn.set_halign(Gtk.Align.START)
                sb_btn.connect(
                    "clicked",
                    lambda b, _uuid=ext["uuid"]: ExtMgr.open_prefs(_uuid),
                )
                inner.append(sb_btn)
        else:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            nl2 = Gtk.Label(label=tr("Not installed"))
            nl2.add_css_class("dim")
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

        card.append(inner)
        return card

    def _toggle_feat(
        self, uuid: str, enable: bool,
        card: Gtk.Box, status_lbl: Gtk.Label, switch: Gtk.Switch,
    ) -> None:
        def task():
            ok, err = ShellReloader.apply_extension_state(uuid, enable)
            if ok:
                GLib.idle_add(self.rebuild_featured)
                GLib.idle_add(self.refresh_installed)
                short = uuid.split("@")[0]
                msg   = f"{short} " + (tr("enabled") if enable else tr("disabled"))
                GLib.idle_add(self._toast, msg)
            else:
                GLib.idle_add(switch.set_active, not enable)
                GLib.idle_add(self._toast, tr("Error") + f": {err}")
        self._pool.submit(task)

    def _confirm_install(self, ext: Dict, card: Gtk.Box) -> None:
        parent = self.get_root()
        d = Adw.MessageDialog(
            transient_for=parent,
            heading=tr("Install extension?"),
            body=f"{ext['name']}\n{tr('Will try to install automatically.')}",
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("yes",    tr("Install"))
        d.set_response_appearance("yes", Adw.ResponseAppearance.SUGGESTED)

        def on_r(dlg, r):
            dlg.destroy()
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
                    ShellReloader.apply_extension_state(ext["uuid"], True)
                    GLib.idle_add(self.rebuild_featured)
                    GLib.idle_add(self.refresh_installed)
                    GLib.idle_add(self._toast, f"✓ {ext['name']} {tr('installed')}")
                else:
                    GLib.idle_add(self.rebuild_featured)
                    GLib.idle_add(self._toast, tr("Install failed") + f": {method}")

            self._pool.submit(task)

        d.connect("response", on_r)
        d.present()

    def _confirm_remove(self, uuid: str, name: str) -> None:
        if not ExtMgr.is_user_dir(uuid):
            self._toast(tr("System extension — cannot remove"))
            return
        parent = self.get_root()
        d = Adw.MessageDialog(
            transient_for=parent,
            heading=tr("Remove extension?"),
            body=f"{name}\n{tr('This cannot be undone.')}",
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("remove", tr("Remove"))
        d.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_r(dlg, r):
            dlg.destroy()
            if r != "remove":
                return

            def task():
                ok, err = ExtMgr.remove(uuid)
                if ok:
                    GLib.idle_add(self.rebuild_featured)
                    GLib.idle_add(self.refresh_installed)
                    GLib.idle_add(self._toast, f"{name} {tr('removed')}")
                else:
                    GLib.idle_add(self._toast, tr("Remove failed") + f": {err}")

            self._pool.submit(task)

        d.connect("response", on_r)
        d.present()

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
        lbl.add_css_class("dim")
        row.append(lbl)
        card.append(row)

    # ── Sub-aba Instaladas ────────────────────────────────────────────────────

    def _build_installed_sub(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Barra superior: contagem + botão abrir GNOME Extensions
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        toolbar.set_margin_start(22)
        toolbar.set_margin_end(22)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(4)

        self._inst_count_lbl = Gtk.Label(label="")
        self._inst_count_lbl.add_css_class("caption")
        self._inst_count_lbl.add_css_class("dim")
        self._inst_count_lbl.set_halign(Gtk.Align.START)
        self._inst_count_lbl.set_hexpand(True)
        toolbar.append(self._inst_count_lbl)

        open_btn = Gtk.Button(label=tr("Open GNOME Extensions"))
        open_btn.add_css_class("flat")
        open_btn.add_css_class("caption")
        open_btn.set_valign(Gtk.Align.CENTER)
        open_btn.connect("clicked", self._open_gnome_extensions)
        toolbar.append(open_btn)
        outer.append(toolbar)

        # Scroll com Adw.Clamp para limitar largura da lista
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(700)
        clamp.set_tightening_threshold(500)

        self._inst_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=0
        )
        self._inst_container.set_margin_start(16)
        self._inst_container.set_margin_end(16)
        self._inst_container.set_margin_top(4)
        self._inst_container.set_margin_bottom(24)

        clamp.set_child(self._inst_container)
        sc.set_child(clamp)
        outer.append(sc)
        return outer

    def _open_gnome_extensions(self, btn) -> None:
        for app_cmd in [["gnome-extensions-app"], ["gnome-shell-extension-prefs"]]:
            if shutil.which(app_cmd[0]):
                ok, err = run_cmd(app_cmd, timeout=5)
                if ok:
                    return
        run_cmd(["xdg-open", "https://extensions.gnome.org"], timeout=5)

    def refresh_installed(self) -> None:
        # Limpa container
        child = self._inst_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._inst_container.remove(child)
            child = nxt

        exts = ExtMgr.list_installed()
        self._refresh_global_btn()

        if not exts:
            self._inst_count_lbl.set_label("")
            ph = Adw.StatusPage(
                title=tr("No extensions installed"),
                icon_name="application-x-addon-symbolic",
            )
            self._inst_container.append(ph)
            return

        enabled_count = sum(1 for e in exts if e["enabled"])
        self._inst_count_lbl.set_label(
            f"{len(exts)} {tr('installed')}  ·  {enabled_count} {tr('enabled')}"
        )

        # Divide em dois grupos: Habilitadas e Desabilitadas
        enabled_exts  = [e for e in exts if e["enabled"]]
        disabled_exts = [e for e in exts if not e["enabled"]]

        for group_label, group_exts in [
            (tr("Enabled"),  enabled_exts),
            (tr("Disabled"), disabled_exts),
        ]:
            if not group_exts:
                continue

            # Cabeçalho do grupo
            gl = Gtk.Label(label=group_label)
            gl.add_css_class("caption")
            gl.add_css_class("dim")
            gl.add_css_class("heading")
            gl.set_halign(Gtk.Align.START)
            gl.set_margin_top(12)
            gl.set_margin_bottom(4)
            self._inst_container.append(gl)

            # ListBox nativa com boxed-list
            lb = Gtk.ListBox()
            lb.add_css_class("boxed-list")
            lb.set_selection_mode(Gtk.SelectionMode.NONE)
            for ext in group_exts:
                row = self._make_installed_row(ext)
                lb.append(row)
            self._inst_container.append(lb)

    def _make_installed_row(self, ext: Dict) -> Gtk.ListBoxRow:
        """
        Linha de extensão instalada como Gtk.ListBoxRow.
        Layout compacto e fixo: ícone | nome+uuid | badge sistema | switch | lixo
        """
        enabled = ext["enabled"]
        is_user = ext["user"]

        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        inner.set_margin_start(12)
        inner.set_margin_end(10)
        inner.set_margin_top(8)
        inner.set_margin_bottom(8)

        # Ícone
        ico = Gtk.Image.new_from_icon_name("application-x-addon-symbolic")
        ico.set_pixel_size(20)
        ico.set_valign(Gtk.Align.CENTER)
        if enabled:
            ico.add_css_class("accent")
        inner.append(ico)

        # Nome + UUID
        tc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        tc.set_hexpand(True)
        tc.set_valign(Gtk.Align.CENTER)

        nl = Gtk.Label(label=ext["name"])
        nl.add_css_class("body")
        nl.set_halign(Gtk.Align.START)
        nl.set_ellipsize(Pango.EllipsizeMode.END)
        nl.set_xalign(0)
        tc.append(nl)

        ul = Gtk.Label(label=ext["uuid"])
        ul.add_css_class("caption")
        ul.add_css_class("dim")
        ul.add_css_class("mono")
        ul.set_halign(Gtk.Align.START)
        ul.set_ellipsize(Pango.EllipsizeMode.END)
        ul.set_xalign(0)
        tc.append(ul)
        inner.append(tc)

        # Controles à direita
        ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ctrl.set_valign(Gtk.Align.CENTER)

        if not is_user:
            sys_l = Gtk.Label(label=tr("system"))
            sys_l.add_css_class("caption")
            sys_l.add_css_class("dim")
            ctrl.append(sys_l)

        sw = Gtk.Switch()
        sw.set_active(enabled)
        sw.set_valign(Gtk.Align.CENTER)
        uuid_ref = ext["uuid"]

        def on_sw(s, p, _uuid=uuid_ref) -> None:
            en = s.get_active()

            def task():
                ok, err = ShellReloader.apply_extension_state(_uuid, en)
                if ok:
                    GLib.idle_add(self.refresh_installed)
                    GLib.idle_add(self.rebuild_featured)
                else:
                    GLib.idle_add(s.set_active, not en)
                    GLib.idle_add(self._toast, tr("Error") + f": {err}")

            self._pool.submit(task)

        sw.connect("notify::active", on_sw)
        ctrl.append(sw)

        if is_user:
            rm = Gtk.Button(icon_name="user-trash-symbolic")
            rm.add_css_class("flat")
            rm.set_tooltip_text(tr("Remove"))
            rm.set_valign(Gtk.Align.CENTER)
            rm.connect(
                "clicked",
                lambda b, _uuid=ext["uuid"], _name=ext["name"]:
                    self._confirm_remove(_uuid, _name),
            )
            ctrl.append(rm)

        inner.append(ctrl)
        row.set_child(inner)
        return row

    # ── Toggle global ─────────────────────────────────────────────────────────

    def _refresh_global_btn(self) -> None:
        on = ExtMgr.all_globally_enabled()
        self._global_btn.set_label(tr("Disable All") if on else tr("Enable All"))
        for c in ("destructive-action", "suggested-action"):
            self._global_btn.remove_css_class(c)
        self._global_btn.add_css_class(
            "destructive-action" if on else "suggested-action"
        )

    def _on_global_toggle(self, btn) -> None:
        currently_on = ExtMgr.all_globally_enabled()

        def task():
            ok, err = ExtMgr.disable_all_globally(disable=currently_on)
            if ok:
                msg = (tr("All extensions disabled") if currently_on
                       else tr("All extensions enabled"))
                GLib.idle_add(self._refresh_global_btn)
                GLib.idle_add(self.refresh_installed)
                GLib.idle_add(self._toast, msg)
            else:
                GLib.idle_add(self._toast, tr("Error") + f": {err}")

        self._pool.submit(task)
