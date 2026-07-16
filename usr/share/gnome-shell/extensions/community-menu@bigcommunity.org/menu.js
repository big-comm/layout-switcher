// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
/*
 * Zorin Menu: The official applications menu for Zorin OS.
 *
 * Copyright (C) 2016-2021 Zorin OS Technologies Ltd.
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

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {PopupAnimation} from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as AppsBackend from './appsbackend.js';
import * as Constants from './constants.js';
import * as Layouts from './layouts/layouts.js';
import * as MenuButton from './widgets/menuButton.js';
import * as SecondaryMenu from './widgets/secondaryMenu.js';
import * as Utils from './utils.js';
import { SETTINGS } from './extension.js'

const ApplicationsMenu = class extends PopupMenu.PopupMenu {
    // Initialize the menu
    constructor(sourceActor, panelInfo) {
        super(sourceActor, 0.5, St.Side.TOP);
        this._panelBox = panelInfo.panelBox;
        this._panelParent = panelInfo.panelParent;
        this._monitorIndex = panelInfo.monitorIndex;

        this._section = new PopupMenu.PopupMenuSection();
        this.addMenuItem(this._section);
        this._appsBackend = new AppsBackend.AppsBackend();

        SETTINGS.connectObject('changed::layout', this._reloadLayout.bind(this), this);

        this.actor.connectObject('captured-event', this._onCapturedEvent.bind(this), this);
        this.actor.add_style_class_name('panel-menu');
        this.actor.add_style_class_name('community-menu');
        this.actor.accessible_role = Atk.Role.MENU;

        Main.uiGroup.add_child(this.actor);
        this.actor.hide();
    }

    _onCapturedEvent(actor, event) {
        if (Main.keyboard.maybeHandleEvent(event))
            return Clutter.EVENT_STOP;

        return Clutter.EVENT_PROPAGATE;
    }

    _loadLayout() {
        const panelInfo = {panelParent: this._panelParent, monitorIndex: this._monitorIndex};
        this._layout = Layouts.getLayout(SETTINGS.get_enum('layout'), this._appsBackend, panelInfo);
        this._section.actor.add_child(this._layout);
        this._layout.connectObject('activated', this._onLayoutActivated.bind(this), this);
        this._layout.connectObject('screenshot-activated', this._onScreenshotActivated.bind(this), this);
    }

    _reloadLayout() {
        this._layout?.destroy();
        this._loadLayout();
    }

    _maybeShowPanel() {
        if (this._panelParent.intellihide && this._panelParent.intellihide.enabled) {
            // Hold.TEMPORARY = 1, immediate = true
            this._panelParent.intellihide.revealAndHold(1, true);
        } else if (!this._panelBox.visible) {
            this._panelBox.visible = true;
            this._panelNeedsHiding = true;
        }
    }

    // Return that the menu is not empty (used by parent class)
    isEmpty() {
        return false;
    }

    // Handle opening the menu
    open(animate) {
        this._maybeShowPanel();
        super.open(animate);
        Main.uiGroup.set_child_below_sibling(this.actor, Main.layoutManager.keyboardBox);
        if (!this._layout) {
            this._loadLayout();
        }
        this._layout.reset();
        this._layout.updateHeight();
    }

    // Handle menu item activation
    _onLayoutActivated() {
        this.close(PopupAnimation.FULL);
        if (Main.overview.visible)
            Main.overview.hide();
    }

    // Handle screenshot item activation
    _onScreenshotActivated() {
        global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            Main.screenshotUI.open().catch(logError);
            return GLib.SOURCE_REMOVE;
        });
        this.close(PopupAnimation.NONE);
    }

    // Handle closing the menu
    close(animate) {
        const monitor = Main.layoutManager.monitors[this._monitorIndex];

        this._layout?.closePopups?.();
        super.close(animate);

        if (this._panelParent?.intellihide?.enabled) {
            this._panelParent.intellihide?.release(1);
        }
        if (this._panelNeedsHiding && this._panelBox) {
            this._panelNeedsHiding = false;
            if (monitor) {
                this._panelBox.visible = !(global.window_group.visible &&
                                           monitor.inFullscreen);
            } else {
                this._panelBox.visible = true;
            }
        }
    }

    updateArrowSide(side) {
        this._arrowSide = side;
        this._boxPointer._arrowSide = side;
        this._boxPointer._userArrowSide = side;
        this._boxPointer.setSourceAlignment(0.5);
        this._arrowAlignment = 0.5;
        this._boxPointer._border.queue_repaint();
    }

    destroy() {
        this.actor?.get_parent()?.remove_child(this.actor);

        SETTINGS?.disconnectObject(this);

        this._layout?.destroy();
        this._layout = null;

        this._section?.destroy();
        this._section = null;

        this._appsBackend?.destroy();
        this._appsBackend = null;

        super.destroy();

        this._panelBox = null;
        this._panelParent = null;
        this._monitorIndex = null;
        this._panelNeedsHiding = null;
    }
};

export const ApplicationsButton = GObject.registerClass({
}, class ApplicationsButton extends PanelMenu.Button {
    // Initialize the menu
    _init(panelInfo) {
        super._init(1.0, _('Community Menu'), true);
        this.add_style_class_name('community-menu-panel-button');

        this.panel = panelInfo.panel;
        this._panelParent = panelInfo.panelParent;
        this.monitorIndex = panelInfo.monitorIndex;

        this.menu.destroy();
        this.menu = null;

        this._menu = new ApplicationsMenu(this, panelInfo);
        this._menu.connectObject('open-state-changed', this._onOpenStateChanged.bind(this), this);

        this._secondaryMenu = new SecondaryMenu.MenuButtonSecondaryMenu(this, panelInfo.panelExtension);
        this._secondaryMenu.connectObject('open-state-changed', this._onOpenStateChanged.bind(this), this);

        this.menuManager = new PopupMenu.PopupMenuManager();
        this.menuManager._changeMenu = (menu) => {};
        this.menuManager.addMenu(this._menu);
        this.menuManager.addMenu(this._secondaryMenu);

        this._menuButton = new MenuButton.MenuButton();
        this.add_child(this._menuButton);

        this._syncArrowSide();
    }

    _syncArrowSide() {
        let dtp = Main.extensionManager.lookup(Constants.DASH_TO_PANEL_UUID);

        this._panelSettings?.disconnectObject(this);
        this._panelSettings = null;

        if (Utils.isExtensionEnabled(dtp) && global.dashToPanel) {
            this._panelSettings = dtp.stateObj?.getSettings('org.gnome.shell.extensions.dash-to-panel');
        }

        if (this._panelSettings && this._panelParent && this._panelParent.getPosition) {
            const side = this._panelParent.getPosition();
            this._setMenuArrowSides(side);

            this._panelSettings.connectObject('changed::panel-positions', () => {
                const newSide = this._panelParent.getPosition ? this._panelParent.getPosition() : St.Side.TOP;
                this._setMenuArrowSides(newSide);
            }, this);
        } else {
            this._setMenuArrowSides(St.Side.TOP);
        }
    }

    setLightStyle(enabled) {
        if (enabled)
            this._menu?.actor.add_style_class_name('community-menu-light');
        else
            this._menu?.actor.remove_style_class_name('community-menu-light');
    }

    _setMenuArrowSides(side) {
        this._menu.updateArrowSide(side);
        this._secondaryMenu.updateArrowSide(side);
    }

    // Destroy the menu button
    _onDestroy() {
        this._panelSettings?.disconnectObject(this);
        this._panelSettings = null;

        this._menu?.destroy();
        this._menu = null;

        this._secondaryMenu?.destroy();
        this._secondaryMenu = null;

        this.menuManager = null;

        this.panel.statusArea['community-menu'] = null;
        this.panel = null;
        this._panelParent = null;
        this.monitorIndex = null;

        this._menuButton?.destroy();
        this._menuButton = null;

        super._onDestroy();
    }

    vfunc_event(event) {
        if (event.type() === Clutter.EventType.BUTTON_PRESS) {
            if (event.get_button() === Clutter.BUTTON_PRIMARY || event.get_button() === Clutter.BUTTON_MIDDLE)
                this._menu.toggle();
            else if (event.get_button() === Clutter.BUTTON_SECONDARY)
                this._secondaryMenu.toggle();
        } else if (event.type() === Clutter.EventType.TOUCH_BEGIN) {
            this._menu.toggle();
        }
        return Clutter.EVENT_PROPAGATE;
    }


    vfunc_hide() {
        super.vfunc_hide();

        if (this._menu)
            this._menu.close();
    }

    _updateMenuMaxHeight() {
        // Setting the max-height won't do any good if the minimum height of the
        // menu is higher then the screen; it's useful if part of the menu is
        // scrollable so the minimum height is smaller than the natural height
        const workArea = Main.layoutManager.getWorkAreaForMonitor(this.monitorIndex);
        const scaleFactor = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const verticalMargins = this._menu.actor.margin_top + this._menu.actor.margin_bottom;

        // The workarea and margin dimensions are in physical pixels, but CSS
        // measures are in logical pixels, so make sure to consider the scale
        // factor when computing max-height
        let maxHeight = Math.round((workArea.height - verticalMargins) / scaleFactor);
        this._menu.actor.style = `max-height: ${maxHeight}px;`;
    }


    _onOpenStateChanged(menu, open) {
        if (open) {
            this.add_style_pseudo_class('active');
            if (Main.panel.menuManager && Main.panel.menuManager.activeMenu)
                Main.panel.menuManager.activeMenu.toggle();

            if (this._menu.isOpen)
                this._updateMenuMaxHeight();
        } else if (!this._menu.isOpen && !this._secondaryMenu.isOpen) {
            this.remove_style_pseudo_class('active');
        }
    }

    maybeCloseMenus() {
        if (this._menu.isOpen)
            this._menu.close(PopupAnimation.FULL);

        if (this._secondaryMenu.isOpen)
            this._secondaryMenu.close(PopupAnimation.FULL);
    }

    toggleMenu() {
        this._menu.toggle();
    }
});
