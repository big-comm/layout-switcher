# SPDX-License-Identifier: MIT
"""
ui/page_layouts.py — Pagina de Layouts.

Comportamento tipo KDE Plasma: ao trocar de layout, o estado atual e salvo
como snapshot do layout anterior. Ao voltar para um layout com snapshot,
o usuario escolhe entre retomar sua versao modificada ou aplicar o padrao.

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

from pathlib import Path
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from backup_manager import BackupManager
from constants import ICONS_DIR, LAYOUTS, tr
from layout_applier import LayoutApplier
from settings_store import Settings
from snapshot_manager import SnapshotManager
from ui.tooltip import Tooltip
from utils import find_file


class LayoutsPage(Gtk.Box):
    """Pagina de Layouts com grid de cards + Resume/Original."""

    def __init__(self, pool, toast_cb) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool = pool
        self._toast = toast_cb
        self._prefs = Settings()
        self._active_layout: Optional[str] = self._prefs.get("active_layout")

        self._build()

    def _build(self) -> None:
        # Label de status (aplicando/aplicado/erro). Comeca vazio e invisivel —
        # so aparece quando ha status real para mostrar.
        self._status_lbl = Gtk.Label(label="")
        self._status_lbl.add_css_class("dim-label")
        self._status_lbl.set_halign(Gtk.Align.START)
        self._status_lbl.set_margin_start(26)
        self._status_lbl.set_margin_top(6)
        self._status_lbl.set_margin_bottom(10)
        self._status_lbl.set_visible(False)
        self._status_lbl.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [tr("Layout status")],
        )
        self.append(self._status_lbl)

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

    @staticmethod
    def _layout_id(cfg: str) -> str:
        """Stem do arquivo de layout (ex.: 'biggnome.txt' -> 'biggnome')."""
        return Path(cfg).stem

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
        has_snapshot = SnapshotManager.has(self._layout_id(cfg))
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("layout-card")
        if is_on:
            card.add_css_class("layout-on")

        # Preview (SVG) com Overlay para sobrepor o badge "Modified" discreto
        overlay = Gtk.Overlay()
        overlay.add_css_class("layout-preview")
        overlay.set_halign(Gtk.Align.CENTER)

        icon_path = find_file(icon_file, [ICONS_DIR])
        if icon_path:
            pic = Gtk.Picture.new_for_filename(str(icon_path))
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            pic.set_size_request(170, 100)
            overlay.set_child(pic)
        else:
            ico = Gtk.Image.new_from_icon_name(fallback)
            ico.set_pixel_size(56)
            ico.set_halign(Gtk.Align.CENTER)
            ico.set_valign(Gtk.Align.CENTER)
            overlay.set_child(ico)

        # Badge "Modified" no topo-centro do preview, flutuando um pouco
        # abaixo da borda superior para nao sobrepor o desenho do layout
        if has_snapshot:
            badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
            badge.add_css_class("layout-modified-badge")
            badge.set_halign(Gtk.Align.CENTER)
            badge.set_valign(Gtk.Align.START)
            badge.set_margin_top(16)
            badge.set_tooltip_text(tr("Contains your saved customizations"))
            badge_icon = Gtk.Image.new_from_icon_name("document-edit-symbolic")
            badge_icon.set_pixel_size(10)
            badge.append(badge_icon)
            badge_lbl = Gtk.Label(label=tr("Modified"))
            badge_lbl.add_css_class("caption")
            badge.append(badge_lbl)
            overlay.add_overlay(badge)

        # Check de ativo no canto superior-direito (reforca o glow neon)
        if is_on:
            check = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            check.set_pixel_size(14)
            check.add_css_class("layout-active-check")
            check.set_halign(Gtk.Align.END)
            check.set_valign(Gtk.Align.START)
            check.set_margin_end(6)
            check.set_margin_top(14)
            check.set_tooltip_text(tr("Active"))
            overlay.add_overlay(check)

        card.append(overlay)

        # Nome do layout (em cor accent + bold quando ativo)
        lbl = Gtk.Label(label=name)
        lbl.add_css_class("heading")
        lbl.add_css_class("layout-name")
        if is_on:
            lbl.add_css_class("layout-name-active")
        lbl.set_halign(Gtk.Align.CENTER)
        lbl.set_margin_bottom(4)
        card.append(lbl)

        # Descricao so aparece no hover como popover elegante, nao poluindo o card
        if desc:
            Tooltip.attach(card, desc)

        gest = Gtk.GestureClick()
        gest.connect(
            "released",
            lambda _g, _n, _x, _y, __n=name, __c=cfg: self._on_click(__n, __c),
        )
        card.add_controller(gest)

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

    # ── Interacao ─────────────────────────────────────────────────────────────

    def _on_click(self, name: str, cfg: str) -> None:
        if name == self._active_layout:
            self._toast(tr("This layout is already active"))
            return

        target_id = self._layout_id(cfg)
        has_snapshot = SnapshotManager.has(target_id)

        parent = self.get_root()
        d = Adw.AlertDialog(heading=name)

        if has_snapshot:
            d.set_body(
                tr(
                    "You have previously modified this layout. Apply the "
                    "original system default or resume your changes?"
                )
            )
            d.add_response("cancel", tr("Cancel"))
            d.add_response("resume", tr("Resume my changes"))
            d.add_response("original", tr("Apply original"))
            d.set_response_appearance("original", Adw.ResponseAppearance.SUGGESTED)
            d.set_default_response("original")
        else:
            d.set_body(
                tr(
                    "Apply this layout? A backup of your current "
                    "configuration will be created automatically."
                )
            )
            d.add_response("cancel", tr("Cancel"))
            d.add_response("apply", tr("Apply"))
            d.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
            d.set_default_response("apply")

        d.set_close_response("cancel")

        def on_r(_dlg, r):
            if r == "cancel":
                return
            ok_bk, info = BackupManager.create()
            if not ok_bk:
                self._toast(tr("Backup failed") + f": {info}")
            self._save_current_snapshot()
            use_snapshot = r == "resume"
            self._apply(name, cfg, use_snapshot=use_snapshot)

        d.connect("response", on_r)
        d.present(parent)

    def _save_current_snapshot(self) -> None:
        """Dump do dconf atual como snapshot do layout ativo."""
        if not self._active_layout:
            return
        for lname, lcfg, *_rest in LAYOUTS:
            if lname == self._active_layout:
                SnapshotManager.save(self._layout_id(lcfg))
                return

    def _apply(self, name: str, cfg: str, use_snapshot: bool = False) -> None:
        """Aplica layout. use_snapshot=True carrega a versao modificada."""
        self._set_status(f"{tr('Applying')} {name}…", "dim-label")
        layout_id = self._layout_id(cfg)

        def task():
            if use_snapshot:
                data = SnapshotManager.read(layout_id)
                if not data:
                    GLib.idle_add(self._done, name, False, tr("Snapshot not found"))
                    return
                # Snapshots são dumps locais — DTP monitor IDs já estão corretos.
                # load_dconf_safely escreve settings.gnome e faz dconf load;
                # o gsettings listener do Shell reabilita as extensões via
                # enabled-extensions, então não precisa reload_all manual.
                before = LayoutApplier._enabled_extensions()
                ok, err = LayoutApplier.load_dconf_safely(
                    data,
                    persist=True,
                    before_uuids=before,
                )
            else:
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
            self._prefs.set("active_layout", name)
            self._set_status(f"{name} {tr('applied')}", "ok-col")
            self.rebuild_grid()
            root = self.get_root()
            overlay = getattr(root, "_toast_overlay", None)
            latest = BackupManager.latest()

            # Primary toast: undo (high priority — won't be dismissed by the
            # restart toast below, and shows first).
            if latest and overlay:
                undo_toast = Adw.Toast(title=f"{name} {tr('applied')}", timeout=15)
                undo_toast.set_priority(Adw.ToastPriority.HIGH)
                undo_toast.set_button_label(tr("Undo"))
                undo_toast.connect(
                    "button-clicked",
                    lambda _t: self._undo_layout(prev, latest),
                )
                overlay.add_toast(undo_toast)
            elif overlay:
                self._toast(f"{name} {tr('applied')}")

            # Secondary toast: offer a session restart for the 100% clean
            # state. Live apply skips ``dconf reset -f /`` to avoid crashing
            # extensions with buggy disable() handlers, so a small subset of
            # visual artefacts (e.g. opaque panel) may need a relogin.
            # ``settings.gnome`` was already written cleanly, so the next
            # session is guaranteed perfect.
            if overlay:
                restart_toast = Adw.Toast(
                    title=tr("Restart the session for the 100% clean state"),
                    timeout=20,
                )
                restart_toast.set_button_label(tr("Restart now"))
                restart_toast.connect(
                    "button-clicked",
                    lambda _t: self._restart_session(),
                )
                overlay.add_toast(restart_toast)
        else:
            self._set_status(f"{tr('Error')}: {msg}", "err-col")

    def _restart_session(self) -> None:
        """
        Log out via gnome-session-quit. comm-gnome-config's
        startgnome-community then runs reset+load on the clean
        settings.gnome we wrote during apply, so the new session
        starts from a guaranteed clean state.
        """
        import subprocess

        try:
            subprocess.Popen(
                ["gnome-session-quit", "--logout", "--no-prompt"],
                start_new_session=True,
            )
        except OSError as exc:
            self._toast(f"{tr('Cannot restart session')}: {exc}")

    def _undo_layout(self, prev_name, backup_path) -> None:
        """Restaura o layout anterior a partir do backup."""

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
        if prev_name:
            self._prefs.set("active_layout", prev_name)
        self._set_status(tr("Layout restored"), "ok-col")
        self.rebuild_grid()
        self._toast(tr("Previous layout restored"))

    def _set_status(self, text: str, css: str) -> None:
        for c in ("ok-col", "err-col", "dim-label"):
            self._status_lbl.remove_css_class(c)
        if css == "ok-col":
            text = f"✓ {text}"
        elif css == "err-col":
            text = f"✗ {text}"
        self._status_lbl.add_css_class(css)
        self._status_lbl.set_label(text)
        # Torna visivel somente quando ha texto — evita espaco vazio na pagina
        self._status_lbl.set_visible(bool(text))
