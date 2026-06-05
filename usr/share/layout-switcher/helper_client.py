# SPDX-License-Identifier: MIT
"""
helper_client.py — D-Bus client for the in-shell layout-switcher-helper.

The companion GNOME Shell extension
``layout-switcher-helper@bigcommunity.org`` performs the live layout switch
from INSIDE gnome-shell (enable/disable/reload via ``Main.extensionManager``
+ ``Main.loadTheme``, sequenced on the shell's main loop). Doing it in-shell
avoids the cross-process race that hangs gnome-shell on heavy transitions and
lets appearance-owning extensions (dash-to-panel, arcmenu, kiwi, light-style)
re-apply their theme without a logout — neither of which is possible from an
external process on GNOME 45+ (the D-Bus ReloadExtension was deprecated).

This module is the thin client the app uses to drive it. When the helper
isn't installed/enabled, ``is_available()`` returns False and the caller
falls back to the legacy external disable/enable path.

The D-Bus calls go in-process via Gio (the JSON reply parses cleanly as a
native string). gi is imported lazily so this module stays importable in the
test environment without a display.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import json
import logging
from typing import Iterable, Optional, Tuple

log = logging.getLogger("layout-switcher")

HELPER_UUID = "layout-switcher-helper@bigcommunity.org"

_DEST = "org.gnome.Shell"
_PATH = "/org/bigcommunity/LayoutSwitcherHelper"
_IFACE = "org.bigcommunity.LayoutSwitcherHelper"


class HelperClient:
    """Drives the in-shell layout-switcher-helper extension over D-Bus."""

    _bus = None

    @classmethod
    def _session_bus(cls):
        if cls._bus is None:
            try:
                from gi.repository import Gio

                cls._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            except Exception as exc:
                log.debug("helper: no session bus: %s", exc)
                cls._bus = None
        return cls._bus

    @classmethod
    def _call(cls, method: str, args, timeout_ms: int) -> Optional[str]:
        """Call a helper method returning ``(s)``; returns the string or None."""
        bus = cls._session_bus()
        if bus is None:
            return None
        try:
            from gi.repository import Gio, GLib

            reply = bus.call_sync(
                _DEST,
                _PATH,
                _IFACE,
                method,
                args,
                GLib.VariantType("(s)"),
                Gio.DBusCallFlags.NONE,
                timeout_ms,
                None,
            )
            return reply.unpack()[0]
        except Exception as exc:
            log.debug("helper %s failed: %s", method, exc)
            return None

    @classmethod
    def is_available(cls, timeout_ms: int = 6000) -> bool:
        """True if the helper extension is loaded and answering Ping."""
        out = cls._call("Ping", None, timeout_ms)
        return bool(out and "layout-switcher" in out)

    @classmethod
    def helper_version(cls, timeout_ms: int = 6000) -> int:
        """
        Protocol version reported by the loaded helper (Ping's ``version``), or
        0 if unavailable/unparseable. The app uses this to tell whether the live
        helper already sequences loadTheme before re-enabling the appearance
        extensions (v3+) or still needs the external post-reload workaround (v2).
        """
        out = cls._call("Ping", None, timeout_ms)
        if not out:
            return 0
        try:
            return int(json.loads(out).get("version", 0))
        except (ValueError, TypeError, json.JSONDecodeError):
            return 0

    @classmethod
    def reload_extension(cls, uuid: str, timeout_ms: int = 20000) -> bool:
        """
        Ask the helper to reload one extension in-shell (trulyReload). Recovers
        an extension stuck in ERROR — a plain enable does not clear that state.
        """
        from gi.repository import GLib

        out = cls._call("ReloadExtension", GLib.Variant("(s)", (uuid,)), timeout_ms)
        return out is not None

    @classmethod
    def apply_layout(
        cls,
        enabled: Iterable[str],
        reload: Optional[Iterable[str]] = None,
        teardown: Optional[Iterable[str]] = None,
        step_ms: int = 150,
        timeout_ms: int = 60000,
    ) -> Tuple[bool, str]:
        """
        Ask the helper to switch to ``enabled`` (the target
        ``enabled-extensions``). ``reload`` lists appearance-owning extensions
        that STAY and must re-read their config; ``teardown`` lists dock/panel
        owners that, when LEAVING, must be reloaded-then-disabled so their
        actor is destroyed cleanly (no ghost dock/bar). The helper filters both
        to the ones that actually apply, and never disables itself. Returns
        ``(ok, message)``.
        """
        from gi.repository import GLib

        payload = json.dumps(
            {
                "enabled": [u for u in enabled if u],
                "reload": [u for u in (reload or []) if u],
                "teardown": [u for u in (teardown or []) if u],
                "step_ms": int(step_ms),
            }
        )
        out = cls._call("ApplyLayout", GLib.Variant("(s)", (payload,)), timeout_ms)
        if out is None:
            return False, "helper ApplyLayout call failed"
        try:
            result = json.loads(out)
        except (ValueError, json.JSONDecodeError):
            return True, out
        if not result.get("ok", True):
            return False, result.get("error", "helper reported failure")
        return True, ", ".join(result.get("steps", []))
