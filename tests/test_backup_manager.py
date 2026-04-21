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
    @patch("shell_reloader.ShellReloader.reload_all")
    def test_restore_success(self, mock_reload, mock_load):
        f = self.backup_dir / "backup_test.dconf"
        f.write_text("[org/gnome/shell]\n" + "x" * 100)
        ok, msg = self.BackupManager.restore(f)
        assert ok is True
        mock_load.assert_called_once()
        mock_reload.assert_called_once()

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
