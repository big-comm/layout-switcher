# SPDX-License-Identifier: MIT
"""
ui/ext_browse_view.py — Sub-aba "Browse" da página de Extensões.

Lista paginada de extensões do extensions.gnome.org. Suporta busca com
debounce, ordenação e filtro de compatibilidade com a versão do GNOME Shell.

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

import re
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

import ego_client
from constants import tr
from extension_manager import ExtMgr
from utils import gnome_shell_version

_DESC_MAX_CHARS = 140


def _clean_desc(text: str) -> str:
    """Colapsa qualquer sequência de espaço/quebra para 1 espaço e trunca."""
    if not text:
        return ""
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) > _DESC_MAX_CHARS:
        flat = flat[:_DESC_MAX_CHARS].rstrip() + "…"
    return flat


# Mapa exibido → constante do EGO
# Strings wrapped in tr() at definition so xgettext extracts them.
SORT_CHOICES = [
    (tr("Popularity"), ego_client.SORT_POPULARITY),
    (tr("Downloads"), ego_client.SORT_DOWNLOADS),
    (tr("Recent"), ego_client.SORT_RECENT),
    (tr("Name"), ego_client.SORT_NAME),
]

DEBOUNCE_MS = 400


class ExtBrowseView(Gtk.Box):
    """Sub-aba 'Browse' — pesquisa e instalação direta do extensions.gnome.org."""

    def __init__(
        self,
        pool,
        toast_cb: Callable[[str], None],
        on_open_detail: Callable[[str, int], None],
        on_after_install: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._pool = pool
        self._toast = toast_cb
        self._on_open_detail = on_open_detail
        self._on_after_install = on_after_install

        # Estado de busca
        self._query = ""
        self._page = 1
        self._num_pages = 1
        self._total = 0
        self._sort = ego_client.SORT_POPULARITY
        # Filtro de compatibilidade desligado por padrão: o EGO marca poucas
        # extensões como compatíveis com versões muito novas do Shell, e
        # ligar de cara faz a busca devolver 1-2 resultados estranhos.
        self._only_compat = False
        self._debounce_source: Optional[int] = None
        self._loading = False
        self._has_loaded_once = False

        self._build()

    # ── Construção ───────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Toolbar: busca + sort + checkbox compat
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(22)
        toolbar.set_margin_end(22)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)

        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text(tr("Search extensions on extensions.gnome.org"))
        self._search.set_hexpand(True)
        self._search.connect("search-changed", self._on_search_changed)
        self._search.connect("activate", lambda e: self._kick_search(immediate=True))
        toolbar.append(self._search)

        labels = [label for label, _key in SORT_CHOICES]
        self._sort_dd = Gtk.DropDown.new_from_strings(labels)
        self._sort_dd.set_tooltip_text(tr("Sort by"))
        self._sort_dd.connect("notify::selected", self._on_sort_changed)
        toolbar.append(self._sort_dd)

        self.append(toolbar)

        compat_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        compat_row.set_margin_start(22)
        compat_row.set_margin_end(22)
        compat_row.set_margin_bottom(4)
        self._compat_chk = Gtk.CheckButton(
            label=tr("Only compatible with GNOME {ver}").format(ver=self._shell_label())
        )
        self._compat_chk.set_active(self._only_compat)
        self._compat_chk.connect("toggled", self._on_compat_toggled)
        compat_row.append(self._compat_chk)
        self.append(compat_row)

        # Stack: estados (loading / empty / results)
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(120)
        self._stack.set_vexpand(True)

        self._stack.add_named(self._build_results_view(), "results")
        self._stack.add_named(self._build_loading_view(), "loading")
        self._stack.add_named(self._build_empty_view(), "empty")
        self._stack.add_named(self._build_initial_view(), "initial")
        self._stack.add_named(self._build_error_view(), "error")
        self._stack.set_visible_child_name("initial")

        self.append(self._stack)

        # Paginação no rodapé
        self.append(self._build_pager())

    def _build_initial_view(self) -> Gtk.Widget:
        page = Adw.StatusPage(
            title=tr("Browse extensions"),
            description=tr("Search above or hit Enter to load popular extensions."),
            icon_name="system-search-symbolic",
        )
        load_btn = Gtk.Button(label=tr("Load popular"))
        load_btn.add_css_class("suggested-action")
        load_btn.add_css_class("pill")
        load_btn.set_halign(Gtk.Align.CENTER)
        load_btn.connect("clicked", lambda b: self._kick_search(immediate=True))
        page.set_child(load_btn)
        return page

    def _build_loading_view(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        sp = Gtk.Spinner()
        sp.set_size_request(32, 32)
        sp.start()
        box.append(sp)
        lbl = Gtk.Label(label=tr("Loading…"))
        lbl.add_css_class("dim-label")
        box.append(lbl)
        return box

    def _build_empty_view(self) -> Gtk.Widget:
        return Adw.StatusPage(
            title=tr("No results"),
            description=tr("Try a different search or sort."),
            icon_name="edit-find-symbolic",
        )

    def _build_error_view(self) -> Gtk.Widget:
        page = Adw.StatusPage(
            title=tr("Could not reach extensions.gnome.org"),
            description=tr("Check your network connection and try again."),
            icon_name="network-offline-symbolic",
        )
        retry = Gtk.Button(label=tr("Retry"))
        retry.add_css_class("suggested-action")
        retry.add_css_class("pill")
        retry.set_halign(Gtk.Align.CENTER)
        retry.connect("clicked", lambda b: self._kick_search(immediate=True))
        page.set_child(retry)
        return page

    def _build_results_view(self) -> Gtk.Widget:
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(640)
        clamp.set_margin_start(22)
        clamp.set_margin_end(22)
        clamp.set_margin_bottom(22)
        # valign=START evita que o Clamp estique e o boxed-list pinte
        # area vazia abaixo dos resultados quando ha poucos itens.
        clamp.set_valign(Gtk.Align.START)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.add_css_class("boxed-list")
        self._listbox.set_valign(Gtk.Align.START)
        clamp.set_child(self._listbox)
        sc.set_child(clamp)
        return sc

    def _build_pager(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_halign(Gtk.Align.CENTER)
        bar.set_margin_top(4)
        bar.set_margin_bottom(10)

        self._prev_btn = Gtk.Button(icon_name="go-previous-symbolic")
        self._prev_btn.add_css_class("flat")
        self._prev_btn.set_tooltip_text(tr("Previous page"))
        self._prev_btn.connect("clicked", lambda b: self._goto_page(self._page - 1))
        bar.append(self._prev_btn)

        self._page_lbl = Gtk.Label(label="")
        self._page_lbl.add_css_class("caption")
        self._page_lbl.add_css_class("dim-label")
        bar.append(self._page_lbl)

        self._next_btn = Gtk.Button(icon_name="go-next-symbolic")
        self._next_btn.add_css_class("flat")
        self._next_btn.set_tooltip_text(tr("Next page"))
        self._next_btn.connect("clicked", lambda b: self._goto_page(self._page + 1))
        bar.append(self._next_btn)

        self._update_pager_state()
        return bar

    # ── Estado / interação ───────────────────────────────────────────────────

    def _shell_label(self) -> str:
        major, _ = gnome_shell_version()
        return str(major) if major > 0 else tr("Shell")

    def _shell_param(self) -> str:
        if not self._only_compat:
            return ego_client.SHELL_ALL
        major, _ = gnome_shell_version()
        return str(major) if major > 0 else ego_client.SHELL_ALL

    def _on_search_changed(self, entry) -> None:
        self._query = entry.get_text().strip()
        # Debounce
        if self._debounce_source is not None:
            GLib.source_remove(self._debounce_source)
        self._debounce_source = GLib.timeout_add(DEBOUNCE_MS, self._debounced_kick)

    def _debounced_kick(self) -> bool:
        self._debounce_source = None
        self._kick_search(immediate=True)
        return False

    def _kick_search(self, immediate: bool = False) -> None:
        self._page = 1
        self._run_search()

    def _on_sort_changed(self, dd, _pspec) -> None:
        idx = dd.get_selected()
        if 0 <= idx < len(SORT_CHOICES):
            self._sort = SORT_CHOICES[idx][1]
            self._kick_search(immediate=True)

    def _on_compat_toggled(self, btn) -> None:
        self._only_compat = btn.get_active()
        self._kick_search(immediate=True)

    def _goto_page(self, page: int) -> None:
        if page < 1 or page > self._num_pages:
            return
        self._page = page
        self._run_search()

    def _update_pager_state(self) -> None:
        if self._total <= 0:
            self._page_lbl.set_label("")
            self._prev_btn.set_sensitive(False)
            self._next_btn.set_sensitive(False)
            return
        self._page_lbl.set_label(tr("Page {p} of {t}").format(p=self._page, t=self._num_pages))
        self._prev_btn.set_sensitive(self._page > 1)
        self._next_btn.set_sensitive(self._page < self._num_pages)

    def _run_search(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._stack.set_visible_child_name("loading")

        query = self._query
        page = self._page
        sort = self._sort
        shell = self._shell_param()

        def task():
            result = ego_client.search(
                query=query,
                page=page,
                sort=sort,
                shell_version=shell,
            )
            GLib.idle_add(self._on_search_done, result)

        self._pool.submit(task)

    def _on_search_done(self, result) -> bool:
        self._loading = False
        self._has_loaded_once = True
        if result is None:
            self._stack.set_visible_child_name("error")
            return False
        self._num_pages = max(1, result.num_pages)
        self._total = result.total
        if not result.extensions:
            self._stack.set_visible_child_name("empty")
            self._update_pager_state()
            return False
        self._render_results(result.extensions)
        self._stack.set_visible_child_name("results")
        self._update_pager_state()
        return False

    def _render_results(self, items) -> None:
        # Limpa a lista
        child = self._listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._listbox.remove(child)
            child = nxt

        for summary in items:
            self._listbox.append(self._make_row(summary))

    def _make_row(self, summary) -> Gtk.Widget:
        installed = ExtMgr.is_installed(summary.uuid)

        row = Adw.ActionRow()
        row.set_title(GLib.markup_escape_text(summary.name))
        subtitle = _clean_desc(summary.description)
        if not subtitle and summary.creator:
            subtitle = tr("by {author}").format(author=summary.creator)
        if subtitle:
            row.set_subtitle(GLib.markup_escape_text(subtitle))
        row.set_subtitle_lines(2)
        row.set_activatable(False)

        ico = Gtk.Image.new_from_icon_name("application-x-addon-symbolic")
        ico.set_pixel_size(40)
        ico.add_css_class("ext-icon")
        if summary.icon_url:
            self._load_icon_async(ico, summary.icon_url)
        row.add_prefix(ico)

        details_btn = Gtk.Button(label=tr("Details"))
        details_btn.add_css_class("pill")
        details_btn.set_valign(Gtk.Align.CENTER)
        details_btn.set_tooltip_text(tr("View extension details"))
        details_btn.connect(
            "clicked",
            lambda b, _u=summary.uuid, _p=summary.pk: self._on_open_detail(_u, _p),
        )
        row.add_suffix(details_btn)

        if installed:
            tag = Gtk.Label(label=tr("Installed"))
            tag.add_css_class("caption")
            tag.add_css_class("dim-label")
            tag.set_valign(Gtk.Align.CENTER)
            row.add_suffix(tag)
        else:
            install_btn = Gtk.Button(label=tr("Install"))
            install_btn.add_css_class("suggested-action")
            install_btn.add_css_class("pill")
            install_btn.set_valign(Gtk.Align.CENTER)
            install_btn.connect(
                "clicked",
                lambda b, _s=summary: self._do_install(_s, None),
            )
            row.add_suffix(install_btn)

        return row

    def _load_icon_async(self, image: Gtk.Image, icon_url: str) -> None:
        """Baixa o ícone da extensão em background e troca o placeholder."""

        def task():
            path = ego_client.fetch_screenshot(icon_url)
            if path is None:
                return
            GLib.idle_add(_apply_icon, str(path))

        def _apply_icon(p: str) -> bool:
            try:
                image.set_from_file(p)
            except Exception:
                pass
            return False

        self._pool.submit(task)

    def _do_install(self, summary, card) -> None:
        def task():
            ok, method = ExtMgr.install(summary.uuid, summary.pk, "")
            if ok:
                ExtMgr.enable_after_install(summary.uuid)
                GLib.idle_add(
                    self._toast,
                    tr("{name} installed and enabled. Restart the session to use it.").format(
                        name=summary.name
                    ),
                )
                GLib.idle_add(self._on_after_install)
                # Re-render só este card via refresh do flow inteiro (mais simples e barato)
                GLib.idle_add(self._run_search)
            else:
                GLib.idle_add(self._toast, tr("Install failed") + f": {method}")

        self._pool.submit(task)
