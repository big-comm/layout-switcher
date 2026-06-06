# SPDX-License-Identifier: MIT
"""
ui/styles.py — CSS da aplicação.

Centraliza todo o estilo visual para facilitar customização e manutenção.
Carregado uma única vez em MainWindow._apply_css().

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

APP_CSS = """
/* ── Sidebar ─────────────────────────────────────────────────────────── */
.nav-row {
    border-radius: 10px;
    margin: 1px 7px;
    transition: background-color 120ms ease;
}
.nav-row:hover              { background-color: alpha(@accent_bg_color, 0.08); }
.nav-row:focus              { outline: 2px solid alpha(@accent_color, 0.5); outline-offset: -2px; }
.nav-row.nav-sel            { background-color: alpha(@accent_bg_color, 0.17); }
.nav-row.nav-sel .nav-lbl   { color: @accent_color; font-weight: 700; }
.nav-lbl                    { font-weight: 500; }

/* ── Layout cards ────────────────────────────────────────────────────── */
.layout-card {
    background-color: alpha(@card_bg_color, 0.50);
    border: 1px solid alpha(@card_fg_color, 0.10);
    border-radius: 15px;
    padding: 10px 10px 13px;
    transition: background-color 160ms ease,
                border-color 160ms ease,
                box-shadow 200ms ease;
    box-shadow: 0 1px 2px alpha(black, 0.05);
}
.layout-card:hover {
    background-color: alpha(@card_bg_color, 0.92);
    border-color: alpha(@accent_color, 0.42);
    box-shadow: 0 8px 22px alpha(black, 0.16);
}
.layout-card.layout-on {
    border-color: @accent_color;
    background-color: alpha(@accent_bg_color, 0.10);
    box-shadow: 0 0 0 1px @accent_color,
                0 8px 24px alpha(@accent_color, 0.20);
}

/* Preview (SVG wrapper) — só arredonda. A seleção vive no card, então o
   preview NÃO ganha contorno próprio (evita o contorno duplo: um interno
   no preview + um externo na borda do card). */
.layout-preview {
    border-radius: 10px;
}

/* Neutraliza a seleção/contorno nativo do FlowBoxChild para não somar com
   a borda do card — a única seleção visível é a do .layout-card. */
.layout-grid > flowboxchild {
    outline: none;
    background: none;
    box-shadow: none;
    border-radius: 15px;
}
.layout-grid > flowboxchild:hover,
.layout-grid > flowboxchild:focus,
.layout-grid > flowboxchild:focus-visible,
.layout-grid > flowboxchild:selected {
    background: none;
    box-shadow: none;
    outline: none;
}

/* Disabled layout (work-in-progress, not yet clickable) */
.layout-disabled                     { opacity: 0.42; }
.layout-disabled:hover {
    background-color: alpha(@card_bg_color, 0.50);
    border-color: alpha(@card_fg_color, 0.10);
    box-shadow: 0 1px 2px alpha(black, 0.05);
}
.layout-disabled:hover .layout-preview { box-shadow: none; }

/* Nome + descrição do layout */
.layout-name                         { font-weight: 700; }
.layout-name-active                  { color: @accent_color; font-weight: 800; letter-spacing: 0; }
.layout-desc {
    font-size: 11px;
    opacity: 0.58;
}

/* Badge "Modified" theme-aware (libadwaita adapta @warning_bg/fg_color) */
.layout-modified-badge {
    background-color: @warning_bg_color;
    color: @warning_fg_color;
    border: 1px solid alpha(@warning_fg_color, 0.22);
    border-radius: 6px;
    padding: 1px 7px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0;
    box-shadow: 0 1px 2px alpha(#000000, 0.15);
}
.layout-modified-badge image,
.layout-modified-badge label {
    color: @warning_fg_color;
}

/* Check de ativo — circulo accent no canto superior-direito do preview */
.layout-active-check {
    background-color: @accent_color;
    color: @accent_fg_color;
    border-radius: 50%;
    padding: 3px;
    box-shadow: 0 0 8px alpha(@accent_color, 0.55);
}

/* ── Extension cards em destaque ─────────────────────────────────────── */
.ext-card {
    outline: 2px solid transparent;
    outline-offset: -2px;
    transition: outline-color 120ms ease;
}
.ext-card.ext-on            { outline-color: @accent_color; }

/* ── Lista de extensões instaladas (boxed-list nativo) ───────────────── */
/* As linhas usam Gtk.ListBoxRow dentro de .boxed-list — sem esticar.    */
.boxed-list > row:hover     { background-color: alpha(@accent_bg_color, 0.05); }
.extension-action-button {
    min-width: 34px;
    min-height: 34px;
    padding: 0;
    border-radius: 8px;
}
.extension-action-button-disabled {
    opacity: 0.38;
}

/* ── Lista de temas (boxed-list nativo) ──────────────────────────────── */
.boxed-list > row.activatable:hover { background-color: alpha(@accent_bg_color, 0.06); }
.theme-name-active          { color: @accent_color; font-weight: 600; }

/* ── Grid de temas (GTK / Shell) ─────────────────────────────────────── */
.theme-tile {
    outline: 2px solid transparent;
    outline-offset: -2px;
    border-radius: 10px;
    transition: outline-color 120ms ease, background-color 120ms ease;
}
.theme-tile:hover           { background-color: alpha(@accent_bg_color, 0.05); }
.theme-tile.theme-tile-active { outline-color: @accent_color; }

/* ── Sub-abas de tipo de tema ────────────────────────────────────────── */
.kind-tab                   { border-radius: 8px; padding: 5px 14px; font-weight: 500; }
.kind-tab.kind-on           { background-color: alpha(@accent_bg_color, 0.18); color: @accent_color; font-weight: 700; }

/* ── Sub-abas de extensões ───────────────────────────────────────────── */
.sub-tab                    { border-radius: 8px; padding: 5px 14px; font-weight: 500; }
.sub-tab.sub-on             { background-color: alpha(@accent_bg_color, 0.18); color: @accent_color; font-weight: 700; }

/* ── Utilitários ─────────────────────────────────────────────────────── */
.page-title                 { font-weight: 800; letter-spacing: 0; }
.ok-col                     { color: @success_color; font-weight: 600; }
.err-col                    { color: @error_color; font-weight: 600; }
.mono                       { font-family: monospace; }
.global-btn                 { border-radius: 10px; padding: 7px 14px; font-weight: 600; }
.spinner-row                { border-radius: 10px; background-color: alpha(@accent_bg_color, 0.07); padding: 14px; }

/* ── Google Fonts ───────────────────────────────────────────────────── */
.google-font-search {
    min-height: 38px;
    border-radius: 9px;
}

/* ── Loading overlay (apply layout) ──────────────────────────────────── */
.loading-backdrop {
    background-color: alpha(black, 0.52);
    opacity: 0;
    transition: opacity 220ms ease;
}
.loading-backdrop.loading-show {
    opacity: 1;
}

.loading-card {
    background-color: alpha(#111318, 0.88);
    color: white;
    border-radius: 14px;
    padding: 22px 34px;
    min-width: 300px;
    min-height: 120px;
    box-shadow: 0 18px 46px alpha(black, 0.42),
                0 0 0 1px alpha(white, 0.10);
    opacity: 0;
    transition: opacity 240ms ease;
}
.loading-card.loading-show {
    opacity: 1;
}
.loading-art {
    margin-bottom: 2px;
    padding: 9px 12px;
    border-radius: 11px;
    background-image: linear-gradient(160deg,
                      alpha(#4a86e8, 0.16),
                      alpha(#2a3550, 0.04));
    box-shadow: inset 0 0 0 1px alpha(#6aa0ff, 0.24),
                0 0 24px alpha(#4a86e8, 0.18);
}
.loading-card label {
    font-weight: 600;
}
.loading-card spinner {
    color: white;
}
.loading-label {
    color: white;
}
"""
