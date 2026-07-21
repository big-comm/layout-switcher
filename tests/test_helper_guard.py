# SPDX-License-Identifier: MIT
"""Static checks for the required helper session guard."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTOSTART = (
    ROOT
    / "etc/xdg/autostart/org.communitybig.layout-switcher-helper-guard.desktop"
)


def test_guard_autostart_uses_modern_gnome_session_path():
    desktop = AUTOSTART.read_text()

    assert "Exec=/usr/bin/layout-switcher-helper-guard" in desktop
    assert "OnlyShowIn=GNOME;" in desktop
    assert "X-GNOME-Autostart-enabled=true" in desktop
    assert "X-GNOME-Autostart-Phase" not in desktop


def test_guard_launcher_is_executable():
    launcher = ROOT / "usr/bin/layout-switcher-helper-guard"

    assert launcher.stat().st_mode & 0o111
    assert "helper_guard.py" in launcher.read_text()
