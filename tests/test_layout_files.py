# SPDX-License-Identifier: MIT
"""Tests for shipped layout dump portability."""

import ast
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
COMMUNITY_MENU_UUID = "community-menu@bigcommunity.org"
ARCMENU_UUID = "arcmenu@arcmenu.com"
DASH_TO_PANEL_UUID = "dash-to-panel@jderose9.github.com"
USER_THEME_UUID = "user-theme@gnome-shell-extensions.gcampax.github.com"
LIGHT_STYLE_UUID = "light-style@gnome-shell-extensions.gcampax.github.com"
LAYOUT_SWITCHER_HELPER_UUID = "layout-switcher-helper@bigcommunity.org"
COMMUNITY_MENU_LAYOUTS = {
    "classic.txt": "APPS_ONLY",
    "desk-ux.txt": "APP_GRID",
    "hybrid.txt": "MINT",
}
NON_COMMUNITY_MENU_LAYOUTS = {"biggnome.txt", "g-unity.txt", "minimal.txt"}


def _read_key_values(layout_text: str):
    for line in layout_text.splitlines():
        if "=" not in line or line.startswith("["):
            continue
        key, value = line.split("=", 1)
        yield key, value


def _section_key_values(layout_text: str, wanted_section: str) -> dict[str, str]:
    section = ""
    values = {}
    for raw_line in layout_text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == wanted_section and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _shell_extension_lists(layout_text: str) -> tuple[list[str], list[str]]:
    values = _section_key_values(layout_text, "org/gnome/shell")
    enabled = ast.literal_eval(values["enabled-extensions"])
    disabled = ast.literal_eval(values["disabled-extensions"])
    return enabled, disabled


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


def test_layout_switcher_helper_is_always_first_and_enabled():
    for layout_file in LAYOUT_DIR.glob("*.txt"):
        enabled, disabled = _shell_extension_lists(layout_file.read_text())
        assert enabled[0] == LAYOUT_SWITCHER_HELPER_UUID
        assert enabled.count(LAYOUT_SWITCHER_HELPER_UUID) == 1
        assert LAYOUT_SWITCHER_HELPER_UUID not in disabled


def test_community_menu_layout_mapping_and_panel_order():
    for filename, menu_layout in COMMUNITY_MENU_LAYOUTS.items():
        text = (LAYOUT_DIR / filename).read_text()
        enabled, disabled = _shell_extension_lists(text)
        menu_values = _section_key_values(
            text,
            "org/gnome/shell/extensions/community-menu",
        )
        dtp_values = _section_key_values(
            text,
            "org/gnome/shell/extensions/dash-to-panel",
        )
        interface_values = _section_key_values(text, "org/gnome/desktop/interface")

        assert menu_values == {"layout": f"'{menu_layout}'"}
        assert dtp_values["hide-overview-on-startup"] == "true"
        assert COMMUNITY_MENU_UUID in enabled
        assert COMMUNITY_MENU_UUID not in disabled
        assert ARCMENU_UUID not in enabled
        assert ARCMENU_UUID in disabled
        assert enabled.index(DASH_TO_PANEL_UUID) < enabled.index(COMMUNITY_MENU_UUID)
        if filename in {"classic.txt", "hybrid.txt"}:
            assert interface_values["icon-theme"] == "'bigicons-papient-light'"
            user_theme_values = _section_key_values(
                text,
                "org/gnome/shell/extensions/user-theme",
            )
            assert user_theme_values["name"] == "''"
            assert USER_THEME_UUID not in enabled
            assert USER_THEME_UUID in disabled
            assert LIGHT_STYLE_UUID in enabled
            assert LIGHT_STYLE_UUID not in disabled
        elif filename == "desk-ux.txt":
            assert interface_values["icon-theme"] == "'bigicons-papient-dark'"

        if filename == "hybrid.txt":
            assert dtp_values["appicon-margin"] == "0"
            assert dtp_values["appicon-padding"] == "1"
            assert dtp_values["panel-sizes"] == "'{\"0\":38}'"
            assert dtp_values["leftbox-padding"] == "6"
            assert dtp_values["animate-appicon-hover-animation-type"] == "'SIMPLE'"
            assert "'SIMPLE': uint32 220" in dtp_values[
                "animate-appicon-hover-animation-duration"
            ]
            assert "'SIMPLE': 0.080000000000000002" in dtp_values[
                "animate-appicon-hover-animation-travel"
            ]


def test_normal_layout_switch_uses_only_shell_curtain():
    source = (
        Path(__file__).resolve().parents[1]
        / "usr/share/layout-switcher/ui/page_layouts.py"
    ).read_text()
    apply_source = source.split("    def _apply(", 1)[1].split("    def _done(", 1)[0]

    assert "begin_loading(" not in apply_source
    assert "show_loading(" not in apply_source
    assert "timeout_add(400" not in apply_source
    assert "icon_from=str(from_icon)" in apply_source
    assert "icon_to=str(to_icon)" in apply_source


def test_only_desk_ux_uses_floating_panel_geometry():
    for layout_file in LAYOUT_DIR.glob("*.txt"):
        values = _section_key_values(
            layout_file.read_text(),
            "org/gnome/shell/extensions/dash-to-panel",
        )
        if layout_file.name == "desk-ux.txt":
            assert values["panel-side-margins"] == "3"
            assert values["panel-top-bottom-margins"] == "3"
            assert values["global-border-radius"] == "4"
        else:
            assert values.get("panel-side-margins", "0") == "0"
            assert values.get("panel-top-bottom-margins", "0") == "0"


def test_community_menu_is_disabled_outside_its_three_layouts():
    for filename in NON_COMMUNITY_MENU_LAYOUTS:
        text = (LAYOUT_DIR / filename).read_text()
        enabled, disabled = _shell_extension_lists(text)

        assert COMMUNITY_MENU_UUID not in enabled
        assert COMMUNITY_MENU_UUID in disabled
        assert ARCMENU_UUID not in enabled
        assert ARCMENU_UUID in disabled


def test_layouts_do_not_ship_arcmenu_settings():
    section = "[org/gnome/shell/extensions/arcmenu]"
    for layout_file in LAYOUT_DIR.glob("*.txt"):
        assert section not in layout_file.read_text()
