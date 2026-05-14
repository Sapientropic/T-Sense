import unittest
from http import HTTPStatus
from unittest.mock import patch

from scripts import dashboard_server


class DashboardStatusEndpointTests(unittest.TestCase):
    def test_get_state_returns_json_error_when_snapshot_fails(self):
        class FakeHandler:
            path = "/api/state"
            status = None
            payload = None

            def _connect(self):
                class FakeConnection:
                    def close(self):
                        pass

                return FakeConnection()

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server.monitor_state,
            "dashboard_snapshot",
            side_effect=dashboard_server.monitor_state.MonitorStateError("state failed"),
        ):
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(handler.payload, {"ok": False, "error": "state failed"})


    def test_health_endpoint_returns_json_before_static_fallback(self):
        class FakeServer:
            server_address = ("127.0.0.1", 8765)

        class FakeHandler:
            path = "/api/desk/health"
            status = None
            payload = None
            server = FakeServer()

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_GET(handler)

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["schema_version"], "desk_health_v1")
        self.assertEqual(handler.payload["app"], "tgcs-signal-desk")
        self.assertIn("desk_notification_token_v1", handler.payload["capabilities"])


    def test_notification_token_status_endpoint_requires_loopback_and_returns_status(self):
        class FakeHandler:
            path = "/api/desk/notification-token/status"
            client_address = ("127.0.0.1", 12345)
            status = None
            payload = None

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "desk_notification_token_status",
            return_value={"schema_version": "desk_notification_token_status_v1", "configured": False},
        ) as status_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        status_mock.assert_called_once_with()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertFalse(handler.payload["token"]["configured"])


    def test_ai_settings_status_endpoint_requires_loopback_and_returns_status(self):
        class FakeHandler:
            path = "/api/desk/ai-settings/status"
            client_address = ("127.0.0.1", 12345)
            status = None
            payload = None

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "desk_ai_settings_status",
            return_value={"schema_version": "desk_ai_settings_status_v1", "configured_count": 1},
        ) as status_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        status_mock.assert_called_once_with()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["ai"]["configured_count"], 1)


    def test_ai_settings_update_endpoint_uses_safe_body(self):
        class FakeHandler:
            path = "/api/desk/ai-settings"
            client_address = ("127.0.0.1", 12345)
            status = None
            payload = None

            def _read_json_body(self):
                return {"provider": "deepseek", "api_key": "sk-deepseek123"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "update_desk_ai_settings",
            return_value={"schema_version": "desk_ai_settings_status_v1", "configured_count": 1},
        ) as update_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        update_mock.assert_called_once_with({"provider": "deepseek", "api_key": "sk-deepseek123"})
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["ai"]["configured_count"], 1)


    def test_profile_patch_revert_endpoint_calls_monitor_state(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            path = "/api/profile-patches/patch_123/revert"
            status = None
            payload = None
            conn = FakeConnection()

            def _read_json_body(self):
                return {}

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server.monitor_state,
            "revert_profile_patch",
            return_value={"patch_id": "patch_123", "status": "reverted"},
        ) as revert_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        revert_mock.assert_called_once_with(handler.conn, patch_id="patch_123")
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["result"]["status"], "reverted")


    def test_profile_patch_apply_endpoint_calls_monitor_state(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            path = "/api/profile-patches/patch_123/apply"
            status = None
            payload = None
            conn = FakeConnection()

            def _read_json_body(self):
                return {}

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server.monitor_state,
            "apply_profile_patch",
            return_value={"patch_id": "patch_123", "status": "applied"},
        ) as apply_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        apply_mock.assert_called_once_with(handler.conn, patch_id="patch_123")
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["result"]["status"], "applied")


    def test_profile_patch_replay_endpoint_calls_monitor_state(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            path = "/api/profile-patches/patch_123/replay"
            status = None
            payload = None
            conn = FakeConnection()

            def _read_json_body(self):
                return {}

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server.monitor_state,
            "replay_profile_patch",
            return_value={"patch_id": "patch_456", "status": "pending", "replayed_from_patch_id": "patch_123"},
        ) as replay_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        replay_mock.assert_called_once_with(handler.conn, patch_id="patch_123")
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["result"]["status"], "pending")
        self.assertEqual(handler.payload["result"]["replayed_from_patch_id"], "patch_123")


    def test_feedback_profile_suggestions_endpoint_calls_monitor_state(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            path = "/api/feedback/profile-suggestions"
            client_address = ("127.0.0.1", 12345)
            status = None
            payload = None
            conn = FakeConnection()

            def _read_json_body(self):
                return {}

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server.monitor_state,
            "create_feedback_profile_patch_suggestions",
            return_value={"schema_version": "feedback_profile_suggestions_result_v1", "created_count": 1},
        ) as suggestions_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        suggestions_mock.assert_called_once_with(handler.conn)
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["suggestions"]["created_count"], 1)



if __name__ == "__main__":
    unittest.main()
