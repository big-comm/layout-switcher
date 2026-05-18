# SPDX-License-Identifier: MIT
"""Tests for google_fonts.py."""

import urllib.error
from unittest.mock import patch

import google_fonts


class FakeResp:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self, size=-1):
        if size is None or size < 0:
            return self._body
        return self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_install_for_user_downloads_css_urls_and_refreshes_cache(tmp_path):
    css = b"""
@font-face {
  font-family: 'Roboto';
  src: url('https://fonts.gstatic.com/s/roboto/v1/roboto.ttf') format('truetype');
}
"""

    def fake_urlopen(req, timeout=0):
        url = req.full_url
        if "fonts.googleapis.com" in url:
            return FakeResp(css)
        if "fonts.gstatic.com" in url:
            return FakeResp(b"fake-font")
        raise AssertionError(url)

    with (
        patch("google_fonts.USER_FONT_DIR", tmp_path / "fonts"),
        patch("google_fonts.urllib.request.urlopen", side_effect=fake_urlopen),
        patch("google_fonts.run_cmd", return_value=(True, "")) as mock_run,
    ):
        ok, info = google_fonts.install_for_user("Roboto")

    assert ok is True
    assert (tmp_path / "fonts" / "roboto" / "roboto.ttf").read_bytes() == b"fake-font"
    assert mock_run.call_args.args[0][0] == "fc-cache"


def test_install_for_user_reports_network_errors(tmp_path):
    with (
        patch("google_fonts.USER_FONT_DIR", tmp_path / "fonts"),
        patch(
            "google_fonts.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ),
    ):
        ok, info = google_fonts.install_for_user("Roboto")

    assert ok is False
    assert info == "network"


def test_search_popular_filters_bundled_families():
    assert google_fonts.search_popular("Roboto", limit=5)[0][0] == "Roboto"
    assert google_fonts.search_popular("Definitely Unknown Font") == []


def test_load_catalog_fetches_and_sorts_google_metadata(tmp_path):
    payload = b""")]}'
{
  "familyMetadataList": [
    {"family": "Later Font", "category": "Serif", "popularity": 20},
    {"family": "Top Font", "category": "Sans Serif", "popularity": 1}
  ]
}
"""

    def fake_urlopen(req, timeout=0):
        assert "fonts.google.com/metadata/fonts" in req.full_url
        return FakeResp(payload)

    with (
        patch("google_fonts.CACHE_FILE", tmp_path / "google-fonts-catalog.json"),
        patch("google_fonts.urllib.request.urlopen", side_effect=fake_urlopen),
    ):
        ok, entries, err = google_fonts.load_catalog(force_refresh=True)

    assert ok is True
    assert err == ""
    assert [entry.family for entry in entries] == ["Top Font", "Later Font"]
    assert entries[0].category == "sans-serif"


def test_load_catalog_falls_back_when_offline_without_cache(tmp_path):
    with (
        patch("google_fonts.CACHE_FILE", tmp_path / "google-fonts-catalog.json"),
        patch(
            "google_fonts.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ),
    ):
        ok, entries, err = google_fonts.load_catalog(force_refresh=True)

    assert ok is False
    assert err == "network"
    assert entries[0].family == "Roboto"
