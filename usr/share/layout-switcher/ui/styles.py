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
    outline: 2px solid transparent;
    outline-offset: -2px;
    border: none;
    box-shadow: none;
    border-radius: 12px;
    background-color: alpha(@card_bg_color, 1);
    padding: 6px;
    transition: outline-color 120ms ease, box-shadow 120ms ease;
}
.layout-card:hover          { outline-color: alpha(@accent_color, 0.35); }
.layout-card.layout-on      { outline-color: @accent_color; }
.layout-ribbon {
    background-color: @accent_bg_color;
    color: @accent_fg_color;
    border-radius: 0 10px 0 8px;
    font-weight: 700;
    padding: 3px 9px;
}
.layout-modified {
    color: @warning_color;
    font-size: 14px;
    font-weight: 700;
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

/* ── Lista de temas (boxed-list nativo) ──────────────────────────────── */
.boxed-list > row.activatable:hover { background-color: alpha(@accent_bg_color, 0.06); }
.theme-name-active          { color: @accent_color; font-weight: 600; }

/* ── Sub-abas de tipo de tema ────────────────────────────────────────── */
.kind-tab                   { border-radius: 8px; padding: 5px 14px; font-weight: 500; }
.kind-tab.kind-on           { background-color: alpha(@accent_bg_color, 0.18); color: @accent_color; font-weight: 700; }

/* ── Sub-abas de extensões ───────────────────────────────────────────── */
.sub-tab                    { border-radius: 8px; padding: 5px 14px; font-weight: 500; }
.sub-tab.sub-on             { background-color: alpha(@accent_bg_color, 0.18); color: @accent_color; font-weight: 700; }

/* ── Utilitários ─────────────────────────────────────────────────────── */
.page-title                 { font-weight: 800; letter-spacing: -0.3px; }
.ok-col                     { color: @success_color; font-weight: 600; }
.err-col                    { color: @error_color; font-weight: 600; }
.mono                       { font-family: monospace; }
.global-btn                 { border-radius: 10px; padding: 7px 14px; font-weight: 600; }
.spinner-row                { border-radius: 10px; background-color: alpha(@accent_bg_color, 0.07); padding: 14px; }
"""
