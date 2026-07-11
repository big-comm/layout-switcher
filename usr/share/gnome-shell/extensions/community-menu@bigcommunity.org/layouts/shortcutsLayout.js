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

import * as BaseLayout from './baseLayout.js'
import * as Sections from '../sections.js';

export const ShortcutsLayout = GObject.registerClass({
}, class ShortcutsLayout extends BaseLayout.BaseLayout {
    // Initialize the layout
    _init(appsBackend, panelInfo) {
        super._init(appsBackend, panelInfo);
        this.add_style_class_name("shortcuts-only-layout-box");
    }

    _loadLayout() {
        this._sidebar = new Sections.SidebarSection();
        this.add_child(this._sidebar);
    }

    _connectSignals() {
        this._sidebar.connectObject('activated', this._activated.bind(this), this);
    }

    updateHeight() {
        const availableHeight = this._availableHeight();
        const newHeight = this._sidebar.updateHeight(availableHeight);
        this.set_height(newHeight);
    }

    _onDestroy() {      
        this._sidebar?.destroy();
        this._sidebar = null;

        super._onDestroy();
    }
});
