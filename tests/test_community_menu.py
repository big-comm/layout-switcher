# SPDX-License-Identifier: MIT
"""Static integration checks for the bundled Community Menu."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = (
    ROOT / "usr/share/gnome-shell/extensions/community-menu@bigcommunity.org"
)
SCHEMA_FILE = (
    ROOT
    / "usr/share/glib-2.0/schemas/org.gnome.shell.extensions.community-menu.gschema.xml"
)


def test_community_menu_metadata_is_independent():
    metadata = json.loads((EXTENSION_DIR / "metadata.json").read_text())

    assert metadata["uuid"] == "community-menu@bigcommunity.org"
    assert metadata["gettext-domain"] == "community-menu"
    assert metadata["settings-schema"] == "org.gnome.shell.extensions.community-menu"
    assert "50" in metadata["shell-version"]
    assert metadata["version"] == 17


def test_community_menu_schema_exposes_only_supported_layouts():
    root = ET.parse(SCHEMA_FILE).getroot()
    enum = root.find("enum")
    schema = root.find("schema")

    assert enum is not None
    assert schema is not None
    assert [value.attrib["nick"] for value in enum.findall("value")] == [
        "ALL",
        "APPS_ONLY",
        "SYSTEM_ONLY",
        "APP_GRID",
        "MINT",
    ]
    assert [key.attrib["name"] for key in schema.findall("key")] == ["layout"]


def test_arcmenu_is_a_package_dependency_for_hybrid():
    pkgbuild = (ROOT / "pkgbuild/PKGBUILD").read_text()

    assert "gnome-shell-extension-arc-menu" in pkgbuild
    assert "GPL-2.0-or-later" in pkgbuild


def test_menu_button_uses_bundled_community_icon():
    source = (EXTENSION_DIR / "widgets/menuButton.js").read_text()
    constants = (EXTENSION_DIR / "constants.js").read_text()

    assert (EXTENSION_DIR / "community-menu.svg").is_file()
    assert "${EXTENSION_PATH}/community-menu.svg" in source
    assert "MENU_BUTTON_ICON_SIZE = 36" in constants
    assert "style_class: 'community-menu-button-icon'" in source
    assert "style_class: 'popup-menu-icon'" not in source


def test_menu_button_active_highlight_is_not_stretched_by_shell_padding():
    extension_source = (EXTENSION_DIR / "extension.js").read_text()
    menu_source = (EXTENSION_DIR / "menu.js").read_text()
    stylesheet = (EXTENSION_DIR / "stylesheet.css").read_text()

    assert "add_style_class_name('community-menu-panel-button')" in menu_source
    assert "#panel .panel-button.community-menu-panel-button" in stylesheet
    assert "-natural-hpadding: 0px" in stylesheet
    assert "-minimum-hpadding: 0px" in stylesheet
    assert "border-width: 0px" in stylesheet
    assert ".community-menu-button-icon" in stylesheet
    assert "icon-size: 36px" in stylesheet
    assert "#panel.dashtopanelMainPanel:overview .panel-button" in stylesheet
    assert "color: inherit" in stylesheet
    assert "community-menu-light-panel" in extension_source
    assert "changed::color-scheme" in extension_source
    assert "community-menu-light-panel" in stylesheet
    assert "background-color: #222226" in stylesheet


def test_classic_categories_are_compact_and_open_cascade_on_hover():
    layout = (EXTENSION_DIR / "layouts/appListLayout.js").read_text()
    menu = (EXTENSION_DIR / "menu.js").read_text()
    sections = (EXTENSION_DIR / "sections.js").read_text()
    app_items = (EXTENSION_DIR / "widgets/appMenuItem.js").read_text()
    items = (EXTENSION_DIR / "widgets/miscMenuItems.js").read_text()
    constants = (EXTENSION_DIR / "constants.js").read_text()
    stylesheet = (EXTENSION_DIR / "stylesheet.css").read_text()

    assert "cascadeMenus: true" in layout
    assert "iconSize: Constants.COMPACT_CATEGORY_ICON_SIZE" in layout
    assert "monitorIndex: this._monitorIndex" in layout
    assert "COMPACT_CATEGORY_ICON_SIZE = 24" in constants
    assert "COMPACT_SUBMENU_ICON_SIZE = 18" in constants
    assert "APPS_ONLY_MENU_HEIGHT = 502" in constants
    assert "button.connectObject('notify::hover'" in sections
    assert "if (button.hover)" in sections
    assert "this._ensureCategoryMenu(button, category.get_menu_id())" in sections
    assert "this._openCategoryMenu(button, category.get_menu_id())" in sections
    assert "const CategoryAppsMenu = class extends PopupMenu.PopupMenu" in sections
    assert "St.Side.RIGHT" in sections
    assert "class CascadePopupMenuManager extends PopupMenu.PopupMenuManager" in sections
    assert "new CascadePopupMenuManager(this, params.cascadeExitActor)" in sections
    assert "event.get_coords()" in sections
    assert "this.activeMenu?.close(PopupAnimation.NONE)" in sections
    assert "this._ensureContent()" in sections
    assert "this._layout?.closePopups?.()" in menu
    assert "_init(app, isGrid, iconSize = Constants.APP_LIST_ICON_SIZE)" in app_items
    assert "_init(category, iconSize = Constants.APP_LIST_ICON_SIZE)" in items
    assert "icon_size: iconSize" in items
    assert ".apps-only-layout-box .categories-list .popup-menu-item" in stylesheet
    assert ".community-category-submenu .apps-list" in stylesheet
    assert "max-height: 24em" not in stylesheet
    assert "padding: 6px 10px" in stylesheet
    assert "spacing: 8px" in stylesheet


def test_classic_sidebar_uses_native_apps_and_session_actions():
    layout = (EXTENSION_DIR / "layouts/appListLayout.js").read_text()
    sections = (EXTENSION_DIR / "sections.js").read_text()
    session_buttons = (EXTENSION_DIR / "widgets/sessionButtons.js").read_text()
    stylesheet = (EXTENSION_DIR / "stylesheet.css").read_text()

    assert "new Sections.ClassicSidebarSection()" in layout
    assert "cascadeExitActor: this._sidebar" in layout
    assert "'org.bigcommunity.CommRelease.desktop'" in sections
    assert "'org.communitybig.layout-switcher.desktop'" in sections
    assert "'br.com.biglinux-settings.desktop'" in sections
    assert "'org.gnome.Calculator.desktop'" in sections
    assert "'org.gnome.TextEditor.desktop'" in sections
    assert "new SessionButtons.LogoutButton" in sections
    assert "new SessionButtons.RestartButton" in sections
    assert "new SessionButtons.PowerButton" in sections
    assert "appSystem.lookup_app(desktopId)" in sections
    assert "export const ApplicationButton" in session_buttons
    assert "this._app.activate()" in session_buttons
    assert ".classic-sidebar" in stylesheet
    assert ".classic-sidebar-separator" in stylesheet
    assert "icon-size: 26px" in stylesheet
    assert "border-radius: 10px" in stylesheet
    assert "background-color: rgba(128, 128, 128, 0.14)" in stylesheet
    assert ".community-menu-light .classic-sidebar-button:hover" in stylesheet
    assert "background-color: rgba(46, 46, 51, 0.18)" in stylesheet


def test_search_entry_tracks_light_color_scheme():
    extension_source = (EXTENSION_DIR / "extension.js").read_text()
    menu_source = (EXTENSION_DIR / "menu.js").read_text()
    stylesheet = (EXTENSION_DIR / "stylesheet.css").read_text()

    assert "menuButton.setLightStyle(true)" in extension_source
    assert "menuButton.setLightStyle(false)" in extension_source
    assert "setLightStyle(enabled)" in menu_source
    assert "community-menu-light" in menu_source
    assert ".community-menu.community-menu-light .search-entry" in stylesheet
    assert "background-color: rgba(128, 128, 128, 0.14)" in stylesheet
    assert "color: #2e2e33" in stylesheet


def test_classic_search_results_are_compact_without_description_tooltips():
    layout = (EXTENSION_DIR / "layouts/appListLayout.js").read_text()
    sections = (EXTENSION_DIR / "sections.js").read_text()
    search = (EXTENSION_DIR / "search.js").read_text()
    stylesheet = (EXTENSION_DIR / "stylesheet.css").read_text()

    assert "Constants.APP_LIST_ICON_SIZE,\n            true" in layout
    assert "compactSearch = false" in sections
    assert "isGrid, monitorIndex, compactSearch" in sections
    assert "this.useTooltip = !compact" in search
    assert "this.description = null" in search
    assert "ellipsize: Pango.EllipsizeMode.END" in search
    assert "community-list-search-result-labels" in search
    assert "style_class: 'list-search-result'" not in search
    assert "compact-search-results" in search
    assert ".compact-search-results .popup-menu-item" in stylesheet
    assert "min-height: 30px" in stylesheet


def test_search_entry_handles_temporarily_missing_stage_focus():
    source = (EXTENSION_DIR / "widgets/searchEntry.js").read_text()

    assert "const appearFocused = focus" in source
    assert "!this._searchResults || !this._text" in source
    assert "this.contains(focus) || this._searchResults.contains(focus)" in source
