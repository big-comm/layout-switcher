# SPDX-License-Identifier: MIT
"""Static checks for the in-shell layout switch helper."""

from pathlib import Path

HELPER = (
    Path(__file__).resolve().parents[1]
    / "usr/share/gnome-shell/extensions/layout-switcher-helper@bigcommunity.org/extension.js"
)


def test_live_color_switch_empties_shell_rebase_slices():
    source = HELPER.read_text()

    assert source.index("_moveExtensionLast(mgr, uuid)") < source.index(
        "mgr.disableExtension(uuid)"
    )
    assert source.index("_moveExtensionLast(mgr, DTP_UUID)") < source.index(
        "mgr.disableExtension(DTP_UUID)"
    )
    assert "const CLASSIC_MENU_LAYOUT = 1" in source
    assert "const HYBRID_MENU_LAYOUT = 4" in source
    assert "const ARCMENU_UUID = 'arcmenu@arcmenu.com'" in source
    assert "const ARCMENU_HYBRID_LAYOUT = 'enterprise'" in source
    assert "COMMUNITY_LIGHT_ICON_LAYOUTS = new Set([CLASSIC_MENU_LAYOUT, HYBRID_MENU_LAYOUT])" in source
    assert "? 'bigicons-papient-dark'" in source
    assert "? 'bigicons-papient-light'" in source
    assert "ORCHIS_SHELL_DARK = 'Big-Blue'" in source
    assert "ORCHIS_SHELL_LIGHT = 'Big-Blue-Light'" in source
    assert "const DESK_UX_MENU_LAYOUT = 3" in source
    assert "const nativeShell = communityLayout === CLASSIC_MENU_LAYOUT" in source
    assert "communityLayout === HYBRID_MENU_LAYOUT || hybridArcMenu" in source
    assert "explicitLightIcons = hybridArcMenu" in source
    assert "(!live.has(COMMUNITY_MENU_UUID) && !hybridArcMenu)" in source
    assert "const deskUxOrchisShell = communityLayout === DESK_UX_MENU_LAYOUT" in source
    assert "? [LIGHT_STYLE_UUID, USER_THEME_UUID]" in source
    assert "if (!(nativeShell && dark) && !isLive(wantOn))" in source
    assert "Main.setThemeStylesheet(null)" in source
