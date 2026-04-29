# SPDX-License-Identifier: MIT
"""
update_checker.py — Detecta e aplica atualizações de extensões via EGO.

Roda fora da UI thread. Compara `metadata.json[version]` local com
`shell_version_map[<shell>].version` do EGO e devolve um dicionário de
atualizações disponíveis.

Auto-update é opt-in via Settings('ext_auto_update', default=False).

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import ego_client
from extension_manager import ExtMgr
from utils import gnome_shell_version

log = logging.getLogger("layout-switcher")


@dataclass
class UpdateInfo:
    """Detalhe de uma atualização disponível."""

    uuid: str
    current_version: int
    latest_version: int
    ego_id: int  # pk no EGO; útil para fallback de download direto


def _shell_version_str() -> str:
    """Versão do Shell em formato aceito pelo EGO ('47'), ou 'all' se desconhecido."""
    major, _ = gnome_shell_version()
    if major <= 0:
        return ego_client.SHELL_ALL
    return str(major)


def check_all(
    progress_cb: Callable[[int, int], None] = None,
) -> Dict[str, UpdateInfo]:
    """
    Verifica atualizações para todas as extensões instaladas pelo usuário.
    Extensões do sistema (em /usr/share/...) são ignoradas — são gerenciadas
    pelo gerenciador de pacotes da distro, não pelo EGO.

    `progress_cb(done, total)` é opcional e chamado a cada extensão verificada.
    """
    shell = _shell_version_str()
    user_exts = [e for e in ExtMgr.list_installed() if e.get("user")]
    total = len(user_exts)
    updates: Dict[str, UpdateInfo] = {}

    for index, ext in enumerate(user_exts):
        uuid = ext["uuid"]
        try:
            current = ExtMgr.installed_version(uuid)
            if current <= 0:
                continue  # versão local indisponível → não temos baseline
            detail = ego_client.info(uuid, shell_version=shell)
            if detail is None:
                continue
            latest = ego_client.latest_version(uuid, shell)
            if latest is None or latest <= current:
                continue
            updates[uuid] = UpdateInfo(
                uuid=uuid,
                current_version=current,
                latest_version=latest,
                ego_id=detail.pk,
            )
        except Exception as exc:
            log.debug("update_checker.check_all %s failed: %s", uuid, exc)
        finally:
            if progress_cb:
                try:
                    progress_cb(index + 1, total)
                except Exception:
                    pass

    return updates


def apply_update(info: UpdateInfo) -> Tuple[bool, str]:
    """Aplica uma atualização individual. Wrapper fino sobre ExtMgr.update."""
    return ExtMgr.update(info.uuid, info.ego_id)


def apply_all(updates: List[UpdateInfo]) -> List[Tuple[UpdateInfo, bool, str]]:
    """Aplica todas as atualizações; retorna lista (info, ok, mensagem)."""
    results: List[Tuple[UpdateInfo, bool, str]] = []
    for info in updates:
        ok, msg = apply_update(info)
        results.append((info, ok, msg))
    return results


# ── Persistência leve do timestamp da última verificação ─────────────────────
#
# Usamos a mesma `Settings` que o resto do app — chave `ext_last_update_check`
# guarda epoch seconds. Não persiste o resultado em disco para evitar mostrar
# updates desatualizados após reabrir o app.


def time_since_last_check(settings) -> float:
    """Segundos decorridos desde a última verificação. ∞ se nunca rodou."""
    last = settings.get("ext_last_update_check", 0) or 0
    try:
        last_f = float(last)
    except (TypeError, ValueError):
        last_f = 0.0
    if last_f <= 0:
        return float("inf")
    return max(0.0, time.time() - last_f)


def mark_checked(settings) -> None:
    """Marca a hora atual como última verificação bem-sucedida."""
    settings.set("ext_last_update_check", time.time())
