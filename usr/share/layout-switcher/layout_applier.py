# SPDX-License-Identifier: MIT
"""
layout_applier.py — Aplica layouts de desktop via dconf (sessao ativa).

Trabalha em conjunto com ``startgnome-community`` (do pacote
``comm-gnome-config``), que no login faz::

  1. ``dconf reset -f /``
  2. ``dconf load / < ~/.config/dconf/settings.gnome``

Portanto, o estado de inicializacao da sessao depende inteiramente do
conteudo de ``settings.gnome``. Se uma chave nao esta nesse arquivo, ela
volta ao default do GNOME no proximo login (gtk-theme volta para Adwaita,
user-theme some, etc.) — visivel como "flash" do GNOME vanilla.

Os layout files do switcher NAO sao dumps completos do dconf: eles sao
recortes focados em extensoes do dock, topbar, app-picker e similares.
Chaves de tema (interface, user-theme), fontes e configuracoes pessoais
nao aparecem porque sao prerrogativa do usuario / do skel do
``comm-gnome-config``.

ANTIGO (errado): ``apply()`` fazia ``dconf reset -f /`` + ``dconf load
layout_file`` + ``dconf dump > settings.gnome``. O reset destruia chaves
preservadas pelo skel; o dump capturava o estado mutilado e gravava em
settings.gnome — corrompendo o arquivo que o ``startgnome-community``
usaria nos proximos logins.

NOVO: ``apply()`` faz MERGE per-key entre o ``settings.gnome`` atual e o
layout file. Chaves do layout sobrescrevem chaves correspondentes; chaves
exclusivas do settings (tema, fontes, etc.) sao preservadas. O merge
resultante e que vai para ``dconf load`` e para ``settings.gnome``.

Fluxo atomico::

  1. ler settings.gnome (estado completo atual)
  2. ler layout_file (recorte do layout)
  3. merge per-key: layout vence chaves comuns; settings preserva o resto
  4. stop dconf-sync-gnome.service
  5. gsettings disable-user-extensions=true (pausa shell de reagir)
  6. dconf reset -f /        (zera dconf user db)
  7. dconf load /            (carrega o MERGE — completo, com tema)
  8. dconf dump / > settings.gnome   (persiste merge para proximo login)
  9. gsettings disable-user-extensions=false
  10. start dconf-sync-gnome.service
  11. ShellReloader.reload_all()

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

from shell_reloader import ShellReloader
from utils import run_cmd

log = logging.getLogger("layout-switcher")

SETTINGS_GNOME = Path.home() / ".config" / "dconf" / "settings.gnome"
SYNC_SERVICE = "dconf-sync-gnome.service"

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


class LayoutApplier:
    """Aplica layout com reset+load, protegendo extensoes e monitor de sync."""

    _SETTLE_SEC = 0.5  # time for Shell to process disable-user-extensions
    _MIN_DUMP_BYTES = 100

    # ── Helpers de infraestrutura ────────────────────────────────────────────

    @staticmethod
    def _has_sync_service() -> bool:
        """True se o servico dconf-sync-gnome do comm-gnome-config existe."""
        ok, _ = run_cmd(
            ["systemctl", "--user", "cat", SYNC_SERVICE],
            timeout=5,
        )
        return ok

    @classmethod
    def _sync_service(cls, action: str) -> None:
        """start/stop do dconf-sync-gnome (silencioso se ausente)."""
        if not cls._has_sync_service():
            return
        run_cmd(
            ["systemctl", "--user", action, SYNC_SERVICE],
            timeout=10,
        )

    @staticmethod
    def _pause_extensions(pause: bool) -> None:
        """Liga/desliga todas as extensoes de usuario via gsettings."""
        run_cmd(
            [
                "gsettings",
                "set",
                "org.gnome.shell",
                "disable-user-extensions",
                "true" if pause else "false",
            ],
            timeout=5,
        )

    @classmethod
    def _persist_to_settings_file(cls) -> Tuple[bool, str]:
        """
        Grava ``dconf dump /`` em ``~/.config/dconf/settings.gnome`` de forma
        atomica (``.tmp`` -> rename, com ``.bak`` do anterior), reproduzindo
        o comportamento do ``dconf-sync-monitor-gnome``.
        """
        ok, data = run_cmd(["dconf", "dump", "/"], timeout=15)
        if not ok:
            return False, f"dconf dump failed: {data}"
        if not data or len(data) < cls._MIN_DUMP_BYTES:
            return False, "dconf dump produced empty/tiny output"

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
            # fsync the directory so the rename itself reaches disk —
            # mirrors the behaviour of dconf-sync-stop-gnome (sync FILE).
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

    # ── Parse / merge de dumps dconf ─────────────────────────────────────────

    @staticmethod
    def _parse_dconf_dump(text: str) -> Dict[str, Dict[str, str]]:
        """
        Parse a ``dconf dump`` output into ``{section: {key: value}}``.

        Format produced by ``dconf dump /`` is::

            [section/path]
            key=value
            another=value

            [other/section]
            ...

        Values are kept as raw GVariant strings (unparsed). Blank lines
        and lines that don't match section/key=value are ignored.
        """
        sections: Dict[str, Dict[str, str]] = {}
        current: str = ""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                current = stripped[1:-1]
                sections.setdefault(current, {})
                continue
            if "=" in stripped and current:
                key, value = stripped.split("=", 1)
                sections[current][key.strip()] = value.strip()
        return sections

    @staticmethod
    def _serialize_dconf_dump(sections: Dict[str, Dict[str, str]]) -> str:
        """Render ``{section: {key: value}}`` back to dconf dump format."""
        chunks: List[str] = []
        for section in sorted(sections):
            keys = sections[section]
            if not keys:
                continue
            chunks.append(f"[{section}]")
            for key in sorted(keys):
                chunks.append(f"{key}={keys[key]}")
            chunks.append("")
        return "\n".join(chunks).rstrip() + "\n"

    @classmethod
    def _merge_layout_into_settings(cls, layout_text: str, settings_text: str) -> str:
        """
        Merge per-key: layout overrides settings on shared keys; keys
        present only in settings (tema, fontes, configs pessoais) are
        preserved; keys present only in the layout are added.

        Returns the merged dump as a string ready for ``dconf load /``.
        """
        layout_sections = cls._parse_dconf_dump(layout_text)
        settings_sections = cls._parse_dconf_dump(settings_text) if settings_text else {}
        merged: Dict[str, Dict[str, str]] = {
            section: dict(keys) for section, keys in settings_sections.items()
        }
        for section, keys in layout_sections.items():
            merged.setdefault(section, {})
            merged[section].update(keys)
        return cls._serialize_dconf_dump(merged)

    @classmethod
    def _load_current_settings_text(cls) -> str:
        """Read ``~/.config/dconf/settings.gnome`` if present, else ``""``."""
        if not SETTINGS_GNOME.exists():
            return ""
        try:
            return SETTINGS_GNOME.read_text(encoding="utf-8")
        except OSError as exc:
            log.debug("failed to read settings.gnome: %s", exc)
            return ""

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

        Must be called *before* ``dconf reset -f /``, since the reset
        wipes the dconf fallback values.
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

    @staticmethod
    def _read_dtp_monitor_ids_from_mutter() -> Set[str]:
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
            timeout=5,
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
    def _migrate_dtp_keys_for_local_monitors(cls, local_keys: Set[str]) -> None:
        """
        After ``dconf load`` has applied the layout (which carries dash-to-panel
        JSON keys from whatever machine generated the file), rewrite each
        monitor-keyed value so the JSON keys match the local machine's monitor
        IDs. Replicates the layout's value across all known local IDs.

        Without this, on next login dash-to-panel briefly renders defaults
        (centered "pill" at the bottom of the screen) while it migrates the
        layout's foreign keys to the local ones — visible as a 1s flash.
        """
        if not local_keys:
            return
        for k in _DTP_MONITOR_KEYED:
            path = f"{_DTP_BASE}/{k}"
            ok, raw = run_cmd(["dconf", "read", path], timeout=5)
            if not ok:
                continue
            d = cls._parse_dtp_json(raw)
            if not d:
                continue
            if set(d.keys()) == local_keys:
                continue
            # Use the first JSON value as the canonical layout intent and
            # replicate it under each local monitor ID.
            source = next(iter(d.values()))
            new_d = {lk: source for lk in local_keys}
            new_json = json.dumps(new_d, separators=(",", ":"))
            # GVariant string syntax: single-quoted, backslash-escape backslash
            # and single quote (JSON itself uses double quotes, no escape needed).
            escaped = new_json.replace("\\", "\\\\").replace("'", "\\'")
            run_cmd(["dconf", "write", path, f"'{escaped}'"], timeout=5)

    # ── API publica ──────────────────────────────────────────────────────────

    @classmethod
    def load_dconf_safely(
        cls,
        data: str,
        persist: bool = True,
        dtp_local_monitors: Set[str] = None,
    ) -> Tuple[bool, str]:
        """
        Aplica um dump dconf em ``/`` usando reset+load (REPLACE, nao MERGE),
        com orquestracao completa: para o monitor, pausa extensoes, reseta,
        carrega, persiste no settings.gnome e restaura tudo no fim.

        Shared entre ``apply()`` (layout) e ``BackupManager.restore()``.
        Nao chama ``ShellReloader.reload_all()`` — cabe ao chamador.

        Se ``dtp_local_monitors`` for informado, reescreve as chaves
        monitor-keyed do dash-to-panel logo após o load para usar os IDs
        do hardware local — evita o flash da pill no próximo login.

        Retorna (True, "") em sucesso ou (False, mensagem_erro).
        """
        if not data or not data.strip():
            return False, "empty dconf data"

        # 1. Stop the sync monitor so it does not capture intermediate states.
        cls._sync_service("stop")

        # 2. Pause extensions BEFORE any dconf change — otherwise they react
        #    to reset signals with empty schemas and go into an error state.
        cls._pause_extensions(pause=True)
        time.sleep(cls._SETTLE_SEC)

        ok = False
        msg = ""
        try:
            # 3. Full reset so the following load behaves as a REPLACE.
            ok_reset, reset_msg = run_cmd(
                ["dconf", "reset", "-f", "/"],
                timeout=10,
            )
            if not ok_reset:
                return False, f"dconf reset failed: {reset_msg}"

            # 4. Load the new state. The data already carries
            #    disable-user-extensions=false (or omits it) — the Shell will
            #    re-enable extensions once the state is complete.
            ok, msg = run_cmd(
                ["dconf", "load", "/"],
                stdin_text=data,
                timeout=20,
            )
            if not ok:
                log.warning("dconf load failed: %s", msg)
                return False, f"dconf load failed: {msg}"

            # 4b. Rewrite dash-to-panel monitor-keyed keys to use local
            #     monitor IDs (BEFORE persist, so settings.gnome already has
            #     the migrated content for the next login).
            if dtp_local_monitors:
                cls._migrate_dtp_keys_for_local_monitors(dtp_local_monitors)

            # 5. Persist to settings.gnome so the state survives next login.
            if persist:
                persist_ok, persist_info = cls._persist_to_settings_file()
                if not persist_ok:
                    log.warning("settings.gnome persist failed: %s", persist_info)
        finally:
            # 6. Re-enable extensions and the sync monitor regardless of
            #    load outcome.
            time.sleep(cls._SETTLE_SEC)
            cls._pause_extensions(pause=False)
            cls._sync_service("start")

        return ok, msg

    @classmethod
    def apply(cls, config_path: Path) -> Tuple[bool, str]:
        """Aplica um arquivo de layout ao ambiente."""
        if not config_path or not config_path.exists():
            return False, f"layout file not found: {config_path}"
        try:
            layout_text = config_path.read_text(encoding="utf-8")
        except Exception as exc:
            return False, f"cannot read layout file: {exc}"
        if not layout_text.strip():
            return False, "layout file is empty"

        # Capture local dash-to-panel monitor IDs BEFORE the reset wipes them.
        local_dtp_monitors = cls._read_dtp_monitor_keys()
        before = cls._enabled_extensions()

        # Merge layout INTO the existing settings.gnome so chaves nao
        # cobertas pelo layout (gtk-theme, user-theme name, fontes etc.)
        # sobrevivam ao reset+load.
        settings_text = cls._load_current_settings_text()
        merged_text = cls._merge_layout_into_settings(layout_text, settings_text)

        ok, msg = cls.load_dconf_safely(
            merged_text,
            persist=True,
            dtp_local_monitors=local_dtp_monitors,
        )
        if ok:
            after = cls._enabled_extensions()
            ShellReloader.reload_all(before_uuids=before, after_uuids=after)
        return ok, msg
