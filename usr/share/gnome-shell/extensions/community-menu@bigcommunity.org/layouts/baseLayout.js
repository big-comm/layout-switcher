// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
/*
 * Zorin Menu: The official applications menu for Zorin OS.
 *
 * Copyright (C) 2016-2025 Zorin OS Technologies Ltd.
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
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import * as Constants from '../constants.js';
import * as Utils from '../utils.js';
import {getOrientationProp} from '../utils.js';

export const BaseLayout = GObject.registerClass({
    Signals: {
        'activated': {},
        'screenshot-activated': {},
    }
}, class BaseLayout extends St.BoxLayout {
    _init(appsBackend, panelInfo) {
        super._init({
            reactive: true,
            ...getOrientationProp(false)
        });

        this._appsBackend = appsBackend;
        this._panelParent = panelInfo.panelParent;
        this._monitorIndex = panelInfo.monitorIndex;
        this._loadLayout();
        this._connectSignals();
        this.reset();
        this.connectObject('key-press-event', this._onKeyPress.bind(this), this);
        this.connect('destroy', () => this._onDestroy());
    }

    _loadLayout() {
    }

    _connectSignals() {
    }

    // Handle key presses
    _onKeyPress(actor, event) {
        Utils.blockHover();

        const symbol = event.get_key_symbol();
        const unicode = Clutter.keysym_to_unicode(symbol);

        if (this._searchEntry && (symbol === Clutter.KEY_Control_L || symbol === Clutter.KEY_Control_R)) {
            global.stage.set_key_focus(this._searchEntry.clutter_text);
            this._searchEntry.clutter_text.event(event, false);
            return Clutter.EVENT_PROPAGATE;
        }

        switch (symbol) {
        case Clutter.KEY_Tab:
        case Clutter.KEY_ISO_Left_Tab:
        case Clutter.KEY_Up: case Clutter.KEY_KP_Up:
        case Clutter.KEY_Down: case Clutter.KEY_KP_Down:
        case Clutter.KEY_Left: case Clutter.KEY_KP_Left:
        case Clutter.KEY_Right: case Clutter.KEY_KP_Right: {
            let direction;
            if (symbol === Clutter.KEY_Down || symbol === Clutter.KEY_KP_Down)
                direction = St.DirectionType.DOWN;
            else if (symbol === Clutter.KEY_Right || symbol === Clutter.KEY_KP_Right)
                direction = St.DirectionType.RIGHT;
            else if (symbol === Clutter.KEY_Up || symbol === Clutter.KEY_KP_Up)
                direction = St.DirectionType.UP;
            else if (symbol === Clutter.KEY_Left || symbol === Clutter.KEY_KP_Left)
                direction = St.DirectionType.LEFT;
            else if (symbol === Clutter.KEY_Tab)
                direction = St.DirectionType.TAB_FORWARD;
            else if (symbol === Clutter.KEY_ISO_Left_Tab)
                direction = St.DirectionType.TAB_BACKWARD;

            if (this._searchEntry && this._searchEntry.has_key_focus() &&
                this._searchResults?.hasActiveResult() && this._searchResults?.get_parent()) {
                const topSearchResult = this._searchResults.getTopResult();
                if (topSearchResult.has_style_pseudo_class('focus')) {
                    topSearchResult.grab_key_focus();
                    topSearchResult.remove_style_pseudo_class('focus');
                    return actor.navigate_focus(global.stage.key_focus, direction, false);
                }
                topSearchResult.grab_key_focus();
                return Clutter.EVENT_STOP;
            } else if (global.stage.key_focus === this && symbol === Clutter.KEY_Up) {
                return actor.navigate_focus(global.stage.key_focus, direction, true);
            } else if (global.stage.key_focus === this) {
                if (this._categoriesSection && this._categoriesSection.visible) {
                    this._categoriesSection.grab_key_focus();
                } else if (this._appsSection && this._appsSection.visible) {
                    this._appsSection.grab_key_focus();
                } else if (this._placesSection) {
                    this._placesSection.grab_key_focus();
                }
                return Clutter.EVENT_STOP;
            }
            return actor.navigate_focus(global.stage.key_focus, direction, false);
        }
        case Clutter.KEY_KP_Enter:
        case Clutter.KEY_Return:
        case Clutter.KEY_Escape:
            return Clutter.EVENT_PROPAGATE;
        default:
            if (this._searchEntry?.shouldTriggerSearch(symbol)) {
                this._searchEntry.startSearch(event);
            }
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _onSearchEntryKeyPress(actor, event) {
        const symbol = event.get_key_symbol();
        switch (symbol) {
        case Clutter.KEY_Up:
        case Clutter.KEY_Down:
        case Clutter.KEY_Left:
        case Clutter.KEY_Right: {
            let direction;
            if (symbol === Clutter.KEY_Down || symbol === Clutter.KEY_Up)
                return Clutter.EVENT_PROPAGATE;
            if (symbol === Clutter.KEY_Right)
                direction = St.DirectionType.RIGHT;
            if (symbol === Clutter.KEY_Left)
                direction = St.DirectionType.LEFT;

            let cursorPosition = this._searchEntry.clutter_text.get_cursor_position();

            if (cursorPosition === Constants.CaretPosition.END && symbol === Clutter.KEY_Right)
                cursorPosition = Constants.CaretPosition.END;
            else if (cursorPosition === Constants.CaretPosition.START && symbol === Clutter.KEY_Left)
                cursorPosition = Constants.CaretPosition.START;
            else
                cursorPosition = Constants.CaretPosition.MIDDLE;

            if (cursorPosition === Constants.CaretPosition.END || cursorPosition === Constants.CaretPosition.START) {
                if (this._searchResults.hasActiveResult()) {
                    const navigateActor = this._searchResults.getTopResult();
                    if (!navigateActor)
                        return Clutter.EVENT_PROPAGATE;

                    if (navigateActor.has_style_pseudo_class('focus')) {
                        navigateActor.grab_key_focus();
                        navigateActor.remove_style_pseudo_class('focus');
                        return this.navigate_focus(navigateActor, direction, false);
                    }
                    navigateActor.grab_key_focus();
                    return Clutter.EVENT_STOP;
                }
            }
            return Clutter.EVENT_PROPAGATE;
        }
        default:
            return Clutter.EVENT_PROPAGATE;
        }
    }

    reset(){
    }

    _availableHeight() {
        const scaleFactor = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        let availableHeight = Main.layoutManager.monitors[this._monitorIndex]?.height
            ?? Main.layoutManager.primaryMonitor?.height ?? 0;

        const panelHeight = this._panelParent.get_height();
        const panelWidth = this._panelParent.get_width();
        if (panelHeight < panelWidth) {
            // Only subtract panel height if the panel is horizontal
            availableHeight -= panelHeight;
            availableHeight -= (Constants.AVAIL_HEIGHT_PADDING * scaleFactor);
        }

        return Math.max(availableHeight, 0);
    }

    updateHeight() {
    }

    _activated() {
        this.emit('activated');
    }

    _onScreenshotActivated() {
        this.emit('screenshot-activated');
    }

    _onDestroy() {
        this._appsBackend = null;
        this._panelParent = null;
        this._monitorIndex = null;
    }
});
