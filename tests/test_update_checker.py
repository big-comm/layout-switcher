# SPDX-License-Identifier: MIT
"""Tests for update_checker.py — detection of available updates."""

from unittest.mock import patch

from ego_client import ExtensionInfo
from update_checker import UpdateInfo, check_all


def _info(uuid: str, pk: int, shell: str, version: int) -> ExtensionInfo:
    return ExtensionInfo(
        uuid=uuid,
        name=uuid,
        description="",
        creator="",
        pk=pk,
        url="",
        icon_url="",
        screenshot_url="",
        screenshots=[],
        downloads=0,
        rating=0.0,
        rating_count=0,
        shell_version_map={shell: {"version": version}},
        homepage="",
        license="",
        comments=[],
    )


class TestCheckAll:
    def test_detects_update(self):
        installed = [
            {"uuid": "a@x.com", "user": True, "version": "5"},
            {"uuid": "b@y.com", "user": True, "version": "10"},
        ]
        with (
            patch("update_checker.ExtMgr.list_installed", return_value=installed),
            patch("update_checker.gnome_shell_version", return_value=(47, 0)),
            patch(
                "update_checker.ExtMgr.installed_version",
                side_effect=lambda u: 5 if u == "a@x.com" else 10,
            ),
            patch(
                "update_checker.ego_client.info",
                side_effect=lambda u, shell_version: _info(
                    u,
                    pk=1 if u == "a@x.com" else 2,
                    shell="47",
                    version=7 if u == "a@x.com" else 10,
                ),
            ),
            patch(
                "update_checker.ego_client.latest_version",
                side_effect=lambda u, s: 7 if u == "a@x.com" else 10,
            ),
        ):
            updates = check_all()
            assert "a@x.com" in updates
            assert "b@y.com" not in updates
            info = updates["a@x.com"]
            assert isinstance(info, UpdateInfo)
            assert info.current_version == 5
            assert info.latest_version == 7
            assert info.ego_id == 1

    def test_skips_system_extensions(self):
        installed = [{"uuid": "sys@z.com", "user": False, "version": "1"}]
        with (
            patch("update_checker.ExtMgr.list_installed", return_value=installed),
            patch("update_checker.gnome_shell_version", return_value=(47, 0)),
        ):
            updates = check_all()
            assert updates == {}

    def test_skips_when_local_version_unknown(self):
        installed = [{"uuid": "a@x.com", "user": True, "version": ""}]
        with (
            patch("update_checker.ExtMgr.list_installed", return_value=installed),
            patch("update_checker.gnome_shell_version", return_value=(47, 0)),
            patch("update_checker.ExtMgr.installed_version", return_value=0),
        ):
            updates = check_all()
            assert updates == {}

    def test_skips_when_ego_returns_none(self):
        installed = [{"uuid": "a@x.com", "user": True, "version": "5"}]
        with (
            patch("update_checker.ExtMgr.list_installed", return_value=installed),
            patch("update_checker.gnome_shell_version", return_value=(47, 0)),
            patch("update_checker.ExtMgr.installed_version", return_value=5),
            patch("update_checker.ego_client.info", return_value=None),
        ):
            updates = check_all()
            assert updates == {}

    def test_progress_callback(self):
        installed = [
            {"uuid": "a@x.com", "user": True, "version": "1"},
            {"uuid": "b@y.com", "user": True, "version": "1"},
        ]
        calls = []
        with (
            patch("update_checker.ExtMgr.list_installed", return_value=installed),
            patch("update_checker.gnome_shell_version", return_value=(47, 0)),
            patch("update_checker.ExtMgr.installed_version", return_value=1),
            patch("update_checker.ego_client.info", return_value=None),
        ):
            check_all(progress_cb=lambda d, t: calls.append((d, t)))
        assert calls == [(1, 2), (2, 2)]
