#!/usr/bin/env bash
#
# patch-blur-my-shell.sh — fix the blur-my-shell "too much recursion" storm that
# pins gnome-shell at 100% CPU during a layout switch.
#
# Root cause (blur-my-shell, components/overview.js): the overview
# update_backgrounds() connects an overviewGroup::child-added handler that
# removes+re-inserts the blurred background. The insert fires child-added again,
# and with a second Overview instance present (extension churn during a layout
# switch) the two handlers ping-pong forever → "JS ERROR: too much recursion".
#
# Fix: a re-entry guard. A shared flag on the overviewGroup actor
# (_bmsReinserting) makes ANY handler bail while one is mid-insert, so the
# cascade can never recurse — works for one or many Overview instances. (A
# previous attempt only disconnected stale handlers of a single instance, which
# did not stop the cross-instance ping-pong.)
#
# Shipped by layout-switcher and re-applied by zz-layout-switcher-blur-my-shell.hook
# on every blur-my-shell (re)install. Idempotent and shape-guarded: only touches
# the known code, never double-applies, no-ops if upstream restructures/fixes it.
set -euo pipefail

OV="/usr/share/gnome-shell/extensions/blur-my-shell@aunetx/components/overview.js"
[ -f "$OV" ] || exit 0

python3 - "$OV" <<'PYEOF'
import sys

ov = sys.argv[1]
s = open(ov, encoding="utf-8").read()
orig = s

# Drop an earlier, insufficient dedupe-only patch line if it is present, so the
# patched file converges to a single clean shape.
s = s.replace(
    "        this.connections.disconnect_all_for(Main.layoutManager.overviewGroup); // ls-bms-recursion-fix\n",
    "",
)

BLOCK = (
    "            if (child !== this.overview_background_group) {\n"
    "                if (this.overview_background_group.get_parent())\n"
    "                    Main.layoutManager.overviewGroup.remove_child(this.overview_background_group);\n"
    "                Main.layoutManager.overviewGroup.insert_child_at_index(this.overview_background_group, 0);\n"
    "            }"
)
GUARDED = (
    "            if (child !== this.overview_background_group && !Main.layoutManager.overviewGroup._bmsReinserting) { // ls-bms-recursion-fix\n"
    "                Main.layoutManager.overviewGroup._bmsReinserting = true;\n"
    "                try {\n"
    "                    if (this.overview_background_group.get_parent())\n"
    "                        Main.layoutManager.overviewGroup.remove_child(this.overview_background_group);\n"
    "                    Main.layoutManager.overviewGroup.insert_child_at_index(this.overview_background_group, 0);\n"
    "                } finally {\n"
    "                    Main.layoutManager.overviewGroup._bmsReinserting = false;\n"
    "                }\n"
    "            }"
)

if "_bmsReinserting" not in s and BLOCK in s:
    s = s.replace(BLOCK, GUARDED, 1)

if s != orig:
    open(ov, "w", encoding="utf-8").write(s)
    print("layout-switcher: applied blur-my-shell re-entry guard to %s" % ov)
PYEOF
