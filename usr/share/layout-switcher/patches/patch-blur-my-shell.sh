#!/usr/bin/env bash
#
# patch-blur-my-shell.sh — fix the blur-my-shell "too much recursion" storm that
# pins gnome-shell at 100% CPU during a layout switch.
#
# Root cause (blur-my-shell, components/overview.js):
#   update_backgrounds() connects a fresh `overviewGroup::child-added` handler on
#   EVERY call and never drops the previous one — its connection manager
#   (conveniences/connections.js) always pushes, never dedupes. The handler
#   removes+re-inserts the blurred background whenever any child enters the
#   overview, so the piled-up handlers cascade into
#   `JS ERROR: too much recursion`. A layout switch (extensions toggling, overview
#   churn) triggers it reliably. With a single handler there is no recursion, so
#   disconnecting the stale ones before reconnecting fixes it.
#
# This patch is shipped by layout-switcher and re-applied by the pacman hook
# zz-layout-switcher-blur-my-shell.hook whenever blur-my-shell is (re)installed.
# It is idempotent and shape-guarded: it only touches the known-vulnerable code,
# never double-applies, and no-ops cleanly if upstream restructures or fixes it.
set -euo pipefail

OV="/usr/share/gnome-shell/extensions/blur-my-shell@aunetx/components/overview.js"
MARK="ls-bms-recursion-fix"

# Nothing to do if the extension isn't installed.
[ -f "$OV" ] || exit 0

# Already patched.
if grep -q "$MARK" "$OV"; then
    exit 0
fi

# Only patch the known-vulnerable shape. If upstream removed the leaking
# child-added connect or renamed update_backgrounds(), leave the file alone.
if ! grep -q 'overviewGroup, "child-added"' "$OV"; then
    exit 0
fi
if ! grep -qE '^[[:space:]]*update_backgrounds\(\)[[:space:]]*\{[[:space:]]*$' "$OV"; then
    exit 0
fi

# Insert the disconnect as the first statement of update_backgrounds(), keeping
# the captured indentation (+4 spaces for the method body).
sed -i -E \
    's#^([[:space:]]*)update_backgrounds\(\)[[:space:]]*\{[[:space:]]*$#\1update_backgrounds() {\n\1    this.connections.disconnect_all_for(Main.layoutManager.overviewGroup); // '"$MARK"'#' \
    "$OV"

if grep -q "$MARK" "$OV"; then
    echo "layout-switcher: applied blur-my-shell recursion fix to ${OV}"
else
    echo "layout-switcher: WARNING - could not apply blur-my-shell recursion fix" >&2
fi
