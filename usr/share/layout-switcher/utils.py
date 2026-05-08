# SPDX-License-Identifier: MIT
"""
utils.py — Funções auxiliares de baixo nível.

Contém:
  - run_cmd()        : executa subprocessos com segurança
  - gsettings_get/set: lê/escreve valores via gsettings
  - dconf_read/write : lê/escreve valores via dconf
  - find_file()      : localiza arquivos em múltiplos diretórios
  - color_from_name(): extrai cor hexadecimal a partir do nome do tema
  - gnome_shell_version(): detecta versão do GNOME Shell
  - is_wayland()     : detecta sessão Wayland

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from constants import COLOR_MAP

log = logging.getLogger("layout-switcher")


def atomic_write_text(dest: Path, data: str, encoding: str = "utf-8") -> None:
    """
    Escreve ``data`` em ``dest`` de forma atômica e durável.

    Estratégia: escreve num ``.tmp`` irmão, faz flush+fsync do conteúdo, troca
    via rename atômico e fsync no diretório pai (durabilidade do metadado em
    ext4/btrfs/etc.). Levanta OSError em falha — caller decide o que fazer.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp") if dest.suffix else dest.with_name(dest.name + ".tmp")
    with open(tmp, "w", encoding=encoding) as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, dest)
    try:
        dir_fd = os.open(str(dest.parent), os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        log.debug("dir fsync skipped for %s: %s", dest.parent, exc)

# ── Subprocess ────────────────────────────────────────────────────────────────


def run_cmd(
    args: List[str],
    stdin_text: Optional[str] = None,
    timeout: int = 30,
    env: Optional[Dict] = None,
) -> Tuple[bool, str]:
    """
    Executa um subprocesso com segurança; nunca levanta exceção.
    Retorna (sucesso, saída).
    """
    try:
        merged_env = None
        if env:
            merged_env = os.environ.copy()
            merged_env.update(env)
        result = subprocess.run(
            args,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
        )
        out = (result.stdout.strip() or result.stderr.strip() or "").strip()
        ok = result.returncode == 0
        if not ok:
            log.debug("cmd fail rc=%d: %s → %s", result.returncode, args, out)
        return ok, out
    except FileNotFoundError:
        log.warning("cmd not found: %s", args[0])
        return False, f"command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        log.warning("cmd timeout %ds: %s", timeout, args)
        return False, f"timed out after {timeout}s"
    except PermissionError:
        log.warning("cmd perm denied: %s", args[0])
        return False, f"permission denied: {args[0]}"
    except Exception as exc:
        log.error("cmd error: %s → %s", args, exc)
        return False, f"error: {exc}"


# ── GSettings / dconf ─────────────────────────────────────────────────────────


def gsettings_get(schema: str, key: str) -> Optional[str]:
    """Lê um valor de gsettings; retorna None em caso de falha."""
    ok, out = run_cmd(["gsettings", "get", schema, key])
    return out.strip("'\" ") if ok else None


def gsettings_set(schema: str, key: str, value: str) -> Tuple[bool, str]:
    """Escreve um valor em gsettings."""
    return run_cmd(["gsettings", "set", schema, key, value])


def dconf_read(path: str) -> Optional[str]:
    """Lê um valor via dconf; retorna None se não existir ou falhar."""
    ok, out = run_cmd(["dconf", "read", path])
    return out.strip() if ok and out else None


def dconf_write(path: str, value: str) -> Tuple[bool, str]:
    """Escreve um valor via dconf."""
    return run_cmd(["dconf", "write", path, value])


# ── Localização de arquivos ───────────────────────────────────────────────────


def find_file(filename: str, subdirs: List[str]) -> Optional[Path]:
    """
    Localiza um arquivo percorrendo múltiplos diretórios base.
    Ordem de busca: diretório do pacote → ~/.local/share → /usr/share → /usr/local/share
    Em caso de falha, loga os caminhos pesquisados para facilitar diagnóstico.
    """
    if not filename:
        return None
    script_dir = Path(__file__).parent
    search_bases = [
        script_dir,
        Path.home() / ".local" / "share" / "layout-switcher",
        Path("/usr/share/layout-switcher"),
        Path("/usr/local/share/layout-switcher"),
    ]
    tried: List[Path] = []
    for d in subdirs:
        for base in search_bases:
            p = base / d / filename
            tried.append(p)
            if p.exists():
                return p
    log.debug("find_file: %s not found; tried: %s", filename, [str(p) for p in tried])
    return None


# ── Cores ─────────────────────────────────────────────────────────────────────


def color_from_name(name: str) -> str:
    """
    Retorna uma cor hexadecimal baseada no nome do tema.
    Usa o COLOR_MAP para tokens conhecidos; caso contrário, deriva do hash do nome.
    """
    low = name.lower()
    for token, hx in COLOR_MAP.items():
        if token in low:
            return hx
    hval = hash(name) & 0xFFFFFF
    return f"#{hval:06x}"


# ── GNOME Shell ───────────────────────────────────────────────────────────────


def gnome_shell_version() -> Tuple[int, int]:
    """
    Retorna (major, minor) da versão do GNOME Shell em execução, ex: (45, 2).
    Retorna (0, 0) se não conseguir detectar.
    """
    ok, out = run_cmd(["gnome-shell", "--version"])
    if ok and out:
        parts = out.split()
        if len(parts) >= 3:
            try:
                nums = parts[-1].split(".")
                return int(nums[0]), int(nums[1]) if len(nums) > 1 else 0
            except (ValueError, IndexError):
                pass
    return 0, 0


def is_wayland() -> bool:
    """Detecta se a sessão atual é Wayland."""
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    display = os.environ.get("WAYLAND_DISPLAY", "")
    return session == "wayland" or bool(display)
