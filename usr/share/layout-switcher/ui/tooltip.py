# SPDX-License-Identifier: MIT
"""
ui/tooltip.py — Elegant popover-based tooltip helper.

Minimal adaptation of the pattern used in ``big-video-converter``: a single
reusable ``Gtk.Popover`` parented to whichever widget is currently hovered,
with fade-in animation via a CSS class. Native GTK tooltips are used as a
fallback on X11 backends, where popover reparenting can crash with some
compositors.

Use via ``Tooltip.attach(widget, "some text")``. The helper keeps an
instance per display, so call sites do not need to manage state.

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

_CSS = b"""
popover.layout-tooltip {
    opacity: 0;
    transition: opacity 180ms ease-in-out;
}
popover.layout-tooltip.visible {
    opacity: 1;
}
popover.layout-tooltip > contents {
    background-color: alpha(#1d1d1d, 0.96);
    background-image: none;
    color: #f0f0f0;
    border: 1px solid alpha(#ffffff, 0.14);
    border-radius: 8px;
    padding: 8px 12px;
    box-shadow: 0 6px 16px alpha(#000000, 0.35);
}
popover.layout-tooltip label {
    color: #f0f0f0;
    font-size: 13px;
}
"""

_HOVER_DELAY_MS = 400


def _is_x11() -> bool:
    try:
        display = Gdk.Display.get_default()
        return display is not None and "X11" in type(display).__name__
    except Exception:
        return False


class Tooltip:
    """Singleton-per-process popover tooltip manager."""

    _instance: "Tooltip | None" = None

    def __init__(self) -> None:
        self._use_native = _is_x11()
        self._active: Gtk.Widget | None = None
        self._show_timer: int | None = None

        if self._use_native:
            self._popover = None
            self._label = None
            return

        self._popover = Gtk.Popover()
        self._popover.set_autohide(False)
        self._popover.set_has_arrow(False)
        self._popover.set_position(Gtk.PositionType.BOTTOM)
        self._popover.set_offset(0, 6)
        self._popover.add_css_class("layout-tooltip")

        self._label = Gtk.Label(
            wrap=True,
            max_width_chars=42,
            halign=Gtk.Align.START,
            justify=Gtk.Justification.LEFT,
        )
        self._popover.set_child(self._label)

        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 50
            )

        self._popover.connect("map", lambda p: p.add_css_class("visible"))

    # ── API publica ──────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "Tooltip":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def attach(cls, widget: Gtk.Widget, text: str) -> None:
        """Attach a popover tooltip to ``widget`` (falls back to native tooltip on X11)."""
        if not text:
            return
        inst = cls.get()
        if inst._use_native:
            widget.set_tooltip_text(text)
            return

        widget._tooltip_text = text  # type: ignore[attr-defined]
        if getattr(widget, "_tooltip_attached", False):
            return
        widget._tooltip_attached = True  # type: ignore[attr-defined]

        controller = Gtk.EventControllerMotion.new()
        controller.connect("enter", inst._on_enter, widget)
        controller.connect("leave", inst._on_leave)
        widget.add_controller(controller)

    # ── Eventos ──────────────────────────────────────────────────────────────

    def _on_enter(self, _ctl, _x, _y, widget: Gtk.Widget) -> None:
        if self._active is widget:
            return
        self._cancel_pending()
        self._hide()
        self._active = widget
        self._show_timer = GLib.timeout_add(_HOVER_DELAY_MS, self._show)

    def _on_leave(self, _ctl) -> None:
        self._cancel_pending()
        self._active = None
        self._hide()

    def _cancel_pending(self) -> None:
        if self._show_timer is not None:
            GLib.source_remove(self._show_timer)
            self._show_timer = None

    def _show(self) -> bool:
        self._show_timer = None
        widget = self._active
        if widget is None or self._popover is None or self._label is None:
            return GLib.SOURCE_REMOVE

        try:
            if not widget.get_mapped() or not widget.get_visible():
                self._active = None
                return GLib.SOURCE_REMOVE

            text = getattr(widget, "_tooltip_text", "")
            if not text:
                return GLib.SOURCE_REMOVE

            self._label.set_text(text)
            if self._popover.get_parent() is not None:
                self._popover.unparent()
            self._popover.remove_css_class("visible")
            self._popover.set_parent(widget)
            self._popover.popup()
        except Exception:
            self._active = None
        return GLib.SOURCE_REMOVE

    def _hide(self) -> None:
        if self._popover is None:
            return
        try:
            self._popover.remove_css_class("visible")
            if self._popover.is_visible():
                self._popover.popdown()
            if self._popover.get_parent() is not None:
                self._popover.unparent()
        except Exception:
            pass
