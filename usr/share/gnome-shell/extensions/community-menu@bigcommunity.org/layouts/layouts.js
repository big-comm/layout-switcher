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

import * as AppGridLayout from './appGridLayout.js'
import * as AppListLayout from './appListLayout.js'
import * as Constants from '../constants.js';
import * as MintLayout from './mintLayout.js'
import * as ShortcutsLayout from './shortcutsLayout.js'
import * as StandardLayout from './standardLayout.js'

export function getLayout(layoutSetting, appsBackend, panelInfo) {
    switch(layoutSetting) {
        case Constants.LAYOUTS.ALL:
            return new StandardLayout.StandardLayout(appsBackend, panelInfo);
        case Constants.LAYOUTS.APPS_ONLY:
            return new AppListLayout.AppListLayout(appsBackend, panelInfo);
        case Constants.LAYOUTS.SYSTEM_ONLY:
            return new ShortcutsLayout.ShortcutsLayout(appsBackend, panelInfo);
        case Constants.LAYOUTS.APP_GRID:
            return new AppGridLayout.AppGridLayout(appsBackend, panelInfo);
        case Constants.LAYOUTS.MINT:
            return new MintLayout.MintLayout(appsBackend, panelInfo);
        default:
            return new StandardLayout.StandardLayout(appsBackend, panelInfo);
    }
}
