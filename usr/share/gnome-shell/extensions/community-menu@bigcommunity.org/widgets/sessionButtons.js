// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import * as BaseMenuItem from './baseMenuItem.js';
import * as Constants from '../constants.js';
import * as SecondaryMenu from './secondaryMenu.js';

export const SessionButton = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class SessionButton extends BaseMenuItem.BaseMenuItem {
    _init(systemActions, accessible_name, icon_name) {        
        super._init({
            style_class: "button system-menu-action"
        });
        this.useTooltip = true;
        this.accessible_name = accessible_name ? accessible_name : "";
        this.description = this.accessible_name;
        this.set({
            x_expand: false,
            x_align: Clutter.ActorAlign.CENTER,
            y_expand: false,
            y_align: Clutter.ActorAlign.CENTER,
        });

        this._systemActions = systemActions;
        this._icon = new St.Icon({
            icon_name: icon_name,
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._icon);
    }

    _createTooltip(){
        super._createTooltip();
        if (this.tooltip)
            this.tooltip.location = Constants.TooltipLocation.TOP_CENTERED;
    }

    activate(event) {
        this.emit('activated');
        super.activate(event);
    }

    _onDestroy() {
        this._systemActions = null;

        this._icon?.destroy();
        this._icon = null;

        super._onDestroy();
    }
});

export const PowerMenuButton = GObject.registerClass({
}, class PowerMenuButton extends SessionButton {
    _init(systemActions) {
        super._init(systemActions, _("Power"), 'system-shutdown-symbolic');
        this._menuManager = new PopupMenu.PopupMenuManager(this);
        this._createPowerMenu();
        this.hasContextMenu = true;
        this.connect('popup-menu', () => this.powerMenu.toggle());

        this._suspendItem.connect('notify::visible',
            () => this._updateButtonReactivity());
        this._restartItem.connect('notify::visible',
            () => this._updateButtonReactivity());
        this._powerOffItem.connect('notify::visible',
            () => this._updateButtonReactivity());
        this._updateButtonReactivity()
    }

    _createPowerMenu(){
        this.powerMenu = new SecondaryMenu.ButtonMenu(this);
        this.powerMenu.connect('open-state-changed', (menu, open) => {
            if(open){
                this.tooltip?.hide();
                this._systemActions.forceUpdate();
            }
        });

        let bindFlags = GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE;

        this._suspendItem = new PopupMenu.PopupImageMenuItem(_("Suspend"), 'media-playback-pause-symbolic');
        this._suspendItem.connect('activate', () => {
            this.powerMenu.itemActivated(BoxPointer.PopupAnimation.NONE);
            this.emit('activated');
            this._systemActions.activateSuspend();
        });
        this.powerMenu.addMenuItem(this._suspendItem);
        this._systemActions.bind_property('can-suspend',
            this._suspendItem, 'visible',
            bindFlags
        );

        this._restartItem = new PopupMenu.PopupImageMenuItem(_("Restart…"), 'system-reboot-symbolic');
        this._restartItem.connect('activate', () => {
            this.powerMenu.itemActivated(BoxPointer.PopupAnimation.NONE);
            this.emit('activated');
            this._systemActions.activateRestart();
        });
        this.powerMenu.addMenuItem(this._restartItem);
        this._systemActions.bind_property('can-restart',
            this._restartItem, 'visible',
            bindFlags
        );

        this._powerOffItem = new PopupMenu.PopupImageMenuItem(_("Power Off…"), 'system-shutdown-symbolic');
        this._powerOffItem.connect('activate', () => {
            this.powerMenu.itemActivated(BoxPointer.PopupAnimation.NONE);
            this.emit('activated');
            this._systemActions.activatePowerOff();
        });
        this.powerMenu.addMenuItem(this._powerOffItem);
        this._systemActions.bind_property('can-power-off',
            this._powerOffItem, 'visible',
            bindFlags
        );

        this._menuManager.addMenu(this.powerMenu);
        this.powerMenu.actor.hide();
        Main.uiGroup.add_child(this.powerMenu.actor);
    }

    _updateButtonReactivity() {
        if (this.isDestroyed)
            return;

        this.reactive =
            this._suspendItem.visible ||
            this._restartItem.visible ||
            this._powerOffItem.visible;
    }

    activate(event) {
        this.powerMenu?.toggle();
    }

    _onDestroy() {
        this.isDestroyed = true;

        this._suspendItem?.destroy();
        this._suspendItem = null;

        this._restartItem?.destroy();
        this._restartItem = null;

        this._powerOffItem?.destroy();
        this._powerOffItem = null;

        this.powerMenu?.actor?.get_parent()?.remove_child(this.powerMenu.actor);
        this.powerMenu?.destroy();
        this.powerMenu = null;
        this._menuManager = null;

        super._onDestroy();
    }
});

export const PowerButton = GObject.registerClass({
}, class PowerButton extends SessionButton {
    _init(systemActions) {
        super._init(systemActions, _("Power Off"), 'system-shutdown-symbolic');

        let bindFlags = GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE;
        this._systemActions.bind_property('can-power-off',
            this, 'reactive',
            bindFlags
        );
    }

    activate(event) {
        super.activate(event);
        this._systemActions.activatePowerOff();
    }
});


export const RestartButton = GObject.registerClass({
}, class RestartButton extends SessionButton {
    _init(systemActions) {
        super._init(systemActions, _("Restart"), 'system-reboot-symbolic');

        let bindFlags = GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE;
        this._systemActions.bind_property('can-restart',
            this, 'visible',
            bindFlags
        );
    }

    activate(event) {
        super.activate(event);
        this._systemActions.activateRestart();
    }
});

export const SuspendButton = GObject.registerClass({
}, class SuspendButton extends SessionButton {
    _init(systemActions) {
        super._init(systemActions, _("Suspend"), 'media-playback-pause-symbolic');

        let bindFlags = GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE;
        this._systemActions.bind_property('can-suspend',
            this, 'visible',
            bindFlags
        );
    }

    activate(event) {
        super.activate(event);
        this._systemActions.activateSuspend();
    }
});

export const LogoutButton = GObject.registerClass({
}, class LogoutButton extends SessionButton {
    _init(systemActions) {
        super._init(systemActions, _("Log Out"), 'application-exit-symbolic');

        let bindFlags = GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE;
        this._systemActions.bind_property('can-logout',
            this, 'visible',
            bindFlags
        );
    }

    activate(event) {
        super.activate(event);
        this._systemActions.activateLogout();
    }
});

export const LockButton = GObject.registerClass({
}, class LockButton extends SessionButton {
    _init(systemActions) {
        super._init(systemActions, _("Lock"), 'changes-prevent-symbolic');

        let bindFlags = GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE;
        this._systemActions.bind_property('can-lock-screen',
            this, 'visible',
            bindFlags
        );
    }

    activate(event) {
        super.activate(event);
        this._systemActions.activateLockScreen();
    }
});
