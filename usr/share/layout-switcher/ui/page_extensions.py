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

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, GLib, Gtk, Pango

import update_checker
from constants import FEATURED_EXTENSIONS, tr
from extension_manager import ExtMgr
from helper_client import HELPER_UUID
from shell_reloader import ShellReloader
from ui.ext_browse_view import ExtBrowseView
from ui.ext_detail_view import ExtDetailView
from utils import run_cmd


class ExtensionsPage(Gtk.Box):
    """
    Página de Extensões com sub-abas Destaque e Instaladas.
    """

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool = pool
        self._toast = toast_cb
        self._ext_sub = "featured"
        # uuid → UpdateInfo. Populated by MainWindow after running the checker.
        self._updates: Dict[str, update_checker.UpdateInfo] = {}
        self._build()

    def set_updates(self, updates: Dict[str, update_checker.UpdateInfo]) -> None:
        """Recebe o dict de atualizações disponíveis e atualiza a UI."""
        self._updates = dict(updates or {})
        # Re-render: featured cards podem ganhar badge, installed list precisa
        # mostrar o botão "Update all" e badges por linha.
        self.rebuild_featured()
        self.refresh_installed()

    def _build(self) -> None:
        # ── Sub-abas + botão global na mesma linha, no topo ───────────────────
        tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tab_bar.set_margin_start(26)
        tab_bar.set_margin_end(22)
        tab_bar.set_margin_top(8)
        tab_bar.set_margin_bottom(10)

        self._tab_btns: Dict[str, Gtk.Button] = {}
        for key, label in [
            ("featured", tr("Featured")),
            ("browse", tr("Browse")),
            ("installed", tr("Installed")),
        ]:
            btn = Gtk.Button(label=label)
            btn.add_css_class("sub-tab")
            btn.add_css_class("flat")
            is_default = key == self._ext_sub
            if is_default:
                btn.add_css_class("sub-on")
            btn.connect("clicked", lambda b, k=key: self._switch_sub(k))
            tab_bar.append(btn)
            self._tab_btns[key] = btn

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        tab_bar.append(spacer)

        # Botão global "Desativar todas" só aparece na aba Instaladas.
        self._global_btn = Gtk.Button()
        self._global_btn.add_css_class("global-btn")
        self._global_btn.set_valign(Gtk.Align.CENTER)
        self._refresh_global_btn()
        self._global_btn.connect("clicked", self._on_global_toggle)
        self._global_btn.set_visible(self._ext_sub == "installed")
        tab_bar.append(self._global_btn)

        self.append(tab_bar)

        # ── Stack de conteúdo ─────────────────────────────────────────────────
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(120)
        self._stack.set_vexpand(True)
        self._stack.add_named(self._build_featured_sub(), "featured")
        self._stack.add_named(self._build_browse_sub(), "browse")
        self._stack.add_named(self._build_installed_sub(), "installed")
        self.append(self._stack)

    def _build_browse_sub(self) -> Gtk.Widget:
        # NavigationView permite empurrar a página de detalhes em cima da lista.
        self._browse_nav = Adw.NavigationView()

        self._browse_view = ExtBrowseView(
            pool=self._pool,
            toast_cb=self._toast,
            on_open_detail=self._open_detail,
            on_after_install=self._on_browse_installed,
        )
        root_page = Adw.NavigationPage()
        root_page.set_title(tr("Browse"))
        root_page.set_child(self._browse_view)
        self._browse_nav.add(root_page)
        return self._browse_nav

    def _open_detail(self, uuid: str, pk: int) -> None:
        """Abre a página de detalhes empurrando-a no NavigationView do Browse."""
        detail = ExtDetailView(
            uuid=uuid,
            pk=pk,
            pool=self._pool,
            toast_cb=self._toast,
            on_after_install=self._on_browse_installed,
        )
        self._browse_nav.push(detail)

    def _on_browse_installed(self) -> None:
        """Hook chamado pelo ExtBrowseView depois de instalar uma extensão."""
        self.rebuild_featured()
        self.refresh_installed()

    def _switch_sub(self, key: str) -> None:
        self._ext_sub = key
        for k, btn in self._tab_btns.items():
            selected = k == key
            if selected:
                btn.add_css_class("sub-on")
            else:
                btn.remove_css_class("sub-on")

        # Botão "Desativar todas" só faz sentido na aba Instaladas.
        if hasattr(self, "_global_btn"):
            self._global_btn.set_visible(key == "installed")

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
        enabled = ExtMgr.is_enabled(ext["uuid"]) if installed else False

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

        inner.append(self._make_feat_header(ext))

        # system extension badge
        if installed and not ExtMgr.is_user_dir(ext["uuid"]):
            sys_lbl = Gtk.Label(label=tr("System extension"))
            sys_lbl.add_css_class("caption")
            sys_lbl.add_css_class("dim-label")
            sys_lbl.set_halign(Gtk.Align.START)
            sys_lbl.set_margin_bottom(4)
            inner.append(sys_lbl)

        inner.append(Gtk.Separator())

        if installed:
            self._build_feat_installed(inner, ext, card, enabled)
            if ext["uuid"] in self._updates:
                upd_lbl = Gtk.Label(label=tr("Update available"))
                upd_lbl.add_css_class("caption")
                upd_lbl.add_css_class("accent")
                upd_lbl.set_halign(Gtk.Align.START)
                inner.append(upd_lbl)
        else:
            self._build_feat_not_installed(inner, ext, card)

        card.append(inner)

        card_label = ext["name"]
        if installed and enabled:
            card_label = f"{ext['name']} ({tr('enabled')})"
        elif installed:
            card_label = f"{ext['name']} ({tr('disabled')})"
        else:
            card_label = f"{ext['name']} ({tr('Not installed')})"
        card.update_property([Gtk.AccessibleProperty.LABEL], [card_label])
        return card

    def _make_feat_header(self, ext: Dict) -> Gtk.Box:
        """Build card header: icon + name + description + author."""
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

    def _build_feat_installed(
        self, inner: Gtk.Box, ext: Dict, card: Gtk.Box, enabled: bool
    ) -> None:
        """Build toggle/remove/settings controls for installed extension."""
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
            lambda s, p, _uuid=ext["uuid"], _card=card, _st=st, _sw=sw: self._toggle_feat(
                _uuid, s.get_active(), _card, _st, _sw
            ),
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

    def _build_feat_not_installed(self, inner: Gtk.Box, ext: Dict, card: Gtk.Box) -> None:
        """Build install button + EGO link for not-installed extension."""
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

    def _toggle_feat(
        self,
        uuid: str,
        enable: bool,
        card: Gtk.Box,
        status_lbl: Gtk.Label,
        switch: Gtk.Switch,
    ) -> None:
        def task():
            ok, err = ShellReloader.apply_extension_state(uuid, enable)
            if ok:
                GLib.idle_add(self.rebuild_featured)
                GLib.idle_add(self.refresh_installed)
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
            heading=tr("Install extension?"),
            body=f"{ext['name']}\n{tr('Will try to install automatically.')}",
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("yes", tr("Install"))
        d.set_response_appearance("yes", Adw.ResponseAppearance.SUGGESTED)

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
                    GLib.idle_add(self.rebuild_featured)
                    GLib.idle_add(self.refresh_installed)
                    GLib.idle_add(
                        self._toast,
                        tr("{name} installed and enabled. Restart the session to use it.").format(
                            name=ext["name"]
                        ),
                    )
                else:
                    GLib.idle_add(self.rebuild_featured)
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
            heading=tr("Remove extension?"),
            body=f"{name}\n{tr('This cannot be undone.')}",
        )
        d.add_response("cancel", tr("Cancel"))
        d.add_response("remove", tr("Remove"))
        d.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_r(_dlg, r):
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

    # ── Sub-aba Instaladas ────────────────────────────────────────────────────

    def _build_installed_sub(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Barra superior: contagem + botão abrir GNOME Extensions
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(22)
        toolbar.set_margin_end(22)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(4)

        self._inst_count_lbl = Gtk.Label(label="")
        self._inst_count_lbl.add_css_class("caption")
        self._inst_count_lbl.add_css_class("dim-label")
        self._inst_count_lbl.set_halign(Gtk.Align.START)
        self._inst_count_lbl.set_hexpand(True)
        toolbar.append(self._inst_count_lbl)

        # "Update all" button — visível apenas quando há atualizações pendentes.
        self._update_all_btn = Gtk.Button(label=tr("Update all"))
        self._update_all_btn.add_css_class("suggested-action")
        self._update_all_btn.add_css_class("pill")
        self._update_all_btn.set_valign(Gtk.Align.CENTER)
        self._update_all_btn.set_visible(False)
        self._update_all_btn.connect("clicked", lambda b: self._do_update_all())
        toolbar.append(self._update_all_btn)

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

        self._inst_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
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

        # update sub-tab label with count
        inst_btn = self._tab_btns.get("installed")
        if inst_btn:
            inst_btn.set_label(f"{tr('Installed')} ({len(exts)})")

        if not exts:
            self._inst_count_lbl.set_label("")
            self._update_all_btn.set_visible(False)
            ph = Adw.StatusPage(
                title=tr("No extensions installed"),
                icon_name="application-x-addon-symbolic",
            )
            self._inst_container.append(ph)
            return

        enabled_count = sum(1 for e in exts if e["enabled"])
        update_count = sum(1 for e in exts if e["uuid"] in self._updates)
        summary = f"{len(exts)} {tr('installed')}  ·  {enabled_count} {tr('enabled')}"
        if update_count > 0:
            summary += f"  ·  {update_count} {tr('update available')}"
        self._inst_count_lbl.set_label(summary)
        self._update_all_btn.set_visible(update_count > 0)
        self._update_all_btn.set_label(
            f"{tr('Update all')} ({update_count})" if update_count > 1 else tr("Update")
        )

        # Divide em dois grupos: Habilitadas e Desabilitadas
        enabled_exts = [e for e in exts if e["enabled"]]
        disabled_exts = [e for e in exts if not e["enabled"]]

        for group_label, group_exts in [
            (tr("Enabled"), enabled_exts),
            (tr("Disabled"), disabled_exts),
        ]:
            if not group_exts:
                continue

            # Cabeçalho do grupo
            gl = Gtk.Label(label=group_label)
            gl.add_css_class("caption")
            gl.add_css_class("dim-label")
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
        is_required = ext["uuid"] == HELPER_UUID

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
        ul.add_css_class("dim-label")
        ul.add_css_class("mono")
        ul.set_halign(Gtk.Align.START)
        ul.set_ellipsize(Pango.EllipsizeMode.END)
        ul.set_xalign(0)
        tc.append(ul)
        if is_required:
            required_label = Gtk.Label(label=tr("Required for layout switching"))
            required_label.add_css_class("caption")
            required_label.add_css_class("accent")
            required_label.set_halign(Gtk.Align.START)
            required_label.set_xalign(0)
            tc.append(required_label)
        inner.append(tc)

        # Right-side controls use fixed slots so every row lines up.
        ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ctrl.set_valign(Gtk.Align.CENTER)
        ctrl.set_halign(Gtk.Align.END)

        update_info = self._updates.get(ext["uuid"])
        if update_info is not None:
            up_btn = Gtk.Button(label=tr("Update"))
            up_btn.add_css_class("suggested-action")
            up_btn.add_css_class("pill")
            up_btn.set_valign(Gtk.Align.CENTER)
            up_btn.set_tooltip_text(
                tr("Update from v{old} to v{new}").format(
                    old=update_info.current_version, new=update_info.latest_version
                )
            )
            up_btn.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [f"{tr('Update')} {ext['name']}"],
            )
            uuid_capture = ext["uuid"]
            up_btn.connect("clicked", lambda b, _u=uuid_capture: self._do_update_one(_u))
            ctrl.append(up_btn)

        prefs_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        prefs_slot.set_size_request(34, 1)
        prefs_slot.set_halign(Gtk.Align.CENTER)
        prefs_slot.set_valign(Gtk.Align.CENTER)
        if ext.get("has_prefs") and enabled:
            pref_btn = Gtk.Button(icon_name="applications-system-symbolic")
            pref_btn.add_css_class("flat")
            pref_btn.add_css_class("extension-action-button")
            pref_btn.set_tooltip_text(tr("Settings"))
            pref_btn.set_valign(Gtk.Align.CENTER)
            pref_btn.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [f"{tr('Settings')} {ext['name']}"],
            )
            uuid_pref = ext["uuid"]
            pref_btn.connect("clicked", lambda b, _u=uuid_pref: ExtMgr.open_prefs(_u))
            prefs_slot.append(pref_btn)
        ctrl.append(prefs_slot)

        sw = Gtk.Switch()
        sw.set_active(enabled)
        sw.set_valign(Gtk.Align.CENTER)
        if is_required:
            sw.set_sensitive(False)
            sw.set_tooltip_text(tr("Required for layout switching"))
            switch_label = f"{ext['name']}: {tr('Required for layout switching')}"
        else:
            switch_label = f"{tr('Toggle')} {ext['name']}"
        sw.update_property([Gtk.AccessibleProperty.LABEL], [switch_label])
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

        if not is_required:
            sw.connect("notify::active", on_sw)
        switch_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        switch_slot.set_size_request(58, 1)
        switch_slot.set_halign(Gtk.Align.CENTER)
        switch_slot.set_valign(Gtk.Align.CENTER)
        switch_slot.append(sw)
        ctrl.append(switch_slot)

        remove_slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        remove_slot.set_size_request(34, 1)
        remove_slot.set_halign(Gtk.Align.CENTER)
        remove_slot.set_valign(Gtk.Align.CENTER)
        system_remove_msg = tr(
            "This extension cannot be removed here because it was installed by the system."
        )
        if is_user:
            rm = Gtk.Button(icon_name="user-trash-symbolic")
            rm.add_css_class("flat")
            rm.add_css_class("extension-action-button")
            rm.set_tooltip_text(tr("Remove"))
            rm.update_property([Gtk.AccessibleProperty.LABEL], [f"{tr('Remove')} {ext['name']}"])
            rm.set_valign(Gtk.Align.CENTER)
            rm.connect(
                "clicked",
                lambda b, _uuid=ext["uuid"], _name=ext["name"]: self._confirm_remove(_uuid, _name),
            )
            remove_slot.append(rm)
        else:
            rm = Gtk.Button(icon_name="user-trash-symbolic")
            rm.add_css_class("flat")
            rm.add_css_class("extension-action-button")
            rm.add_css_class("extension-action-button-disabled")
            rm.set_tooltip_text(system_remove_msg)
            rm.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [system_remove_msg],
            )
            rm.set_valign(Gtk.Align.CENTER)
            rm.connect("clicked", lambda b, msg=system_remove_msg: self._toast(msg))
            remove_slot.append(rm)
        ctrl.append(remove_slot)

        inner.append(ctrl)
        row.set_child(inner)
        return row

    # ── Atualizações ──────────────────────────────────────────────────────────

    def _do_update_one(self, uuid: str) -> None:
        info = self._updates.get(uuid)
        if info is None:
            return

        def task():
            ok, msg = update_checker.apply_update(info)
            if ok:
                self._updates.pop(uuid, None)
                GLib.idle_add(self.rebuild_featured)
                GLib.idle_add(self.refresh_installed)
                GLib.idle_add(
                    self._toast,
                    tr("{name} updated to v{ver}").format(
                        name=uuid.split("@")[0], ver=info.latest_version
                    ),
                )
            else:
                GLib.idle_add(self._toast, tr("Update failed") + f": {msg}")

        self._pool.submit(task)

    def _do_update_all(self) -> None:
        if not self._updates:
            return
        # snapshot da lista para iterar (a UI pode mexer no dict durante o loop)
        snapshot = list(self._updates.values())
        total = len(snapshot)

        def task():
            failed = []
            for info in snapshot:
                ok, msg = update_checker.apply_update(info)
                if ok:
                    self._updates.pop(info.uuid, None)
                else:
                    failed.append(info.uuid)
            GLib.idle_add(self.rebuild_featured)
            GLib.idle_add(self.refresh_installed)
            if not failed:
                GLib.idle_add(
                    self._toast,
                    tr("Updated {n} extensions").format(n=total),
                )
            else:
                GLib.idle_add(
                    self._toast,
                    tr("Updated {n}/{t}; failed: {f}").format(
                        n=total - len(failed), t=total, f=len(failed)
                    ),
                )

        self._pool.submit(task)

    # ── Toggle global ─────────────────────────────────────────────────────────

    def _refresh_global_btn(self) -> None:
        on = ExtMgr.all_globally_enabled()
        label = tr("Disable All") if on else tr("Enable All")
        self._global_btn.set_label(label)
        self._global_btn.update_property([Gtk.AccessibleProperty.LABEL], [label])
        for c in ("destructive-action", "suggested-action"):
            self._global_btn.remove_css_class(c)
        self._global_btn.add_css_class("destructive-action" if on else "suggested-action")

    def _on_global_toggle(self, btn) -> None:
        currently_on = ExtMgr.all_globally_enabled()

        if currently_on:
            # confirm before disabling all
            parent = self.get_root()
            d = Adw.AlertDialog(
                heading=tr("Disable all extensions?"),
                body=tr("All extensions will be disabled. You can re-enable them later."),
            )
            d.add_response("cancel", tr("Cancel"))
            d.add_response("disable", tr("Disable All"))
            d.set_response_appearance("disable", Adw.ResponseAppearance.DESTRUCTIVE)

            def on_r(_dlg, r):
                if r == "disable":
                    self._do_global_toggle(True)

            d.connect("response", on_r)
            d.present(parent)
        else:
            self._do_global_toggle(False)

    def _do_global_toggle(self, currently_on: bool) -> None:
        def task():
            ok, err = ExtMgr.disable_all_globally(disable=currently_on)
            if ok:
                msg = (
                    tr("All extensions disabled") if currently_on else tr("All extensions enabled")
                )
                GLib.idle_add(self._refresh_global_btn)
                GLib.idle_add(self.refresh_installed)
                GLib.idle_add(self._toast, msg)
            else:
                GLib.idle_add(self._toast, tr("Error") + f": {err}")

        self._pool.submit(task)
