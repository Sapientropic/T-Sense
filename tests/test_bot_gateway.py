import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from scripts import bot_gateway, monitor_state, source_registry


class FakeTelegramBotHandler(BaseHTTPRequestHandler):
    updates_sent = False
    send_messages: list[dict] = []

    def log_message(self, format, *args):  # noqa: A002
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(raw or "{}")
        method = self.path.rsplit("/", 1)[-1]
        if method == "setMyCommands":
            self._json({"ok": True, "result": True})
            return
        if method == "getUpdates":
            if not FakeTelegramBotHandler.updates_sent:
                FakeTelegramBotHandler.updates_sent = True
                self._json(
                    {
                        "ok": True,
                        "result": [
                            {
                                "update_id": 100,
                                "message": {
                                    "chat": {"id": 12345},
                                    "text": "/status",
                                },
                            }
                        ],
                    }
                )
                return
            if FakeTelegramBotHandler.send_messages:
                self._json({"ok": False, "description": "stop smoke"})
                return
            self._json({"ok": True, "result": []})
            return
        if method == "sendMessage":
            FakeTelegramBotHandler.send_messages.append(payload)
            self._json({"ok": True, "result": {"message_id": 1}})
            return
        self._json({"ok": True, "result": True})

    def _json(self, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeBotApi:
    def __init__(self):
        self.messages = []
        self.callbacks = []
        self.commands_installed = False
        self.menu_button = None
        self.profile_photo = None

    def send_message(self, chat_id, text, *, reply_markup=None, parse_mode=None):
        self.messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup, "parse_mode": parse_mode}
        )

    def answer_callback_query(self, callback_query_id, text=""):
        self.callbacks.append({"callback_query_id": callback_query_id, "text": text})

    def set_my_commands(self):
        self.commands_installed = True

    def set_my_name(self, name):
        self.name = name

    def set_my_description(self, description):
        self.description = description

    def set_my_short_description(self, short_description):
        self.short_description = short_description

    def set_chat_menu_button(self):
        self.menu_button = "commands"

    def set_my_profile_photo(self, photo_path):
        self.profile_photo = photo_path


class FailingProfilePhotoApi(FakeBotApi):
    def set_my_profile_photo(self, photo_path):
        raise bot_gateway.BotGatewayError(f"cannot read {photo_path} with token 123456:ABCDEF_secret")


class BotGatewayTests(unittest.TestCase):
    def test_command_menu_contains_discoverable_actions(self):
        commands = {item["command"]: item["description"] for item in bot_gateway.BOT_COMMANDS}

        self.assertIn("status", commands)
        self.assertIn("scan", commands)
        self.assertIn("sources", commands)
        self.assertIn("latest", commands)
        self.assertIn("profiles", commands)
        self.assertIn("settings", commands)

    def test_main_menu_exposes_all_safe_status_surfaces(self):
        encoded = json.dumps(bot_gateway.main_menu_keyboard(), ensure_ascii=False)

        self.assertIn('"callback_data": "status"', encoded)
        self.assertIn('"callback_data": "latest"', encoded)
        self.assertIn('"callback_data": "sources"', encoded)
        self.assertIn('"callback_data": "profiles"', encoded)
        self.assertIn('"callback_data": "settings"', encoded)

    def test_apply_identity_sets_brand_text_commands_menu_and_profile_photo(self):
        api = FakeBotApi()

        result = bot_gateway.apply_bot_identity(api)

        self.assertEqual(result["schema_version"], "bot_identity_apply_result_v1")
        self.assertEqual(api.name, "T-Sense")
        self.assertIn("local-first", api.description)
        self.assertTrue(api.commands_installed)
        self.assertEqual(api.menu_button, "commands")
        self.assertEqual(Path(api.profile_photo).name, "bot-avatar.jpg")
        self.assertTrue(result["menu_button_updated"])
        self.assertTrue(result["profile_photo_updated"])
        self.assertTrue(result["steps"]["profile_photo"]["ok"])

    def test_apply_identity_reports_step_failure_without_sensitive_details(self):
        api = FailingProfilePhotoApi()

        result = bot_gateway.apply_bot_identity(api)

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["schema_version"], "bot_identity_apply_result_v1")
        self.assertTrue(result["commands_installed"])
        self.assertFalse(result["profile_photo_updated"])
        self.assertFalse(result["steps"]["profile_photo"]["ok"])
        self.assertIn("[redacted", result["steps"]["profile_photo"]["error"])
        self.assertNotIn(str(bot_gateway.BOT_AVATAR_PATH), rendered)
        self.assertNotIn("123456:ABCDEF_secret", rendered)

    def test_profile_photo_multipart_uses_static_jpg_attach_payload(self):
        class CapturingApi(bot_gateway.TelegramBotApi):
            def __init__(self):
                super().__init__("123456:ABCDEF_secret")
                self.multipart = None

            def request_multipart(self, method, fields, files):
                self.multipart = {"method": method, "fields": fields, "files": files}
                return {"ok": True, "result": True}

        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "avatar.jpg"
            photo.write_bytes(b"\xff\xd8fake-jpeg\xff\xd9")
            api = CapturingApi()
            api.set_my_profile_photo(photo)

        payload = json.loads(api.multipart["fields"]["photo"])
        self.assertEqual(api.multipart["method"], "setMyProfilePhoto")
        self.assertEqual(payload, {"type": "static", "photo": "attach://profile_photo"})
        self.assertEqual(list(api.multipart["files"]), ["profile_photo"])
        filename, content, content_type = api.multipart["files"]["profile_photo"]
        self.assertEqual(filename, "bot-avatar.jpg")
        self.assertEqual(content, b"\xff\xd8fake-jpeg\xff\xd9")
        self.assertEqual(content_type, "image/jpeg")

    def test_send_message_uses_markdown_parse_mode(self):
        class CapturingApi(bot_gateway.TelegramBotApi):
            def __init__(self):
                super().__init__("123456:ABCDEF_secret")
                self.payloads = []

            def request(self, method, payload=None):
                self.payloads.append({"method": method, "payload": payload})
                return {"ok": True, "result": {"message_id": 1}}

        api = CapturingApi()
        api.send_message("12345", "*Ready*", reply_markup={"inline_keyboard": []})

        payload = api.payloads[0]["payload"]
        self.assertEqual(payload["parse_mode"], "Markdown")
        self.assertEqual(payload["reply_markup"], {"inline_keyboard": []})

    def test_packaged_avatar_is_static_jpg_asset(self):
        data = bot_gateway.BOT_AVATAR_PATH.read_bytes()

        self.assertEqual(bot_gateway.BOT_AVATAR_PATH.suffix.lower(), ".jpg")
        self.assertEqual(data[:2], b"\xff\xd8")
        self.assertEqual(data[-2:], b"\xff\xd9")

    def test_intent_schema_rejects_extra_fields_unknown_actions_and_command_strings(self):
        from scripts import bot_intents

        valid_status = {
            "schema_version": "bot_intent_v1",
            "action": "status",
            "confidence": "high",
            "source": "llm",
            "args": {},
            "needs_confirmation": False,
            "safe_reply": "",
        }
        self.assertIsNone(
            bot_intents.validate_llm_intent_payload(
                {"schema_version": "bot_intent_v1", "action": "status", "args": {}, "command": "rm -rf ."}
            )
        )
        self.assertIsNone(bot_intents.validate_llm_intent_payload({**valid_status, "source": "deterministic"}))
        missing_safe_reply = dict(valid_status)
        missing_safe_reply.pop("safe_reply")
        self.assertIsNone(bot_intents.validate_llm_intent_payload(missing_safe_reply))
        self.assertIsNone(
            bot_intents.validate_llm_intent_payload(
                {"schema_version": "bot_intent_v1", "action": "shell", "args": {}}
            )
        )
        self.assertIsNone(
            bot_intents.validate_llm_intent_payload(
                {
                    "schema_version": "bot_intent_v1",
                    "action": "scan_profile_dry_run",
                    "args": {"profile_id": "jobs-fast; powershell"},
                }
            )
        )

    def test_intent_router_maps_knowledge_and_unsafe_requests_without_shell_access(self):
        from scripts import bot_intents

        knowledge = bot_intents.route_text_to_intent("怎么添加 Telegram 频道？", use_llm=False)
        unsafe = bot_intents.route_text_to_intent("run powershell Remove-Item -Recurse C:\\private", use_llm=False)

        self.assertEqual(knowledge.schema_version, "bot_intent_v1")
        self.assertEqual(knowledge.action, "knowledge_answer")
        self.assertEqual(knowledge.source, "deterministic-no-llm")
        self.assertEqual(unsafe.action, "knowledge_answer")
        self.assertIn("not", unsafe.safe_reply.casefold())
        self.assertNotIn("Remove-Item", unsafe.safe_reply)

    def test_bot_defaults_use_llm_for_free_text_knowledge_when_available(self):
        api = FakeBotApi()
        gateway = bot_gateway.BotGateway(api, allowed={"12345"})

        with patch.object(
            bot_gateway.bot_actions.bot_knowledge.BotKnowledge,
            "answer",
            return_value=bot_gateway.bot_actions.bot_knowledge.KnowledgeAnswer(
                text="AI answer from local docs.",
                sections=(),
                used_llm=True,
            ),
        ) as answer_mock:
            gateway.handle_text("12345", "怎么添加 Telegram 频道？")

        answer_mock.assert_called_once()
        self.assertTrue(answer_mock.call_args.kwargs["use_llm"])
        self.assertIn("AI answer from local docs", api.messages[-1]["text"])
        self.assertIn("Status", json.dumps(api.messages[-1]["reply_markup"]))

    def test_run_loop_uses_llm_by_default_and_can_opt_out(self):
        from scripts import bot_runtime

        captured: list[bool] = []

        class FakeApi:
            def __init__(self, token):
                self.token = token

            def get_updates(self, *, offset, timeout_seconds):
                raise KeyboardInterrupt

        class FakeLock:
            def __init__(self, _path):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        class CapturingGateway:
            def __init__(self, _api, *, use_llm, **_kwargs):
                captured.append(use_llm)
                self.allowed = {"12345"}

        def args(**overrides):
            base = {
                "lock": "bot.lock",
                "db": "state.db",
                "state": "bot-state.json",
                "skip_menu": True,
                "allow_chat_id": [],
                "poll_timeout": 0,
                "llm": False,
                "no_llm": False,
            }
            base.update(overrides)
            return argparse.Namespace(**base)

        with patch.object(bot_runtime, "load_bot_token", return_value="123456:ABCDEF_secret"):
            with patch.object(bot_runtime, "TelegramBotApi", FakeApi):
                with patch.object(bot_runtime, "BotGatewayLock", FakeLock):
                    with patch.object(bot_runtime, "load_state", return_value={}):
                        with patch.object(bot_runtime, "write_gateway_state"):
                            with patch.object(bot_runtime, "BotGateway", CapturingGateway):
                                with self.assertRaises(KeyboardInterrupt):
                                    bot_runtime.run_loop(args())
                                with self.assertRaises(KeyboardInterrupt):
                                    bot_runtime.run_loop(args(no_llm=True))

        self.assertEqual(captured, [True, False])

    def test_bot_llm_routing_requires_explicit_opt_in(self):
        routed = bot_gateway.BotIntent(action="status", source="llm")

        with patch.object(bot_gateway.bot_intents, "llm_intent", return_value=routed) as llm_mock:
            default_intent = bot_gateway.route_text_to_intent("semantic fuzzy intent zzz")
            opt_in_intent = bot_gateway.route_text_to_intent("semantic fuzzy intent zzz", use_llm=True)

        self.assertEqual(default_intent.action, "knowledge_answer")
        self.assertEqual(default_intent.source, "deterministic-no-llm")
        self.assertEqual(opt_in_intent, routed)
        llm_mock.assert_called_once_with("semantic fuzzy intent zzz")

    def test_intent_router_maps_common_natural_language_actions_without_llm(self):
        from scripts import bot_intents

        status = bot_intents.route_text_to_intent("我想看看 T-Sense 现在有没有配置好，下一步该做什么", use_llm=False)
        latest = bot_intents.route_text_to_intent("给我看看最新结果", use_llm=False)
        scan = bot_intents.route_text_to_intent(
            "I want a jobs-fast practice run from Telegram, not live delivery",
            use_llm=False,
        )
        sources = bot_intents.route_text_to_intent("add @remote_jobs to remote-work", use_llm=False)

        self.assertEqual(status.action, "status")
        self.assertEqual(latest.action, "latest")
        self.assertEqual(scan.action, "scan_profile_dry_run")
        self.assertEqual(scan.profile_id, "jobs-fast")
        self.assertEqual(sources.action, "sources_plan")
        self.assertEqual(sources.topic, "remote-work")

    def test_knowledge_answer_includes_safe_action_buttons(self):
        api = FakeBotApi()
        gateway = bot_gateway.BotGateway(api, allowed={"12345"}, use_llm=False)

        gateway.handle_text("12345", "怎么添加 Telegram 频道？")

        keyboard = api.messages[-1]["reply_markup"]["inline_keyboard"]
        encoded = json.dumps(keyboard, ensure_ascii=False)
        self.assertIn("status", encoded)
        self.assertIn("sources", encoded)
        self.assertIn("profiles", encoded)
        self.assertIn("settings", encoded)
        self.assertNotIn("12345", encoded)

    def test_menu_callbacks_route_profiles_and_settings(self):
        api = FakeBotApi()
        gateway = bot_gateway.BotGateway(api, allowed={"12345"}, use_llm=False)
        snapshot = {"profiles": [{"profile_id": "jobs-fast", "display_name": "Jobs Fast", "enabled": True}]}

        with patch.object(bot_gateway, "dashboard_snapshot", return_value=snapshot):
            gateway.handle_callback("12345", "cb-profiles", "profiles")
        gateway.handle_callback("12345", "cb-settings", "settings")

        self.assertEqual(api.callbacks[0]["callback_query_id"], "cb-profiles")
        self.assertEqual(api.callbacks[1]["callback_query_id"], "cb-settings")
        self.assertIn("Jobs Fast", api.messages[0]["text"])
        self.assertIn("Settings", api.messages[1]["text"])

    def test_llm_topic_inference_accepts_valid_topic_and_marks_invalid_fallback(self):
        from scripts import bot_intents

        valid = bot_intents.validate_llm_intent_payload(
            {
                "schema_version": "bot_intent_v1",
                "action": "sources_plan",
                "confidence": "high",
                "source": "llm",
                "args": {"instruction": "add @remote_jobs", "topic": "remote-work"},
                "needs_confirmation": True,
                "safe_reply": "",
            }
        )
        invalid = bot_intents.validate_llm_intent_payload(
            {
                "schema_version": "bot_intent_v1",
                "action": "sources_plan",
                "confidence": "high",
                "source": "llm",
                "args": {"instruction": "add @remote_jobs", "topic": "C:/private"},
                "needs_confirmation": True,
                "safe_reply": "",
            }
        )

        self.assertIsNotNone(valid)
        self.assertEqual(valid.topic, "remote-work")
        self.assertIsNotNone(invalid)
        self.assertEqual(invalid.topic, "jobs")
        self.assertIn("[⚠️]", invalid.safe_reply)

    def test_knowledge_corpus_reads_only_allowlisted_relative_docs(self):
        from scripts import bot_knowledge

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Setup\nAdd sources from Signal Desk.", encoding="utf-8")
            (root / "private.md").write_text("# Secret\nDo not load this.", encoding="utf-8")
            knowledge = bot_knowledge.BotKnowledge(root=root, allowlist=("README.md",))

            sections = knowledge.load_sections()
            answer = knowledge.answer("How do I add sources?", use_llm=False)

        self.assertEqual({section.path for section in sections}, {"README.md"})
        self.assertIn("Signal Desk", answer.text)
        self.assertNotIn("Secret", answer.text)

    def test_action_registry_scan_uses_fixed_desk_action_and_rejects_other_profiles(self):
        from scripts import bot_actions, bot_intents

        with patch.object(
            bot_actions.dashboard_server,
            "run_desk_action",
            return_value={
                "schema_version": "desk_action_result_v1",
                "action_id": "monitor_jobs_dry_run",
                "status": "success",
                "title": "Run AI review",
                "detail": "Fresh AI review finished.",
                "next_action": "Review cards.",
            },
        ) as run_mock:
            result = bot_actions.BotActionRegistry().execute(
                bot_intents.BotIntent(action="scan_profile_dry_run", args={"profile_id": "jobs-fast"})
            )

        run_mock.assert_called_once_with("monitor_jobs_dry_run")
        self.assertEqual(result.error_category, "")
        self.assertIn("Fresh AI review finished", result.text)

        rejected = bot_actions.BotActionRegistry().execute(
            bot_intents.BotIntent(action="scan_profile_dry_run", args={"profile_id": "market-news"})
        )
        self.assertEqual(rejected.error_category, "unsupported_request")
        self.assertIn("jobs-fast", rejected.text)
        self.assertNotIn("dry", rejected.text.casefold())

    def test_action_registry_scan_busy_reply_has_one_next_step(self):
        from scripts import bot_actions, bot_intents

        with patch.object(
            bot_actions.dashboard_server,
            "run_desk_action",
            return_value={
                "schema_version": "desk_action_result_v1",
                "action_id": "monitor_jobs_dry_run",
                "status": "blocked",
                "title": "Action already running",
                "detail": "AI review is already running.",
                "next_action": "Wait for the current action to finish, then refresh Signal Desk.",
            },
        ):
            result = bot_actions.BotActionRegistry().execute(
                bot_intents.BotIntent(action="scan_profile_dry_run", args={"profile_id": "jobs-fast"})
        )

        self.assertEqual(result.error_category, "action_busy")
        self.assertIn("AI review is already running.", result.text)
        self.assertIn("Next: Wait for the current action to finish", result.text)

    def test_redaction_removes_sensitive_telegram_reply_content(self):
        from scripts import bot_actions

        text = (
            "token 123456:ABCDEF_secret\n"
            "Authorization: Bearer sk-localSecret12345\n"
            "MY_SECRET=\"plain-secret-value\" ghp_1234567890abcdefABCDEF1234567890abcd\n"
            "args=['tgcs','scan']\n"
            "path C:\\Users\\Administrator\\secret\\scan.jsonl and /home/sdy/private/scan.jsonl and \\\\server\\share\\secret.txt\n"
            "chat_id 123456789\n"
            "Traceback (most recent call last): raw message text"
        )

        redacted = bot_actions.redact_telegram_reply(text)

        self.assertNotIn("123456:ABCDEF_secret", redacted)
        self.assertNotIn("sk-localSecret12345", redacted)
        self.assertNotIn("plain-secret-value", redacted)
        self.assertNotIn("ghp_1234567890abcdefABCDEF1234567890abcd", redacted)
        self.assertNotIn("['tgcs','scan']", redacted)
        self.assertNotIn("C:\\Users", redacted)
        self.assertNotIn("/home/sdy", redacted)
        self.assertNotIn("\\\\server\\share", redacted)
        self.assertNotIn("123456789", redacted)
        self.assertNotIn("Traceback", redacted)
        self.assertIn("[redacted", redacted)

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
        self.assertEqual(preview_mock.call_args.args[0]["confirm_external_ai"], False)
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
        self.assertIn("Bot delivery: private Telegram bot ready", text)

    def test_status_summary_surfaces_delivery_and_proof_loop_next_step(self):
        snapshot = {
            "setup_status": {"stage": "ready", "next_step": "Review cards"},
            "inbox": [],
            "runs": [{"status": "complete", "profile_id": "jobs-fast"}],
            "delivery_targets": [],
            "validation_summary": {
                "schema_version": "dashboard_validation_summary_v1",
                "runs_count": 1,
                "first_decision_minutes": 7,
                "first_decision_action": "keep",
            },
        }

        text = bot_gateway.status_summary(snapshot)

        self.assertIn("Bot delivery: needs chat in Settings > Alerts", text)
        self.assertIn("Proof loop: first decision 7 min (keep)", text)

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

    def test_card_lifecycle_callback_uses_local_review_state(self):
        api = FakeBotApi()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / ".tgcs" / "tgcs.db"
            conn = monitor_state.connect(db)
            try:
                cards = monitor_state.upsert_review_cards(
                    conn,
                    profile_id="jobs-fast",
                    run_id="run-1",
                    items=[
                        {
                            "topic": "Frontend role",
                            "rating": "high",
                            "decision_state": {"status": "new", "semantic_cluster": "role-1"},
                            "source_message_refs": [{"channel": "jobs", "id": 1}],
                        }
                    ],
                )
                card_id = cards[0]["card_id"]
            finally:
                conn.close()

            gateway = bot_gateway.BotGateway(api, db_path=db, allowed={"12345"})
            gateway.handle_callback("12345", "cb-ok", f"card:applied:{card_id}")
            conn = monitor_state.connect(db)
            try:
                updated = monitor_state.get_review_card(conn, card_id)
            finally:
                conn.close()

        self.assertEqual(api.callbacks[-1]["text"], "Marked Applied")
        self.assertEqual(updated["opportunity_status"], "applied")
        self.assertIn("Applied", api.messages[-1]["text"])

    def test_latest_summary_attaches_lifecycle_buttons_for_first_actionable_card(self):
        api = FakeBotApi()
        gateway = bot_gateway.BotGateway(api, allowed={"12345"})
        snapshot = {
            "opportunity_summary": {
                "display_name": "Developer Opportunity",
                "status": "complete",
                "scanned_count": 120,
                "matched_count": 9,
                "review_card_count": 3,
                "high_actionable_count": 1,
                "alert_count": 1,
                "top_items": [
                    {
                        "title": "Frontend role",
                        "rating": "high",
                        "decision_status": "new",
                        "why": "raw Telegram body must not be needed here",
                    }
                ],
                "next_action": {"label": "Review priority cards", "detail": "1 card ready", "command": ""},
            },
            "inbox": [
                {
                    "card_id": "card_abc123",
                    "title": "Frontend role",
                    "rating": "high",
                    "decision_status": "new",
                    "opportunity_status": "open",
                    "status": "pending",
                }
            ],
        }

        with patch.object(bot_gateway, "dashboard_snapshot", return_value=snapshot):
            gateway.handle_text("12345", "/latest")

        keyboard = api.messages[-1]["reply_markup"]["inline_keyboard"]
        encoded = json.dumps(keyboard)
        message = api.messages[-1]["text"]
        self.assertIn("Developer Opportunity latest", message)
        self.assertIn("Scanned: 120 | Matched: 9 | Cards: 3 | High: 1 | Alerts: 1", message)
        self.assertIn("- Frontend role (high/new)", message)
        self.assertIn("Next: Review priority cards", message)
        self.assertIn("card:applied:card_abc123", encoded)
        self.assertIn("card:saved:card_abc123", encoded)
        self.assertNotIn("12345", encoded)

    def test_latest_summary_keeps_legacy_items_fallback(self):
        message = bot_gateway.latest_summary(
            {
                "opportunity_summary": {
                    "title": "Latest results",
                    "detail": "1 legacy item ready",
                    "items": [{"label": "Legacy card", "rating": "medium"}],
                }
            }
        )

        self.assertIn("- Legacy card (medium)", message)

    def test_gateway_state_writes_health_without_chat_ids_or_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bot-gateway-state.json"
            bot_gateway.write_gateway_state(
                path,
                offset=10,
                started_at="2026-05-12T12:00:00Z",
                authorized_chat_count=2,
                commands_installed=True,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "bot_gateway_state_v1")
        self.assertEqual(payload["offset"], 10)
        self.assertEqual(payload["authorized_chat_count"], 2)
        self.assertTrue(payload["commands_installed"])
        self.assertNotIn("chat_id", json.dumps(payload))
        self.assertNotIn("token", json.dumps(payload).lower())

    def test_gateway_lock_rejects_second_local_process_without_leaking_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "bot-gateway.lock"

            with bot_gateway.BotGatewayLock(lock_path):
                with self.assertRaises(bot_gateway.BotGatewayError) as raised:
                    with bot_gateway.BotGatewayLock(lock_path):
                        pass

        message = str(raised.exception)
        self.assertIn("already running", message)
        self.assertNotIn(str(lock_path), message)

    def test_gateway_process_handles_update_against_fake_telegram_api(self):
        FakeTelegramBotHandler.updates_sent = False
        FakeTelegramBotHandler.send_messages = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeTelegramBotHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / ".tgcs" / "tgcs.db"
            state = root / ".tgcs" / "bot-state.json"
            lock = root / ".tgcs" / "bot.lock"
            env = {
                **os.environ,
                "TGCS_TELEGRAM_BOT_TOKEN": "123456:TEST_TOKEN",
                "TGCS_BOT_API_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "TGCS_BOT_ALLOWED_CHAT_IDS": "12345",
                "PYTHONUNBUFFERED": "1",
            }
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(bot_gateway.PROJECT_ROOT / "scripts" / "bot_gateway.py"),
                    "run",
                    "--db",
                    str(db),
                    "--state",
                    str(state),
                    "--lock",
                    str(lock),
                    "--poll-timeout",
                    "0",
                    "--no-llm",
                ],
                cwd=bot_gateway.PROJECT_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.time() + 10
                while time.time() < deadline and not FakeTelegramBotHandler.send_messages:
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
                deadline = time.time() + 10
                while time.time() < deadline:
                    if process.poll() is not None:
                        break
                    if state.exists():
                        payload = json.loads(state.read_text(encoding="utf-8"))
                        if payload.get("last_error"):
                            break
                    time.sleep(0.1)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                server.shutdown()
                thread.join(timeout=5)

            sent_text = "\n".join(str(item.get("text") or "") for item in FakeTelegramBotHandler.send_messages)
            self.assertIn("T-Sense status", sent_text)
            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "bot_gateway_state_v1")
            self.assertTrue(payload["commands_installed"])
            self.assertEqual(payload["authorized_chat_count"], 1)
            self.assertIn("Telegram Bot API rejected getUpdates", payload.get("last_error", ""))
            with bot_gateway.BotGatewayLock(lock):
                pass
            self.assertFalse(lock.exists())

    def test_tgcs_bot_run_delegates_to_fixed_gateway_script(self):
        from tests.tgcs_cli import load_tgcs_module

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
        from tests.tgcs_cli import load_tgcs_module

        tgcs = load_tgcs_module(self)

        def fake_run(cmd, check=False, cwd=None):
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
            exit_code = tgcs.main(["bot", "run", "--skip-menu"])

        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertEqual(exit_code, 0)
        self.assertIn("--skip-menu", cmd)

    def test_tgcs_bot_autostart_commands_delegate_to_gateway_script(self):
        from tests.tgcs_cli import load_tgcs_module

        tgcs = load_tgcs_module(self)
        calls: list[list[str]] = []

        def fake_run(cmd, check=False, cwd=None):
            calls.append([str(part) for part in cmd])
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(tgcs.subprocess, "run", side_effect=fake_run):
            self.assertEqual(tgcs.main(["bot", "install-autostart"]), 0)
            self.assertEqual(tgcs.main(["bot", "remove-autostart"]), 0)
            self.assertEqual(tgcs.main(["bot", "status"]), 0)

        self.assertEqual([call[2] for call in calls], ["install-autostart", "remove-autostart", "status"])
        for call in calls:
            self.assertIn("bot_gateway.py", call[1])
            self.assertNotIn("token", " ".join(call).lower())

    def test_tgcs_bot_run_can_opt_out_of_default_llm(self):
        from tests.tgcs_cli import load_tgcs_module

        tgcs = load_tgcs_module(self)
        calls: list[list[str]] = []

        def fake_run(cmd, check=False, cwd=None):
            calls.append([str(part) for part in cmd])
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(tgcs.subprocess, "run", side_effect=fake_run):
            self.assertEqual(tgcs.main(["bot", "run"]), 0)
            self.assertEqual(tgcs.main(["bot", "run", "--no-llm"]), 0)

        self.assertNotIn("--llm", calls[0])
        self.assertNotIn("--no-llm", calls[0])
        self.assertIn("--no-llm", calls[1])


if __name__ == "__main__":
    unittest.main()
