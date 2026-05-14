import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.tgcs_cli import load_tgcs_module


class TgcsDelegateTests(unittest.TestCase):
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
        self.assertNotIn("--auto-port", cmd)

    def test_dashboard_open_flag_delegates_to_dashboard_server(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dashboard" / "dist").mkdir(parents=True)
            (root / "dashboard" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

            def fake_run(cmd, check=False):
                return subprocess.CompletedProcess(cmd, 0)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run) as run_mock:
                    exit_code = tgcs.main(["dashboard", "--open"])

        self.assertEqual(exit_code, 0)
        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("--open", cmd)
        self.assertIn("--auto-port", cmd)
        self.assertIn("8765", cmd)

    def test_dashboard_auto_builds_missing_static_assets_before_serving(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dashboard").mkdir()
            calls = []

            def fake_run(cmd, check=False, cwd=None, **kwargs):
                calls.append((cmd, cwd))
                stdout = "v22.12.0\n" if cmd[:2] == ["node", "--version"] else ""
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout)

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.subprocess, "run", side_effect=fake_run):
                    exit_code = tgcs.main(["dashboard"])

        self.assertEqual(exit_code, 0)
        self.assertEqual([call[0][0] for call in calls], ["node", "npm", "npm", str(tgcs._python())])
        self.assertEqual(calls[1][0][1:], ["ci"])
        self.assertEqual(calls[2][0][1:], ["run", "build"])
        self.assertEqual(calls[1][1], root / "dashboard")
        self.assertEqual(calls[2][1], root / "dashboard")

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

    def test_dashboard_missing_node_error_points_to_app_launchers(self):
        tgcs = load_tgcs_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stderr = io.StringIO()

            with patch.object(tgcs, "PROJECT_ROOT", root):
                with patch.object(tgcs.shutil, "which", return_value=None):
                    with patch("sys.stderr", stderr):
                        exit_code = tgcs.main(["dashboard"])

        self.assertEqual(exit_code, 3)
        error = stderr.getvalue()
        self.assertIn("Node.js 20.19+", error)
        self.assertIn("Signal Desk.bat", error)
        self.assertIn("./signal-desk", error)

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
        self.assertIn(str(root / "output" / "feedback" / "review-feedback.jsonl"), cmd)
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



if __name__ == "__main__":
    unittest.main()
