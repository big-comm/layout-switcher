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

import shutil
from typing import Tuple

from constants import (
    DBUS_EVAL_IFACE,
    DBUS_EXT_IFACE,
    DBUS_EXT_PATH,
    DBUS_SHELL_NAME,
    DBUS_SHELL_PATH,
)
from utils import is_wayland, run_cmd


class ShellReloader:
    """
    Recarrega o GNOME Shell / extensões em tempo real sem logout.

    Uso típico:
        ok, msg = ShellReloader.apply_extension_state(uuid, enable=True)
        ShellReloader.reload_all()
    """

    # ── Recarga de extensão individual ────────────────────────────────────────

    @staticmethod
    def reload_extension(uuid: str) -> bool:
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
            timeout=8,
        )
        return ok

    # ── Ativar / desativar via D-Bus ──────────────────────────────────────────

    @staticmethod
    def enable_extension_dbus(uuid: str, enable: bool) -> Tuple[bool, str]:
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
            timeout=8,
        )
        return ok, out

    # ── Recarga geral ─────────────────────────────────────────────────────────

    @staticmethod
    def reload_all() -> None:
        """
        Solicita recarga geral de extensões ao Shell.
        Tenta múltiplas estratégias; nunca levanta exceção.
        """
        # Estratégia 1: D-Bus Extensions API (GS 40+, Wayland-safe)
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
                f"{DBUS_EXT_IFACE}.ReloadExtension",
                "",
            ],
            timeout=5,
        )

        # Estratégia 2: gnome-extensions CLI
        if shutil.which("gnome-extensions"):
            run_cmd(["gnome-extensions", "reset"], timeout=5)

        # Estratégia 3: Eval reexec (X11 somente — ignorado silenciosamente no Wayland)
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
            ShellReloader.reload_extension(uuid)
            return True, msg

        # 2. Fallback: gsettings + reload geral
        ok2, msg2 = ExtMgr._set_enabled_gsettings(uuid, enable)
        if ok2:
            ShellReloader.reload_all()
            return True, msg2

        return False, msg2
