#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# install.sh — Instala o Community Layout Switcher no sistema.
#
# Uso:
#   ./install.sh              # instala para o usuário atual (~/.local)
#   sudo ./install.sh         # instala para todos os usuários (/usr)
#
# Desinstalar:
#   ./install.sh --uninstall
#   sudo ./install.sh --uninstall

set -euo pipefail

APP_NAME="community-layout-switcher"
ICON_NAME="comm-layout-switcher"          # nome do ícone (sem extensão)
ICON_SRC="icons/comm-layout-switcher.svg" # caminho relativo ao projeto
DESKTOP_FILE="org.bigappearance.app.desktop"
LAUNCHER="${APP_NAME}"

# ── Determina escopo da instalação ────────────────────────────────────────────
if [[ "${EUID}" -eq 0 ]]; then
    SHARE_DIR="/usr/share/${APP_NAME}"
    BIN_DIR="/usr/bin"
    APPS_DIR="/usr/share/applications"
    ICONS_BASE="/usr/share/icons"
    SCOPE="sistema"
else
    SHARE_DIR="${HOME}/.local/share/${APP_NAME}"
    BIN_DIR="${HOME}/.local/bin"
    APPS_DIR="${HOME}/.local/share/applications"
    ICONS_BASE="${HOME}/.local/share/icons"
    SCOPE="usuário (${HOME}/.local)"
fi

# Caminho canônico do ícone SVG no tema hicolor (scalable)
ICON_DEST_DIR="${ICONS_BASE}/hicolor/scalable/apps"
ICON_DEST="${ICON_DEST_DIR}/${ICON_NAME}.svg"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Helpers ───────────────────────────────────────────────────────────────────
update_icon_cache() {
    local base="${1}"
    # gtk-update-icon-cache só existe quando GTK está instalado
    if command -v gtk-update-icon-cache &>/dev/null; then
        gtk-update-icon-cache -f -t "${base}/hicolor" 2>/dev/null || true
    fi
    # xdg-icon-resource como alternativa
    if command -v xdg-icon-resource &>/dev/null; then
        xdg-icon-resource forceupdate 2>/dev/null || true
    fi
}

update_desktop_db() {
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "${APPS_DIR}" 2>/dev/null || true
    fi
}

# ── Desinstalar ───────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Desinstalando ${APP_NAME} (${SCOPE})..."
    rm -rf "${SHARE_DIR}"
    rm -f  "${BIN_DIR}/${LAUNCHER}"
    rm -f  "${APPS_DIR}/${DESKTOP_FILE}"
    rm -f  "${ICON_DEST}"
    update_icon_cache "${ICONS_BASE}"
    update_desktop_db
    echo "✓ Desinstalado com sucesso."
    exit 0
fi

# ── Verificações ──────────────────────────────────────────────────────────────
ICON_SRC_PATH="${SCRIPT_DIR}/${ICON_SRC}"
if [[ ! -f "${ICON_SRC_PATH}" ]]; then
    echo "⚠  Ícone não encontrado: ${ICON_SRC_PATH}"
    echo "   Coloque o arquivo 'comm-layout-switcher.svg' em ./icons/ e execute novamente."
    echo "   A instalação continuará, mas o ícone não aparecerá no menu."
    SKIP_ICON=1
else
    SKIP_ICON=0
fi

# ── Instalar ──────────────────────────────────────────────────────────────────
echo "Instalando ${APP_NAME} em: ${SCOPE}"
echo ""

# 1. Arquivos do aplicativo
echo "  [1/4] Copiando arquivos do app → ${SHARE_DIR}"
mkdir -p "${SHARE_DIR}"
cp -r "${SCRIPT_DIR}/community_layout_switcher" "${SHARE_DIR}/"
cp    "${SCRIPT_DIR}/main.py"                   "${SHARE_DIR}/"

# Assets opcionais (layouts, icons, locale)
for asset in layouts icons locale; do
    if [[ -d "${SCRIPT_DIR}/${asset}" ]]; then
        cp -r "${SCRIPT_DIR}/${asset}" "${SHARE_DIR}/"
        echo "       ↳ asset '${asset}' copiado"
    fi
done

# 2. Ícone SVG → hicolor/scalable/apps
if [[ "${SKIP_ICON}" -eq 0 ]]; then
    echo "  [2/4] Instalando ícone SVG → ${ICON_DEST}"
    mkdir -p "${ICON_DEST_DIR}"
    cp "${ICON_SRC_PATH}" "${ICON_DEST}"
    chmod 644 "${ICON_DEST}"
    update_icon_cache "${ICONS_BASE}"
    echo "       ↳ cache de ícones atualizado"
else
    echo "  [2/4] Ícone ignorado (arquivo não encontrado)"
fi

# 3. Launcher executável
echo "  [3/4] Instalando launcher → ${BIN_DIR}/${LAUNCHER}"
mkdir -p "${BIN_DIR}"
cp "${SCRIPT_DIR}/${LAUNCHER}" "${BIN_DIR}/${LAUNCHER}"
chmod +x "${BIN_DIR}/${LAUNCHER}"

# 4. Arquivo .desktop
echo "  [4/4] Instalando .desktop → ${APPS_DIR}/${DESKTOP_FILE}"
mkdir -p "${APPS_DIR}"
cp "${SCRIPT_DIR}/${DESKTOP_FILE}" "${APPS_DIR}/${DESKTOP_FILE}"
update_desktop_db
echo "       ↳ banco de dados de aplicativos atualizado"

# ── Resumo ────────────────────────────────────────────────────────────────────
echo ""
echo "✓ Instalação concluída!"
echo ""
echo "  Executar no terminal : ${LAUNCHER}"
echo "  Ou abra pelo menu    : 'Community Layout Switcher'"
echo ""

# Aviso se ~/.local/bin não estiver no PATH (apenas instalação de usuário)
if [[ "${EUID}" -ne 0 ]]; then
    if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
        echo "⚠  '${BIN_DIR}' não está no seu PATH."
        echo "   Adicione ao ~/.bashrc ou ~/.profile:"
        echo ""
        echo "       export PATH=\"\${HOME}/.local/bin:\${PATH}\""
        echo ""
        echo "   Depois execute:  source ~/.bashrc"
    fi
fi
