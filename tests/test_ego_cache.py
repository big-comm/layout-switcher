# SPDX-License-Identifier: MIT
"""Tests for ego_cache.py — JSON TTL + thumbs LRU eviction."""

import time
from unittest.mock import patch

import ego_cache


class TestJsonCache:
    def test_put_and_get_roundtrip(self, tmp_path):
        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch("ego_cache.EGO_THUMBS_DIR", tmp_path / "thumbs"),
        ):
            ego_cache.json_put("info", "uuid@x.com|47", {"name": "X", "version": 1})
            got = ego_cache.json_get("info", "uuid@x.com|47", ttl_seconds=60)
            assert got == {"name": "X", "version": 1}

    def test_get_missing_returns_none(self, tmp_path):
        with patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"):
            assert ego_cache.json_get("info", "nada", ttl_seconds=60) is None

    def test_expired_entry_returns_none(self, tmp_path):
        with patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"):
            ego_cache.json_put("info", "k", {"v": 1})
            # mtime no passado distante
            path = (tmp_path / "ego" / "info").iterdir().__next__()
            old = time.time() - 7200
            import os

            os.utime(path, (old, old))
            assert ego_cache.json_get("info", "k", ttl_seconds=60) is None

    def test_invalidate(self, tmp_path):
        with patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"):
            ego_cache.json_put("search", "q", {"a": 1})
            assert ego_cache.json_get("search", "q", ttl_seconds=60) == {"a": 1}
            ego_cache.json_invalidate("search", "q")
            assert ego_cache.json_get("search", "q", ttl_seconds=60) is None

    def test_corrupted_file_returns_none(self, tmp_path):
        with patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"):
            ego_cache.json_put("info", "k", {"v": 1})
            path = (tmp_path / "ego" / "info").iterdir().__next__()
            path.write_text("not valid json")
            assert ego_cache.json_get("info", "k", ttl_seconds=60) is None


class TestThumbsCache:
    def test_put_and_get_roundtrip(self, tmp_path):
        with patch("ego_cache.EGO_THUMBS_DIR", tmp_path / "thumbs"):
            data = b"\x89PNG\r\n\x1a\n" + b"x" * 100
            saved = ego_cache.thumb_put("https://e.gnome.org/s/1.png", data)
            assert saved is not None
            assert saved.exists()
            got = ego_cache.thumb_get("https://e.gnome.org/s/1.png")
            assert got == saved

    def test_get_missing_returns_none(self, tmp_path):
        with patch("ego_cache.EGO_THUMBS_DIR", tmp_path / "thumbs"):
            assert ego_cache.thumb_get("nope") is None

    def test_lru_eviction(self, tmp_path):
        # cap pequeno → 200 bytes; grava 3 arquivos de 100 bytes cada → 1 sai
        with (
            patch("ego_cache.EGO_THUMBS_DIR", tmp_path / "thumbs"),
            patch("ego_cache.EGO_THUMBS_MAX_BYTES", 200),
        ):
            ego_cache.thumb_put("u1", b"a" * 100)
            time.sleep(0.02)
            ego_cache.thumb_put("u2", b"b" * 100)
            time.sleep(0.02)
            ego_cache.thumb_put("u3", b"c" * 100)
            # u1 deve ter sido removido (mais antigo)
            assert ego_cache.thumb_get("u1") is None
            assert ego_cache.thumb_get("u2") is not None
            assert ego_cache.thumb_get("u3") is not None

    def test_empty_data_not_stored(self, tmp_path):
        with patch("ego_cache.EGO_THUMBS_DIR", tmp_path / "thumbs"):
            assert ego_cache.thumb_put("u", b"") is None

    def test_clear_all_wipes(self, tmp_path):
        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch("ego_cache.EGO_THUMBS_DIR", tmp_path / "thumbs"),
        ):
            ego_cache.json_put("info", "k", {"v": 1})
            ego_cache.thumb_put("u", b"abc")
            ego_cache.clear_all()
            assert ego_cache.json_get("info", "k", ttl_seconds=60) is None
            assert ego_cache.thumb_get("u") is None
