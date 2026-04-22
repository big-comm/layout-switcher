# SPDX-License-Identifier: MIT
"""Tests for snapshot_manager.py — per-layout user snapshots."""

from unittest.mock import patch

import pytest


class TestSnapshotManager:
    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path):
        self.snapshots_dir = tmp_path / "layout-snapshots"
        self._patches = [
            patch("constants.CONFIG_DIR", tmp_path),
        ]
        for p in self._patches:
            p.start()
        import importlib

        import snapshot_manager

        importlib.reload(snapshot_manager)
        self.SnapshotManager = snapshot_manager.SnapshotManager
        self.SNAPSHOTS_DIR = snapshot_manager.SNAPSHOTS_DIR

    def teardown_method(self):
        for p in self._patches:
            p.stop()

    @patch("snapshot_manager.run_cmd", return_value=(True, "[/]\n" + "x" * 200))
    def test_save_creates_snapshot(self, _mock_run):
        ok, path = self.SnapshotManager.save("biggnome")
        assert ok is True
        assert "biggnome" in path
        assert self.SNAPSHOTS_DIR.exists()
        assert (self.SNAPSHOTS_DIR / "biggnome.dconf").exists()

    @patch("snapshot_manager.run_cmd", return_value=(False, "dconf error"))
    def test_save_fails_on_dump_error(self, _mock_run):
        ok, msg = self.SnapshotManager.save("classic")
        assert ok is False
        assert "failed" in msg.lower() or "error" in msg.lower()

    @patch("snapshot_manager.run_cmd", return_value=(True, "tiny"))
    def test_save_rejects_empty_dump(self, _mock_run):
        ok, msg = self.SnapshotManager.save("modern")
        assert ok is False

    def test_save_rejects_empty_id(self):
        ok, msg = self.SnapshotManager.save("")
        assert ok is False

    def test_load_returns_none_when_absent(self):
        assert self.SnapshotManager.load("nonexistent") is None
        assert self.SnapshotManager.has("nonexistent") is False

    def test_load_returns_path_when_present(self):
        self.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        f = self.SNAPSHOTS_DIR / "yaru.dconf"
        f.write_text("[/]\n" + "x" * 200)

        result = self.SnapshotManager.load("yaru")
        assert result is not None
        assert result.name == "yaru.dconf"
        assert self.SnapshotManager.has("yaru") is True

    def test_load_rejects_tiny_snapshot(self):
        self.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        f = self.SNAPSHOTS_DIR / "classic.dconf"
        f.write_text("tiny")
        assert self.SnapshotManager.load("classic") is None
        assert self.SnapshotManager.has("classic") is False

    def test_read_returns_contents(self):
        self.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        f = self.SNAPSHOTS_DIR / "minimal.dconf"
        content = "[/]\n" + "y" * 200
        f.write_text(content)
        assert self.SnapshotManager.read("minimal") == content

    def test_read_returns_none_when_absent(self):
        assert self.SnapshotManager.read("nothing") is None

    def test_delete_removes_snapshot(self):
        self.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        f = self.SNAPSHOTS_DIR / "biggnome.dconf"
        f.write_text("[/]\n" + "x" * 200)
        assert self.SnapshotManager.delete("biggnome") is True
        assert not f.exists()

    def test_delete_is_idempotent(self):
        assert self.SnapshotManager.delete("nonexistent") is True

    def test_list_all_sorted_newest_first(self):
        import time

        self.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        names = ["a", "b", "c"]
        for n in names:
            (self.SNAPSHOTS_DIR / f"{n}.dconf").write_text("x" * 200)
            time.sleep(0.01)

        result = self.SnapshotManager.list_all()
        assert len(result) == 3
        assert result[0].stat().st_mtime >= result[-1].stat().st_mtime

    def test_path_for_sanitizes_id(self):
        # Caracteres perigosos sao removidos
        p = self.SnapshotManager._path_for("../etc/passwd")
        assert "/" not in p.name
        assert ".." not in p.name
