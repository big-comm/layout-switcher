# SPDX-License-Identifier: MIT
"""
ui/widgets.py — Widgets reutilizáveis customizados.

Contém:
  ColorDot : círculo colorido para representar a cor de um tema

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class ColorDot(Gtk.DrawingArea):
    """
    Círculo preenchido que representa a cor associada a um tema.
    Usado nos cards de tema na aba Themes.
    """

    def __init__(self, hex_color: str, size: int = 30) -> None:
        super().__init__()
        try:
            self._r = int(hex_color[1:3], 16) / 255
            self._g = int(hex_color[3:5], 16) / 255
            self._b = int(hex_color[5:7], 16) / 255
        except Exception:
            self._r = self._g = self._b = 0.5
        self.set_size_request(size, size)
        self.set_draw_func(self._draw, None)

    def _draw(self, area, ctx, w, h, data) -> None:
        r = min(w, h) / 2 - 2
        ctx.arc(w / 2, h / 2, r, 0, 2 * math.pi)
        ctx.set_source_rgb(self._r, self._g, self._b)
        ctx.fill_preserve()
        ctx.set_source_rgba(0, 0, 0, 0.15)
        ctx.set_line_width(1.5)
        ctx.stroke()
