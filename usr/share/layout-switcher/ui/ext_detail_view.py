# SPDX-License-Identifier: MIT
"""
ui/ext_detail_view.py — Página de detalhes de uma extensão (carrossel +
comentários).

É uma `Adw.NavigationPage` empurrada na pilha do `Adw.NavigationView` da
sub-aba Browse quando o usuário clica em "Details".

DEVELOPER NOTE — DO NOT name any variable `_` in this file.
"""

from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, GLib, Gtk, Pango

import ego_client
from constants import EGO_BASE_URL, tr
from extension_manager import ExtMgr
from utils import gnome_shell_version, run_cmd


class ExtDetailView(Adw.NavigationPage):
    """Página de detalhes de uma extensão do EGO."""

    def __init__(
        self,
        uuid: str,
        pk: int,
        pool,
        toast_cb: Callable[[str], None],
        on_after_install: Callable[[], None],
    ) -> None:
        super().__init__()
        self._uuid = uuid
        self._pk = pk
        self._pool = pool
        self._toast = toast_cb
        self._on_after_install = on_after_install
        self._info: Optional[ego_client.ExtensionInfo] = None
        self._action_btn: Optional[Gtk.Button] = None

        self.set_title(uuid.split("@")[0] or uuid)
        self._build()
        # carrega info em background ao apresentar
        self._pool.submit(self._load_info)

    # ── Construção ───────────────────────────────────────────────────────────

    def _build(self) -> None:
        toolbar = Adw.ToolbarView()

        hdr = Adw.HeaderBar()
        # Janela principal já tem botões de min/max/close — esconder aqui evita duplicar.
        hdr.set_show_end_title_buttons(False)
        hdr.set_show_start_title_buttons(False)
        self._title = Adw.WindowTitle(title=self.get_title(), subtitle="")
        hdr.set_title_widget(self._title)

        self._action_btn = Gtk.Button(label=tr("Install"))
        self._action_btn.add_css_class("suggested-action")
        self._action_btn.add_css_class("pill")
        self._action_btn.set_sensitive(False)
        self._action_btn.connect("clicked", lambda b: self._on_action_clicked())
        hdr.pack_end(self._action_btn)

        toolbar.add_top_bar(hdr)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(820)
        clamp.set_tightening_threshold(640)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._content.set_margin_start(20)
        self._content.set_margin_end(20)
        self._content.set_margin_top(16)
        self._content.set_margin_bottom(28)

        self._content.append(self._build_loading_placeholder())

        clamp.set_child(self._content)
        scrolled.set_child(clamp)
        toolbar.set_content(scrolled)

        self.set_child(toolbar)

    def _build_loading_placeholder(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        sp = Gtk.Spinner()
        sp.set_size_request(28, 28)
        sp.start()
        box.append(sp)
        lbl = Gtk.Label(label=tr("Loading extension details…"))
        lbl.add_css_class("dim-label")
        box.append(lbl)
        return box

    def _build_error_placeholder(self) -> Gtk.Widget:
        page = Adw.StatusPage(
            title=tr("Could not load details"),
            description=tr("Check your network connection and try again."),
            icon_name="network-offline-symbolic",
        )
        retry = Gtk.Button(label=tr("Retry"))
        retry.add_css_class("suggested-action")
        retry.add_css_class("pill")
        retry.set_halign(Gtk.Align.CENTER)
        retry.connect("clicked", lambda b: self._pool.submit(self._load_info))
        page.set_child(retry)
        return page

    # ── Carregamento ─────────────────────────────────────────────────────────

    def _shell_param(self) -> str:
        major, _ = gnome_shell_version()
        return str(major) if major > 0 else ego_client.SHELL_ALL

    def _load_info(self) -> None:
        info = ego_client.info(self._uuid, shell_version=self._shell_param())
        GLib.idle_add(self._render, info)

    def _render(self, info: Optional[ego_client.ExtensionInfo]) -> bool:
        # Limpa o conteúdo
        child = self._content.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._content.remove(child)
            child = nxt

        if info is None:
            self._content.append(self._build_error_placeholder())
            return False

        self._info = info
        self._title.set_title(info.name or self._uuid)
        if info.creator:
            self._title.set_subtitle(tr("by {author}").format(author=info.creator))
        self._refresh_action_button()

        # Carrossel de screenshots
        if info.screenshots:
            self._content.append(self._build_carousel(info.screenshots))

        # Bloco de métricas + descrição
        self._content.append(self._build_overview(info))

        if info.description:
            self._content.append(self._build_description(info.description))

        if info.comments:
            self._content.append(self._build_comments(info.comments))

        self._content.append(self._build_links(info))
        return False

    def _build_carousel(self, screenshots: List[ego_client.ScreenshotRef]) -> Gtk.Widget:
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        carousel = Adw.Carousel()
        carousel.set_size_request(-1, 320)
        carousel.set_allow_long_swipes(True)
        carousel.set_spacing(8)

        placeholders: List[Gtk.Picture] = []
        for shot in screenshots[:6]:  # cap em 6 para não esticar download
            pic = Gtk.Picture()
            pic.set_can_shrink(True)
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            pic.set_size_request(-1, 320)
            carousel.append(pic)
            placeholders.append(pic)
            self._pool.submit(self._fetch_screenshot, shot.url, pic)

        wrapper.append(carousel)

        if len(placeholders) > 1:
            indic = Adw.CarouselIndicatorDots()
            indic.set_carousel(carousel)
            indic.set_halign(Gtk.Align.CENTER)
            wrapper.append(indic)

        return wrapper

    def _fetch_screenshot(self, url: str, picture: Gtk.Picture) -> None:
        path = ego_client.fetch_screenshot(url)
        if path is None:
            return
        GLib.idle_add(picture.set_filename, str(path))

    def _build_overview(self, info: ego_client.ExtensionInfo) -> Gtk.Widget:
        grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        grid.set_homogeneous(False)

        if info.rating > 0 and info.rating_count > 0:
            grid.append(
                self._stat(f"★ {info.rating:.1f}", tr("{n} ratings").format(n=info.rating_count))
            )
        if info.downloads > 0:
            grid.append(self._stat(self._fmt_downloads(info.downloads), tr("downloads")))
        compat = self._compat_label(info)
        if compat:
            grid.append(self._stat(compat, tr("compatibility")))
        return grid

    def _stat(self, value: str, caption: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        v = Gtk.Label(label=value)
        v.add_css_class("title-3")
        v.set_halign(Gtk.Align.START)
        box.append(v)
        c = Gtk.Label(label=caption)
        c.add_css_class("caption")
        c.add_css_class("dim-label")
        c.set_halign(Gtk.Align.START)
        box.append(c)
        return box

    def _compat_label(self, info: ego_client.ExtensionInfo) -> str:
        svm = info.shell_version_map or {}
        if not svm:
            return ""
        keys = []
        for k in svm.keys():
            try:
                keys.append(int(str(k).split(".")[0]))
            except (TypeError, ValueError):
                continue
        if not keys:
            return ""
        keys.sort()
        if len(keys) == 1:
            return f"GNOME {keys[0]}"
        return f"GNOME {keys[0]}–{keys[-1]}"

    def _fmt_downloads(self, n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}k"
        return str(n)

    def _build_description(self, text: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        h = Gtk.Label(label=tr("Description"))
        h.add_css_class("heading")
        h.set_halign(Gtk.Align.START)
        box.append(h)
        body = Gtk.Label(label=text)
        body.set_wrap(True)
        body.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body.set_halign(Gtk.Align.START)
        body.set_xalign(0)
        body.set_selectable(True)
        box.append(body)
        return box

    def _build_comments(self, comments: List[ego_client.CommentEntry]) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        h = Gtk.Label(label=tr("Recent comments"))
        h.add_css_class("heading")
        h.set_halign(Gtk.Align.START)
        box.append(h)

        lb = Gtk.ListBox()
        lb.add_css_class("boxed-list")
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        for comment in comments[:5]:
            lb.append(self._comment_row(comment))
        box.append(lb)

        if self._pk > 0:
            link = Gtk.Button(label=tr("View all comments on extensions.gnome.org"))
            link.add_css_class("flat")
            link.add_css_class("caption")
            link.set_halign(Gtk.Align.START)
            link.connect(
                "clicked",
                lambda b: run_cmd(
                    ["xdg-open", f"{EGO_BASE_URL}/extension/{self._pk}/"],
                    timeout=5,
                ),
            )
            box.append(link)
        return box

    def _comment_row(self, comment: ego_client.CommentEntry) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.set_margin_start(12)
        inner.set_margin_end(12)
        inner.set_margin_top(8)
        inner.set_margin_bottom(8)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        author = Gtk.Label(label=comment.author)
        author.add_css_class("body")
        author.set_halign(Gtk.Align.START)
        head.append(author)

        if comment.rating > 0:
            stars = "★" * max(0, min(5, comment.rating))
            rl = Gtk.Label(label=stars)
            rl.add_css_class("caption")
            rl.add_css_class("accent")
            head.append(rl)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        head.append(spacer)

        if comment.date:
            dt = Gtk.Label(label=comment.date)
            dt.add_css_class("caption")
            dt.add_css_class("dim-label")
            head.append(dt)

        inner.append(head)

        body = Gtk.Label(label=comment.text)
        body.set_wrap(True)
        body.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body.set_halign(Gtk.Align.START)
        body.set_xalign(0)
        body.add_css_class("caption")
        inner.append(body)

        row.set_child(inner)
        return row

    def _build_links(self, info: ego_client.ExtensionInfo) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        h = Gtk.Label(label=tr("Links"))
        h.add_css_class("heading")
        h.set_halign(Gtk.Align.START)
        box.append(h)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        if info.homepage:
            row.append(self._link_button(tr("Homepage"), info.homepage))
        if self._pk > 0:
            row.append(
                self._link_button(
                    tr("View on GNOME Extensions"),
                    f"{EGO_BASE_URL}/extension/{self._pk}/",
                )
            )
        if info.license:
            lic = Gtk.Label(label=tr("License: {lic}").format(lic=info.license))
            lic.add_css_class("caption")
            lic.add_css_class("dim-label")
            lic.set_halign(Gtk.Align.START)
            row.append(lic)
        box.append(row)
        return box

    def _link_button(self, label: str, url: str) -> Gtk.Button:
        b = Gtk.Button(label=label)
        b.add_css_class("flat")
        b.connect("clicked", lambda btn, _u=url: run_cmd(["xdg-open", _u], timeout=5))
        return b

    # ── Botão de ação (Install / Update / Open prefs) ────────────────────────

    def _refresh_action_button(self) -> None:
        if self._action_btn is None:
            return
        self._action_btn.set_sensitive(True)
        if ExtMgr.is_installed(self._uuid):
            # Já instalada — verifica se há update
            try:
                latest = ego_client.latest_version(self._uuid, self._shell_param())
            except Exception:
                latest = None
            current = ExtMgr.installed_version(self._uuid)
            if latest is not None and current > 0 and latest > current:
                self._action_btn.set_label(tr("Update"))
                self._action_btn.remove_css_class("flat")
                self._action_btn.add_css_class("suggested-action")
                self._mode = "update"
            else:
                self._action_btn.set_label(tr("Open prefs"))
                self._action_btn.add_css_class("flat")
                self._action_btn.remove_css_class("suggested-action")
                self._mode = "prefs"
        else:
            self._action_btn.set_label(tr("Install"))
            self._action_btn.add_css_class("suggested-action")
            self._action_btn.remove_css_class("flat")
            self._mode = "install"

    def _on_action_clicked(self) -> None:
        mode = getattr(self, "_mode", "install")
        if mode == "prefs":
            ExtMgr.open_prefs(self._uuid)
            return
        if mode in ("install", "update"):
            self._action_btn.set_sensitive(False)
            self._action_btn.set_label(tr("Working…"))
            uuid = self._uuid
            pk = self._pk

            def task():
                if mode == "update":
                    ok, msg = ExtMgr.update(uuid, pk)
                else:
                    ok, msg = ExtMgr.install(uuid, pk, "")
                    if ok:
                        ExtMgr.enable_after_install(uuid)
                GLib.idle_add(self._on_action_done, ok, msg, mode)

            self._pool.submit(task)

    def _on_action_done(self, ok: bool, msg: str, mode: str) -> bool:
        if ok:
            name = self._info.name if self._info else self._uuid
            if mode == "update":
                self._toast(tr("{name} updated").format(name=name))
            else:
                self._toast(
                    tr("{name} installed and enabled. Restart the session to use it.").format(
                        name=name
                    )
                )
            self._on_after_install()
        else:
            self._toast(tr("Operation failed") + f": {msg}")
        self._refresh_action_button()
        return False
