import json
import subprocess
import tempfile
import unittest
import io
from pathlib import Path
from unittest.mock import patch


def load_tgcs_module(testcase):
    try:
        from scripts import tgcs
    except ModuleNotFoundError as exc:
        testcase.fail(f"scripts.tgcs should exist: {exc}")
    return tgcs


class TgcsCliTests(unittest.TestCase):
    def test_run_defaults_to_market_news_html_registry_and_state(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "sources.json").write_text("{}", encoding="utf-8")
            calls = []

            def fake_run(cmd, check=False):
                calls.append(cmd)
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run):
                    exit_code = tgcs.main(["run"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        cmd = [str(part) for part in calls[0]]
        self.assertIn("daily_report.py", cmd[1])
        self.assertIn("--source-registry", cmd)
        self.assertIn(str(root / ".tgcs" / "sources.json"), cmd)
        self.assertIn("--profile", cmd)
        self.assertIn(str(root / "profiles" / "templates" / "market-news.md"), cmd)
        self.assertIn("--html", cmd)
        self.assertIn("--state-dir", cmd)
        self.assertIn(str(root / ".tgcs" / "state"), cmd)

    def test_run_no_state_omits_state_dir(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "sources.json").write_text("{}", encoding="utf-8")

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["run", "--no-state"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertNotIn("--state-dir", cmd)

    def test_demo_uses_offline_fixture_defaults(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = io.StringIO()

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    with patch("sys.stdout", stdout):
                        exit_code = tgcs.main(["demo"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("report.py", cmd[1])
        self.assertIn("--html-only", cmd)
        self.assertIn(str(root / "docs" / "demo" / "fixtures" / "demo-report.md"), cmd)
        self.assertIn(str(root / "output" / "demo-report.html"), cmd)
        output = stdout.getvalue()
        self.assertIn("Demo report ready", output)
        self.assertIn("output", output)
        self.assertIn("tgcs init", output)

    def test_init_creates_local_config_and_source_registry(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "channel_lists").mkdir()
            (root / "channel_lists" / "example.txt").write_text("example\n", encoding="utf-8")
            stdout = io.StringIO()

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    with patch("sys.stdout", stdout):
                        exit_code = tgcs.main(["init"])

            config_text = (root / ".tgcs" / "config.toml").read_text(encoding="utf-8")
            profiles_config_text = (root / ".tgcs" / "profiles.toml").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("profile", config_text)
        self.assertIn("state_dir", config_text)
        self.assertIn("profile_run_config_v1", profiles_config_text)
        self.assertIn("semantic_max_messages = 20", profiles_config_text)
        self.assertIn("semantic_max_tokens = 2000", profiles_config_text)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("source_registry.py", cmd[1])
        self.assertIn("import-list", cmd)
        output = stdout.getvalue()
        self.assertIn("Local project defaults ready", output)
        self.assertIn("market-news", output)
        self.assertIn("jobs-fast", output)
        self.assertIn("tgcs doctor", output)
        self.assertIn("tgcs sources import channel_lists/jobs.txt --topic jobs", output)
        self.assertIn("tgcs schedule print --profile-id jobs-fast", output)
        self.assertIn("tgcs dashboard", output)

    def test_init_jobs_starter_imports_real_jobs_list_with_topic(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "channel_lists").mkdir()
            (root / "channel_lists" / "jobs.txt").write_text("jobs_in_it_remoute\n", encoding="utf-8")

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["init", "--starter", "jobs"])

            config_text = (root / ".tgcs" / "config.toml").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn('profile = "jobs"', config_text)
        self.assertIn('channel_list = "channel_lists/jobs.txt"', config_text)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn(str(root / "channel_lists" / "jobs.txt"), cmd)
        self.assertIn("--topic", cmd)
        self.assertIn("jobs", cmd)

    def test_init_jobs_starter_imports_jobs_list_when_registry_already_exists(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "channel_lists").mkdir()
            (root / "channel_lists" / "jobs.txt").write_text("jobs_in_it_remoute\n", encoding="utf-8")
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "sources.json").write_text(
                json.dumps({"schema_version": "source_registry_v1", "sources": []}),
                encoding="utf-8",
            )

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["init", "--starter", "jobs"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("source_registry.py", cmd[1])
        self.assertIn("import-list", cmd)
        self.assertIn(str(root / "channel_lists" / "jobs.txt"), cmd)
        self.assertIn("--source-registry", cmd)
        self.assertIn(str(root / ".tgcs" / "sources.json"), cmd)
        self.assertIn("--topic", cmd)
        self.assertIn("jobs", cmd)

    def test_quickstart_jobs_points_clean_workspace_to_jobs_init(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = io.StringIO()

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch("sys.stdout", stdout):
                    exit_code = tgcs.main(["quickstart", "jobs"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Developer Opportunity quickstart", output)
        self.assertIn("Stage: init_required", output)
        self.assertIn("Next: tgcs init --starter jobs", output)

    def test_quickstart_jobs_json_points_to_login_when_credentials_exist_without_session(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_path = root / "session"
            stdout = io.StringIO()
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "config.toml").write_text('profile = "jobs"\n', encoding="utf-8")
            (root / ".tgcs" / "profiles.toml").write_text('schema_version = "profile_run_config_v1"\n', encoding="utf-8")
            (root / ".tgcs" / "sources.json").write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [{"username": "jobs", "topics": ["jobs"], "enabled": True}],
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs, "DEFAULT_SESSION_PATH", session_path):
                    with patch.dict("os.environ", {"TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "hash"}, clear=True):
                        with patch("sys.stdout", stdout):
                            exit_code = tgcs.main(["quickstart", "jobs", "--format", "json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["stage"], "login_required")
        self.assertEqual(payload["next_command"], "tgcs login")

    def test_quickstart_jobs_points_to_first_dry_run_after_login(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_path = root / "session"
            stdout = io.StringIO()
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "config.toml").write_text('profile = "jobs"\n', encoding="utf-8")
            (root / ".tgcs" / "profiles.toml").write_text('schema_version = "profile_run_config_v1"\n', encoding="utf-8")
            (root / ".tgcs" / "sources.json").write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [{"username": "jobs", "topics": ["jobs"], "enabled": True}],
                    }
                ),
                encoding="utf-8",
            )
            session_path.write_text("session", encoding="utf-8")

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs, "DEFAULT_SESSION_PATH", session_path):
                    with patch.dict("os.environ", {"TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "hash"}, clear=True):
                        with patch("sys.stdout", stdout):
                            exit_code = tgcs.main(["quickstart", "jobs", "--format", "json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["stage"], "dry_run_required")
        self.assertEqual(
            payload["next_command"],
            "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
        )

    def test_login_calls_scan_login_only(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["login"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("scan.py", cmd[1])
        self.assertIn("--login-only", cmd)

    def test_doctor_uses_channel_list_flag_when_registry_is_missing(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "channel_lists").mkdir()
            (root / "channel_lists" / "example.txt").write_text("remote_jobs\n", encoding="utf-8")

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["doctor", "--format", "json"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("doctor.py", cmd[1])
        self.assertIn("--channel-list", cmd)
        self.assertIn(str(root / "channel_lists" / "example.txt"), cmd)

    def test_monitor_run_delegates_to_monitor_script(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(
                        [
                            "monitor",
                            "run",
                            "--profile-id",
                            "market-news",
                            "--delivery-mode",
                            "dry-run",
                            "--format",
                            "json",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("monitor.py", cmd[1])
        self.assertIn("run", cmd)
        self.assertIn("--profile-id", cmd)
        self.assertIn("market-news", cmd)
        self.assertIn("--format", cmd)

    def test_dashboard_delegates_to_dashboard_server(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dashboard" / "dist").mkdir(parents=True)
            (root / "dashboard" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["dashboard", "--port", "8765"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("dashboard_server.py", cmd[1])
        self.assertIn("--host", cmd)
        self.assertIn("127.0.0.1", cmd)

    def test_dashboard_auto_builds_missing_static_assets_before_serving(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dashboard").mkdir()
            calls = []

            def fake_run(cmd, check=False, cwd=None):
                calls.append((cmd, cwd))
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run):
                    exit_code = tgcs.main(["dashboard"])

        self.assertEqual(exit_code, 0)
        self.assertEqual([call[0][0] for call in calls], ["npm", "npm", str(tgcs._python())])
        self.assertEqual(calls[0][0][1:], ["ci"])
        self.assertEqual(calls[1][0][1:], ["run", "build"])
        self.assertEqual(calls[0][1], root / "dashboard")
        self.assertEqual(calls[1][1], root / "dashboard")

    def test_dashboard_no_build_skips_missing_static_asset_build(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def fake_run(cmd, check=False, cwd=None):
                calls.append((cmd, cwd))
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run):
                    exit_code = tgcs.main(["dashboard", "--no-build"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("dashboard_server.py", [str(part) for part in calls[0][0]][1])

    def test_delivery_test_delegates_to_monitor_delivery_test(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["delivery", "test", "telegram-bot", "--chat-id", "123"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("monitor.py", cmd[1])
        self.assertIn("delivery-test", cmd)
        self.assertIn("telegram-bot", cmd)

    def test_feedback_export_delegates_to_monitor_with_local_defaults(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["feedback", "export", "--format", "json"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("monitor.py", cmd[1])
        self.assertIn("feedback-export", cmd)
        self.assertIn("--db", cmd)
        self.assertIn(str(root / ".tgcs" / "tgcs.db"), cmd)
        self.assertIn("--output", cmd)
        self.assertIn(str(root / "output" / "dashboard-feedback.jsonl"), cmd)
        self.assertIn("--format", cmd)
        self.assertIn("json", cmd)

    def test_sources_import_forwards_topic_tags(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_list = root / "jobs.txt"
            source_list.write_text("remote_jobs\n", encoding="utf-8")

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(
                        [
                            "sources",
                            "import",
                            str(source_list),
                            "--topic",
                            "jobs",
                            "--topic",
                            "remote-work",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("source_registry.py", cmd[1])
        self.assertIn("--topic", cmd)
        self.assertIn("jobs", cmd)
        self.assertIn("remote-work", cmd)

    def test_sources_list_forwards_topic_filter(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["sources", "list", "--topic", "jobs", "--format", "json"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("list", cmd)
        self.assertIn("--topic", cmd)
        self.assertIn("jobs", cmd)

    def test_schedule_print_windows_outputs_task_scheduler_command_without_running_it(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = io.StringIO()
            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run") as run_mock:
                    with patch("sys.stdout", stdout):
                        exit_code = tgcs.main(
                            [
                                "schedule",
                                "print",
                                "--platform",
                                "windows",
                                "--profile-id",
                                "jobs-fast",
                                "--interval-minutes",
                                "15",
                                "--delivery-mode",
                                "live",
                            ]
                        )

        self.assertEqual(exit_code, 0)
        run_mock.assert_not_called()
        output = stdout.getvalue()
        self.assertIn("schtasks", output)
        self.assertIn("tgcs.bat", output)
        self.assertIn("jobs-fast", output)
        self.assertIn("--delivery-mode live", output)

    def test_schedule_print_windows_quotes_tgcs_path_inside_task_action(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "with space"
            stdout = io.StringIO()
            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch("sys.stdout", stdout):
                    exit_code = tgcs.main(["schedule", "print", "--platform", "windows"])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn(f'\\"{root / "tgcs.bat"}\\" monitor run', output)

    def test_schedule_print_cron_outputs_crontab_line_without_running_it(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = io.StringIO()
            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run") as run_mock:
                    with patch("sys.stdout", stdout):
                        exit_code = tgcs.main(
                            [
                                "schedule",
                                "print",
                                "--platform",
                                "cron",
                                "--profile-id",
                                "jobs-fast",
                                "--interval-minutes",
                                "15",
                            ]
                        )

        self.assertEqual(exit_code, 0)
        run_mock.assert_not_called()
        output = stdout.getvalue()
        self.assertIn("*/15 * * * *", output)
        self.assertIn("./tgcs monitor run --profile-id jobs-fast", output)

    def test_schedule_print_cron_outputs_two_hour_interval(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = io.StringIO()
            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch("sys.stdout", stdout):
                    exit_code = tgcs.main(
                        [
                            "schedule",
                            "print",
                            "--platform",
                            "cron",
                            "--profile-id",
                            "market-news",
                            "--interval-minutes",
                            "120",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        self.assertIn("0 */2 * * *", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
