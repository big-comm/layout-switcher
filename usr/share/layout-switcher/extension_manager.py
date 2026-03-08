# SPDX-License-Identifier: MIT
"""
extension_manager.py — Gerenciamento de extensões do GNOME Shell.

Responsabilidades:
  - Consultar extensões instaladas e habilitadas
  - Instalar (CLI / download EGO / gerenciador de pacotes)
  - Remover extensões do usuário
  - Ativar/desativar em tempo real via D-Bus (sem logout)
  - Abrir preferências de extensão

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from constants import EXT_SYS_DIR, EXT_USER_DIR
from utils import dconf_read, dconf_write, gnome_shell_version, gsettings_get, run_cmd


class ExtMgr:
    """
    Todas as operações de extensão do GNOME Shell.
    Thread-safe para leituras. Escritas serializam via gsettings/dconf/D-Bus.
    """

    # ── Consultas ─────────────────────────────────────────────────────────────

    @staticmethod
    def is_installed(uuid: str) -> bool:
        """Verifica se a extensão está instalada (usuário ou sistema)."""
        return (EXT_USER_DIR / uuid).exists() or (EXT_SYS_DIR / uuid).exists()

    @staticmethod
    def is_user_dir(uuid: str) -> bool:
        """Retorna True se instalada em ~/.local (removível pelo usuário)."""
        return (EXT_USER_DIR / uuid).exists()

    @staticmethod
    def enabled_list() -> List[str]:
        """
        Retorna lista de UUIDs de extensões habilitadas.
        Corrigido para tratar @as [], listas vazias, espaços e aspas.
        """
        val = gsettings_get("org.gnome.shell", "enabled-extensions") or ""
        val = val.strip()

        # Casos especiais: lista vazia em formato GVariant
        if not val or val in ("@as []", "[]", "@as[]"):
            return []

        # Remove prefixo de tipo GVariant e colchetes
        val = val.lstrip("@as").strip()
        if val.startswith("[") and val.endswith("]"):
            val = val[1:-1]

        result = []
        for token in val.split(","):
            clean = token.strip().strip("'\"")
            if clean:
                result.append(clean)
        return result

    @staticmethod
    def is_enabled(uuid: str) -> bool:
        return uuid in ExtMgr.enabled_list()

    @staticmethod
    def all_globally_enabled() -> bool:
        """
        Retorna True se extensões estão globalmente habilitadas.
        False quando disable-extensions=true no dconf.
        """
        val = dconf_read("/org/gnome/shell/disable-extensions")
        return val is None or val.lower() != "true"

    # ── Listar instaladas ─────────────────────────────────────────────────────

    @staticmethod
    def list_installed() -> List[Dict]:
        """
        Escaneia diretórios de extensões do usuário e do sistema.
        Robusto contra metadata.json ausente, malformado ou incompleto.
        """
        results: List[Dict] = []
        seen: set = set()
        enabled = set(ExtMgr.enabled_list())

        for base_dir, is_user in [(EXT_USER_DIR, True), (EXT_SYS_DIR, False)]:
            if not base_dir.is_dir():
                continue
            try:
                entries = sorted(base_dir.iterdir(), key=lambda p: p.name.lower())
            except PermissionError:
                continue
            for entry in entries:
                if not entry.is_dir() or entry.name in seen:
                    continue
                seen.add(entry.name)
                meta: Dict = {}
                meta_path = entry / "metadata.json"
                if meta_path.exists():
                    try:
                        raw_text = meta_path.read_text(encoding="utf-8", errors="replace")
                        meta = json.loads(raw_text)
                    except Exception:
                        meta = {}
                uuid = meta.get("uuid") or entry.name
                results.append({
                    "uuid":        uuid,
                    "name":        meta.get("name") or uuid,
                    "description": meta.get("description", ""),
                    "version":     str(meta.get("version", "")),
                    "url":         meta.get("url", ""),
                    "user":        is_user,
                    "enabled":     uuid in enabled,
                })
        return results

    # ── Ativar / Desativar ────────────────────────────────────────────────────

    @staticmethod
    def set_enabled(uuid: str, enable: bool) -> Tuple[bool, str]:
        """
        Ativa ou desativa extensão em tempo real via D-Bus (sem logout).
        Fallback automático para gsettings.
        """
        # Import local para evitar circular import
        from shell_reloader import ShellReloader
        return ShellReloader.apply_extension_state(uuid, enable)

    @staticmethod
    def _set_enabled_gsettings(uuid: str, enable: bool) -> Tuple[bool, str]:
        """
        Fallback: modifica a lista de extensões diretamente via gsettings.
        Usado quando D-Bus não está disponível.
        """
        cur = ExtMgr.enabled_list()
        if enable:
            if uuid not in cur:
                cur.append(uuid)
        else:
            cur = [e for e in cur if e != uuid]
        inner = ", ".join(f"'{e}'" for e in cur)
        return run_cmd([
            "gsettings", "set", "org.gnome.shell", "enabled-extensions",
            f"[{inner}]",
        ])

    @staticmethod
    def disable_all_globally(disable: bool) -> Tuple[bool, str]:
        """
        Desabilita ou habilita globalmente todas as extensões.
        disable=True  → desabilita tudo
        disable=False → re-habilita tudo
        """
        from shell_reloader import ShellReloader
        ok, msg = dconf_write(
            "/org/gnome/shell/disable-extensions",
            "true" if disable else "false",
        )
        if ok:
            ShellReloader.reload_all()
        return ok, msg

    # ── Instalar ──────────────────────────────────────────────────────────────

    @staticmethod
    def install(uuid: str, ego_id: int, pkg: str) -> Tuple[bool, str]:
        """
        Instala uma extensão usando o melhor método disponível.

        Prioridade:
          1. gnome-extensions install  (GS 3.36+, funciona no Wayland)
          2. Download direto de extensions.gnome.org com shell_version correto
          3. Gerenciadores de pacotes do sistema

        Retorna (True, método_usado) ou (False, mensagem_erro).
        """
        # 1. gnome-extensions CLI (mais confiável, Wayland-safe)
        if shutil.which("gnome-extensions"):
            ok, out = run_cmd(
                ["gnome-extensions", "install", "--force", uuid],
                timeout=90,
            )
            if ok:
                return True, "gnome-extensions"

        # 2. Download direto do EGO com shell_version correto
        if ego_id > 0:
            ok, out = ExtMgr._install_from_ego(uuid, ego_id)
            if ok:
                return True, "ego-download"

        # 3. Gerenciadores de pacotes
        for cmd in [
            ["pkcon",   "install",  "-y",          pkg],
            ["apt-get", "install",  "-y",           pkg],
            ["apt",     "install",  "-y",           pkg],
            ["dnf",     "install",  "-y",           pkg],
            ["pacman",  "-S",       "--noconfirm",  pkg],
            ["zypper",  "install",  "-y",           pkg],
        ]:
            if shutil.which(cmd[0]):
                ok, out = run_cmd(cmd, timeout=180)
                if ok:
                    return True, cmd[0]

        return False, "no installation method succeeded"

    @staticmethod
    def _install_from_ego(uuid: str, ego_id: int) -> Tuple[bool, str]:
        """
        Baixa extensão de extensions.gnome.org com shell_version correto.
        Corrigido para GNOME 45+ que mudou o formato do query param.
        Proteção contra path traversal em zips maliciosos.
        """
        try:
            major, minor = gnome_shell_version()
            url = (
                f"https://extensions.gnome.org/download-extension"
                f"/{uuid}.shell-extension.zip"
            )
            if major > 0:
                url += f"?shell_version={major}"

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 GNOME-Shell-Extension-Installer"
                    ),
                    "Accept": "application/zip, application/octet-stream, */*",
                },
            )

            dest = EXT_USER_DIR / uuid
            dest.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_f:
                tmp_path = Path(tmp_f.name)

            with urllib.request.urlopen(req, timeout=60) as resp:
                ct = resp.headers.get("Content-Type", "")
                if "text/html" in ct:
                    return False, "server returned HTML instead of zip"
                data = resp.read()

            if not data or len(data) < 100:
                try:
                    dest.rmdir()
                except Exception:
                    pass
                return False, "empty or too-small download"

            tmp_path.write_bytes(data)

            with zipfile.ZipFile(str(tmp_path)) as zf:
                # Segurança: evita path traversal no zip
                for member in zf.namelist():
                    if ".." in member or member.startswith("/"):
                        continue
                    zf.extract(member, str(dest))

            tmp_path.unlink(missing_ok=True)
            return True, url

        except Exception as exc:
            return False, str(exc)

    # ── Remover ───────────────────────────────────────────────────────────────

    @staticmethod
    def remove(uuid: str) -> Tuple[bool, str]:
        """
        Remove extensão instalada pelo usuário.
        Desativa via D-Bus antes de remover (sem logout).
        """
        path = EXT_USER_DIR / uuid
        if not path.exists():
            return False, "not found in user extensions directory"

        # Desativa em tempo real antes de remover
        from shell_reloader import ShellReloader
        ShellReloader.apply_extension_state(uuid, False)

        try:
            shutil.rmtree(str(path))
            ShellReloader.reload_all()
            return True, ""
        except Exception as exc:
            return False, str(exc)

    # ── Preferências ──────────────────────────────────────────────────────────

    @staticmethod
    def open_prefs(uuid: str) -> None:
        """
        Abre as preferências de uma extensão.
        Suporta X11 e Wayland via D-Bus OpenExtensionPrefs (GS 40+).
        """
        from constants import DBUS_EXT_IFACE, DBUS_EXT_PATH, DBUS_SHELL_NAME

        # Método 1: gnome-extensions prefs (Wayland-safe, GS 3.36+)
        if shutil.which("gnome-extensions"):
            ok, err = run_cmd(["gnome-extensions", "prefs", uuid], timeout=5)
            if ok:
                return

        # Método 2: D-Bus OpenExtensionPrefs (GS 40+)
        run_cmd([
            "gdbus", "call", "--session",
            "--dest",        DBUS_SHELL_NAME,
            "--object-path", DBUS_EXT_PATH,
            "--method",      f"{DBUS_EXT_IFACE}.OpenExtensionPrefs",
            uuid, "", "{}",
        ], timeout=5)
