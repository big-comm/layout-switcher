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

import GObject from 'gi://GObject';
import St from 'gi://St';

import * as BaseLayout from './baseLayout.js'
import * as Constants from '../constants.js';
import * as MiscMenuItems from '../widgets/miscMenuItems.js';
import * as SearchEntry from '../widgets/searchEntry.js';
import * as Sections from '../sections.js';
import * as Utils from '../utils.js';
import {getOrientationProp} from '../utils.js';

export const AppListLayout = GObject.registerClass({
}, class AppListLayout extends BaseLayout.BaseLayout {
    // Initialize the layout
    _init(appsBackend, panelInfo) {
        super._init(appsBackend, panelInfo);
        this.add_style_class_name("main-box");
        this.add_style_class_name("apps-only-layout-box");
    }

    _loadLayout() {
        // Create Sections and Widgets
        this._categoriesSection = new Sections.CategoriesListSection(this._appsBackend);
        this._appsSection = new Sections.AppsListSection(this._appsBackend, false, this._monitorIndex);
        this._searchResults = this._appsSection.searchResults;
        this._searchEntry = new SearchEntry.SearchEntry(this._searchResults);
        this._allAppsButton = new MiscMenuItems.AllAppsMenuItem();
        this._backButton = new MiscMenuItems.BackMenuItem();

        // Create Box
        this._box = new St.BoxLayout({
            ...getOrientationProp(true),
            style_class: 'apps-box'
        });

        // Fill Box
        this._box.add_child(this._categoriesSection);
        this._box.add_child(this._appsSection);
        this._box.add_child(this._allAppsButton);
        this._box.add_child(this._backButton);
        this._box.add_child(this._searchEntry);

        // Add Box
        this.add_child(this._box);
    }

    _connectSignals() {
        this._categoriesSection.connectObject('selected', this._onSelectCategory.bind(this), this);
        this._appsSection.connectObject('activated', this._activated.bind(this), this);
        this._searchEntry.connectObject('notify::search-active', this._onSearchChanged.bind(this), this);
        this._searchEntry.connectObject('entry-key-press', this._onSearchEntryKeyPress.bind(this), this);
        this._searchResults.connectObject('screenshot-activated', this._onScreenshotActivated.bind(this), this);
        this._allAppsButton.connectObject('activated', this._onAllApps.bind(this), this);
        this._backButton.connectObject('activated', this.reset.bind(this), this);
    }

    _onSearchChanged() {
        Utils.blockHover();
        const {searchActive} = this._searchEntry;
        if (searchActive) {
            this._appsSection.searchActive();
            this._categoriesSection.hide();
            this._allAppsButton.hide();
            this._appsSection.show();
            this._backButton.show();
            this._searchEntry.grab_key_focus();
        } else {
            this._appsSection.hide();
            this._backButton.hide();
            this._categoriesSection.show();
            this._allAppsButton.show();
            this._categoriesSection.grab_key_focus();
        }
    }

    _onAllApps(actor) {
        this._onSelectCategory(actor, "all_apps");
    }

    _onSelectCategory(actor, category_menu_id){
        if (category_menu_id) {
            Utils.blockHover();
            this._appsSection.selectCategory(category_menu_id);
            this._categoriesSection.hide();
            this._allAppsButton.hide();
            this._appsSection.show();
            this._backButton.show();
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
        const naturalHeight = Constants.APPS_ONLY_MENU_HEIGHT * scaleFactor;
        this.set_height((naturalHeight > availableHeight) ? availableHeight : naturalHeight);
    }

    _onDestroy() {
        this._categoriesSection?.destroy();
        this._categoriesSection = null;

        this._searchEntry?.destroy();
        this._searchEntry = null;

        this._appsSection?.destroy();
        this._appsSection = null;
        this._searchResults = null;

        this._allAppsButton?.destroy();
        this._allAppsButton = null;

        this._backButton?.destroy();
        this._backButton = null;

        this._box?.destroy();
        this._box = null;

        super._onDestroy();
    }
});
