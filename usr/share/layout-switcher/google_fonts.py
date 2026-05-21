# SPDX-License-Identifier: MIT
"""
google_fonts.py - Minimal Google Fonts installer.

Uses the public CSS2 endpoint to resolve a family to font file URLs, then
installs those files for the current user under ~/.local/share/fonts.

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from constants import CACHE_DIR
from utils import run_cmd

log = logging.getLogger("layout-switcher")

CSS2_URL = "https://fonts.googleapis.com/css2"
CATALOG_URL = "https://fonts.google.com/metadata/fonts"
USER_FONT_DIR = Path.home() / ".local" / "share" / "fonts" / "layout-switcher" / "google-fonts"
CACHE_FILE = CACHE_DIR / "google-fonts-catalog.json"

HTTP_TIMEOUT = 20
MAX_CSS_BYTES = 1024 * 1024
MAX_CATALOG_BYTES = 12 * 1024 * 1024
MAX_FONT_BYTES = 50 * 1024 * 1024
CATALOG_CACHE_TTL = 60 * 60 * 24 * 7

_FONT_URL_RE = re.compile(r"url\(['\"]?(https://fonts\.gstatic\.com/[^)'\"\s]+)['\"]?\)")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


POPULAR_GOOGLE_FONTS: List[Tuple[str, str]] = [
    ("Roboto", "sans-serif"),
    ("Open Sans", "sans-serif"),
    ("Lato", "sans-serif"),
    ("Montserrat", "sans-serif"),
    ("Oswald", "sans-serif"),
    ("Source Sans 3", "sans-serif"),
    ("Poppins", "sans-serif"),
    ("Raleway", "sans-serif"),
    ("Inter", "sans-serif"),
    ("Noto Sans", "sans-serif"),
    ("Noto Serif", "serif"),
    ("Merriweather", "serif"),
    ("Playfair Display", "serif"),
    ("Libre Baskerville", "serif"),
    ("Source Serif 4", "serif"),
    ("Roboto Slab", "serif"),
    ("Ubuntu", "sans-serif"),
    ("Nunito", "sans-serif"),
    ("Work Sans", "sans-serif"),
    ("Fira Sans", "sans-serif"),
    ("PT Sans", "sans-serif"),
    ("PT Serif", "serif"),
    ("Rubik", "sans-serif"),
    ("Mulish", "sans-serif"),
    ("Quicksand", "sans-serif"),
    ("Manrope", "sans-serif"),
    ("DM Sans", "sans-serif"),
    ("DM Serif Display", "serif"),
    ("IBM Plex Sans", "sans-serif"),
    ("IBM Plex Serif", "serif"),
    ("JetBrains Mono", "monospace"),
    ("Roboto Mono", "monospace"),
    ("Source Code Pro", "monospace"),
    ("Fira Code", "monospace"),
    ("Inconsolata", "monospace"),
    ("Bebas Neue", "display"),
    ("Anton", "display"),
    ("Pacifico", "handwriting"),
    ("Lobster", "handwriting"),
    ("Caveat", "handwriting"),
]


@dataclass(frozen=True)
class FontFamily:
    """Small catalog entry used by the UI."""

    family: str
    category: str


class GoogleFontError(Exception):
    """Raised with a stable error code for user-facing handling."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def family_slug(family: str) -> str:
    """Filesystem-safe family directory name."""
    safe = _SAFE_NAME_RE.sub("-", family.strip()).strip("-").lower()
    return safe or "font"


def is_installed(family: str) -> bool:
    """True if this app already installed at least one file for family."""
    dest = USER_FONT_DIR / family_slug(family)
    try:
        return dest.is_dir() and any(p.suffix.lower() in (".ttf", ".otf") for p in dest.iterdir())
    except OSError:
        return False


def search_popular(query: str, limit: int = 30) -> List[Tuple[str, str]]:
    """Filter the bundled popular-family list."""
    q = query.strip().lower()
    if not q:
        return POPULAR_GOOGLE_FONTS[:limit]
    matches = [(family, cat) for family, cat in POPULAR_GOOGLE_FONTS if q in family.lower()]
    return matches[:limit]


def fallback_catalog() -> List[FontFamily]:
    """Bundled popular fallback sorted by popularity."""
    return [FontFamily(family, category) for family, category in POPULAR_GOOGLE_FONTS]


def _request(url: str, accept: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LayoutSwitcher",
            "Accept": accept,
        },
    )


def _read_capped(resp, limit: int) -> bytes:
    try:
        raw = resp.read(limit + 1)
    except TypeError:
        raw = resp.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > limit:
        raise GoogleFontError("too-large")
    return raw


def _fetch_css(family: str) -> str:
    params = urllib.parse.urlencode({"family": family.strip(), "display": "swap"})
    url = f"{CSS2_URL}?{params}"
    try:
        with urllib.request.urlopen(_request(url, "text/css,*/*"), timeout=HTTP_TIMEOUT) as resp:
            if getattr(resp, "status", 200) != 200:
                raise GoogleFontError("not-found")
            raw = _read_capped(resp, MAX_CSS_BYTES)
    except GoogleFontError:
        raise
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        raise GoogleFontError("network", str(exc)) from exc
    return raw.decode("utf-8", errors="replace")


def _strip_xssi_prefix(text: str) -> str:
    """Google metadata endpoints may prefix JSON with )]}'."""
    text = text.lstrip()
    if text.startswith(")]}'"):
        _, _sep, rest = text.partition("\n")
        return rest.lstrip()
    return text


def _parse_catalog_payload(raw: str) -> List[FontFamily]:
    payload = json.loads(_strip_xssi_prefix(raw))
    items = payload.get("familyMetadataList") or payload.get("items") or []
    if not isinstance(items, list):
        return []

    entries = []
    for pos, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        family = (item.get("family") or item.get("name") or "").strip()
        if not family:
            continue
        category = (item.get("category") or "sans-serif").strip().lower().replace(" ", "-")
        category = category or "sans-serif"
        rank = item.get("popularity", pos)
        try:
            rank_num = int(rank)
        except (TypeError, ValueError):
            rank_num = pos
        entries.append((rank_num, pos, FontFamily(family, category)))

    # If the metadata carries a popularity rank, lower ranks are more popular.
    # Otherwise this preserves endpoint order through ``pos``.
    entries.sort(key=lambda item: (item[0], item[1]))
    return [entry for _rank, _pos, entry in entries]


def _catalog_to_json(entries: List[FontFamily]) -> dict:
    return {
        "saved_at": time.time(),
        "items": [{"family": entry.family, "category": entry.category} for entry in entries],
    }


def _catalog_from_json(payload: dict) -> List[FontFamily]:
    items = payload.get("items") or []
    if not isinstance(items, list):
        return []
    entries = []
    for item in items:
        if not isinstance(item, dict):
            continue
        family = (item.get("family") or "").strip()
        if family:
            category = (item.get("category") or "sans-serif").strip().lower().replace(" ", "-")
            entries.append(FontFamily(family, category or "sans-serif"))
    return entries


def _read_cached_catalog(fresh_only: bool) -> List[FontFamily]:
    try:
        if not CACHE_FILE.exists():
            return []
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if fresh_only:
            age = time.time() - float(payload.get("saved_at", 0) or 0)
            if age > CATALOG_CACHE_TTL:
                return []
        return _catalog_from_json(payload)
    except Exception as exc:
        log.debug("google font catalog cache read failed: %s", exc)
        return []


def _write_cached_catalog(entries: List[FontFamily]) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_catalog_to_json(entries), ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except Exception as exc:
        log.debug("google font catalog cache write failed: %s", exc)


def _fetch_catalog_from_network() -> List[FontFamily]:
    url = CATALOG_URL + "?sort=popularity"
    try:
        with urllib.request.urlopen(
            _request(url, "application/json,text/plain,*/*"),
            timeout=HTTP_TIMEOUT,
        ) as resp:
            if getattr(resp, "status", 200) != 200:
                raise GoogleFontError("network")
            raw = _read_capped(resp, MAX_CATALOG_BYTES)
        entries = _parse_catalog_payload(raw.decode("utf-8", errors="replace"))
    except GoogleFontError:
        raise
    except (TimeoutError, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GoogleFontError("network", str(exc)) from exc
    if not entries:
        raise GoogleFontError("not-found")
    return entries


def load_catalog(force_refresh: bool = False) -> Tuple[bool, List[FontFamily], str]:
    """
    Load the Google Fonts catalog.

    Returns (True, entries, "") from fresh cache/network. If the network fails,
    stale cache is accepted. If no cache exists, returns the bundled fallback
    with ok=False and error code "network".
    """
    if not force_refresh:
        cached = _read_cached_catalog(fresh_only=True)
        if cached:
            return True, cached, ""

    try:
        entries = _fetch_catalog_from_network()
        _write_cached_catalog(entries)
        return True, entries, ""
    except GoogleFontError as exc:
        stale = _read_cached_catalog(fresh_only=False)
        if stale:
            return True, stale, ""
        return False, fallback_catalog(), exc.code


def _font_urls_from_css(css: str) -> List[str]:
    urls: List[str] = []
    seen = set()
    for url in _FONT_URL_RE.findall(css or ""):
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _download_font(url: str) -> bytes:
    try:
        with urllib.request.urlopen(
            _request(url, "font/ttf,font/otf,application/octet-stream,*/*"),
            timeout=HTTP_TIMEOUT,
        ) as resp:
            if getattr(resp, "status", 200) != 200:
                raise GoogleFontError("download-failed")
            return _read_capped(resp, MAX_FONT_BYTES)
    except GoogleFontError:
        raise
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        raise GoogleFontError("network", str(exc)) from exc


def _filename_for(url: str, index: int) -> str:
    path = urllib.parse.urlparse(url).path
    name = Path(path).name
    suffix = Path(name).suffix.lower()
    if suffix not in (".ttf", ".otf"):
        suffix = ".ttf"
    stem = Path(name).stem or f"font-{index}"
    return f"{family_slug(stem)}{suffix}"


def install_for_user(family: str) -> Tuple[bool, str]:
    """
    Install a Google Fonts family for the current user.

    Returns (True, destination_dir) or (False, stable_error_code).
    """
    family = family.strip()
    if not family:
        return False, "empty"

    try:
        css = _fetch_css(family)
        urls = _font_urls_from_css(css)
        if not urls:
            return False, "not-found"

        dest = USER_FONT_DIR / family_slug(family)
        dest.mkdir(parents=True, exist_ok=True)

        written = 0
        for index, url in enumerate(urls, start=1):
            data = _download_font(url)
            if not data:
                continue
            target = dest / _filename_for(url, index)
            target.write_bytes(data)
            written += 1

        if written == 0:
            return False, "download-failed"

        run_cmd(["fc-cache", "-f", str(dest)], timeout=30)
        return True, str(dest)
    except GoogleFontError as exc:
        log.debug("google font install failed: %s (%s)", family, exc.detail or exc.code)
        return False, exc.code
    except OSError as exc:
        log.debug("google font write failed: %s -> %s", family, exc)
        return False, "write-failed"
