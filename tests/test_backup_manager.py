# SPDX-License-Identifier: MIT
"""Tests for backup_manager.py — create, latest, list_all, restore, prune."""

from pathlib import Path
from unittest.mock import patch

import pytest


class TestBackupManager:
    """Tests with mocked subprocess and temp directories."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path):
        self.backup_dir = tmp_path / "backups"
        self.backup_dir.mkdir()
        # Patch constants before importing
        self._patches = [
            patch("constants.BACKUP_DIR", self.backup_dir),
            patch("constants.CONFIG_DIR", tmp_path),
        ]
        for p in self._patches:
            p.start()

        # Import after patching
        import importlib

        import backup_manager

        importlib.reload(backup_manager)
        self.BackupManager = backup_manager.BackupManager

    def teardown_method(self):
        for p in self._patches:
            p.stop()

    @patch("backup_manager.run_cmd")
    @patch("shell_reloader.ShellReloader.reload_all")
    def test_create_success(self, mock_reload, mock_run):
        mock_run.return_value = (True, "[org/gnome/shell]\n" + "x" * 100)
        ok, path = self.BackupManager.create()
        assert ok is True
        assert "backup_" in path
        assert Path(path).exists()

    @patch("backup_manager.run_cmd", return_value=(False, "error"))
    def test_create_failure(self, mock_run):
        ok, msg = self.BackupManager.create()
        assert ok is False
        assert "failed" in msg.lower() or "error" in msg.lower()

    def test_latest_no_backups(self):
        result = self.BackupManager.latest()
        assert result is None

    def test_latest_with_backup(self):
        f = self.backup_dir / "backup_20250101_120000.dconf"
        f.write_text("x" * 100)
        result = self.BackupManager.latest()
        assert result is not None
        assert result.name == f.name

    def test_list_all_sorted(self):
        import time

        for i in range(3):
            f = self.backup_dir / f"backup_2025010{i}_120000.dconf"
            f.write_text("x" * 100)
            time.sleep(0.01)

        results = self.BackupManager.list_all()
        assert len(results) == 3
        # Most recent first
        assert results[0].name > results[-1].name

    @patch("layout_applier.LayoutApplier.load_dconf_safely", return_value=(True, ""))
    def test_restore_success(self, mock_load):
        f = self.backup_dir / "backup_test.dconf"
        f.write_text("[org/gnome/shell]\n" + "x" * 100)
        ok, msg = self.BackupManager.restore(f)
        assert ok is True
        mock_load.assert_called_once()

    def test_restore_missing_file(self):
        ok, msg = self.BackupManager.restore(Path("/nonexistent"))
        assert ok is False

    def test_restore_too_small(self):
        f = self.backup_dir / "backup_small.dconf"
        f.write_text("tiny")
        ok, msg = self.BackupManager.restore(f)
        assert ok is False
        assert "corrupt" in msg.lower() or "small" in msg.lower()

    @patch("backup_manager.run_cmd")
    @patch("shell_reloader.ShellReloader.reload_all")
    def test_prune_keeps_n(self, mock_reload, mock_run):
        mock_run.return_value = (True, "[org/gnome/shell]\n" + "x" * 100)
        # Create 15 backups manually
        import time

        for i in range(15):
            f = self.backup_dir / f"backup_2025010{i:02d}_120000.dconf"
            f.write_text("x" * 100)
            time.sleep(0.01)

        self.BackupManager._prune()
        remaining = list(self.backup_dir.glob("backup_*.dconf"))
        assert len(remaining) <= self.BackupManager.N_KEEP

    def test_prune_drops_corrupt_keeps_valid(self):
        # D1: corrupt (tiny) files must not push valid backups out of the
        # N_KEEP window. _prune keeps the N_KEEP newest VALID backups and
        # removes every corrupt file, even if the corrupt ones are newer.
        import time

        n_keep = self.BackupManager.N_KEEP
        valid = []
        for i in range(n_keep):
            f = self.backup_dir / f"backup_2025020{i:02d}_120000.dconf"
            f.write_text("x" * 200)
            valid.append(f)
            time.sleep(0.01)
        # Newer but corrupt (below MIN_BYTES) — would win the mtime sort.
        for i in range(5):
            f = self.backup_dir / f"backup_2025030{i:02d}_120000.dconf"
            f.write_text("x")
            time.sleep(0.01)

        self.BackupManager._prune()
        remaining = {p.name for p in self.backup_dir.glob("backup_*.dconf")}
        assert remaining == {p.name for p in valid}

    def test_create_no_collision_same_second(self):
        # D3: two backups created within the same second must not collide on
        # the same filename (microsecond suffix makes them unique).
        with (
            patch("backup_manager.run_cmd", return_value=(True, "[org/gnome/shell]\n" + "x" * 100)),
            patch("shell_reloader.ShellReloader.reload_all"),
        ):
            ok1, p1 = self.BackupManager.create()
            ok2, p2 = self.BackupManager.create()
        assert ok1 and ok2
        assert p1 != p2
        assert len(list(self.backup_dir.glob("backup_*.dconf"))) == 2
