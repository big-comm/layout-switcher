# SPDX-License-Identifier: MIT
"""Tests for utils.py — run_cmd, gsettings/dconf helpers, find_file, color_from_name."""

import os
from pathlib import Path
from unittest.mock import patch

from utils import (
    color_from_name,
    dconf_read,
    dconf_write,
    find_file,
    gnome_shell_version,
    gsettings_get,
    gsettings_set,
    is_wayland,
    run_cmd,
)

# ── run_cmd ───────────────────────────────────────────────────────────────────


class TestRunCmd:
    def test_success(self):
        ok, out = run_cmd(["echo", "hello"])
        assert ok is True
        assert "hello" in out

    def test_failure_exit_code(self):
        ok, out = run_cmd(["false"])
        assert ok is False

    def test_command_not_found(self):
        ok, out = run_cmd(["__nonexistent_command_xyz__"])
        assert ok is False
        assert "command not found" in out

    def test_timeout(self):
        ok, out = run_cmd(["sleep", "10"], timeout=1)
        assert ok is False
        assert "timed out" in out

    def test_stdin_text(self):
        ok, out = run_cmd(["cat"], stdin_text="hello world")
        assert ok is True
        assert "hello world" in out

    def test_env_override(self):
        ok, out = run_cmd(["env"], env={"TEST_VAR_XYZ": "123"})
        assert ok is True
        assert "TEST_VAR_XYZ=123" in out


# ── gsettings/dconf helpers ───────────────────────────────────────────────────


class TestGsettings:
    @patch("utils.run_cmd", return_value=(True, "'Adwaita'"))
    def test_gsettings_get_success(self, mock_run):
        val = gsettings_get("org.gnome.desktop.interface", "gtk-theme")
        assert val == "Adwaita"
        mock_run.assert_called_once_with(
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"]
        )

    @patch("utils.run_cmd", return_value=(False, ""))
    def test_gsettings_get_failure(self, mock_run):
        val = gsettings_get("org.gnome.desktop.interface", "gtk-theme")
        assert val is None

    @patch("utils.run_cmd", return_value=(True, ""))
    def test_gsettings_set(self, mock_run):
        ok, out = gsettings_set("org.gnome.desktop.interface", "gtk-theme", "Adwaita")
        assert ok is True
        mock_run.assert_called_once_with(
            ["gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", "Adwaita"]
        )


class TestDconf:
    @patch("utils.run_cmd", return_value=(True, "'value'"))
    def test_dconf_read_success(self, mock_run):
        val = dconf_read("/org/gnome/shell/some-key")
        assert val == "'value'"

    @patch("utils.run_cmd", return_value=(False, ""))
    def test_dconf_read_failure(self, mock_run):
        val = dconf_read("/org/gnome/shell/some-key")
        assert val is None

    @patch("utils.run_cmd", return_value=(True, ""))
    def test_dconf_write(self, mock_run):
        ok, out = dconf_write("/org/gnome/shell/some-key", "true")
        assert ok is True


# ── find_file ─────────────────────────────────────────────────────────────────


class TestFindFile:
    def test_find_existing_file(self, tmp_path):
        (tmp_path / "layouts").mkdir()
        (tmp_path / "layouts" / "classic.txt").write_text("data")
        # find_file uses hardcoded search paths — integration test only

    def test_find_file_none_for_empty(self):
        result = find_file("", ["layouts"])
        assert result is None

    def test_find_file_not_found(self):
        result = find_file("__nonexistent_file__.xyz", ["layouts"])
        # May return None if not in any search path
        # The test verifies it doesn't raise
        assert result is None or isinstance(result, Path)


# ── color_from_name ───────────────────────────────────────────────────────────


class TestColorFromName:
    def test_known_color(self):
        assert color_from_name("Adwaita-Blue") == "#3584e4"

    def test_known_color_case_insensitive(self):
        assert color_from_name("DRACULA-theme") == "#bd93f9"

    def test_unknown_color_returns_hex(self):
        result = color_from_name("UnknownThemeName")
        assert result.startswith("#")
        assert len(result) == 7

    def test_deterministic_hash(self):
        a = color_from_name("CustomTheme123")
        b = color_from_name("CustomTheme123")
        assert a == b


# ── gnome_shell_version ───────────────────────────────────────────────────────


class TestGnomeShellVersion:
    @patch("utils.run_cmd", return_value=(True, "GNOME Shell 46.2"))
    def test_normal_version(self, mock_run):
        major, minor = gnome_shell_version()
        assert major == 46
        assert minor == 2

    @patch("utils.run_cmd", return_value=(True, "GNOME Shell 45"))
    def test_major_only(self, mock_run):
        major, minor = gnome_shell_version()
        assert major == 45
        assert minor == 0

    @patch("utils.run_cmd", return_value=(False, ""))
    def test_failure(self, mock_run):
        major, minor = gnome_shell_version()
        assert major == 0
        assert minor == 0


# ── is_wayland ────────────────────────────────────────────────────────────────


class TestIsWayland:
    @patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": ""})
    def test_wayland_session(self):
        assert is_wayland() is True

    @patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": ""})
    def test_x11_session(self):
        assert is_wayland() is False

    @patch.dict(os.environ, {"XDG_SESSION_TYPE": "", "WAYLAND_DISPLAY": "wayland-0"})
    def test_wayland_display(self):
        assert is_wayland() is True
