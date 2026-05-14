import unittest
from http import HTTPStatus
from unittest.mock import patch

from scripts import dashboard_server, desk_http_security


class DashboardHttpSecurityTests(unittest.TestCase):
    def test_handler_security_helpers_delegate_to_security_module(self):
        self.assertIsNotNone(desk_http_security.require_post_request_integrity)
        self.assertIsNotNone(desk_http_security.require_loopback_access)

        class FakeHandler:
            headers = {"Content-Type": "application/json", "Host": "127.0.0.1:8765"}
            client_address = ("127.0.0.1", 51000)
            server = type("Server", (), {"server_address": ("127.0.0.1", 8765)})()

        handler = FakeHandler()

        self.assertEqual(dashboard_server.DashboardHandler._request_host_port(handler), 8765)
        self.assertTrue(dashboard_server.DashboardHandler._is_loopback_same_port_url(handler, "http://localhost:8765"))
        dashboard_server.DashboardHandler._require_post_request_integrity(handler)
        dashboard_server.DashboardHandler._require_loopback_access(handler, "Dashboard state")


    def test_telegram_post_endpoints_require_loopback_client(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("192.168.1.10", 51000)

            def __init__(self, path):
                self.path = path

            def _read_json_body(self):
                return {"api_id": "12345", "api_hash": "a" * 32, "phone": "+15551234567", "code": "12345"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        endpoint_functions = {
            "/api/desk/telegram-credentials": "save_telegram_credentials",
            "/api/desk/telegram-login/send-code": "telegram_send_code",
            "/api/desk/telegram-login/verify-code": "telegram_verify_code",
            "/api/desk/telegram-login/cancel": "telegram_cancel_login",
            "/api/desk/delivery-targets/telegram-bot-default": "save_desk_delivery_target",
            "/api/desk/delivery-targets/telegram-bot-default/test": "test_desk_delivery_target",
            "/api/desk/delivery-targets/telegram-bot-default/detect-chat-id": "detect_desk_delivery_chat_id",
            "/api/desk/sources/preview": "preview_desk_source_import",
            "/api/desk/sources/import": "import_desk_sources",
            "/api/desk/sources/starter": "import_starter_sources",
            "/api/desk/sources/assistant": "run_source_assistant",
            "/api/desk/sources/telegram%3Aremote_jobs/enabled": "set_desk_source_enabled",
            "/api/desk/sources/telegram%3Aremote_jobs/topics": "set_desk_source_topics",
            "/api/desk/sources/telegram%3Aremote_jobs/remove": "remove_desk_source",
            "/api/profiles/jobs-fast/enabled": "update_profile_enabled",
            "/api/profiles/jobs-fast/runtime-settings": "update_profile_runtime_settings",
            "/api/profiles/jobs-fast/alert-mode": "update_profile_alert_mode",
            "/api/profiles/jobs-fast/draft-note": "create_profile_patch_suggestion",
            "/api/profiles/jobs-fast/delete": "delete_profile",
            "/api/profiles/create": "create_profile_from_brief",
        }
        for path, function_name in endpoint_functions.items():
            with self.subTest(path=path):
                module = dashboard_server.monitor_state if function_name.startswith("update_profile_") or function_name == "create_profile_patch_suggestion" else dashboard_server
                with patch.object(module, function_name) as action_mock:
                    handler = FakeHandler(path)
                    dashboard_server.DashboardHandler.do_POST(handler)

                action_mock.assert_not_called()
                self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                self.assertIn("localhost", handler.payload["error"])


    def test_local_state_mutation_endpoints_require_loopback_client(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("192.168.1.10", 51000)
            connected = False

            def __init__(self, path):
                self.path = path

            def _read_json_body(self):
                return {"confirm": True, "action": "keep", "preferences": "Prefer remote roles."}

            def _connect(self):
                self.connected = True
                raise AssertionError("local mutation connection should be gated before use")

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        endpoint_functions = {
            "/api/git/check-updates": (dashboard_server, "_git_update_status"),
            "/api/git/pull-latest": (dashboard_server, "_git_pull_latest"),
            "/api/feedback/export": (dashboard_server, "write_feedback_export"),
            "/api/feedback/clear": (dashboard_server.monitor_state, "clear_feedback_decisions"),
            "/api/feedback/profile-suggestions": (
                dashboard_server.monitor_state,
                "create_feedback_profile_patch_suggestions",
            ),
            "/api/review-cards/card_123/action": (dashboard_server.monitor_state, "set_card_action"),
            "/api/review-cards/card_123/undo": (dashboard_server.monitor_state, "undo_card_action"),
            "/api/profiles/jobs-fast/matching-preferences": (
                dashboard_server.monitor_state,
                "create_profile_preferences_patch_suggestion",
            ),
            "/api/profiles/jobs-fast/delete": (dashboard_server, "delete_profile"),
            "/api/profile-patches/patch_123/apply": (dashboard_server.monitor_state, "apply_profile_patch"),
            "/api/profile-patches/patch_123/revert": (dashboard_server.monitor_state, "revert_profile_patch"),
            "/api/profile-patches/patch_123/replay": (dashboard_server.monitor_state, "replay_profile_patch"),
        }
        for path, (module, function_name) in endpoint_functions.items():
            with self.subTest(path=path):
                with patch.object(module, function_name) as action_mock:
                    handler = FakeHandler(path)
                    dashboard_server.DashboardHandler.do_POST(handler)

                action_mock.assert_not_called()
                self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                self.assertIn("localhost", handler.payload["error"])
                self.assertFalse(handler.connected)


    def test_desk_actions_http_endpoint_returns_actions(self):
        class FakeHandler:
            path = "/api/desk/actions"
            status = None
            payload = None

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_GET(handler)

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["schema_version"], "desk_actions_v1")


    def test_desk_action_run_endpoint_returns_bad_request_for_unknown_action(self):
        class FakeHandler:
            path = "/api/desk/actions/unknown/run"
            status = None
            payload = None

            def _read_json_body(self):
                return {}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("Unknown Desk action", handler.payload["error"])


    def test_desk_action_run_endpoint_uses_requested_action_id(self):
        class FakeHandler:
            path = "/api/desk/actions/monitor_jobs_dry_run/run"
            status = None
            payload = None

            def _read_json_body(self):
                return {"command": "ignored"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "run_desk_action",
            return_value={
                "schema_version": "desk_action_result_v1",
                "action_id": "monitor_jobs_dry_run",
                "status": "success",
                "title": "Run AI review",
                "detail": "done",
                "display_command": "tgcs monitor run --profile-id jobs-fast --delivery-mode live",
                "exit_code": 0,
                "artifact_path": "",
                "next_action": "",
                "finished_at": "2026-05-10T00:00:00Z",
            },
        ) as run_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        run_mock.assert_called_once_with("monitor_jobs_dry_run", body={"command": "ignored"})
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["result"]["action_id"], "monitor_jobs_dry_run")


    def test_post_mutations_require_json_content_type_before_action(self):
        class FakeHandler:
            path = "/api/desk/actions/monitor_jobs_dry_run/run"
            client_address = ("127.0.0.1", 51000)
            headers = {"Content-Type": "text/plain", "Host": "127.0.0.1:8765"}
            status = None
            payload = None

            def _read_json_body(self):
                raise AssertionError("non-JSON POST should be rejected before body parsing")

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(dashboard_server, "run_desk_action") as run_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        run_mock.assert_not_called()
        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("application/json", handler.payload["error"])


    def test_post_mutations_reject_non_loopback_origin_before_action(self):
        class FakeHandler:
            path = "/api/desk/actions/monitor_jobs_dry_run/run"
            client_address = ("127.0.0.1", 51000)
            headers = {
                "Content-Type": "application/json",
                "Host": "127.0.0.1:8765",
                "Origin": "https://example.com",
            }
            status = None
            payload = None

            def _read_json_body(self):
                raise AssertionError("cross-origin POST should be rejected before body parsing")

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(dashboard_server, "run_desk_action") as run_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        run_mock.assert_not_called()
        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("local dashboard", handler.payload["error"])


    def test_post_mutations_reject_referer_with_different_loopback_port_before_action(self):
        class FakeHandler:
            path = "/api/desk/actions/monitor_jobs_dry_run/run"
            client_address = ("127.0.0.1", 51000)
            headers = {
                "Content-Type": "application/json",
                "Host": "127.0.0.1:8765",
                "Referer": "http://localhost:8766/dashboard",
            }
            status = None
            payload = None

            def _read_json_body(self):
                raise AssertionError("wrong-port Referer should be rejected before body parsing")

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(dashboard_server, "run_desk_action") as run_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        run_mock.assert_not_called()
        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("local dashboard", handler.payload["error"])


    def test_post_mutations_accept_json_from_loopback_same_port_origin(self):
        class FakeHandler:
            path = "/api/desk/actions/monitor_jobs_dry_run/run"
            client_address = ("127.0.0.1", 51000)
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Host": "127.0.0.1:8765",
                "Origin": "http://localhost:8765",
            }
            status = None
            payload = None

            def _read_json_body(self):
                return {"confirm": True}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "run_desk_action",
            return_value={"schema_version": "desk_action_result_v1", "action_id": "monitor_jobs_dry_run", "status": "success"},
        ) as run_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        run_mock.assert_called_once()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["result"]["status"], "success")



if __name__ == "__main__":
    unittest.main()
