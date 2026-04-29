# SPDX-License-Identifier: MIT
"""
ego_cache.py — Cache em disco para respostas do extensions.gnome.org.

Dois caches independentes:
  - JSON cache (search/info)  → TTL configurável, evict por idade.
  - Thumbs cache (PNG/JPEG)   → sem TTL, evict LRU acima de tamanho-limite.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

from constants import (
    EGO_CACHE_DIR,
    EGO_THUMBS_DIR,
    EGO_THUMBS_MAX_BYTES,
)

log = logging.getLogger("layout-switcher")


def _hash_key(key: str) -> str:
    """SHA-1 do conteúdo da chave; nomes de arquivo previsíveis e seguros."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


# ── JSON cache ────────────────────────────────────────────────────────────────


def _json_dir(namespace: str) -> Path:
    """Diretório do namespace (search, info, ...). Criado sob demanda."""
    path = EGO_CACHE_DIR / namespace
    path.mkdir(parents=True, exist_ok=True)
    return path


def json_get(namespace: str, key: str, ttl_seconds: int) -> Optional[dict]:
    """
    Lê JSON do cache se existir e estiver dentro do TTL. Retorna None caso contrário.
    Falhas de I/O / JSON malformado são silenciadas → None.
    """
    path = _json_dir(namespace) / f"{_hash_key(key)}.json"
    try:
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > ttl_seconds:
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        log.debug("ego_cache.json_get %s/%s failed: %s", namespace, key, exc)
        return None


def json_put(namespace: str, key: str, payload: dict) -> None:
    """Grava JSON atomicamente (tmp + rename). Silencia falhas."""
    path = _json_dir(namespace) / f"{_hash_key(key)}.json"
    try:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        tmp.replace(path)
    except Exception as exc:
        log.debug("ego_cache.json_put %s/%s failed: %s", namespace, key, exc)


def json_invalidate(namespace: str, key: str) -> None:
    """Remove uma entrada específica do cache JSON."""
    path = _json_dir(namespace) / f"{_hash_key(key)}.json"
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


# ── Thumbs cache (binários) ───────────────────────────────────────────────────


def thumbs_dir() -> Path:
    """Diretório de thumbs criado sob demanda."""
    EGO_THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    return EGO_THUMBS_DIR


def thumb_path(url: str) -> Path:
    """Caminho determinístico (não cria) para a thumb correspondente à URL."""
    suffix = Path(url).suffix.lower() or ".png"
    if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        suffix = ".png"
    return thumbs_dir() / f"{_hash_key(url)}{suffix}"


def thumb_get(url: str) -> Optional[Path]:
    """Retorna o Path da thumb se já estiver em cache; None caso contrário."""
    path = thumb_path(url)
    if path.exists() and path.stat().st_size > 0:
        # touch atime para LRU
        try:
            path.touch()
        except Exception:
            pass
        return path
    return None


def thumb_put(url: str, data: bytes) -> Optional[Path]:
    """
    Grava a thumb e dispara evict LRU se necessário. Retorna o Path final ou None.
    """
    if not data:
        return None
    path = thumb_path(url)
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        _evict_thumbs_if_needed()
        return path
    except Exception as exc:
        log.debug("ego_cache.thumb_put %s failed: %s", url, exc)
        return None


def _evict_thumbs_if_needed() -> None:
    """
    Mantém o diretório de thumbs abaixo de EGO_THUMBS_MAX_BYTES.
    Remove os menos recentemente acessados (mtime crescente) até voltar ao limite.
    """
    base = thumbs_dir()
    try:
        files = [(p, p.stat()) for p in base.iterdir() if p.is_file()]
    except Exception:
        return
    total = sum(st.st_size for _, st in files)
    if total <= EGO_THUMBS_MAX_BYTES:
        return
    # Mais antigos primeiro (mtime ascendente).
    files.sort(key=lambda item: item[1].st_mtime)
    for path, st in files:
        if total <= EGO_THUMBS_MAX_BYTES:
            break
        try:
            path.unlink(missing_ok=True)
            total -= st.st_size
        except Exception:
            pass


def clear_all() -> None:
    """Remove todos os arquivos do cache (uso em testes / opção de manutenção)."""
    for base in (EGO_CACHE_DIR, EGO_THUMBS_DIR):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file():
                try:
                    p.unlink()
                except Exception:
                    pass
