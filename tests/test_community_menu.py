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


def test_arcmenu_is_not_a_package_dependency():
    pkgbuild = (ROOT / "pkgbuild/PKGBUILD").read_text()

    assert "gnome-shell-extension-arc-menu" not in pkgbuild
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
