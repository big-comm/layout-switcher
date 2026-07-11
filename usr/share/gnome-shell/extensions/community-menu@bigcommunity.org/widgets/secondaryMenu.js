// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
/*
 * Zorin Menu: The official applications menu for Zorin OS.
 *
 * Copyright (C) 2016-2023 Zorin OS Technologies Ltd.
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
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Util from 'resource:///org/gnome/shell/misc/util.js';
import * as AppMenu from 'resource:///org/gnome/shell/ui/appMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as SystemActions from 'resource:///org/gnome/shell/misc/systemActions.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as Constants from '../constants.js';
import * as Utils from '../utils.js';


export const AppItemMenu = class extends AppMenu.AppMenu {
    constructor(source) {
        super(source, St.Side.TOP);
        this._enableFavorites = true;
        this._showSingleWindows = true;

        this._newWindowItem.connect('activate', () => this.emit('activate-window'));
        this._onGpuMenuItem.connect('activate', () => this.emit('activate-window'));
        this._detailsItem.connect('activate', () => this.emit('activate-window'));
        this._windowSection.connect('activate', () => this.emit('activate-window'));
        this._actionSection.connect('activate', () => this.emit('activate-window'));

        this._addToDesktopItem = new PopupMenu.PopupMenuItem(_("Add to Desktop"));
        this._addToDesktopItem.connect('activate', () => {
            this._onAddToDesktopActivated();
        });
        this.addMenuItem(this._addToDesktopItem, 7);
        this.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(), 8);

        this.setApp(source.app);

        Main.uiGroup.add_child(this.actor);
        this.actor.connect('key-press-event', this._menuKeyPress.bind(this));
    }

    setApp(app) {
        super.setApp(app);
        this._updateAddToDesktopItem();
    }

    _updateAddToDesktopItem() {
        if (!this._app) {
            this._addToDesktopItem.visible = false;
            return;
        }
        this._addToDesktopItem.visible = true;

        let desktop = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP);
        let file = Gio.File.new_for_path(GLib.build_filenamev([desktop, this._app.get_id()]));
        let isOnDesktop = file.query_exists(null);

        this._addToDesktopItem.label.text = isOnDesktop ? _("Remove from Desktop")
            : _("Add to Desktop");
    }

    _onAddToDesktopActivated() {
        if (!this._app) {
            this._updateAddToDesktopItem();
            return;
        }

        let desktop = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP);
        let file = Gio.File.new_for_path(GLib.build_filenamev([desktop, this._app.get_id()]));
        if (!file.query_exists(null)){
            Utils.addToDesktop(this._app.app_info);
        } else {
            try {
                file.delete(null);
            } catch (e) {
                log(`Failed to delete desktop shortcut: ${e.message}`);
            }
        }

        this._updateAddToDesktopItem();
    }

    _onKeyPress() {
        return Clutter.EVENT_PROPAGATE;
    }

    open(animate) {
        super.open(animate);
        this.sourceActor.add_style_pseudo_class('active');
    }

    close(animate) {
        super.close(animate);
        this.sourceActor?.remove_style_pseudo_class('active');
        this.sourceActor?.sync_hover();
    }

    _menuKeyPress(actor, event) {
        const symbol = event.get_key_symbol();
        if (symbol === Clutter.KEY_Menu) {
            this.toggle();
            this.sourceActor.sync_hover();
        }
    }

    destroy() {
        this.actor?.get_parent()?.remove_child(this.actor);
        super.destroy();
    }
};

export const ButtonMenu = class extends PopupMenu.PopupMenu {
    constructor(source) {
        super(source, 0.5 , St.Side.BOTTOM);
    }

    _onKeyPress() {
        return Clutter.EVENT_PROPAGATE;
    }

    open(animate) {
        super.open(animate);
        this.sourceActor.add_style_pseudo_class('active');
    }

    close(animate) {
        super.close(animate);
        this.sourceActor?.remove_style_pseudo_class('active');
        this.sourceActor?.sync_hover();
    }
};

export const MenuButtonSecondaryMenu = class extends PopupMenu.PopupMenu {
    constructor(source, panelExtension) {
        super(source, 0.5, St.Side.TOP);

        this.actor.add_style_class_name('panel-menu app-menu');
        Main.uiGroup.add_child(this.actor);
        this.actor.hide();

        this._systemActions = new SystemActions.getDefault();
        this._systemActions.forceUpdate();

        this._maybeAppendCommandItem({
            title: _('System Monitor'),
            cmd: ['gnome-system-monitor']
        });

        this._maybeAppendCommandItem({
            title: _('Files'),
            cmd: ['nautilus']
        });

        this._maybeAppendCommandItem({
            title: _('Settings'),
            cmd: ['gnome-control-center']
        });

        this._appendSeparator();
        this._appendPowerSubMenu();
        this._appendSeparator();

        this._maybeAppendCommandItem({
            title: _('Edit Menu'),
            cmd: ['alacarte']
        });

        this._maybeAppendCommandItem({
            title: _('Search Settings'),
            cmd: ['gnome-control-center', 'search']
        });

        this._maybeAppendPanelExtensionSettings(panelExtension);
    }

    // Only add menu entries for commands that exist in path
    _maybeAppendCommandItem(info) {
        if (Utils.checkIfCommandExists(info.cmd[0])) {
            let item = this._appendMenuItem(_(info.title));

            item.connect('activate', function() {
                Util.spawn(info.cmd);
            });
            return item;
        }

        return null;
    }

    _appendSeparator() {
        let separator = new PopupMenu.PopupSeparatorMenuItem();
        this.addMenuItem(separator);
    }

    _appendMenuItem(labelText) {
        let item = new PopupMenu.PopupMenuItem(labelText);
        this.addMenuItem(item);
        return item;
    }

    _appendPowerSubMenu() {
        this._powerOptionsItem = new PopupMenu.PopupSubMenuMenuItem(_('Power Off / Log Out'));

        this._suspendItem = this._powerOptionsItem.menu.addAction(_('Suspend'),
            () => this._systemActions.activateSuspend());
        this._suspendItem.visible = this._systemActions.canSuspend;

        this._restartItem = this._powerOptionsItem.menu.addAction(_('Restart…'),
            () => this._systemActions.activateRestart());
        this._restartItem.visible = this._systemActions.canRestart;

        this._powerOffItem = this._powerOptionsItem.menu.addAction(_('Power Off…'),
            () => this._systemActions.activatePowerOff());
        this._powerOffItem.visible = this._systemActions.canPowerOff;

        this._powerOptionsItem.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._lockItem = this._powerOptionsItem.menu.addAction(_('Lock'),
            () => this._systemActions.activateLockScreen());
        this._lockItem.visible = this._systemActions.canLockScreen;

        this._switchUserItem = this._powerOptionsItem.menu.addAction(_('Switch User…'),
            () => this._systemActions.activateSwitchUser());
        this._switchUserItem.visible = this._systemActions.canSwitchUser;

        this._logoutItem = this._powerOptionsItem.menu.addAction(_('Log Out…'),
            () => this._systemActions.activateLogout());
        this._logoutItem.visible = this._systemActions.canLogout;

        this._systemActions.connectObject(
            'notify::can-suspend', () => this._updatePowerSubMenuVisibility(),
            'notify::can-restart', () => this._updatePowerSubMenuVisibility(),
            'notify::can-power-off', () => this._updatePowerSubMenuVisibility(),
            'notify::can-lock-screen', () => this._updatePowerSubMenuVisibility(),
            'notify::can-switch-user', () => this._updatePowerSubMenuVisibility(),
            'notify::can-logout', () => this._updatePowerSubMenuVisibility(),
            this);

        this.addMenuItem(this._powerOptionsItem);
        this._updatePowerSubMenuVisibility();
    }

    _updatePowerSubMenuVisibility() {
        this._suspendItem.visible = this._systemActions.canSuspend;
        this._restartItem.visible = this._systemActions.canRestart;
        this._powerOffItem.visible = this._systemActions.canPowerOff;
        this._lockItem.visible = this._systemActions.canLockScreen;
        this._switchUserItem.visible = this._systemActions.canSwitchUser;
        this._logoutItem.visible = this._systemActions.canLogout;

        this._powerOptionsItem.visible =
            this._suspendItem.visible ||
            this._restartItem.visible ||
            this._powerOffItem.visible ||
            this._lockItem.visible ||
            this._switchUserItem.visible ||
            this._logoutItem.visible;
     }

    _maybeAppendPanelExtensionSettings(panelExtension) {
        if(!panelExtension) {
            return;
        }

        if (panelExtension === "dashToPanel") {
            const item = new PopupMenu.PopupMenuItem(_('Dash to Panel Settings'));
            item.connect('activate', () => Utils.openPrefs(Constants.DASH_TO_PANEL_UUID));
            this.addMenuItem(item);
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

        this._systemActions?.disconnectObject(this);
        this._systemActions = null;

        this._powerOptionsItem = null;
        this._suspendItem = null;
        this._restartItem = null;
        this._powerOffItem = null;
        this._lockItem = null;
        this._switchUserItem = null;
        this._logoutItem = null;

        super.destroy();
    }
};
