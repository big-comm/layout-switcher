# SPDX-License-Identifier: MIT
"""
layout_applier.py — Apply desktop layouts via dconf (live session).

Works together with ``comm-gnome-config``:

  * ``startgnome-community`` — at login, does::

        dconf reset -f /
        dconf load / < ~/.config/dconf/settings.gnome
        # Shell starts AFTER load → no race, clean state every login

  * ``dconf-sync-gnome.service`` (running ``dconf-sync-monitor-gnome``)
    — watches the live dconf and re-dumps it to ``settings.gnome``
    whenever it changes, with a 2s debounce. On comm-gnome-config
    ≥ 26.05.07 it honours the lock file at
    ``$XDG_RUNTIME_DIR/dconf-sync-gnome.lock`` and skips dumps while
    the lock is held — the mechanism we use to write settings.gnome
    atomically here without the watcher clobbering it.

Architectural reality: in runtime, gnome-shell is alive and listening
on dconf change-signals. Mass mutation (``dconf reset -f /``) fires
hundreds of Notify signals; any extension whose ``disable()`` left
orphan handlers behind crashes with ``this._settings is null``,
corrupting its state for the rest of the session (panel transparency
loss, dock blur missing, etc.). We can't fix every extension's
``disable()``, so we don't trigger those signals.

Strategy:

  * ``settings.gnome`` is the absolute source of truth — written
    atomically with the layout text, with the lock held so the watcher
    won't clobber it. Next login is guaranteed clean regardless of
    runtime quirks.
  * Live apply: surgical reset of orphan keys in
    ``/org/gnome/shell/extensions/`` (keys present in live dconf but
    absent from the target layout), then ``dconf load`` of the target.
    The surgical reset fixes layout cross-contamination — e.g. minimal
    sets ``blur-my-shell/panel/blur=false`` and biggnome doesn't mention
    that key (expecting default ``true``); without the reset, biggnome
    inherits minimal's ``false`` because ``dconf load`` is purely
    additive (it sets but never clears).
  * No global ``dconf reset -f /`` — that fires Notify on every key in
    dconf and any extension whose ``disable()`` left orphan handlers
    behind crashes with ``this._settings is null``. Scoping the reset
    to extension storage and restricting it to keys actually leaving
    keeps the signal storm small enough to not trip the orphan handlers.
  * Per-extension disable is still ordered (sorted UUID DBus calls) to
    avoid the cross-extension teardown SIGSEGV documented in
    ``_disable_extensions_in_order``.
  * No ``reload_all`` after the load — the Shell's gsettings listener
    on ``enabled-extensions`` already enables UUIDs as they appear.
    Calling ``EnableExtension`` again races with that listener and
    causes double-init.

Per-machine fixup: dash-to-panel stores some keys as a JSON dict keyed
by monitor id (``vendor-serial`` at runtime, ``unknown-unknown`` in VMs
without EDID). The layout file ships with whatever ids it was generated
under; we rewrite those keys in the text BEFORE the load so live dconf
ends up with the local hardware ids.

Flow::

  1. read layout_file, rewrite DTP monitor-keyed values to local ids
  2. read before = enabled-extensions
  3. acquire lock file
  4. stop dconf-sync-gnome.service
  5. DisableExtension via DBus per UUID, in sorted order
  6. dconf reset <key> for each orphan in /org/gnome/shell/extensions/
     (key in live dump but not in layout text)
  7. atomic write settings.gnome = layout text  (clean, no garbage)
  8. dconf load / < layout
  9. start dconf-sync-gnome.service              (watcher honours lock)
 10. release lock file

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from shell_reloader import ShellReloader
from utils import run_cmd

log = logging.getLogger("layout-switcher")

SETTINGS_GNOME = Path.home() / ".config" / "dconf" / "settings.gnome"
SYNC_SERVICE = "dconf-sync-gnome.service"

# comm-gnome-config's QT-theme path watcher fires whenever
# ~/.config/dconf/user is touched (dconf load does that). The watcher
# itself only writes to ~/.config/Kvantum/* and ~/.config/kdeglobals
# (no dconf round-trip), but ``startgnome-community`` stops it during
# its own reset+load — we mirror that for consistency and to avoid the
# extra fs activity racing with our atomic write of settings.gnome.
QT_THEME_WATCHER = "sync-gnome-theme-to-qt.path"

# Lock honoured by comm-gnome-config's dconf-sync-monitor-gnome (≥ 26.05.07):
# while present, the watcher skips its dconf→file dump, so we can
# atomically write settings.gnome without it being clobbered.
_SYNC_LOCK_PATH = Path(
    os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
) / "dconf-sync-gnome.lock"

# dash-to-panel stores some settings as JSON dicts keyed by monitor ID
# (e.g. ``"unknown-unknown"`` in VMs, ``"DEL-S2719DGF-..."`` on real
# hardware). Layout files were generated on a different machine, so the
# JSON keys won't match the local monitor IDs — dash-to-panel falls back
# to defaults briefly while it migrates the keys, producing a visible
# "default GNOME pill" at the bottom of the screen.
_DTP_BASE = "/org/gnome/shell/extensions/dash-to-panel"
_DTP_MONITOR_KEYED = (
    "panel-element-positions",
    "panel-positions",
    "panel-sizes",
    "panel-anchors",
    "panel-lengths",
)

# Paths where we're allowed to reset orphan keys (keys present in live
# dconf but absent from the target layout). Restricted to extension
# storage: that's where layout differences cause visible damage
# (e.g. minimal sets blur-my-shell/panel/blur=false; biggnome doesn't
# mention the key, expecting the default true; without a targeted
# reset, blur stays off after switching). Other paths (settings-daemon,
# notification app history, third-party apps) are off-limits — resetting
# them would lose unrelated user state.
_ORPHAN_RESET_PREFIXES = (
    "/org/gnome/shell/extensions/",
)

# Extensions that should NOT be disabled at the start of a layout switch.
#
# user-theme is special: it owns the global ``StTheme`` (Main.loadTheme).
# Other visual extensions (blur-my-shell, dash-to-dock) register their
# stylesheets on top of whatever StTheme is current at the time of their
# enable(). If we disable user-theme during the switch, StTheme reverts
# to the default GNOME theme; subsequent re-enables run against that
# default. By the time user-theme's enable() runs again and rebuilds
# StTheme, blur-my-shell's panel-class wiring has already happened
# against the wrong theme — and the rebuild doesn't re-trigger
# blur-my-shell's _set_should_override_panel(), so the panel's
# ``.transparent-panel`` class either isn't set or has no matching rule.
#
# user-theme has no setting watchers that the dconf load's Notify
# storm would crash, so it's safe to leave enabled throughout.
_NO_DISABLE = frozenset({
    "user-theme@gnome-shell-extensions.gcampax.github.com",
})


class LayoutApplier:
    """Aplica layout em sessão viva: write atômico em settings.gnome +
    best-effort dconf load. Coordena com o watcher do comm-gnome-config
    via lock file. Não usa dconf reset (perigoso com Shell rodando)."""

    # DBus DisableExtension is synchronous — the extension is fully disabled
    # when the call returns. The gap lets the GLib event loop drain any
    # pending idle callbacks queued by the extension's disable() body before
    # we move on; some extensions (blur-my-shell, dash-to-dock) need >20ms.
    _DISABLE_STEP_SEC = 0.1
    _SETTLE_SEC = 0.5  # final settle after last disable, before dconf load
    _MIN_DUMP_BYTES = 100
    _SHELL_DBUS_TIMEOUT_SEC = 2
    _MAX_DISABLE_DBUS_TIMEOUTS = 3

    # ── Helpers de infraestrutura ────────────────────────────────────────────

    # Cache for ``_has_user_unit`` results within a single apply. Each lookup
    # spawns a ``systemctl --user cat`` (~50–150 ms); the cache makes the
    # four lookups per apply (sync service + qt theme watcher, twice each)
    # collapse to two. Reset at the start of every ``load_dconf_safely``.
    _unit_cache: Dict[str, bool] = {}

    @classmethod
    def _has_user_unit(cls, unit: str) -> bool:
        """True if a systemd --user unit exists on this machine (cached)."""
        cached = cls._unit_cache.get(unit)
        if cached is not None:
            return cached
        ok, _ = run_cmd(
            ["systemctl", "--user", "cat", unit],
            timeout=5,
        )
        cls._unit_cache[unit] = ok
        return ok

    @classmethod
    def _qt_theme_watcher(cls, action: str) -> None:
        """start/stop do sync-gnome-theme-to-qt.path (silencioso se ausente).

        The QT theme path watcher fires every time ``~/.config/dconf/user``
        is modified — and our ``dconf load`` modifies it many times in
        sequence. Letting it fire repeatedly during the apply means N
        spawns of ``sync-gnome-theme-to-qt.sh`` racing against Kvantum /
        kdeglobals writes. Cheaper to stop the path watcher for the apply
        window and re-run the script once at the end.
        """
        if not cls._has_user_unit(QT_THEME_WATCHER):
            return
        run_cmd(
            ["systemctl", "--user", action, QT_THEME_WATCHER],
            timeout=10,
        )

    @staticmethod
    def _sync_lock_acquire() -> None:
        """
        Create the watcher-coordination lock file. Compatible with
        comm-gnome-config ≥ 26.05.07; older versions silently ignore
        the file (so this is a no-op for them — they'll dump the live
        dconf normally, picking up settings.gnome via the next change).
        """
        try:
            _SYNC_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            _SYNC_LOCK_PATH.write_text(f"{os.getpid()}\n")
        except OSError as exc:
            log.debug("could not create sync lock: %s", exc)

    @staticmethod
    def _sync_lock_release() -> None:
        """Remove the watcher-coordination lock. Idempotent."""
        try:
            _SYNC_LOCK_PATH.unlink(missing_ok=True)
        except OSError as exc:
            log.debug("could not remove sync lock: %s", exc)

    @staticmethod
    def _parse_target_enabled_extensions(text: str) -> Set[str]:
        """
        Extract the ``enabled-extensions`` UUID set from a dconf dump
        string (the layout text). Returns an empty set if the key isn't
        present or can't be parsed.

        Used to predict which extensions the new layout wants enabled,
        so we can decide which extensions are STAYING vs LEAVING and
        treat them differently during the switch (see
        ``_disable_extensions_in_order`` callsite).
        """
        import ast

        section = ""
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                section = "/" + stripped[1:-1].strip("/")
                continue
            if section != "/org/gnome/shell" or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            if key.strip() != "enabled-extensions":
                continue
            try:
                lst = ast.literal_eval(value.strip())
            except (ValueError, SyntaxError):
                return set()
            return {u for u in lst if isinstance(u, str) and u}
        return set()

    @staticmethod
    def _parse_dconf_dump_paths(text: str) -> Set[str]:
        """
        Parse a dconf dump and return the set of full key paths it contains.

        Format::

            [section/path]
            key1=value1
            key2=value2

        A line ``key=value`` under section ``[a/b]`` produces ``/a/b/key``.
        Blank lines and lines without ``=`` (other than section headers)
        are ignored.
        """
        paths: Set[str] = set()
        section = ""
        for raw in text.splitlines():
            line = raw.rstrip("\r")
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                section = "/" + stripped[1:-1].strip("/")
                continue
            if "=" not in line:
                continue
            key, _, _value = line.partition("=")
            key = key.strip()
            if not key or not section:
                continue
            paths.add(f"{section}/{key}")
        return paths

    @classmethod
    def _reset_orphan_keys(cls, target_text: str) -> int:
        """
        Reset keys present in live dconf but absent from ``target_text``,
        restricted to ``_ORPHAN_RESET_PREFIXES`` (extension storage only).

        Why this exists: ``dconf load`` is purely additive — it sets the
        keys in its input but never clears keys that aren't there. So if
        the previous layout (e.g. minimal) set
        ``blur-my-shell/panel/blur=false`` and the new layout (biggnome)
        doesn't mention that key (expecting the default ``true``), the
        loaded biggnome inherits minimal's ``false`` and the panel blur
        stays off.

        Restricting to ``/org/gnome/shell/extensions/`` keeps the signal
        storm small (and skips paths where reset would lose unrelated user
        state — settings-daemon caches, notification app history, etc.).
        Extensions are already disabled when this runs, so the Notify
        signals fire mostly into dead code.

        Returns the number of keys reset.
        """
        ok, dump = run_cmd(["dconf", "dump", "/"], timeout=15)
        if not ok or not dump:
            return 0
        live_paths = cls._parse_dconf_dump_paths(dump)
        target_paths = cls._parse_dconf_dump_paths(target_text)
        orphans = {
            p
            for p in (live_paths - target_paths)
            if any(p.startswith(pre) for pre in _ORPHAN_RESET_PREFIXES)
        }
        if not orphans:
            return 0

        # Group by extension subdir (/org/gnome/shell/extensions/<uuid>/).
        # When every live key under a subdir is orphan (extension fully
        # leaving the layout), one ``dconf reset -f <subdir>`` clears the
        # whole branch in a single dconf call — orders of magnitude faster
        # than per-key for hybrid → biggnome (arcmenu, dash-to-panel, pano,
        # gtk4-ding can each contribute hundreds of keys). Extensions still
        # present in the target layout fall back to per-key reset so
        # surviving keys stay untouched.
        ext_base = "/org/gnome/shell/extensions/"

        def ext_subdir(path: str) -> Optional[str]:
            if not path.startswith(ext_base):
                return None
            rest = path[len(ext_base):]
            slash = rest.find("/")
            if slash < 0:
                return None
            return ext_base + rest[:slash] + "/"

        live_by_subdir: Dict[str, Set[str]] = {}
        for p in live_paths:
            sd = ext_subdir(p)
            if sd:
                live_by_subdir.setdefault(sd, set()).add(p)
        orphan_by_subdir: Dict[str, Set[str]] = {}
        for p in orphans:
            sd = ext_subdir(p)
            if sd:
                orphan_by_subdir.setdefault(sd, set()).add(p)

        n = 0
        handled: Set[str] = set()
        for sd, orph_keys in orphan_by_subdir.items():
            if orph_keys == live_by_subdir.get(sd, set()):
                ok2, _msg = run_cmd(["dconf", "reset", "-f", sd], timeout=10)
                if ok2:
                    n += len(orph_keys)
                    handled.update(orph_keys)

        for path in sorted(orphans - handled):
            ok2, _msg = run_cmd(["dconf", "reset", path], timeout=5)
            if ok2:
                n += 1
        if n:
            log.info("reset %d orphan key(s) before load", n)
        return n

    # Extensions that own visual state (CSS, panel actors, theme
    # references) and don't recover it cleanly from a plain
    # Disable→Enable cycle. We ReloadExtension these after the dconf
    # load so they re-init their JS module from scratch — same effect
    # as a logout, but per-extension. Other UUIDs (gsconnect, pamac,
    # appindicators, etc.) restore fine via Shell's auto-enable path.
    #
    # ``user-theme`` is intentionally NOT here: it stays enabled
    # throughout (see ``_NO_DISABLE``) so the global ``StTheme`` never
    # reverts to default mid-switch, and other extensions register
    # their stylesheets on top of the live Big-Blue theme.
    _RELOAD_AFTER_LOAD = (
        "blur-my-shell@aunetx",
        "dash-to-dock@micxgx.gmail.com",
        "dash-to-panel@jderose9.github.com",
        "big-shot@bigcommunity.org",
    )

    @classmethod
    def _reload_visual_extensions(cls, uuids: Iterable[str]) -> None:
        """
        Call ReloadExtension via DBus for visually-stateful UUIDs.

        Only acts on UUIDs in the intersection of ``uuids`` and
        ``_RELOAD_AFTER_LOAD``, preserving the order declared in
        ``_RELOAD_AFTER_LOAD`` (NOT alphabetical). Sleeps briefly between
        reloads so each extension's enable() body finishes before the
        next reload starts (same rationale as ``_DISABLE_STEP_SEC``).
        """
        present = {u for u in uuids if u}
        for uuid in cls._RELOAD_AFTER_LOAD:
            if uuid not in present:
                continue
            ok = ShellReloader.reload_extension(
                uuid,
                timeout=cls._SHELL_DBUS_TIMEOUT_SEC,
            )
            if not ok:
                log.warning("ReloadExtension failed or timed out for %s", uuid)
                continue
            time.sleep(cls._DISABLE_STEP_SEC)

    @classmethod
    def _disable_extensions_in_order(cls, uuids: Iterable[str]) -> bool:
        """
        Disable each extension via DBus, in sorted UUID order, with a
        small delay between calls.

        We do NOT use ``gsettings set ... disable-user-extensions=true``
        for this because that triggers an async cascade where the Shell
        disables extensions in implementation-defined (non-deterministic)
        order and runs them concurrently. That race caused gnome-shell
        SIGSEGV on real layout transitions: ``copyous`` ``disable()``
        called ``theme.destroy()``, which fired a signal handler bound
        inside dash-to-panel's ``enable()``; the handler then read
        ``Me.settings.get_string()`` on dash-to-panel — but DTP had
        already been torn down, so ``Me.settings`` was null. JS errors
        cascaded into disposed-object accesses and the Shell crashed
        back to GDM.

        Sorted UUIDs put ``copyous@…`` before ``dash-to-panel@…``
        (``c`` < ``d``), so cross-extension callbacks during ``copyous``'s
        teardown still see a live DTP. The 0.1s gap lets each extension's
        ``disable()`` body run to completion before the next one starts.

        Returns False if the Shell DBus path timed out repeatedly and
        the caller should skip further extension DBus work in this apply.
        """
        timeout_count = 0
        for uuid in sorted({u for u in uuids if u and u not in _NO_DISABLE}):
            ok, msg = ShellReloader.enable_extension_dbus(
                uuid,
                enable=False,
                timeout=cls._SHELL_DBUS_TIMEOUT_SEC,
            )
            if ok:
                timeout_count = 0
                time.sleep(cls._DISABLE_STEP_SEC)
                continue

            log.warning("DisableExtension failed for %s: %s", uuid, msg)
            if "timed out" not in (msg or "").lower():
                continue

            timeout_count += 1
            if timeout_count >= cls._MAX_DISABLE_DBUS_TIMEOUTS:
                log.warning(
                    "aborting extension disable phase after %d DBus timeouts",
                    timeout_count,
                )
                return False
        return True

    @classmethod
    def _persist_to_settings_file(cls, data: str) -> Tuple[bool, str]:
        """
        Atomically write ``data`` (the layout text) to
        ``~/.config/dconf/settings.gnome``.

        The layout file is the single source of truth for the desktop
        state, so the persisted file is a verbatim copy of it (with DTP
        monitor keys already rewritten to local IDs by the caller).
        Atomic via ``.tmp`` + rename, with a ``.bak`` of the previous
        version, mirroring ``dconf-sync-monitor-gnome``'s behaviour.
        """
        if not data or len(data) < cls._MIN_DUMP_BYTES:
            return False, "layout text is empty/tiny"

        try:
            SETTINGS_GNOME.parent.mkdir(parents=True, exist_ok=True)
            tmp = SETTINGS_GNOME.parent / (SETTINGS_GNOME.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            if SETTINGS_GNOME.exists() and SETTINGS_GNOME.stat().st_size > 0:
                bak = SETTINGS_GNOME.parent / (SETTINGS_GNOME.name + ".bak")
                try:
                    bak.write_bytes(SETTINGS_GNOME.read_bytes())
                except Exception as exc:
                    log.debug("could not create .bak: %s", exc)
            tmp.replace(SETTINGS_GNOME)
            try:
                dir_fd = os.open(str(SETTINGS_GNOME.parent), os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError as exc:
                log.debug("dir fsync skipped: %s", exc)
            return True, str(SETTINGS_GNOME)
        except Exception as exc:
            return False, f"write failed: {exc}"

    @staticmethod
    def _enabled_extensions() -> List[str]:
        """Lê ``/org/gnome/shell/enabled-extensions`` como lista de UUIDs."""
        ok, raw = run_cmd(["dconf", "read", "/org/gnome/shell/enabled-extensions"], timeout=5)
        if not ok or not raw:
            return []
        # dconf returns a GVariant string like ['uuid@a', 'uuid@b']
        try:
            import ast

            val = ast.literal_eval(raw)
            return [u for u in val if isinstance(u, str) and u]
        except (ValueError, SyntaxError) as exc:
            log.debug("parse enabled-extensions failed: %s -> %s", raw, exc)
            return []

    @staticmethod
    def _parse_dtp_json(raw: str) -> dict:
        """
        Parse dash-to-panel's monitor-keyed JSON-string dconf value.
        Returns ``{}`` on failure. The dconf wire format is
        ``'{"key":...}'`` (single-quoted GVariant string with JSON inside).
        """
        if not raw:
            return {}
        s = raw.strip()
        # Strip GVariant single-quote wrapping
        if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
            s = s[1:-1]
        try:
            d = json.loads(s)
        except json.JSONDecodeError:
            return {}
        return d if isinstance(d, dict) else {}

    @classmethod
    def _read_dtp_monitor_keys(cls) -> Set[str]:
        """
        Discover the local machine's dash-to-panel monitor IDs.

        Strategy: query mutter via DBus for the real (vendor, serial) of
        each connected monitor and reconstruct the id the same way DTP does
        (``f"{vendor}-{serial}"`` when both present, else the connector name,
        else the numeric index). Falls back to reading existing dconf keys
        if mutter is unreachable — but mutter is the source of truth, since
        dconf may carry stale ``unknown-unknown`` entries from a previous
        layout generated on a VM with no EDID, which won't match the actual
        identifier DTP computes at runtime.

        Must be called *before* the ``dconf load``, since the rewrite
        is what makes the loaded data carry local-machine IDs.
        """
        keys = cls._read_dtp_monitor_ids_from_mutter()
        if keys:
            return keys
        # Fallback to whatever dconf already has.
        keys = set()
        for k in _DTP_MONITOR_KEYED:
            ok, raw = run_cmd(["dconf", "read", f"{_DTP_BASE}/{k}"], timeout=5)
            if not ok:
                continue
            d = cls._parse_dtp_json(raw)
            keys.update(d.keys())
        return keys

    @classmethod
    def _read_dtp_monitor_ids_from_mutter(cls) -> Set[str]:
        """
        Ask org.gnome.Mutter.DisplayConfig.GetCurrentState for the connected
        monitors and reconstruct the dash-to-panel monitor id format.

        DTP source (panelSettings.js): ``id = vendor && serial ? f"{vendor}-{serial}"
        : connector || index``. We replicate that logic here so the keys we
        write to dconf match exactly what DTP will look up at runtime.
        """
        ok, raw = run_cmd(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.gnome.Mutter.DisplayConfig",
                "--object-path",
                "/org/gnome/Mutter/DisplayConfig",
                "--method",
                "org.gnome.Mutter.DisplayConfig.GetCurrentState",
            ],
            timeout=cls._SHELL_DBUS_TIMEOUT_SEC,
        )
        if not ok or not raw:
            return set()
        # Each physical monitor appears as a 4-tuple
        # ('connector', 'vendor', 'product', 'serial') inside the GVariant.
        import re

        ids: Set[str] = set()
        pattern = re.compile(r"\('([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\)")
        for idx, match in enumerate(pattern.finditer(raw)):
            connector, vendor, _product, serial = match.groups()
            if vendor and serial:
                ids.add(f"{vendor}-{serial}")
            elif connector:
                ids.add(connector)
            else:
                ids.add(str(idx))
        return ids

    @classmethod
    def _rewrite_dtp_keys_in_text(cls, text: str, local_keys: Set[str]) -> str:
        """
        Rewrite dash-to-panel monitor-keyed values in a dconf dump string so
        the JSON keys match the local machine's monitor IDs.

        Layout files are typically generated on a different machine — they
        ship with foreign monitor IDs (or ``unknown-unknown`` in VMs). At
        login, DTP looks up its config by the runtime-computed local id
        (``vendor-serial`` per panelSettings.js) and falls back to vanilla
        defaults when nothing matches — that fallback is what causes the
        visible flash on the way to the desktop. Pre-rewriting the layout
        text fixes the file we persist AND the data we feed to dconf load,
        so both sides see the right keys without any post-load patching.
        """
        if not local_keys:
            return text
        out_lines: List[str] = []
        for line in text.splitlines():
            if "=" not in line:
                out_lines.append(line)
                continue
            key, _, value = line.partition("=")
            if key.strip() not in _DTP_MONITOR_KEYED:
                out_lines.append(line)
                continue
            d = cls._parse_dtp_json(value.strip())
            if not d:
                out_lines.append(line)
                continue
            if set(d.keys()) == local_keys:
                out_lines.append(line)
                continue
            source = next(iter(d.values()))
            new_d = {lk: source for lk in local_keys}
            new_json = json.dumps(new_d, separators=(",", ":"))
            escaped = new_json.replace("\\", "\\\\").replace("'", "\\'")
            out_lines.append(f"{key}='{escaped}'")
        # Preserve trailing newline if the input had one.
        joined = "\n".join(out_lines)
        if text.endswith("\n") and not joined.endswith("\n"):
            joined += "\n"
        return joined

    # ── API publica ──────────────────────────────────────────────────────────

    @classmethod
    def load_dconf_safely(
        cls,
        data: str,
        persist: bool = True,
        before_uuids: Optional[Iterable[str]] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """
        Apply ``data`` (a full dconf dump) to live dconf, and atomically
        write it to ``settings.gnome`` so the next login is clean.

        Flow:
          1. acquire lock                       (watcher won't dump)
          2. stop sync-gnome-theme-to-qt.path    (avoid re-fires
             during the dconf load's burst of writes)
          3. disable ``before_uuids`` via DBus   (sorted, see
             ``_disable_extensions_in_order``)
          4. settle so disable() callbacks drain
          5. surgical reset of orphan extension keys (see
             ``_reset_orphan_keys``)
          6. atomic write settings.gnome = data  (clean, no garbage)
          7. dconf load < data
          8. ReloadExtension on visually-stateful UUIDs (see
             ``_reload_visual_extensions``) — fresh JS module init so
             CSS/actor state matches the new dconf values
          9. start sync-gnome-theme-to-qt.path
         10. release lock

        Why no ``systemctl stop dconf-sync-gnome.service``: comm-gnome-config's
        watcher honours the lock file we hold throughout this method
        (``$XDG_RUNTIME_DIR/dconf-sync-gnome.lock``). With the lock held
        it skips its dump-on-change, which is the only thing that could
        clobber our atomic write of ``settings.gnome``. Stopping the
        service was extra ceremony (≈200 ms of synchronous systemctl
        round-trips) that the lock already prevents — so we drop it
        entirely. Live dconf changes still flow through the watcher's
        ``dconf watch /`` pipe; the watcher just logs them and short-
        circuits the save under the lock.

        Why no global ``dconf reset -f /`` in runtime: with gnome-shell
        alive, the reset fires Notify on every key in dconf. Extensions
        whose ``disable()`` left orphan signal handlers behind crash
        with ``this._settings is null`` and stay broken for the rest of
        the session. The surgical orphan-only reset above keeps the
        Notify storm small (only keys actually leaving fire) and scoped
        to extension storage (no risk to user data elsewhere).

        Why no ``reload_all`` after the load: ``dconf load`` writes
        ``enabled-extensions``, which fires the Shell's gsettings listener
        and enables each UUID. Calling ``EnableExtension`` again races
        with that listener and double-inits the extension.

        ``persist=False`` skips the settings.gnome write — used by callers
        that already wrote it themselves (e.g. snapshots).

        ``progress_cb`` (if provided) is called with a short stage label
        (str) before each visible phase so the caller can update its
        loading overlay. Best-effort: any exception from the callback is
        swallowed so it never breaks the apply.
        """
        if not data or not data.strip():
            return False, "empty dconf data"

        cls._unit_cache = {}

        def progress(label: str) -> None:
            if progress_cb is None:
                return
            try:
                progress_cb(label)
            except Exception as exc:
                log.debug("progress_cb raised: %s", exc)

        cls._sync_lock_acquire()
        try:
            cls._qt_theme_watcher("stop")

            # Disable extensions in two phases: LEAVING (in before but not
            # target) first, then STAYING (in both). Why two phases:
            #
            # Shell's ``_callExtensionDisable`` performs a "rebase" — it
            # disables every extension loaded *after* the target in
            # ``_extensionOrder``, then re-enables them. So when we
            # disable extension X, every later extension Y goes through
            # a stateObj.disable()+stateObj.enable() cycle, even if Y is
            # also about to be disabled. After our DBus call returns,
            # Shell splices X out of ``_extensionOrder`` — Y's later
            # disable then has fewer (or no) post-X extensions to rebase.
            #
            # Why LEAVING first: extensions like arcmenu hold static
            # singletons that survive a re-enable, and don't tolerate
            # being disabled twice. If a STAYING extension's rebase
            # touches arcmenu mid-switch, arcmenu's enable() rebuilds
            # its singleton; then the dconf load's listener cascade
            # disables arcmenu *again*, which throws (and once the
            # singleton is left set without a successful enable, both
            # enable and disable throw forever — visible as the loop
            # of "ArcMenu has been already initialized" /
            # "_updateNotification is undefined" errors). Disabling
            # LEAVING first puts arcmenu through one clean cycle while
            # everything else is still healthy, then splices it out of
            # ``_extensionOrder`` so no later rebase can touch it.
            #
            # Why STAYING is still pre-disabled: their keys are about
            # to be mutated by the orphan reset and the dconf load, and
            # live handlers reacting to the Notify storm have caused
            # ``this._settings is null`` cascades.
            target_enabled = cls._parse_target_enabled_extensions(data)
            before_set = {u for u in (before_uuids or ()) if u}
            leaving = before_set - target_enabled
            staying = before_set & target_enabled
            if leaving or staying:
                progress("Disabling extensions…")
            shell_dbus_available = True
            if leaving:
                shell_dbus_available = cls._disable_extensions_in_order(leaving)
                time.sleep(cls._DISABLE_STEP_SEC)
            if staying and shell_dbus_available:
                shell_dbus_available = cls._disable_extensions_in_order(staying)
                # Let last extension's disable() body finish before
                # we change the keys it was bound to.
                time.sleep(cls._SETTLE_SEC)
            elif staying:
                log.warning("skipping remaining extension disables after DBus timeouts")

            progress("Loading layout…")
            # Clear keys from the previous layout that the new layout
            # doesn't cover (scoped to extension storage). Done after
            # disabling extensions so most Notify signals fire into
            # dead code, before the load so target wins everywhere.
            cls._reset_orphan_keys(data)

            if persist:
                ok_persist, info = cls._persist_to_settings_file(data)
                if not ok_persist:
                    log.warning("could not persist settings.gnome: %s", info)

            ok, msg = run_cmd(
                ["dconf", "load", "/"],
                stdin_text=data,
                timeout=20,
            )
            if not ok:
                log.warning("dconf load failed: %s", msg)
                return False, f"dconf load failed: {msg}"

            # Force fresh JS module init for visually-stateful extensions.
            # Disable→Enable alone reuses the extension's JS module and
            # leaves stale CSS references (e.g. user-theme keeps the
            # previous shell-theme CSS partly applied; panel transparency
            # from Big-Blue.css doesn't take effect until logout).
            # ReloadExtension does disable + drop module + load fresh +
            # enable, which is what logout would do — but per-extension,
            # without restarting gnome-shell.
            #
            # Only ``after``: extensions present in ``before`` but not
            # ``after`` are LEAVING the layout — they were disabled by
            # ``_disable_extensions_in_order`` and the gsettings listener
            # confirmed it when ``dconf load`` rewrote enabled-extensions.
            # Calling ``ReloadExtension`` on a leaving extension re-enables
            # it (Reload = disable+drop+load+enable), which re-creates its
            # actors. That's how the dash-to-panel bottom bar leaks into
            # g-unity after a desk-ux→g-unity switch: DTP gets disabled
            # cleanly, then Reload brings it back as a ghost actor.
            # Extensions that "stay enabled across the switch" (user-theme,
            # big-shot) live in ``before ∩ after`` — already covered by
            # ``after`` alone, no union needed.
            after_uuids = cls._enabled_extensions()
            if after_uuids and shell_dbus_available:
                progress("Reloading components…")
                cls._reload_visual_extensions(after_uuids)
            elif after_uuids:
                log.warning("skipping visual extension reloads after DBus timeouts")

            # Note: we previously toggled ``org.gnome.Shell.OverviewActive``
            # true→false here to force a CSS style recompute on Main.panel
            # (Big-Blue.css's transparent ``#panel`` rule wasn't repainting).
            # That trick worked but flashed the Activities Overview for ~0.4 s,
            # which read to users as a "freeze" — especially layered on top
            # of the extension reloads that had just finished. The "Restart
            # the session for the 100% clean state" toast in page_layouts.py
            # already covers the residual case: settings.gnome is written
            # cleanly, so the next login renders transparency correctly.

            return True, msg
        finally:
            cls._qt_theme_watcher("start")
            cls._sync_lock_release()

    @classmethod
    def apply(
        cls,
        config_path: Path,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str]:
        """
        Apply a layout file as the complete next-login dconf state, and
        best-effort apply to the live session.

        ``settings.gnome`` becomes a verbatim copy of the layout file
        (after DTP monitor-id rewriting). The live session also gets
        the layout via ``dconf load``; any leftover keys from the
        previous layout that aren't in this one persist in live dconf
        until the next login (harmless — see ``load_dconf_safely``).

        ``progress_cb`` is forwarded to ``load_dconf_safely`` so the
        caller can update its loading overlay between stages.
        """
        if not config_path or not config_path.exists():
            return False, f"layout file not found: {config_path}"
        try:
            layout_text = config_path.read_text(encoding="utf-8")
        except Exception as exc:
            return False, f"cannot read layout file: {exc}"
        if not layout_text.strip():
            return False, "layout file is empty"

        local_dtp_monitors = cls._read_dtp_monitor_keys()
        layout_text = cls._rewrite_dtp_keys_in_text(layout_text, local_dtp_monitors)

        before = cls._enabled_extensions()
        return cls.load_dconf_safely(
            layout_text,
            persist=True,
            before_uuids=before,
            progress_cb=progress_cb,
        )
