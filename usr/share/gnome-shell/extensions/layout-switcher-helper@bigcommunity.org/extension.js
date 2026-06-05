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
// D-BUS INTERFACE  (exported on the shell's bus name org.gnome.Shell)
//   dest:  org.gnome.Shell
//   path:  /org/bigcommunity/LayoutSwitcherHelper
//   iface: org.bigcommunity.LayoutSwitcherHelper
//   Ping()                  -> s   JSON {helper, version}
//   ApplyLayout(payload: s) -> s   see _applyLayout for the schema
//   ReloadExtension(uuid: s)-> s   reload one extension (re-read appearance)

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_PATH = '/org/bigcommunity/LayoutSwitcherHelper';
const HELPER_VERSION = 4;

// GNOME Shell ExtensionState: ENABLED=1, ENABLING=8 → "live".
const LIVE_STATES = new Set([1, 8]);

const IFACE = `
<node>
  <interface name="org.bigcommunity.LayoutSwitcherHelper">
    <method name="Ping">
      <arg type="s" direction="out" name="info"/>
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

// Resolve after `ms` on the main loop — lets each extension's enable()/disable()
// body and any idle callbacks it queued drain before the next step.
function sleep(ms) {
    return new Promise(resolve => {
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, Math.max(0, ms | 0), () => {
            resolve();
            return GLib.SOURCE_REMOVE;
        });
    });
}

export default class LayoutSwitcherHelper extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, BUS_PATH);
        logHelper(`exported D-Bus interface (v${HELPER_VERSION})`);
    }

    disable() {
        if (this._dbus) {
            this._dbus.unexport();
            this._dbus = null;
        }
        logHelper('unexported');
    }

    Ping() {
        return JSON.stringify({helper: 'layout-switcher', version: HELPER_VERSION});
    }

    _selfUuid() {
        return this.metadata?.uuid ?? 'layout-switcher-helper@bigcommunity.org';
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

    // Re-initialise one extension so it re-reads its config / destroys+rebuilds
    // its actors. Prefers trulyReloadExtension (drops the JS module cache),
    // falls back to reloadExtension, then to a plain disable+enable.
    _reloadOne(mgr, uuid) {
        const ext = mgr.lookup(uuid);
        if (!ext)
            return false;
        try {
            if (typeof mgr.trulyReloadExtension === 'function')
                mgr.trulyReloadExtension(uuid);
            else if (typeof mgr.reloadExtension === 'function')
                mgr.reloadExtension(ext);
            else {
                mgr.disableExtension(uuid);
                mgr.enableExtension(uuid);
            }
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
        if (this._applying) {
            invocation.return_value(new GLib.Variant('(s)', [
                JSON.stringify({ok: false, steps: [], error: 'busy: a layout switch is already in progress'}),
            ]));
            return;
        }
        this._applying = true;
        this._applyLayout(payload)
            .then(result => {
                invocation.return_value(new GLib.Variant('(s)', [result]));
            })
            .catch(err => {
                logHelper(`ApplyLayout fatal: ${err}`);
                invocation.return_value(new GLib.Variant('(s)', [
                    JSON.stringify({ok: false, steps: [], error: String(err)}),
                ]));
            })
            .finally(() => {
                this._applying = false;
            });
    }

    ReloadExtensionAsync(params, invocation) {
        const [uuid] = params;
        // A reload mutates the extension manager too; don't run it concurrently
        // with an in-flight ApplyLayout (post-apply self-heal/theme re-assert
        // calls land right after, but the apply promise has already settled).
        if (this._applying) {
            invocation.return_value(new GLib.Variant('(s)', [
                JSON.stringify({ok: false, uuid, error: 'busy'}),
            ]));
            return;
        }
        const ok = this._reloadOne(Main.extensionManager, uuid);
        invocation.return_value(new GLib.Variant('(s)', [
            JSON.stringify({ok, uuid}),
        ]));
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
                    this._reloadOne(mgr, uuid);
                    steps.push(`teardown-reload ${uuid}`);
                    await sleep(stepMs);
                }
                mgr.disableExtension(uuid);
                steps.push(`disable ${uuid}`);
            } catch (e) {
                steps.push(`disable ${uuid} ERR ${e}`);
            }
            await sleep(stepMs);
        }

        // 2. Disable the staying-but-reload set so step 3 re-enables them and
        //    their enable() re-reads the (already loaded) dconf appearance.
        for (const uuid of order) {
            if (reload.has(uuid) && live.has(uuid) && target.has(uuid)) {
                try {
                    mgr.disableExtension(uuid);
                    steps.push(`reload-off ${uuid}`);
                } catch (e) {
                    steps.push(`reload-off ${uuid} ERR ${e}`);
                }
                await sleep(stepMs);
            }
        }

        // 3. Reload the base shell stylesheet *before* re-enabling the
        //    appearance extensions. loadTheme() rebuilds the global St theme
        //    from disk (default, or user-theme's named stylesheet if it's
        //    live), which CLOBBERS any panel styling an extension applied on
        //    enable. Extensions that paint the shell themselves (kiwi,
        //    light-style) must therefore enable *after* this, so their theming
        //    lands on top and survives. (Ordering bug fixed in v3: previously
        //    loadTheme ran last and wiped kiwi's panel — minimal/g-unity bar.)
        if (req.theme_reload !== false) {
            try {
                Main.loadTheme();
                steps.push('loadTheme');
            } catch (e) {
                steps.push(`loadTheme ERR ${e}`);
            }
            await sleep(stepMs);
        }

        // 4. Enable every target extension not currently live, in target order,
        //    so each applies its appearance on top of the freshly-loaded theme.
        const liveNow = this._liveUuids(mgr);
        for (const uuid of order) {
            if (liveNow.has(uuid))
                continue;
            try {
                mgr.enableExtension(uuid);
                steps.push(`enable ${uuid}`);
            } catch (e) {
                steps.push(`enable ${uuid} ERR ${e}`);
            }
            await sleep(stepMs);
        }

        logHelper(`ApplyLayout done: ${steps.join(' | ')}`);
        return JSON.stringify({ok: true, steps, error: ''});
    }
}
