// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {EventEmitter} from 'resource:///org/gnome/shell/misc/signals.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as BaseMenuItem from './baseMenuItem.js';

export const PlaceInfo = class extends EventEmitter {
    constructor(file, name, icon) {
        super();

        this.file = file;
        this.name = name ? name : this._getFileName();
        this.icon = icon ? new Gio.ThemedIcon({ name: icon }) : this.getIcon();
    }

    // Launch place with appropriate application
    launch(timestamp) {
        let launchContext = global.create_app_launch_context(timestamp, -1);
        Gio.AppInfo.launch_default_for_uri(this.file.get_uri(), launchContext);
    }

    // Get Icon for place
    getIcon() {
        this.file.query_info_async('standard::symbolic-icon',
            Gio.FileQueryInfoFlags.NONE,
            0,
            null,
            (file, result) => {
                try {
                    const info = file.query_info_finish(result);
                    this.icon = info.get_symbolic_icon();
                    this.emit('changed');
                } catch (e) {
                    if (e instanceof Gio.IOErrorEnum)
                        return;
                    throw e;
                }
            });

        // return a generic icon for this kind for now, until we have the
        // icon from the query info above
        if (!this.file.is_native())
            return new Gio.ThemedIcon({name: 'folder-remote-symbolic'});
        else
            return new Gio.ThemedIcon({name: 'folder-symbolic'});
    }

    // Get display name for place
    _getFileName() {
        if (this.file.get_path() === GLib.get_home_dir())
            return _('Home');
        try {
            const info = this.file.query_info('standard::display-name', 0, null);
            return info.get_display_name();
        } catch (e) {
            if (e instanceof Gio.IOErrorEnum)
                return this.file.get_basename();
            throw e;
        }
    }
};

// Menu Place Shortcut item class
export const PlaceMenuItem = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class PlaceMenuItem extends BaseMenuItem.BaseMenuItem {
    _init(info) {
        super._init();
        this._info = info;
        this._icon = new St.Icon({
            gicon: info.icon,
            icon_size: 16
        });
        this.add_child(this._icon);
        this._label = new St.Label({
            text: info.name,
            y_expand: true,
            y_align: Clutter.ActorAlign.CENTER
        });
        this.add_child(this._label);
        this._info.connectObject('changed', this._propertiesChanged.bind(this), this);
    }

    // Destroy menu item
    _onDestroy() {
        this._info?.disconnectObject(this);
        this._info = null;

        this._icon?.destroy();
        this._icon = null;

        this._label?.destroy();
        this._label = null;

        super._onDestroy();
    }

    // Activate (launch) the shortcut
    activate(event) {
        this._info.launch(event?.get_time() ?? 0);
        this.emit('activated');
        super.activate(event);
    }

    // Handle changes in place info (redisplay new info)
    _propertiesChanged(info) {
        this._icon.gicon = info.icon;
        this._label.text = info.name;
    }
});
