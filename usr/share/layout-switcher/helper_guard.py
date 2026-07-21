# SPDX-License-Identifier: MIT
"""Keep the required in-shell layout helper enabled for the user session."""

import logging

from constants import ICON_NAME, tr
from helper_client import HelperClient

log = logging.getLogger("layout-switcher-helper-guard")


class HelperGuard:
    """Monitor only the two Shell lists that can disable the required helper."""

    def __init__(self) -> None:
        from gi.repository import Gio

        self._settings = Gio.Settings.new("org.gnome.shell")
        self._pending_source = 0

    def start(self) -> None:
        from gi.repository import GLib

        ok, changed, info = HelperClient.ensure_enabled()
        if not ok:
            log.warning("initial helper repair failed: %s", info)
        elif changed:
            self._notify_repair()

        self._settings.connect("changed::enabled-extensions", self._on_settings_changed)
        self._settings.connect("changed::disabled-extensions", self._on_settings_changed)
        self._loop = GLib.MainLoop()
        self._loop.run()

    def _on_settings_changed(self, settings, key: str) -> None:
        from gi.repository import GLib

        if self._pending_source:
            return
        self._pending_source = GLib.timeout_add(80, self._repair)

    def _repair(self) -> bool:
        self._pending_source = 0
        ok, changed, info = HelperClient.ensure_enabled()
        if not ok:
            log.warning("helper repair failed: %s", info)
        elif changed:
            self._notify_repair()
        return False

    @staticmethod
    def _notify_repair() -> None:
        """Use the desktop notification D-Bus API without a libnotify dependency."""
        try:
            from gi.repository import Gio, GLib

            proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.NONE,
                None,
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications",
                None,
            )
            args = GLib.Variant(
                "(susssasa{sv}i)",
                (
                    "Layout Switcher",
                    0,
                    ICON_NAME,
                    tr("Layout helper restored"),
                    tr("The required layout helper was re-enabled automatically."),
                    [],
                    {},
                    5000,
                ),
            )
            proxy.call_sync("Notify", args, Gio.DBusCallFlags.NONE, 3000, None)
        except Exception as exc:
            log.debug("notification failed: %s", exc)


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    HelperGuard().start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
