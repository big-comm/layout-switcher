# SPDX-License-Identifier: MIT
"""Tests for extension_manager.py — enabled_list, is_installed, install, remove."""

from unittest.mock import patch

from extension_manager import ExtMgr


class TestEnabledList:
    @patch(
        "extension_manager.gsettings_get",
        return_value="['ext-a@foo.com', 'ext-b@bar.com']",
    )
    def test_normal_list(self, mock_gs):
        result = ExtMgr.enabled_list()
        assert result == ["ext-a@foo.com", "ext-b@bar.com"]

    @patch("extension_manager.gsettings_get", return_value="@as []")
    def test_empty_gvariant(self, mock_gs):
        result = ExtMgr.enabled_list()
        assert result == []

    @patch("extension_manager.gsettings_get", return_value="[]")
    def test_empty_brackets(self, mock_gs):
        result = ExtMgr.enabled_list()
        assert result == []

    @patch("extension_manager.gsettings_get", return_value=None)
    def test_none(self, mock_gs):
        result = ExtMgr.enabled_list()
        assert result == []

    @patch("extension_manager.gsettings_get", return_value="")
    def test_empty_string(self, mock_gs):
        result = ExtMgr.enabled_list()
        assert result == []

    @patch("extension_manager.gsettings_get", return_value="@as[]")
    def test_gvariant_no_space(self, mock_gs):
        result = ExtMgr.enabled_list()
        assert result == []


class TestIsInstalled:
    def test_user_dir(self, tmp_path):
        ext_dir = tmp_path / "test-ext@foo.com"
        ext_dir.mkdir()
        with (
            patch("extension_manager.EXT_USER_DIR", tmp_path),
            patch("extension_manager.EXT_SYS_DIR", tmp_path / "sys"),
        ):
            assert ExtMgr.is_installed("test-ext@foo.com") is True

    def test_not_installed(self, tmp_path):
        with (
            patch("extension_manager.EXT_USER_DIR", tmp_path),
            patch("extension_manager.EXT_SYS_DIR", tmp_path / "sys"),
        ):
            assert ExtMgr.is_installed("nonexistent@foo.com") is False


class TestIsEnabled:
    @patch("extension_manager.ExtMgr.enabled_list", return_value=["ext-a@foo.com"])
    def test_enabled(self, _mock_el):
        assert ExtMgr.is_enabled("ext-a@foo.com") is True

    @patch("extension_manager.ExtMgr.enabled_list", return_value=["ext-a@foo.com"])
    def test_not_enabled(self, _mock_el):
        assert ExtMgr.is_enabled("ext-b@bar.com") is False


class TestAllGloballyEnabled:
    @patch("extension_manager.dconf_read", return_value=None)
    def test_default_enabled(self, _mock_read):
        assert ExtMgr.all_globally_enabled() is True

    @patch("extension_manager.dconf_read", return_value="true")
    def test_disabled(self, _mock_read):
        assert ExtMgr.all_globally_enabled() is False

    @patch("extension_manager.dconf_read", return_value="false")
    def test_explicitly_enabled(self, _mock_read):
        assert ExtMgr.all_globally_enabled() is True


class TestListInstalled:
    def test_empty_dirs(self, tmp_path):
        user_dir = tmp_path / "user"
        sys_dir = tmp_path / "sys"
        user_dir.mkdir()
        sys_dir.mkdir()
        with (
            patch("extension_manager.EXT_USER_DIR", user_dir),
            patch("extension_manager.EXT_SYS_DIR", sys_dir),
            patch("extension_manager.ExtMgr.enabled_list", return_value=[]),
        ):
            result = ExtMgr.list_installed()
            assert result == []

    def test_with_extensions(self, tmp_path):
        user_dir = tmp_path / "user"
        sys_dir = tmp_path / "sys"
        user_dir.mkdir()
        sys_dir.mkdir()

        ext_dir = user_dir / "test-ext@foo.com"
        ext_dir.mkdir()
        meta = ext_dir / "metadata.json"
        meta.write_text('{"uuid": "test-ext@foo.com", "name": "Test Ext"}')

        with (
            patch("extension_manager.EXT_USER_DIR", user_dir),
            patch("extension_manager.EXT_SYS_DIR", sys_dir),
            patch(
                "extension_manager.ExtMgr.enabled_list",
                return_value=["test-ext@foo.com"],
            ),
        ):
            result = ExtMgr.list_installed()
            assert len(result) == 1
            assert result[0]["uuid"] == "test-ext@foo.com"
            assert result[0]["name"] == "Test Ext"
            assert result[0]["enabled"] is True
            assert result[0]["user"] is True

    def test_malformed_metadata(self, tmp_path):
        user_dir = tmp_path / "user"
        sys_dir = tmp_path / "sys"
        user_dir.mkdir()
        sys_dir.mkdir()

        ext_dir = user_dir / "broken-ext@foo.com"
        ext_dir.mkdir()
        meta = ext_dir / "metadata.json"
        meta.write_text("not valid json")

        with (
            patch("extension_manager.EXT_USER_DIR", user_dir),
            patch("extension_manager.EXT_SYS_DIR", sys_dir),
            patch("extension_manager.ExtMgr.enabled_list", return_value=[]),
        ):
            result = ExtMgr.list_installed()
            assert len(result) == 1
            assert result[0]["uuid"] == "broken-ext@foo.com"


class TestInstalledVersion:
    def test_reads_int_version(self, tmp_path):
        ext_dir = tmp_path / "ext-a@foo.com"
        ext_dir.mkdir()
        (ext_dir / "metadata.json").write_text('{"version": 7}')
        with (
            patch("extension_manager.EXT_USER_DIR", tmp_path),
            patch("extension_manager.EXT_SYS_DIR", tmp_path / "sys"),
        ):
            assert ExtMgr.installed_version("ext-a@foo.com") == 7

    def test_reads_string_version(self, tmp_path):
        ext_dir = tmp_path / "ext-b@foo.com"
        ext_dir.mkdir()
        (ext_dir / "metadata.json").write_text('{"version": "12"}')
        with (
            patch("extension_manager.EXT_USER_DIR", tmp_path),
            patch("extension_manager.EXT_SYS_DIR", tmp_path / "sys"),
        ):
            assert ExtMgr.installed_version("ext-b@foo.com") == 12

    def test_no_metadata_returns_zero(self, tmp_path):
        ext_dir = tmp_path / "ext-c@foo.com"
        ext_dir.mkdir()
        with (
            patch("extension_manager.EXT_USER_DIR", tmp_path),
            patch("extension_manager.EXT_SYS_DIR", tmp_path / "sys"),
        ):
            assert ExtMgr.installed_version("ext-c@foo.com") == 0

    def test_malformed_metadata_returns_zero(self, tmp_path):
        ext_dir = tmp_path / "ext-d@foo.com"
        ext_dir.mkdir()
        (ext_dir / "metadata.json").write_text("not json")
        with (
            patch("extension_manager.EXT_USER_DIR", tmp_path),
            patch("extension_manager.EXT_SYS_DIR", tmp_path / "sys"),
        ):
            assert ExtMgr.installed_version("ext-d@foo.com") == 0


class TestUpdate:
    def test_calls_install_and_reenables(self):
        with (
            patch("extension_manager.ExtMgr.is_enabled", return_value=True),
            patch(
                "extension_manager.ExtMgr.install",
                return_value=(True, "gnome-extensions"),
            ),
            patch(
                "shell_reloader.ShellReloader.apply_extension_state",
                return_value=(True, ""),
            ) as mock_apply,
        ):
            ok, method = ExtMgr.update("uuid@x.com", ego_id=42)
            assert ok is True
            assert method == "gnome-extensions"
            mock_apply.assert_called_once_with("uuid@x.com", True)

    def test_no_reenable_when_disabled(self):
        with (
            patch("extension_manager.ExtMgr.is_enabled", return_value=False),
            patch("extension_manager.ExtMgr.install", return_value=(True, "ego-download")),
            patch("shell_reloader.ShellReloader.apply_extension_state") as mock_apply,
        ):
            ok, method = ExtMgr.update("uuid@x.com", ego_id=42)
            assert ok is True
            mock_apply.assert_not_called()

    def test_failure_propagates(self):
        with (
            patch("extension_manager.ExtMgr.is_enabled", return_value=True),
            patch(
                "extension_manager.ExtMgr.install",
                return_value=(False, "no method"),
            ),
        ):
            ok, msg = ExtMgr.update("uuid@x.com", ego_id=42)
            assert ok is False
            assert "no method" in msg


class TestRemove:
    def test_remove_user_extension(self, tmp_path):
        ext_dir = tmp_path / "test-ext@foo.com"
        ext_dir.mkdir()
        (ext_dir / "metadata.json").write_text("{}")

        with (
            patch("extension_manager.EXT_USER_DIR", tmp_path),
            patch(
                "shell_reloader.ShellReloader.apply_extension_state",
                return_value=(True, ""),
            ),
            patch("shell_reloader.ShellReloader.reload_all"),
        ):
            ok, msg = ExtMgr.remove("test-ext@foo.com")
            assert ok is True
            assert not ext_dir.exists()

    def test_remove_nonexistent(self, tmp_path):
        with patch("extension_manager.EXT_USER_DIR", tmp_path):
            ok, msg = ExtMgr.remove("nonexistent@foo.com")
            assert ok is False
