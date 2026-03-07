# SPDX-License-Identifier: MIT
"""
community_layout_switcher/ui — Pacote de interface gráfica.

Exporta:
  MainWindow  : janela principal
  LayoutsPage : página de layouts
  ExtensionsPage : página de extensões
  ThemesPage  : página de temas
  ColorDot    : widget de cor reutilizável
"""

from .window import MainWindow
from .page_layouts import LayoutsPage
from .page_extensions import ExtensionsPage
from .page_themes import ThemesPage
from .widgets import ColorDot

__all__ = [
    "MainWindow",
    "LayoutsPage",
    "ExtensionsPage",
    "ThemesPage",
    "ColorDot",
]
