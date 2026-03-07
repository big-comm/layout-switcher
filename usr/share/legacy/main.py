#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
main.py — Ponto de entrada do Community Layout Switcher.

Uso:
    python3 main.py
    community-layout-switcher          # via /usr/bin/community-layout-switcher

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
`tr = gettext.gettext` is the translation function.
"""

import sys

# Garante que o diretório do projeto está no path quando executado diretamente
from pathlib import Path
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gio

from community_layout_switcher.constants import APP_ID, tr
from community_layout_switcher.ui.window import MainWindow


class App(Adw.Application):
    """
    Classe de aplicativo GTK/Adwaita.

    Registra a ação de saída (Ctrl+Q) e instancia a janela principal.
    """

    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        self.connect("activate", self._on_activate)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda a, p: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

    def _on_activate(self, app: "App") -> None:
        win = MainWindow(self)
        win.present()


def main() -> int:
    """Inicializa e executa o aplicativo. Retorna o código de saída."""
    app = App()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
