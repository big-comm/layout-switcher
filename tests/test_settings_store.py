# SPDX-License-Identifier: MIT
"""Tests for settings_store.py — Settings JSON persistence."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "usr" / "share" / "layout-switcher"))

import pytest


class TestSettings:
    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path):
        self.config_dir = tmp_path
        self.settings_file = tmp_path / "settings.json"
        self._patches = [
            patch("constants.CONFIG_DIR", self.config_dir),
            patch("constants.SETTINGS_FILE", self.settings_file),
        ]
        for p in self._patches:
            p.start()

        import importlib
        import settings_store
        importlib.reload(settings_store)
        self.Settings = settings_store.Settings

    def teardown_method(self):
        for p in self._patches:
            p.stop()

    def test_get_default(self):
        s = self.Settings()
        assert s.get("nonexistent") is None
        assert s.get("nonexistent", 42) == 42

    def test_set_and_get(self):
        s = self.Settings()
        s.set("intro_shown", True)
        assert s.get("intro_shown") is True

    def test_persistence(self):
        s1 = self.Settings()
        s1.set("foo", "bar")

        s2 = self.Settings()
        assert s2.get("foo") == "bar"

    def test_atomic_write(self):
        s = self.Settings()
        s.set("key", "value")
        assert self.settings_file.exists()
        data = json.loads(self.settings_file.read_text())
        assert data["key"] == "value"
        # No temp file left behind
        assert not self.settings_file.with_suffix(".tmp").exists()

    def test_corrupted_file(self):
        self.settings_file.write_text("not json")
        s = self.Settings()
        assert s.get("anything") is None

    def test_delete(self):
        s = self.Settings()
        s.set("to_delete", True)
        assert s.get("to_delete") is True
        s.delete("to_delete")
        assert s.get("to_delete") is None
