# SPDX-License-Identifier: MIT
"""
settings_store.py — Persistência de configurações do app e monitor de GSettings.

Classes:
  Settings          : configurações JSON persistentes do aplicativo
  GSettingsMonitor  : monitora mudanças externas em GSettings em tempo real

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import json
from typing import Callable, Dict, List, Tuple

from constants import CONFIG_DIR, SETTINGS_FILE
from utils import atomic_write_text

# ── Settings ──────────────────────────────────────────────────────────────────


class Settings:
    """
    Configurações persistentes em JSON.
    Escrita atômica via arquivo temporário + rename.
    Silencia todos os erros de I/O.
    """

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._data: Dict = {}
        try:
            if SETTINGS_FILE.exists():
                text = SETTINGS_FILE.read_text(encoding="utf-8")
                self._data = json.loads(text)
        except Exception:
            pass

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def _reload_from_disk(self) -> None:
        """
        Re-read the JSON file into ``self._data``. Multiple Settings()
        instances co-exist (window, page_layouts, etc.) and each one
        loads from disk only at __init__. Without re-reading before a
        write, instance A's stale ``_data`` would clobber keys instance
        B persisted (e.g. ``intro_shown`` set by window vanished when
        page_layouts later wrote ``active_layout``).
        """
        try:
            if SETTINGS_FILE.exists():
                self._data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    def set(self, key: str, value) -> None:
        self._reload_from_disk()
        self._data[key] = value
        try:
            atomic_write_text(SETTINGS_FILE, json.dumps(self._data, indent=2))
        except Exception:
            pass

    def delete(self, key: str) -> None:
        self._reload_from_disk()
        self._data.pop(key, None)
        try:
            atomic_write_text(SETTINGS_FILE, json.dumps(self._data, indent=2))
        except Exception:
            pass


# ── GSettings Monitor ─────────────────────────────────────────────────────────


class GSettingsMonitor:
    """
    Monitora mudanças externas em GSettings e notifica callbacks.

    Permite que a UI reflita mudanças feitas fora do app (ex: GNOME Tweaks,
    outro programa, linha de comando) sem precisar reiniciar o aplicativo.

    Uso:
        monitor = GSettingsMonitor()
        monitor.watch("org.gnome.shell", "enabled-extensions", my_callback)
        # ...
        monitor.disconnect_all()  # limpeza ao fechar
    """

    def __init__(self) -> None:
        # lazy import → Settings class stays testable without gi
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gio

        self._Gio = Gio
        # Lista de (Gio.Settings, key, handler_id) para desconexão posterior
        self._watchers: List[Tuple] = []

    def watch(self, schema: str, key: str, callback: Callable) -> bool:
        """
        Registra um callback para quando schema::key mudar externamente.
        O callback é chamado sem argumentos na UI thread (via GLib signals).
        Retorna True se o schema existe e o watch foi registrado com sucesso.
        """
        try:
            Gio = self._Gio
            src = Gio.SettingsSchemaSource.get_default()
            if src and src.lookup(schema, True) is None:
                return False
            gs = Gio.Settings.new(schema)
            handler = gs.connect(f"changed::{key}", lambda s, k: callback())
            self._watchers.append((gs, key, handler))
            return True
        except Exception:
            return False

    def watch_any(self, schema: str, callback: Callable) -> bool:
        """
        Registra callback para qualquer mudança no schema inteiro.
        Útil para schemas com muitas chaves.
        """
        try:
            Gio = self._Gio
            src = Gio.SettingsSchemaSource.get_default()
            if src and src.lookup(schema, True) is None:
                return False
            gs = Gio.Settings.new(schema)
            handler = gs.connect("changed", lambda s, k: callback())
            self._watchers.append((gs, "any", handler))
            return True
        except Exception:
            return False

    def disconnect_all(self) -> None:
        """Desconecta todos os watchers registrados. Chamar ao destruir a janela."""
        for gs, key, handler in self._watchers:
            try:
                gs.disconnect(handler)
            except Exception:
                pass
        self._watchers.clear()
