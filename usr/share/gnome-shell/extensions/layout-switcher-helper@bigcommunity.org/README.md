# Layout Switcher Helper (GNOME Shell extension)

In-shell companion for the **Community Layout Switcher**. It performs the
*live* layout switch from **inside** GNOME Shell, driven over D-Bus by the
`layout-switcher` app.

## Why it exists

The `layout-switcher` app is an **external process**. The GNOME Shell
extensions a layout uses (`dash-to-panel`, `arcmenu`, `kiwi`, `light-style`,
`user-theme`, …) are JavaScript modules running **inside** the gnome-shell
process. From outside, the only way to switch extensions is to write
`org/gnome/shell/enabled-extensions` to dconf — which fires the Shell's
gsettings listener **asynchronously and concurrently** with the rest of the
apply. That cross-process race is what:

1. **hangs gnome-shell** on heavy transitions (e.g. `biggnome → g-unity`,
   `g-unity → classic`), and
2. **never lets appearance-owning extensions re-apply live** — they don't
   re-read their config on a dconf change, and the D-Bus `ReloadExtension`
   was **deprecated in GNOME 45+**.

No amount of external timing/ordering fixes this; it is an architectural
limit. This helper runs *inside* the Shell, so it can:

- drive enable/disable through `Main.extensionManager` directly, **sequenced
  on the Shell's own main loop** — no cross-process race, no hang;
- force appearance-owning extensions to re-read their config (disable+enable,
  or `reloadExtension`), which is impossible from outside on GNOME 45+;
- re-apply the shell stylesheet via `Main.loadTheme()` — the clean, no-flash
  replacement for the old external "OverviewActive pulse" hack; works on
  **Wayland without unsafe-mode** (that only gates the external `Eval`).

## Division of labour

| Component | Responsibility |
|---|---|
| `layout-switcher` (Python app) | UI; writes `~/.config/dconf/settings.gnome`; loads the dconf **values** of the layout (everything except `enabled-extensions`); then calls `ApplyLayout` over D-Bus. Falls back to the legacy external path if the helper isn't present. |
| **this extension** (JS, in-shell) | The critical orchestration: disable leaving extensions, enable entering ones, reload the ones that must re-theme, reload the shell stylesheet — all sequenced inside the Shell. |

## D-Bus interface

Exported on the Shell's own bus name (`org.gnome.Shell`):

- **dest:** `org.gnome.Shell`
- **path:** `/org/bigcommunity/LayoutSwitcherHelper`
- **iface:** `org.bigcommunity.LayoutSwitcherHelper`

### `Ping() → s`
Returns `{"helper":"layout-switcher","version":N}`. The app calls this to
detect whether the helper is installed/enabled and pick the in-shell path.

### `ApplyLayout(payload: s) → s`

`payload` is JSON:

| key | type | meaning |
|---|---|---|
| `enabled` | `[uuid…]` | target `enabled-extensions`, in load order |
| `reload` | `[uuid…]` | subset that must re-read appearance even if it stays enabled (disable+enable so `enable()` re-runs) |
| `theme` | `string` | user-theme stylesheet name (`""` = no shell theme) — reserved; theme is currently re-applied via `Main.loadTheme()` |
| `step_ms` | `int` | settle between steps (default `120`) |
| `theme_reload` | `bool` | call `Main.loadTheme()` at the end (default `true`) |

Returns JSON `{ "ok": bool, "steps": [string…], "error": string }` where
`steps` is the ordered log of what was done (for diagnostics).

The app is expected to have already `dconf load`ed the layout's values
(so each extension reads correct config on enable/reload) **before** calling
this.

## Manual test

```bash
# is the helper alive?
gdbus call --session --dest org.gnome.Shell \
  --object-path /org/bigcommunity/LayoutSwitcherHelper \
  --method org.bigcommunity.LayoutSwitcherHelper.Ping

# switch to a kiwi+dock layout, forcing kiwi to re-theme
gdbus call --session --dest org.gnome.Shell \
  --object-path /org/bigcommunity/LayoutSwitcherHelper \
  --method org.bigcommunity.LayoutSwitcherHelper.ApplyLayout \
  '{"enabled":["kiwi@kemma","dash-to-dock@micxgx.gmail.com"],"reload":["kiwi@kemma"],"theme":""}'
```

Logs go to the journal: `journalctl --user -f | grep layout-switcher-helper`.

## Status

**Proof of concept / under validation.** The goal of the POC is to confirm
that doing the switch in-shell (1) does **not** hang on the transitions that
hang via the external path, and (2) makes the appearance-owning extensions
re-theme live. Once validated, the app's `layout_applier` gains a thin
client that prefers this helper and the legacy external disable/enable
ordering can be retired.

## Install

Ships under `usr/share/gnome-shell/extensions/` and is installed system-wide
by the `layout-switcher` package (PKGBUILD copies `usr/`). Enable with:

```bash
gnome-extensions enable layout-switcher-helper@bigcommunity.org
```

It must be listed in `enabled-extensions` (the app/package ensures this) and,
being a pure D-Bus service with no UI, it is safe to keep enabled in every
layout.
