# SPDX-License-Identifier: MIT
"""
layout_applier.py — Aplica layouts de desktop via dconf.

Após carregar o layout, recarrega extensões em tempo real via ShellReloader
sem necessidade de logout ou reinicialização.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

from pathlib import Path
from typing import Tuple

from shell_reloader import ShellReloader
from utils import run_cmd


class LayoutApplier:
    """
    Aplica arquivos de layout (formato dconf dump) ao GNOME Shell.

    Os arquivos de layout devem estar no formato produzido por:
        dconf dump /org/gnome/shell/ > layout.txt

    Após aplicar, as extensões são recarregadas em tempo real via D-Bus.
    """

    @staticmethod
    def apply(config_path: Path) -> Tuple[bool, str]:
        """
        Lê o arquivo de layout e aplica via dconf load.

        Após a aplicação bem-sucedida:
          - Recarrega extensões via ShellReloader.reload_all()
          - Não requer logout

        Retorna (True, "") em caso de sucesso ou (False, mensagem_erro).
        """
        if not config_path or not config_path.exists():
            return False, f"layout file not found: {config_path}"

        try:
            data = config_path.read_text(encoding="utf-8")
        except Exception as exc:
            return False, f"cannot read layout file: {exc}"

        if not data.strip():
            return False, "layout file is empty"

        ok, msg = run_cmd(
            ["dconf", "load", "/org/gnome/shell/"],
            stdin_text=data,
            timeout=15,
        )
        if ok:
            # Recarrega extensões imediatamente após aplicar o layout
            ShellReloader.reload_all()

        return ok, msg
