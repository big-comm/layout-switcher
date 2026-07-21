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

import * as SystemActions from 'resource:///org/gnome/shell/misc/systemActions.js';

import * as BaseLayout from './baseLayout.js'
import * as Constants from '../constants.js';
import * as SearchEntry from '../widgets/searchEntry.js';
import * as Sections from '../sections.js';
import * as SessionButtons from '../widgets/sessionButtons.js';
import * as UserWidgets from '../widgets/userWidgets.js';
import * as Utils from '../utils.js';
import {getOrientationProp} from '../utils.js';

export const AppGridLayout = GObject.registerClass({
}, class AppGridLayout extends BaseLayout.BaseLayout {
    // Initialize the layout
    _init(appsBackend, panelInfo) {
        super._init(appsBackend, panelInfo);
        this.add_style_class_name("main-box");
        this.add_style_class_name("grid-layout-box");
    }

    _loadLayout() {
        // Create Sections and Widgets
        this._appsSection = new Sections.AppsListSection(this._appsBackend, true, this._monitorIndex);
        this._searchResults = this._appsSection.searchResults;
        this._searchEntry = new SearchEntry.SearchEntry(this._searchResults);
        this._searchEntry.x_expand = false;
        this._searchEntry.x_align = Clutter.ActorAlign.CENTER;
        this._headerBox = new St.BoxLayout({
            ...getOrientationProp(false),
            x_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            style_class: 'grid-header-box',
        });
        this._headerBox.add_child(this._searchEntry);

        this._systemActions = new SystemActions.getDefault();
        this._systemActions.forceUpdate();
        this._userButton = new UserWidgets.UserMenuButton(this._systemActions);
        this._userButton.x_align = Clutter.ActorAlign.START;
        this._sessionActions = [
            new SessionButtons.SuspendButton(this._systemActions),
            new SessionButtons.LogoutButton(this._systemActions),
            new SessionButtons.RestartButton(this._systemActions),
            new SessionButtons.PowerButton(this._systemActions),
        ];
        this._sessionActionsBox = new St.BoxLayout({
            ...getOrientationProp(false),
            x_expand: true,
            x_align: Clutter.ActorAlign.END,
            style_class: 'session-actions-box',
        });
        for (const button of this._sessionActions)
            this._sessionActionsBox.add_child(button);

        // Create and Fill Session Box
        this._sessionBox = new St.BoxLayout({
            ...getOrientationProp(false),
            x_expand: true,
            style_class: 'session-box'
        });
        this._sessionBox.add_child(this._userButton);
        this._sessionBox.add_child(this._sessionActionsBox);

        // Create Box
        this._box = new St.BoxLayout({
            ...getOrientationProp(true),
            style_class: 'grid-box'
        });

        // Fill Box
        this._box.add_child(this._headerBox);
        this._box.add_child(this._appsSection);
        this._box.add_child(this._sessionBox);

        // Add Box
        this.add_child(this._box);
    }

    _connectSignals() {
        this._appsSection.connectObject('activated', this._activated.bind(this), this);
        this._searchEntry.connectObject('notify::search-active', this._onSearchChanged.bind(this), this);
        this._searchEntry.connectObject('entry-key-press', this._onSearchEntryKeyPress.bind(this), this);
        this._searchResults.connectObject('screenshot-activated', this._onScreenshotActivated.bind(this), this);
        this._userButton.connectObject('activated', this._activated.bind(this), this);
        for (const button of this._sessionActions)
            button.connectObject('activated', this._activated.bind(this), this);
    }

    _onSearchChanged() {
        Utils.blockHover();
        const {searchActive} = this._searchEntry;
        if (searchActive) {
            this._appsSection.searchActive();
            this._searchEntry.grab_key_focus();
        } else {
            this._appsSection.displayAllApps();
            this._appsSection.grab_key_focus();
        }
    }

    reset(){
        this._searchEntry.clear();
        this._onSearchChanged();
    }

    updateHeight() {
        const scaleFactor = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const availableHeight = this._availableHeight();
        const naturalHeight = Constants.GRID_MENU_HEIGHT * scaleFactor;
        this.set_height((naturalHeight > availableHeight) ? availableHeight : naturalHeight);
    }

    _onDestroy() {
        this._systemActions = null;

        this._searchEntry?.destroy();
        this._searchEntry = null;

        this._headerBox?.destroy();
        this._headerBox = null;

        this._appsSection?.destroy();
        this._appsSection = null;
        this._searchResults = null;

        this._userButton?.destroy();
        this._userButton = null;

        for (const button of this._sessionActions ?? [])
            button?.destroy();
        this._sessionActions = null;

        this._sessionActionsBox?.destroy();
        this._sessionActionsBox = null;

        this._sessionBox?.destroy();
        this._sessionBox = null;

        this._box?.destroy();
        this._box = null;

        super._onDestroy();
    }
});
