# SPDX-License-Identifier: MIT
"""
theme_preview.py — Previews reais para linhas de temas.

Duas funcoes publicas:

  * ``find_folder_icon(theme_name)``  -> Optional[Path]
      Retorna o caminho do icone ``folder`` (svg/png) do tema de icones,
      procurando em ``scalable/places/`` e tamanhos comuns. Usado para
      mostrar uma miniatura real do icone em vez de uma bolinha arbitraria.

  * ``extract_theme_color(theme_name, kind)`` -> Optional[str]
      Extrai um hex ``#rrggbb`` representativo do tema GTK ou Shell,
      parseando variaveis de cor do CSS (``@define-color accent_color``,
      ``accent_bg_color``, ``theme_selected_bg_color``, ...). Fallback para
      None quando o tema usa referencia a outra variavel ou funcao (nao
      resolvemos recursivamente).

DEVELOPER NOTE - DO NOT name any variable `_` in this file.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("layout-switcher")


# ── Icon theme: folder preview ───────────────────────────────────────────────


_ICON_ROOTS: List[Path] = [
    Path.home() / ".icons",
    Path.home() / ".local" / "share" / "icons",
    Path("/usr/local/share/icons"),
    Path("/usr/share/icons"),
]

# Caminhos relativos a tentar em ordem de preferencia. SVG > PNG; places > default.
_FOLDER_REL_PATHS: List[str] = [
    "scalable/places/folder.svg",
    "scalable/places/default-folder.svg",
    "places/scalable/folder.svg",
    "48x48/places/folder.png",
    "64x64/places/folder.png",
    "32x32/places/folder.png",
    "24x24/places/folder.png",
    "scalable/places/folder-blue.svg",
]


def find_folder_icon(theme_name: str) -> Optional[Path]:
    """
    Retorna o caminho do icone ``folder`` do tema, pronto para
    ``Gtk.Picture.new_for_filename()``.

    Tenta caminhos padrao; se nenhum existir, faz glob recursivo
    procurando qualquer ``folder.svg`` ou ``folder.png``.

    Retorna None se o tema nao for encontrado ou nao tiver icone folder.
    """
    if not theme_name:
        return None

    for root in _ICON_ROOTS:
        theme_dir = root / theme_name
        if not theme_dir.is_dir():
            continue

        # Caminhos conhecidos primeiro
        for rel in _FOLDER_REL_PATHS:
            candidate = theme_dir / rel
            if candidate.is_file():
                return candidate

        # Fallback: glob recursivo limitado
        try:
            for pattern in ("folder.svg", "folder.png"):
                hits = list(theme_dir.rglob(pattern))
                if hits:
                    # Prefere hit em "places/" sobre outros locais
                    places = [h for h in hits if "places" in h.parts]
                    return places[0] if places else hits[0]
        except Exception as exc:
            log.debug("folder glob failed for %s: %s", theme_name, exc)

    return None


# ── GTK / Shell theme: color extraction ──────────────────────────────────────


_THEME_ROOTS: List[Path] = [
    Path.home() / ".themes",
    Path("/usr/local/share/themes"),
    Path("/usr/share/themes"),
]

# CSS variaveis em ordem de preferencia (primeira que bater ganha)
_ACCENT_VARS: List[str] = [
    "accent_bg_color",
    "accent_color",
    "theme_selected_bg_color",
    "selected_bg_color",
    "primary_color",
]

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _css_files(theme_name: str, kind: str) -> List[Path]:
    """Arquivos CSS candidatos para extrair cor do tema."""
    files: List[Path] = []
    for root in _THEME_ROOTS:
        base = root / theme_name
        if not base.is_dir():
            continue
        if kind == "gtk":
            for sub in ("gtk-4.0/gtk.css", "gtk-3.0/gtk.css"):
                f = base / sub
                if f.is_file():
                    files.append(f)
        elif kind == "shell":
            for sub in ("gnome-shell/gnome-shell.css", "gnome-shell.css"):
                f = base / sub
                if f.is_file():
                    files.append(f)
    return files


def _normalize_hex(value: str) -> Optional[str]:
    """Normaliza ``#rgb`` / ``#rrggbb`` / ``#rrggbbaa`` -> ``#rrggbb``."""
    value = value.strip().rstrip(";").strip()
    if not _HEX_RE.match(value):
        return None
    if len(value) == 4:  # #rgb -> #rrggbb
        return "#" + "".join(c * 2 for c in value[1:])
    return "#" + value[1:7].lower()


def _extract_from_css(text: str) -> Optional[str]:
    """Procura ``@define-color <var> <hex>`` para variaveis conhecidas."""
    for var in _ACCENT_VARS:
        pat = rf"@define-color\s+{var}\s+([^;]+);"
        match = re.search(pat, text)
        if not match:
            continue
        raw = match.group(1).strip()
        # Valor pode ser: "#rrggbb", "#rgb", "rgba(...)", "@other_var", "mix(...)"
        # So sabemos lidar com hex literal; outros casos devolvem None.
        normalized = _normalize_hex(raw)
        if normalized:
            return normalized
    return None


def extract_theme_color(theme_name: str, kind: str) -> Optional[str]:
    """
    Extrai um hex representativo do tema GTK ou Shell.

    Args:
        theme_name: nome do tema (diretorio em ``~/.themes`` ou ``/usr/share/themes``)
        kind: "gtk" ou "shell"

    Retorna ``#rrggbb`` ou None se nao for possivel extrair uma cor literal.
    """
    if kind not in ("gtk", "shell"):
        return None

    for css_path in _css_files(theme_name, kind):
        try:
            # Limita leitura para nao carregar arquivos enormes inteiros
            # (gtk.css pode ter 100k+ linhas em temas grandes)
            text = css_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            log.debug("css read failed: %s -> %s", css_path, exc)
            continue

        color = _extract_from_css(text)
        if color:
            return color

    return None
