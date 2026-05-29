# SPDX-License-Identifier: MIT
"""Tests for shipped layout dump portability."""

import json
from pathlib import Path


LAYOUT_DIR = Path(__file__).resolve().parents[1] / "usr/share/layout-switcher/layouts"
MONITOR_KEYED_DTP_KEYS = {
    "panel-anchors",
    "panel-element-positions",
    "panel-lengths",
    "panel-positions",
    "panel-sizes",
}
MACHINE_MONITOR_IDS = {
    "Virtual-1",
    "eDP-1",
    "HDMI-1",
    "unknown-unknown",
}


def _read_key_values(layout_text: str):
    for line in layout_text.splitlines():
        if "=" not in line or line.startswith("["):
            continue
        key, value = line.split("=", 1)
        yield key, value


def test_layout_dumps_do_not_ship_machine_monitor_ids():
    for layout_file in LAYOUT_DIR.glob("*.txt"):
        text = layout_file.read_text()
        for monitor_id in MACHINE_MONITOR_IDS:
            assert monitor_id not in text, f"{layout_file.name} contains {monitor_id}"


def test_dash_to_dock_uses_primary_monitor_template():
    for layout_file in LAYOUT_DIR.glob("*.txt"):
        values = dict(_read_key_values(layout_file.read_text()))
        assert values.get("preferred-monitor-by-connector") == "'primary'"


def test_dash_to_panel_monitor_maps_use_neutral_index():
    for layout_file in LAYOUT_DIR.glob("*.txt"):
        for key, value in _read_key_values(layout_file.read_text()):
            if key not in MONITOR_KEYED_DTP_KEYS:
                continue

            data = json.loads(value.strip().strip("'"))
            assert set(data) in (set(), {"0"}), f"{layout_file.name}:{key} is not neutral"
