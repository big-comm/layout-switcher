// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as Dash from 'resource:///org/gnome/shell/ui/dash.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import * as Constants from '../constants.js';
import * as Utils from '../utils.js';
import {getOrientationProp} from '../utils.js';

export const Tooltip = class {
    constructor(sourceActor, title, description) {
        this.sourceActor = sourceActor;
        this.location = Constants.TooltipLocation.BOTTOM;
        this.label = new St.Label({ 
            style_class: 'dash-label community-menu-tooltip',
            opacity: 0
        });
        this.label.clutterText.set({
            line_wrap: true,
            line_wrap_mode: Pango.WrapMode.WORD_CHAR,
        });
        this.actor = this.label;

        if (title && description) {
            const escapedTitle = GLib.markup_escape_text(title, -1);
            const escapedDescription = GLib.markup_escape_text(description, -1);
            const text = `<b>${escapedTitle}</b>\n${escapedDescription}`;
            this.label.clutter_text.set_markup(text);
        } else if (title && !description) {
            this.label.text = title;
        } else if (!title && description) {
            this.label.text = description;
        }

        global.stage.add_child(this.actor);

        this.sourceActor.connectObject(
            'notify::active', () => this.setActive(this.sourceActor.active),
            'notify::hover', this._onHover.bind(this),
            this.actor);
    }

    setActive(active){
        if(!active)
            this.hide();
    }

    _onHover() {
        if(!Utils.isBlockHover() && this.sourceActor.hover){
            if (this.tooltipShowingID)
                return;
            this.tooltipShowingID = GLib.timeout_add(0, Constants.TOOLTIP_TIMEOUT, () => {
                this.show();
                this.tooltipShowingID = null;
                return GLib.SOURCE_REMOVE;
            });
        } else if (!this.sourceActor.hover || Utils.isBlockHover()) {
            this.hide();
        }
    }

    show() {
        this.actor.opacity = 0;
        this.actor.show();

        let [stageX, stageY] = this.sourceActor.get_transformed_position();

        let itemWidth  = this.sourceActor.allocation.x2 - this.sourceActor.allocation.x1;
        let itemHeight = this.sourceActor.allocation.y2 - this.sourceActor.allocation.y1;

        let labelWidth = this.actor.get_width();
        let labelHeight = this.actor.get_height();

        let x, y;
        let gap = 5;

        switch (this.location) {
            case Constants.TooltipLocation.BOTTOM_CENTERED:
                y = stageY + itemHeight + gap;
                x = stageX + Math.floor((itemWidth - labelWidth) / 2);
                break;
            case Constants.TooltipLocation.TOP_CENTERED:
                y = stageY - labelHeight - gap;
                x = stageX + Math.floor((itemWidth - labelWidth) / 2);
                break;
            case Constants.TooltipLocation.BOTTOM:
                y = stageY + itemHeight;
                x = stageX + gap * 2;
                break;
        }

        // keep the label inside the screen          
        let monitor = Main.layoutManager.findMonitorForActor(this.sourceActor);
        if (x - monitor.x < gap)
            x += monitor.x - x + gap;
        else if (x + labelWidth > monitor.x + monitor.width - gap)
            x -= x + labelWidth - (monitor.x + monitor.width) + gap;
        else if (y - monitor.y < gap)
            y += monitor.y - y + gap;
        else if (y + labelHeight > monitor.y + monitor.height - gap)
            y -= y + labelHeight - (monitor.y + monitor.height) + gap;

        this.actor.set_position(x, y);
        this.actor.ease({
            opacity: 255,
            duration: Dash.DASH_ITEM_LABEL_SHOW_TIME,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });
    }

    hide() {
        if(this.tooltipShowingID){
            GLib.source_remove(this.tooltipShowingID);
            this.tooltipShowingID = null;
        }
        this.actor.ease({
            opacity: 0,
            duration: Dash.DASH_ITEM_LABEL_HIDE_TIME,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => this.actor.hide()
        });
    }

    destroy() {
        if (this.tooltipShowingID) {
            GLib.source_remove(this.tooltipShowingID);
            this.tooltipShowingID = null;
        }

        if (this.actor) {
            this.sourceActor?.disconnectObject(this.actor);
            global.stage.remove_child(this.actor);
            this.actor.destroy();
        }
        this.actor = null;
        this.label = null;
    }
};
