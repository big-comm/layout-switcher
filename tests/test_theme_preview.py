# SPDX-License-Identifier: MIT
"""Tests for theme_preview.py — folder icon discovery and color extraction."""

from unittest.mock import patch

import theme_preview


class TestFindFolderIcon:
    def test_none_for_empty_name(self):
        assert theme_preview.find_folder_icon("") is None

    def test_returns_canonical_scalable_path(self, tmp_path):
        theme_dir = tmp_path / "MyIcons"
        (theme_dir / "scalable" / "places").mkdir(parents=True)
        folder_svg = theme_dir / "scalable" / "places" / "folder.svg"
        folder_svg.write_text("<svg/>")

        with patch.object(theme_preview, "_ICON_ROOTS", [tmp_path]):
            result = theme_preview.find_folder_icon("MyIcons")
            assert result == folder_svg

    def test_prefers_svg_over_png(self, tmp_path):
        theme_dir = tmp_path / "MixTheme"
        (theme_dir / "scalable" / "places").mkdir(parents=True)
        (theme_dir / "48x48" / "places").mkdir(parents=True)
        svg = theme_dir / "scalable" / "places" / "folder.svg"
        png = theme_dir / "48x48" / "places" / "folder.png"
        svg.write_text("<svg/>")
        png.write_text("PNG")

        with patch.object(theme_preview, "_ICON_ROOTS", [tmp_path]):
            # SVG esta antes na lista _FOLDER_REL_PATHS
            result = theme_preview.find_folder_icon("MixTheme")
            assert result == svg

    def test_falls_back_to_glob(self, tmp_path):
        theme_dir = tmp_path / "WeirdTheme"
        deep = theme_dir / "weird" / "nested"
        deep.mkdir(parents=True)
        folder = deep / "folder.svg"
        folder.write_text("<svg/>")

        with patch.object(theme_preview, "_ICON_ROOTS", [tmp_path]):
            result = theme_preview.find_folder_icon("WeirdTheme")
            assert result == folder

    def test_returns_none_for_missing_theme(self, tmp_path):
        with patch.object(theme_preview, "_ICON_ROOTS", [tmp_path]):
            assert theme_preview.find_folder_icon("Nonexistent") is None


class TestExtractThemeColor:
    def test_extracts_accent_bg_color(self, tmp_path):
        theme_dir = tmp_path / "MyGTK"
        gtk4 = theme_dir / "gtk-4.0"
        gtk4.mkdir(parents=True)
        (gtk4 / "gtk.css").write_text(
            "@define-color accent_bg_color #3584e4;\n@define-color window_bg_color #ffffff;\n"
        )

        with patch.object(theme_preview, "_THEME_ROOTS", [tmp_path]):
            assert theme_preview.extract_theme_color("MyGTK", "gtk") == "#3584e4"

    def test_normalizes_short_hex(self, tmp_path):
        theme_dir = tmp_path / "ShortHex"
        gtk4 = theme_dir / "gtk-4.0"
        gtk4.mkdir(parents=True)
        (gtk4 / "gtk.css").write_text("@define-color accent_color #abc;\n")

        with patch.object(theme_preview, "_THEME_ROOTS", [tmp_path]):
            assert theme_preview.extract_theme_color("ShortHex", "gtk") == "#aabbcc"

    def test_returns_none_for_rgba_value(self, tmp_path):
        """Nao resolvemos rgba()/mix()/referencias — fica para fallback."""
        theme_dir = tmp_path / "RgbaTheme"
        gtk4 = theme_dir / "gtk-4.0"
        gtk4.mkdir(parents=True)
        (gtk4 / "gtk.css").write_text("@define-color accent_bg_color rgba(53, 132, 228, 1);\n")

        with patch.object(theme_preview, "_THEME_ROOTS", [tmp_path]):
            assert theme_preview.extract_theme_color("RgbaTheme", "gtk") is None

    def test_returns_none_for_variable_reference(self, tmp_path):
        theme_dir = tmp_path / "VarRef"
        gtk4 = theme_dir / "gtk-4.0"
        gtk4.mkdir(parents=True)
        (gtk4 / "gtk.css").write_text("@define-color accent_bg_color @primary_accent;\n")

        with patch.object(theme_preview, "_THEME_ROOTS", [tmp_path]):
            assert theme_preview.extract_theme_color("VarRef", "gtk") is None

    def test_tries_gtk3_when_gtk4_absent(self, tmp_path):
        theme_dir = tmp_path / "Legacy"
        gtk3 = theme_dir / "gtk-3.0"
        gtk3.mkdir(parents=True)
        (gtk3 / "gtk.css").write_text("@define-color accent_color #ff00ff;\n")

        with patch.object(theme_preview, "_THEME_ROOTS", [tmp_path]):
            assert theme_preview.extract_theme_color("Legacy", "gtk") == "#ff00ff"

    def test_unknown_kind_returns_none(self):
        assert theme_preview.extract_theme_color("AnyTheme", "weird") is None

    def test_shell_theme_css(self, tmp_path):
        theme_dir = tmp_path / "ShellT"
        shell_dir = theme_dir / "gnome-shell"
        shell_dir.mkdir(parents=True)
        (shell_dir / "gnome-shell.css").write_text(
            "@define-color theme_selected_bg_color #1c71d8;\n"
        )

        with patch.object(theme_preview, "_THEME_ROOTS", [tmp_path]):
            assert theme_preview.extract_theme_color("ShellT", "shell") == "#1c71d8"
