# SPDX-License-Identifier: MIT
"""
snapshot_manager.py — Snapshots personalizados por layout.

Replica o comportamento do KDE Plasma: cada layout tem um snapshot
dedicado ("sua versao modificada") que persiste quando o usuario troca
e volta. Ao retornar, o app oferece:

  * **Retomar** — carrega o snapshot salvo (modificacoes do usuario)
  * **Original** — carrega o arquivo padrao da distro (em ``layouts/``)

Os snapshots sao armazenados em
``~/.config/big-appearance/layout-snapshots/<layout_id>.dconf`` — formato
identico ao ``dconf dump /``.

``layout_id`` e o stem do arquivo de layout (ex.: ``"biggnome"`` para
``biggnome.txt``), estavel entre releases.

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from constants import CONFIG_DIR
from utils import atomic_write_text, run_cmd

log = logging.getLogger("layout-switcher")

SNAPSHOTS_DIR = CONFIG_DIR / "layout-snapshots"
MIN_SNAPSHOT_BYTES = 100


class SnapshotManager:
    """Gerencia snapshots de layout (versoes modificadas pelo usuario)."""

    @staticmethod
    def _path_for(layout_id: str) -> Path:
        """Caminho do snapshot para um layout_id (ex.: 'biggnome')."""
        # Nomes de layout ja sao seguros (stem de arquivo), mas aplicamos
        # lower() e filtro defensivo para evitar qualquer surpresa.
        safe = "".join(c for c in layout_id.lower() if c.isalnum() or c in "-_")
        return SNAPSHOTS_DIR / f"{safe}.dconf"

    # ── Save ─────────────────────────────────────────────────────────────────

    @classmethod
    def save(cls, layout_id: str) -> Tuple[bool, str]:
        """
        Salva o estado atual do dconf como snapshot do ``layout_id``.

        Retorna (True, caminho) em sucesso ou (False, mensagem_erro).
        Silencioso: falhas nao devem bloquear a troca de layout.
        """
        if not layout_id:
            return False, "empty layout_id"

        try:
            SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return False, f"cannot create snapshots dir: {exc}"

        ok, data = run_cmd(["dconf", "dump", "/"], timeout=15)
        if not ok:
            return False, f"dconf dump failed: {data}"
        if not data or len(data) < MIN_SNAPSHOT_BYTES:
            return False, "dconf dump produced empty/tiny output"

        dest = cls._path_for(layout_id)
        try:
            atomic_write_text(dest, data)
            log.debug("snapshot saved: %s (%d bytes)", dest, len(data))
            return True, str(dest)
        except Exception as exc:
            return False, f"write failed: {exc}"

    # ── Load ─────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, layout_id: str) -> Optional[Path]:
        """Retorna o Path do snapshot se existir e for valido; senao None."""
        if not layout_id:
            return None
        p = cls._path_for(layout_id)
        try:
            if p.exists() and p.stat().st_size >= MIN_SNAPSHOT_BYTES:
                return p
        except Exception:
            pass
        return None

    @classmethod
    def has(cls, layout_id: str) -> bool:
        """True se existe snapshot valido para o layout."""
        return cls.load(layout_id) is not None

    @classmethod
    def read(cls, layout_id: str) -> Optional[str]:
        """Retorna o conteudo do snapshot ou None se ausente/invalido."""
        p = cls.load(layout_id)
        if not p:
            return None
        try:
            return p.read_text(encoding="utf-8")
        except Exception as exc:
            log.debug("snapshot read failed: %s -> %s", p, exc)
            return None

    # ── Delete / list ────────────────────────────────────────────────────────

    @classmethod
    def delete(cls, layout_id: str) -> bool:
        """Remove o snapshot (idempotente)."""
        if not layout_id:
            return False
        try:
            cls._path_for(layout_id).unlink(missing_ok=True)
            return True
        except Exception as exc:
            log.debug("snapshot delete failed: %s", exc)
            return False

    @classmethod
    def list_all(cls) -> List[Path]:
        """Lista todos os snapshots existentes (mais recentes primeiro)."""
        try:
            SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            return sorted(
                [
                    p
                    for p in SNAPSHOTS_DIR.glob("*.dconf")
                    if p.stat().st_size >= MIN_SNAPSHOT_BYTES
                ],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return []
