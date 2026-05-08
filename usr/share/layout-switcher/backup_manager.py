# SPDX-License-Identifier: MIT
"""
backup_manager.py — Backup e restauração do dconf.

Estratégia:
  - Escrita sempre em arquivo temporário com rename atômico.
  - Mantém os últimos N_KEEP backups para limitar uso de disco.
  - latest() nunca retorna symlink quebrado.
  - restore() valida o arquivo antes de carregar.
  - Todos os métodos retornam (bool, str) e nunca levantam exceção.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import datetime
import os
from pathlib import Path
from typing import List, Optional, Tuple

from constants import BACKUP_DIR
from utils import atomic_write_text, run_cmd


class BackupManager:
    """Gerencia backups do dconf para restauração de layouts e configurações."""

    N_KEEP = int(os.environ.get("LAYOUT_SWITCHER_N_KEEP", "10"))
    MIN_BYTES = 20  # um dump dconf válido tem pelo menos este tamanho

    # ── Criar ─────────────────────────────────────────────────────────────────

    @classmethod
    def create(cls) -> Tuple[bool, str]:
        """
        Cria um novo backup do dconf completo.
        Retorna (True, caminho_do_arquivo) ou (False, mensagem_erro).
        """
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return False, f"cannot create backup dir: {exc}"

        ok, data = run_cmd(["dconf", "dump", "/"], timeout=15)
        if not ok or not data or len(data) < cls.MIN_BYTES:
            return False, f"dconf dump failed or empty: {data!r}"

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BACKUP_DIR / f"backup_{ts}.dconf"

        try:
            atomic_write_text(dest, data)
        except Exception as exc:
            return False, f"write failed: {exc}"

        # Atualiza symlink "latest" de forma atômica.
        # symlink é conveniência (latest() faz fallback para o arquivo mais novo),
        # então qualquer erro aqui é silenciado.
        lnk = BACKUP_DIR / "latest.dconf"
        lnk_tmp = BACKUP_DIR / "latest.dconf.tmp"
        try:
            lnk_tmp.unlink(missing_ok=True)
            lnk_tmp.symlink_to(dest.name)  # symlink relativo
            os.replace(str(lnk_tmp), str(lnk))  # rename atômico
        except OSError:
            try:
                lnk_tmp.unlink(missing_ok=True)
            except OSError:
                pass

        cls._prune()
        return True, str(dest)

    # ── Localizar ─────────────────────────────────────────────────────────────

    @classmethod
    def latest(cls) -> Optional[Path]:
        """
        Retorna o caminho do backup mais recente válido, ou None.
        Compatível com Python 3.8+ (usa os.readlink em vez de Path.readlink).
        """
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        lnk = BACKUP_DIR / "latest.dconf"

        # Tenta symlink primeiro
        if lnk.is_symlink():
            try:
                target = lnk.parent / os.readlink(str(lnk))
                if target.exists() and target.stat().st_size >= cls.MIN_BYTES:
                    return target
            except Exception:
                pass

        # Fallback: arquivo mais novo
        return cls._newest_file()

    @classmethod
    def list_all(cls) -> List[Path]:
        """Retorna todos os backups válidos ordenados do mais novo para o mais antigo."""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            return sorted(
                [
                    p
                    for p in BACKUP_DIR.glob("backup_*.dconf")
                    if p.exists() and p.stat().st_size >= cls.MIN_BYTES
                ],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return []

    # ── Restaurar ─────────────────────────────────────────────────────────────

    @classmethod
    def restore(cls, path: Path) -> Tuple[bool, str]:
        """
        Restaura um backup usando ``LayoutApplier.load_dconf_safely``:
        pausa watcher (lock), desabilita extensões em ordem, escreve
        ``settings.gnome`` atomicamente e faz ``dconf load``. O listener
        de gsettings do Shell reabilita as extensões via mudança em
        ``enabled-extensions``, sem reload manual.

        Retorna (True, "") ou (False, mensagem_erro).
        """
        if not path or not path.exists():
            return False, "backup file not found"
        try:
            data = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return False, f"cannot read backup: {exc}"
        if len(data) < cls.MIN_BYTES:
            return False, "backup file appears to be corrupt (too small)"

        # Import aqui para evitar ciclo (layout_applier nao importa backup).
        from layout_applier import LayoutApplier

        # Backups são dumps locais — DTP monitor IDs já correspondem ao hardware
        # atual, não precisa pré-reescrita.
        before = LayoutApplier._enabled_extensions()
        ok, out = LayoutApplier.load_dconf_safely(
            data,
            persist=True,
            before_uuids=before,
        )
        if not ok:
            return False, f"dconf load failed: {out}"
        return True, out

    # ── Privado ───────────────────────────────────────────────────────────────

    @classmethod
    def _newest_file(cls) -> Optional[Path]:
        files = cls.list_all()
        return files[0] if files else None

    @classmethod
    def _prune(cls) -> None:
        """Remove backups excedentes, mantendo apenas os N_KEEP mais recentes."""
        try:
            all_files = sorted(
                BACKUP_DIR.glob("backup_*.dconf"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in all_files[cls.N_KEEP :]:
                try:
                    old.unlink()
                except Exception:
                    pass
        except Exception:
            pass
