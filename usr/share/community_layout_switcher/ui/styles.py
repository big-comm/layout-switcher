# SPDX-License-Identifier: MIT
"""
ui/styles.py — CSS da aplicação.

Centraliza todo o estilo visual para facilitar customização e manutenção.
Carregado uma única vez em MainWindow._apply_css().

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

APP_CSS = """
/* ── Sidebar ─────────────────────────────────────────────────────────── */
.main-sidebar {
    background-color: alpha(@card_bg_color, 0.5);
    border-right: 1px solid alpha(@borders, 0.3);
    min-width: 192px;
}
.nav-row {
    border-radius: 10px;
    margin: 1px 7px;
    transition: background-color 120ms ease;
}
.nav-row:hover              { background-color: alpha(@accent_bg_color, 0.08); }
.nav-row:focus              { outline: 2px solid alpha(@accent_color, 0.5); outline-offset: -2px; }
.nav-row.nav-sel            { background-color: alpha(@accent_bg_color, 0.17); }
.nav-row.nav-sel .nav-lbl   { color: @accent_color; font-weight: 700; }
.nav-lbl                    { font-size: 10pt; font-weight: 500; }

/* ── Layout cards ────────────────────────────────────────────────────── */
.layout-card {
    border-radius: 14px;
    outline: 2px solid transparent;
    outline-offset: -2px;
    transition: outline-color 120ms ease, box-shadow 120ms ease;
}
.layout-card:hover          { outline-color: alpha(@accent_color, 0.35); }
.layout-card.layout-on      { outline-color: @accent_color; }
.layout-ribbon {
    background-color: @accent_bg_color;
    color: @accent_fg_color;
    border-radius: 0 10px 0 8px;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 3px 9px;
}

/* ── Extension cards em destaque ─────────────────────────────────────── */
.ext-card {
    border-radius: 14px;
    outline: 2px solid transparent;
    outline-offset: -2px;
    transition: outline-color 120ms ease;
}
.ext-card.ext-on            { outline-color: @accent_color; }

/* ── Lista de extensões instaladas (boxed-list nativo) ───────────────── */
/* As linhas usam Gtk.ListBoxRow dentro de .boxed-list — sem esticar.    */
.boxed-list > row:hover     { background-color: alpha(@accent_bg_color, 0.05); }

/* ── Lista de temas (boxed-list nativo) ──────────────────────────────── */
.boxed-list > row.activatable:hover { background-color: alpha(@accent_bg_color, 0.06); }
.theme-name-active          { color: @accent_color; font-weight: 600; }

/* ── Dark/Light scheme pill ──────────────────────────────────────────── */
.scheme-pill                { border-radius: 999px; padding: 6px 12px; font-size: 9pt; font-weight: 500; transition: all 100ms ease; }
.scheme-pill.s-on           { background-color: @accent_bg_color; color: @accent_fg_color; }

/* ── Sub-abas de tipo de tema ────────────────────────────────────────── */
.kind-tab                   { border-radius: 8px; padding: 5px 14px; font-size: 9.5pt; font-weight: 500; }
.kind-tab.kind-on           { background-color: alpha(@accent_bg_color, 0.18); color: @accent_color; font-weight: 700; }

/* ── Sub-abas de extensões ───────────────────────────────────────────── */
.sub-tab                    { border-radius: 8px; padding: 5px 14px; font-size: 9.5pt; font-weight: 500; }
.sub-tab.sub-on             { background-color: alpha(@accent_bg_color, 0.18); color: @accent_color; font-weight: 700; }

/* ── Utilitários ─────────────────────────────────────────────────────── */
.page-title                 { font-size: 17pt; font-weight: 800; letter-spacing: -0.3px; }
.ok-col                     { color: #26a269; font-weight: 600; }
.err-col                    { color: #c01c28; font-weight: 600; }
.dim                        { opacity: 0.55; }
.mono                       { font-family: monospace; font-size: 8.5pt; }
.global-btn                 { border-radius: 10px; padding: 7px 14px; font-weight: 600; }
.spinner-row                { border-radius: 10px; background-color: alpha(@accent_bg_color, 0.07); padding: 14px; }
"""
