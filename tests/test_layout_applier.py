# SPDX-License-Identifier: MIT
"""Tests for layout_applier.py — apply layout via dconf load."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "usr" / "share" / "layout-switcher"))

import pytest
from layout_applier import LayoutApplier


class TestLayoutApplier:
    @patch("shell_reloader.ShellReloader.reload_all")
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_apply_success(self, mock_run, mock_reload, tmp_path):
        layout = tmp_path / "classic.txt"
        layout.write_text("[org/gnome/shell]\nfavorite-apps=['firefox.desktop']")

        ok, msg = LayoutApplier.apply(layout)
        assert ok is True
        mock_run.assert_called_once()
        mock_reload.assert_called_once()

    def test_apply_nonexistent_file(self):
        ok, msg = LayoutApplier.apply(Path("/nonexistent/layout.txt"))
        assert ok is False
        assert "not found" in msg

    def test_apply_none_path(self):
        ok, msg = LayoutApplier.apply(None)
        assert ok is False

    def test_apply_empty_file(self, tmp_path):
        layout = tmp_path / "empty.txt"
        layout.write_text("")
        ok, msg = LayoutApplier.apply(layout)
        assert ok is False
        assert "empty" in msg.lower()

    @patch("shell_reloader.ShellReloader.reload_all")
    @patch("layout_applier.run_cmd", return_value=(False, "dconf error"))
    def test_apply_dconf_failure(self, mock_run, mock_reload, tmp_path):
        layout = tmp_path / "bad.txt"
        layout.write_text("[org/gnome/shell]\ndata=true")
        ok, msg = LayoutApplier.apply(layout)
        assert ok is False
        mock_reload.assert_not_called()


class TestShellReloader:
    @patch("shell_reloader.run_cmd", return_value=(True, ""))
    @patch("shell_reloader.is_wayland", return_value=True)
    def test_reload_all_wayland(self, mock_way, mock_run):
        from shell_reloader import ShellReloader
        ShellReloader.reload_all()
        # Should NOT call reexec on Wayland
        calls = [str(c) for c in mock_run.call_args_list]
        assert not any("reexec" in c for c in calls)

    @patch("shell_reloader.run_cmd", return_value=(True, ""))
    @patch("shell_reloader.is_wayland", return_value=False)
    def test_reload_all_x11(self, mock_way, mock_run):
        from shell_reloader import ShellReloader
        ShellReloader.reload_all()
        # Should call multiple strategies including reexec on X11
        assert mock_run.call_count >= 2
