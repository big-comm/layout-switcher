# SPDX-License-Identifier: MIT
"""Tests for helper_client.py — D-Bus client for the in-shell helper."""

from unittest.mock import call, patch

from helper_client import HELPER_UUID, HelperClient


class TestIsAvailable:
    @patch(
        "helper_client.HelperClient._call",
        return_value='{"helper":"layout-switcher","version":1}',
    )
    def test_available(self, _mock):
        assert HelperClient.is_available() is True

    @patch("helper_client.HelperClient._call", return_value=None)
    def test_unavailable_no_reply(self, _mock):
        assert HelperClient.is_available() is False


class TestRequiredExtensionLists:
    def test_helper_is_first_and_removed_from_disabled(self):
        enabled, disabled = HelperClient.required_extension_lists(
            ["alpha@example.org", HELPER_UUID, "beta@example.org"],
            ["disabled@example.org", HELPER_UUID],
        )

        assert enabled == [HELPER_UUID, "alpha@example.org", "beta@example.org"]
        assert disabled == ["disabled@example.org"]

    def test_does_not_change_optional_extensions(self):
        enabled, disabled = HelperClient.required_extension_lists(
            ["alpha@example.org"],
            ["disabled@example.org"],
        )

        assert enabled == [HELPER_UUID, "alpha@example.org"]
        assert disabled == ["disabled@example.org"]


class TestEnsureAvailable:
    @patch("helper_client.HelperClient.ensure_enabled", return_value=(True, True, ""))
    @patch("helper_client.HelperClient.is_available", side_effect=[False, True])
    def test_repairs_and_waits_for_helper(self, mock_available, mock_ensure):
        ok, info = HelperClient.ensure_available(timeout_ms=1000)

        assert ok is True
        assert info == ""
        assert mock_available.call_args_list == [call(timeout_ms=800), call(timeout_ms=800)]
        mock_ensure.assert_called_once_with()

    @patch(
        "helper_client.HelperClient.ensure_enabled",
        return_value=(False, False, "helper missing"),
    )
    @patch("helper_client.HelperClient.is_available", return_value=False)
    def test_returns_repair_error(self, _mock_available, _mock_ensure):
        ok, info = HelperClient.ensure_available(timeout_ms=1000)

        assert ok is False
        assert info == "helper missing"

    @patch("helper_client.HelperClient._call", return_value="something else")
    def test_unavailable_wrong_reply(self, _mock):
        assert HelperClient.is_available() is False


class TestApplyLayout:
    @patch("helper_client.HelperClient._call")
    def test_ok_returns_steps(self, mock_call):
        mock_call.return_value = '{"ok":true,"steps":["disable a","enable b"],"error":""}'
        ok, msg = HelperClient.apply_layout(["b@x"], reload=["b@x"])
        assert ok is True
        assert "disable a" in msg and "enable b" in msg

    @patch("helper_client.HelperClient._call")
    def test_helper_reported_error(self, mock_call):
        mock_call.return_value = '{"ok":false,"steps":[],"error":"boom"}'
        ok, msg = HelperClient.apply_layout(["b@x"])
        assert ok is False
        assert msg == "boom"

    @patch("helper_client.HelperClient._call", return_value=None)
    def test_call_failed(self, _mock):
        ok, _msg = HelperClient.apply_layout(["b@x"])
        assert ok is False

    @patch("helper_client.HelperClient._call")
    def test_payload_shape(self, mock_call):
        mock_call.return_value = '{"ok":true,"steps":[],"error":""}'
        HelperClient.apply_layout(["a@x", "", "b@y"], reload=["a@x"], step_ms=200)
        # second positional arg to _call is the (s) variant carrying the JSON
        import json

        variant = mock_call.call_args.args[1]
        payload = json.loads(variant.unpack()[0])
        assert payload["enabled"] == ["a@x", "b@y"]  # blanks filtered
        assert payload["reload"] == ["a@x"]
        assert payload["step_ms"] == 200


def test_helper_uuid_constant():
    assert HELPER_UUID == "layout-switcher-helper@bigcommunity.org"
