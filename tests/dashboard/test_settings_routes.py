import unittest
from contextlib import contextmanager
from http import HTTPStatus
from unittest.mock import patch

from scripts import dashboard_server, desk_settings_routes


class DashboardSettingsRouteTests(unittest.TestCase):
    def test_settings_route_owner_handles_delivery_save_with_loopback_gate_and_closed_connection(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            status = None
            payload = None
            conn = FakeConnection()

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        features = []
        body = {"enabled": True, "chat_id": "12345"}

        @contextmanager
        def close_after_use(conn):
            try:
                yield conn
            finally:
                conn.close()

        def save_target(conn, target_id, payload):
            return {"conn": conn is handler.conn, "target_id": target_id, "body": dict(payload)}

        handler = FakeHandler()
        handled = desk_settings_routes.handle_settings_post_route(
            handler,
            "/api/desk/delivery-targets/telegram-bot-default",
            body,
            require_loopback_access=lambda value, feature: features.append((value, feature)),
            close_after_use=close_after_use,
            save_telegram_credentials=lambda api_id, api_hash: {},
            telegram_send_code=lambda phone: {},
            telegram_verify_code=lambda code, password: {},
            telegram_cancel_login=lambda: {},
            update_desk_notification_token=lambda payload: {},
            apply_desk_bot_identity=lambda: {},
            update_desk_ai_settings=lambda payload: {},
            save_desk_delivery_target=save_target,
            test_desk_delivery_target=lambda conn, target_id, payload: {},
            detect_desk_delivery_chat_id=lambda target_id, payload: {},
        )

        self.assertTrue(handled)
        self.assertEqual(features, [(handler, "Notification settings")])
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(
            handler.payload,
            {"ok": True, "target": {"conn": True, "target_id": "telegram-bot-default", "body": body}},
        )


    def test_settings_route_owner_returns_false_for_non_settings_path(self):
        handled = desk_settings_routes.handle_settings_post_route(
            object(),
            "/api/desk/sources/preview",
            {},
            require_loopback_access=lambda handler, feature: None,
            close_after_use=lambda conn: conn,
            save_telegram_credentials=lambda api_id, api_hash: {},
            telegram_send_code=lambda phone: {},
            telegram_verify_code=lambda code, password: {},
            telegram_cancel_login=lambda: {},
            update_desk_notification_token=lambda payload: {},
            apply_desk_bot_identity=lambda: {},
            update_desk_ai_settings=lambda payload: {},
            save_desk_delivery_target=lambda conn, target_id, payload: {},
            test_desk_delivery_target=lambda conn, target_id, payload: {},
            detect_desk_delivery_chat_id=lambda target_id, payload: {},
        )

        self.assertFalse(handled)


    def test_settings_route_owner_rejects_unsupported_delivery_path(self):
        class FakeHandler:
            def _json(self, status, payload):
                raise AssertionError("Unsupported delivery path should raise before JSON response")

        with self.assertRaisesRegex(ValueError, "Unsupported notification settings path"):
            desk_settings_routes.handle_settings_post_route(
                FakeHandler(),
                "/api/desk/delivery-targets/telegram-bot-default/unknown",
                {},
                require_loopback_access=lambda handler, feature: None,
                close_after_use=lambda conn: conn,
                save_telegram_credentials=lambda api_id, api_hash: {},
                telegram_send_code=lambda phone: {},
                telegram_verify_code=lambda code, password: {},
                telegram_cancel_login=lambda: {},
                update_desk_notification_token=lambda payload: {},
                apply_desk_bot_identity=lambda: {},
                update_desk_ai_settings=lambda payload: {},
                save_desk_delivery_target=lambda conn, target_id, payload: {},
                test_desk_delivery_target=lambda conn, target_id, payload: {},
                detect_desk_delivery_chat_id=lambda target_id, payload: {},
            )


    def test_dashboard_handler_post_uses_facade_injected_settings_helpers(self):
        class FakeHandler:
            status = None
            payload = None

            def __init__(self, path, body):
                self.path = path
                self.body = body

            def _read_json_body(self):
                return self.body

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        cases = [
            (
                "/api/desk/telegram-credentials",
                {"api_id": "12345", "api_hash": "a" * 32},
                "save_telegram_credentials",
                ("12345", "a" * 32),
                "telegram",
            ),
            ("/api/desk/telegram-login/send-code", {"phone": "+15551234567"}, "telegram_send_code", ("+15551234567",), "telegram"),
            (
                "/api/desk/telegram-login/verify-code",
                {"code": "12345", "password": "secret"},
                "telegram_verify_code",
                ("12345", "secret"),
                "telegram",
            ),
            ("/api/desk/telegram-login/cancel", {}, "telegram_cancel_login", (), "telegram"),
            ("/api/desk/notification-token", {"token": "12345:abc"}, "update_desk_notification_token", ({"token": "12345:abc"},), "token"),
            ("/api/desk/bot-identity/apply", {}, "apply_desk_bot_identity", (), "identity"),
            ("/api/desk/ai-settings", {"provider": "deepseek"}, "update_desk_ai_settings", ({"provider": "deepseek"},), "ai"),
        ]
        for path, body, helper_name, expected_args, payload_key in cases:
            with self.subTest(path=path):
                result = {"schema_version": f"patched_{payload_key}_v1"}
                with patch.object(dashboard_server, helper_name, return_value=result) as helper_mock:
                    handler = FakeHandler(path, body)
                    dashboard_server.DashboardHandler.do_POST(handler)

                helper_mock.assert_called_once_with(*expected_args)
                self.assertEqual(handler.status, HTTPStatus.OK)
                self.assertEqual(handler.payload, {"ok": True, payload_key: result})


    def test_dashboard_handler_post_delivery_save_uses_facade_and_closes_connection(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            path = "/api/desk/delivery-targets/telegram-bot-default"
            status = None
            payload = None
            conn = FakeConnection()
            body = {"enabled": True}

            def _read_json_body(self):
                return self.body

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        result = {"schema_version": "delivery_target_v1"}
        with patch.object(dashboard_server, "save_desk_delivery_target", return_value=result) as save_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        save_mock.assert_called_once_with(handler.conn, "telegram-bot-default", {"enabled": True})
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload, {"ok": True, "target": result})


    def test_dashboard_handler_post_delivery_test_uses_facade_and_closes_connection(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            path = "/api/desk/delivery-targets/telegram-bot-default/test"
            status = None
            payload = None
            conn = FakeConnection()
            body = {"chat_id": "12345"}

            def _read_json_body(self):
                return self.body

            def _connect(self):
                return self.conn

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        result = {"schema_version": "delivery_test_result_v1"}
        with patch.object(dashboard_server, "test_desk_delivery_target", return_value=result) as test_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        test_mock.assert_called_once_with(handler.conn, "telegram-bot-default", {"chat_id": "12345"})
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload, {"ok": True, "result": result})


    def test_dashboard_handler_post_delivery_detect_chat_id_uses_facade_without_state_connection(self):
        class FakeHandler:
            path = "/api/desk/delivery-targets/telegram-bot-default/detect-chat-id"
            status = None
            payload = None
            body = {}

            def _read_json_body(self):
                return self.body

            def _connect(self):
                raise AssertionError("Chat-id detection should not open dashboard state")

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        result = {"schema_version": "delivery_chat_detection_v1", "ok": True}
        with patch.object(dashboard_server, "detect_desk_delivery_chat_id", return_value=result) as detect_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        detect_mock.assert_called_once_with("telegram-bot-default", {})
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload, {"ok": True, "result": result})


if __name__ == "__main__":
    unittest.main()
