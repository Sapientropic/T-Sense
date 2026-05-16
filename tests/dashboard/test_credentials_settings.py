import tempfile
import unittest
import json
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from unittest.mock import AsyncMock, patch

from scripts import (
    dashboard_server,
    desk_credentials,
    desk_delivery_settings,
    desk_secret_settings,
    desk_telegram_login,
    monitor_state,
)


class DashboardCredentialsSettingsTests(unittest.TestCase):
    def test_desk_credentials_helpers_stay_available_from_dashboard_server_facade(self):
        self.assertIs(dashboard_server.telegram_status, desk_credentials.telegram_status)
        self.assertIs(dashboard_server.save_telegram_credentials, desk_credentials.save_telegram_credentials)
        self.assertIs(dashboard_server.detect_desk_delivery_chat_id, desk_credentials.detect_desk_delivery_chat_id)
        self.assertIs(dashboard_server.desk_notification_token_status, desk_credentials.desk_notification_token_status)
        self.assertIs(dashboard_server.desk_ai_settings_status, desk_credentials.desk_ai_settings_status)
        self.assertIs(dashboard_server.desk_action_env, desk_credentials.desk_action_env)
        self.assertEqual(desk_credentials.TELEGRAM_CONFIG_PATH, desk_telegram_login.TELEGRAM_CONFIG_PATH)
        self.assertEqual(desk_credentials.TELEGRAM_LOGIN_CODE_TTL_SECONDS, desk_telegram_login.TELEGRAM_LOGIN_CODE_TTL_SECONDS)
        self.assertEqual(desk_credentials.DESK_DELIVERY_TARGET_ID, desk_delivery_settings.DESK_DELIVERY_TARGET_ID)
        self.assertEqual(desk_credentials.DESK_AI_PROVIDER_CONFIGS, desk_secret_settings.DESK_AI_PROVIDER_CONFIGS)


    def test_secret_settings_provider_config_uses_dashboard_facade_patch_after_split(self):
        custom_config = {
            "custom": {
                "label": "Custom",
                "env_name": "CUSTOM_API_KEY",
                "target": "tgcs.signal-desk.custom-api-key",
                "username": "Custom API key",
            }
        }
        stored = dashboard_server.local_credentials.StoredSecret(
            secret="custom-local-secret",
            updated_at="2026-05-10T00:00:00Z",
        )

        with patch.object(dashboard_server, "DESK_AI_PROVIDER_CONFIGS", custom_config):
            with patch.dict("os.environ", {}, clear=True):
                with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
                    with patch.object(dashboard_server.local_credentials, "read_secret", return_value=stored):
                        status = dashboard_server.desk_ai_settings_status()
                        env = dashboard_server.desk_action_env()

        self.assertEqual([provider["provider"] for provider in status["providers"]], ["custom"])
        self.assertIn(
            status["providers"][0]["source"],
            {
                dashboard_server.local_credentials.BACKEND_WINDOWS,
                dashboard_server.local_credentials.BACKEND_KEYRING,
            },
        )
        self.assertEqual(env["CUSTOM_API_KEY"], "custom-local-secret")


    def test_delivery_chat_detection_uses_dashboard_facade_patch_after_split(self):
        candidate = {"chat_id": "987654", "chat_type": "group", "source": "patched"}

        with patch.object(dashboard_server, "_detect_chat_id_from_bot_updates", return_value=candidate) as detect_mock:
            with patch.object(dashboard_server, "_telegram_current_user_chat_id", return_value="unused") as session_mock:
                result = dashboard_server.detect_desk_delivery_chat_id("telegram-bot-default", {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["chat_id"], "987654")
        self.assertEqual(result["chat_type"], "group")
        self.assertEqual(result["source"], "telegram_bot_updates")
        detect_mock.assert_called_once_with()
        session_mock.assert_not_called()


    def test_delivery_chat_detection_direct_owner_uses_credentials_session_fallback_after_split(self):
        def no_facade(_name, default):
            return default

        with patch.object(desk_delivery_settings, "_facade_attr", side_effect=no_facade):
            with patch.object(desk_delivery_settings, "_detect_chat_id_from_bot_updates", return_value=None):
                with patch.object(
                    desk_delivery_settings,
                    "_telegram_current_user_chat_id",
                    desk_delivery_settings._telegram_current_user_chat_id_from_credentials,
                ):
                    with patch.object(desk_credentials, "_telegram_current_user_chat_id", return_value="24680") as session_mock:
                        result = desk_delivery_settings.detect_desk_delivery_chat_id("telegram-bot-default", {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["chat_id"], "24680")
        self.assertEqual(result["source"], "telegram_session")
        session_mock.assert_called_once_with()


    def test_telegram_login_split_preserves_desk_credentials_async_hook_patches(self):
        status = {
            "schema_version": "desk_telegram_status_v1",
            "credentials_ready": True,
            "session_ready": False,
            "login_state": "code_sent",
            "detail": "Telegram sent a verification code.",
            "next_step": "Enter the code in Signal Desk.",
            "config_path": "~/.config/tgcli/config.toml",
            "session_path": "~/.config/tgcli/session",
        }
        send_mock = AsyncMock(return_value=status)
        verify_mock = AsyncMock(return_value={**status, "login_state": "authorized", "session_ready": True})

        with patch.object(desk_credentials, "_telegram_send_code_async", send_mock):
            sent = desk_credentials.telegram_send_code("+15551234567")
        with patch.object(desk_credentials, "_telegram_verify_code_async", verify_mock):
            verified = desk_credentials.telegram_verify_code("12345", "secret")

        self.assertEqual(sent["login_state"], "code_sent")
        self.assertEqual(verified["login_state"], "authorized")
        send_mock.assert_awaited_once_with(
            "+15551234567",
            config_path=desk_credentials.TELEGRAM_CONFIG_PATH,
            session_path=desk_credentials.TELEGRAM_SESSION_PATH,
        )
        verify_mock.assert_awaited_once_with(
            "12345",
            "secret",
            config_path=desk_credentials.TELEGRAM_CONFIG_PATH,
            session_path=desk_credentials.TELEGRAM_SESSION_PATH,
        )


    def test_telegram_credentials_are_saved_without_echoing_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            session_path = Path(tmp) / "session"

            status = dashboard_server.save_telegram_credentials(
                "12345",
                "a" * 32,
                config_path=config_path,
                session_path=session_path,
            )

            self.assertTrue(status["credentials_ready"])
            self.assertEqual(status["credentials_status"], "saved_unverified")
            self.assertFalse(status["session_ready"])
            self.assertNotIn("a" * 32, json.dumps(status))
            self.assertIn("api_hash", config_path.read_text(encoding="utf-8"))
            session_path.write_text("session-string", encoding="utf-8")
            status = dashboard_server.telegram_status(config_path=config_path, session_path=session_path)
            self.assertEqual(status["login_state"], "authorized")
            self.assertEqual(status["credentials_status"], "verified")


    def test_telegram_status_requires_credentials_and_session_for_scan_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            session_path = Path(tmp) / "session"
            session_path.write_text("session-string", encoding="utf-8")

            status = dashboard_server.telegram_status(config_path=config_path, session_path=session_path)

        self.assertFalse(status["credentials_ready"])
        self.assertEqual(status["credentials_status"], "missing")
        self.assertTrue(status["session_ready"])
        self.assertEqual(status["login_state"], "credentials_missing")
        self.assertIn("credentials are missing", status["detail"])


    def test_telegram_credentials_reject_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"

            with self.assertRaises(ValueError):
                dashboard_server.save_telegram_credentials("bad", "a" * 32, config_path=config_path)
            with self.assertRaises(ValueError):
                dashboard_server.save_telegram_credentials("123", "not valid hash!", config_path=config_path)

            self.assertFalse(config_path.exists())


    def test_telegram_status_expires_stale_code_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            session_path = Path(tmp) / "session"
            dashboard_server.save_telegram_credentials("12345", "a" * 32, config_path=config_path, session_path=session_path)
            old_sent_at = (datetime.now(UTC) - timedelta(seconds=dashboard_server.TELEGRAM_LOGIN_CODE_TTL_SECONDS + 1)).isoformat().replace("+00:00", "Z")
            dashboard_server._telegram_login_set(
                {
                    "state": "code_sent",
                    "phone": "+15551234567",
                    "phone_code_hash": "hash",
                    "sent_at": old_sent_at,
                }
            )

            status = dashboard_server.telegram_status(config_path=config_path, session_path=session_path)

        self.assertEqual(status["login_state"], "ready_for_code")
        self.assertIn("expired", status["detail"].lower())
        self.assertEqual(dashboard_server._telegram_login_snapshot(), {})


    def test_telegram_verify_rejects_expired_code_state_before_network(self):
        old_sent_at = (datetime.now(UTC) - timedelta(seconds=dashboard_server.TELEGRAM_LOGIN_CODE_TTL_SECONDS + 1)).isoformat().replace("+00:00", "Z")
        dashboard_server._telegram_login_set(
            {
                "state": "code_sent",
                "phone": "+15551234567",
                "phone_code_hash": "hash",
                "sent_at": old_sent_at,
            }
        )

        with self.assertRaises(ValueError) as raised:
            dashboard_server.telegram_verify_code("12345")

        self.assertIn("expired", str(raised.exception).lower())
        self.assertEqual(dashboard_server._telegram_login_snapshot(), {})


    def test_telegram_send_code_converts_provider_errors_to_user_readable_error(self):
        with patch.object(
            dashboard_server,
            "_telegram_send_code_async",
            side_effect=RuntimeError("connection dropped"),
        ):
            with self.assertRaises(ValueError) as raised:
                dashboard_server.telegram_send_code("+15551234567")

        self.assertIn("Telegram code request failed", str(raised.exception))


    def test_telegram_verify_converts_provider_errors_to_user_readable_error(self):
        dashboard_server._telegram_login_set(
            {
                "state": "code_sent",
                "phone": "+15551234567",
                "phone_code_hash": "hash",
                "sent_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
        provider_error = type("PhoneCodeInvalidError", (Exception,), {})
        with patch.object(
            dashboard_server,
            "_telegram_verify_code_async",
            side_effect=provider_error("bad code"),
        ):
            with self.assertRaises(ValueError) as raised:
                dashboard_server.telegram_verify_code("12345")

        self.assertIn("rejected the verification code", str(raised.exception))


    def test_telegram_login_http_endpoint_uses_specialized_api(self):
        class FakeHandler:
            path = "/api/desk/telegram-login/send-code"
            status = None
            payload = None

            def _read_json_body(self):
                return {"phone": "+15551234567", "command": "ignored"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "telegram_send_code",
            return_value={
                "schema_version": "desk_telegram_status_v1",
                "credentials_ready": True,
                "session_ready": False,
                "login_state": "code_sent",
                "detail": "Telegram sent a verification code.",
                "next_step": "Enter the code in Signal Desk.",
                "config_path": "~/.config/tgcli/config.toml",
                "session_path": "~/.config/tgcli/session",
            },
        ) as send_code:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        send_code.assert_called_once_with("+15551234567")
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["telegram"]["login_state"], "code_sent")


    def test_telegram_login_http_endpoint_returns_json_for_unexpected_error(self):
        class FakeHandler:
            path = "/api/desk/telegram-login/send-code"
            status = None
            payload = None

            def _read_json_body(self):
                return {"phone": "+15551234567"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(dashboard_server, "telegram_send_code", side_effect=RuntimeError("provider exploded")):
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertFalse(handler.payload["ok"])
        self.assertIn("internal error", handler.payload["error"])


    def test_telegram_verify_http_endpoint_uses_specialized_api(self):
        class FakeHandler:
            path = "/api/desk/telegram-login/verify-code"
            status = None
            payload = None

            def _read_json_body(self):
                return {"code": "12345", "password": "secret", "command": "ignored"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "telegram_verify_code",
            return_value={
                "schema_version": "desk_telegram_status_v1",
                "credentials_ready": True,
                "session_ready": True,
                "login_state": "authorized",
                "detail": "Telegram is connected for local scans.",
                "next_step": "Run the first scan from Signal Desk.",
                "config_path": "~/.config/tgcli/config.toml",
                "session_path": "~/.config/tgcli/session",
            },
        ) as verify_code:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        verify_code.assert_called_once_with("12345", "secret")
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertTrue(handler.payload["telegram"]["session_ready"])


    def test_telegram_cancel_http_endpoint_clears_login_state(self):
        class FakeHandler:
            path = "/api/desk/telegram-login/cancel"
            status = None
            payload = None

            def _read_json_body(self):
                return {"command": "ignored"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "telegram_cancel_login",
            return_value={
                "schema_version": "desk_telegram_status_v1",
                "credentials_ready": True,
                "session_ready": False,
                "login_state": "ready_for_code",
                "detail": "Credentials are saved.",
                "next_step": "Enter your phone number.",
                "config_path": "~/.config/tgcli/config.toml",
                "session_path": "~/.config/tgcli/session",
            },
        ) as cancel_login:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        cancel_login.assert_called_once_with()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["telegram"]["login_state"], "ready_for_code")


    def test_desk_delivery_target_save_rejects_secret_or_command_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = monitor_state.connect(Path(tmp) / "tgcs.db")
            try:
                with self.assertRaises(ValueError):
                    dashboard_server.save_desk_delivery_target(
                        conn,
                        "telegram-bot-default",
                        {"chat_id": "123456", "enabled": True, "bot_token": "secret"},
                    )
                with self.assertRaises(ValueError):
                    dashboard_server.save_desk_delivery_target(
                        conn,
                        "telegram-bot-default",
                        {"chat_id": "123456", "enabled": True, "command": "tgcs monitor run"},
                    )
            finally:
                snapshot = monitor_state.dashboard_snapshot(conn)
                conn.close()

        self.assertNotIn("secret", json.dumps(snapshot, ensure_ascii=False))
        self.assertEqual(snapshot["delivery_targets"], [])


    def test_desk_delivery_target_save_returns_sanitized_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = monitor_state.connect(Path(tmp) / "tgcs.db")
            try:
                target = dashboard_server.save_desk_delivery_target(
                    conn,
                    "telegram-bot-default",
                    {"chat_id": "@signal_channel", "enabled": True},
                )
            finally:
                conn.close()

        self.assertEqual(target["schema_version"], "delivery_target_v1")
        self.assertTrue(target["enabled"])
        self.assertEqual(target["config"]["chat_id"], "@signal_channel")
        self.assertNotIn("token", json.dumps(target, ensure_ascii=False).lower())


    def test_desk_delivery_target_test_sends_live_test_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = monitor_state.connect(Path(tmp) / "tgcs.db")
            dashboard_server.save_desk_delivery_target(
                conn,
                "telegram-bot-default",
                {"chat_id": "123456", "enabled": True},
            )
            try:
                with patch.object(
                    dashboard_server.delivery,
                    "send_telegram_bot_message",
                    return_value=dashboard_server.delivery.DeliveryAttempt(
                        target_id="telegram-bot-default",
                        target_type="telegram_bot",
                        mode="live",
                        ok=True,
                        status="sent",
                    ),
                ) as send_mock:
                    result = dashboard_server.test_desk_delivery_target(
                        conn,
                        "telegram-bot-default",
                        {"chat_id": "654321"},
                    )
            finally:
                conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "live")
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args.kwargs["chat_id"], "654321")
        self.assertEqual(send_mock.call_args.kwargs["mode"], "live")


    def test_desk_delivery_target_test_rejects_user_controlled_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = monitor_state.connect(Path(tmp) / "tgcs.db")
            try:
                with self.assertRaises(ValueError):
                    dashboard_server.test_desk_delivery_target(
                        conn,
                        "telegram-bot-default",
                        {"chat_id": "123456", "mode": "live"},
                    )
            finally:
                conn.close()


    def test_delivery_chat_id_detection_uses_bot_updates_without_echoing_token(self):
        payload = {
            "ok": True,
            "result": [
                {"message": {"chat": {"id": 123456, "type": "private"}}},
            ],
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        token = dashboard_server.delivery.TelegramBotToken(token="123456:secret_token", source="keyring")
        with patch.object(dashboard_server.delivery, "resolve_telegram_bot_token", return_value=token):
            with patch.object(dashboard_server, "urlopen", return_value=FakeResponse()) as open_mock:
                result = dashboard_server.detect_desk_delivery_chat_id("telegram-bot-default", {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["chat_id"], "123456")
        self.assertEqual(result["source"], "telegram_bot_updates")
        self.assertNotIn("secret_token", json.dumps(result, ensure_ascii=False))
        self.assertIn("getUpdates", open_mock.call_args.args[0])


    def test_delivery_chat_id_detection_falls_back_to_telegram_session(self):
        with patch.object(dashboard_server, "_detect_chat_id_from_bot_updates", return_value=None):
            with patch.object(dashboard_server, "_telegram_current_user_chat_id", return_value="456789"):
                result = dashboard_server.detect_desk_delivery_chat_id("telegram-bot-default", {})

        self.assertTrue(result["ok"])
        self.assertEqual(result["chat_id"], "456789")
        self.assertEqual(result["source"], "telegram_session")


    def test_bot_gateway_status_uses_sanitized_state_and_authorized_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = monitor_state.connect(root / ".tgcs" / "tgcs.db")
            try:
                monitor_state.upsert_delivery_target(
                    conn,
                    {
                        "id": "telegram-bot-default",
                        "type": "telegram_bot",
                        "enabled": True,
                        "config": {"chat_id": "123456"},
                    },
                )
                state_path = root / ".tgcs" / "bot-gateway-state.json"
                state_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "bot_gateway_state_v1",
                            "pid": 123,
                            "started_at": "2026-05-12T12:00:00Z",
                            "last_poll_at": "2026-05-12T12:00:20Z",
                            "authorized_chat_count": 1,
                            "commands_installed": True,
                            "offset": 9,
                        }
                    ),
                    encoding="utf-8",
                )
                with patch.object(dashboard_server, "PROJECT_ROOT", root):
                    with patch.object(
                        dashboard_server,
                        "desk_notification_token_status",
                        return_value={"configured": True, "source": "keyring"},
                    ):
                        status = dashboard_server.desk_bot_gateway_status(
                            conn,
                            now=datetime(2026, 5, 12, 12, 1, tzinfo=UTC),
                        )
            finally:
                conn.close()

        status_text = json.dumps(status, ensure_ascii=False)
        self.assertEqual(status["schema_version"], "desk_bot_gateway_status_v1")
        self.assertEqual(status["gateway_status"], "running")
        self.assertTrue(status["token_configured"])
        self.assertEqual(status["authorized_chat_count"], 1)
        self.assertEqual(status["supported_commands"], ["/status", "/latest", "/sources", "/profiles", "/scan"])
        self.assertNotIn("123456", status_text)
        self.assertNotIn("token", status_text.lower().replace("token_configured", ""))


    def test_bot_identity_endpoint_returns_sanitized_local_result(self):
        from scripts import bot_gateway

        class FakeHandler:
            path = "/api/desk/bot-identity/apply"
            client_address = ("127.0.0.1", 12345)
            status = None
            payload = None

            def _read_json_body(self):
                return {}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        result = {
            "schema_version": "bot_identity_apply_result_v1",
            "name": "T-Sense",
            "description_updated": True,
            "short_description_updated": True,
            "commands_installed": True,
            "profile_photo_updated": False,
        }
        with patch.object(bot_gateway, "apply_bot_identity", return_value=result) as apply_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        apply_mock.assert_called_once_with()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["identity"], result)
        rendered = json.dumps(handler.payload, ensure_ascii=False)
        self.assertNotIn("token", rendered.lower())
        self.assertNotIn("chat", rendered.lower())


    def test_notification_token_status_prefers_env_without_echoing_token(self):
        stored = dashboard_server.local_credentials.StoredSecret(
            secret="local-token",
            updated_at="2026-05-10T00:00:00Z",
        )
        with patch.dict("os.environ", {dashboard_server.delivery.TELEGRAM_BOT_TOKEN_ENV: "env-token"}):
            with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
                with patch.object(dashboard_server.local_credentials, "read_secret", return_value=stored):
                    status = dashboard_server.desk_notification_token_status()

        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "environment")
        self.assertEqual(status["verification_status"], "env_unverified")
        rendered = json.dumps(status, ensure_ascii=False)
        self.assertNotIn("env-token", rendered)
        self.assertNotIn("local-token", rendered)


    def test_notification_token_status_reports_keyring_backend_and_label(self):
        stored = dashboard_server.local_credentials.StoredSecret(
            secret="local-token",
            updated_at="2026-05-10T00:00:00Z",
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
                with patch.object(dashboard_server.local_credentials, "backend", return_value="keyring", create=True):
                    with patch.object(
                        dashboard_server.local_credentials,
                        "store_label",
                        return_value="macOS Keychain",
                        create=True,
                    ):
                        with patch.object(dashboard_server.local_credentials, "read_secret", return_value=stored):
                            status = dashboard_server.desk_notification_token_status()

        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "keyring")
        self.assertEqual(status["verification_status"], "saved_unverified")
        self.assertEqual(status["local_store_backend"], "keyring")
        self.assertEqual(status["local_store_label"], "macOS Keychain")
        self.assertIn("macOS Keychain", status["detail"])


    def test_notification_token_save_and_clear_uses_credential_store_without_echoing_secret(self):
        store: dict[str, dashboard_server.local_credentials.StoredSecret] = {}

        def fake_write(target_name, secret, *, username="Signal Desk"):
            store[target_name] = dashboard_server.local_credentials.StoredSecret(
                secret=secret,
                updated_at="2026-05-10T00:00:00Z",
            )

        def fake_delete(target_name):
            store.pop(target_name, None)

        def fake_read(target_name):
            return store.get(target_name)

        with patch.dict("os.environ", {}, clear=True):
            with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
                with patch.object(dashboard_server.local_credentials, "write_secret", side_effect=fake_write):
                    with patch.object(dashboard_server.local_credentials, "delete_secret", side_effect=fake_delete):
                        with patch.object(dashboard_server.local_credentials, "read_secret", side_effect=fake_read):
                            saved = dashboard_server.update_desk_notification_token(
                                {"token": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12"}
                            )
                            cleared = dashboard_server.update_desk_notification_token({"clear": True})

        self.assertTrue(saved["configured"])
        self.assertEqual(saved["verification_status"], "saved_unverified")
        self.assertIn(
            saved["source"],
            {
                dashboard_server.local_credentials.BACKEND_WINDOWS,
                dashboard_server.local_credentials.BACKEND_KEYRING,
            },
        )
        self.assertFalse(cleared["configured"])
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12", json.dumps(saved, ensure_ascii=False))


    def test_notification_token_update_rejects_command_fields(self):
        with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
            with self.assertRaises(ValueError):
                dashboard_server.update_desk_notification_token(
                    {"token": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef12", "command": "tgcs monitor run"}
                )


    def test_notification_token_update_rejects_invalid_token_shapes(self):
        with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
            for bad_token in ["", "bad-token", "123:short", "123456:has space"]:
                with self.subTest(bad_token=bad_token):
                    with self.assertRaises(ValueError):
                        dashboard_server.update_desk_notification_token({"token": bad_token})


    def test_ai_settings_status_prefers_env_without_echoing_key(self):
        stored = dashboard_server.local_credentials.StoredSecret(
            secret="local-deepseek-key",
            updated_at="2026-05-10T00:00:00Z",
        )
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "env-deepseek-key"}, clear=True):
            with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
                with patch.object(dashboard_server.local_credentials, "read_secret", return_value=stored):
                    status = dashboard_server.desk_ai_settings_status()

        deepseek = next(item for item in status["providers"] if item["provider"] == "deepseek")
        self.assertTrue(deepseek["configured"])
        self.assertEqual(deepseek["source"], "environment")
        self.assertEqual(deepseek["verification_status"], "env_unverified")
        rendered = json.dumps(status, ensure_ascii=False)
        self.assertNotIn("env-deepseek-key", rendered)
        self.assertNotIn("local-deepseek-key", rendered)


    def test_ai_settings_status_reports_keyring_backend_and_label(self):
        stored = dashboard_server.local_credentials.StoredSecret(
            secret="local-deepseek-key",
            updated_at="2026-05-10T00:00:00Z",
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
                with patch.object(dashboard_server.local_credentials, "backend", return_value="keyring", create=True):
                    with patch.object(
                        dashboard_server.local_credentials,
                        "store_label",
                        return_value="Linux Secret Service/KWallet",
                        create=True,
                    ):
                        with patch.object(dashboard_server.local_credentials, "read_secret", return_value=stored):
                            status = dashboard_server.desk_ai_settings_status()

        deepseek = next(item for item in status["providers"] if item["provider"] == "deepseek")
        self.assertTrue(deepseek["configured"])
        self.assertEqual(deepseek["source"], "keyring")
        self.assertEqual(deepseek["verification_status"], "saved_unverified")
        self.assertEqual(status["local_store_backend"], "keyring")
        self.assertEqual(status["local_store_label"], "Linux Secret Service/KWallet")
        self.assertEqual(deepseek["local_store_backend"], "keyring")
        self.assertEqual(deepseek["local_store_label"], "Linux Secret Service/KWallet")


    def test_ai_settings_save_and_clear_uses_credential_store_without_echoing_secret(self):
        store: dict[str, dashboard_server.local_credentials.StoredSecret] = {}

        def fake_write(target_name, secret, *, username="Signal Desk"):
            store[target_name] = dashboard_server.local_credentials.StoredSecret(
                secret=secret,
                updated_at="2026-05-10T00:00:00Z",
            )

        def fake_delete(target_name):
            store.pop(target_name, None)

        def fake_read(target_name):
            return store.get(target_name)

        with patch.dict("os.environ", {}, clear=True):
            with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
                with patch.object(dashboard_server.local_credentials, "write_secret", side_effect=fake_write):
                    with patch.object(dashboard_server.local_credentials, "delete_secret", side_effect=fake_delete):
                        with patch.object(dashboard_server.local_credentials, "read_secret", side_effect=fake_read):
                            saved = dashboard_server.update_desk_ai_settings({"provider": "deepseek", "api_key": "sk-deepseek123"})
                            env = dashboard_server.desk_action_env()
                            cleared = dashboard_server.update_desk_ai_settings({"provider": "deepseek", "clear": True})

        deepseek_saved = next(item for item in saved["providers"] if item["provider"] == "deepseek")
        deepseek_cleared = next(item for item in cleared["providers"] if item["provider"] == "deepseek")
        self.assertTrue(deepseek_saved["configured"])
        self.assertTrue(deepseek_saved["usable_for_matching"])
        self.assertEqual(deepseek_saved["verification_status"], "saved_unverified")
        self.assertIn(
            deepseek_saved["source"],
            {
                dashboard_server.local_credentials.BACKEND_WINDOWS,
                dashboard_server.local_credentials.BACKEND_KEYRING,
            },
        )
        self.assertEqual(env["DEEPSEEK_API_KEY"], "sk-deepseek123")
        self.assertFalse(deepseek_cleared["configured"])
        self.assertNotIn("sk-deepseek123", json.dumps(saved, ensure_ascii=False))


    def test_ai_settings_separates_matching_keys_from_ocr_only_keys(self):
        xai_target = dashboard_server.DESK_AI_PROVIDER_CONFIGS["xai"]["target"]
        stored = dashboard_server.local_credentials.StoredSecret(
            secret="local-xai-key",
            updated_at="2026-05-10T00:00:00Z",
        )
        with patch.dict("os.environ", {}, clear=True):
            with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
                with patch.object(
                    dashboard_server.local_credentials,
                    "read_secret",
                    side_effect=lambda target_name: stored if target_name == xai_target else None,
                ):
                    status = dashboard_server.desk_ai_settings_status()

        xai = next(item for item in status["providers"] if item["provider"] == "xai")
        self.assertEqual(status["configured_count"], 1)
        self.assertEqual(status["matching_configured_count"], 0)
        self.assertEqual(status["ocr_configured_count"], 1)
        self.assertEqual(xai["purpose"], "ocr")
        self.assertTrue(xai["configured"])
        self.assertFalse(xai["usable_for_matching"])
        self.assertIn("OCR-only", xai["detail"])


    def test_ai_settings_update_rejects_command_fields_and_bad_keys(self):
        with patch.object(dashboard_server.local_credentials, "is_supported", return_value=True):
            with self.assertRaises(ValueError):
                dashboard_server.update_desk_ai_settings(
                    {"provider": "deepseek", "api_key": "sk-deepseek123", "command": "tgcs monitor run"}
                )
            for payload in (
                {"provider": "../bad", "api_key": "sk-deepseek123"},
                {"provider": "deepseek", "api_key": "short"},
                {"provider": "deepseek", "api_key": "has space key"},
            ):
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        dashboard_server.update_desk_ai_settings(payload)



if __name__ == "__main__":
    unittest.main()
