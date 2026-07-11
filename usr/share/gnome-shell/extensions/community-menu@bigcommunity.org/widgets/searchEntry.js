// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as EntryMenu from './entryMenu.js';
import * as Utils from '../utils.js';

// Search Entry class
export const SearchEntry = GObject.registerClass({
    Signals: {
        'entry-key-press': {param_types: [Clutter.Event.$gtype]},
    },
    Properties: {
        'search-active': GObject.ParamSpec.boolean(
            'search-active', 'search-active', 'search-active',
            GObject.ParamFlags.READABLE,
            false),
    }
}, class SearchEntry extends St.Entry {
    _init(searchResults) {
        super._init({
            name: 'search-entry',
            style_class: 'search-entry',
            hint_text: _("Type to search"),
            track_hover: true,
            can_focus: true,
            x_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            y_align: Clutter.ActorAlign.START
        });
        EntryMenu.addContextMenu(this);
        this._searchIcon = new St.Icon({
            style_class: 'search-entry-icon',
            icon_name: 'edit-find-symbolic',
            icon_size: 16
        });
        this._clearIcon = new St.Icon({
            style_class: 'search-entry-icon',
            icon_name: 'edit-clear-symbolic',
            icon_size: 16
        });
        this.set_primary_icon(this._searchIcon);
        this.connect('secondary-icon-clicked', this.clear.bind(this));

        this._searchResults = searchResults;
        this._searchActive = false;

        this.connect('button-press-event', this._onButtonPress.bind(this));
        this.clutter_text.connect('button-press-event', this._onButtonPress.bind(this));

        this.connect('popup-menu', () => {
            if (!this._searchActive) {
                this._openMenu();
                return;
            }

            this.menu.close();
            this._searchResults?.popupMenuDefault();
        });

        this._text = this.get_clutter_text();
        this._text.connectObject('text-changed', this._onTextChanged.bind(this), this);
        this._text.connectObject('key-press-event', this._onKeyPress.bind(this), this);
        this._text.connect('key-focus-in', () => {
            this._searchResults?.highlightDefault(true);
        });
        this._text.connect('key-focus-out', () => {
            this._searchResults?.highlightDefault(false);
        });

        global.stage.connectObject('notify::key-focus', this._onStageKeyFocusChanged.bind(this), this);

        this.connect('destroy', () => this._onDestroy());
    }

    _openMenu(stageX) {
        if (stageX) {
            let [success, entryX] = this.transform_stage_point(stageX, 0);
            if (success)
                this.menu.setSourceAlignment(entryX / this.width);
        } else {
            let cursorPosition = this.clutter_text.get_cursor_position();
            let [success, textX, textY_, lineHeight_] = this.clutter_text.position_to_coords(cursorPosition);
            if (success)
                this.menu.setSourceAlignment(textX / this.width);
        }
        this.menu.open(BoxPointer.PopupAnimation.FULL);
    }

    _onButtonPress(actor, event) {
        if (this.menu.isOpen) {
            this.menu.close(BoxPointer.PopupAnimation.FULL);
            return Clutter.EVENT_STOP;
        } else if (event.get_button() === Clutter.BUTTON_SECONDARY) {
            let [x] = event.get_coords();
            this._openMenu(x);
            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    get searchActive() {
        return this._searchActive;
    }

    _setSearchActive(searchActive) {
        if (this._searchActive === searchActive)
            return;

        this._searchActive = searchActive;
        this.notify('search-active');
    }

    startSearch(event) {
        global.stage.set_key_focus(this._text);
        this._text.event(event, false);
    }

    has_key_focus() {
        const keyFocus = global.stage.get_key_focus();
        return keyFocus ? this.contains(keyFocus) : false;
    }

    // Clear the search box
    clear() {
        this.set_text('');
        this._text.set_cursor_visible(true);
        this._text.set_selection(0, 0);
        this.grab_key_focus();
    }

    _setClearIcon() {
       this.set_secondary_icon(this._clearIcon);
    }

    _unsetClearIcon() {
        this.set_secondary_icon(null);
    }

    _onStageKeyFocusChanged() {
        if (!this._searchResults) {
            return;
        }

        let focus = global.stage.get_key_focus();
        let appearFocused = this.contains(focus) || this._searchResults.contains(focus);

        this._text.set_cursor_visible(appearFocused);

        if (appearFocused)
            this.add_style_pseudo_class('focus');
        else
            this.remove_style_pseudo_class('focus');
    }

    _onKeyPress(actor, event) {
        const symbol = event.get_key_symbol();

        if (this._searchActive) {
            if (symbol == Clutter.KEY_KP_Enter || symbol == Clutter.KEY_Return) {
                this._searchResults?.activateDefault();
                return Clutter.EVENT_STOP;
            }
        }
        this.emit('entry-key-press', event);
        return Clutter.EVENT_PROPAGATE;
    }

    _getTermsForSearchString(searchString) {
        searchString = searchString.replace(/^\s+/g, '').replace(/\s+$/g, '');
        if (searchString === '')
            return [];
        return searchString.split(/\s+/);
    }

    shouldTriggerSearch(symbol) {
        if (symbol === Clutter.KEY_Multi_key)
            return true;

        if (symbol === Clutter.KEY_BackSpace && this._searchActive)
            return true;

        let unicode = Clutter.keysym_to_unicode(symbol);
        if (unicode === 0)
            return false;

        if (this._getTermsForSearchString(String.fromCharCode(unicode)).length > 0)
            return true;

        return false;
    }

    // Handle search text entry input changes
    _onTextChanged() {
        let terms = this._getTermsForSearchString(this.get_text());
        const searchActive = terms.length > 0;
        if (searchActive)
            Utils.blockHover();
        this._searchResults?.setTerms(terms);

        if (searchActive) {
            this._setSearchActive(true);
            this._setClearIcon();
        } else {
            this._unsetClearIcon();
            this._setSearchActive(false);
            if (this._text.text !== '')
                this.clear();
        }
    }

    _onDestroy() {
        global.stage.disconnectObject(this);

        this._searchResults = null;
        this._searchActive = null;
        this._text = null;

        this._searchIcon?.destroy();
        this._searchIcon = null;
        this._clearIcon?.destroy();
        this._clearIcon = null;
    }
});
