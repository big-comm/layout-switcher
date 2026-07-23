// SPDX-License-Identifier: MIT
//
// Layout Switcher Helper — in-shell orchestration for live layout switches.
//
// WHY THIS EXISTS
// ---------------
// GNOME Shell extensions (dash-to-panel, arcmenu, kiwi, light-style,
// user-theme, …) are JavaScript modules living INSIDE the gnome-shell
// process. An external process (the layout-switcher Python app) can only
// reach the shell over D-Bus, and the only lever it has to switch extensions
// is writing `org/gnome/shell/enabled-extensions` to dconf — which fires the
// Shell's gsettings listener ASYNCHRONOUSLY and concurrently with the rest of
// the apply. That cross-process race (a) hangs gnome-shell on heavy
// transitions and (b) never lets appearance-owning extensions re-apply live
// (their D-Bus ReloadExtension was deprecated in GNOME 45+).
//
// This helper runs INSIDE the Shell, driving the switch through
// `Main.extensionManager` directly, sequenced on the Shell's main loop, and
// re-applying the shell stylesheet via `Main.loadTheme()`.
//
// CLEAN-ROOM PROTOCOL (v7)
// ------------------------
// A login always renders a layout perfectly because it is an ABSOLUTE state:
// `dconf reset` + `load`, then every extension builds from scratch, in order,
// with nothing listening while the state is written. The incremental protocol
// (v6 ApplyLayout) instead performed surgery on a live desktop — partial
// toggles raced the Shell's async extension machinery (lost disables → ghost
// docks, "rebase" re-toggles with no state signals, Notify storms into live
// extensions) and every layout pair was a special case.
//
// v7 reproduces the login path inside the session, under a fullscreen
// transition curtain:
//   BeginSwitch    curtain up → disable ALL managed extensions (reverse load
//                  order, each awaited) → arm an auto-rollback timer
//   (caller)       dconf reset of layout-owned branches + full layout load —
//                  nothing is listening, so no Notify storm and no residue
//   CompleteSwitch repair colorScheme → loadTheme → enable the target set in
//                  layout order (each awaited) → panel style recompute →
//                  checkmark → curtain down
//   AbortSwitch    restore the pre-switch extension set (caller failed)
// Mass-toggling every extension is the Shell's own most-tested path — it is
// exactly what happens on every screen lock/unlock.
//
// D-BUS INTERFACE  (exported on the shell's bus name org.gnome.Shell)
//   dest:  org.gnome.Shell
//   path:  /org/bigcommunity/LayoutSwitcherHelper
//   iface: org.bigcommunity.LayoutSwitcherHelper
//   Ping()                    -> s   JSON {helper, version, busy}
//   BeginSwitch(payload: s)   -> s   see _beginSwitch for the schema
//   CompleteSwitch(payload: s)-> s   see _completeSwitch for the schema
//   AbortSwitch()             -> s   rollback to the pre-switch set
//   ApplyLayout(payload: s)   -> s   legacy v6 incremental switch
//   ReloadExtension(uuid: s)  -> s   reload one extension (re-read appearance)

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Spinner} from 'resource:///org/gnome/shell/ui/animation.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_PATH = '/org/bigcommunity/LayoutSwitcherHelper';
const HELPER_VERSION = 7;

// Shell-theme owners toggled by the live color-scheme follower.
const USER_THEME_UUID = 'user-theme@gnome-shell-extensions.gcampax.github.com';
const LIGHT_STYLE_UUID = 'light-style@gnome-shell-extensions.gcampax.github.com';
const DTP_UUID = 'dash-to-panel@jderose9.github.com';
const KIWI_UUID = 'kiwi@kemma';
const COMMUNITY_MENU_UUID = 'community-menu@bigcommunity.org';
const ARCMENU_UUID = 'arcmenu@arcmenu.com';
const ORCHIS_SHELL_DARK = 'Big-Blue';
const ORCHIS_SHELL_LIGHT = 'Big-Blue-Light';
const CLASSIC_MENU_LAYOUT = 1; // APPS_ONLY
const DESK_UX_MENU_LAYOUT = 3; // APP_GRID
const HYBRID_MENU_LAYOUT = 4; // MINT
const ARCMENU_HYBRID_LAYOUT = 'enterprise';
const COMMUNITY_LIGHT_ICON_LAYOUTS = new Set([CLASSIC_MENU_LAYOUT, HYBRID_MENU_LAYOUT]);
const LIGHT_OVERVIEW_PANEL_CLASS = 'layout-switcher-light-overview-panel';
const NATIVE_ACCENT_PANEL_CLASS = 'layout-switcher-native-accent-panel';
const ACCENT_PROBE_CLASS = 'layout-switcher-accent-probe';
// Build marker within a protocol version — lets a deploy verify over Ping
// that the RUNNING module is the freshly-installed code (the Shell caches
// ES modules; only a reload/relogin picks a new file up).
const HELPER_BUILD = 31;

// GNOME Shell ExtensionState: ACTIVE=1, INACTIVE=2, ERROR=3, OUT_OF_DATE=4,
// DOWNLOADING=5, INITIALIZED=6, DEACTIVATING=7, ACTIVATING=8.
const LIVE_STATES = new Set([1, 8]);
const STATE_ACTIVE = 1;
const STATE_ERROR = 3;
const STATE_DEACTIVATING = 7;

// Per-extension settle budget while awaiting a state transition. Heavy
// extensions (dash-to-panel) can take well over the old fixed 150 ms; a
// bounded poll means we move on exactly when the extension is ready.
const STATE_WAIT_MS = 4000;
const STATE_POLL_MS = 50;

// If the caller dies between BeginSwitch and CompleteSwitch, restore the
// previous extension set so the user is never left on a bare desktop.
const ROLLBACK_TIMEOUT_S = 60;

const CURTAIN_FADE_MS = 250;
const CURTAIN_CHECK_MS = 650;

const IFACE = `
<node>
  <interface name="org.bigcommunity.LayoutSwitcherHelper">
    <method name="Ping">
      <arg type="s" direction="out" name="info"/>
    </method>
    <method name="BeginSwitch">
      <arg type="s" direction="in" name="payload"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="CompleteSwitch">
      <arg type="s" direction="in" name="payload"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="AbortSwitch">
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="ApplyLayout">
      <arg type="s" direction="in" name="payload"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="ReloadExtension">
      <arg type="s" direction="in" name="uuid"/>
      <arg type="s" direction="out" name="result"/>
    </method>
  </interface>
</node>`;

function logHelper(msg) {
    console.log(`[layout-switcher-helper] ${msg}`);
}

// getStyleVariant() in the Shell returns '' for any sessionMode.colorScheme not
// in this set, which then breaks default-stylesheet resolution.
const VALID_COLOR_SCHEMES = new Set([
    'prefer-dark', 'prefer-light', 'force-dark', 'force-light',
]);

// The stock `light-style` extension mutates Main.sessionMode.colorScheme (it
// sets 'prefer-light' on enable and restores a saved value on disable). Toggled
// during a layout switch, that saved value can be lost, leaving
// sessionMode.colorScheme `undefined`. getStyleVariant() then returns '' and the
// Shell's _getDefaultStylesheet() finds no base 'gnome-shell.css' in the
// BigCommunity theme gresource (it only ships -dark/-light/-high-contrast), so
// Main._defaultCssStylesheet becomes null and the next loadTheme() throws
// "Argument file may not be null" — the shell renders unstyled (white panel).
// Restore a valid scheme and re-resolve the default stylesheet (the color-scheme
// notify drives Main._loadDefaultStylesheet) before we call loadTheme().
// Returns true when it had to repair an invalid scheme.
//
// NOTE: we ALWAYS re-resolve (notify), not only when the scheme is invalid.
// light-style can null Main._defaultCssStylesheet via a transient invalid scheme
// during its disable() and then have the scheme end up valid again with no
// further notify to recompute the stylesheet — so checking the current scheme is
// not enough; we must drive Main._loadDefaultStylesheet() unconditionally so
// _defaultCssStylesheet is non-null before loadTheme() reads it.
function ensureValidColorScheme() {
    const repaired = !VALID_COLOR_SCHEMES.has(Main.sessionMode.colorScheme);
    if (repaired)
        Main.sessionMode.colorScheme = 'prefer-dark';
    St.Settings.get().notify('color-scheme');
    return repaired;
}

export default class LayoutSwitcherHelper extends Extension {
    enable() {
        this._pendingSources ??= new Set();
        if (this._bounceCheck) {
            // Re-enabled synchronously after a Shell "rebase" disable (the
            // Shell bounces every later-loaded extension whenever one loaded
            // before it is disabled — including by our own teardown). The
            // in-flight switch survives: timers were kept alive, the D-Bus
            // export was deliberately never touched, and the deferred cancel
            // is dropped here. A bounce is a complete no-op.
            GLib.Source.remove(this._bounceCheck);
            this._bounceCheck = 0;
            logHelper('survived a rebase bounce mid-switch');
            return;
        }
        this._cancelled = false;
        this._export();
        // Panel actors already exist when extensions are enabled. Connect to
        // UPower immediately so the desktop fallback never reaches a frame;
        // the delayed pass below only covers unusually late panel startup.
        this._setupPanelSystemIndicator();
        this._syncNativeAccentPanelClass();
        // Live appearance follower. Classic/Hybrid use GNOME's native Shell;
        // the other Community layouts use their configured shell themes.
        // Papient variants follow the app color scheme in all six layouts.
        if (!this._ifaceSettings) {
            try {
                this._ifaceSettings = new Gio.Settings({
                    schema_id: 'org.gnome.desktop.interface',
                });
                this._schemeSignal = this._ifaceSettings.connect(
                    'changed::color-scheme', () => this._onColorSchemeChanged());
                this._accentSignal = this._ifaceSettings.connect(
                    'changed::accent-color',
                    () => this._syncNativeAccentPanelClass());
                this._lastColorSchemeDark =
                    this._ifaceSettings.get_string('color-scheme') === 'prefer-dark';
                this._syncLightOverviewPanelClass();
                this._syncNativeAccentPanelClass();
                // At login, preserve the saved Shell theme and extension
                // choices. The delayed pass only refreshes derived visuals.
                this._sleep(1000).then(() => {
                    this._onColorSchemeChanged(false);
                    this._setupPanelSystemIndicator();
                    this._syncLightOverviewPanelClass();
                    this._syncNativeAccentPanelClass();
                });
            } catch (e) {
                logHelper(`color-scheme follower unavailable: ${e}`);
                this._ifaceSettings = null;
            }
        }
    }

    disable() {
        if (this._switching || this._applying) {
            // Two ways to land here mid-switch: (a) a rebase bounce — the
            // matching enable() follows synchronously on the same stack;
            // (b) a real disable (screen lock, user toggle). KEEP the D-Bus
            // object exported (consecutive bounces must not interleave
            // unexport/export pairs — re-exporting over a live export
            // throws and kills the extension) and defer the hard cancel by
            // one main-loop iteration: a bounce's enable() drops it, a real
            // disable lets it run.
            if (!this._bounceCheck) {
                this._bounceCheck = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                    this._bounceCheck = 0;
                    logHelper('real disable mid-switch — cancelling');
                    this._hardCancel();
                    return GLib.SOURCE_REMOVE;
                });
            }
            return;
        }
        this._hardCancel();
        logHelper('unexported');
    }

    _export() {
        if (this._dbus)
            return;
        const dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        try {
            dbus.export(Gio.DBus.session, BUS_PATH);
            this._dbus = dbus;
            logHelper(`exported D-Bus interface (v${HELPER_VERSION} build ${HELPER_BUILD})`);
        } catch (e) {
            logHelper(`export failed: ${e}`);
        }
    }

    _unexport() {
        if (!this._dbus)
            return;
        try {
            this._dbus.unexport();
        } catch (e) {
            logHelper(`unexport failed: ${e}`);
        }
        this._dbus = null;
    }

    // Stop every pending timer so no step of an in-flight switch fires into a
    // session-mode transition, and never leave the curtain up.
    _hardCancel() {
        this._teardownPanelSystemIndicator();
        this._clearLightOverviewPanelClass();
        this._clearNativeAccentPanelClass();
        this._unexport();
        if (this._schemeDebounce) {
            GLib.Source.remove(this._schemeDebounce);
            this._schemeDebounce = 0;
        }
        if (this._ifaceSettings) {
            if (this._schemeSignal)
                this._ifaceSettings.disconnect(this._schemeSignal);
            if (this._accentSignal)
                this._ifaceSettings.disconnect(this._accentSignal);
            this._schemeSignal = 0;
            this._accentSignal = 0;
            this._ifaceSettings = null;
        }
        this._cancelled = true;
        if (this._bounceCheck) {
            GLib.Source.remove(this._bounceCheck);
            this._bounceCheck = 0;
        }
        if (this._pendingSources) {
            for (const id of this._pendingSources)
                GLib.Source.remove(id);
            this._pendingSources.clear();
        }
        this._cancelRollbackTimer();
        this._destroyCurtain();
        this._switching = false;
        this._applying = false;
    }

    Ping() {
        return JSON.stringify({
            helper: 'layout-switcher',
            version: HELPER_VERSION,
            build: HELPER_BUILD,
            busy: Boolean(this._switching || this._applying),
        });
    }

    _selfUuid() {
        return this.metadata?.uuid ?? 'layout-switcher-helper@bigcommunity.org';
    }

    _busy() {
        return Boolean(this._switching || this._applying);
    }

    _returnJson(invocation, obj) {
        invocation.return_value(new GLib.Variant('(s)', [JSON.stringify(obj)]));
    }

    // Resolve after `ms` on the main loop — lets each extension's
    // enable()/disable() body and any idle callbacks it queued drain before
    // the next step. Sources are tracked so disable() can cancel them; a
    // cancelled sleep never resolves (the caller chain is abandoned, which is
    // exactly what we want mid-lock).
    _sleep(ms) {
        return new Promise(resolve => {
            const id = GLib.timeout_add(GLib.PRIORITY_DEFAULT, Math.max(0, ms | 0), () => {
                this._pendingSources?.delete(id);
                resolve();
                return GLib.SOURCE_REMOVE;
            });
            this._pendingSources?.add(id);
        });
    }

    // Await an extension state transition instead of trusting a fixed delay.
    // Polls until `predicate(state)` (state is undefined when the uuid is not
    // in the manager map) or the timeout elapses. Returns true on success.
    async _waitState(mgr, uuid, predicate, timeoutMs = STATE_WAIT_MS) {
        const deadline = GLib.get_monotonic_time() + timeoutMs * 1000;
        for (;;) {
            if (this._cancelled)
                return false;
            const state = mgr.lookup(uuid)?.state;
            if (predicate(state))
                return true;
            if (GLib.get_monotonic_time() >= deadline)
                return false;
            await this._sleep(STATE_POLL_MS);
        }
    }

    _isDown(state) {
        return state === undefined ||
            (!LIVE_STATES.has(state) && state !== STATE_DEACTIVATING);
    }

    _isSettledUp(state) {
        // ERROR counts as settled: waiting longer won't fix it, and the
        // caller's self-heal pass handles it.
        return state === STATE_ACTIVE || state === STATE_ERROR;
    }

    _liveUuids(mgr) {
        const uuids = typeof mgr.getUuids === 'function'
            ? mgr.getUuids()
            : [...(mgr._extensions?.keys() ?? [])];
        const live = new Set();
        for (const uuid of uuids) {
            const ext = mgr.lookup(uuid);
            if (ext && LIVE_STATES.has(ext.state))
                live.add(uuid);
        }
        return live;
    }

    // Live uuids in the Shell's real enable order (`_extensionOrder`), so a
    // reverse walk disables later-loaded extensions first. Disabling in that
    // order keeps every `_callExtensionDisable` "rebase" slice empty — the
    // Shell never has to bounce other extensions through silent
    // stateObj.disable()/enable() cycles (the source of duplicated actors and
    // dead cross-extension hooks in the incremental protocol).
    _orderedLive(mgr) {
        const live = this._liveUuids(mgr);
        const order = Array.isArray(mgr._extensionOrder) ? mgr._extensionOrder : [];
        const ordered = order.filter(u => live.has(u));
        for (const uuid of live) {
            if (!ordered.includes(uuid))
                ordered.push(uuid);
        }
        return ordered;
    }

    // GNOME Shell disables an extension by bouncing every live extension that
    // follows it in `_extensionOrder`. Put a single target last before turning
    // it off so that rebase slice is empty. This protects long-lived status
    // indicators whose disable() leaves callbacks behind (notably pamac).
    _moveExtensionLast(mgr, uuid) {
        const order = mgr._extensionOrder;
        if (!Array.isArray(order))
            return false;
        const idx = order.indexOf(uuid);
        if (idx < 0)
            return false;
        if (idx !== order.length - 1) {
            order.splice(idx, 1);
            order.push(uuid);
        }
        return true;
    }

    _extensionWillRun(uuid) {
        const mgr = Main.extensionManager;
        if (LIVE_STATES.has(mgr.lookup(uuid)?.state))
            return true;

        try {
            this._shellSettings ??= new Gio.Settings({
                schema_id: 'org.gnome.shell',
            });
            return this._shellSettings.get_strv('enabled-extensions')
                .includes(uuid);
        } catch (e) {
            logHelper(`enabled extension read failed: ${e}`);
            return false;
        }
    }

    _usesMenuSessionActions() {
        if (!this._extensionWillRun(DTP_UUID))
            return false;

        if (this._extensionWillRun(COMMUNITY_MENU_UUID)) {
            try {
                const settings = new Gio.Settings({
                    schema_id: 'org.gnome.shell.extensions.community-menu',
                });
                const layout = settings.get_enum('layout');
                return layout === CLASSIC_MENU_LAYOUT ||
                    layout === DESK_UX_MENU_LAYOUT;
            } catch (e) {
                logHelper(`community layout read failed: ${e}`);
            }
        }

        if (this._extensionWillRun(ARCMENU_UUID)) {
            try {
                const settings = new Gio.Settings({
                    schema_id: 'org.gnome.shell.extensions.arcmenu',
                });
                return settings.get_string('menu-layout') ===
                    ARCMENU_HYBRID_LAYOUT;
            } catch (e) {
                logHelper(`ArcMenu layout read failed: ${e}`);
            }
        }
        return false;
    }

    _syncPanelSystemIndicator() {
        const indicator = Main.panel.statusArea.quickSettings?._system;
        const powerToggle = indicator?._systemItem?.powerToggle;
        if (!indicator || !powerToggle)
            return false;

        const hidePowerFallback = this._usesMenuSessionActions() &&
            !powerToggle.visible;
        if (hidePowerFallback)
            indicator.hide();
        else
            indicator._syncIndicatorsVisible?.();
        return hidePowerFallback;
    }

    _setupPanelSystemIndicator() {
        this._setupQuickSettingsShutdownItem();
        const indicator = Main.panel.statusArea.quickSettings?._system;
        const powerToggle = indicator?._systemItem?.powerToggle;
        if (!powerToggle)
            return;

        if (this._panelPowerToggle !== powerToggle) {
            if (this._panelPowerToggle && this._panelPowerSignal)
                this._panelPowerToggle.disconnect(this._panelPowerSignal);
            this._panelPowerToggle = powerToggle;
            this._panelPowerSignal = powerToggle.connect(
                'notify::visible', () => this._syncPanelSystemIndicator());
        }
        this._syncPanelSystemIndicator();
    }

    _teardownPanelSystemIndicator() {
        this._teardownQuickSettingsShutdownItem();
        if (this._panelPowerToggle && this._panelPowerSignal)
            this._panelPowerToggle.disconnect(this._panelPowerSignal);
        this._panelPowerToggle = null;
        this._panelPowerSignal = 0;

        const indicator = Main.panel.statusArea.quickSettings?._system;
        indicator?._syncIndicatorsVisible?.();
    }

    _findQuickSettingsShutdownItem() {
        const systemItem = Main.panel.statusArea.quickSettings?._system?._systemItem;
        return systemItem?.child?.get_children()
            .find(item => item?.menu === systemItem.menu) ?? null;
    }

    _syncQuickSettingsShutdownItem() {
        const item = this._quickSettingsShutdownItem;
        if (!item)
            return;

        if (this._usesMenuSessionActions()) {
            if (item.visible)
                item.hide();
            this._quickSettingsShutdownHidden = true;
        } else if (this._quickSettingsShutdownHidden) {
            this._quickSettingsShutdownHidden = false;
            if (typeof item._sync === 'function')
                item._sync();
            else
                item.show();
        }
    }

    _setupQuickSettingsShutdownItem() {
        const item = this._findQuickSettingsShutdownItem();
        if (!item)
            return;

        if (this._quickSettingsShutdownItem !== item) {
            this._teardownQuickSettingsShutdownItem();
            this._quickSettingsShutdownItem = item;
            this._quickSettingsShutdownSignal = item.connect(
                'notify::visible', () => this._syncQuickSettingsShutdownItem());
        }
        this._syncQuickSettingsShutdownItem();
    }

    _teardownQuickSettingsShutdownItem() {
        const item = this._quickSettingsShutdownItem;
        if (item && this._quickSettingsShutdownSignal)
            item.disconnect(this._quickSettingsShutdownSignal);
        this._quickSettingsShutdownSignal = 0;
        this._quickSettingsShutdownItem = null;

        if (item && this._quickSettingsShutdownHidden) {
            this._quickSettingsShutdownHidden = false;
            if (typeof item._sync === 'function')
                item._sync();
            else
                item.show();
        }
    }

    _clearLightOverviewPanelClass() {
        for (const panel of this._lightOverviewPanels ?? []) {
            try {
                panel.remove_style_class_name(LIGHT_OVERVIEW_PANEL_CLASS);
            } catch (e) {
                logHelper(`light overview panel cleanup failed: ${e}`);
            }
        }
        this._lightOverviewPanels?.clear();
    }

    _clearNativeAccentPanelClass() {
        for (const panel of this._nativeAccentPanels ?? []) {
            try {
                panel.remove_style_class_name(NATIVE_ACCENT_PANEL_CLASS);
            } catch (e) {
                logHelper(`native accent panel cleanup failed: ${e}`);
            }
        }
        this._nativeAccentPanels?.clear();
    }

    _shellAccentColor() {
        const probe = new St.Widget({style_class: ACCENT_PROBE_CLASS});
        try {
            Main.uiGroup.add_child(probe);
            if (typeof probe.ensure_style === 'function')
                probe.ensure_style();
            const color = probe.get_theme_node().get_background_color();
            return `#${[color.red, color.green, color.blue]
                .map(channel => channel.toString(16).padStart(2, '0'))
                .join('')}`;
        } catch (e) {
            logHelper(`shell accent read failed: ${e}`);
            return '';
        } finally {
            probe.destroy();
        }
    }

    _syncClassicFocusHighlight() {
        const accent = this._shellAccentColor();
        if (!accent)
            return;

        try {
            const settings = new Gio.Settings({
                schema_id: 'org.gnome.shell.extensions.dash-to-panel',
            });
            if (settings.get_string('focus-highlight-color') !== accent)
                settings.set_string('focus-highlight-color', accent);
        } catch (e) {
            logHelper(`Classic focus highlight sync failed: ${e}`);
        }
    }

    _syncNativeAccentPanelClass() {
        this._clearNativeAccentPanelClass();
        if (!this._extensionWillRun(DTP_UUID))
            return;

        let nativeAccentLayout = false;
        let classicLayout = false;
        if (this._extensionWillRun(COMMUNITY_MENU_UUID)) {
            try {
                const settings = new Gio.Settings({
                    schema_id: 'org.gnome.shell.extensions.community-menu',
                });
                classicLayout = settings.get_enum('layout') === CLASSIC_MENU_LAYOUT;
                nativeAccentLayout = classicLayout;
            } catch (e) {
                logHelper(`community layout read failed: ${e}`);
            }
        } else if (this._extensionWillRun(ARCMENU_UUID)) {
            try {
                const settings = new Gio.Settings({
                    schema_id: 'org.gnome.shell.extensions.arcmenu',
                });
                nativeAccentLayout = settings.get_string('menu-layout') ===
                    ARCMENU_HYBRID_LAYOUT;
            } catch (e) {
                logHelper(`ArcMenu layout read failed: ${e}`);
            }
        }
        if (!nativeAccentLayout)
            return;

        if (classicLayout)
            this._syncClassicFocusHighlight();

        const panels = global.dashToPanel?.panels
            ?.map(panel => panel?.panel)
            .filter(Boolean) ?? [];
        if (panels.length === 0)
            panels.push(Main.panel);
        this._nativeAccentPanels ??= new Set();
        for (const panel of panels) {
            panel.add_style_class_name(NATIVE_ACCENT_PANEL_CLASS);
            this._nativeAccentPanels.add(panel);
        }
    }

    _syncLightOverviewPanelClass() {
        this._clearLightOverviewPanelClass();
        if (!this._ifaceSettings ||
            this._ifaceSettings.get_string('color-scheme') === 'prefer-dark' ||
            !this._extensionWillRun(DTP_UUID) ||
            !this._extensionWillRun(ARCMENU_UUID))
            return;

        try {
            const settings = new Gio.Settings({
                schema_id: 'org.gnome.shell.extensions.arcmenu',
            });
            if (settings.get_string('menu-layout') !== ARCMENU_HYBRID_LAYOUT)
                return;
        } catch (e) {
            logHelper(`ArcMenu layout read failed: ${e}`);
            return;
        }

        const panels = global.dashToPanel?.panels
            ?.map(panel => panel?.panel)
            .filter(Boolean) ?? [];
        if (panels.length === 0)
            panels.push(Main.panel);
        this._lightOverviewPanels ??= new Set();
        for (const panel of panels) {
            panel.add_style_class_name(LIGHT_OVERVIEW_PANEL_CLASS);
            this._lightOverviewPanels.add(panel);
        }
    }

    // ── Live color-scheme follower ──────────────────────────────────────────

    _onColorSchemeChanged(reconcileShell = true) {
        // Debounce: GNOME Settings can emit several changes in a burst, and
        // the layout apply's own dconf load fires this too (skipped below —
        // the apply already sequences the correct shell theme).
        if (this._schemeDebounce)
            GLib.Source.remove(this._schemeDebounce);
        this._schemeDebounce = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
            this._schemeDebounce = 0;
            this._followColorScheme(reconcileShell)
                .catch(e => logHelper(`color-scheme follow failed: ${e}`));
            return GLib.SOURCE_REMOVE;
        });
    }

    async _followColorScheme(reconcileShell = true) {
        if (this._busy() || this._cancelled || !this._ifaceSettings)
            return;
        const mgr = Main.extensionManager;
        const live = this._liveUuids(mgr);
        const dark =
            this._ifaceSettings.get_string('color-scheme') === 'prefer-dark';
        const previousDark = this._lastColorSchemeDark ?? dark;
        const isLive = uuid => LIVE_STATES.has(mgr.lookup(uuid)?.state);
        this._applying = true;   // serialize against layout switches
        try {
            // Classic/Hybrid use an explicit -light icon design. The other
            // four layouts use the unsuffixed design in light mode.
            let explicitLightIcons = false;
            let communityLayout = -1;
            let hybridArcMenu = false;
            if (live.has(COMMUNITY_MENU_UUID)) {
                try {
                    const communitySettings = new Gio.Settings({
                        schema_id: 'org.gnome.shell.extensions.community-menu',
                    });
                    communityLayout = communitySettings.get_enum('layout');
                    explicitLightIcons = COMMUNITY_LIGHT_ICON_LAYOUTS.has(
                        communityLayout);
                } catch (e) {
                    logHelper(`community layout read failed: ${e}`);
                }
            } else if (live.has(ARCMENU_UUID)) {
                try {
                    const arcMenuSettings = new Gio.Settings({
                        schema_id: 'org.gnome.shell.extensions.arcmenu',
                    });
                    hybridArcMenu = arcMenuSettings.get_string('menu-layout') ===
                        ARCMENU_HYBRID_LAYOUT;
                    explicitLightIcons = hybridArcMenu;
                } catch (e) {
                    logHelper(`ArcMenu layout read failed: ${e}`);
                }
            }
            try {
                const icon = this._ifaceSettings.get_string('icon-theme');
                const variants = new Set([
                    'bigicons-papient',
                    'bigicons-papient-dark',
                    'bigicons-papient-light',
                ]);
                const target = dark
                    ? 'bigicons-papient-dark'
                    : (explicitLightIcons
                        ? 'bigicons-papient-light'
                        : 'bigicons-papient');
                if (variants.has(icon) && icon !== target)
                    this._ifaceSettings.set_string('icon-theme', target);
            } catch (e) {
                logHelper(`icon-theme follow failed: ${e}`);
            }

            // BigGnome and the Kiwi layouts keep an always-dark Shell. Their
            // app/icon preference above still follows light/dark.
            if (live.has(KIWI_UUID) || !live.has(DTP_UUID) ||
                (!live.has(COMMUNITY_MENU_UUID) && !hybridArcMenu))
                return;

            const nativeShell = communityLayout === CLASSIC_MENU_LAYOUT ||
                communityLayout === HYBRID_MENU_LAYOUT || hybridArcMenu;
            const deskUxOrchisShell = communityLayout === DESK_UX_MENU_LAYOUT;
            this._shellSettings ??= new Gio.Settings({schema_id: 'org.gnome.shell'});
            const enabled = this._shellSettings.get_strv('enabled-extensions');
            const disabled = this._shellSettings.get_strv('disabled-extensions');
            const configured = uuid => enabled.includes(uuid) && !disabled.includes(uuid);
            const userThemeSettings = new Gio.Settings({
                schema_id: 'org.gnome.shell.extensions.user-theme',
            });
            const currentShellTheme = userThemeSettings.get_string('name');
            const managedNativeState = nativeShell &&
                currentShellTheme === '' &&
                !configured(USER_THEME_UUID) &&
                configured(LIGHT_STYLE_UUID) === !previousDark;
            const previousDeskUxTheme = previousDark
                ? ORCHIS_SHELL_DARK
                : ORCHIS_SHELL_LIGHT;
            const managedDeskUxState = deskUxOrchisShell &&
                currentShellTheme === previousDeskUxTheme &&
                configured(USER_THEME_UUID) &&
                !configured(LIGHT_STYLE_UUID);
            const manageShell = reconcileShell &&
                (managedNativeState || managedDeskUxState);
            const wantOn = deskUxOrchisShell
                ? USER_THEME_UUID
                : (dark ? USER_THEME_UUID : LIGHT_STYLE_UUID);
            const wantOff = deskUxOrchisShell
                ? LIGHT_STYLE_UUID
                : (dark ? LIGHT_STYLE_UUID : USER_THEME_UUID);
            const shellMode = nativeShell
                ? 'native'
                : (deskUxOrchisShell
                    ? (dark ? ORCHIS_SHELL_DARK : ORCHIS_SHELL_LIGHT)
                    : (dark ? ORCHIS_SHELL_DARK : 'light-style'));
            logHelper(`color-scheme follow: ${dark ? 'dark' : 'light'} (${shellMode}, ${
                manageShell ? 'managed' : 'preserved'})`);

            const shellThemeName = nativeShell
                ? ''
                : (deskUxOrchisShell
                    ? (dark ? ORCHIS_SHELL_DARK : ORCHIS_SHELL_LIGHT)
                    : (dark ? ORCHIS_SHELL_DARK : userThemeSettings.get_string('name')));
            if (manageShell) {
                if (currentShellTheme !== shellThemeName)
                    userThemeSettings.set_string('name', shellThemeName);

                const turnOff = nativeShell && dark
                    ? [LIGHT_STYLE_UUID, USER_THEME_UUID]
                    : [wantOff];
                for (const uuid of turnOff) {
                    if (!isLive(uuid))
                        continue;
                    this._moveExtensionLast(mgr, uuid);
                    mgr.disableExtension(uuid);
                    await this._waitState(mgr, uuid, s => this._isDown(s));
                }
                if (nativeShell && dark)
                    Main.sessionMode.colorScheme = 'prefer-dark';
                ensureValidColorScheme();
                try {
                    if (nativeShell)
                        Main.setThemeStylesheet(null);
                    Main.loadTheme();
                } catch (e) {
                    logHelper(`loadTheme ERR ${e}`);
                }
                await this._sleep(50);

                if (!(nativeShell && dark) && !isLive(wantOn)) {
                    mgr.enableExtension(wantOn);
                    await this._waitState(
                        mgr, wantOn, s => this._isSettledUp(s));
                    if (mgr.lookup(wantOn)?.state === STATE_ERROR)
                        logHelper(`${wantOn} errored while following color scheme`);
                }
            }
            // Window-title label colors (unfocused + minimized): DTP's
            // 'inherit' resolves to white regardless of the light shell
            // theme — black in light mode, back to inherit in dark. Only the
            // inherit↔black pair is swapped (custom designs untouched).
            try {
                // Distro packages install the schema into the GLOBAL compiled
                // source (/usr/share/glib-2.0/schemas); only user-installed
                // copies carry a compiled schema in the extension dir.
                const defaultSource = Gio.SettingsSchemaSource.get_default();
                let schema = defaultSource?.lookup(
                    'org.gnome.shell.extensions.dash-to-panel', true);
                if (!schema) {
                    const dtpExt = mgr.lookup(DTP_UUID);
                    if (dtpExt?.path) {
                        const source = Gio.SettingsSchemaSource.new_from_directory(
                            `${dtpExt.path}/schemas`, defaultSource, false);
                        schema = source?.lookup(
                            'org.gnome.shell.extensions.dash-to-panel', true);
                    }
                }
                {
                    if (schema) {
                        const dtpSettings = new Gio.Settings({settings_schema: schema});
                        // focused label sits on the blue highlight → white;
                        // unfocused/minimized sit on the light bar → black.
                        const lightColors = {
                            'group-apps-label-font-color': '#ffffff',
                            'group-apps-label-font-color-minimized': '#000000',
                        };
                        for (const [key, lightColor] of Object.entries(lightColors)) {
                            const cur = dtpSettings.get_string(key);
                            if (dark && cur === lightColor)
                                dtpSettings.set_string(key, 'inherit');
                            else if (!dark && cur === 'inherit')
                                dtpSettings.set_string(key, lightColor);
                        }
                    }
                }
            } catch (e) {
                logHelper(`dtp label-color follow failed: ${e}`);
            }
            // dash-to-panel bakes label/foreground colors from the theme at
            // construction time — rebuild it so window-title labels re-read
            // the new theme (white-on-light labels otherwise).
            if (isLive(DTP_UUID)) {
                this._moveExtensionLast(mgr, DTP_UUID);
                mgr.disableExtension(DTP_UUID);
                await this._waitState(mgr, DTP_UUID, s => this._isDown(s));
                mgr.enableExtension(DTP_UUID);
                await this._waitState(mgr, DTP_UUID, s => this._isSettledUp(s));
            }
            this._setupPanelSystemIndicator();
            this._syncLightOverviewPanelClass();
            this._syncNativeAccentPanelClass();
            // Cross-frame style recompute so the panel picks the new theme.
            Main.panel.add_style_class_name('ls-style-recompute');
            await this._sleep(60);
            Main.panel.remove_style_class_name('ls-style-recompute');
        } finally {
            this._lastColorSchemeDark = dark;
            this._applying = false;
        }
    }

    // ── Transition curtain ──────────────────────────────────────────────────

    _createCurtain(label, labelFrom, iconFrom, iconTo) {
        const curtain = new St.BoxLayout({
            style_class: 'layout-switcher-curtain',
            style: 'background-color: #101014;',
            vertical: true,
            reactive: true,   // swallow clicks while the desktop mutates
            opacity: 0,
        });
        curtain.set_position(0, 0);
        curtain.set_size(global.stage.width, global.stage.height);

        const box = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            y_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'spacing: 36px;',
        });

        // The "one environment to the other" art: the previous layout's
        // preview dims while the target's slides into place.
        const validPath = path => {
            try {
                if (path && GLib.file_test(path, GLib.FileTest.EXISTS))
                    return path;
            } catch (e) {
                logHelper(`curtain icon failed: ${e}`);
            }
            return null;
        };
        // The preview SVGs are wide (~1.7:1). St.Icon forces a SQUARE box and
        // squishes them laterally — render through the texture cache with a
        // fixed width and free height so the aspect ratio is preserved.
        const makePreview = path => {
            try {
                const cache = St.TextureCache.get_default();
                if (typeof cache.load_file_async === 'function') {
                    const scale =
                        St.ThemeContext.get_for_stage(global.stage).scale_factor;
                    const actor = cache.load_file_async(
                        Gio.File.new_for_path(path), 230, -1, scale, 1);
                    return new St.Bin({
                        child: actor,
                        x_align: Clutter.ActorAlign.CENTER,
                    });
                }
            } catch (e) {
                logHelper(`curtain preview failed: ${e}`);
            }
            // Fallback: square icon box (letterboxes the art).
            return new St.Icon({
                gicon: new Gio.FileIcon({file: Gio.File.new_for_path(path)}),
                icon_size: 150,
                x_align: Clutter.ActorAlign.CENTER,
            });
        };
        const fromPath = validPath(iconFrom);
        const toPath = validPath(iconTo);
        // Layout previews as proper cards (translucent backing so the dark
        // line-art SVGs actually read on the near-black curtain), each with
        // its name; the target card gets an accent border + neon glow.
        const makeCard = (path, name, highlight) => {
            const card = new St.BoxLayout({
                vertical: true,
                style: highlight
                    ? 'background-color: rgba(255, 255, 255, 0.07); ' +
                      'border-radius: 18px; padding: 22px 26px; spacing: 14px; ' +
                      'border: 1px solid rgba(53, 132, 228, 0.85); ' +
                      'box-shadow: 0 0 26px 3px rgba(53, 132, 228, 0.35);'
                    : 'background-color: rgba(255, 255, 255, 0.04); ' +
                      'border-radius: 18px; padding: 22px 26px; spacing: 14px; ' +
                      'border: 1px solid rgba(255, 255, 255, 0.08);',
            });
            card.add_child(makePreview(path));
            if (name) {
                card.add_child(new St.Label({
                    text: name,
                    style: highlight
                        ? 'font-size: 16px; font-weight: bold; color: #ffffff;'
                        : 'font-size: 16px; color: #9a9996;',
                    x_align: Clutter.ActorAlign.CENTER,
                }));
            }
            return card;
        };
        if (toPath) {
            const row = new St.BoxLayout({
                x_align: Clutter.ActorAlign.CENTER,
                style: 'spacing: 30px;',
            });
            if (fromPath) {
                const fromCard = makeCard(fromPath, labelFrom, false);
                row.add_child(fromCard);
                row.add_child(new St.Icon({
                    icon_name: 'go-next-symbolic',
                    icon_size: 26,
                    style: 'color: #777777;',
                    y_align: Clutter.ActorAlign.CENTER,
                }));
                fromCard.ease({
                    opacity: 150,
                    duration: 700,
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                });
            }
            const toCard = makeCard(toPath, label, true);
            toCard.opacity = 0;
            toCard.translation_x = 48;
            row.add_child(toCard);
            toCard.ease({
                opacity: 255,
                translation_x: 0,
                duration: 700,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
            box.add_child(row);
        } else if (label) {
            box.add_child(new St.Label({
                text: label,
                style: 'font-size: 24px; font-weight: bold; color: #eeeeec;',
                x_align: Clutter.ActorAlign.CENTER,
            }));
        }
        let spinner = null;
        try {
            spinner = new Spinner(36, {animate: true});
            spinner.play();
        } catch (e) {
            logHelper(`spinner unavailable: ${e}`);
        }
        if (spinner) {
            const spinnerBin = new St.Bin({
                child: spinner,
                x_align: Clutter.ActorAlign.CENTER,
            });
            box.add_child(spinnerBin);
            curtain._lsSpinner = spinnerBin;
        }
        curtain.add_child(box);
        curtain._lsStatusBox = box;
        return curtain;
    }

    _curtainUp(req) {
        if (this._curtain)
            return;
        try {
            const curtain = this._createCurtain(
                req.label || '', req.label_from || '',
                req.icon_from || '', req.icon_to || '');
            Main.layoutManager.uiGroup.add_child(curtain);
            this._curtain = curtain;
            curtain.ease({
                opacity: 255,
                duration: CURTAIN_FADE_MS,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        } catch (e) {
            // Purely cosmetic — a failed curtain must never block the switch.
            logHelper(`curtain up failed: ${e}`);
            this._curtain = null;
        }
    }

    // Swap the spinner for a neon-glow green checkmark: the in-shell "done"
    // signal the user sees right before the curtain lifts.
    _curtainCheckmark() {
        const curtain = this._curtain;
        if (!curtain)
            return;
        try {
            if (curtain._lsSpinner) {
                curtain._lsSpinner.destroy();
                curtain._lsSpinner = null;
            }
            const badge = new St.Bin({
                child: new St.Icon({
                    icon_name: 'object-select-symbolic',
                    icon_size: 42,
                    style: 'color: #2ec27e;',
                }),
                style: 'background-color: rgba(38, 162, 105, 0.16); ' +
                       'border: 1px solid rgba(46, 194, 126, 0.55); ' +
                       'border-radius: 999px; padding: 18px; ' +
                       'box-shadow: 0 0 32px 8px rgba(46, 194, 126, 0.55);',
                x_align: Clutter.ActorAlign.CENTER,
            });
            badge.set_pivot_point(0.5, 0.5);
            badge.set_scale(0.5, 0.5);
            curtain._lsStatusBox?.add_child(badge);
            badge.ease({
                scale_x: 1,
                scale_y: 1,
                duration: 300,
                mode: Clutter.AnimationMode.EASE_OUT_BACK,
            });
        } catch (e) {
            logHelper(`curtain checkmark failed: ${e}`);
        }
    }

    _curtainDown() {
        const curtain = this._curtain;
        this._curtain = null;
        if (!curtain)
            return;
        try {
            curtain.ease({
                opacity: 0,
                duration: CURTAIN_FADE_MS,
                mode: Clutter.AnimationMode.EASE_IN_QUAD,
                onComplete: () => curtain.destroy(),
            });
        } catch (e) {
            curtain.destroy();
        }
    }

    _destroyCurtain() {
        if (this._curtain) {
            this._curtain.destroy();
            this._curtain = null;
        }
    }

    // Force a style recompute on the panel without opening the Overview.
    // Same-tick add/remove is coalesced by St into a no-op for the panel
    // BACKGROUND, so this is only the cheap best-effort used by the legacy
    // (curtainless) path — the clean-room path uses _panelRepaint().
    _panelStyleRecompute() {
        try {
            Main.panel.add_style_class_name('ls-style-recompute');
            Main.panel.remove_style_class_name('ls-style-recompute');
        } catch (e) {
            logHelper(`panel recompute failed: ${e}`);
        }
    }

    // Make the panel re-resolve its themed background for real. A style-class
    // toggle and even loadTheme() do not repaint Big-Blue's transparent
    // `#panel` rule; the one reliable trigger found is an Overview
    // round-trip (the old "overview pulse" workaround, removed for flashing —
    // under the curtain it is invisible, so it returns here flash-free).
    async _panelRepaint() {
        try {
            Main.panel.add_style_class_name('ls-style-recompute');
            await this._sleep(60);
            Main.panel.remove_style_class_name('ls-style-recompute');
            await this._sleep(60);
        } catch (e) {
            logHelper(`panel recompute failed: ${e}`);
        }
        try {
            Main.overview.show();
            await this._sleep(300);
            Main.overview.hide();
            await this._sleep(250);
        } catch (e) {
            logHelper(`overview pulse failed: ${e}`);
        }
    }

    // ── Rollback safety net ─────────────────────────────────────────────────

    _armRollbackTimer(seconds) {
        this._cancelRollbackTimer();
        this._rollbackTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, seconds, () => {
            this._rollbackTimer = 0;
            if (this._switching) {
                logHelper('CompleteSwitch never arrived — rolling back');
                this._rollback().catch(e => logHelper(`rollback failed: ${e}`));
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    _cancelRollbackTimer() {
        if (this._rollbackTimer) {
            GLib.Source.remove(this._rollbackTimer);
            this._rollbackTimer = 0;
        }
    }

    async _rollback() {
        const mgr = Main.extensionManager;
        const prev = this._prevEnabled ?? [];
        for (const uuid of prev) {
            if (this._cancelled)
                break;
            try {
                if (!LIVE_STATES.has(mgr.lookup(uuid)?.state)) {
                    mgr.enableExtension(uuid);
                    await this._waitState(mgr, uuid, s => this._isSettledUp(s));
                }
            } catch (e) {
                logHelper(`rollback enable ${uuid} failed: ${e}`);
            }
        }
        this._syncLightOverviewPanelClass();
        this._syncNativeAccentPanelClass();
        await this._panelRepaint();
        this._setupPanelSystemIndicator();
        this._curtainDown();
        this._switching = false;
        logHelper(`rollback done (${prev.length} extensions restored)`);
    }

    // ── Clean-room protocol (v7) ────────────────────────────────────────────

    // payload (JSON):
    //   persist: [uuid…]  informative: system indicators the caller re-adds
    //                     to the CompleteSwitch target (the teardown cycles
    //                     them too — one clean toggle beats the Shell's
    //                     repeated rebase toggles, which break pamac-updates)
    //   label:   str      layout display name shown on the curtain
    //   icon_from/icon_to: str  preview SVG paths for the curtain art
    // result (JSON): { ok, steps:[…], disabled:[…], error }
    BeginSwitchAsync(params, invocation) {
        const [payload] = params;
        if (this._busy()) {
            this._returnJson(invocation, {
                ok: false, steps: [], disabled: [],
                error: 'busy: a layout switch is already in progress',
            });
            return;
        }
        this._switching = true;
        this._beginSwitch(payload)
            .then(result => this._returnJson(invocation, result))
            .catch(err => {
                logHelper(`BeginSwitch fatal: ${err}`);
                this._switching = false;
                this._destroyCurtain();
                this._returnJson(invocation, {
                    ok: false, steps: [], disabled: [], error: String(err),
                });
            });
    }

    async _beginSwitch(payload) {
        const steps = [];
        const req = JSON.parse(payload || '{}');
        const self = this._selfUuid();
        const mgr = Main.extensionManager;

        this._curtainUp(req);
        // Let the curtain reach full opacity before the desktop mutates.
        await this._sleep(CURTAIN_FADE_MS + 30);

        // Hoist ourselves to the FRONT of the Shell's extension order. The
        // Shell's "rebase" cascade re-toggles every live extension loaded
        // AFTER the one being disabled — asynchronously, with awaits in
        // between — and a single broken third-party disable() (pamac-updates
        // throws on a double toggle) aborts it mid-way, leaving extensions
        // (including us) dead. With the helper first and the teardown below
        // walking strict reverse order, every rebase slice is empty: nobody
        // gets bounced, ever.
        if (Array.isArray(mgr._extensionOrder)) {
            const idx = mgr._extensionOrder.indexOf(self);
            if (idx > 0) {
                mgr._extensionOrder.splice(idx, 1);
                mgr._extensionOrder.unshift(self);
                steps.push('hoist self');
            }
        }

        // Snapshot for AbortSwitch / the auto-rollback timer (enable order),
        // and arm the safety net BEFORE mutating anything — a fatal failure
        // anywhere in the teardown still auto-restores the previous set.
        this._prevEnabled = this._orderedLive(mgr);
        this._armRollbackTimer(ROLLBACK_TIMEOUT_S);

        // Tear down EVERY live extension except ourselves — including the
        // persist indicators (req.persist is honoured by the CALLER keeping
        // them in the CompleteSwitch target list). Skipping them here looks
        // gentler but is strictly worse: they sit late in the load order, so
        // each managed disable would rebase-toggle them repeatedly and
        // pamac-updates' broken disable() aborts the Shell's rebase loop.
        // One clean disable + one clean enable per switch instead. Strict
        // reverse order keeps every rebase slice empty. After this loop
        // nothing is listening to the layout-owned dconf branches — the
        // caller can reset+load them like a login does.
        const teardown = this._prevEnabled.filter(u => u !== self).reverse();
        const disabled = [];
        for (const uuid of teardown) {
            try {
                const accepted = mgr.disableExtension(uuid);
                if (accepted === false) {
                    steps.push(`disable ${uuid} REJECTED`);
                    continue;
                }
                const settled = await this._waitState(mgr, uuid, s => this._isDown(s));
                steps.push(settled ? `disable ${uuid}` : `disable ${uuid} TIMEOUT`);
                disabled.push(uuid);
            } catch (e) {
                steps.push(`disable ${uuid} ERR ${e}`);
            }
        }
        // Drain any idles the last disable() queued.
        await this._sleep(100);

        logHelper(`BeginSwitch done: ${steps.join(' | ')}`);
        return {ok: true, steps, disabled, error: ''};
    }

    // payload (JSON):
    //   enabled:      [uuid…]  target extension set, in layout (enable) order
    //   theme_reload: bool     call Main.loadTheme() before enabling (default true)
    // result (JSON): { ok, steps:[…], error }
    CompleteSwitchAsync(params, invocation) {
        const [payload] = params;
        if (!this._switching) {
            this._returnJson(invocation, {
                ok: false, steps: [], error: 'no switch in progress (BeginSwitch first)',
            });
            return;
        }
        this._cancelRollbackTimer();
        this._completeSwitch(payload)
            .then(result => this._returnJson(invocation, result))
            .catch(err => {
                logHelper(`CompleteSwitch fatal: ${err}`);
                this._switching = false;
                this._destroyCurtain();
                this._returnJson(invocation, {ok: false, steps: [], error: String(err)});
            });
    }

    async _completeSwitch(payload) {
        const steps = [];
        const req = JSON.parse(payload || '{}');
        const order = (req.enabled || []).filter(Boolean);
        const target = new Set(order);
        const mgr = Main.extensionManager;

        // Self-protection: we must stay exported through the whole switch.
        const self = this._selfUuid();
        target.add(self);

        // The state is final on disk and nothing re-themes behind us: repair
        // the color scheme and rebuild the base stylesheet exactly once,
        // BEFORE the appearance extensions enable on top of it.
        if (ensureValidColorScheme())
            steps.push('fix colorScheme');
        if (req.theme_reload !== false) {
            try {
                Main.loadTheme();
                steps.push('loadTheme');
            } catch (e) {
                steps.push(`loadTheme ERR ${e}`);
            }
            await this._sleep(50);
        }

        // Build up the target set in layout order — a fresh enable() reading
        // the final dconf state, exactly like a login. user-theme is expected
        // first in `order` (its enable() re-runs loadTheme with the named
        // stylesheet; anything enabled before it would be re-themed over).
        for (const uuid of order) {
            const state = mgr.lookup(uuid)?.state;
            if (LIVE_STATES.has(state))
                continue;
            try {
                const accepted = mgr.enableExtension(uuid);
                if (accepted === false) {
                    steps.push(`enable ${uuid} REJECTED`);
                    continue;
                }
                const settled = await this._waitState(mgr, uuid, s => this._isSettledUp(s));
                const finalState = mgr.lookup(uuid)?.state;
                if (finalState === STATE_ERROR)
                    steps.push(`enable ${uuid} ERROR`);
                else
                    steps.push(settled ? `enable ${uuid}` : `enable ${uuid} TIMEOUT`);
            } catch (e) {
                steps.push(`enable ${uuid} ERR ${e}`);
            }
        }

        // Reconcile: anything still live that the target does not want
        // (defensive — persist uuids are part of the target by contract).
        for (const uuid of this._orderedLive(mgr).reverse()) {
            if (target.has(uuid))
                continue;
            try {
                mgr.disableExtension(uuid);
                await this._waitState(mgr, uuid, s => this._isDown(s));
                steps.push(`reconcile-off ${uuid}`);
            } catch (e) {
                steps.push(`reconcile-off ${uuid} ERR ${e}`);
            }
        }

        this._syncLightOverviewPanelClass();
        this._syncNativeAccentPanelClass();
        await this._panelRepaint();
        steps.push('panel repaint');
        this._setupPanelSystemIndicator();

        this._curtainCheckmark();
        await this._sleep(CURTAIN_CHECK_MS);
        this._curtainDown();

        this._prevEnabled = null;
        this._switching = false;
        logHelper(`CompleteSwitch done: ${steps.join(' | ')}`);
        return {ok: true, steps, error: ''};
    }

    AbortSwitchAsync(params, invocation) {
        if (!this._switching) {
            this._returnJson(invocation, {ok: true, restored: 0, error: ''});
            return;
        }
        this._cancelRollbackTimer();
        const count = this._prevEnabled?.length ?? 0;
        this._rollback()
            .then(() => this._returnJson(invocation, {ok: true, restored: count, error: ''}))
            .catch(err => {
                logHelper(`AbortSwitch fatal: ${err}`);
                this._switching = false;
                this._destroyCurtain();
                this._returnJson(invocation, {ok: false, restored: 0, error: String(err)});
            });
    }

    // ── Legacy incremental protocol (v6) — kept for older app versions ─────

    // Re-initialise one extension so it re-reads its config / destroys+rebuilds
    // its actors. `reloadExtension` is async in GNOME 45+ — await it, or the
    // subsequent disable races the in-flight reload and can be silently lost.
    async _reloadOne(mgr, uuid) {
        const ext = mgr.lookup(uuid);
        if (!ext)
            return false;
        try {
            if (typeof mgr.reloadExtension === 'function') {
                await mgr.reloadExtension(ext);
            } else {
                mgr.disableExtension(uuid);
                await this._waitState(mgr, uuid, s => this._isDown(s));
                mgr.enableExtension(uuid);
            }
            await this._waitState(mgr, uuid, s => this._isSettledUp(s));
            return true;
        } catch (e) {
            logHelper(`reloadOne ${uuid} failed: ${e}`);
            return false;
        }
    }

    // Async D-Bus method (GJS convention: <name>Async(params, invocation)).
    ApplyLayoutAsync(params, invocation) {
        const [payload] = params;
        // Serialize: an ApplyLayout drives many enable/disable/reload steps on
        // the Shell main loop. A second ApplyLayout arriving before the first
        // finishes (rapid switching, a wedged caller) interleaves extension
        // manager mutations and can spin the main loop to a hang. One switch
        // runs at a time — reject overlapping calls instead of racing them.
        if (this._busy()) {
            this._returnJson(invocation, {
                ok: false, steps: [],
                error: 'busy: a layout switch is already in progress',
            });
            return;
        }
        this._applying = true;
        this._applyLayout(payload)
            .then(result => {
                invocation.return_value(new GLib.Variant('(s)', [result]));
            })
            .catch(err => {
                logHelper(`ApplyLayout fatal: ${err}`);
                this._returnJson(invocation, {ok: false, steps: [], error: String(err)});
            })
            .finally(() => {
                this._applying = false;
            });
    }

    ReloadExtensionAsync(params, invocation) {
        const [uuid] = params;
        // A reload mutates the extension manager too; don't run it concurrently
        // with an in-flight switch.
        if (this._busy()) {
            this._returnJson(invocation, {ok: false, uuid, error: 'busy'});
            return;
        }
        this._applying = true;
        this._reloadOne(Main.extensionManager, uuid)
            .then(ok => this._returnJson(invocation, {ok, uuid}))
            .catch(err => this._returnJson(invocation, {ok: false, uuid, error: String(err)}))
            .finally(() => {
                this._applying = false;
            });
    }

    // payload (JSON):
    //   enabled:  [uuid…]  target enabled-extensions, in load order
    //   reload:   [uuid…]  staying extensions to reload (re-read appearance)
    //   teardown: [uuid…]  leaving extensions to reload-then-disable, so their
    //                      actor is rebuilt fresh and destroyed cleanly (kills
    //                      the ghost dock/panel left by a plain disable)
    //   step_ms:  int      settle between steps (default 150)
    //   theme_reload: bool call Main.loadTheme() at the end (default true)
    // result (JSON): { ok, steps:[…], error }
    async _applyLayout(payload) {
        const steps = [];
        const req = JSON.parse(payload || '{}');
        const order = (req.enabled || []).filter(Boolean);
        const target = new Set(order);
        const reload = new Set((req.reload || []).filter(Boolean));
        const teardown = new Set((req.teardown || []).filter(Boolean));
        const stepMs = Number.isFinite(req.step_ms) ? req.step_ms : 150;
        const mgr = Main.extensionManager;

        // Self-protection: never tear ourselves down mid-apply.
        const self = this._selfUuid();
        target.add(self);
        reload.delete(self);
        teardown.delete(self);

        const live = this._liveUuids(mgr);

        // 1. Disable extensions leaving the layout. Reverse so later-loaded go
        //    first (fewer of the Shell's internal "rebase" cycles). Extensions
        //    in `teardown` (dock/panel owners) get a reload first so their
        //    actor is fresh and disable() destroys it cleanly instead of
        //    leaving a ghost.
        const leaving = [...live].filter(u => !target.has(u)).reverse();
        for (const uuid of leaving) {
            try {
                if (teardown.has(uuid)) {
                    await this._reloadOne(mgr, uuid);
                    steps.push(`teardown-reload ${uuid}`);
                    await this._sleep(stepMs);
                }
                const accepted = mgr.disableExtension(uuid);
                await this._waitState(mgr, uuid, s => this._isDown(s));
                steps.push(accepted === false ? `disable ${uuid} REJECTED` : `disable ${uuid}`);
            } catch (e) {
                steps.push(`disable ${uuid} ERR ${e}`);
            }
            await this._sleep(stepMs);
        }

        // 2. Disable the staying-but-reload set so step 4 re-enables them and
        //    their enable() re-reads the (already loaded) dconf appearance.
        for (const uuid of order) {
            if (reload.has(uuid) && live.has(uuid) && target.has(uuid)) {
                try {
                    mgr.disableExtension(uuid);
                    await this._waitState(mgr, uuid, s => this._isDown(s));
                    steps.push(`reload-off ${uuid}`);
                } catch (e) {
                    steps.push(`reload-off ${uuid} ERR ${e}`);
                }
                await this._sleep(stepMs);
            }
        }

        // 3. Reload the base shell stylesheet *before* re-enabling the
        //    appearance extensions. loadTheme() rebuilds the global St theme
        //    from disk (default, or user-theme's named stylesheet if it's
        //    live), which CLOBBERS any panel styling an extension applied on
        //    enable. Extensions that paint the shell themselves (kiwi,
        //    light-style) must therefore enable *after* this, so their theming
        //    lands on top and survives.
        if (ensureValidColorScheme())
            steps.push('fix colorScheme');

        if (req.theme_reload !== false) {
            try {
                Main.loadTheme();
                steps.push('loadTheme');
            } catch (e) {
                steps.push(`loadTheme ERR ${e}`);
            }
            await this._sleep(stepMs);
        }

        // 4. Enable every target extension not currently live, in target order,
        //    so each applies its appearance on top of the freshly-loaded theme.
        const liveNow = this._liveUuids(mgr);
        for (const uuid of order) {
            if (liveNow.has(uuid))
                continue;
            try {
                const accepted = mgr.enableExtension(uuid);
                await this._waitState(mgr, uuid, s => this._isSettledUp(s));
                steps.push(accepted === false ? `enable ${uuid} REJECTED` : `enable ${uuid}`);
            } catch (e) {
                steps.push(`enable ${uuid} ERR ${e}`);
            }
            await this._sleep(stepMs);
        }

        this._panelStyleRecompute();
        this._setupPanelSystemIndicator();
        this._syncLightOverviewPanelClass();
        this._syncNativeAccentPanelClass();

        logHelper(`ApplyLayout done: ${steps.join(' | ')}`);
        return JSON.stringify({ok: true, steps, error: ''});
    }
}
