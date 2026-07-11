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

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as SystemActions from 'resource:///org/gnome/shell/misc/systemActions.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as AppMenuItem from './widgets/appMenuItem.js';
import * as Constants from './constants.js';
import * as MiscMenuItems from './widgets/miscMenuItems.js';
import * as PlaceMenuItem from './widgets/placeMenuItem.js';
import * as Search from './search.js';
import * as SessionButtons from './widgets/sessionButtons.js';
import * as UserWidgets from './widgets/userWidgets.js';
import * as Utils from './utils.js';
import * as Widgets from './widgets/widgets.js';
import {getOrientationProp} from './utils.js';

export const SessionButtonsSection = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class SessionButtonsSection extends PopupMenu.PopupBaseMenuItem {
    _init() {
        super._init({
            reactive: false,
            can_focus: false,
            style_class: 'session-buttons-section'
        });
        this.x_align = Clutter.ActorAlign.CENTER;
        this.y_align = Clutter.ActorAlign.END;
        this.y_expand = true;
        this._systemActions = new SystemActions.getDefault();
        this._systemActions.forceUpdate();

        // Add session buttons to section
        this._logout = new SessionButtons.LogoutButton(this._systemActions);
        this._logout.connectObject('activated', this._activated.bind(this), this);
        this.add_child(this._logout);

        this._lock = new SessionButtons.LockButton(this._systemActions);
        this._lock.connectObject('activated', this._activated.bind(this), this);
        this.add_child(this._lock);

        this._power = new SessionButtons.PowerMenuButton(this._systemActions);
        this._power.connectObject('activated', this._activated.bind(this), this);
        this.add_child(this._power);

        this.connect('destroy', () => this._onDestroy());
    }

    // Emit signal if one of the buttons is activated
    _activated() {
        this.emit('activated');
    }

    _onDestroy() {
        this._systemActions = null;

        this._logout?.destroy();
        this._logout = null

        this._lock?.destroy();
        this._lock = null

        this._power?.destroy();
        this._power = null;
    }
});

export const PlacesSection = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class PlacesSection extends St.BoxLayout {
    _init() {
        super._init({
            ...getOrientationProp(true)
        });
        this._items = [];

        // Fix for when XDG User Dirs are empty due to being cached too early during initialization
        GLib.reload_user_special_dirs_cache();

        let homePath = GLib.get_home_dir();
        let placeInfo = new PlaceMenuItem.PlaceInfo(Gio.File.new_for_path(homePath), _("Home"));
        let placeMenuItem = new PlaceMenuItem.PlaceMenuItem(placeInfo);
        this._items.push(placeMenuItem);

        for (let i = 0; i < Constants.DEFAULT_DIRECTORIES.length; i++) {
            let path = GLib.get_user_special_dir(Constants.DEFAULT_DIRECTORIES[i]);
            if (path == null || path == homePath)
                continue;
            let placeInfo = new PlaceMenuItem.PlaceInfo(Gio.File.new_for_path(path));
            let placeMenuItem = new PlaceMenuItem.PlaceMenuItem(placeInfo);
            this._items.push(placeMenuItem);
        }

        this._items.forEach(function(item) {
            this.add_child(item);
            item.connectObject('activated', this._activated.bind(this), this);
        }, this);

        this.connect('destroy', () => this._onDestroy());
    }

    grab_key_focus() {
        let item = this.get_first_child();
        if (item) {
            item.grab_key_focus();
        }
    }

    // Emit signal if one of the buttons is activated
    _activated() {
        this.emit('activated');
    }

    _onDestroy() {
        this._items = null;
    }
});

export const ShortcutsSection = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class ShortcutsSection extends St.BoxLayout {
    _init() {
        super._init({
            ...getOrientationProp(true)
        });
        this._items = [];

        let software = new MiscMenuItems.ShortcutMenuItem(_("Software"), ["gnome-software"], "gnome-software-symbolic", "org.gnome.Software-symbolic");
        if (software.commandExists())
            this._items.push(software);

        let settings = new MiscMenuItems.ShortcutMenuItem(_("Settings"), ["gnome-control-center"], "preferences-system-symbolic");
        if (settings.commandExists())
            this._items.push(settings);

        this._items.forEach(function(item) {
            this.add_child(item.actor);
            item.connectObject('activated', this._activated.bind(this), this);
        }, this);

        this.connect('destroy', () => this._onDestroy());
    }

    grab_key_focus() {
        let item = this.get_first_child();
        if (item) {
            item.grab_key_focus();
        }
    }

    // Emit signal if one of the buttons is activated
    _activated() {
        this.emit('activated');
    }

    _onDestroy() {
        this._items = null;
    }
});

export const CategoriesListSection = GObject.registerClass({
    Signals: {
        'selected': { param_types: [GObject.TYPE_STRING] },
    }
}, class CategoriesListSection extends St.Bin {
    // Initialize the button
    _init(appsBackend) {
        super._init({ x_expand: true, y_expand: true, style_class: 'categories-list', accessible_name: _('Categories')});
        this._appsBackend = appsBackend;
        this._categoryButtons = new Map();
        this._categoriesBox = new St.BoxLayout({...getOrientationProp(true)});
        this._scrollBox = new Widgets.ScrollView({
                x_expand: true,
                y_expand: true,
                x_align: Clutter.ActorAlign.FILL,
                y_align: Clutter.ActorAlign.FILL,
                style_class: 'apps-menu vfade',
                reactive:true
        });
        this._scrollBox.set_child(this._categoriesBox);
        this.set_child(this._scrollBox);
        this._load();
        this._appsBackend.connectObject('reload', this._reload.bind(this), this);
        this.connect('destroy', this._onDestroy.bind(this));
    }

    _load() {
        let categories = this._appsBackend.getCategories();
        categories.forEach(this._addCategoryButton, this);
    }

    _reload() {
        this._clear();
        this._clearCategoryButtons();
        this._load();
    }

    _addCategoryButton(category) {
        let button = this._categoryButtons.get(category);
        if (!button) {
            button = new MiscMenuItems.CategoryMenuItem(category);
            this._categoryButtons.set(category, button);
            button.connectObject('selected', this._selected.bind(this), this);
        }
        if (!button.get_parent()) {
            this._categoriesBox.add_child(button);
        }
    }

    _clearCategoryButtons() {
        this._categoryButtons.forEach(button => button.destroy());
        this._categoryButtons.clear();
    }

    // Clear the categories box
    _clear() {
        this._scrollBox.resetScroll();
        this._categoriesBox?.remove_all_children();
    }

    _selected(categoryItem, category_menu_id) {
        this.emit('selected', category_menu_id);
    }

    grab_key_focus() {
        let item = this._categoriesBox.get_first_child();
        if (item) {
            item.grab_key_focus();
        }
    }

    show() {
        this._scrollBox.resetScroll();
        super.show();
        let item = this._categoriesBox.get_first_child();
        if (item) {
            item.grab_key_focus();
        }
    }

    _onDestroy() {
        this._appsBackend?.disconnectObject(this);
        this._appsBackend = null;

        this._categoryButtons.clear();
        this._categoryButtons = null;

        this._categoriesBox?.destroy();
        this._categoriesBox = null;

        this._scrollBox?.destroy();
        this._scrollBox = null;
    }
});

export const CategoriesHoverSection = GObject.registerClass({
}, class CategoriesHoverSection extends CategoriesListSection {
    _init(appsBackend) {
        super._init(appsBackend);
        this._leaveEventTimeoutId = null;
        this._initialMotionEventItem = null;
    }

    _load() {
        this._addCategoryButton(this._appsBackend.allAppsCategory());
        super._load();
        this._activeCategory = this._categoriesBox.get_first_child();
        this._activeCategory?.add_style_pseudo_class('active');
    }

    _reset() {
        this._clearLeaveEventTimeout();
        this._activeCategory?.remove_style_pseudo_class('active');
        this._activeCategory = null;
        this._initialMotionEventItem = null;
        delete this._prevX;
        delete this._prevY;
    }

    _clear() {
        this._reset();
        super._clear();
    }

    _addCategoryButton(category) {
        let button = this._categoryButtons.get(category);
        if (!button) {
            button = new MiscMenuItems.CategoryHoverMenuItem(category);
            this._categoryButtons.set(category, button);
            button.connectObject('selected', this._selected.bind(this), this);
            button.connectObject('motion-event', this._onMotionEvent.bind(this), this);
            button.connectObject('enter-event', this._onEnterEvent.bind(this), this);
            button.connectObject('leave-event', this._onLeaveEvent.bind(this), this);
        }
        if (!button.get_parent()) {
            this._categoriesBox.add_child(button);
        }
    }

    _clearLeaveEventTimeout() {
        if (this._leaveEventTimeoutId) {
            GLib.source_remove(this._leaveEventTimeoutId);
            this._leaveEventTimeoutId = null;
        }
    }

    _onEnterEvent() {
        this._clearLeaveEventTimeout();
    }

    _onLeaveEvent() {
        if (!this._leaveEventTimeoutId) {
            this._leaveEventTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
                this._initialMotionEventItem = null;
                this._leaveEventTimeoutId = null;
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _onMotionEvent(categoryItem, event) {
        if (!this._initialMotionEventItem)
            this._initialMotionEventItem = categoryItem;

        const inActivationZone = this._inActivationZone(categoryItem, event.get_coords());
        if (inActivationZone) {
            categoryItem.activate(Clutter.get_current_event());
            this._initialMotionEventItem = categoryItem;
        }
    }

    _inActivationZone(categoryItem, [x, y]) {
        // no need to activate the category if its already active
        if (this._activeCategory && (this._activeCategory === categoryItem)) {
            this._prevX = x;
            this._prevY = y;
            return false;
        }

        if (!this._initialMotionEventItem)
            return false;

        const [posX, posY] = this._initialMotionEventItem.get_transformed_position();

        // the mouse is on the initialMotionEventItem
        const onInitialMotionEventItem = this._initialMotionEventItem === categoryItem;
        if (onInitialMotionEventItem) {
            this._prevX = x;
            this._prevY = y;
            return true;
        }

        // _prevX/_prevY may not have been set yet on the first motion event.
        // Initialize them and return false (don't switch categories) so the
        // triangle logic has a valid previous position to work with on the
        // next motion event.
        if (this._prevX === undefined || this._prevY === undefined) {
            this._prevX = x;
            this._prevY = y;
            return false;
        }

        const {width} = this._initialMotionEventItem;
        const {height} = this._initialMotionEventItem;

        const maxX = posX + width;
        const maxY = posY + height;

        // In LTR, the apps list is to the right of the categories (use maxX).
        // In RTL, the apps list is to the left of the categories (use posX).
        const isRtl = this.get_text_direction() === Clutter.TextDirection.RTL;
        const edgeX = isRtl ? posX : maxX;

        const distance = Math.abs(edgeX - this._prevX);
        const point1 = [this._prevX, this._prevY];
        const point2 = [edgeX, posY - distance];
        const point3 = [edgeX, maxY + distance];

        const area = Utils.areaOfTriangle(point1, point2, point3);
        const a1 = Utils.areaOfTriangle([x, y], point2, point3);
        const a2 = Utils.areaOfTriangle(point1, [x, y], point3);
        const a3 = Utils.areaOfTriangle(point1, point2, [x, y]);
        const outsideTriangle = Math.abs(area - (a1 + a2 + a3)) > 0.5;

        return outsideTriangle;
    }

    _selected(categoryItem, category_menu_id) {
        if (this._activeCategory && (this._activeCategory === categoryItem)) {
            return;
        }
        this._activeCategory?.remove_style_pseudo_class('active');
        categoryItem.add_style_pseudo_class('active');
        this._activeCategory = categoryItem;
        this._activeCategory.grab_key_focus();
        super._selected(categoryItem, category_menu_id);
    }

    grab_key_focus() {
        if (this._activeCategory) {
            this._activeCategory.grab_key_focus();
            return;
        }
        super.grab_key_focus();
    }

    show() {
        this._reset();
        super.show();
        this._activeCategory = this._categoriesBox.get_first_child();
        this._activeCategory?.add_style_pseudo_class('active');
    }

    hide() {
        super.hide();
        this._reset();
    }

    _onDestroy() {
        this._reset();
        super._onDestroy();
    }
});

export const AppsListSection = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class AppsListSection extends St.Bin {
    _init(appsBackend, isGrid, monitorIndex) {
        super._init({ x_expand: true, y_expand: true, style_class: 'apps-list', accessible_name: _('Applications')});
        this._appsBackend = appsBackend;
        this._appButtons = new Map();
        this._category = null;
        this._searchTerms = [];
        this.searchResults = new Search.SearchResults(isGrid, monitorIndex);
        this.searchResults.connectObject('activated', this._activated.bind(this), this);
        this._appsBox = new St.BoxLayout({...getOrientationProp(true)});

        if (isGrid) {
            this.grid = new Widgets.Grid(Constants.COLUMN_COUNT, Constants.COLUMN_SPACING, Constants.ROW_SPACING);
            this._appsBox.add_child(this.grid);
        }
        this._scrollBox = new Widgets.ScrollView({
                x_expand: true,
                y_expand: true,
                x_align: Clutter.ActorAlign.FILL,
                y_align: Clutter.ActorAlign.FILL,
                style_class: 'apps-menu vfade',
                reactive:true
        });
        this._scrollBox.set_child(this._appsBox);
        this.set_child(this._scrollBox);
        this._load();
        this._appsBackend.connectObject('reload', this._reload.bind(this), this);
        this.connect('destroy', this._onDestroy.bind(this));
    }

    _display(apps, alphabetize) {
        this._scrollBox.resetScroll();

        if (this.grid) {
            if (!this._appsBox.contains(this.grid)) {
                this._appsBox.add_child(this.grid);
            }
            this.grid.show();
        }

        if (apps) {
            let currentCharacter;

            for (let i = 0; i < apps.length; i++) {
                const app = apps[i];

                if (!this.grid && alphabetize) {
                    const appNameFirstChar = app.get_name().charAt(0).toUpperCase();
                    if (currentCharacter !== appNameFirstChar) {
                        currentCharacter = appNameFirstChar;

                        const label = new PopupMenu.PopupSeparatorMenuItem(currentCharacter);
                        this._appsBox.add_child(label);
                    }
                }
                this._addAppButton(app);
            }
        }
    }

    _load() {
        if (this._searchTerms.length > 0) {
            this.searchResults.setTerms(this._searchTerms);
            this.searchActive();
        } else {
            this._displayCategory();
        }
    }

    _reload() {
        this._searchTerms = this.searchResults.terms;
        this._clear();
        this._clearAppButtons();
        this._load();
        this._searchTerms = [];
    }

    // Emit signal if one of the buttons is activated
    _activated() {
        this.emit('activated');
    }

    _clearAppButtons() {
        this._appButtons.forEach(button => button.destroy());
        this._appButtons.clear();
    }

    _addAppButton(app) {
        let button = this._appButtons.get(app);
        if (!button) {
            button = new AppMenuItem.AppMenuItem(app, (this.grid != null));
            this._appButtons.set(app, button);
            button.connectObject('activated', this._activated.bind(this), this);
        }
        if (!button.get_parent()) {
            if (this.grid) {
                this.grid.add_item(button);
            } else {
                this._appsBox.add_child(button);
            }
        }
    }

    // Clear the apps box
    _clear() {
        Utils.blockHover();
        if (this.grid) {
            this.grid.clear();
        }
        this.searchResults.setTerms([]);
        this._appsBox.remove_all_children();
        this._scrollBox.resetScroll();
    }

    selectCategory(category_menu_id) {
        if (this._category === category_menu_id || (!category_menu_id && this._category == "all_apps")) {
            return; // Do nothing if category is unchanged
        }
        this._category = category_menu_id;
        this._displayCategory();
    }

    _displayCategory() {
        const category_menu_id = this._category;
        if (category_menu_id === "all_apps") {
            this.displayAllApps();
        } else if (category_menu_id) {
            let apps = this._appsBackend.getAppsByCategory(category_menu_id);
            this._clear();
            this._display(apps, false);
        } else {
            this.displayAllApps();
        }
    }

    searchActive() {
        this._category = null;
        this._scrollBox.resetScroll();
        if (!this._appsBox.contains(this.searchResults)) {
            const terms = this.searchResults.terms;
            this._clear();
            this.searchResults.setTerms(terms);
            this._appsBox.add_child(this.searchResults);
        }
    }

    displayAllApps() {
        this._category = "all_apps";
        let apps = this._appsBackend.getAllApps();
        this._clear();
        this._display(apps, true);
    }

    grab_key_focus() {
        let item = this._appsBox.get_first_child();
        while (item && item instanceof PopupMenu.PopupSeparatorMenuItem) {
            item = item.get_next_sibling()
        }
        if (item) {
            item.grab_key_focus();
        }
    }

    show() {
        super.show();
        this.grab_key_focus();
    }

    _onDestroy() {
        this._appsBackend?.disconnectObject(this);
        this._appsBackend = null;

        this._appButtons.clear();
        this._appButtons = null;

        this._category = null;

        this.searchResults?.destroy();
        this.searchResults = null;
        this._searchTerms = null;

        this.grid?.destroy();
        this.grid = null;

        this._appsBox?.destroy();
        this._appsBox = null;

        this._scrollBox?.destroy();
        this._scrollBox = null;
    }
});

export const SidebarSection = GObject.registerClass({
    Signals: {
        'activated': {},
    }
}, class SidebarSection extends St.BoxLayout {
    _init() {
        super._init({
            ...getOrientationProp(true),
            style_class: 'shortcuts-box',
            accessible_name: _('Shortcuts')
        });
        
        // Create Sections and Widgets
        this._userItem = new UserWidgets.UserMenuItem();
        this._placesSection = new PlacesSection();
        this._shortcutsSection = new ShortcutsSection();
        this._sessionButtonsSection = new SessionButtonsSection();

        // Fill Box
        this.add_child(this._userItem);
        this._userSeparator = new PopupMenu.PopupSeparatorMenuItem();
        this.add_child(this._userSeparator);
        this.add_child(this._placesSection);
        this._shortcutSectionSeparator = new PopupMenu.PopupSeparatorMenuItem();
        this.add_child(this._shortcutSectionSeparator);
        this.add_child(this._shortcutsSection);
        let separator = new PopupMenu.PopupSeparatorMenuItem();
        this.add_child(separator);
        this.add_child(this._sessionButtonsSection);

        // Connect Signals
        this._userItem.connectObject('activated', this._activated.bind(this), this);
        this._placesSection.connectObject('activated', this._activated.bind(this), this);
        this._shortcutsSection.connectObject('activated', this._activated.bind(this), this);
        this._sessionButtonsSection.connectObject('activated', this._activated.bind(this), this);
        this.connect('destroy', () => this._onDestroy());
    }

    // Emit signal if one of the buttons is activated
    _activated() {
        this.emit('activated');
    }
    
    updateHeight(availableHeight) {
        // Ensure shortcuts section and user item are visible for correct height calculation
        this._shortcutSectionSeparator.show();
        this._shortcutsSection.show();
        this._userItem.show();
        this._userSeparator.show();

        let [, naturalHeight] = this.get_preferred_height(-1);
        if (naturalHeight > availableHeight) {
            // Hide shortcuts section to make sidebar more compact and recalculate height
            this._shortcutSectionSeparator.hide();
            this._shortcutsSection.hide();
            [, naturalHeight] = this.get_preferred_height(-1);
            if (naturalHeight > availableHeight) {
                // Hide user item to make sidebar super compact and recalculate height
                this._userItem.hide();
                this._userSeparator.hide();
                [, naturalHeight] = this.get_preferred_height(-1);
            }
        }
        const newHeight = (naturalHeight > availableHeight) ? availableHeight : naturalHeight;
        return newHeight;
    }

    _onDestroy() {
        this._userItem?.destroy();
        this._userItem = null;

        this._userSeparator?.destroy();
        this._userSeparator = null;

        this._placesSection?.destroy();
        this._placesSection = null;

        this._shortcutsSection?.destroy();
        this._shortcutsSection = null;

        this._shortcutSectionSeparator?.destroy();
        this._shortcutSectionSeparator = null;

        this._sessionButtonsSection?.destroy();
        this._sessionButtonsSection = null;
    }
});
