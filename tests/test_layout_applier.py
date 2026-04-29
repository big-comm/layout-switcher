# SPDX-License-Identifier: MIT
"""Tests for layout_applier.py — apply layout via dconf load."""

from pathlib import Path
from unittest.mock import patch

from layout_applier import LayoutApplier


class TestLayoutApplier:
    @patch("layout_applier.time.sleep")
    @patch("shell_reloader.ShellReloader.reload_all")
    @patch("layout_applier.LayoutApplier._load_current_settings_text", return_value="")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_sync_service", return_value=True)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_apply_full_flow(
        self,
        mock_run,
        _has,
        mock_persist,
        _settings,
        mock_reload,
        _sleep,
        tmp_path,
    ):
        """Cobre fluxo completo: dtp-probe (5 reads) -> read-before -> stop
        monitor -> pause ext -> reset -> load -> persist -> unpause ext ->
        start monitor -> read-after -> reload shell."""
        layout = tmp_path / "classic.txt"
        layout.write_text("[/]\nfoo='bar'")

        ok, msg = LayoutApplier.apply(layout)
        assert ok is True

        # 1 mutter gdbus probe + 5 dconf reads (dtp fallback) +
        # 1 read enabled-extensions (before) +
        # stop + pause-on + reset + load +
        # pause-off + start +
        # 1 read enabled-extensions (after) = 14.
        assert mock_run.call_count == 14
        calls = [c.args[0] for c in mock_run.call_args_list]
        # 1: gdbus probe to mutter for monitor IDs
        assert calls[0][0] == "gdbus"
        assert "Mutter.DisplayConfig" in calls[0][4]
        # 2-6: dtp monitor-key probes (fallback because mutter returned empty)
        assert all(c[:2] == ["dconf", "read"] for c in calls[1:6])
        assert all("dash-to-panel" in c[2] for c in calls[1:6])
        # 7: enabled-extensions before
        assert calls[6] == ["dconf", "read", "/org/gnome/shell/enabled-extensions"]
        # 8-11: load_dconf_safely (stop, pause-on, reset, load)
        assert calls[7][:3] == ["systemctl", "--user", "stop"]
        assert calls[8] == [
            "gsettings",
            "set",
            "org.gnome.shell",
            "disable-user-extensions",
            "true",
        ]
        assert calls[9] == ["dconf", "reset", "-f", "/"]
        assert calls[10] == ["dconf", "load", "/"]
        # 12: pause-off
        assert calls[11][-1] == "false"
        # 13: systemctl start
        assert calls[12][:3] == ["systemctl", "--user", "start"]
        # 14: enabled-extensions after
        assert calls[13] == ["dconf", "read", "/org/gnome/shell/enabled-extensions"]
        mock_persist.assert_called_once()
        mock_reload.assert_called_once()

    @patch("layout_applier.time.sleep")
    @patch("shell_reloader.ShellReloader.reload_all")
    @patch("layout_applier.LayoutApplier._load_current_settings_text", return_value="")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_sync_service", return_value=False)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_apply_without_sync_service(
        self,
        mock_run,
        _has,
        _persist,
        _settings,
        mock_reload,
        _sleep,
        tmp_path,
    ):
        """Quando dconf-sync-gnome nao esta instalado, systemctl e pulado."""
        layout = tmp_path / "x.txt"
        layout.write_text("[/]\nx=1")

        ok, _ = LayoutApplier.apply(layout)
        assert ok is True
        # 1 gdbus mutter probe + 5 dtp dconf reads + 1 enabled-ext read
        # (before) + 4 (pause_on, reset, load, pause_off) + 1 enabled-ext
        # read (after) = 12.
        assert mock_run.call_count == 12
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
        # reset + load no meio
        assert mock_run.call_args_list[8].args[0] == ["dconf", "reset", "-f", "/"]
        assert mock_run.call_args_list[9].args[0] == ["dconf", "load", "/"]
        mock_reload.assert_called_once()

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
    @patch("shell_reloader.ShellReloader.reload_all")
    @patch("layout_applier.LayoutApplier._load_current_settings_text", return_value="")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file")
    @patch("layout_applier.LayoutApplier._has_sync_service", return_value=True)
    @patch("layout_applier.run_cmd")
    def test_apply_load_failure_still_cleans_up(
        self,
        mock_run,
        _has,
        mock_persist,
        _settings,
        mock_reload,
        _sleep,
        tmp_path,
    ):
        """Se o dconf load falhar: monitor reinicia, extensoes reativam,
        shell NAO recarrega, settings.gnome NAO e sobrescrito."""
        # 1 mutter gdbus probe (returns empty so dconf fallback runs),
        # 5 dtp dconf reads, read-before, stop OK, pause_on OK, reset OK,
        # load FAIL, pause_off OK, start OK. Sem read-after porque
        # ok=False bypassa.
        mock_run.side_effect = [
            (True, ""),  # gdbus mutter probe
            (True, ""),  # dtp probe 1
            (True, ""),  # dtp probe 2
            (True, ""),  # dtp probe 3
            (True, ""),  # dtp probe 4
            (True, ""),  # dtp probe 5
            (True, "[]"),  # read enabled-extensions (before)
            (True, ""),  # systemctl stop
            (True, ""),  # pause on
            (True, ""),  # dconf reset
            (False, "dconf error"),  # dconf load FAILS
            (True, ""),  # pause off
            (True, ""),  # systemctl start
        ]
        layout = tmp_path / "bad.txt"
        layout.write_text("[/]\ndata=true")

        ok, msg = LayoutApplier.apply(layout)
        assert ok is False
        mock_persist.assert_not_called()
        mock_reload.assert_not_called()
        # Garantir que a ultima chamada foi start do service (finally rodou)
        assert mock_run.call_args_list[-1].args[0][:3] == [
            "systemctl",
            "--user",
            "start",
        ]


class TestMergeLayoutIntoSettings:
    """Garante que o merge preserva chaves do settings ausentes no layout."""

    def test_preserves_theme_keys_not_in_layout(self):
        """Tema do shell e GTK existem só em settings — devem sobreviver."""
        settings = (
            "[org/gnome/desktop/interface]\n"
            "gtk-theme='adw-gtk3-dark'\n"
            "icon-theme='bigicons-papient'\n"
            "\n"
            "[org/gnome/shell/extensions/user-theme]\n"
            "name='Big-Blue-Dark'\n"
        )
        layout = "[org/gnome/shell]\nenabled-extensions=['dash-to-dock@x']\n"
        merged = LayoutApplier._merge_layout_into_settings(layout, settings)
        assert "gtk-theme='adw-gtk3-dark'" in merged
        assert "icon-theme='bigicons-papient'" in merged
        assert "name='Big-Blue-Dark'" in merged
        assert "enabled-extensions=['dash-to-dock@x']" in merged

    def test_layout_overrides_settings_per_key(self):
        """Quando ambos definem a mesma chave, layout vence."""
        settings = (
            "[org/gnome/shell]\nenabled-extensions=['old@x']\nfavorite-apps=['old.desktop']\n"
        )
        layout = "[org/gnome/shell]\nenabled-extensions=['new@x']\n"
        merged = LayoutApplier._merge_layout_into_settings(layout, settings)
        assert "enabled-extensions=['new@x']" in merged
        # favorite-apps nao esta no layout — deve ser preservada do settings.
        assert "favorite-apps=['old.desktop']" in merged

    def test_empty_settings_returns_layout_only(self):
        """Sem settings.gnome, merged == layout (formato canonico)."""
        layout = "[/]\nfoo='bar'\n"
        merged = LayoutApplier._merge_layout_into_settings(layout, "")
        assert "foo='bar'" in merged
        assert merged.startswith("[/]")


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
        assert mock_run.call_count == 2
        assert any("DisableExtension" in args[-2] and "c@z" in args[-1] for args in calls)
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
