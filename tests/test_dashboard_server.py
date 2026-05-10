import subprocess
import tempfile
import unittest
import json
from io import BytesIO
from contextlib import AbstractContextManager
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_server, monitor_state


class DashboardServerGitTests(unittest.TestCase):
    def test_close_after_use_closes_connection_handle(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        fake = FakeConnection()

        with dashboard_server.close_after_use(fake) as conn:
            self.assertIs(conn, fake)
            self.assertIsInstance(dashboard_server.close_after_use(fake), AbstractContextManager)

        self.assertTrue(fake.closed)

    def test_run_git_wraps_timeout(self):
        with patch.object(
            dashboard_server.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["git", "fetch"], timeout=1),
        ):
            with self.assertRaises(dashboard_server.DashboardGitError) as raised:
                dashboard_server._run_git(["fetch"], timeout=1)

        self.assertIn("git fetch timed out", str(raised.exception))

    def test_run_git_wraps_missing_git_binary(self):
        with patch.object(dashboard_server.subprocess, "run", side_effect=OSError("git not found")):
            with self.assertRaises(dashboard_server.DashboardGitError) as raised:
                dashboard_server._run_git(["status"])

        self.assertIn("Unable to run git", str(raised.exception))

    def test_update_status_blocks_pull_when_worktree_is_dirty(self):
        outputs = {
            ("rev-parse", "--abbrev-ref", "HEAD"): "main\n",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/main\n",
            ("config", "--get", "remote.origin.url"): "git@github.com:Sapientropic/tg-channel-scanner.git\n",
            ("status", "--porcelain"): " M dashboard/src/main.tsx\n",
            ("fetch", "--prune", "origin"): "",
            ("rev-parse", "--short", "HEAD"): "abc123\n",
            ("rev-parse", "--short", "origin/main"): "def456\n",
            ("rev-list", "--left-right", "--count", "HEAD...origin/main"): "0\t2\n",
        }

        def fake_run(args, *, timeout=dashboard_server.GIT_TIMEOUT_SECONDS):
            return subprocess.CompletedProcess(args, 0, stdout=outputs[tuple(args)])

        with patch.object(dashboard_server, "_run_git", side_effect=fake_run):
            status = dashboard_server._git_update_status(fetch=True)

        self.assertEqual(status["status"], "behind")
        self.assertTrue(status["dirty"])
        self.assertFalse(status["pull_allowed"])
        self.assertEqual(status["dirty_count"], 1)
        self.assertEqual(status["repo_url"], "https://github.com/Sapientropic/tg-channel-scanner")
        self.assertIn("Commit or stash", status["message"])

    def test_pull_latest_uses_fast_forward_only_after_clean_check(self):
        before = {
            "dirty": False,
            "status": "behind",
            "pull_allowed": True,
            "message": "1 upstream commit available.",
        }
        after = {
            "dirty": False,
            "status": "up_to_date",
            "pull_allowed": False,
            "message": "Local branch is up to date with upstream.",
        }

        with patch.object(dashboard_server, "_git_update_status", side_effect=[before, after]):
            with patch.object(
                dashboard_server,
                "_run_git",
                return_value=subprocess.CompletedProcess(["pull"], 0, stdout="Fast-forward\n"),
            ) as run_mock:
                result = dashboard_server._git_pull_latest()

        run_mock.assert_called_once_with(["pull", "--ff-only"], timeout=60)
        self.assertEqual(result["status"], "up_to_date")
        self.assertEqual(result["pull_output"], "Fast-forward")

    def test_resolve_run_artifact_allows_encoded_output_runs_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            report = artifact_root / "run-1" / "report.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            resolved = dashboard_server.resolve_run_artifact_path(
                "output%2Fruns%2Frun-1%2Freport.html",
                artifact_root=artifact_root,
            )

        self.assertEqual(resolved, report.resolve())

    def test_resolve_run_artifact_allows_named_report_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            report = artifact_root / "run-1" / "jobs-fast-signal-report-2026-05-09-1225.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            resolved = dashboard_server.resolve_run_artifact_path(
                "output/runs/run-1/jobs-fast-signal-report-2026-05-09-1225.html",
                artifact_root=artifact_root,
            )

        self.assertEqual(resolved, report.resolve())

    def test_resolve_run_artifact_allows_custom_output_dir_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "out" / "runs"
            report = artifact_root / "run-1" / "report.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            resolved = dashboard_server.resolve_run_artifact_path(
                "out/runs/run-1/report.html",
                artifact_root=artifact_root,
            )

        self.assertEqual(resolved, report.resolve())

    def test_resolve_run_artifact_defaults_to_output_dir_from_requested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "out" / "runs" / "run-1" / "report.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                resolved = dashboard_server.resolve_run_artifact_path("out/runs/run-1/report.html")

        self.assertEqual(resolved, report.resolve())

    def test_resolve_run_artifact_rejects_raw_scan_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            scan = artifact_root / "run-1" / "scan.jsonl"
            scan.parent.mkdir(parents=True)
            scan.write_text('{"text":"raw"}\n', encoding="utf-8")

            with self.assertRaises(dashboard_server.DashboardArtifactError):
                dashboard_server.resolve_run_artifact_path(
                    "output/runs/run-1/scan.jsonl",
                    artifact_root=artifact_root,
                )

    def test_resolve_run_artifact_rejects_non_report_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            other = artifact_root / "run-1" / "other.html"
            other.parent.mkdir(parents=True)
            other.write_text("<html>other</html>", encoding="utf-8")

            with self.assertRaises(dashboard_server.DashboardArtifactError):
                dashboard_server.resolve_run_artifact_path(
                    "output/runs/run-1/other.html",
                    artifact_root=artifact_root,
                )

    def test_resolve_run_artifact_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            artifact_root.mkdir(parents=True)
            (root / "output" / "secret.html").write_text("secret", encoding="utf-8")

            with self.assertRaises(dashboard_server.DashboardArtifactError):
                dashboard_server.resolve_run_artifact_path(
                    "output/runs/../secret.html",
                    artifact_root=artifact_root,
                )

    def test_resolve_static_path_rejects_sibling_prefix_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            static_dir = root / "dist"
            sibling = root / "dist_evil"
            static_dir.mkdir()
            sibling.mkdir()
            index = static_dir / "index.html"
            secret = sibling / "secret.txt"
            index.write_text("index", encoding="utf-8")
            secret.write_text("secret", encoding="utf-8")

            resolved = dashboard_server.resolve_static_path("/../dist_evil/secret.txt", static_dir=static_dir)

        self.assertEqual(resolved, index.resolve())

    def test_dashboard_host_warning_only_warns_for_non_loopback_hosts(self):
        self.assertIsNone(dashboard_server.dashboard_host_warning("127.0.0.1"))
        self.assertIsNone(dashboard_server.dashboard_host_warning("localhost"))
        self.assertIsNone(dashboard_server.dashboard_host_warning("::1"))

        warning = dashboard_server.dashboard_host_warning("0.0.0.0")

        self.assertIsNotNone(warning)
        self.assertIn("report artifacts", (warning or "").lower())

    def test_markdown_report_artifact_renders_as_mobile_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.md"
            report.write_text(
                "# Market News Signal Brief\n\n"
                "A readable report with **strong signal**.\n\n"
                "| Source | Count |\n| --- | --- |\n| Telegram | 2 |\n\n"
                "- Open [source](https://example.com)\n",
                encoding="utf-8",
            )

            body = dashboard_server.render_markdown_artifact(report).decode("utf-8")

        self.assertIn("<meta name=\"viewport\"", body)
        self.assertIn("<h1>Market News Signal Brief</h1>", body)
        self.assertIn("<strong>strong signal</strong>", body)
        self.assertIn("<table>", body)
        self.assertIn('href="https://example.com"', body)

    def test_serve_markdown_artifact_over_http_as_rendered_html(self):
        class FakeHandler:
            status = None
            headers = {}
            wfile = BytesIO()

            def send_response(self, status):
                self.status = status

            def send_header(self, key, value):
                self.headers[key] = value

            def end_headers(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "output" / "runs" / "run-1" / "report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Report\n\nBody", encoding="utf-8")

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                handler = FakeHandler()
                dashboard_server.DashboardHandler._serve_artifact(handler, "output/runs/run-1/report.md")

        self.assertEqual(handler.status, HTTPStatus.OK.value)
        self.assertEqual(handler.headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"<h1>Report</h1>", handler.wfile.getvalue())

    def test_serve_html_report_artifact_injects_mobile_patch(self):
        class FakeHandler:
            status = None
            headers = {}
            wfile = BytesIO()

            def send_response(self, status):
                self.status = status

            def send_header(self, key, value):
                self.headers[key] = value

            def end_headers(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "output" / "runs" / "run-1" / "report.html"
            report.parent.mkdir(parents=True)
            report.write_text(
                "<html><head><title>Report</title></head><body><h1 class=\"report-title\">Long Report</h1></body></html>",
                encoding="utf-8",
            )

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                handler = FakeHandler()
                dashboard_server.DashboardHandler._serve_artifact(handler, "output/runs/run-1/report.html")

        self.assertEqual(handler.status, HTTPStatus.OK.value)
        self.assertEqual(handler.headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"data-dashboard-report-mobile-patch", handler.wfile.getvalue())

    def test_write_feedback_export_writes_note_free_dashboard_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / ".tgcs" / "tgcs.db"
            output_path = root / "output" / "dashboard-feedback.jsonl"
            conn = monitor_state.connect(db_path)
            try:
                cards = monitor_state.upsert_review_cards(
                    conn,
                    profile_id="jobs-fast",
                    run_id="run-1",
                    items=[
                        {
                            "topic": "Contract role",
                            "rating": "high",
                            "source_message_refs": [{"channel": "jobs", "id": 1}],
                        }
                    ],
                )
                monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="private")

                result = dashboard_server.write_feedback_export(conn, output_path=output_path)
            finally:
                conn.close()

            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result["feedback_count"], 1)
        self.assertEqual(rows[0]["feedback"], "keep")
        self.assertEqual(rows[0]["note"], "")

    def test_write_feedback_export_defaults_to_grouped_feedback_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / ".tgcs" / "tgcs.db"
            conn = monitor_state.connect(db_path)
            try:
                with patch.object(dashboard_server, "PROJECT_ROOT", root):
                    result = dashboard_server.write_feedback_export(conn)
            finally:
                conn.close()

            output_path = root / "output" / "feedback" / "review-feedback.jsonl"
            output_exists = output_path.exists()

        self.assertEqual(result["output_path"], "output/feedback/review-feedback.jsonl")
        self.assertTrue(output_exists)

    def test_serve_artifact_rejects_raw_scan_over_http_handler(self):
        class FakeHandler:
            status = None
            payload = None

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan = root / "output" / "runs" / "run-1" / "scan.jsonl"
            scan.parent.mkdir(parents=True)
            scan.write_text('{"text":"raw"}\n', encoding="utf-8")

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                handler = FakeHandler()
                dashboard_server.DashboardHandler._serve_artifact(handler, "output/runs/run-1/scan.jsonl")

        self.assertEqual(handler.status, HTTPStatus.NOT_FOUND)
        self.assertEqual(handler.payload["error"], "artifact_type_not_report")

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


if __name__ == "__main__":
    unittest.main()
