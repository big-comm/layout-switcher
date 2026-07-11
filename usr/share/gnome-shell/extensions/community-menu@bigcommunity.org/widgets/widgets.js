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
 *
 * Credits:
 * This file contains code from the Applications Menu extension by easy2002
 * and Debarshi Ray, the Drive Menu extension by Giovanni Campagna, and
 * userWidget.js from Gnome Shell
 */

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Utils from '../utils.js';

export const VerticalSeparator = class {
    constructor() {
        this.actor = new St.Widget({ style_class: 'popup-separator-menu-item vertical-separator',
                                     x_expand: true,
                                     y_expand: true,
                                     x_align: Clutter.ActorAlign.CENTER,
                                     y_align: Clutter.ActorAlign.FILL });
    }

    destroy() {
        this.actor?.destroy();
        this.actor = null;
    }
};

export const Grid = GObject.registerClass({
}, class Grid extends St.Widget {
    _init(column_count, column_spacing, row_spacing) {
        this._column_count = column_count;
        let layout = new Clutter.GridLayout({ 
            orientation: Clutter.Orientation.VERTICAL,
            column_spacing: column_spacing,
            row_spacing: row_spacing
        });
        super._init({ 
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            layout_manager: layout,
            style_class: 'apps-grid'
        });
        layout.hookup_style(this);
    }

    add_item(item) {
        let position = this.get_n_children();
        let row = Math.trunc(position / this._column_count);
        let col = position % this._column_count;
        if (this.get_text_direction() == Clutter.TextDirection.RTL) {
            col = (this._column_count - 1) - col;
        }
        this.layout_manager.attach(item, col, row, 1, 1);
    }

    get_first_item() {
        let col = 0;
        if (this.get_text_direction() == Clutter.TextDirection.RTL) {
            col = this._column_count - 1;
        }
        let item = this.layout_manager.get_child_at(col, 0);
        if (item) {
            return item;
        } else {
            return null;
        }
    }

    grab_key_focus() {
        let item = this.get_first_item();
        if (item) {
            item.grab_key_focus();
        }
    }

    clear() {
         this.remove_all_children();
    }
});

export const ScrollView = GObject.registerClass({
}, class ScrollView extends St.ScrollView {
    _init(params){
        super._init({
            ...params,
            clip_to_allocation: true,
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            overlay_scrollbars: true,
        });

        this.get_children().forEach(child => {
            if (child instanceof St.ScrollBar)
                child.z_position = 1;
        });

        this._panGesture = Utils.addPanGesture(this, (action) => {
            this.onPan(action);
        });
    }

    onPan(action) {
        Utils.blockHover();
        const dy = action.get_delta().get_y();
        this.vadjustment.value -= dy;
        return false;
    }

    resetScroll() {
        this.vadjustment.set_value(0);
    }
});
