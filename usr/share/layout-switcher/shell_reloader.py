# SPDX-License-Identifier: MIT
"""
shell_reloader.py — Recarrega extensões e temas do GNOME Shell em tempo real.

Estratégias em cascata (mais segura → fallback):
  1. D-Bus org.gnome.Shell.Extensions.Enable/DisableExtension — GS 3.36+, Wayland
  2. D-Bus org.gnome.Shell.Extensions.ReloadExtension         — recarga cirúrgica
  3. gnome-extensions reset CLI                               — GS 3.34+
  4. D-Bus Eval global.reexec_self()                          — X11 somente

Nenhuma estratégia exige logout ou encerramento de sessão.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import re
import time
from typing import Dict, Iterable, Optional, Tuple

from constants import (
    DBUS_EVAL_IFACE,
    DBUS_EXT_IFACE,
    DBUS_EXT_PATH,
    DBUS_SHELL_NAME,
    DBUS_SHELL_PATH,
)
from utils import is_wayland, run_cmd

# GNOME Shell's ExtensionState enum (from extensionUtils.js):
#   ENABLED=1, DISABLED=2, ERROR=3, OUT_OF_DATE=4, DOWNLOADING=5,
#   INITIALIZED=6, DISABLING=7, ENABLING=8
# A UUID is "live" if EnableExtension would be a no-op or harmful:
#   ENABLED — already running; re-enabling triggers double-init
#   ENABLING — Shell is mid-enable; the call would be redundant
_LIVE_EXT_STATES = {1, 8}

_LIST_EXT_STATE_RE = re.compile(
    r"'([^']+)':\s*\{[^{}]*?'state':\s*<(\d+(?:\.\d+)?)>",
    re.DOTALL,
)


class ShellReloader:
    """
    Recarrega o GNOME Shell / extensões em tempo real sem logout.

    Uso típico:
        ok, msg = ShellReloader.apply_extension_state(uuid, enable=True)
        ShellReloader.reload_all()
    """

    # ── Recarga de extensão individual ────────────────────────────────────────

    @staticmethod
    def reload_extension(uuid: str, timeout: int = 8) -> bool:
        """
        Recarrega uma extensão específica via D-Bus (recarga cirúrgica).
        Funciona em Wayland e X11. Retorna True se o D-Bus aceitou o comando.
        """
        ok, out = run_cmd(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                DBUS_SHELL_NAME,
                "--object-path",
                DBUS_EXT_PATH,
                "--method",
                f"{DBUS_EXT_IFACE}.ReloadExtension",
                uuid,
            ],
            timeout=timeout,
        )
        return ok

    # ── Ativar / desativar via D-Bus ──────────────────────────────────────────

    @staticmethod
    def enable_extension_dbus(
        uuid: str,
        enable: bool,
        timeout: int = 8,
    ) -> Tuple[bool, str]:
        """
        Ativa ou desativa uma extensão diretamente via D-Bus.
        Funciona em Wayland sem precisar de logout (GS 3.36+).
        Retorna (sucesso, mensagem).
        """
        method = (
            f"{DBUS_EXT_IFACE}.EnableExtension" if enable else f"{DBUS_EXT_IFACE}.DisableExtension"
        )
        ok, out = run_cmd(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                DBUS_SHELL_NAME,
                "--object-path",
                DBUS_EXT_PATH,
                "--method",
                method,
                uuid,
            ],
            timeout=timeout,
        )
        return ok, out

    # ── Estado das extensões ──────────────────────────────────────────────────

    @staticmethod
    def list_extensions_state() -> Dict[str, int]:
        """
        Consulta ``org.gnome.Shell.Extensions.ListExtensions`` via D-Bus e
        retorna ``{uuid: state}`` (state é o ExtensionState int do Shell).
        Em falha retorna ``{}``.
        """
        ok, raw = run_cmd(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                DBUS_SHELL_NAME,
                "--object-path",
                DBUS_EXT_PATH,
                "--method",
                f"{DBUS_EXT_IFACE}.ListExtensions",
            ],
            timeout=8,
        )
        if not ok or not raw:
            return {}
        states: Dict[str, int] = {}
        for match in _LIST_EXT_STATE_RE.finditer(raw):
            uuid, state_str = match.group(1), match.group(2)
            try:
                states[uuid] = int(float(state_str))
            except ValueError:
                continue
        return states

    # ── Recarga geral ─────────────────────────────────────────────────────────

    @staticmethod
    def reload_all(
        before_uuids: Optional[Iterable[str]] = None,
        after_uuids: Optional[Iterable[str]] = None,
    ) -> None:
        """
        Aplica diff de extensões via D-Bus por UUID. Em GS 45+ não existe mais
        reload global (``ReloadExtension`` virou deprecated, ``gnome-extensions
        reset`` exige UUID), então fazemos só o mínimo necessário:

          - UUIDs em ``before − after`` → ``DisableExtension`` (Shell descarrega).
          - UUIDs em ``after − before`` → ``EnableExtension`` **somente se**
            ainda não estiverem ENABLED/ENABLING. Quando o caller é o
            ``LayoutApplier``, o Shell já auto-habilitou via gsettings (na
            phase 2 do load), então a maioria dos UUIDs já está viva — repetir
            o ``EnableExtension`` causaria double-init (ex: dash-to-dock,
            drive-menu).
          - UUIDs já ligados e que continuam → não tocados. ``dconf load``
            propaga as mudanças via gsettings reativo.

        Em sessão X11 mantém ``reexec_self()`` como reforço final.
        Nunca levanta exceção.
        """
        before_set = {u for u in (before_uuids or []) if u}
        after_set = {u for u in (after_uuids or []) if u}

        # Disable extensions that should no longer be running.
        for uuid in sorted(before_set - after_set):
            run_cmd(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    DBUS_SHELL_NAME,
                    "--object-path",
                    DBUS_EXT_PATH,
                    "--method",
                    f"{DBUS_EXT_IFACE}.DisableExtension",
                    uuid,
                ],
                timeout=5,
            )

        # Settle a touch so any Shell auto-enable triggered by a recent
        # gsettings change has time to advance past ENABLING into ENABLED
        # before we query state. Cheap and avoids spurious EnableExtension.
        to_enable = sorted(after_set - before_set)
        if to_enable:
            time.sleep(0.2)
            states = ShellReloader.list_extensions_state()
            for uuid in to_enable:
                if states.get(uuid) in _LIVE_EXT_STATES:
                    continue
                run_cmd(
                    [
                        "gdbus",
                        "call",
                        "--session",
                        "--dest",
                        DBUS_SHELL_NAME,
                        "--object-path",
                        DBUS_EXT_PATH,
                        "--method",
                        f"{DBUS_EXT_IFACE}.EnableExtension",
                        uuid,
                    ],
                    timeout=5,
                )

        # X11 reinforcement (ignored on Wayland)
        if not is_wayland():
            run_cmd(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    DBUS_SHELL_NAME,
                    "--object-path",
                    DBUS_SHELL_PATH,
                    "--method",
                    DBUS_EVAL_IFACE,
                    "global.reexec_self()",
                ],
                timeout=5,
            )

    # ── Ponto de entrada principal ────────────────────────────────────────────

    @staticmethod
    def apply_extension_state(uuid: str, enable: bool) -> Tuple[bool, str]:
        """
        Ativa ou desativa uma extensão e recarrega em tempo real.

        Fluxo:
          1. Tenta D-Bus direto (sem logout, Wayland-safe).
          2. Em caso de falha, cai para gsettings + reload geral.

        Retorna (sucesso, mensagem).
        """
        # Import aqui para evitar circular import (ExtMgr importa ShellReloader)
        from extension_manager import ExtMgr

        # 1. D-Bus direto
        ok, msg = ShellReloader.enable_extension_dbus(uuid, enable)
        if ok:
            if enable:
                ShellReloader.reload_extension(uuid)
            return True, msg

        # 2. Fallback: gsettings + reload geral
        ok2, msg2 = ExtMgr._set_enabled_gsettings(uuid, enable)
        if ok2:
            ShellReloader.reload_all()
            return True, msg2

        return False, msg2
