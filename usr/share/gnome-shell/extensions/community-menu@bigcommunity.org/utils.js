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
 * and Debarshi Ray
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Config from 'resource:///org/gnome/shell/misc/config.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as Constants from './constants.js';

const [ShellVersion] = Config.PACKAGE_VERSION.split('.').map(s => Number(s));

Gio._promisify(Gio._LocalFilePrototype, 'query_info_async', 'query_info_finish');
Gio._promisify(Gio._LocalFilePrototype, 'set_attributes_async', 'set_attributes_finish');

async function _markTrusted(file) {
    let modeAttr = Gio.FILE_ATTRIBUTE_UNIX_MODE;
    let queryFlags = Gio.FileQueryInfoFlags.NONE;
    let ioPriority = GLib.PRIORITY_DEFAULT;
    let S_IXUSR = 0o00100;

    try {
        let info = await file.query_info_async(modeAttr, queryFlags, ioPriority, null);
        let mode = info.get_attribute_uint32(modeAttr) | S_IXUSR;
        info.set_attribute_uint32(modeAttr, mode);
        info.set_attribute_string('metadata::trusted', 'true');
        await file.set_attributes_async(info, queryFlags, ioPriority, null);

        // Hack: force nautilus to reload file info
        info = new Gio.FileInfo();
        info.set_attribute_uint64(
            Gio.FILE_ATTRIBUTE_TIME_ACCESS, GLib.get_real_time());
        try {
            await file.set_attributes_async(info, queryFlags, ioPriority, null);
        } catch (e) {
            log(`Failed to update access time: ${e.message}`);
        }
    } catch (e) {
        log(`Failed to mark file as trusted: ${e.message}`);
    }
};

export function addToDesktop(appInfo) {
    if (!appInfo)
        return;

    let desktop = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP);
    let src = Gio.File.new_for_path(appInfo.get_filename());
    let dst = Gio.File.new_for_path(GLib.build_filenamev([desktop, src.get_basename()]));

    try {
        src.copy(dst, Gio.FileCopyFlags.OVERWRITE, null, null);
        _markTrusted(dst).catch(logError);
    } catch (e) {
        log(`Failed to copy to desktop: ${e.message}`);
    }
};

/**
 * Check if an app exists in the system.
 */
let checkedCommandsMap = new Map();

export function clearCommandsCache() {
    checkedCommandsMap.clear();
}

export function checkIfCommandExists(app) {
    let answer = checkedCommandsMap.get(app);
    if (answer === undefined) {
        answer = GLib.find_program_in_path(app) !== null;
        checkedCommandsMap.set(app, answer);
    }
    return answer;
}

export function getScrollViewParent(actor) {
    let parent = actor.get_parent();
    while (!(parent instanceof St.ScrollView)) {
        if (!parent)
            return null;

        parent = parent.get_parent();
    }
    return parent;
}

// modified from GNOME shell's ensureActorVisibleInScrollView()
export function ensureActorVisibleInScrollView(actor, axis = Clutter.Orientation.VERTICAL) {
    let box = actor.get_allocation_box();
    let {y1} = box, {y2} = box;
    let {x1} = box, {x2} = box;

    let parent = actor.get_parent();
    while (!(parent instanceof St.ScrollView)) {
        if (!parent)
            return;

        box = parent.get_allocation_box();
        y1 += box.y1;
        y2 += box.y1;
        x1 += box.x1;
        x2 += box.x1;
        parent = parent.get_parent();
    }

    let adjustment, startPoint, endPoint;

    if (axis === Clutter.Orientation.VERTICAL) {
        adjustment = parent.vadjustment;
        startPoint = y1;
        endPoint = y2;
    } else {
        adjustment = parent.hadjustment;
        startPoint = x1;
        endPoint = x2;
    }

    let [value, lower_, upper, stepIncrement_, pageIncrement_, pageSize] = adjustment.get_values();

    let offset = 0;
    const fade = parent.get_effect('fade');
    if (fade)
        offset = axis === Clutter.Orientation.VERTICAL ? fade.fade_margins.top : fade.fade_margins.left;

    if (startPoint < value + offset)
        value = Math.max(0, startPoint - offset);
    else if (endPoint > value + pageSize - offset)
        value = Math.min(upper, endPoint + offset - pageSize);
    else
        return;

    blockHover();

    adjustment.ease(value, {
        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        duration: Constants.SCROLL_ANIMATION_DURATION,
    });
}

let _blockHover = false;

export function isBlockHover() {
    return _blockHover;
}

export function blockHover(block = true) {
    _blockHover = block;
}

/**
 * GNOME 46 renamed the extension states. Use this const instead.
 */
export const ExtensionState = {
    ACTIVE: 1,
    INACTIVE: 2,
};

export function isExtensionEnabled(extension) {
    return (extension?.state === ExtensionState.ACTIVE);
}

export function isExtensionDisabled(extension) {
    return (extension?.state === ExtensionState.INACTIVE);
}

export function isPanelExtension(uuid) {
    if (!uuid)
        return false;

    return uuid === Constants.DASH_TO_PANEL_UUID;
}

/**
 *
 * @param {boolean} vertical
 * @description GNOME 48 - St.BoxLayout uses 'orientation' instead of 'vertical'
 */
export function getOrientationProp(vertical) {
    if (ShellVersion >= 48)
        return {orientation: vertical ? Clutter.Orientation.VERTICAL : Clutter.Orientation.HORIZONTAL};
    else
        return {vertical};
}

/**
 * Attach a GNOME 49+ pan gesture to an actor.
 * Clutter.PanAction was removed before GNOME 50.
 */
export function addPanGesture(actor, callback) {
    const gesture = new Clutter.PanGesture();
    gesture.connect('pan-update', callback);
    actor.add_action(gesture);
    return gesture;
}

/**
 * Attach GNOME 49+ click gestures to an actor.
 * Clutter.ClickAction and its long-press signal no longer exist in GNOME 50.
 */
export function addClickGestures(actor, callbacks, enabled = true) {
    const clickGesture = new Clutter.ClickGesture({enabled});
    clickGesture.connect('recognize', callbacks.onClick);
    if (callbacks.onPressed)
        clickGesture.connect('notify::pressed', callbacks.onPressed);
    actor.add_action(clickGesture);

    const longPressGesture = new Clutter.LongPressGesture();
    if (callbacks.onLongPress)
        longPressGesture.connect('recognize', callbacks.onLongPress);
    actor.add_action(longPressGesture);

    const rightClickGesture = new Clutter.ClickGesture({
        required_button: Clutter.BUTTON_SECONDARY,
        recognize_on_press: true,
    });
    if (callbacks.onRightClick)
        rightClickGesture.connect('recognize', callbacks.onRightClick);
    actor.add_action(rightClickGesture);

    return {clickGesture, longPressGesture, rightClickGesture};
}

export function openPrefs(uuid) {
    const extension = Extension.lookupByUUID(uuid);
    if (extension !== null)
        extension.openPreferences();
}

export function areaOfTriangle(p1, p2, p3) {
    return Math.abs((p1[0] * (p2[1] - p3[1]) + p2[0] * (p3[1] - p1[1]) + p3[0] * (p1[1] - p2[1])) / 2.0);
}
