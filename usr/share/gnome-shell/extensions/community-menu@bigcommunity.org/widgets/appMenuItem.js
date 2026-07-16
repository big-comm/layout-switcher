// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as IconGrid from 'resource:///org/gnome/shell/ui/iconGrid.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import * as BaseMenuItem from './baseMenuItem.js';
import * as Constants from '../constants.js';
import * as SecondaryMenu from './secondaryMenu.js';
import * as Utils from '../utils.js';
import {getOrientationProp} from '../utils.js';

export const AppMenuItem = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class AppMenuItem extends BaseMenuItem.BaseMenuItem {
    _init(app, isGrid, iconSize = Constants.APP_LIST_ICON_SIZE) {
        super._init();
        this._isGrid = isGrid;
        this._iconSize = iconSize;
        this.app = app;
        this.hasContextMenu = !!this.app;
        this.useTooltip = true;
        this._iconBin = new St.Bin({
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._iconBin);
        this.actor.add_style_class_name("app-item");

        let appLabel = new St.Label({
            text: this.app ? this.app.get_name() : "",
            x_expand: true,
            y_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            y_align: Clutter.ActorAlign.CENTER
        });
        this.add_child(appLabel);
        this.label_actor = appLabel;


        if (this.app) {
            this.description = this.app.get_description();
            this.connectObject('popup-menu', this.popupMenu.bind(this), this);
            this._menuManager = new PopupMenu.PopupMenuManager(this);
        }
        this._updateIcon();
        this._menu = null;

        if (this._isGrid) {
            this._setGrid();
        }
    }

    _setGrid() {
        this._iconBin.x_align = Clutter.ActorAlign.CENTER;
        this._iconBin.y_align = Clutter.ActorAlign.START;
        this._iconBin.y_expand = false;
        this.label_actor.y_align = Clutter.ActorAlign.START;
        this.label_actor.y_expand = false;
        this.label_actor.get_clutter_text().set({
            line_wrap: true,
            line_wrap_mode: Pango.WrapMode.WORD_CHAR,
        });
        this.set({...getOrientationProp(true)});
        this._iconSize = Constants.APP_GRID_ICON_SIZE;
        this._updateIcon();
    }

    _launchApp(event) {
        if (this.app) {
            if (this.app.can_open_new_window()) {
                this.animateLaunch();
                this.app.open_new_window(-1);
            } else {
                if (this.app.state == Shell.AppState.STOPPED) {
                    this.animateLaunch();
                }
                this.app.activate();
            }
        }
    } 

    // Activate menu item (Launch application)
    activate(event) {
        this._launchApp(event);
        this.emit('activated');
        super.activate(event);
    }

    // Update the app icon in the menu
    _updateIcon() {
        if (this.isDestroyed)
        return;

        const icon = this.app.create_icon_texture(this._iconSize);
        if (icon) {
            icon.style_class = this._isGrid ? '' : 'popup-menu-icon';
        }
        this._iconBin.set_child(icon);
    }

    popupMenu() {
        if (!this.app) {
            return;
        }

        this.tooltip?.hide();

        if (!this._menu) {
            this._menu = new SecondaryMenu.AppItemMenu(this);
            this._menu.connect('activate-window', () => {
                this.emit('activated');
            });

            // We want to keep the item hovered while the menu is up
            this._menu.blockSourceEvents = true;

            this._menuManager.addMenu(this._menu);
        }

        this._menu.open(BoxPointer.PopupAnimation.FULL);

        return false;
    }

    animateLaunch() {
        IconGrid.zoomOutActor(this._iconBin);
    }

    _onDestroy() {
        this._iconBin?.destroy();
        this._iconBin = null;

        this.label_actor?.destroy();
        this.label_actor = null;

        this._menu?.destroy();
        this._menu = null;
        this._menuManager = null;

        super._onDestroy();
    }
});
