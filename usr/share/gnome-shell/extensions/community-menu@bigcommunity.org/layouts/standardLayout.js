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

import * as BaseLayout from './baseLayout.js'
import * as MiscMenuItems from '../widgets/miscMenuItems.js';
import * as SearchEntry from '../widgets/searchEntry.js';
import * as Sections from '../sections.js';
import * as Utils from '../utils.js';
import * as Widgets from '../widgets/widgets.js';
import {getOrientationProp} from '../utils.js';

export const StandardLayout = GObject.registerClass({
}, class StandardLayout extends BaseLayout.BaseLayout {
    // Initialize the layout
    _init(appsBackend, panelInfo) {
        super._init(appsBackend, panelInfo);
        this.add_style_class_name("main-box");
        this.add_style_class_name("all-layout-box");
    }

    _loadLayout() {
        // Create Sections and Widgets
        this._categoriesSection = new Sections.CategoriesListSection(this._appsBackend);
        this._appsSection = new Sections.AppsListSection(this._appsBackend, false, this._monitorIndex);
        this._searchResults = this._appsSection.searchResults;
        this._searchEntry = new SearchEntry.SearchEntry(this._searchResults);
        this._allAppsButton = new MiscMenuItems.AllAppsMenuItem();
        this._backButton = new MiscMenuItems.BackMenuItem();
        this._verticalSeparator = new Widgets.VerticalSeparator();

        // Create Boxes
        this._leftBox = new St.BoxLayout({
            x_expand: true,
            y_expand: true,
            ...getOrientationProp(true),
            y_align: Clutter.ActorAlign.FILL,
            style_class: 'apps-box'
        });
        this._sidebar =  new Sections.SidebarSection();

        // Fill Left Box
        this._leftBox.add_child(this._categoriesSection);
        this._leftBox.add_child(this._appsSection);
        this._leftBox.add_child(this._allAppsButton);
        this._leftBox.add_child(this._backButton);
        this._leftBox.add_child(this._searchEntry);

        // Add Boxes
        this.add_child(this._leftBox);
        this.add_child(this._verticalSeparator.actor);
        this.add_child(this._sidebar);
    }

    _connectSignals() {
        this._categoriesSection.connectObject('selected', this._onSelectCategory.bind(this), this);
        this._appsSection.connectObject('activated', this._activated.bind(this), this);
        this._searchEntry.connectObject('notify::search-active', this._onSearchChanged.bind(this), this);
        this._searchEntry.connectObject('entry-key-press', this._onSearchEntryKeyPress.bind(this), this);
        this._searchResults.connectObject('screenshot-activated', this._onScreenshotActivated.bind(this), this);
        this._allAppsButton.connectObject('activated', this._onAllApps.bind(this), this);
        this._backButton.connectObject('activated', this.reset.bind(this), this);
        this._sidebar.connectObject('activated', this._activated.bind(this), this);
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

    reset() {
        this._searchEntry.clear();
        this._onSearchChanged();
    }

    updateHeight() {
        const availableHeight = this._availableHeight();
        const newHeight = this._sidebar.updateHeight(availableHeight);
        this.set_height(newHeight);
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

        this._verticalSeparator?.destroy();
        this._verticalSeparator = null;

        this._leftBox?.destroy();
        this._leftBox = null;

        this._sidebar?.destroy();
        this._sidebar = null;

        super._onDestroy();
    }
});
