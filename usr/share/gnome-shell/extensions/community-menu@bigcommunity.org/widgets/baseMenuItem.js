// Modified by Community Big, 2026-07-10: renamed, de-Zorinized, and adapted for GNOME Shell 50.
import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import Graphene from 'gi://Graphene';
import St from 'gi://St';

import * as Config from 'resource:///org/gnome/shell/misc/config.js';
import * as Params from 'resource:///org/gnome/shell/misc/params.js';

import {ScrollView} from './widgets.js';
import * as Tooltip from './tooltip.js';
import * as Utils from '../utils.js';

const [ShellVersion] = Config.PACKAGE_VERSION.split('.').map(s => Number(s));

export const BaseMenuItem = GObject.registerClass({
    Properties: {
        'active': GObject.ParamSpec.boolean(
            'active', null, null,
            GObject.ParamFlags.READWRITE,
            false),
        'sensitive': GObject.ParamSpec.boolean(
            'sensitive', null, null,
            GObject.ParamFlags.READWRITE,
            true),
    },
    Signals: {
        'activate': {param_types: [Clutter.Event.$gtype]},
    },
}, class BaseMenuItem extends St.BoxLayout {
    _init(params) {
        params = Params.parse(params, {
            reactive: true,
            activate: true,
            hover: true,
            style_class: null,
            can_focus: true,
        });
        super._init({
            style_class: 'popup-menu-item',
            x_align: Clutter.ActorAlign.FILL,
            x_expand: true,
            y_expand: false,
            reactive: params.reactive,
            track_hover: params.reactive,
            can_focus: params.can_focus,
            pivot_point: new Graphene.Point({x: 0.5, y: 0.5}),
            accessible_role: Atk.Role.MENU_ITEM,
        });
        this._delegate = this;
        this.hasContextMenu = false;
        this.useTooltip = false;
        this._keepActive = false;

        this._parent = null;
        this._active = false;
        this._activatable = params.reactive && params.activate;
        this._sensitive = true;

        this._panAction = Utils.addPanGesture(this, this._onPan.bind(this));
        const gestures = Utils.addClickGestures(this, {
            onClick: this._onClicked.bind(this),
            onPressed: this._onPressed.bind(this),
            onLongPress: this._onLongPress.bind(this),
            onRightClick: this._onRightClick.bind(this),
        }, this._activatable);
        this._clickAction = gestures.clickGesture;
        this._longPressAction = gestures.longPressGesture;
        this._rightClickAction = gestures.rightClickGesture;
        if (!this._activatable)
            this.add_style_class_name('popup-inactive-menu-item');

        if (params.style_class)
            this.add_style_class_name(params.style_class);

        if (params.hover)
            this.connectObject('notify::hover', this._onHover.bind(this), this);
        if (params.reactive && params.hover)
            this.bind_property('hover', this, 'active', GObject.BindingFlags.SYNC_CREATE);

        this.connect('destroy', () => this._onDestroy());
    }

    _onHover() {
        if (!this.useTooltip) {
            return;
        }

        if(this.tooltip==undefined && this.hover && (this.label_actor || this.description)){
            this._createTooltip();
            this.tooltip?._onHover();
        }
    }

    _createTooltip(){
        let description = this.description;
        let isEllipsized = false;

        if (this.label_actor) {
            let lbl = this.label_actor.clutter_text;
            lbl.get_allocation_box();
            isEllipsized = lbl.get_layout().is_ellipsized();
        }

        if(isEllipsized || description){
            let titleText, descriptionText;
            if(isEllipsized && description){
                titleText = this.label_actor.text.replace(/\n/g, " ");
                descriptionText = description;
            }
            else if(isEllipsized && !description)
                titleText = this.label_actor.text.replace(/\n/g, " ");
            else if(!isEllipsized && description)
                descriptionText = description;
            this.tooltip = new Tooltip.Tooltip(this, titleText, descriptionText);
        }
    }

    _onPan(action) {
        let parent = this.get_parent();
        while (!(parent instanceof ScrollView)) {
            if (!parent)
                return false;
            parent = parent.get_parent();
        }
        let scrollview = parent;
        Utils.blockHover();

        return scrollview.onPan(action);
    }

    _onPressed() {
        if (this._clickAction.pressed) {
            Utils.blockHover(false);
            this.hover = true;
            this.add_style_pseudo_class('active');
        } else
            this.remove_style_pseudo_class('active');
    }

    _onClicked(action) {
        const isPrimaryOrTouch = action.get_button() === Clutter.BUTTON_PRIMARY || action.get_button() === 0;
        const isMiddleButton = action.get_button() === Clutter.BUTTON_MIDDLE || action.get_button() === 2;
        if (isPrimaryOrTouch || isMiddleButton) {
            this.active = false;
            this.remove_style_pseudo_class('active');
            this.activate(Clutter.get_current_event());
        } else if (action.get_button() === Clutter.BUTTON_SECONDARY) {
            if (this.hasContextMenu)
                this.emit('popup-menu');
            else
                this.remove_style_pseudo_class('active');
        } else if (action.get_button() === 8) {
            // TODO?: handle mouse back button
        }
    }    

    _onLongPress() {
        if (this.hasContextMenu) {
            Utils.blockHover(false);
            this.sync_hover();
            this.emit('popup-menu');
        }
    }

    _onRightClick() {
        if (this.hasContextMenu)
            this.emit('popup-menu');
    }

    get actor() {
        return this;
    }

    _setParent(parent) {
        this._parent = parent;
    }

    _setSelectedStyle() {
        if (ShellVersion >= 47)
            this.add_style_pseudo_class('selected');
        else
            this.add_style_class_name('selected');
    }

    _removeSelectedStyle() {
        if (ShellVersion >= 47)
            this.remove_style_pseudo_class('selected');
        else
            this.remove_style_class_name('selected');
    }

    set_hover(hover) {
        if (hover && Utils.isBlockHover())
            return;

        super.set_hover(hover);
    }

    vfunc_key_press_event(event) {
        Utils.blockHover();
        if (global.focus_manager.navigate_from_event(event))
            return Clutter.EVENT_STOP;

        if (!this._activatable)
            return super.vfunc_key_press_event(event);

        let state = event.get_state();

        // if user has a modifier down (except shift, capslock and numlock)
        // then don't handle the key press here
        state &= ~Clutter.ModifierType.SHIFT_MASK
        state &= ~Clutter.ModifierType.LOCK_MASK;
        state &= ~Clutter.ModifierType.MOD2_MASK;
        state &= Clutter.ModifierType.MODIFIER_MASK;

        if (state)
            return Clutter.EVENT_PROPAGATE;

        state = event.get_state(); // reset state variable
        let symbol = event.get_key_symbol();

        // Handle context menu
        if (this.hasContextMenu && (symbol === Clutter.KEY_Menu || (symbol === Clutter.KEY_F10 && (state & Clutter.ModifierType.SHIFT_MASK)))) {
            this.emit('popup-menu');
            return Clutter.EVENT_STOP;
        }

        // If shift modifier is down and context menu shortcut was not activated handle keypress elsewhere
        if (state & Clutter.ModifierType.SHIFT_MASK) {
            return Clutter.EVENT_PROPAGATE;
        }

        // Handle menu item activation
        if (symbol === Clutter.KEY_Return || symbol === Clutter.KEY_KP_Enter) {
            this.activate(Clutter.get_current_event());
            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    vfunc_motion_event() {
        // Prevent a mouse hover event from setting a new active menu item, until next mouse move event.
        if (Utils.isBlockHover()) {
            Utils.blockHover(false);
            this.hover = true;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    vfunc_key_focus_in() {
        super.vfunc_key_focus_in();
        this.active = true;
    }

    vfunc_key_focus_out() {
        super.vfunc_key_focus_out();
        this.active = false;
        this.hover = false;
    }

    activate(event) {
        this.emit('activate', event);
    }

    get active() {
        return this._active;
    }

    set active(active) {
        if (this.isDestroyed || !this.mapped)
            return;

        if (this.hover && Utils.isBlockHover()) {
            this.hover = false;
            return;
        }

        let activeChanged = active !== this.active;
        if (activeChanged) {
            this._active = active;
            if (active) {
                let scrollview = Utils.getScrollViewParent(this);
                if (scrollview && (scrollview.lastActiveMenuItem === undefined || scrollview.lastActiveMenuItem !== this)) {
                    scrollview.lastActiveMenuItem = this;
                    if (!this.hover)
                        Utils.ensureActorVisibleInScrollView(this);
                }

                this._setSelectedStyle();
                if (this.can_focus)
                    this.grab_key_focus();
            } else {
                this._removeSelectedStyle();
                if (!this._keepActive) {
                    this.remove_style_pseudo_class('active');
                }
            }
            this.notify('active');
        }
    }

    syncSensitive() {
        let sensitive = this.sensitive;
        this.reactive = sensitive;
        this.can_focus = sensitive;
        this.notify('sensitive');
        return sensitive;
    }

    getSensitive() {
        const parentSensitive = this._parent?.sensitive ?? true;
        return this._activatable && this._sensitive && parentSensitive;
    }

    setSensitive(sensitive) {
        if (this._sensitive === sensitive)
            return;

        this._sensitive = sensitive;
        this.syncSensitive();
    }

    get sensitive() {
        return this.getSensitive();
    }

    set sensitive(sensitive) {
        this.setSensitive(sensitive);
    }

    _onDestroy() {
        this.isDestroyed = true;

        this.tooltip?.destroy();
        this.tooltip = null;

        this._panAction = null;
        this._clickAction = null;
        this._longPressAction = null;
        this._rightClickAction = null;

        this._parent = null;
    }
});
