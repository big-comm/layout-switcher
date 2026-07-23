# SPDX-License-Identifier: MIT
"""Static checks for the in-shell layout switch helper."""

from pathlib import Path

HELPER = (
    Path(__file__).resolve().parents[1]
    / "usr/share/gnome-shell/extensions/layout-switcher-helper@bigcommunity.org/extension.js"
)
HELPER_STYLESHEET = HELPER.with_name("stylesheet.css")


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
    assert "this._onColorSchemeChanged(false)" in source
    assert "const managedNativeState = nativeShell" in source
    assert "const managedDeskUxState = deskUxOrchisShell" in source
    assert "const manageShell = reconcileShell" in source
    assert "manageShell ? 'managed' : 'preserved'" in source
    assert "? [LIGHT_STYLE_UUID, USER_THEME_UUID]" in source
    assert "if (!(nativeShell && dark) && !isLive(wantOn))" in source
    assert "Main.setThemeStylesheet(null)" in source


def test_menu_layouts_hide_only_the_desktop_power_fallback():
    source = HELPER.read_text()

    assert "const HELPER_BUILD = 37" in source
    assert "get_strv('enabled-extensions')" in source
    assert "_extensionWillRun(DTP_UUID)" in source
    assert "_usesMenuSessionActions()" in source
    assert "layout === CLASSIC_MENU_LAYOUT" in source
    assert "layout === DESK_UX_MENU_LAYOUT" in source
    assert "ARCMENU_HYBRID_LAYOUT" in source
    assert "Main.panel.statusArea.quickSettings?._system" in source
    assert "indicator?._systemItem?.powerToggle" in source
    assert "!powerToggle.visible" in source
    assert "indicator.hide()" in source
    assert "indicator._syncIndicatorsVisible?.()" in source
    assert "'notify::visible', () => this._syncPanelSystemIndicator()" in source
    assert source.index("this._setupPanelSystemIndicator();") < source.index(
        "this._sleep(1000).then"
    )


def test_menu_layouts_hide_only_quick_settings_shutdown_action():
    source = HELPER.read_text()

    assert "_findQuickSettingsShutdownItem()" in source
    assert ".find(item => item?.menu === systemItem.menu)" in source
    assert "_setupQuickSettingsShutdownItem()" in source
    assert "_syncQuickSettingsShutdownItem()" in source
    assert "if (this._usesMenuSessionActions())" in source
    assert "item.hide()" in source
    assert "item._sync()" in source
    assert "_teardownQuickSettingsShutdownItem()" in source


def test_hybrid_light_panel_keeps_overview_icon_contrast():
    source = HELPER.read_text()
    stylesheet = HELPER_STYLESHEET.read_text()

    assert "LIGHT_OVERVIEW_PANEL_CLASS" in source
    assert "_syncLightOverviewPanelClass()" in source
    assert "_clearLightOverviewPanelClass()" in source
    assert "get_string('color-scheme') === 'prefer-dark'" in source
    assert "settings.get_string('menu-layout') !== ARCMENU_HYBRID_LAYOUT" in source
    assert "global.dashToPanel?.panels" in source
    assert "layout-switcher-light-overview-panel:overview" in stylesheet
    assert "color: #222226" in stylesheet


def test_native_shell_running_indicators_follow_shell_accent():
    source = HELPER.read_text()
    stylesheet = HELPER_STYLESHEET.read_text()

    assert "const HELPER_BUILD = 37" in source
    assert "NATIVE_ACCENT_PANEL_CLASS" in source
    assert "_syncNativeAccentPanelClass()" in source
    assert "_clearNativeAccentPanelClass()" in source
    assert "settings.get_enum('layout') === CLASSIC_MENU_LAYOUT" in source
    assert "ARCMENU_HYBRID_LAYOUT" in source
    assert "'changed::accent-color'" in source
    assert "_syncClassicFocusHighlight()" in source
    assert "get_string('focus-highlight-color')" in source
    assert "set_string('focus-highlight-color', accent)" in source
    assert "layout-switcher-accent-probe" in stylesheet
    assert "layout-switcher-native-accent-panel" in stylesheet
    assert "background-color: -st-accent-color" in stylesheet


def test_hybrid_focused_indicator_is_twenty_percent_shorter():
    source = HELPER.read_text()

    assert "const HYBRID_INDICATOR_SCALE = 0.8" in source
    assert "_waitDashToPanelReady" in source
    assert "panel?.taskbar?._box" in source
    assert "if (target.has(DTP_UUID))" in source
    assert "await this._waitDashToPanelReady()" in source
    assert "_syncHybridFocusedIndicators()" in source
    assert "_teardownHybridFocusedIndicators()" in source
    assert "actor.has_style_class_name?.('dtp-dots-container')" in source
    assert "indicator.set_pivot_point(0.5, 0.5)" in source
    assert "for (const [index, indicator] of indicators.entries())" in source
    assert "indicator.set_scale(HYBRID_INDICATOR_SCALE, 1)" in source
    assert "new Clutter.DesaturateEffect({factor: 1})" in source
    assert "_watchHybridTaskbarTree(taskbarBox)" in source
    assert "'child-added', (_parent, child)" in source
    assert "this._watchHybridTaskbarTree(child)" in source
    assert "_watchHybridIndicatorContainer(actor)" in source
    assert "'child-removed', (_container, indicator)" in source
    assert "for (const container of this._hybridIndicatorContainers" in source
    assert "for (const actor of this._hybridTaskbarActors" in source
