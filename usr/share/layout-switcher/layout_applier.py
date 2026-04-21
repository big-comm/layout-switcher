# SPDX-License-Identifier: MIT
"""
layout_applier.py — Aplica layouts de desktop via dconf (sessao ativa).

Reproduz o comportamento do ``startgnome-community`` (do pacote
``comm-gnome-config``) em tempo de execucao, sem precisar de logout.

O ``startgnome-community`` no boot faz:

  1. ``dconf reset -f /``                    (limpa perfil)
  2. ``dconf load / < ~/.config/dconf/settings.gnome``

Isso garante que o estado final seja IGUAL ao arquivo (sem residuos de
layouts anteriores) — ``dconf load`` sozinho faz MERGE, nao REPLACE.

Durante a sessao ativa, precisamos do mesmo reset+load, mas o GNOME Shell
esta rodando e as extensoes reagem a todos os eventos ``changed`` do
GSettings. Se o reset disparar esses eventos com esquemas esvaziados,
extensoes entram em estado de erro.

Solucao: pausar extensoes ANTES do reset. Assim o Shell nao tenta
reconstruir extensoes enquanto o estado do dconf esta incompleto. O
``dconf load`` posterior traz todos os valores corretos (incluindo
``disable-user-extensions`` do proprio layout), e o Shell reativa
extensoes uma unica vez, com o estado final estabilizado.

Tambem paramos o ``dconf-sync-gnome.service`` (do comm-gnome-config)
durante a operacao para evitar que ele salve estados intermediarios em
``~/.config/dconf/settings.gnome``. Ao final, gravamos o settings.gnome
explicitamente com o dump limpo.

Fluxo atomico:

  1. stop   dconf-sync-gnome.service   (se existir)
  2. gsettings disable-user-extensions=true (pausa shell de reagir)
  3. sleep settle
  4. dconf reset -f /                  (limpa tudo)
  5. dconf load /  < arquivo           (aplica estado novo completo)
  6. dconf dump / > settings.gnome     (persiste para proximo boot)
  7. gsettings disable-user-extensions=false (idempotente, apos load)
  8. start  dconf-sync-gnome.service
  9. ShellReloader.reload_all()

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import logging
import time
from pathlib import Path
from typing import Tuple

from shell_reloader import ShellReloader
from utils import run_cmd

log = logging.getLogger("layout-switcher")

SETTINGS_GNOME = Path.home() / ".config" / "dconf" / "settings.gnome"
SYNC_SERVICE = "dconf-sync-gnome.service"


class LayoutApplier:
    """Aplica layout com reset+load, protegendo extensoes e monitor de sync."""

    _SETTLE_SEC = 0.5  # tempo para o Shell processar disable-user-extensions
    _MIN_DUMP_BYTES = 100

    # ── Helpers de infraestrutura ────────────────────────────────────────────

    @staticmethod
    def _has_sync_service() -> bool:
        """True se o servico dconf-sync-gnome do comm-gnome-config existe."""
        ok, _ = run_cmd(
            ["systemctl", "--user", "cat", SYNC_SERVICE],
            timeout=5,
        )
        return ok

    @classmethod
    def _sync_service(cls, action: str) -> None:
        """start/stop do dconf-sync-gnome (silencioso se ausente)."""
        if not cls._has_sync_service():
            return
        run_cmd(
            ["systemctl", "--user", action, SYNC_SERVICE],
            timeout=10,
        )

    @staticmethod
    def _pause_extensions(pause: bool) -> None:
        """Liga/desliga todas as extensoes de usuario via gsettings."""
        run_cmd(
            [
                "gsettings",
                "set",
                "org.gnome.shell",
                "disable-user-extensions",
                "true" if pause else "false",
            ],
            timeout=5,
        )

    @classmethod
    def _persist_to_settings_file(cls) -> Tuple[bool, str]:
        """
        Grava ``dconf dump /`` em ``~/.config/dconf/settings.gnome`` de forma
        atomica (``.tmp`` -> rename, com ``.bak`` do anterior), reproduzindo
        o comportamento do ``dconf-sync-monitor-gnome``.
        """
        ok, data = run_cmd(["dconf", "dump", "/"], timeout=15)
        if not ok:
            return False, f"dconf dump failed: {data}"
        if not data or len(data) < cls._MIN_DUMP_BYTES:
            return False, "dconf dump produced empty/tiny output"

        try:
            SETTINGS_GNOME.parent.mkdir(parents=True, exist_ok=True)
            tmp = SETTINGS_GNOME.parent / (SETTINGS_GNOME.name + ".tmp")
            tmp.write_text(data, encoding="utf-8")
            if SETTINGS_GNOME.exists() and SETTINGS_GNOME.stat().st_size > 0:
                bak = SETTINGS_GNOME.parent / (SETTINGS_GNOME.name + ".bak")
                try:
                    bak.write_bytes(SETTINGS_GNOME.read_bytes())
                except Exception as exc:
                    log.debug("could not create .bak: %s", exc)
            tmp.replace(SETTINGS_GNOME)
            return True, str(SETTINGS_GNOME)
        except Exception as exc:
            return False, f"write failed: {exc}"

    # ── API publica ──────────────────────────────────────────────────────────

    @classmethod
    def load_dconf_safely(cls, data: str, persist: bool = True) -> Tuple[bool, str]:
        """
        Aplica um dump dconf em ``/`` usando reset+load (REPLACE, nao MERGE),
        com orquestracao completa: para o monitor, pausa extensoes, reseta,
        carrega, persiste no settings.gnome e restaura tudo no fim.

        Shared entre ``apply()`` (layout) e ``BackupManager.restore()``.
        Nao chama ``ShellReloader.reload_all()`` — cabe ao chamador.

        Retorna (True, "") em sucesso ou (False, mensagem_erro).
        """
        if not data or not data.strip():
            return False, "empty dconf data"

        # 1. Para o monitor para nao capturar estados intermediarios.
        cls._sync_service("stop")

        # 2. Pausa extensoes ANTES de qualquer mudanca no dconf, senao elas
        #    reagem aos sinais do reset com esquemas esvaziados e entram em
        #    estado de erro.
        cls._pause_extensions(pause=True)
        time.sleep(cls._SETTLE_SEC)

        ok = False
        msg = ""
        try:
            # 3. Reset total: garante que o load seguinte produza um REPLACE.
            ok_reset, reset_msg = run_cmd(
                ["dconf", "reset", "-f", "/"],
                timeout=10,
            )
            if not ok_reset:
                return False, f"dconf reset failed: {reset_msg}"

            # 4. Load do novo estado. O proprio arquivo traz
            #    disable-user-extensions=false (ou omite) — o Shell vai
            #    reativar extensoes com o estado ja completo.
            ok, msg = run_cmd(
                ["dconf", "load", "/"],
                stdin_text=data,
                timeout=20,
            )
            if not ok:
                log.warning("dconf load failed: %s", msg)
                return False, f"dconf load failed: {msg}"

            # 5. Persiste no settings.gnome para sobreviver ao proximo login.
            if persist:
                persist_ok, persist_info = cls._persist_to_settings_file()
                if not persist_ok:
                    log.warning("settings.gnome persist failed: %s", persist_info)
        finally:
            # 6. Reativa extensoes e monitor, haja ou nao sucesso no load.
            time.sleep(cls._SETTLE_SEC)
            cls._pause_extensions(pause=False)
            cls._sync_service("start")

        return ok, msg

    @classmethod
    def apply(cls, config_path: Path) -> Tuple[bool, str]:
        """Aplica um arquivo de layout ao ambiente."""
        if not config_path or not config_path.exists():
            return False, f"layout file not found: {config_path}"
        try:
            data = config_path.read_text(encoding="utf-8")
        except Exception as exc:
            return False, f"cannot read layout file: {exc}"
        if not data.strip():
            return False, "layout file is empty"

        ok, msg = cls.load_dconf_safely(data, persist=True)
        if ok:
            ShellReloader.reload_all()
        return ok, msg
