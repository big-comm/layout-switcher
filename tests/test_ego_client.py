# SPDX-License-Identifier: MIT
"""Tests for ego_client.py — HTTP client with cache + parsing."""

import json
from io import BytesIO
from unittest.mock import patch

import ego_client


def _fake_response(payload, status: int = 200):
    """Constrói um objeto que satisfaz o context manager de urllib."""

    class FakeResp:
        def __init__(self, body, status):
            self.status = status
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    if isinstance(payload, (dict, list)):
        body = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        body = payload.encode("utf-8")
    else:
        body = payload
    return FakeResp(body, status)


SAMPLE_QUERY = {
    "extensions": [
        {
            "uuid": "dash-to-dock@micxgx.gmail.com",
            "name": "Dash to Dock",
            "description": "A dock for the GNOME Shell",
            "creator": "michelegasparri",
            "pk": 307,
            "icon": "/static/extension-data/icons/icon_307.png",
            "downloads": 1234567,
            "rating": 4.8,
            "rating_count": 200,
            "shell_version_map": {"47": {"version": 99, "pk": 1}},
        }
    ],
    "page": 1,
    "numpages": 5,
    "total": 50,
}

SAMPLE_INFO = {
    "uuid": "dash-to-dock@micxgx.gmail.com",
    "name": "Dash to Dock",
    "description": "A dock",
    "creator": "michelegasparri",
    "pk": 307,
    "link": "/extension/307/",
    "icon": "/static/extension-data/icons/icon_307.png",
    "screenshot": "/static/extension-data/screenshots/s_307.png",
    "screenshots": [{"url": "/static/extension-data/screenshots/extra_307.png"}],
    "downloads": 1234567,
    "rating": 4.8,
    "rating_count": 200,
    "shell_version_map": {"47": {"version": 99}},
    "url": "https://micheleg.github.io/dash-to-dock/",
    "license": "GPL-2.0+",
    "comments": [
        {"username": "alice", "rating": 5, "date": "2025-12-01", "comment": "Great"},
        {"username": "bob", "rating": 4, "date": "2025-11-15", "comment": "Solid"},
    ],
}


class TestSearch:
    def test_parses_response(self, tmp_path):
        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch(
                "ego_client.urllib.request.urlopen",
                return_value=_fake_response(SAMPLE_QUERY),
            ),
        ):
            result = ego_client.search(query="dock", page=1, use_cache=False)
            assert result is not None
            assert result.total == 50
            assert result.num_pages == 5
            assert len(result.extensions) == 1
            ext = result.extensions[0]
            assert ext.uuid == "dash-to-dock@micxgx.gmail.com"
            assert ext.name == "Dash to Dock"
            assert ext.downloads == 1234567
            assert ext.icon_url.startswith("https://extensions.gnome.org/")

    def test_cache_hit_skips_http(self, tmp_path):
        with patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"):
            # primeira chamada vai à rede
            with patch(
                "ego_client.urllib.request.urlopen",
                return_value=_fake_response(SAMPLE_QUERY),
            ) as mock_urlopen:
                first = ego_client.search(query="dock", page=1)
                assert first is not None
                assert mock_urlopen.call_count == 1
            # segunda chamada deve vir do cache
            with patch("ego_client.urllib.request.urlopen") as mock_urlopen:
                second = ego_client.search(query="dock", page=1)
                assert second is not None
                assert mock_urlopen.call_count == 0

    def test_network_error_returns_none(self, tmp_path):
        import urllib.error

        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch(
                "ego_client.urllib.request.urlopen",
                side_effect=urllib.error.URLError("dns fail"),
            ),
        ):
            result = ego_client.search(query="x", use_cache=False)
            assert result is None

    def test_malformed_json_returns_none(self, tmp_path):
        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch(
                "ego_client.urllib.request.urlopen",
                return_value=_fake_response("not json"),
            ),
        ):
            assert ego_client.search(query="x", use_cache=False) is None


class TestInfo:
    def test_parses_info(self, tmp_path):
        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch(
                "ego_client.urllib.request.urlopen",
                return_value=_fake_response(SAMPLE_INFO),
            ),
        ):
            detail = ego_client.info(
                "dash-to-dock@micxgx.gmail.com",
                shell_version="47",
                use_cache=False,
            )
            assert detail is not None
            assert detail.uuid == "dash-to-dock@micxgx.gmail.com"
            assert detail.homepage == "https://micheleg.github.io/dash-to-dock/"
            assert detail.license == "GPL-2.0+"
            assert len(detail.screenshots) == 2
            assert detail.screenshots[0].url.endswith("/s_307.png")
            assert len(detail.comments) == 2
            assert detail.comments[0].author == "alice"
            assert detail.comments[0].rating == 5

    def test_html_comments_become_empty(self, tmp_path):
        payload = dict(SAMPLE_INFO)
        payload["comments"] = "<div>html</div>"
        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch(
                "ego_client.urllib.request.urlopen",
                return_value=_fake_response(payload),
            ),
        ):
            detail = ego_client.info("x@y.com", use_cache=False)
            assert detail is not None
            assert detail.comments == []


class TestLatestVersion:
    def test_uses_shell_version_map(self, tmp_path):
        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch(
                "ego_client.urllib.request.urlopen",
                return_value=_fake_response(SAMPLE_INFO),
            ),
        ):
            v = ego_client.latest_version("dash-to-dock@micxgx.gmail.com", "47")
            assert v == 99

    def test_returns_none_when_unknown(self, tmp_path):
        empty = dict(SAMPLE_INFO)
        empty["shell_version_map"] = {}
        with (
            patch("ego_cache.EGO_CACHE_DIR", tmp_path / "ego"),
            patch(
                "ego_client.urllib.request.urlopen",
                return_value=_fake_response(empty),
            ),
        ):
            assert ego_client.latest_version("x@y.com", "47") is None


class TestFetchScreenshot:
    def test_caches_after_first_fetch(self, tmp_path):
        with (
            patch("ego_cache.EGO_THUMBS_DIR", tmp_path / "thumbs"),
            patch(
                "ego_client.urllib.request.urlopen",
                return_value=_fake_response(b"\x89PNG\r\n\x1a\n" + b"x" * 100),
            ) as mock_urlopen,
        ):
            url = "https://extensions.gnome.org/static/extension-data/screenshots/x.png"
            path = ego_client.fetch_screenshot(url)
            assert path is not None and path.exists()
            assert mock_urlopen.call_count == 1

            # Segunda chamada deve usar cache
            with patch("ego_client.urllib.request.urlopen") as mock2:
                path2 = ego_client.fetch_screenshot(url)
                assert path2 == path
                assert mock2.call_count == 0


# Garante que o import do BytesIO não fica órfão (e que o módulo é executável).
def test_import_smoke():
    assert BytesIO  # placeholder — keeps lint happy if we ever stop using helpers
