#!/usr/bin/env bash
#
# patch-dash-to-panel-labels.sh — split window-title label colors by focus.
#
# Upstream dash-to-panel styles ungrouped window-title labels with only TWO
# states: minimized windows use `group-apps-label-font-color-minimized`,
# everything else (focused AND unfocused-but-visible) shares
# `group-apps-label-font-color`. That makes it impossible to have the
# BigCommunity classic light design: white label on the blue focus highlight
# with black labels for the unfocused ones sitting on the light bar.
#
# This patch redefines the semantics to match the design (and the natural
# reading of the settings): `-minimized` = minimized OR unfocused,
# `group-apps-label-font-color` = the focused window only. It also refreshes
# the title style on focus changes so the colors swap immediately.
#
# Shipped by layout-switcher and re-applied by
# zz-layout-switcher-dash-to-panel.hook on every dash-to-panel (re)install.
# Idempotent and shape-guarded: only touches the known code, never
# double-applies, no-ops if upstream restructures it.
set -euo pipefail

AI="/usr/share/gnome-shell/extensions/dash-to-panel@jderose9.github.com/appIcons.js"
[ -f "$AI" ] || exit 0

python3 - "$AI" <<'PYEOF'
import sys

ai = sys.argv[1]
s = open(ai, encoding="utf-8").read()
orig = s

MARKER = "ls-dtp-label-focus-fix"

COLOR_BLOCK = (
    "        let fontColor = this.window.minimized\n"
    "          ? SETTINGS.get_string('group-apps-label-font-color-minimized')\n"
    "          : SETTINGS.get_string('group-apps-label-font-color')\n"
)
COLOR_PATCHED = (
    "        let fontColor = // ls-dtp-label-focus-fix: unfocused == minimized\n"
    "          this.window.minimized || !this._isFocusedWindow()\n"
    "            ? SETTINGS.get_string('group-apps-label-font-color-minimized')\n"
    "            : SETTINGS.get_string('group-apps-label-font-color')\n"
)

FOCUS_BLOCK = (
    "    _onFocusAppChanged() {\n"
    "      this._displayProperIndicator()\n"
    "    }\n"
)
FOCUS_PATCHED = (
    "    _onFocusAppChanged() {\n"
    "      this._displayProperIndicator()\n"
    "      if (this._windowTitle) // ls-dtp-label-focus-fix\n"
    "        this._updateWindowTitleStyle()\n"
    "    }\n"
)

if MARKER not in s and COLOR_BLOCK in s and FOCUS_BLOCK in s:
    s = s.replace(COLOR_BLOCK, COLOR_PATCHED, 1)
    s = s.replace(FOCUS_BLOCK, FOCUS_PATCHED, 1)

if s != orig:
    open(ai, "w", encoding="utf-8").write(s)
    print("layout-switcher: applied dash-to-panel focused-label patch to %s" % ai)
elif MARKER not in s:
    print(
        "layout-switcher: WARNING dash-to-panel label patch NOT applied "
        "(upstream code changed shape) — focused/unfocused label colors "
        "will share one setting",
        file=sys.stderr,
    )
PYEOF
