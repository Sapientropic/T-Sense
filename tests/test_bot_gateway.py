import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import bot_gateway, monitor_state, source_registry


class FakeBotApi:
    def __init__(self):
        self.messages = []
        self.callbacks = []
        self.commands_installed = False

    def send_message(self, chat_id, text, *, reply_markup=None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})

    def answer_callback_query(self, callback_query_id, text=""):
        self.callbacks.append({"callback_query_id": callback_query_id, "text": text})

    def set_my_commands(self):
        self.commands_installed = True


class BotGatewayTests(unittest.TestCase):
    def test_command_menu_contains_discoverable_actions(self):
        commands = {item["command"]: item["description"] for item in bot_gateway.BOT_COMMANDS}

        self.assertIn("status", commands)
        self.assertIn("scan", commands)
        self.assertIn("sources", commands)
        self.assertIn("latest", commands)

    def test_unauthorized_chat_gets_setup_message_without_action(self):
        api = FakeBotApi()
        gateway = bot_gateway.BotGateway(api, allowed={"11111"})

        gateway.handle_text("22222", "/scan")

        self.assertEqual(len(api.messages), 1)
        self.assertIn("not authorized", api.messages[0]["text"])

    def test_source_plan_preview_requires_same_chat_callback_before_apply(self):
        api = FakeBotApi()
        gateway = bot_gateway.BotGateway(api, allowed={"12345"}, use_llm=False)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / ".tgcs" / "sources.json"
            source_registry.import_channels(["old_jobs"], registry, dry_run=False, topics=["jobs"], input_path="test")
            with patch.object(bot_gateway.dashboard_server, "PROJECT_ROOT", root):
                gateway.handle_text("12345", "add @remote_jobs; remove @old_jobs")
                preview_message = api.messages[-1]
                callback_data = preview_message["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
                gateway.handle_callback("99999", "cb-wrong", callback_data)
                gateway.handle_callback("12345", "cb-ok", callback_data)
                listed = bot_gateway.dashboard_server.desk_sources()

        self.assertIn("Source plan ready", preview_message["text"])
        self.assertIn("Apply source plan", json.dumps(preview_message["reply_markup"]))
        self.assertEqual(api.callbacks[0]["text"], "Open Signal Desk Settings to authorize this chat.")
        self.assertEqual(listed["source_count"], 1)
        self.assertEqual(listed["sources"][0]["channel"], "remote_jobs")

    def test_source_plan_apply_uses_cached_resolved_plan(self):
        api = FakeBotApi()
        gateway = bot_gateway.BotGateway(api, allowed={"12345"})

        preview_result = {
            "title": "Source plan ready",
            "detail": "Review the plan, then apply it.",
            "added_count": 1,
            "updated_count": 0,
            "removed_count": 0,
            "enabled_count": 0,
            "disabled_count": 0,
            "preview_sources": [{"label": "remote_jobs", "source_id": "telegram:remote_jobs"}],
            "resolved_plan": {"add": ["remote_jobs"], "remove": [], "disable": [], "enable": []},
        }
        applied_result = {
            "title": "Source plan applied",
            "added_count": 1,
            "updated_count": 0,
            "removed_count": 0,
            "enabled_count": 0,
            "disabled_count": 0,
        }

        with patch.object(bot_gateway.dashboard_server, "run_source_assistant", return_value=preview_result) as preview_mock:
            with patch.object(
                bot_gateway.dashboard_server,
                "apply_source_assistant_resolved_plan",
                return_value=applied_result,
            ) as apply_mock:
                gateway.handle_text("12345", "add @remote_jobs")
                callback_data = api.messages[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
                gateway.handle_callback("12345", "cb-ok", callback_data)

        self.assertEqual(preview_mock.call_count, 1)
        apply_mock.assert_called_once_with({"add": ["remote_jobs"], "remove": [], "disable": [], "enable": []}, "jobs")
        self.assertIn("Source plan applied", api.messages[-1]["text"])

    def test_source_plan_confirmation_expires(self):
        api = FakeBotApi()
        gateway = bot_gateway.BotGateway(api, allowed={"12345"})
        gateway.pending_source_plans["old"] = bot_gateway.PendingSourcePlan(
            chat_id="12345",
            topic="jobs",
            resolved_plan={"add": ["remote_jobs"], "remove": [], "disable": [], "enable": []},
            created_at=0,
        )

        with patch.object(bot_gateway.time, "time", return_value=bot_gateway.PENDING_SOURCE_PLAN_TTL_SECONDS + 1):
            gateway.handle_callback("12345", "cb-old", "sources_apply:old")

        self.assertEqual(api.callbacks[-1]["text"], "Source plan expired.")

    def test_status_summary_does_not_render_chat_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / ".tgcs" / "tgcs.db"
            conn = monitor_state.connect(db)
            try:
                monitor_state.upsert_delivery_target(
                    conn,
                    {
                        "id": "telegram-bot-default",
                        "type": "telegram_bot",
                        "enabled": True,
                        "config": {"chat_id": "123456789"},
                    },
                )
                snapshot = monitor_state.dashboard_snapshot(conn)
            finally:
                conn.close()

        text = bot_gateway.status_summary(snapshot)

        self.assertNotIn("123456789", text)
        self.assertIn("T-Sense status", text)

    def test_allowed_chats_only_use_enabled_telegram_bot_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / ".tgcs" / "tgcs.db"
            conn = monitor_state.connect(db)
            try:
                monitor_state.upsert_delivery_target(
                    conn,
                    {
                        "id": "telegram-bot-default",
                        "type": "telegram_bot",
                        "enabled": True,
                        "config": {"chat_id": "111111"},
                    },
                )
                monitor_state.upsert_delivery_target(
                    conn,
                    {
                        "id": "email-default",
                        "type": "email",
                        "enabled": True,
                        "config": {"chat_id": "222222"},
                    },
                )
            finally:
                conn.close()

            self.assertEqual(bot_gateway.allowed_chat_ids_from_db(db), {"111111"})

    def test_gateway_refreshes_allowed_chats_from_saved_settings(self):
        api = FakeBotApi()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / ".tgcs" / "tgcs.db"
            conn = monitor_state.connect(db)
            conn.close()
            gateway = bot_gateway.BotGateway(api, db_path=db)
            conn = monitor_state.connect(db)
            try:
                monitor_state.upsert_delivery_target(
                    conn,
                    {
                        "id": "telegram-bot-default",
                        "type": "telegram_bot",
                        "enabled": True,
                        "config": {"chat_id": "12345"},
                    },
                )
            finally:
                conn.close()

            with patch.object(bot_gateway, "dashboard_snapshot", return_value={}):
                gateway.handle_text("12345", "/status")

        self.assertIn("T-Sense status", api.messages[-1]["text"])

    def test_tgcs_bot_run_delegates_to_fixed_gateway_script(self):
        from tests.test_tgcs_cli import load_tgcs_module

        tgcs = load_tgcs_module(self)

        def fake_run(cmd, check=False, cwd=None):
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
            exit_code = tgcs.main(["bot", "run", "--allow-chat-id", "12345", "--no-llm", "--install-menu"])

        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertEqual(exit_code, 0)
        self.assertIn("bot_gateway.py", cmd[1])
        self.assertIn("run", cmd)
        self.assertIn("--allow-chat-id", cmd)
        self.assertIn("--no-llm", cmd)
        self.assertIn("--install-menu", cmd)

    def test_tgcs_bot_run_can_skip_default_menu_installation(self):
        from tests.test_tgcs_cli import load_tgcs_module

        tgcs = load_tgcs_module(self)

        def fake_run(cmd, check=False, cwd=None):
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
            exit_code = tgcs.main(["bot", "run", "--skip-menu"])

        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertEqual(exit_code, 0)
        self.assertIn("--skip-menu", cmd)


if __name__ == "__main__":
    unittest.main()
