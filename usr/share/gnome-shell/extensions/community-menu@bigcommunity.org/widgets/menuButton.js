// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Constants from '../constants.js';
import {EXTENSION_PATH} from '../extension.js';

export const MenuButton = GObject.registerClass({
}, class MenuButton extends St.BoxLayout {
    _init() {
        super._init({
            style_class: 'panel-status-menu-box'
        });

        this._icon = new St.Icon({
            icon_size: Constants.MENU_BUTTON_ICON_SIZE,
            style_class: 'community-menu-button-icon'
        });
        this._setIcon();
        this.add_child(this._icon);

        this.connect('destroy', this._onDestroy.bind(this));
    }

    _setIcon() {
        const menu_icon = `${EXTENSION_PATH}/community-menu.svg`;
        this._icon.set_gicon(Gio.icon_new_for_string(menu_icon));
    }

    _onDestroy() {
        this._icon?.destroy();
        this._icon = null;
    }
});
