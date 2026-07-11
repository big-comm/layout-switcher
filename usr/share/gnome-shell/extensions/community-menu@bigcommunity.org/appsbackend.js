// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
/*
 * Zorin Menu: The official applications menu for Zorin OS.
 *
 * Copyright (C) 2016-2021 Zorin OS Technologies Ltd.
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

// Import Libraries
import Gio from 'gi://Gio';
import GMenu from 'gi://GMenu';
import Shell from 'gi://Shell';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import {EventEmitter} from 'resource:///org/gnome/shell/misc/signals.js';
import * as ParentalControlsManager from 'resource:///org/gnome/shell/misc/parentalControlsManager.js';

export const AppsBackend = class extends EventEmitter {
    constructor() {
        super();

        this._appSys = Shell.AppSystem.get_default();
        this._parentalControlsManager = ParentalControlsManager.getDefault();

        this._categories = [];
        this._appsByCategory = {};

        this._load();
        this.reloading = false;

        this._parentalControlsManager.connectObject('app-filter-changed', this._reload.bind(this), this);
        this._appSys.connectObject('installed-changed', this._reload.bind(this), this);
    }

    allAppsCategory() {
        return {
            get_name: () => _('All Apps'),
            get_menu_id: () => 'all_apps',
            get_icon: () => Gio.icon_new_for_string('view-app-grid-symbolic'),
        };
    }

    // Load data for a single menu category
    _loadCategory(categoryId, dir) {
        let iter = dir.iter();
        let nextType;
        while ((nextType = iter.next()) != GMenu.TreeItemType.INVALID) {
            if (nextType == GMenu.TreeItemType.ENTRY) {
                let entry = iter.get_entry();
                let id;
                try {
                    id = entry.get_desktop_file_id();
                } catch(e) {
                    continue;
                }
                let app = this._appSys.lookup_app(id);
                if (app && app.get_app_info().should_show() && (this._parentalControlsManager.shouldShowApp(app.app_info)))
                    this._appsByCategory[categoryId].push(app);
            } else if (nextType == GMenu.TreeItemType.DIRECTORY) {
                let subdir = iter.get_directory();
                if (!subdir.get_is_nodisplay())
                    this._loadCategory(categoryId, subdir);
            }
        }
    }

    // Load data for all menu categories
    _load() {
        this._menuTree = new GMenu.Tree({ menu_basename: 'applications.menu', flags: GMenu.TreeFlags.SORT_DISPLAY_NAME });
        this._menuTree.load_sync();
        this._menuTree.connectObject('changed', this._reload.bind(this), this);

        let root = this._menuTree.get_root_directory();
        let iter = root.iter();
        let nextType;
        while ((nextType = iter.next()) != GMenu.TreeItemType.INVALID) {
            if (nextType == GMenu.TreeItemType.DIRECTORY) {
                let dir = iter.get_directory();
                if (!dir.get_is_nodisplay()) {
                    let categoryId = dir.get_menu_id();
                    this._appsByCategory[categoryId] = [];
                    this._loadCategory(categoryId, dir);
                    if (this._appsByCategory[categoryId].length > 0) {
                        this._categories.push(dir);
                    }
                }
            }
        }
    }

    // Reload data for all menu categories
    _reload() {
        if (this.reloading) {
            return
        }
        this.reloading = true;

        this._menuTree?.disconnectObject(this);
        this._menuTree = null;

        this._categories = [];
        this._appsByCategory = {};

        this._load();

        this.reloading = false;
        this.emit('reload');
    }

    // Return a list of all apps (unsorted)
    _allApps() {
        let appsMap = new Map();

        // Get all apps, deduplicated by app ID
        for (let directory in this._appsByCategory) {
            for (let app of this._appsByCategory[directory]) {
                appsMap.set(app.get_id(), app);
            }
        }
        return [...appsMap.values()];
    }

    // Sort apps alphabetically by name
    _sortApps(apps) {
        if (!apps)
            return [];

        return apps.sort((a, b) =>
            a.get_name().toLowerCase().localeCompare(b.get_name().toLowerCase())
        );
    }

    // Return a list of all apps (sorted)
    getAllApps() {
        let apps = this._allApps();
        return this._sortApps(apps);
    }

    // Return a list of apps for a category (sorted)
    getAppsByCategory(category_menu_id) {
        if (category_menu_id == "all_apps") {
            return this.getAllApps();
        }

        if (category_menu_id) {
            let apps = this._appsByCategory[category_menu_id].slice();
            return this._sortApps(apps);
        }

        return [];
    }

    // Return a list of all categories
    getCategories() {
        return this._categories.slice();
    }

    // Destroy the Apps Backend object
    destroy() {
        this._appSys?.disconnectObject(this);
        this._appSys = null;

        this._parentalControlsManager?.disconnectObject(this);
        this._parentalControlsManager = null;

        this._menuTree?.disconnectObject(this);
        this._menuTree = null;

        this._categories = null;
        this._appsByCategory = null;

        this.reloading = null;

        this.emit('destroy');
    }
};
