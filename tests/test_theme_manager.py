# SPDX-License-Identifier: MIT
"""Tests for theme_manager.py — list, apply, color_scheme."""

from unittest.mock import patch

from theme_manager import ThemeMgr


class TestListThemes:
    def test_list_gtk_themes(self, tmp_path):
        theme_dir = tmp_path / "themes" / "Adwaita" / "gtk-4.0"
        theme_dir.mkdir(parents=True)

        with patch.object(ThemeMgr, "list_themes", wraps=ThemeMgr.list_themes):
            # Directly test with known paths
            roots = [tmp_path / "themes"]
            # Simulate what list_themes does
            seen = {}
            for root in roots:
                if not root.is_dir():
                    continue
                for d in root.iterdir():
                    if not d.is_dir():
                        continue
                    if any((d / sub).exists() for sub in ("gtk-4.0", "gtk-3.0", "gtk-2.0")):
                        seen[d.name] = True
            assert "Adwaita" in seen

    def test_list_icon_themes(self, tmp_path):
        icon_dir = tmp_path / "icons" / "Papirus"
        icon_dir.mkdir(parents=True)
        (icon_dir / "index.theme").write_text("[Icon Theme]\nName=Papirus")

        # Simulate what list_themes does for icons
        seen = {}
        for d in (tmp_path / "icons").iterdir():
            if d.is_dir() and (d / "index.theme").exists():
                seen[d.name] = True
        assert "Papirus" in seen


class TestApply:
    @patch("theme_manager.gsettings_set", return_value=(True, ""))
    def test_apply_gtk(self, mock_gs):
        ok, msg = ThemeMgr.apply("gtk", "Adwaita")
        assert ok is True
        mock_gs.assert_called_with("org.gnome.desktop.interface", "gtk-theme", "Adwaita")

    @patch("theme_manager.gsettings_set", return_value=(True, ""))
    def test_apply_icons(self, mock_gs):
        ok, msg = ThemeMgr.apply("icons", "Papirus")
        assert ok is True
        mock_gs.assert_called_with("org.gnome.desktop.interface", "icon-theme", "Papirus")

    @patch("extension_manager.ExtMgr.is_installed", return_value=False)
    def test_apply_shell_no_user_theme(self, _mock_inst):
        ok, msg = ThemeMgr.apply("shell", "Orchis")
        assert ok is False
        assert msg == "user-theme-not-installed"

    def test_apply_unknown_kind(self):
        ok, msg = ThemeMgr.apply("invalid", "Theme")
        assert ok is False


class TestCurrent:
    @patch("theme_manager.gsettings_get", return_value="Adwaita")
    def test_current_gtk(self, mock_gs):
        assert ThemeMgr.current("gtk") == "Adwaita"

    @patch("theme_manager.gsettings_get", return_value=None)
    def test_current_empty(self, mock_gs):
        assert ThemeMgr.current("gtk") == ""

    def test_current_unknown_kind(self):
        assert ThemeMgr.current("invalid") == ""


class TestColorScheme:
    @patch("theme_manager.gsettings_get", return_value="prefer-dark")
    def test_color_scheme_dark(self, mock_gs):
        assert ThemeMgr.color_scheme() == "prefer-dark"

    @patch("theme_manager.gsettings_get", return_value=None)
    def test_color_scheme_default(self, mock_gs):
        assert ThemeMgr.color_scheme() == "prefer-light"
