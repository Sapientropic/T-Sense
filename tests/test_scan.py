import asyncio
import getpass
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from scripts import scan
from telethon.errors import SessionPasswordNeededError


def _make_mock_message(msg_id: int, date_str: str, text: str = ""):
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.sender_id = None
    msg.media = None
    msg.reply_to = None
    if date_str:
        text_date = date_str
        if text_date.endswith("Z"):
            text_date = f"{text_date[:-1]}+00:00"
        msg.date = datetime.fromisoformat(text_date)
    else:
        msg.date = None
    return msg


class AsyncIteratorMock:
    """Wrap a list as an async iterator for mocking iter_dialogs()."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


class ScanTests(unittest.TestCase):
    def test_precise_time_filter_keeps_only_messages_at_or_after_cutoff(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        rows = [
            {"id": 1, "date": "2026-05-06T07:29:59+00:00", "text": "old"},
            {"id": 2, "date": "2026-05-06T07:30:00+00:00", "text": "boundary"},
            {"id": 3, "date": "2026-05-06T08:00:00Z", "text": "new"},
        ]

        kept, skipped = scan.filter_messages(rows, cutoff)

        self.assertEqual([row["id"] for row in kept], [2, 3])
        self.assertEqual(skipped, 0)

    def test_channel_read_stops_at_cutoff(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        msgs = [
            _make_mock_message(3, "2026-05-06T08:00:00+00:00"),
            _make_mock_message(2, "2026-05-06T07:30:00+00:00"),
            _make_mock_message(1, "2026-05-06T06:00:00+00:00"),
        ]

        client = MagicMock()

        async def _iter_msgs(*a, **kw):
            for m in msgs:
                yield m

        client.iter_messages = _iter_msgs

        result = asyncio.run(
            scan.read_channel(client, "entity", "jobs", cutoff, 5000)
        )

        self.assertFalse(result.incomplete)
        self.assertEqual(result.raw_count, 3)
        self.assertEqual([m["id"] for m in result.messages], [3, 2])

    def test_channel_read_reports_incomplete_at_safety_cap(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        # All messages within window — iter_messages yields until safety cap
        msgs = [
            _make_mock_message(i, "2026-05-06T09:00:00+00:00") for i in range(6)
        ]

        client = MagicMock()

        async def _iter_msgs(*a, limit=None, **kw):
            count = 0
            for m in msgs:
                if limit is not None and count >= limit:
                    return
                yield m
                count += 1

        client.iter_messages = _iter_msgs

        result = asyncio.run(
            scan.read_channel(client, "entity", "jobs", cutoff, 4)
        )

        self.assertTrue(result.incomplete)
        self.assertEqual(result.raw_count, 4)

    def test_channel_read_is_complete_when_cutoff_is_seen_at_safety_cap(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        msgs = [
            _make_mock_message(3, "2026-05-06T08:00:00+00:00"),
            _make_mock_message(2, "2026-05-06T07:30:00+00:00"),
            _make_mock_message(1, "2026-05-06T06:00:00+00:00"),
        ]

        client = MagicMock()

        async def _iter_msgs(*a, limit=None, **kw):
            for m in msgs[:limit]:
                yield m

        client.iter_messages = _iter_msgs

        result = asyncio.run(
            scan.read_channel(client, "entity", "jobs", cutoff, 3)
        )

        self.assertFalse(result.incomplete)
        self.assertEqual(result.raw_count, 3)
        self.assertEqual([m["id"] for m in result.messages], [3, 2])

    def test_load_channel_list_trims_whitespace_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "channels.txt"
            path.write_text(
                "\n# comment\n  jobs_a  \n\njobs_b\n", encoding="utf-8"
            )

            self.assertEqual(
                scan.load_channel_list(path), ["jobs_a", "jobs_b"]
            )

    def test_resolve_entity_by_username(self):
        entity = MagicMock()
        client = MagicMock()
        client.get_entity = AsyncMock(return_value=entity)

        result = asyncio.run(scan.resolve_entity(client, "remote_italic"))
        self.assertEqual(result, entity)

    def test_resolve_entity_by_display_name(self):
        entity = MagicMock()
        entity.username = "remote_italic"

        dialog = MagicMock()
        dialog.name = "Remote Italic"
        dialog.entity = entity

        client = MagicMock()
        client.get_entity = AsyncMock(side_effect=Exception("not found"))
        client.iter_dialogs = MagicMock(return_value=AsyncIteratorMock([dialog]))

        result = asyncio.run(scan.resolve_entity(client, "Remote Italic"))
        self.assertEqual(result, entity)

    def test_resolve_entity_raises_on_unknown(self):
        client = MagicMock()
        client.get_entity = AsyncMock(side_effect=Exception("not found"))
        client.iter_dialogs = MagicMock(return_value=AsyncIteratorMock([]))

        with self.assertRaises(scan.ScanError):
            asyncio.run(scan.resolve_entity(client, "nonexistent_channel"))

    def test_message_to_dict_extracts_media_fields(self):
        msg = MagicMock()
        msg.id = 42
        msg.date = datetime(2026, 5, 6, 8, 0, tzinfo=timezone.utc)
        msg.text = "hello"
        msg.sender_id = 123
        msg.reply_to = None
        msg.voice = False
        msg.video = False

        # Use a real MessageMediaPhoto instance for isinstance check
        from telethon.tl.types import MessageMediaPhoto as RealPhoto

        msg.media = RealPhoto(photo=MagicMock(), spoiler=False)

        result = scan.message_to_dict(msg, "test_channel")
        self.assertTrue(result["has_photo"])
        self.assertEqual(result["media_type"], "MessageMediaPhoto")
        self.assertEqual(result["media_group"], "photo")
        self.assertNotIn("media_path", result)

    def test_ocr_default_is_disabled_even_when_openai_key_exists(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            parser = scan.build_parser()
            args = parser.parse_args(["channel_lists/example.txt"])

            self.assertIsNone(scan._make_ocr_config(args))

    def test_ocr_openai_provider_uses_openai_default_base_url(self):
        created = []

        class FakeOpenAI:
            def __init__(self, *, base_url, api_key):
                created.append((base_url, api_key))

        fake_openai = SimpleNamespace(OpenAI=FakeOpenAI)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch.object(scan, "openai", fake_openai):
                parser = scan.build_parser()
                args = parser.parse_args(
                    [
                        "channel_lists/example.txt",
                        "--ocr",
                        "--ocr-provider",
                        "openai",
                    ]
                )

                cfg = scan._make_ocr_config(args)

        self.assertIsNotNone(cfg)
        self.assertEqual(created[0], ("https://api.openai.com/v1", "sk-test"))

    def test_ocr_xai_provider_uses_current_xai_image_model(self):
        created = []

        class FakeOpenAI:
            def __init__(self, *, base_url, api_key):
                created.append((base_url, api_key))

        fake_openai = SimpleNamespace(OpenAI=FakeOpenAI)
        with patch.dict(os.environ, {"XAI_API_KEY": "xai-test"}, clear=True):
            with patch.object(scan, "openai", fake_openai):
                parser = scan.build_parser()
                args = parser.parse_args(
                    [
                        "channel_lists/example.txt",
                        "--ocr",
                        "--ocr-provider",
                        "xai",
                    ]
                )

                cfg = scan._make_ocr_config(args)

        self.assertIsNotNone(cfg)
        self.assertEqual(created[0], ("https://api.x.ai/v1", "xai-test"))
        self.assertEqual(cfg.model, "grok-4.3")

    def test_ocr_custom_provider_uses_explicit_base_url(self):
        created = []

        class FakeOpenAI:
            def __init__(self, *, base_url, api_key):
                created.append((base_url, api_key))

        fake_openai = SimpleNamespace(OpenAI=FakeOpenAI)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            with patch.object(scan, "openai", fake_openai):
                parser = scan.build_parser()
                args = parser.parse_args(
                    [
                        "channel_lists/example.txt",
                        "--ocr",
                        "--ocr-provider",
                        "custom",
                        "--ocr-base-url",
                        "http://localhost:11434/v1",
                    ]
                )

                cfg = scan._make_ocr_config(args)

        self.assertIsNotNone(cfg)
        self.assertEqual(created[0], ("http://localhost:11434/v1", "sk-test"))

    def test_scan_initial_limit_env_is_deprecated_and_ignored(self):
        with patch.dict(os.environ, {"SCAN_INITIAL_LIMIT": "abc"}, clear=True):
            parser = scan.build_parser()
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                args = parser.parse_args(["channel_lists/example.txt"])
                scan.warn_deprecated_options(["channel_lists/example.txt"], args)

        self.assertIn("SCAN_INITIAL_LIMIT", stderr.getvalue())
        self.assertIn("ignored", stderr.getvalue())

    def test_invalid_scan_env_reports_parser_error_before_help(self):
        with patch.dict(os.environ, {"SCAN_DELAY": "nope"}, clear=True):
            parser = scan.build_parser()
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                with self.assertRaises(SystemExit):
                    parser.parse_args(["--help"])

        self.assertIn("SCAN_DELAY", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_run_scan_passes_flood_wait_threshold_to_telethon_client(self):
        created = {}

        class FakeClient:
            def __init__(self, session, api_id, api_hash, *, flood_sleep_threshold):
                created["session"] = session
                created["api_id"] = api_id
                created["api_hash"] = api_hash
                created["flood_sleep_threshold"] = flood_sleep_threshold

            async def connect(self):
                return None

            async def is_user_authorized(self):
                return True

            async def disconnect(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            channel_list = Path(tmp) / "channels.txt"
            channel_list.write_text("jobs\n", encoding="utf-8")
            output_dir = Path(tmp) / "output"
            parser = scan.build_parser()
            args = parser.parse_args(
                [
                    str(channel_list),
                    "--output-dir",
                    str(output_dir),
                    "--max-flood-wait-seconds",
                    "42",
                ]
            )

            async def fake_resolve_entity(client, channel_name):
                return f"entity:{channel_name}"

            async def fake_read_channel(**kwargs):
                return scan.ChannelResult(
                    channel=kwargs["channel_name"],
                    messages=[],
                    raw_count=0,
                    skipped_missing_date=0,
                    limit=kwargs["max_limit"],
                    incomplete=False,
                    ocr_count=0,
                    stderr="",
                )

            with patch.object(scan, "load_config", return_value=scan.ScannerConfig(1, "hash", "session")):
                with patch.object(scan, "StringSession", return_value="fake-session"):
                    with patch.object(scan, "TelegramClient", FakeClient):
                        with patch.object(scan, "resolve_entity", side_effect=fake_resolve_entity):
                            with patch.object(scan, "read_channel", side_effect=fake_read_channel):
                                exit_code = asyncio.run(scan._run_scan(args))

        self.assertEqual(exit_code, 0)
        self.assertEqual(created["session"], "fake-session")
        self.assertEqual(created["api_id"], 1)
        self.assertEqual(created["api_hash"], "hash")
        self.assertEqual(created["flood_sleep_threshold"], 42)

    def test_run_scan_uses_bounded_source_concurrency_and_writes_source_order(self):
        class FakeClient:
            def __init__(self, session, api_id, api_hash, *, flood_sleep_threshold):
                pass

            async def connect(self):
                return None

            async def is_user_authorized(self):
                return True

            async def disconnect(self):
                return None

        active = 0
        max_active = 0

        with tempfile.TemporaryDirectory() as tmp:
            channel_list = Path(tmp) / "channels.txt"
            channel_list.write_text("jobs_a\njobs_b\njobs_c\n", encoding="utf-8")
            output_dir = Path(tmp) / "output"
            output_path = output_dir / "scan.jsonl"
            parser = scan.build_parser()
            args = parser.parse_args(
                [
                    str(channel_list),
                    "--output-dir",
                    str(output_dir),
                    "--output",
                    str(output_path),
                    "--delay",
                    "0",
                    "--scan-concurrency",
                    "2",
                ]
            )

            async def fake_resolve_entity(client, channel_name):
                return f"entity:{channel_name}"

            async def fake_read_channel(**kwargs):
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                try:
                    await asyncio.sleep(0.01)
                    channel = kwargs["channel_name"]
                    return scan.ChannelResult(
                        channel=channel,
                        messages=[{"channel": channel, "id": len(channel)}],
                        raw_count=1,
                        skipped_missing_date=0,
                        limit=kwargs["max_limit"],
                        incomplete=False,
                        ocr_count=0,
                        stderr="",
                    )
                finally:
                    active -= 1

            with patch.object(scan, "load_config", return_value=scan.ScannerConfig(1, "hash", "session")):
                with patch.object(scan, "StringSession", return_value="fake-session"):
                    with patch.object(scan, "TelegramClient", FakeClient):
                        with patch.object(scan, "resolve_entity", side_effect=fake_resolve_entity):
                            with patch.object(scan, "read_channel", side_effect=fake_read_channel):
                                exit_code = asyncio.run(scan._run_scan(args))

            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(exit_code, 0)
        self.assertEqual(max_active, 2)
        self.assertEqual([row["channel"] for row in rows], ["jobs_a", "jobs_b", "jobs_c"])

    def test_run_scan_can_keep_partial_source_failures_as_warnings(self):
        class FakeClient:
            def __init__(self, session, api_id, api_hash, *, flood_sleep_threshold):
                pass

            async def connect(self):
                return None

            async def is_user_authorized(self):
                return True

            async def disconnect(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            channel_list = Path(tmp) / "channels.txt"
            channel_list.write_text("good_jobs\nmissing_jobs\n", encoding="utf-8")
            output_dir = Path(tmp) / "output"
            output_path = output_dir / "scan.jsonl"
            parser = scan.build_parser()
            args = parser.parse_args(
                [
                    str(channel_list),
                    "--output-dir",
                    str(output_dir),
                    "--output",
                    str(output_path),
                    "--allow-partial-failures",
                    "--format",
                    "json",
                ]
            )

            async def fake_resolve_entity(client, channel_name):
                if channel_name == "missing_jobs":
                    raise scan.ScanError("cannot resolve entity")
                return f"entity:{channel_name}"

            async def fake_read_channel(**kwargs):
                channel = kwargs["channel_name"]
                return scan.ChannelResult(
                    channel=channel,
                    messages=[{"channel": channel, "id": 1}],
                    raw_count=1,
                    skipped_missing_date=0,
                    limit=kwargs["max_limit"],
                    incomplete=False,
                    ocr_count=0,
                    stderr="",
                )

            stdout = io.StringIO()
            with patch.object(scan, "load_config", return_value=scan.ScannerConfig(1, "hash", "session")):
                with patch.object(scan, "StringSession", return_value="fake-session"):
                    with patch.object(scan, "TelegramClient", FakeClient):
                        with patch.object(scan, "resolve_entity", side_effect=fake_resolve_entity):
                            with patch.object(scan, "read_channel", side_effect=fake_read_channel):
                                with patch("sys.stdout", stdout):
                                    exit_code = asyncio.run(scan._run_scan(args))

            payload = json.loads(stdout.getvalue())
            metadata = json.loads(scan.meta_path_for_output(output_path).read_text(encoding="utf-8"))

        self.assertEqual(exit_code, scan.agent_cli.EXIT_SUCCESS)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "complete_with_warnings")
        self.assertEqual(payload["data"]["failure_count"], 1)
        self.assertEqual(metadata["failure_count"], 1)
        self.assertEqual(metadata["total_messages_collected"], 1)

    def test_run_scan_fails_empty_channel_list(self):
        class FakeClient:
            def __init__(self, session, api_id, api_hash, *, flood_sleep_threshold):
                pass

            async def connect(self):
                return None

            async def is_user_authorized(self):
                return True

            async def disconnect(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            channel_list = Path(tmp) / "channels.txt"
            channel_list.write_text("", encoding="utf-8")
            parser = scan.build_parser()
            args = parser.parse_args([str(channel_list), "--output-dir", str(Path(tmp) / "output")])

            with patch.object(scan, "load_config", return_value=scan.ScannerConfig(1, "hash", "session")):
                with patch.object(scan, "StringSession", return_value="fake-session"):
                    with patch.object(scan, "TelegramClient", FakeClient):
                        exit_code = asyncio.run(scan._run_scan(args))

        self.assertEqual(exit_code, 1)

    def test_initial_limit_is_deprecated_and_ignored(self):
        parser = scan.build_parser()
        args = parser.parse_args(["channel_lists/example.txt", "--initial-limit", "10"])
        stderr = io.StringIO()

        with patch("sys.stderr", stderr):
            scan.warn_deprecated_options(["channel_lists/example.txt", "--initial-limit", "10"], args)

        self.assertIn("--initial-limit", stderr.getvalue())
        self.assertIn("ignored", stderr.getvalue())

    def test_interactive_login_handles_two_factor_password(self):
        client = MagicMock()
        client.send_code_request = AsyncMock()
        client.sign_in = AsyncMock(
            side_effect=[
                SessionPasswordNeededError(request=None),
                None,
            ]
        )
        client.session = "session"

        with tempfile.TemporaryDirectory() as tmp:
            session_path = Path(tmp) / "session"
            with patch.object(scan, "SESSION_PATH", session_path):
                with patch("builtins.input", side_effect=["+15550000000", "12345"]):
                    with patch.object(getpass, "getpass", return_value="2fa-secret"):
                        with patch.object(
                            scan.StringSession, "save", return_value="saved-session"
                        ):
                            asyncio.run(scan.interactive_login(client))
            saved_session = session_path.read_text(encoding="utf-8")

        self.assertEqual(client.sign_in.await_args_list[0].args, ("+15550000000", "12345"))
        self.assertEqual(client.sign_in.await_args_list[1].kwargs, {"password": "2fa-secret"})
        self.assertEqual(saved_session, "saved-session")

    def test_interactive_login_retries_empty_and_rejected_phone(self):
        client = MagicMock()
        client.send_code_request = AsyncMock(side_effect=[Exception("bad phone"), None])
        client.sign_in = AsyncMock()
        client.session = "session"

        with tempfile.TemporaryDirectory() as tmp:
            session_path = Path(tmp) / "session"
            stderr = io.StringIO()
            with patch.object(scan, "SESSION_PATH", session_path):
                with patch("builtins.input", side_effect=["", "+bad", "+15550000000", "12345"]):
                    with patch.object(scan.StringSession, "save", return_value="saved-session"):
                        with patch("sys.stderr", stderr):
                            asyncio.run(scan.interactive_login(client))

        self.assertEqual(client.send_code_request.await_args_list[0].args, ("+bad",))
        self.assertEqual(client.send_code_request.await_args_list[1].args, ("+15550000000",))
        self.assertEqual(client.sign_in.await_args.args, ("+15550000000", "12345"))
        self.assertIn("Phone number cannot be empty", stderr.getvalue())
        self.assertIn("Telegram rejected that phone number", stderr.getvalue())

    def test_login_only_does_not_require_source_input(self):
        class FakeClient:
            def __init__(self, session, api_id, api_hash, *, flood_sleep_threshold):
                pass

            async def connect(self):
                return None

            async def is_user_authorized(self):
                return False

            async def disconnect(self):
                return None

        parser = scan.build_parser()
        args = parser.parse_args(["--login-only"])

        with patch.object(scan, "load_config", return_value=scan.ScannerConfig(1, "hash", "")):
            with patch.object(scan, "StringSession", return_value="fake-session"):
                with patch.object(scan, "TelegramClient", FakeClient):
                    with patch.object(scan, "interactive_login", new_callable=AsyncMock) as login_mock:
                        with patch.object(sys.stdin, "isatty", return_value=True):
                            exit_code = asyncio.run(scan._run_scan(args))

        self.assertEqual(exit_code, 0)
        login_mock.assert_awaited_once()

    def test_login_only_json_mode_returns_auth_error_without_prompting(self):
        class FakeClient:
            def __init__(self, session, api_id, api_hash, *, flood_sleep_threshold):
                pass

            async def connect(self):
                return None

            async def is_user_authorized(self):
                return False

            async def disconnect(self):
                return None

        parser = scan.build_parser()
        args = parser.parse_args(["--login-only", "--format", "json"])
        stdout = io.StringIO()

        with patch.object(scan, "load_config", return_value=scan.ScannerConfig(1, "hash", "")):
            with patch.object(scan, "StringSession", return_value="fake-session"):
                with patch.object(scan, "TelegramClient", FakeClient):
                    with patch.object(scan, "interactive_login", new_callable=AsyncMock) as login_mock:
                        with patch("sys.stdout", stdout):
                            exit_code = asyncio.run(scan._run_scan(args))

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, scan.agent_cli.EXIT_AUTH)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "telegram_login_interactive_required")
        login_mock.assert_not_awaited()

    def test_main_reports_login_error_without_traceback(self):
        stderr = io.StringIO()

        async def fake_run_scan(args):
            raise scan.ScanError("Login cancelled.")

        with patch.object(scan, "_run_scan", new=fake_run_scan):
            with patch("sys.stderr", stderr):
                exit_code = scan.main(["--login-only"])

        self.assertEqual(exit_code, scan.agent_cli.EXIT_AUTH)
        self.assertIn("Login cancelled.", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_scan_metadata_sidecar_path_and_fields_are_stable(self):
        started = datetime(2026, 5, 6, 8, 0, tzinfo=timezone.utc)
        completed = datetime(2026, 5, 6, 8, 1, tzinfo=timezone.utc)
        cutoff = datetime(2026, 5, 5, 8, 0, tzinfo=timezone.utc)
        output_path = Path("output") / "scan_20260506_080000.jsonl"
        errors_path = Path("output") / "scan_20260506_080000.errors.log"

        try:
            meta_path = scan.meta_path_for_output(output_path)
            metadata = scan.build_scan_metadata(
                started_at=started,
                completed_at=completed,
                cutoff=cutoff,
                channel_list_path=Path("channel_lists/example.txt"),
                channels=["react_jobs", "frontend_jobs"],
                output_path=output_path,
                errors_path=errors_path,
                total_written=7,
                failed_channels=["frontend_jobs"],
                incomplete_channels=["react_jobs"],
                total_ocr=2,
                ocr_enabled=True,
                hours=24,
            )
        except AttributeError as exc:
            self.fail(f"scan metadata helpers should exist: {exc}")

        self.assertEqual(meta_path, Path("output") / "scan_20260506_080000.meta.json")
        self.assertEqual(metadata["scan_date"], "2026-05-06")
        self.assertEqual(metadata["scan_window"], "Last 24 hours")
        self.assertEqual(metadata["channel_count"], 2)
        self.assertEqual(metadata["channels"], ["react_jobs", "frontend_jobs"])
        self.assertEqual(metadata["total_messages_collected"], 7)
        self.assertEqual(metadata["failed_channels"], ["frontend_jobs"])
        self.assertEqual(metadata["incomplete_channels"], ["react_jobs"])
        self.assertEqual(metadata["ocr_count"], 2)
        self.assertTrue(metadata["ocr_enabled"])
        self.assertEqual(metadata["output_path"], str(output_path))
        self.assertEqual(metadata["errors_path"], str(errors_path))

    def test_write_scan_metadata_writes_json_sidecar(self):
        metadata = {"scan_date": "2026-05-06", "channel_count": 2}

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan_20260506_080000.meta.json"
            try:
                scan.write_scan_metadata(path, metadata)
            except AttributeError as exc:
                self.fail(f"write_scan_metadata should exist: {exc}")
            written = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(written, metadata)


if __name__ == "__main__":
    unittest.main()
