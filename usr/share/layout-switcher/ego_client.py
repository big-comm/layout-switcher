# SPDX-License-Identifier: MIT
"""
ego_client.py — Cliente HTTP do extensions.gnome.org.

Endpoints suportados:
  - /extension-query/   → busca paginada
  - /extension-info/    → metadados completos (incl. comentários e screenshots)
  - /static/...         → download de thumbnails

Toda chamada HTTP é não-bloqueante apenas se invocada de uma thread fora
da UI; este módulo NÃO faz threading sozinho. Use o pool da janela principal.

Cache em disco em ego_cache.py — search 1h, info 24h, thumbs LRU 50 MiB.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import ego_cache
from constants import (
    APP_VERSION,
    EGO_BASE_URL,
    EGO_CACHE_TTL_INFO,
    EGO_CACHE_TTL_SEARCH,
    EGO_USER_AGENT,
)

log = logging.getLogger("layout-switcher")

SORT_POPULARITY = "popularity"
SORT_DOWNLOADS = "downloads"
SORT_RECENT = "recent"
SORT_NAME = "name"

# extension-query "shell_version=all" devolve tudo, ignorando compatibilidade.
SHELL_ALL = "all"

# Conexão lenta ainda deve ter chance de completar — 15s é o que o
# extension-manager usa.
HTTP_TIMEOUT = 15

# Defesa contra respostas absurdamente grandes (servidor comprometido,
# proxy malicioso). JSON do EGO costuma ter < 200 KiB; thumbs raramente
# passam de 2 MiB. Caps generosos para não rejeitar payloads legítimos.
_MAX_JSON_BYTES = 5 * 1024 * 1024  # 5 MiB
_MAX_THUMB_BYTES = 10 * 1024 * 1024  # 10 MiB


# ── Modelos ───────────────────────────────────────────────────────────────────


@dataclass
class ExtensionSummary:
    """Resumo retornado em /extension-query/."""

    uuid: str
    name: str
    description: str
    creator: str
    pk: int  # ego_id (chave primária no EGO)
    icon_url: str
    downloads: int
    rating: float
    rating_count: int
    shell_version_map: dict = field(default_factory=dict)


@dataclass
class ScreenshotRef:
    """Referência a uma screenshot do EGO."""

    url: str  # URL absoluta (preencher antes de exibir)


@dataclass
class CommentEntry:
    """Comentário retornado pelo EGO."""

    author: str
    rating: int  # 0-5; 0 = sem rating
    date: str  # já como string "YYYY-MM-DD" ou similar do servidor
    text: str


@dataclass
class ExtensionInfo:
    """Detalhes completos de uma extensão (saída de /extension-info/)."""

    uuid: str
    name: str
    description: str
    creator: str
    pk: int
    url: str
    icon_url: str
    screenshot_url: str
    screenshots: List[ScreenshotRef]
    downloads: int
    rating: float
    rating_count: int
    shell_version_map: dict
    homepage: str
    license: str
    comments: List[CommentEntry]


@dataclass
class SearchResult:
    """Página de resultados de busca."""

    extensions: List[ExtensionSummary]
    page: int
    num_pages: int
    total: int


# ── Helpers ───────────────────────────────────────────────────────────────────


def _user_agent() -> str:
    return EGO_USER_AGENT.format(version=APP_VERSION)


def _absolute_url(path_or_url: str) -> str:
    """Resolve URLs relativas (/static/...) contra o base do EGO."""
    if not path_or_url:
        return ""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    if not path_or_url.startswith("/"):
        path_or_url = "/" + path_or_url
    return EGO_BASE_URL + path_or_url


def _read_capped(resp, limit: int) -> Optional[bytes]:
    """Lê do response até ``limit`` bytes; devolve None se exceder."""
    try:
        raw = resp.read(limit + 1)
    except TypeError:
        # Some test doubles and file-like objects only implement read().
        raw = resp.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > limit:
        log.debug("ego_client response exceeded %d bytes — discarded", limit)
        return None
    return raw


def _http_json(url: str) -> Optional[dict]:
    """
    GET → JSON. Retorna None em qualquer falha (rede, HTTP != 200, JSON inválido,
    payload acima do limite).
    Sem retry — chamadores podem repetir se quiserem.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _user_agent(),
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            if resp.status != 200:
                log.debug("ego_client http %s → %s", url, resp.status)
                return None
            raw = _read_capped(resp, _MAX_JSON_BYTES)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        log.debug("ego_client http %s failed: %s", url, exc)
        return None


def _http_bytes(url: str) -> Optional[bytes]:
    """GET → bytes brutos (cap em ``_MAX_THUMB_BYTES``). Retorna None em falha."""
    req = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return _read_capped(resp, _MAX_THUMB_BYTES)
    except (urllib.error.URLError, OSError) as exc:
        log.debug("ego_client bytes %s failed: %s", url, exc)
        return None


def _parse_summary(item: dict) -> Optional[ExtensionSummary]:
    """Tolerante a campos faltando — pula entradas que não têm uuid+name."""
    uuid = item.get("uuid") or ""
    name = item.get("name") or uuid
    if not uuid:
        return None
    icon = item.get("icon") or ""
    return ExtensionSummary(
        uuid=uuid,
        name=name,
        description=item.get("description", "") or "",
        creator=item.get("creator", "") or "",
        pk=int(item.get("pk", 0) or 0),
        icon_url=_absolute_url(icon),
        downloads=int(item.get("downloads", 0) or 0),
        rating=float(item.get("rating", 0) or 0),
        rating_count=int(item.get("rating_count", 0) or 0),
        shell_version_map=item.get("shell_version_map") or {},
    )


def _parse_comments(raw: object) -> List[CommentEntry]:
    """
    O endpoint /extension-info/ pode devolver comentários como lista de dicts
    (formato moderno) ou como string HTML (formato antigo). Aqui só tratamos a
    versão estruturada — se o servidor mandar HTML, devolvemos vazio e a UI
    oferece o link "ver todos no site".
    """
    if not isinstance(raw, list):
        return []
    out: List[CommentEntry] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        author = entry.get("username") or entry.get("author") or "anon"
        rating_val = entry.get("rating")
        rating = int(rating_val) if isinstance(rating_val, (int, float)) else 0
        date = str(entry.get("date") or entry.get("created") or "")
        text = (entry.get("comment") or entry.get("text") or "").strip()
        if text:
            out.append(CommentEntry(author=author, rating=rating, date=date, text=text))
    return out


# ── API pública ───────────────────────────────────────────────────────────────


def search(
    query: str = "",
    page: int = 1,
    sort: str = SORT_POPULARITY,
    shell_version: str = SHELL_ALL,
    use_cache: bool = True,
) -> Optional[SearchResult]:
    """
    Busca paginada em /extension-query/.

    `shell_version` aceita "47", "47.0", "all" ou "" (= "all"). O EGO trata
    "all" especialmente, devolvendo extensões de qualquer versão.
    """
    page = max(1, int(page))
    sort = sort or SORT_POPULARITY
    shell = shell_version or SHELL_ALL

    params = {
        "search": query or "",
        "sort": sort,
        "page": str(page),
        "shell_version": shell,
    }
    cache_key = json.dumps(params, sort_keys=True)
    if use_cache:
        cached = ego_cache.json_get("search", cache_key, EGO_CACHE_TTL_SEARCH)
        if cached is not None:
            return _result_from_dict(cached)

    url = f"{EGO_BASE_URL}/extension-query/?" + urllib.parse.urlencode(params)
    payload = _http_json(url)
    if payload is None:
        return None

    ego_cache.json_put("search", cache_key, payload)
    return _result_from_dict(payload)


def _result_from_dict(payload: dict) -> SearchResult:
    raw_list = payload.get("extensions") or []
    items: List[ExtensionSummary] = []
    for item in raw_list:
        summary = _parse_summary(item)
        if summary is not None:
            items.append(summary)
    return SearchResult(
        extensions=items,
        page=int(payload.get("page", 1) or 1),
        num_pages=int(payload.get("numpages", 1) or 1),
        total=int(payload.get("total", len(items)) or len(items)),
    )


def info(
    uuid: str,
    shell_version: str = SHELL_ALL,
    use_cache: bool = True,
) -> Optional[ExtensionInfo]:
    """
    Detalhes completos de uma extensão. Sem `shell_version` o EGO devolve o
    metadata da última release; passar a versão alvo deixa `shell_version_map`
    correto para a UI calcular compatibilidade.
    """
    if not uuid:
        return None
    shell = shell_version or SHELL_ALL
    cache_key = f"{uuid}|{shell}"
    if use_cache:
        cached = ego_cache.json_get("info", cache_key, EGO_CACHE_TTL_INFO)
        if cached is not None:
            return _info_from_dict(cached)

    params = {"uuid": uuid, "shell_version": shell}
    url = f"{EGO_BASE_URL}/extension-info/?" + urllib.parse.urlencode(params)
    payload = _http_json(url)
    if payload is None:
        return None

    ego_cache.json_put("info", cache_key, payload)
    return _info_from_dict(payload)


def _info_from_dict(payload: dict) -> ExtensionInfo:
    summary = _parse_summary(payload) or ExtensionSummary(
        uuid=payload.get("uuid", ""),
        name=payload.get("name", ""),
        description="",
        creator=payload.get("creator", ""),
        pk=int(payload.get("pk", 0) or 0),
        icon_url="",
        downloads=0,
        rating=0.0,
        rating_count=0,
    )
    screenshot_url = _absolute_url(payload.get("screenshot") or "")
    screenshots = [ScreenshotRef(url=screenshot_url)] if screenshot_url else []
    extra = payload.get("screenshots") or []
    if isinstance(extra, list):
        for s in extra:
            url = _absolute_url(s if isinstance(s, str) else s.get("url", ""))
            if url and url != screenshot_url:
                screenshots.append(ScreenshotRef(url=url))
    return ExtensionInfo(
        uuid=summary.uuid,
        name=summary.name,
        description=summary.description or payload.get("description", "") or "",
        creator=summary.creator,
        pk=summary.pk,
        url=_absolute_url(payload.get("link") or f"/extension/{summary.pk}/"),
        icon_url=summary.icon_url,
        screenshot_url=screenshot_url,
        screenshots=screenshots,
        downloads=summary.downloads,
        rating=summary.rating,
        rating_count=summary.rating_count,
        shell_version_map=payload.get("shell_version_map") or summary.shell_version_map,
        homepage=payload.get("url") or "",
        license=payload.get("license") or "",
        comments=_parse_comments(payload.get("comments")),
    )


def latest_version(uuid: str, shell_version: str) -> Optional[int]:
    """
    Retorna a versão (inteira) mais recente da extensão para a versão do Shell
    informada, ou None se incompatível / inexistente.

    O `shell_version_map` do EGO mapeia "47" → {"version": 12, "pk": ..., "version_tag": ...}.
    """
    detail = info(uuid, shell_version=shell_version)
    if detail is None:
        return None
    svm = detail.shell_version_map or {}
    candidates = []
    if shell_version and shell_version != SHELL_ALL and shell_version in svm:
        candidates.append(svm[shell_version])
    # Fallback: maior version disponível em qualquer entrada do mapa
    for entry in svm.values():
        if entry not in candidates:
            candidates.append(entry)
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if isinstance(version, int):
            return version
        try:
            return int(version)
        except (TypeError, ValueError):
            continue
    return None


def fetch_screenshot(url: str) -> Optional[Path]:
    """
    Baixa a screenshot e devolve o Path local (cache). Se já estiver em cache,
    devolve direto sem rede.
    """
    if not url:
        return None
    cached = ego_cache.thumb_get(url)
    if cached is not None:
        return cached
    data = _http_bytes(url)
    if not data:
        return None
    return ego_cache.thumb_put(url, data)
