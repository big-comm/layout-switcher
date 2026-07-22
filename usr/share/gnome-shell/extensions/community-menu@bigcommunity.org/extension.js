// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
/*
 * Zorin Menu: The official applications menu for Zorin OS.
 *
 * Copyright (C) 2016-2025 Zorin OS Technologies Ltd.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import * as Constants from './constants.js';
import * as Menu from './menu.js';
import {SearchProviderEmitter} from './searchProviderEmitter.js';
import * as Utils from './utils.js';

export let EXTENSION_PATH = null;
export let SETTINGS = null;
export let SEARCH_EMITTER = null;

const LIGHT_PANEL_STYLE_CLASS = 'community-menu-light-panel';
const DARK_PANEL_STYLE_CLASS = 'community-menu-dark-panel';
const GRID_PANEL_STYLE_CLASS = 'community-menu-grid-panel';

export default class CommunityMenuExtension extends Extension {
    enable() {
        EXTENSION_PATH = this.path;
        SETTINGS = this.getSettings();
        SEARCH_EMITTER = new SearchProviderEmitter();

        this.menuButtons = [];
        this._styledPanels = new Set();
        this._taskbarBoxes = new Set();
        this._focusedIndicators = new Map();
        this._interfaceSettings = new Gio.Settings({
            schema_id: 'org.gnome.desktop.interface',
        });
        this._interfaceSettings.connectObject(
            'changed::color-scheme', () => this._syncPanelColorClass(), this);
        this._mutterSettings = new Gio.Settings({
            schema_id: Constants.MUTTER_SCHEMA,
        });
        this._savedOverlayKey = this._mutterSettings.get_value('overlay-key');
        this._mutterSettings.connectObject('changed::overlay-key', () => {
            if (!this._changingOverlayKey)
                this._savedOverlayKey = this._mutterSettings.get_value('overlay-key');
        }, this);
        SETTINGS.connectObject('changed::layout', () => {
            this._syncOverlayKeyBinding();
            this._syncPanelColorClass();
        }, this);

        this._getActivePanelExtension();
        this._enableButtons();
        this._syncOverlayKeyBinding();

        Main.extensionManager.connectObject('extension-state-changed', (data, extension) => {
            if (Utils.isPanelExtension(extension.uuid)) {
                this._getActivePanelExtension();
                this._disconnectExtensionSignals();
                this._connectExtensionSignals();
                this._reload();
            }
        }, this);

        this._connectExtensionSignals();
    }

    disable() {
        this._disableOverlayKeyBinding();
        SETTINGS?.disconnectObject(this);
        this._interfaceSettings?.disconnectObject(this);
        this._mutterSettings?.disconnectObject(this);
        this._clearPanelColorClass();
        this._interfaceSettings = null;
        this._mutterSettings = null;
        this._savedOverlayKey = null;

        this._restoreFocusedIndicators();
        this._disconnectExtensionSignals();
        Main.extensionManager.disconnectObject(this);

        this._disableButtons();
        this.menuButtons = null;

        SEARCH_EMITTER?.destroy();
        SEARCH_EMITTER = null;

        Utils.clearCommandsCache();

        EXTENSION_PATH = null;
        SETTINGS = null;
    }

    _getActivePanelExtension() {
        this._panelExtension = null;

        let dtp = Main.extensionManager.lookup(Constants.DASH_TO_PANEL_UUID);

        if (Utils.isExtensionEnabled(dtp) && global.dashToPanel) {
            this._panelExtension = "dashToPanel";
        }
    }

    _connectExtensionSignals() {
        if (this._panelExtension && global[this._panelExtension]) {
            global[this._panelExtension].connectObject('panels-created', () => {
                this._connectTaskbarSignals();
                this._reload();
            }, this);
            this._connectTaskbarSignals();
        }
    }

    _connectTaskbarSignals() {
        for (const panel of global.dashToPanel?.panels ?? []) {
            const taskbarBox = panel?.taskbar?._box;
            if (!taskbarBox || this._taskbarBoxes.has(taskbarBox))
                continue;

            taskbarBox.connectObject('child-added', (_box, actor) => {
                this._syncFocusedIndicators(actor);
            }, this);
            this._taskbarBoxes.add(taskbarBox);
            this._syncFocusedIndicators(taskbarBox);
        }
    }

    _disconnectExtensionSignals() {
        if (global.dashToPanel)
            global.dashToPanel.disconnectObject(this);
        for (const taskbarBox of this._taskbarBoxes ?? [])
            taskbarBox.disconnectObject(this);
        this._taskbarBoxes?.clear();
    }

    _reload() {
        this._disableButtons();
        this._enableButtons();
    }

    _enableButtons() {
        let panelExtensionEnabled = false;
        let panels;

        if (this._panelExtension && global[this._panelExtension]?.panels) {
            panels = global[this._panelExtension].panels.filter(p => p);
            panelExtensionEnabled = true;
        } else {
            panels = [Main.panel];
        }

        const primaryPanelIndex = Main.layoutManager.primaryMonitor?.index;

        for (var i = 0; i < panels.length; i++) {
            if (!panels[i]) {
                console.log(`Community Menu Error: panel ${i} not found. Skipping...`);
                continue;
            }

            let panel, panelBox, panelParent;
            if (panelExtensionEnabled) {
                panel = panels[i].panel;
                panelBox = panels[i].panelBox;
                panelParent = panels[i];
            } else {
                panel = panels[i];
                panelBox = Main.layoutManager.panelBox;
                panelParent = Main.panel;
            }

            let monitorIndex = 0;
            if (panelParent.monitor)
                monitorIndex = panelParent.monitor.index;
            else if (panel === Main.panel)
                monitorIndex = primaryPanelIndex ?? 0;

            const panelExtension = this._panelExtension;
            const panelInfo = {panel, panelBox, panelParent, monitorIndex, panelExtension};

            const menuButton = new Menu.ApplicationsButton(panelInfo);
            this._enableButton(menuButton)
        }

        this._syncPanelColorClass();
    }

    _clearPanelColorClass() {
        for (const menuButton of this.menuButtons ?? [])
            menuButton.setLightStyle(false);

        for (const panel of this._styledPanels ?? []) {
            try {
                panel.remove_style_class_name(LIGHT_PANEL_STYLE_CLASS);
                panel.remove_style_class_name(DARK_PANEL_STYLE_CLASS);
                panel.remove_style_class_name(GRID_PANEL_STYLE_CLASS);
            } catch (e) {
                console.debug(`Community Menu: panel style cleanup failed: ${e}`);
            }
        }
        this._styledPanels?.clear();
    }

    _syncPanelColorClass() {
        this._clearPanelColorClass();
        const layout = SETTINGS.get_enum('layout');
        const lightMode = this._interfaceSettings &&
            this._interfaceSettings.get_string('color-scheme') !== 'prefer-dark';
        const panelStyleClass = lightMode
            ? (layout === Constants.LAYOUTS.APPS_ONLY
                ? LIGHT_PANEL_STYLE_CLASS
                : (layout === Constants.LAYOUTS.APP_GRID
                    ? DARK_PANEL_STYLE_CLASS
                    : null))
            : null;
        for (const menuButton of this.menuButtons ?? []) {
            menuButton.setLightStyle(lightMode);
            const panel = menuButton.panel;
            if (!panel)
                continue;
            if (layout === Constants.LAYOUTS.APP_GRID)
                panel.add_style_class_name(GRID_PANEL_STYLE_CLASS);
            if (panelStyleClass)
                panel.add_style_class_name(panelStyleClass);
            this._styledPanels.add(panel);
        }
        this._syncFocusedIndicators();
    }

    _syncFocusedIndicators(root = null) {
        if (SETTINGS?.get_enum('layout') !== Constants.LAYOUTS.APP_GRID) {
            this._restoreFocusedIndicators();
            return;
        }

        const roots = root ? [root] : [...(this._taskbarBoxes ?? [])];
        const currentIndicators = new Set();

        const visit = actor => {
            if (actor.has_style_class_name?.('dtp-dots-container')) {
                const indicators = actor.get_children()
                    .filter(child => child instanceof St.DrawingArea);
                const focusedIndicator = indicators.at(-1);
                if (focusedIndicator) {
                    this._configureFocusedIndicator(actor, focusedIndicator);
                    currentIndicators.add(focusedIndicator);
                }
            }

            for (const child of actor.get_children?.() ?? [])
                visit(child);
        };

        for (const actor of roots)
            visit(actor);

        if (!root) {
            for (const actor of this._focusedIndicators?.keys() ?? []) {
                if (!currentIndicators.has(actor))
                    this._restoreFocusedIndicator(actor);
            }
        }
    }

    _configureFocusedIndicator(container, indicator) {
        if (!this._focusedIndicators.has(indicator)) {
            const syncWidth = () => {
                const fullWidth = container.width;
                if (indicator.width <= 0 || fullWidth <= 1)
                    return;

                const targetWidth = Math.max(1, Math.round(fullWidth / 2));
                if (indicator.width !== targetWidth)
                    indicator.width = targetWidth;
            };

            indicator.connectObject('notify::width', syncWidth, this);
            container.connectObject('notify::width', syncWidth, this);
            indicator.connectObject('destroy', () => {
                this._focusedIndicators.delete(indicator);
            }, this);
            this._focusedIndicators.set(indicator, container);
        }

        indicator.x_expand = false;
        indicator.x_align = Clutter.ActorAlign.CENTER;
        indicator.set_scale(1, 1);
        const fullWidth = container.width;
        if (indicator.width > 0 && fullWidth > 1)
            indicator.width = Math.max(1, Math.round(fullWidth / 2));
    }

    _restoreFocusedIndicator(indicator) {
        const container = this._focusedIndicators?.get(indicator);
        try {
            indicator.disconnectObject(this);
            container?.disconnectObject(this);
            indicator.x_align = Clutter.ActorAlign.FILL;
            indicator.set_scale(1, 1);
        } catch (e) {
            console.debug(`Community Menu: indicator cleanup failed: ${e}`);
        }
        this._focusedIndicators?.delete(indicator);
    }

    _restoreFocusedIndicators() {
        for (const actor of [...(this._focusedIndicators?.keys() ?? [])])
            this._restoreFocusedIndicator(actor);
        this._focusedIndicators?.clear();
    }

    _enableButton(menuButton) {
        const panel = menuButton.panel;

        panel?.addToStatusArea(
            'community-menu', menuButton, 0, 'left'
        );
        panel?.connectObject('destroy', () => this._disableButton(menuButton, panel), this);

        this.menuButtons.push(menuButton);
    }

    _disableButtons() {
        for (let i = this.menuButtons.length - 1; i >= 0; --i) {
            const mb = this.menuButtons[i];
            this._disableButton(mb, mb.panel);
        }
    }

    _disableButton(menuButton, panel) {
        if (panel) {
            panel.disconnectObject(this);
            panel.statusArea['community-menu'] = null;
        }

        const index = this.menuButtons.indexOf(menuButton);
        if (index !== -1)
            this.menuButtons.splice(index, 1);

        menuButton?.destroy();
    }

    _getOpenedMenu() {
        const menus = this._getAllMenus();
        for (let i = 0; i < menus.length; i++) {
            if (menus[i].isOpen)
                return menus[i];
        }
        return null;
    }

    _getAllMenus() {
        const menus = [];
        for (let i = 0; i < this.menuButtons.length; i++) {
            menus.push(this.menuButtons[i]._menu);
        }
        return menus;
    }

    _toggleMenu() {
        if (this.menuButtons.length < 1) {
            Main.overview.toggle();
        } else if (this.menuButtons.length === 1) {
            this.menuButtons[0].toggleMenu();
        } else {
            this._toggleMenuOnMonitor();
        }
    }

    _syncOverlayKeyBinding() {
        const layout = SETTINGS.get_enum('layout');
        const opensWithSuper = layout === Constants.LAYOUTS.APP_GRID ||
            layout === Constants.LAYOUTS.APPS_ONLY;
        if (opensWithSuper)
            this._enableOverlayKeyBinding();
        else
            this._disableOverlayKeyBinding();
    }

    _enableOverlayKeyBinding() {
        if (this._overlayKeyActive)
            return;

        this._overlayKeyActive = true;
        this._changingOverlayKey = true;
        this._mutterSettings.set_string('overlay-key', 'Super_L');
        this._changingOverlayKey = false;
        Main.wm.allowKeybinding('overlay-key', Shell.ActionMode.ALL);

        if (Main.layoutManager._startingUp) {
            Main.layoutManager.connectObject('startup-complete', () => {
                if (this._overlayKeyActive)
                    this._overrideOverlayKey();
            }, this);
        } else {
            this._overrideOverlayKey();
        }
    }

    _overrideOverlayKey() {
        this._defaultOverlayKeyId = GObject.signal_handler_find(
            global.display, {signalId: 'overlay-key'});
        if (!this._defaultOverlayKeyId) {
            console.warn('Community Menu: failed to override the Super key');
            this._disableOverlayKeyBinding();
            return;
        }

        GObject.signal_handler_block(global.display, this._defaultOverlayKeyId);
        global.display.connectObject('overlay-key', () => {
            this._toggleMenu();
            Main.wm.allowKeybinding('overlay-key', Shell.ActionMode.ALL);
        }, this);
    }

    _disableOverlayKeyBinding() {
        Main.layoutManager.disconnectObject(this);
        global.display.disconnectObject(this);

        if (this._defaultOverlayKeyId) {
            GObject.signal_handler_unblock(global.display, this._defaultOverlayKeyId);
            this._defaultOverlayKeyId = 0;
        }

        if (this._overlayKeyActive && this._mutterSettings && this._savedOverlayKey) {
            this._changingOverlayKey = true;
            this._mutterSettings.set_value('overlay-key', this._savedOverlayKey);
            this._changingOverlayKey = false;
        }

        this._overlayKeyActive = false;
        Main.wm.allowKeybinding(
            'overlay-key', Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW);
    }

    _toggleMenuOnMonitor() {
        const monitor = Main.layoutManager.currentMonitor;
        if (!monitor) {
            this.menuButtons[0]?.toggleMenu();
            return;
        }

        const primaryMonitorIndex = Main.layoutManager.primaryMonitor?.index ?? 0;
        let targetButton = null;
        let primaryButton = null;

        for (let i = 0; i < this.menuButtons.length; i++) {
            const menuButton = this.menuButtons[i];
            const {monitorIndex} = menuButton;

            if (monitor.index === monitorIndex) {
                targetButton = menuButton;
            } else {
                menuButton.maybeCloseMenus();
            }

            if (monitorIndex === primaryMonitorIndex)
                primaryButton = menuButton;
        }

        // Open the menu on the current monitor, or fall back to the
        // primary monitor's menu if none is found on the current one.
        const buttonToToggle = targetButton ?? primaryButton ?? this.menuButtons[0];
        buttonToToggle?.toggleMenu();
    }

}
