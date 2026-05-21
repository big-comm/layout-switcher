# SPDX-License-Identifier: MIT
"""
ui/dialog_backups.py — Dialogo de gerenciamento de backups do dconf.

Lista todos os backups em ``~/.config/big-appearance/backups/`` e permite:
  - criar snapshot manual
  - restaurar qualquer backup (com confirmacao)
  - excluir um backup individual

O backup mais recente recebe destaque visual (subtitulo "Latest").

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import datetime
from pathlib import Path
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from backup_manager import BackupManager
from constants import BACKUP_DIR, tr


def _humanize_ts(path: Path) -> str:
    """Converte ``backup_YYYYMMDD_HHMMSS.dconf`` em string legivel."""
    try:
        stem = path.stem  # backup_20260421_143018
        raw = stem.replace("backup_", "")
        ts = datetime.datetime.strptime(raw, "%Y%m%d_%H%M%S")
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return path.name


def _humanize_size(nbytes: int) -> str:
    """Formata tamanho em KiB/MiB."""
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024 * 1024:
        return f"{nbytes / 1024:.1f} KiB"
    return f"{nbytes / (1024 * 1024):.2f} MiB"


class BackupsDialog(Adw.Dialog):
    """Dialogo modal listando backups com Restore/Delete em cada linha."""

    def __init__(
        self,
        pool,
        toast_cb: Callable[[str], None],
        on_restored: Callable[[], None],
    ) -> None:
        super().__init__()
        self._pool = pool
        self._toast = toast_cb
        self._on_restored = on_restored

        self.set_title(tr("Backups"))
        self.set_content_width(560)
        self.set_content_height(560)

        self._build()
        self._populate()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        toolbar = Adw.ToolbarView()

        hdr = Adw.HeaderBar()
        hdr.set_show_end_title_buttons(True)

        self._create_btn = Gtk.Button(label=tr("Create backup now"))
        self._create_btn.add_css_class("suggested-action")
        self._create_btn.set_tooltip_text(tr("Snapshot current dconf settings"))
        self._create_btn.connect("clicked", self._on_create)
        hdr.pack_start(self._create_btn)

        toolbar.add_top_bar(hdr)

        # ── Conteudo: lista scrollavel ou status vazio ───────────────────────
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Empty state
        empty = Adw.StatusPage()
        empty.set_icon_name("drive-harddisk-symbolic")
        empty.set_title(tr("No backups yet"))
        empty.set_description(
            tr("A backup is created automatically every time you apply a layout.")
        )
        self._stack.add_named(empty, "empty")

        # List state
        self._sw = Gtk.ScrolledWindow()
        self._sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._sw.set_vexpand(True)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_start(16)
        self._list_box.set_margin_end(16)
        self._list_box.set_margin_top(16)
        self._list_box.set_margin_bottom(16)

        self._sw.set_child(self._list_box)
        self._stack.add_named(self._sw, "list")

        toolbar.set_content(self._stack)
        self.set_child(toolbar)

    def _populate(self) -> None:
        # Limpa rows antigas
        child = self._list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt

        backups = BackupManager.list_all()
        if not backups:
            self._stack.set_visible_child_name("empty")
            return

        self._stack.set_visible_child_name("list")
        latest: Optional[Path] = BackupManager.latest()
        for path in backups:
            row = self._make_row(path, is_latest=(latest and path == latest))
            self._list_box.append(row)

    def _make_row(self, path: Path, is_latest: bool) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(_humanize_ts(path))

        try:
            size = path.stat().st_size
        except Exception:
            size = 0

        subtitle_parts = [_humanize_size(size)]
        if is_latest:
            subtitle_parts.append(tr("Latest"))
        row.set_subtitle(" · ".join(subtitle_parts))

        # Restore
        restore_btn = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
        restore_btn.set_tooltip_text(tr("Restore this backup"))
        restore_btn.add_css_class("flat")
        restore_btn.set_valign(Gtk.Align.CENTER)
        restore_btn.connect("clicked", lambda _b, p=path: self._on_restore_clicked(p))
        row.add_suffix(restore_btn)

        # Delete
        delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        delete_btn.set_tooltip_text(tr("Delete this backup"))
        delete_btn.add_css_class("flat")
        delete_btn.add_css_class("destructive-action")
        delete_btn.set_valign(Gtk.Align.CENTER)
        delete_btn.connect("clicked", lambda _b, p=path: self._on_delete_clicked(p))
        row.add_suffix(delete_btn)

        return row

    # ── Acoes ─────────────────────────────────────────────────────────────────

    def _on_create(self, _btn) -> None:
        self._create_btn.set_sensitive(False)

        def task():
            ok, info = BackupManager.create()
            GLib.idle_add(self._on_create_done, ok, info)

        self._pool.submit(task)

    def _on_create_done(self, ok: bool, info: str) -> bool:
        self._create_btn.set_sensitive(True)
        if ok:
            self._toast(tr("Backup created"))
            self._populate()
        else:
            self._toast(tr("Backup failed") + f": {info}")
        return False

    def _on_restore_clicked(self, path: Path) -> None:
        confirm = Adw.AlertDialog(
            heading=tr("Restore this backup?"),
            body=tr(
                "All current dconf settings will be overwritten with the snapshot from {ts}."
            ).format(ts=_humanize_ts(path)),
        )
        confirm.add_response("cancel", tr("Cancel"))
        confirm.add_response("restore", tr("Restore"))
        confirm.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_default_response("restore")
        confirm.set_close_response("cancel")

        def on_r(_dlg, r):
            if r != "restore":
                return

            def task():
                ok, info = BackupManager.restore(path)
                GLib.idle_add(self._on_restore_done, ok, info)

            self._pool.submit(task)

        confirm.connect("response", on_r)
        confirm.present(self)

    def _on_restore_done(self, ok: bool, info: str) -> bool:
        if ok:
            self._toast(tr("Backup restored"))
            self._on_restored()
            self.close()
        else:
            self._toast(tr("Restore failed") + f": {info}")
        return False

    def _on_delete_clicked(self, path: Path) -> None:
        confirm = Adw.AlertDialog(
            heading=tr("Delete this backup?"),
            body=_humanize_ts(path),
        )
        confirm.add_response("cancel", tr("Cancel"))
        confirm.add_response("delete", tr("Delete"))
        confirm.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_default_response("cancel")
        confirm.set_close_response("cancel")

        def on_r(_dlg, r):
            if r != "delete":
                return
            try:
                path.unlink(missing_ok=True)
                # Se apagou o alvo do symlink "latest", remove o symlink
                lnk = BACKUP_DIR / "latest.dconf"
                if lnk.is_symlink():
                    try:
                        import os

                        if not (lnk.parent / os.readlink(str(lnk))).exists():
                            lnk.unlink()
                    except Exception:
                        pass
                self._toast(tr("Backup deleted"))
                self._populate()
            except Exception as exc:
                self._toast(tr("Delete failed") + f": {exc}")

        confirm.connect("response", on_r)
        confirm.present(self)
