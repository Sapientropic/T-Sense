import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.tgcs_cli import load_tgcs_module


class TgcsRunDemoInitTests(unittest.TestCase):
    def test_run_defaults_to_market_news_html_registry_and_state(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "sources.json").write_text("{}", encoding="utf-8")
            (root / "profiles" / "templates").mkdir(parents=True)
            (root / "profiles" / "templates" / "market-news.md").write_text("# Market news\n", encoding="utf-8")
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
        self.assertIn(str(tgcs.PACKAGE_ROOT / "templates" / "demo" / "fixtures" / "demo-report.md"), cmd)
        self.assertIn(str(root / "output" / "demo-report.html"), cmd)
        output = stdout.getvalue()
        self.assertIn("Demo report ready", output)
        self.assertIn("output", output)
        self.assertIn("tgcs init", output)

    def test_packaged_runtime_uses_packaged_scripts_even_from_source_checkout_cwd(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_root = root / "site-packages"
            package_script = package_root / "scripts" / "report.py"
            package_script.parent.mkdir(parents=True)
            package_script.write_text("# packaged report\n", encoding="utf-8")
            source_root = root / "source-checkout"
            local_script = source_root / "scripts" / "report.py"
            local_script.parent.mkdir(parents=True)
            local_script.write_text("# local report\n", encoding="utf-8")

            with patch.object(tgcs, "PACKAGE_ROOT", package_root):
                with patch.object(tgcs, "PROJECT_ROOT", source_root):
                    self.assertEqual(tgcs._script("report.py"), package_script)

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
        self.assertIn("scan_concurrency = 3", profiles_config_text)
        self.assertIn("scan_delay_seconds = 0.2", profiles_config_text)
        self.assertIn("semantic_max_messages = 40", profiles_config_text)
        self.assertIn("semantic_max_tokens = 6000", profiles_config_text)
        self.assertIn("semantic_batch_size = 20", profiles_config_text)
        self.assertIn("semantic_concurrency = 2", profiles_config_text)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("source_registry.py", cmd[1])
        self.assertIn("import-list", cmd)
        output = stdout.getvalue()
        self.assertIn("Local project defaults ready", output)
        self.assertIn("market-news", output)
        self.assertIn("jobs-fast", output)
        self.assertIn("tgcs doctor", output)
        self.assertIn("Settings > Sources", output)
        self.assertIn("Source assistant", output)
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
        self.assertIn("App: Open Signal Desk Start", output)

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
        self.assertIn("Signal Desk Start", payload["next_app_step"])

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
        self.assertEqual(payload["next_app_step"], "Open Signal Desk Start and run the first dry-run scan.")

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

    def test_doctor_uses_packaged_default_channel_list_in_installed_workspace(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["doctor", "--format", "json"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("--channel-list", cmd)
        self.assertIn(str(tgcs.PACKAGE_ROOT / "channel_lists" / "example.txt"), cmd)
        self.assertIn(str(root / "output"), cmd)



if __name__ == "__main__":
    unittest.main()
