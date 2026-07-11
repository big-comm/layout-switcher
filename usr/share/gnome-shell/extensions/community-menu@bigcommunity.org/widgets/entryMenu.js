// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
// Based on ui.shellEntry from GNOME Shell but with disable PopupMenu onKeyPress handling

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Params from 'resource:///org/gnome/shell/misc/params.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

export class EntryMenu extends PopupMenu.PopupMenu {
    constructor(entry) {
        super(entry, 0, St.Side.TOP);

        this._entry = entry;
        this._clipboard = St.Clipboard.get_default();

        // Populate menu
        let item;
        item = new PopupMenu.PopupMenuItem(_('Copy'));
        item.connectObject('activate', this._onCopyActivated.bind(this), this);
        this.addMenuItem(item);
        this._copyItem = item;

        item = new PopupMenu.PopupMenuItem(_('Paste'));
        item.connectObject('activate', this._onPasteActivated.bind(this), this);
        this.addMenuItem(item);
        this._pasteItem = item;

        if (entry instanceof St.PasswordEntry)
            this._makePasswordItem();

        Main.uiGroup.add_child(this.actor);
        this.actor.hide();
    }

    _makePasswordItem() {
        let item = new PopupMenu.PopupMenuItem('');
        item.connectObject('activate', this._onPasswordActivated.bind(this), this);
        this.addMenuItem(item);
        this._passwordItem = item;

        this._entry.bind_property('show-peek-icon',
            this._passwordItem, 'visible',
            GObject.BindingFlags.SYNC_CREATE);
    }

    open(animate) {
        this._updatePasteItem();
        this._updateCopyItem();
        if (this._passwordItem)
            this._updatePasswordItem();

        super.open(animate);
        this._entry.add_style_pseudo_class('focus');

        let direction = St.DirectionType.TAB_FORWARD;
        if (!this.actor.navigate_focus(null, direction, false))
            this.actor.grab_key_focus();
    }

    _updateCopyItem() {
        let selection = this._entry.clutter_text.get_selection();
        this._copyItem.setSensitive(!this._entry.clutter_text.password_char &&
                                    selection && selection !== '');
    }

    _updatePasteItem() {
        this._clipboard.get_text(St.ClipboardType.CLIPBOARD,
            (clipboard, text) => {
                this._pasteItem.setSensitive(text && text !== '');
            });
    }

    _updatePasswordItem() {
        if (!this._entry.password_visible)
            this._passwordItem.label.set_text(_('Show Text'));
        else
            this._passwordItem.label.set_text(_('Hide Text'));
    }

    _onCopyActivated() {
        let selection = this._entry.clutter_text.get_selection();
        this._clipboard.set_text(St.ClipboardType.CLIPBOARD, selection);
    }

    _onPasteActivated() {
        this._clipboard.get_text(St.ClipboardType.CLIPBOARD,
            (clipboard, text) => {
                if (!text)
                    return;
                this._entry.clutter_text.delete_selection();
                let pos = this._entry.clutter_text.get_cursor_position();
                this._entry.clutter_text.insert_text(text, pos);
            });
    }

    _onPasswordActivated() {
        this._entry.password_visible  = !this._entry.password_visible;
    }

    _onKeyPress() {
        return Clutter.EVENT_PROPAGATE;
    }
};

/**
 * @param {St.Entry} entry
 * @param {*} params
 */
export function addContextMenu(entry, params) {
    if (entry.menu)
        return;

    params = Params.parse(params, {actionMode: Shell.ActionMode.POPUP});

    entry.menu = new EntryMenu(entry);
    entry._menuManager = new PopupMenu.PopupMenuManager(entry, {
        actionMode: params.actionMode,
    });
    entry._menuManager.addMenu(entry.menu);

    entry.connect('destroy', () => {
        entry.menu?.actor?.get_parent()?.remove_child(entry.menu.actor);
        entry.menu?.destroy();
        entry.menu = null;
        entry._menuManager = null;
    });
}
