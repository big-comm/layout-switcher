// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Util from 'resource:///org/gnome/shell/misc/util.js';

import * as BaseMenuItem from './baseMenuItem.js';
import * as Constants from '../constants.js';
import * as Utils from '../utils.js';

// Menu item to go back to category view
export const BackMenuItem = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class BackMenuItem extends BaseMenuItem.BaseMenuItem {
    _init() {
        super._init();
        this._icon = new St.Icon({
            icon_name: 'go-previous-symbolic',
            style_class: 'popup-menu-icon',
            icon_size: Constants.APP_LIST_ICON_SIZE
        });
        this.add_child(this._icon);
        let backLabel = new St.Label({
            text: _("Back"),
            y_expand: true,
            y_align: Clutter.ActorAlign.CENTER
        });
        this.add_child(backLabel);
    }

    // Activate the button (go back to category view)
    activate(event) {
        this.emit('activated');
        super.activate(event);
    }

    _onDestroy() {
        this._icon?.destroy();
        this._icon = null;

        super._onDestroy();
    }
});

export const ShortcutMenuItem = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class ShortcutMenuItem extends BaseMenuItem.BaseMenuItem {
    _init(name, command, icon, fallbackIcon) {
        super._init();
        this._command = command;
        this._icon = new St.Icon({
            icon_name: icon,
            style_class: 'popup-menu-icon',
            icon_size: 16
        });
        if (fallbackIcon && (typeof fallbackIcon == 'string' || fallbackIcon instanceof String))
            this._icon.set_fallback_icon_name(fallbackIcon);
        this.add_child(this._icon);
        let label = new St.Label({
            text: name, y_expand: true,
            y_align: Clutter.ActorAlign.CENTER
        });
        this.add_child(label);
    }

    commandExists() {
        return Utils.checkIfCommandExists(this._command[0]);
    }

    // Activate the menu item (Launch the shortcut)
    activate(event) {
        this.emit('activated');
        Util.spawn(this._command);
        super.activate(event);
    }

    _onDestroy() {
        this._icon?.destroy();
        this._icon = null;

        this._command = null;

        super._onDestroy();
    }
});

export const CategoryMenuItem = GObject.registerClass({
    Signals: {
        'selected': { param_types: [GObject.TYPE_STRING] },
    }
}, class CategoryMenuItem extends BaseMenuItem.BaseMenuItem {
    _init(category, iconSize = Constants.APP_LIST_ICON_SIZE) {
        super._init();
        this._category = category;
        let name = this._category?.get_name();
        this._icon = new St.Icon({
            gicon: this._category?.get_icon(),
            style_class: 'popup-menu-icon',
            icon_size: iconSize
        });
        this.add_child(this._icon);
        let categoryLabel = new St.Label({
            text: name,
            y_expand: true,
            y_align: Clutter.ActorAlign.CENTER
        });
        this.add_child(categoryLabel);
        this.label_actor = categoryLabel;
        this._arrowIcon = new St.Icon({
            icon_name: 'go-next-symbolic',
            style_class: 'popup-menu-icon',
            x_expand: true,
            x_align: Clutter.ActorAlign.END,
            icon_size: 12,
            opacity: 128
        });
        this.add_child(this._arrowIcon);
    }

    // Activate menu item (Display applications in category)
    activate(event) {
        this.emit('selected', this._category?.get_menu_id());
        super.activate(event);
    }

    _onDestroy() {
        this._icon?.destroy();
        this._icon = null;

        this.label_actor?.destroy();
        this.label_actor = null;

        this._arrowIcon?.destroy();
        this._arrowIcon = null;

        this._category = null;

        super._onDestroy();
    }
});

export const CategoryHoverMenuItem = GObject.registerClass({
}, class CategoryHoverMenuItem extends CategoryMenuItem {
    _init(category) {
        super._init(category);
        this._keepActive = true;
        this.track_hover = false;
        this.hover = false;
    }

    _onPressed() {
    }

    _onClicked(action) {
        const isPrimaryOrTouch = action.get_button() === Clutter.BUTTON_PRIMARY || action.get_button() === 0;
        const isMiddleButton = action.get_button() === Clutter.BUTTON_MIDDLE || action.get_button() === 2;
        if (isPrimaryOrTouch || isMiddleButton) {
            this.activate(Clutter.get_current_event());
        }
    }

    _onLongPress() {
    }

    vfunc_motion_event() {
        // Prevent a mouse hover event from setting a new active menu item, until next mouse move event.
        if (Utils.isBlockHover()) {
            Utils.blockHover(false);
        }
        return Clutter.EVENT_PROPAGATE;
    }

    vfunc_key_focus_in() {
        super.vfunc_key_focus_in();
        this.activate(Clutter.get_current_event());
    }
});

// Menu item to go to all apps view
export const AllAppsMenuItem = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class AllAppsMenuItem extends BaseMenuItem.BaseMenuItem {
    _init() {
        super._init();
        this._icon = new St.Icon({
            icon_name: 'view-app-grid-symbolic',
            style_class: 'popup-menu-icon',
            icon_size: Constants.APP_LIST_ICON_SIZE
        });
        this.add_child(this._icon);
        let label = new St.Label({
            text: _("All Apps"),
            x_expand: false,
            x_align: Clutter.ActorAlign.START,
            y_expand: true,
            y_align: Clutter.ActorAlign.CENTER
        });
        this.add_child(label);
    }

    // Activate the button
    activate(event) {
        this.emit('activated');
        super.activate(event);
    }

    _onDestroy() {
        this._icon?.destroy();
        this._icon = null;

        super._onDestroy();
    }
});
