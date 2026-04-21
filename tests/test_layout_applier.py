# SPDX-License-Identifier: MIT
"""Tests for layout_applier.py — apply layout via dconf load."""

from pathlib import Path
from unittest.mock import patch

from layout_applier import LayoutApplier


class TestLayoutApplier:
    @patch("layout_applier.time.sleep")
    @patch("shell_reloader.ShellReloader.reload_all")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_sync_service", return_value=True)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_apply_full_flow(
        self,
        mock_run,
        _has,
        mock_persist,
        mock_reload,
        _sleep,
        tmp_path,
    ):
        """Cobre fluxo completo: stop monitor -> pause ext -> reset -> load
        -> persist -> unpause ext -> start monitor -> reload shell."""
        layout = tmp_path / "classic.txt"
        layout.write_text("[/]\nfoo='bar'")

        ok, msg = LayoutApplier.apply(layout)
        assert ok is True

        # Sequencia esperada:
        #   1) systemctl stop  dconf-sync-gnome.service
        #   2) gsettings set disable-user-extensions true
        #   3) dconf reset -f /
        #   4) dconf load /
        #   5) gsettings set disable-user-extensions false
        #   6) systemctl start dconf-sync-gnome.service
        assert mock_run.call_count == 6
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert calls[0][:3] == ["systemctl", "--user", "stop"]
        assert calls[1] == [
            "gsettings",
            "set",
            "org.gnome.shell",
            "disable-user-extensions",
            "true",
        ]
        assert calls[2] == ["dconf", "reset", "-f", "/"]
        assert calls[3] == ["dconf", "load", "/"]
        assert calls[4][-1] == "false"
        assert calls[5][:3] == ["systemctl", "--user", "start"]
        mock_persist.assert_called_once()
        mock_reload.assert_called_once()

    @patch("layout_applier.time.sleep")
    @patch("shell_reloader.ShellReloader.reload_all")
    @patch("layout_applier.LayoutApplier._persist_to_settings_file", return_value=(True, "/x"))
    @patch("layout_applier.LayoutApplier._has_sync_service", return_value=False)
    @patch("layout_applier.run_cmd", return_value=(True, ""))
    def test_apply_without_sync_service(
        self,
        mock_run,
        _has,
        _persist,
        mock_reload,
        _sleep,
        tmp_path,
    ):
        """Quando dconf-sync-gnome nao esta instalado, systemctl e pulado."""
        layout = tmp_path / "x.txt"
        layout.write_text("[/]\nx=1")

        ok, _ = LayoutApplier.apply(layout)
        assert ok is True
        # Sem systemctl: pause_ext_on, reset, load, pause_ext_off = 4 chamadas
        assert mock_run.call_count == 4
        assert mock_run.call_args_list[1].args[0] == ["dconf", "reset", "-f", "/"]
        assert mock_run.call_args_list[2].args[0] == ["dconf", "load", "/"]
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
    @patch("layout_applier.LayoutApplier._persist_to_settings_file")
    @patch("layout_applier.LayoutApplier._has_sync_service", return_value=True)
    @patch("layout_applier.run_cmd")
    def test_apply_load_failure_still_cleans_up(
        self,
        mock_run,
        _has,
        mock_persist,
        mock_reload,
        _sleep,
        tmp_path,
    ):
        """Se o dconf load falhar: monitor reinicia, extensoes reativam,
        shell NAO recarrega, settings.gnome NAO e sobrescrito."""
        # stop OK, pause_on OK, reset OK, load FAIL, pause_off OK, start OK
        mock_run.side_effect = [
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


class TestShellReloader:
    @patch("shell_reloader.run_cmd", return_value=(True, ""))
    @patch("shell_reloader.is_wayland", return_value=True)
    def test_reload_all_wayland(self, _mock_way, mock_run):
        from shell_reloader import ShellReloader

        ShellReloader.reload_all()
        # Should NOT call reexec on Wayland
        calls = [str(c) for c in mock_run.call_args_list]
        assert not any("reexec" in c for c in calls)

    @patch("shell_reloader.run_cmd", return_value=(True, ""))
    @patch("shell_reloader.is_wayland", return_value=False)
    def test_reload_all_x11(self, _mock_way, mock_run):
        from shell_reloader import ShellReloader

        ShellReloader.reload_all()
        # Should call multiple strategies including reexec on X11
        assert mock_run.call_count >= 2
