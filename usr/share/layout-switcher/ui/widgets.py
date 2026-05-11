# SPDX-License-Identifier: MIT
"""
ui/widgets.py — Widgets reutilizáveis customizados.

Contém:
  ColorDot           : círculo colorido — preview legacy de tema
  IconStrip          : faixa horizontal com 5 ícones representativos do tema
  MiniWindowPreview  : mockup de janela GTK (header bar + corpo + botão accent)
  MiniPanelPreview   : mockup do panel do GNOME Shell

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import math
from pathlib import Path
from typing import List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


# ── Helpers de cor ───────────────────────────────────────────────────────────


def _hex_to_rgb(
    hex_color: Optional[str],
    default: Tuple[float, float, float] = (0.5, 0.5, 0.5),
) -> Tuple[float, float, float]:
    """Converte ``#rrggbb``/``#rgb`` para floats 0..1. Falha → default."""
    if not hex_color:
        return default
    try:
        raw = hex_color.lstrip("#")
        if len(raw) == 3:
            raw = "".join(c * 2 for c in raw)
        return (
            int(raw[0:2], 16) / 255,
            int(raw[2:4], 16) / 255,
            int(raw[4:6], 16) / 255,
        )
    except Exception:
        return default


def _luminance(rgb: Tuple[float, float, float]) -> float:
    """sRGB relative luminance 0..1 (WCAG)."""

    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _rounded_rect(ctx, x: float, y: float, w: float, h: float, r: float) -> None:
    """Caminho de retângulo arredondado em Cairo."""
    r = max(0.0, min(r, min(w, h) / 2))
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


# ── ColorDot (legacy, ainda útil) ────────────────────────────────────────────


class ColorDot(Gtk.DrawingArea):
    """
    Círculo preenchido que representa a cor associada a um tema.
    Usa Cairo DrawingArea — cada dot pode ter cor distinta sem empilhar CSS.
    """

    def __init__(self, hex_color: str, size: int = 30) -> None:
        super().__init__()
        self._r, self._g, self._b = _hex_to_rgb(hex_color)
        self.set_size_request(size, size)
        self.set_draw_func(self._draw, None)
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        self.update_property([Gtk.AccessibleProperty.LABEL], [f"Color: {hex_color}"])

    def _draw(self, _area, ctx, w, h, _data) -> None:
        r = min(w, h) / 2 - 2
        ctx.arc(w / 2, h / 2, r, 0, 2 * math.pi)
        ctx.set_source_rgb(self._r, self._g, self._b)
        ctx.fill_preserve()
        ctx.set_source_rgba(0, 0, 0, 0.15)
        ctx.set_line_width(1.5)
        ctx.stroke()


# ── IconStrip ────────────────────────────────────────────────────────────────


class _EmptySlot(Gtk.DrawingArea):
    """Placeholder pontilhado para slot que o tema nao define."""

    def __init__(self, size: int = 18) -> None:
        super().__init__()
        self.set_size_request(size, size)
        self.set_draw_func(self._draw, None)
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["icon not defined by this theme"],
        )

    def _draw(self, _area, ctx, w, h, _data) -> None:
        ctx.set_source_rgba(0.5, 0.5, 0.5, 0.35)
        ctx.set_line_width(1.0)
        ctx.set_dash([1.6, 1.6])
        _rounded_rect(ctx, 1.5, 1.5, w - 3, h - 3, 2.0)
        ctx.stroke()


class IconStrip(Gtk.Box):
    """
    Faixa horizontal com até 5 ícones que o tema **realmente sobrescreve**
    (folder, home, mime de texto, navegador, settings). Slots que o tema
    não define mostram um placeholder pontilhado — herança via
    ``Index.theme`` é deliberadamente ignorada para que cada tema mostre
    o que ele de fato traz, em vez de convergir nos ícones do Adwaita.
    """

    _SLOT_COUNT = 5

    def __init__(self, icon_paths: List[Optional[Path]], slot_size: int = 18) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.add_css_class("theme-icon-strip")
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Icon theme preview"])

        for i in range(self._SLOT_COUNT):
            path = icon_paths[i] if i < len(icon_paths) else None
            child = self._build_slot(path, slot_size)
            child.set_valign(Gtk.Align.CENTER)
            self.append(child)

    @staticmethod
    def _build_slot(path: Optional[Path], size: int) -> Gtk.Widget:
        if path is not None and path.is_file():
            pic = Gtk.Picture.new_for_filename(str(path))
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            pic.set_size_request(size, size)
            pic.set_can_shrink(True)
            return pic
        return _EmptySlot(size)


# ── MiniWindowPreview (GTK theme) ────────────────────────────────────────────


class MiniWindowPreview(Gtk.DrawingArea):
    """
    Mockup compacto de janela GTK: header bar + corpo + um botão accent.
    Heuristica light/dark a partir do nome do tema decide as cores neutras;
    a cor accent vem do CSS quando extraivel, senão de ``color_from_name``.
    """

    def __init__(
        self,
        accent_hex: str,
        dark: bool = False,
        width: int = 60,
        height: int = 34,
    ) -> None:
        super().__init__()
        self._accent = _hex_to_rgb(accent_hex)
        self._dark = dark
        if dark:
            self._body = (0.16, 0.16, 0.18)
            self._header = (0.10, 0.10, 0.12)
            self._line = (1.0, 1.0, 1.0, 0.18)
            self._border = (0, 0, 0, 0.55)
        else:
            self._body = (0.98, 0.98, 0.98)
            self._header = (0.92, 0.92, 0.93)
            self._line = (0, 0, 0, 0.18)
            self._border = (0, 0, 0, 0.22)
        self.set_size_request(width, height)
        self.set_draw_func(self._draw, None)
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"GTK theme preview accent {accent_hex}"],
        )

    def _draw(self, _area, ctx, w, h, _data) -> None:
        margin = 1.0
        x = margin
        y = margin
        ww = w - 2 * margin
        hh = h - 2 * margin
        radius = 4.0

        # Corpo
        _rounded_rect(ctx, x, y, ww, hh, radius)
        ctx.set_source_rgb(*self._body)
        ctx.fill_preserve()
        ctx.set_source_rgba(*self._border)
        ctx.set_line_width(1.0)
        ctx.stroke()

        # Header bar (top ~38%) clipado ao retângulo arredondado
        hb_h = max(8.0, hh * 0.38)
        ctx.save()
        _rounded_rect(ctx, x, y, ww, hh, radius)
        ctx.clip()
        ctx.rectangle(x, y, ww, hb_h)
        ctx.set_source_rgb(*self._header)
        ctx.fill()
        ctx.restore()

        # Separador sob o header
        ctx.set_source_rgba(*self._line)
        ctx.set_line_width(1.0)
        ctx.move_to(x, y + hb_h + 0.5)
        ctx.line_to(x + ww, y + hb_h + 0.5)
        ctx.stroke()

        # "Title" abstrato no header: 2 dashes
        title_y = y + hb_h / 2
        title_h = max(1.5, hb_h * 0.25)
        ctx.set_source_rgba(*self._line)
        ctx.rectangle(x + 4, title_y - title_h / 2, ww * 0.22, title_h)
        ctx.fill()

        # Botão "close" accent no canto direito do header
        close_r = max(1.8, hb_h * 0.22)
        close_cx = x + ww - 5 - close_r
        close_cy = y + hb_h / 2
        ctx.arc(close_cx, close_cy, close_r, 0, 2 * math.pi)
        ctx.set_source_rgb(*self._accent)
        ctx.fill()

        # Conteúdo do corpo: pill accent + duas linhas de texto fake
        body_top = y + hb_h + 3
        body_bot = y + hh - 3
        body_h = max(0.0, body_bot - body_top)

        pill_h = max(5.0, body_h * 0.50)
        pill_w = ww * 0.34
        pill_x = x + 4
        pill_y = body_top + (body_h - pill_h) / 2
        _rounded_rect(ctx, pill_x, pill_y, pill_w, pill_h, pill_h / 2)
        ctx.set_source_rgb(*self._accent)
        ctx.fill()

        # Linhas de "texto" ao lado do botão
        line_x = pill_x + pill_w + 4
        line_w = (x + ww - 4) - line_x
        if line_w > 4:
            ctx.set_source_rgba(*self._line)
            for frac in (0.32, 0.70):
                ly = pill_y + pill_h * frac
                ctx.rectangle(line_x, ly, line_w, max(1.0, pill_h * 0.14))
                ctx.fill()


# ── MiniPanelPreview (GNOME Shell theme) ─────────────────────────────────────


class MiniPanelPreview(Gtk.DrawingArea):
    """
    Mockup do top panel do GNOME Shell + uma área de tela embaixo.
    A cor do panel vem de ``#panel { background-color: ... }`` quando
    extraivel; senão preto translúcido típico do Shell. O accent destaca
    "Activities" e a área central da tela como hint de janela ativa.
    """

    def __init__(
        self,
        panel_hex: Optional[str],
        accent_hex: str,
        width: int = 60,
        height: int = 34,
    ) -> None:
        super().__init__()
        self._panel = _hex_to_rgb(panel_hex, default=(0.10, 0.10, 0.11))
        self._accent = _hex_to_rgb(accent_hex)
        # Cor do "ícone" no panel: clara se panel escuro, escura se claro
        lum = _luminance(self._panel)
        self._panel_fg = (0.95, 0.95, 0.95) if lum < 0.5 else (0.15, 0.15, 0.15)
        self.set_size_request(width, height)
        self.set_draw_func(self._draw, None)
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [f"Shell theme preview accent {accent_hex}"],
        )

    def _draw(self, _area, ctx, w, h, _data) -> None:
        margin = 1.0
        x = margin
        y = margin
        ww = w - 2 * margin
        hh = h - 2 * margin
        radius = 4.0

        # Tela (wallpaper genérico claro-azulado)
        _rounded_rect(ctx, x, y, ww, hh, radius)
        ctx.set_source_rgb(0.82, 0.85, 0.90)
        ctx.fill_preserve()
        ctx.set_source_rgba(0, 0, 0, 0.22)
        ctx.set_line_width(1.0)
        ctx.stroke()

        # Panel no topo (~28%) clipado ao retângulo arredondado
        pb_h = max(7.0, hh * 0.28)
        ctx.save()
        _rounded_rect(ctx, x, y, ww, hh, radius)
        ctx.clip()
        ctx.rectangle(x, y, ww, pb_h)
        ctx.set_source_rgb(*self._panel)
        ctx.fill()
        ctx.restore()

        cy = y + pb_h / 2

        # Indicador "Activities" (accent) à esquerda
        act_r = max(1.5, pb_h * 0.22)
        ctx.arc(x + 4, cy, act_r, 0, 2 * math.pi)
        ctx.set_source_rgb(*self._accent)
        ctx.fill()

        # "Relógio" centralizado no panel — pílula em fg do panel
        clock_w = ww * 0.20
        clock_h = max(1.5, pb_h * 0.32)
        clock_x = x + (ww - clock_w) / 2
        clock_y = cy - clock_h / 2
        _rounded_rect(ctx, clock_x, clock_y, clock_w, clock_h, clock_h / 2)
        ctx.set_source_rgb(*self._panel_fg)
        ctx.fill()

        # Indicadores de bandeja à direita (2 dots)
        tray_r = max(1.0, pb_h * 0.16)
        for i in range(2):
            tx = x + ww - 4 - tray_r - i * (tray_r * 2 + 2)
            ctx.arc(tx, cy, tray_r, 0, 2 * math.pi)
            ctx.set_source_rgb(*self._panel_fg)
            ctx.fill()

        # Janela "ativa" no corpo da tela com leve sombra + borda accent
        body_top = y + pb_h + 2
        body_bot = y + hh - 2
        body_h = max(0.0, body_bot - body_top)
        if body_h <= 0:
            return

        win_w = ww * 0.68
        win_h = body_h * 0.78
        win_x = x + (ww - win_w) / 2
        win_y = body_top + (body_h - win_h) / 2
        win_r = 2.5

        # sombra fake
        _rounded_rect(ctx, win_x + 0.8, win_y + 1.0, win_w, win_h, win_r)
        ctx.set_source_rgba(0, 0, 0, 0.18)
        ctx.fill()

        _rounded_rect(ctx, win_x, win_y, win_w, win_h, win_r)
        ctx.set_source_rgb(0.97, 0.97, 0.98)
        ctx.fill_preserve()
        ctx.set_source_rgba(*self._accent, 0.85)
        ctx.set_line_width(1.0)
        ctx.stroke()

        # Faixa de headerbar accent na janelinha
        head_h = max(2.0, win_h * 0.30)
        ctx.save()
        _rounded_rect(ctx, win_x, win_y, win_w, win_h, win_r)
        ctx.clip()
        ctx.rectangle(win_x, win_y, win_w, head_h)
        ctx.set_source_rgba(*self._accent, 0.85)
        ctx.fill()
        ctx.restore()
