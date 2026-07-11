// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import AccountsService from 'gi://AccountsService';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Params from 'resource:///org/gnome/shell/misc/params.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Util from 'resource:///org/gnome/shell/misc/util.js';

import * as BaseMenuItem from './baseMenuItem.js';
import * as Constants from '../constants.js';
import * as SecondaryMenu from './secondaryMenu.js';

export const Avatar = GObject.registerClass({
}, class Avatar extends St.Bin {
    _init(user, params) {
        params = Params.parse(params, {
            reactive: false,
            iconSize: Constants.APP_LIST_ICON_SIZE,
            styleClass: 'menu-user-avatar'
        });

        this._iconSize = params.iconSize;

        super._init({
            style_class: params.styleClass,
            reactive: params.reactive,
            style: `width: ${this._iconSize}px; height: ${this._iconSize}px;`,
        });

        this._user = user;

        this.bind_property('reactive', this, 'track-hover',
            GObject.BindingFlags.SYNC_CREATE);
        this.bind_property('reactive', this, 'can-focus',
            GObject.BindingFlags.SYNC_CREATE);
    }

    update() {
        let iconFile = null;
        if (this._user) {
            iconFile = this._user.get_icon_file();
            if (iconFile && !GLib.file_test(iconFile, GLib.FileTest.EXISTS))
                iconFile = null;
        }

        if (iconFile) {
            if (this.child)
                this.child.destroy();
            this.child = null;
            this.add_style_class_name('user-avatar');
            this.style = `
                background-image: url("${iconFile}");
                background-size: cover;
                width: ${this._iconSize}px;
                height: ${this._iconSize}px;`;
        } else {
            this.style = `width: ${this._iconSize}px; height: ${this._iconSize}px;`;
            this.child = new St.Icon({
                icon_name: 'avatar-default-symbolic',
                icon_size: this._iconSize,
                style: `width: ${this._iconSize}px; height: ${this._iconSize}px;`,
            });
        }
    }
});

export const UserMenuItem = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class UserMenuItem extends BaseMenuItem.BaseMenuItem {
    _init() {
        super._init();
        this.useTooltip = true;
        let username = GLib.get_user_name();
        this.description = username;
        this._user = AccountsService.UserManager.get_default().get_user(username);
        this._avatar = new Avatar(this._user);
        this.add_child(this._avatar);
        this._userLabel = new St.Label({
            text: username,
            y_expand: true,
            y_align: Clutter.ActorAlign.CENTER
        });
        this.add_style_class_name('user-menu-item');
        this.add_child(this._userLabel);
        this.label_actor = this._userLabel;
        this._user.connectObject('notify::is-loaded', this._onUserChanged.bind(this), this);
        this._user.connectObject('changed', this._onUserChanged.bind(this), this);
        this._onUserChanged();
    }

    _createTooltip(){
        super._createTooltip();
        if (this.tooltip)
            this.tooltip.location = Constants.TooltipLocation.BOTTOM_CENTERED;
    }

    // Activate the menu item (Open user account settings)
    activate(event) {
        this.emit('activated');
        Util.spawnCommandLine("gnome-control-center system users");
        super.activate(event);
    }

    // Handle changes to user information (redisplay new info)
    _onUserChanged() {
        if (this._user.is_loaded) {
            this._userLabel.set_text(this._user.get_real_name());
            this._avatar.update();
        }
    }

    _onDestroy() {
        this._user?.disconnectObject(this);
        this._user = null;

        this._avatar?.destroy();
        this._avatar = null;

        this._userLabel?.destroy();
        this._userLabel = null;
        this.label_actor = null;

        super._onDestroy();
    }
});

export const UserMenuButton = GObject.registerClass({
}, class UserMenuButton extends UserMenuItem {
    _init(systemActions) {
        super._init();
        this._systemActions = systemActions;
        this._menuManager = new PopupMenu.PopupMenuManager(this);
        this._createUserMenu();
        this.hasContextMenu = true;
        this.connect('popup-menu', () => this.userMenu.toggle());

        this._lockItem.connect('notify::visible',
            () => this._updateSeparatorVisibility());
        this._switchUserItem.connect('notify::visible',
            () => this._updateSeparatorVisibility());
        this._logoutItem.connect('notify::visible',
            () => this._updateSeparatorVisibility());
        this._updateSeparatorVisibility()
    }

    _createTooltip(){
        super._createTooltip();
        if (this.tooltip)
            this.tooltip.location = Constants.TooltipLocation.TOP_CENTERED;
    }

    _createUserMenu(){
        this.userMenu = new SecondaryMenu.ButtonMenu(this);
        this.userMenu.connect('open-state-changed', (menu, open) => {
            if(open){
                this.tooltip?.hide();
                this._systemActions.forceUpdate();
            }
        });

        let bindFlags = GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE;

        this._accountSettingsItem = new PopupMenu.PopupImageMenuItem(_("Account Settings"), 'avatar-default-symbolic');
        this._accountSettingsItem.connect('activate', () => {
            this.userMenu.itemActivated(BoxPointer.PopupAnimation.NONE);
            this.emit('activated');
            Util.spawnCommandLine("gnome-control-center system users");
        });
        this.userMenu.addMenuItem(this._accountSettingsItem);

        this._separatorItem = new PopupMenu.PopupSeparatorMenuItem();
        this.userMenu.addMenuItem(this._separatorItem);

        this._lockItem = new PopupMenu.PopupImageMenuItem(_("Lock"), 'changes-prevent-symbolic');
        this._lockItem.connect('activate', () => {
            this.userMenu.itemActivated(BoxPointer.PopupAnimation.NONE);
            this.emit('activated');
            this._systemActions.activateLockScreen();
        });
        this.userMenu.addMenuItem(this._lockItem);
        this._systemActions.bind_property('can-lock-screen',
            this._lockItem, 'visible',
            bindFlags
        );

        this._switchUserItem = new PopupMenu.PopupImageMenuItem(_("Switch User…"), 'system-switch-user-symbolic');
        this._switchUserItem.connect('activate', () => {
            this.userMenu.itemActivated(BoxPointer.PopupAnimation.NONE);
            this.emit('activated');
            this._systemActions.activateSwitchUser();
        });
        this.userMenu.addMenuItem(this._switchUserItem);
        this._systemActions.bind_property('can-switch-user',
            this._switchUserItem, 'visible',
            bindFlags
        );

        this._logoutItem = new PopupMenu.PopupImageMenuItem(_("Log Out…"), 'application-exit-symbolic');
        this._logoutItem.connect('activate', () => {
            this.userMenu.itemActivated(BoxPointer.PopupAnimation.NONE);
            this.emit('activated');
            this._systemActions.activateLogout();
        });
        this.userMenu.addMenuItem(this._logoutItem);
        this._systemActions.bind_property('can-logout',
            this._logoutItem, 'visible',
            bindFlags
        );

        this._menuManager.addMenu(this.userMenu);
        this.userMenu.actor.hide();
        Main.uiGroup.add_child(this.userMenu.actor);
    }

    _updateSeparatorVisibility() {
        if (this.isDestroyed)
            return;

        this._separatorItem.visible =
            this._lockItem.visible ||
            this._switchUserItem.visible ||
            this._logoutItem.visible;
    }

    activate(event) {
        this.userMenu.toggle();
    }

    _onDestroy() {
        this.isDestroyed = true;

        this._systemActions = null;

        this._accountSettingsItem?.destroy();
        this._accountSettingsItem = null;

        this._separatorItem?.destroy();
        this._separatorItem = null;

        this._lockItem?.destroy();
        this._lockItem = null;

        this._switchUserItem?.destroy();
        this._switchUserItem = null;

        this._logoutItem?.destroy();
        this._logoutItem = null;

        this.userMenu?.actor?.get_parent()?.remove_child(this.userMenu.actor);
        this.userMenu?.destroy();
        this.userMenu = null;
        this._menuManager = null;

        super._onDestroy();
    }
});
