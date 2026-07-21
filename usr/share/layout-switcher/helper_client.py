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
import time
from pathlib import Path
from typing import Iterable, Optional, Tuple

from constants import tr

log = logging.getLogger("layout-switcher")

HELPER_UUID = "layout-switcher-helper@bigcommunity.org"

_DEST = "org.gnome.Shell"
_PATH = "/org/bigcommunity/LayoutSwitcherHelper"
_IFACE = "org.bigcommunity.LayoutSwitcherHelper"

_HELPER_DIRS = (
    Path.home() / ".local" / "share" / "gnome-shell" / "extensions" / HELPER_UUID,
    Path("/usr/share/gnome-shell/extensions") / HELPER_UUID,
    Path("/usr/local/share/gnome-shell/extensions") / HELPER_UUID,
)


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

    @staticmethod
    def required_extension_lists(
        enabled: Iterable[str],
        disabled: Iterable[str],
    ) -> Tuple[list[str], list[str]]:
        """Return Shell extension lists with the required helper enabled first."""
        enabled_out = [HELPER_UUID]
        enabled_out.extend(uuid for uuid in enabled if uuid and uuid != HELPER_UUID)
        disabled_out = [uuid for uuid in disabled if uuid and uuid != HELPER_UUID]
        return enabled_out, disabled_out

    @classmethod
    def ensure_enabled(cls) -> Tuple[bool, bool, str]:
        """Repair GNOME's extension lists without touching optional extensions."""
        if not any(path.is_dir() for path in _HELPER_DIRS):
            return False, False, tr("The required layout helper is not installed.")

        try:
            from gi.repository import Gio

            settings = Gio.Settings.new("org.gnome.shell")
            enabled = list(settings.get_strv("enabled-extensions"))
            disabled = list(settings.get_strv("disabled-extensions"))
            enabled_out, disabled_out = cls.required_extension_lists(enabled, disabled)
            changed = enabled != enabled_out or disabled != disabled_out
            if disabled != disabled_out:
                settings.set_strv("disabled-extensions", disabled_out)
            if enabled != enabled_out:
                settings.set_strv("enabled-extensions", enabled_out)
            if changed:
                Gio.Settings.sync()
            return True, changed, ""
        except Exception as exc:
            log.warning("helper: could not repair extension settings: %s", exc)
            return False, False, str(exc)

    @classmethod
    def ensure_available(cls, timeout_ms: int = 6000) -> Tuple[bool, str]:
        """Enable the required helper and wait until its D-Bus API is ready."""
        quick_timeout = min(timeout_ms, 800)
        if cls.is_available(timeout_ms=quick_timeout):
            return True, ""

        ok, _changed, info = cls.ensure_enabled()
        if not ok:
            return False, info

        deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
        while time.monotonic() < deadline:
            remaining_ms = max(100, int((deadline - time.monotonic()) * 1000))
            if cls.is_available(timeout_ms=min(remaining_ms, 800)):
                return True, ""
            time.sleep(0.1)

        return False, tr("The required layout helper did not start.")

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
    def ping_info(cls, timeout_ms: int = 6000) -> dict:
        """Parsed Ping reply ({helper, version, busy}) or {} when unavailable."""
        out = cls._call("Ping", None, timeout_ms)
        if not out:
            return {}
        try:
            return json.loads(out)
        except (ValueError, json.JSONDecodeError):
            return {}

    @classmethod
    def begin_switch(
        cls,
        persist: Iterable[str],
        label: str = "",
        label_from: str = "",
        icon_from: str = "",
        icon_to: str = "",
        timeout_ms: int = 90000,
    ) -> Tuple[bool, str]:
        """
        Clean-room protocol (helper v7), phase 1: raise the transition curtain
        (showing ``label``) and tear down every managed extension, each awaited.
        ``persist`` lists extensions to keep alive through the switch (system
        indicators). On success nothing is listening to the layout-owned dconf
        branches — the caller may reset+load them like a login does, then call
        :meth:`complete_switch`. The helper arms an auto-rollback timer in case
        the caller dies in between.
        """
        from gi.repository import GLib

        payload = json.dumps(
            {
                "persist": [u for u in persist if u],
                "label": label or "",
                "label_from": label_from or "",
                # Preview SVGs for the curtain's from→to transition art.
                "icon_from": icon_from or "",
                "icon_to": icon_to or "",
            }
        )
        out = cls._call("BeginSwitch", GLib.Variant("(s)", (payload,)), timeout_ms)
        if out is None:
            return False, "helper BeginSwitch call failed"
        try:
            result = json.loads(out)
        except (ValueError, json.JSONDecodeError):
            return False, f"helper BeginSwitch bad reply: {out}"
        if not result.get("ok", False):
            return False, result.get("error", "helper reported failure")
        return True, ", ".join(result.get("steps", []))

    @classmethod
    def complete_switch(
        cls,
        enabled: Iterable[str],
        theme_reload: bool = True,
        timeout_ms: int = 120000,
    ) -> Tuple[bool, str]:
        """
        Clean-room protocol (helper v7), phase 2: with the final dconf state on
        disk, rebuild — repair colorScheme, ``Main.loadTheme()``, enable
        ``enabled`` in order (each awaited), recompute the panel style, flash
        the checkmark and drop the curtain.
        """
        from gi.repository import GLib

        payload = json.dumps(
            {
                "enabled": [u for u in enabled if u],
                "theme_reload": bool(theme_reload),
            }
        )
        out = cls._call("CompleteSwitch", GLib.Variant("(s)", (payload,)), timeout_ms)
        if out is None:
            return False, "helper CompleteSwitch call failed"
        try:
            result = json.loads(out)
        except (ValueError, json.JSONDecodeError):
            return False, f"helper CompleteSwitch bad reply: {out}"
        if not result.get("ok", False):
            return False, result.get("error", "helper reported failure")
        return True, ", ".join(result.get("steps", []))

    @classmethod
    def abort_switch(cls, timeout_ms: int = 60000) -> bool:
        """
        Roll a begun-but-failed switch back to the pre-switch extension set
        (drops the curtain too). Safe to call when no switch is in progress.
        """
        out = cls._call("AbortSwitch", None, timeout_ms)
        if out is None:
            return False
        try:
            return bool(json.loads(out).get("ok", False))
        except (ValueError, json.JSONDecodeError):
            return False

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
