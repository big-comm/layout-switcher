# SPDX-License-Identifier: MIT
"""Tests for layout_applier.py — apply layout via dconf load."""

from pathlib import Path
from unittest.mock import patch

from layout_applier import LayoutApplier


class TestLayoutApplier:
    @patch("layout_applier.time.sleep")
    @patch(
        "layout_applier.LayoutApplier._preserve_user_color_scheme",
        side_effect=lambda data: data,
    )
    @patch("layout_applier.LayoutApplier._reload_visual_extensions")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_user_unit", return_value=True)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_apply_full_flow(
        self,
        mock_run,
        _has,
        mock_persist,
        mock_reload_visual,
        mock_preserve_theme,
        _sleep,
        tmp_path,
    ):
        """Cobre fluxo completo: mutter gdbus probe -> dtp dconf fallback (5
        reads) -> read enabled-ext (before, vazio) -> stop watcher Qt ->
        persist -> orphan scan -> load -> read enabled-ext (after) ->
        start watcher Qt."""
        layout = tmp_path / "classic.txt"
        layout.write_text("[/]\nfoo='bar'")

        ok, msg = LayoutApplier.apply(layout)
        assert ok is True

        # 1 mutter gdbus probe + 5 dconf reads (dtp fallback) + 1 read
        # enabled-extensions (before) + stop watcher + dconf dump scan +
        # load + 1 read enabled-extensions (after) + start watcher = 12.
        assert mock_run.call_count == 12
        calls = [c.args[0] for c in mock_run.call_args_list]
        # 1: gdbus probe to mutter for monitor IDs
        assert calls[0][0] == "gdbus"
        assert "Mutter.DisplayConfig" in calls[0][4]
        # 2-6: dtp monitor-key probes (fallback because mutter returned empty)
        assert all(c[:2] == ["dconf", "read"] for c in calls[1:6])
        assert all("dash-to-panel" in c[2] for c in calls[1:6])
        # 7: enabled-extensions before
        assert calls[6] == ["dconf", "read", "/org/gnome/shell/enabled-extensions"]
        # 8: stop Qt theme watcher
        assert calls[7][:3] == ["systemctl", "--user", "stop"]
        # 9-10: orphan scan + load (no per-UUID disables since before=[])
        assert calls[8] == ["dconf", "dump", "/"]
        assert calls[9] == ["dconf", "load", "/"]
        # 11: enabled-extensions after
        assert calls[10] == ["dconf", "read", "/org/gnome/shell/enabled-extensions"]
        # 12: start Qt theme watcher
        assert calls[11][:3] == ["systemctl", "--user", "start"]
        mock_preserve_theme.assert_called_once()
        mock_persist.assert_called_once()
        mock_reload_visual.assert_not_called()

    @patch("layout_applier.time.sleep")
    @patch(
        "layout_applier.LayoutApplier._preserve_user_color_scheme",
        side_effect=lambda data: data,
    )
    @patch("layout_applier.LayoutApplier._reload_visual_extensions")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_user_unit", return_value=False)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_apply_without_sync_service(
        self,
        mock_run,
        _has,
        mock_persist,
        mock_reload_visual,
        mock_preserve_theme,
        _sleep,
        tmp_path,
    ):
        """Quando o watcher Qt nao existe, systemctl e pulado."""
        layout = tmp_path / "x.txt"
        layout.write_text("[/]\nx=1")

        ok, _ = LayoutApplier.apply(layout)
        assert ok is True
        # 1 gdbus mutter probe + 5 dtp dconf reads + 1 enabled-ext read
        # (before) + dconf dump scan + load + 1 enabled-ext read (after) = 10.
        # No systemctl stop/start (watcher ausente), no per-UUID disables.
        assert mock_run.call_count == 10
        # 1st: gdbus mutter probe
        assert mock_run.call_args_list[0].args[0][0] == "gdbus"
        # 2nd-6th: reads de dash-to-panel
        assert all(c.args[0][:2] == ["dconf", "read"] for c in mock_run.call_args_list[1:6])
        # 7th: enabled-extensions before
        assert mock_run.call_args_list[6].args[0] == [
            "dconf",
            "read",
            "/org/gnome/shell/enabled-extensions",
        ]
        # 8th-9th: orphan scan + load
        assert mock_run.call_args_list[7].args[0] == ["dconf", "dump", "/"]
        assert mock_run.call_args_list[8].args[0] == ["dconf", "load", "/"]
        # 10th: enabled-extensions after
        assert mock_run.call_args_list[9].args[0] == [
            "dconf",
            "read",
            "/org/gnome/shell/enabled-extensions",
        ]
        mock_preserve_theme.assert_called_once()
        mock_persist.assert_called_once()
        mock_reload_visual.assert_not_called()

    def test_apply_nonexistent_file(self):
        ok, msg = LayoutApplier.apply(Path("/nonexistent/layout.txt"))
        assert ok is False
        assert "not found" in msg

    def test_apply_none_path(self):
        ok, msg = LayoutApplier.apply(None)
        assert ok is False

    def test_apply_empty_file(self, tmp_path):
        layout = tmp_path / "empty.txt"
        layout.write_text("")
        ok, msg = LayoutApplier.apply(layout)
        assert ok is False
        assert "empty" in msg.lower()

    @patch("layout_applier.time.sleep")
    @patch(
        "layout_applier.LayoutApplier._preserve_user_color_scheme",
        side_effect=lambda data: data,
    )
    @patch("layout_applier.LayoutApplier._reload_visual_extensions")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_user_unit", return_value=True)
    @patch("layout_applier.run_cmd")
    def test_apply_load_failure_still_cleans_up(
        self,
        mock_run,
        _has,
        mock_persist,
        mock_reload_visual,
        _preserve_theme,
        _sleep,
        tmp_path,
    ):
        """Se o dconf load falhar: watcher Qt reinicia e shell nao recarrega."""
        # 1 mutter gdbus probe (returns empty so dconf fallback runs),
        # 5 dtp dconf reads, read-before (vazio -> []), stop OK,
        # orphan scan OK, load FAIL, start OK (finally). Sem read-after.
        mock_run.side_effect = [
            (True, ""),  # gdbus mutter probe
            (True, ""),  # dtp probe 1
            (True, ""),  # dtp probe 2
            (True, ""),  # dtp probe 3
            (True, ""),  # dtp probe 4
            (True, ""),  # dtp probe 5
            (True, "[]"),  # read enabled-extensions (before)
            (True, ""),  # systemctl stop watcher
            (True, ""),  # dconf dump orphan scan
            (False, "dconf error"),  # dconf load FAILS
            (True, ""),  # systemctl start watcher (finally)
        ]
        layout = tmp_path / "bad.txt"
        layout.write_text("[/]\ndata=true")

        ok, msg = LayoutApplier.apply(layout)
        assert ok is False
        mock_persist.assert_called_once()
        mock_reload_visual.assert_not_called()
        # Garantir que a ultima chamada foi start do watcher (finally rodou)
        assert mock_run.call_args_list[-1].args[0][:3] == [
            "systemctl",
            "--user",
            "start",
        ]

    @patch("layout_applier.time.sleep")
    @patch("layout_applier.ShellReloader.list_extensions_state", return_value={})
    @patch(
        "layout_applier.ShellReloader.enable_extension_dbus",
        return_value=(False, "timed out after 2s"),
    )
    def test_disable_extensions_stops_after_repeated_dbus_timeouts(
        self,
        mock_disable,
        _mock_states,
        mock_sleep,
    ):
        """Repeated Shell DBus timeouts must not stall the apply for minutes."""
        ok = LayoutApplier._disable_extensions_in_order(
            ["z@ext", "a@ext", "m@ext", "b@ext", "c@ext"]
        )

        assert ok is False
        assert mock_disable.call_count == LayoutApplier._MAX_DISABLE_DBUS_TIMEOUTS
        assert mock_sleep.call_count == 0
        assert all(
            call.kwargs["timeout"] == LayoutApplier._SHELL_DBUS_TIMEOUT_SEC
            for call in mock_disable.call_args_list
        )

    @patch("layout_applier.time.sleep")
    @patch(
        "layout_applier.ShellReloader.enable_extension_dbus",
        return_value=(True, ""),
    )
    @patch(
        "layout_applier.ShellReloader.list_extensions_state",
        return_value={"err@ext": 3, "live@ext": 1},
    )
    def test_disable_extensions_skips_non_live_shell_state(
        self,
        _mock_states,
        mock_disable,
        mock_sleep,
    ):
        """Do not call DisableExtension for UUIDs Shell already disabled/errored."""
        ok = LayoutApplier._disable_extensions_in_order(
            ["err@ext", "live@ext"],
            sort=False,
        )

        assert ok is True
        mock_disable.assert_called_once_with(
            "live@ext",
            enable=False,
            timeout=LayoutApplier._SHELL_DBUS_TIMEOUT_SEC,
        )
        mock_sleep.assert_called_once()

    def test_leaving_extensions_disable_newest_first(self):
        """Leaving extensions follow reverse active order to avoid Shell rebase."""
        before = [
            "older@ext",
            "arcmenu@arcmenu.com",
            "dash-to-panel@jderose9.github.com",
            "copyous@boerdereinar.dev",
        ]
        leaving = {
            "dash-to-panel@jderose9.github.com",
            "arcmenu@arcmenu.com",
            "unknown@ext",
        }

        ordered = LayoutApplier._leaving_extensions_in_disable_order(before, leaving)

        assert ordered == [
            "dash-to-panel@jderose9.github.com",
            "arcmenu@arcmenu.com",
            "unknown@ext",
        ]

    def test_split_shell_extension_switch_keys_loads_extensions_last(self):
        """Extension enable lists are loaded after extension settings."""
        data = (
            "[org/gnome/shell]\n"
            "favorite-apps=['a.desktop']\n"
            "enabled-extensions=['dash-to-panel@jderose9.github.com']\n"
            "disabled-extensions=['dash-to-dock@micxgx.gmail.com']\n"
            "\n"
            "[org/gnome/shell/extensions/dash-to-panel]\n"
            "panel-sizes='{\"monitor\":42}'\n"
        )

        settings_data, switch_data = LayoutApplier._split_shell_extension_switch_keys(data)

        assert "favorite-apps=['a.desktop']" in settings_data
        assert "panel-sizes" in settings_data
        assert "enabled-extensions" not in settings_data
        assert "disabled-extensions" not in settings_data
        assert switch_data == (
            "[org/gnome/shell]\n"
            "disabled-extensions=['dash-to-dock@micxgx.gmail.com']\n"
            "enabled-extensions=['dash-to-panel@jderose9.github.com']\n"
        )

    def test_replace_existing_dconf_key_does_not_append_duplicate_section(self):
        """Replacing an early section must not append the same section at EOF."""
        data = (
            "[org/gnome/desktop/interface]\n"
            "gtk-theme='adw-gtk3'\n"
            "\n"
            "[org/gtk/settings/file-chooser]\n"
            "show-hidden=false\n"
        )

        out = LayoutApplier._replace_or_add_dconf_key(
            data,
            "/org/gnome/desktop/interface",
            "gtk-theme",
            "'adw-gtk3-dark'",
        )

        assert out.count("[org/gnome/desktop/interface]") == 1
        assert "gtk-theme='adw-gtk3-dark'" in out
        assert out.rstrip().endswith("show-hidden=false")

    @patch("layout_applier.run_cmd")
    def test_preserve_user_dark_color_scheme(self, mock_run):
        """Original layouts keep user dark mode but restore factory themes."""
        light_style = "light-style@gnome-shell-extensions.gcampax.github.com"
        user_theme = "user-theme@gnome-shell-extensions.gcampax.github.com"
        data = (
            "[org/gnome/desktop/interface]\n"
            "gtk-theme='adw-gtk3'\n"
            "icon-theme='bigicons-papient'\n"
            "\n"
            "[org/gnome/shell]\n"
            f"disabled-extensions=['{user_theme}']\n"
            f"enabled-extensions=['{light_style}', 'dash-to-panel@jderose9.github.com']\n"
            "\n"
            "[org/gnome/shell/extensions/user-theme]\n"
            "name=''\n"
        )
        mock_run.side_effect = [
            (True, "'prefer-dark'"),
        ]

        out = LayoutApplier._preserve_user_color_scheme(data)

        assert "color-scheme='prefer-dark'" in out
        assert "gtk-theme='adw-gtk3'\n" in out
        assert "icon-theme='bigicons-papient'\n" in out
        assert "name=''" in out
        shell = LayoutApplier._section_key_values(out, "/org/gnome/shell")
        enabled = LayoutApplier._string_list(shell["enabled-extensions"])
        disabled = LayoutApplier._string_list(shell["disabled-extensions"])
        assert user_theme in enabled
        assert light_style not in enabled
        assert light_style in disabled
        assert user_theme not in disabled

    @patch("layout_applier.run_cmd")
    def test_preserve_user_light_color_scheme(self, mock_run):
        """Original layouts keep user light mode but restore factory themes."""
        light_style = "light-style@gnome-shell-extensions.gcampax.github.com"
        user_theme = "user-theme@gnome-shell-extensions.gcampax.github.com"
        data = (
            "[org/gnome/desktop/interface]\n"
            "color-scheme='prefer-dark'\n"
            "gtk-theme='adw-gtk3-dark'\n"
            "icon-theme='bigicons-papient-dark'\n"
            "\n"
            "[org/gnome/shell]\n"
            f"disabled-extensions=['{light_style}']\n"
            f"enabled-extensions=['{user_theme}', 'dash-to-dock@micxgx.gmail.com']\n"
            "\n"
            "[org/gnome/shell/extensions/user-theme]\n"
            "name='Big-Blue'\n"
        )
        mock_run.side_effect = [
            (True, "'prefer-light'"),
        ]

        out = LayoutApplier._preserve_user_color_scheme(data)

        assert "color-scheme='prefer-light'" in out
        assert "gtk-theme='adw-gtk3-dark'" in out
        assert "icon-theme='bigicons-papient-dark'" in out
        assert "name='Big-Blue'" in out
        shell = LayoutApplier._section_key_values(out, "/org/gnome/shell")
        enabled = LayoutApplier._string_list(shell["enabled-extensions"])
        disabled = LayoutApplier._string_list(shell["disabled-extensions"])
        assert light_style in enabled
        assert user_theme not in enabled
        assert user_theme in disabled
        assert light_style not in disabled

    @patch("layout_applier.run_cmd")
    def test_preserve_user_color_scheme_uses_effective_gsettings(self, mock_run):
        """Preserve light/dark even when dconf has no explicit override."""
        data = (
            "[org/gnome/desktop/interface]\n"
            "color-scheme='prefer-dark'\n"
            "gtk-theme='adw-gtk3-dark'\n"
        )
        mock_run.side_effect = [
            (True, ""),  # dconf read: default/unset
            (True, "'prefer-light'"),  # gsettings effective value
        ]

        out = LayoutApplier._preserve_user_color_scheme(data)

        assert "color-scheme='prefer-light'" in out
        assert "gtk-theme='adw-gtk3-dark'" in out
        assert mock_run.call_args_list[0].args[0] == [
            "dconf",
            "read",
            "/org/gnome/desktop/interface/color-scheme",
        ]
        assert mock_run.call_args_list[1].args[0] == [
            "gsettings",
            "get",
            "org.gnome.desktop.interface",
            "color-scheme",
        ]

    @patch("layout_applier.time.sleep")
    @patch("layout_applier.ShellReloader.reload_extension", return_value=True)
    def test_reload_visual_extensions_uses_reload_timeout(
        self,
        mock_reload,
        mock_sleep,
    ):
        """Visual reloads get enough time for heavy Shell extensions."""
        LayoutApplier._reload_visual_extensions(
            ["dash-to-dock@micxgx.gmail.com", "blur-my-shell@aunetx"]
        )

        assert mock_reload.call_count == 1
        assert mock_sleep.call_count == 1
        assert mock_reload.call_args.args[0] == "blur-my-shell@aunetx"
        assert all(
            call.kwargs["timeout"] == LayoutApplier._SHELL_RELOAD_TIMEOUT_SEC
            for call in mock_reload.call_args_list
        )

    @patch("layout_applier.time.sleep")
    @patch("layout_applier.ShellReloader.reload_extension", return_value=True)
    def test_reload_visual_extensions_skips_fragile_or_slow_extensions(
        self,
        mock_reload,
        _mock_sleep,
    ):
        """Avoid ReloadExtension for extensions that error or block."""
        LayoutApplier._reload_visual_extensions(
            [
                "arcmenu@arcmenu.com",
                "dash-to-panel@jderose9.github.com",
                "dash-to-dock@micxgx.gmail.com",
                "big-shot@bigcommunity.org",
            ]
        )

        mock_reload.assert_not_called()

    @patch("layout_applier.LayoutApplier._reload_visual_extensions")
    @patch("layout_applier.LayoutApplier._enabled_extensions", return_value={"after@ext"})
    @patch("layout_applier.LayoutApplier._disable_extensions_in_order", return_value=False)
    @patch("layout_applier.LayoutApplier._reset_orphan_keys")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_user_unit", return_value=False)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_load_skips_remaining_shell_dbus_after_breaker(
        self,
        mock_run,
        _has,
        mock_persist,
        _reset,
        mock_disable,
        _enabled,
        mock_reload,
    ):
        """Once Shell DBus times out repeatedly, finish via dconf without more DBus."""
        data = "[org/gnome/shell]\nenabled-extensions=['stay@ext']\n"

        ok, _ = LayoutApplier.load_dconf_safely(
            data,
            before_uuids=["leave@ext", "stay@ext"],
        )

        assert ok is True
        assert mock_disable.call_count == 1
        assert mock_disable.call_args.args[0] == ["leave@ext"]
        assert mock_disable.call_args.kwargs == {"sort": False}
        mock_persist.assert_called_once()
        mock_reload.assert_not_called()
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0].args[0] == ["dconf", "load", "/"]
        assert mock_run.call_args_list[0].kwargs["stdin_text"] == "[org/gnome/shell]\n"
        assert mock_run.call_args_list[1].args[0] == ["dconf", "load", "/"]
        assert "enabled-extensions=['stay@ext']" in mock_run.call_args_list[1].kwargs["stdin_text"]

    @patch("layout_applier.time.sleep")
    @patch("layout_applier.LayoutApplier._reload_visual_extensions")
    @patch(
        "layout_applier.LayoutApplier._enabled_extensions",
        return_value=[
            "stay@ext",
            "dash-to-panel@jderose9.github.com",
        ],
    )
    @patch("layout_applier.LayoutApplier._disable_extensions_in_order", return_value=True)
    @patch("layout_applier.LayoutApplier._reset_orphan_keys")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_user_unit", return_value=False)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_load_restarts_staying_dash_to_panel_before_other_leavers(
        self,
        _mock_run,
        _has,
        _persist,
        _reset,
        mock_disable,
        _enabled,
        _reload,
        mock_sleep,
    ):
        """Protect staying dash-to-panel from Shell rebase during removals."""
        data = (
            "[org/gnome/shell]\n"
            "enabled-extensions=['stay@ext', 'dash-to-panel@jderose9.github.com']\n"
        )

        ok, _ = LayoutApplier.load_dconf_safely(
            data,
            before_uuids=[
                "leave@ext",
                "dash-to-panel@jderose9.github.com",
                "stay@ext",
            ],
        )

        assert ok is True
        assert mock_disable.call_args.args[0] == [
            "dash-to-panel@jderose9.github.com",
            "leave@ext",
        ]
        assert mock_disable.call_args.kwargs == {"sort": False}
        mock_sleep.assert_any_call(LayoutApplier._DTP_REENABLE_SETTLE_SEC)

    @patch("layout_applier.time.sleep")
    @patch("layout_applier.LayoutApplier._reload_visual_extensions")
    @patch(
        "layout_applier.LayoutApplier._enabled_extensions",
        return_value=["dash-to-panel@jderose9.github.com"],
    )
    @patch("layout_applier.LayoutApplier._disable_extensions_in_order", return_value=True)
    @patch("layout_applier.LayoutApplier._reset_orphan_keys")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_user_unit", return_value=False)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_load_restarts_dash_to_panel_when_reapplying_same_layout(
        self,
        _mock_run,
        _has,
        _persist,
        _reset,
        mock_disable,
        _enabled,
        _reload,
        mock_sleep,
    ):
        """Reapplying a DTP layout must rebuild DTP panel actors."""
        data = (
            "[org/gnome/shell]\n"
            "enabled-extensions=['dash-to-panel@jderose9.github.com']\n"
        )

        ok, _ = LayoutApplier.load_dconf_safely(
            data,
            before_uuids=["dash-to-panel@jderose9.github.com"],
        )

        assert ok is True
        assert mock_disable.call_args.args[0] == [
            "dash-to-panel@jderose9.github.com",
        ]
        assert mock_disable.call_args.kwargs == {"sort": False}
        mock_sleep.assert_any_call(LayoutApplier._DTP_REENABLE_SETTLE_SEC)

    @patch("layout_applier.run_cmd")
    def test_reset_orphan_keys_resets_leaving_branches_and_stale_keys(
        self,
        mock_run,
    ):
        """Treat layout text as exact state, not a merge patch."""
        live = (
            "[org/gnome/shell/extensions/leaving]\n"
            "old=true\n"
            "\n"
            "[org/gnome/shell/extensions/staying]\n"
            "keep=true\n"
            "old=true\n"
        )
        target = "[org/gnome/shell/extensions/staying]\nkeep=true\n"
        mock_run.side_effect = [
            (True, live),
            (True, ""),
            (True, ""),
        ]

        count = LayoutApplier._reset_orphan_keys(target)

        assert count == 2
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[0].args[0] == ["dconf", "dump", "/"]
        assert mock_run.call_args_list[1].args[0] == [
            "dconf",
            "reset",
            "-f",
            "/org/gnome/shell/extensions/leaving/",
        ]
        assert mock_run.call_args_list[2].args[0] == [
            "dconf",
            "reset",
            "/org/gnome/shell/extensions/staying/old",
        ]


class TestRewriteDtpKeysInText:
    """Garante que o rewrite text-level converte monitor IDs DTP para os locais."""

    def test_rewrites_foreign_keys_to_local(self):
        """Layout vem com 'unknown-unknown'; local é 'CMN-0x00000000'."""
        text = (
            "[org/gnome/shell/extensions/dash-to-panel]\n"
            'panel-positions=\'{"unknown-unknown":"BOTTOM"}\'\n'
        )
        out = LayoutApplier._rewrite_dtp_keys_in_text(text, {"CMN-0x00000000"})
        assert "CMN-0x00000000" in out
        assert "unknown-unknown" not in out
        assert "BOTTOM" in out

    def test_noop_when_keys_already_match(self):
        """Se o layout já tem o ID local, mantém intacto."""
        text = "[org/gnome/shell/extensions/dash-to-panel]\npanel-sizes='{\"DEL-12345\":48}'\n"
        out = LayoutApplier._rewrite_dtp_keys_in_text(text, {"DEL-12345"})
        assert out == text

    def test_empty_local_keys_returns_text_unchanged(self):
        """Sem IDs locais (mutter/dconf vazios), não mexe no texto."""
        text = '[org/gnome/shell/extensions/dash-to-panel]\npanel-positions=\'{"foo":"BOTTOM"}\'\n'
        assert LayoutApplier._rewrite_dtp_keys_in_text(text, set()) == text

    def test_non_dtp_lines_pass_through(self):
        """Chaves fora da lista DTP monitor-keyed não são tocadas."""
        text = (
            "[org/gnome/desktop/interface]\n"
            "gtk-theme='adw-gtk3-dark'\n"
            "icon-theme='bigicons-papient'\n"
        )
        out = LayoutApplier._rewrite_dtp_keys_in_text(text, {"CMN-0x00000000"})
        assert out == text

    def test_preserves_trailing_newline(self):
        """Newline final do dump deve ser preservado."""
        text = "[/]\nfoo='bar'\n"
        out = LayoutApplier._rewrite_dtp_keys_in_text(text, {"X"})
        assert out.endswith("\n")

    def test_replicates_value_to_all_local_monitors(self):
        """Com múltiplos monitores locais, replica o valor original em cada um."""
        text = '[org/gnome/shell/extensions/dash-to-panel]\npanel-positions=\'{"old":"BOTTOM"}\'\n'
        out = LayoutApplier._rewrite_dtp_keys_in_text(text, {"A-1", "B-2"})
        assert "A-1" in out
        assert "B-2" in out
        assert "old" not in out


class TestShellReloader:
    @patch("shell_reloader.run_cmd", return_value=(True, ""))
    @patch("shell_reloader.is_wayland", return_value=True)
    def test_reload_all_wayland(self, _mock_way, mock_run):
        from shell_reloader import ShellReloader

        # before = {a, c}; after = {a, b}.
        # Esperado: Disable c (em before, não em after), Enable b (em after,
        # não em before). a@x fica em paz (em ambos). Sem reexec no Wayland.
        ShellReloader.reload_all(
            before_uuids=["a@x", "c@z"],
            after_uuids=["a@x", "b@y"],
        )
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert mock_run.call_count == 3
        assert any("DisableExtension" in args[-2] and "c@z" in args[-1] for args in calls)
        assert any("ListExtensions" in args[-1] for args in calls)
        assert any("EnableExtension" in args[-2] and "b@y" in args[-1] for args in calls)
        # a@x não deve ser tocada
        for args in calls:
            assert "a@x" != args[-1]
        assert not any("reexec" in str(c) for c in mock_run.call_args_list)

    @patch("shell_reloader.run_cmd", return_value=(True, ""))
    @patch("shell_reloader.is_wayland", return_value=False)
    def test_reload_all_x11(self, _mock_way, mock_run):
        from shell_reloader import ShellReloader

        ShellReloader.reload_all(before_uuids=["x@1"], after_uuids=["y@2"])
        # Disable x@1 (removed) + Enable y@2 (added) + reexec_self (X11) = 3
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("DisableExtension" in c and "x@1" in c for c in calls)
        assert any("EnableExtension" in c and "y@2" in c for c in calls)
        assert any("reexec" in c for c in calls)

    @patch("shell_reloader.run_cmd", return_value=(True, ""))
    @patch("shell_reloader.is_wayland", return_value=True)
    def test_reload_all_no_args_is_noop_on_wayland(self, _mock_way, mock_run):
        """Sem before/after, em Wayland, reload_all não emite chamadas."""
        from shell_reloader import ShellReloader

        ShellReloader.reload_all()
        assert mock_run.call_count == 0

    @patch("shell_reloader.ShellReloader.reload_extension")
    @patch("shell_reloader.ShellReloader.enable_extension_dbus", return_value=(True, ""))
    def test_apply_extension_state_disable_does_not_reload(self, _mock_dbus, mock_reload):
        from shell_reloader import ShellReloader

        ok, _ = ShellReloader.apply_extension_state("uuid@x", enable=False)

        assert ok is True
        mock_reload.assert_not_called()
