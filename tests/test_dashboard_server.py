import subprocess
import tempfile
import unittest
import json
import plistlib
from types import SimpleNamespace
from io import BytesIO
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
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
            ("config", "--get", "remote.origin.url"): "git@github.com:Sapientropic/T-Sense.git\n",
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
        self.assertEqual(status["repo_url"], "https://github.com/Sapientropic/T-Sense")
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

    def test_loopback_address_detection_handles_common_local_forms(self):
        self.assertTrue(dashboard_server.is_loopback_address("127.0.0.1"))
        self.assertTrue(dashboard_server.is_loopback_address("::1"))
        self.assertTrue(dashboard_server.is_loopback_address("localhost"))
        self.assertTrue(dashboard_server.is_loopback_address("::ffff:127.0.0.1"))
        self.assertFalse(dashboard_server.is_loopback_address("192.168.1.10"))

    def test_select_dashboard_server_reuses_existing_compatible_instance(self):
        with patch.object(
            dashboard_server,
            "fetch_compatible_desk_health",
            return_value={
                "schema_version": "desk_health_v1",
                "app": "tgcs-signal-desk",
                "url": "http://127.0.0.1:8765",
            },
        ):
            with patch.object(dashboard_server, "ThreadingHTTPServer") as server_mock:
                selection = dashboard_server.select_dashboard_server(
                    host="127.0.0.1",
                    port=8765,
                    auto_port=True,
                    handler_cls=dashboard_server.BaseHTTPRequestHandler,
                )

        server_mock.assert_not_called()
        self.assertTrue(selection.reused_existing)
        self.assertEqual(selection.url, "http://127.0.0.1:8765")

    def test_select_dashboard_server_auto_port_skips_incompatible_occupied_port(self):
        calls = []

        def fake_server(address, handler_cls):
            calls.append(address[1])
            if address[1] == 8765:
                raise OSError("port in use")
            return object()

        with patch.object(dashboard_server, "fetch_compatible_desk_health", return_value=None):
            with patch.object(dashboard_server, "ThreadingHTTPServer", side_effect=fake_server):
                selection = dashboard_server.select_dashboard_server(
                    host="127.0.0.1",
                    port=8765,
                    auto_port=True,
                    handler_cls=dashboard_server.BaseHTTPRequestHandler,
                )

        self.assertEqual(calls, [8765, 8766])
        self.assertFalse(selection.reused_existing)
        self.assertEqual(selection.port, 8766)

    def test_select_dashboard_server_explicit_port_stays_strict(self):
        with patch.object(dashboard_server, "fetch_compatible_desk_health") as health_mock:
            with patch.object(dashboard_server, "ThreadingHTTPServer", side_effect=OSError("port in use")):
                with self.assertRaises(OSError):
                    dashboard_server.select_dashboard_server(
                        host="127.0.0.1",
                        port=8765,
                        auto_port=False,
                        handler_cls=dashboard_server.BaseHTTPRequestHandler,
                    )

        health_mock.assert_not_called()

    def test_sensitive_desk_setup_endpoint_requires_loopback_client(self):
        class FakeHandler:
            path = "/api/desk/telegram-status"
            client_address = ("192.168.1.10", 51000)
            status = None
            payload = None

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_GET(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("localhost", handler.payload["error"])

    def test_desk_actions_exposes_allowlisted_actions_and_human_boundaries(self):
        payload = dashboard_server.desk_actions()

        self.assertEqual(payload["schema_version"], "desk_actions_v1")
        actions = {item["action_id"]: item for item in payload["actions"]}
        for action_id in [
            "init_jobs",
            "demo_render",
            "doctor_jobs",
            "sources_validate",
            "sources_probe_access",
            "sources_import_jobs",
            "monitor_jobs_dry_run",
            "feedback_export",
            "schedule_preview",
        ]:
            self.assertEqual(actions[action_id]["run_mode"], "execute")
            self.assertNotIn("python", actions[action_id]["display_command"].lower())

        self.assertEqual(actions["schedule_install_dry_run"]["run_mode"], "confirm_execute")
        self.assertEqual(actions["schedule_remove_dry_run"]["run_mode"], "confirm_execute")
        self.assertEqual(actions["sources_pause_inaccessible"]["run_mode"], "confirm_execute")
        self.assertEqual(actions["sources_keep_accessible"]["run_mode"], "confirm_execute")
        self.assertNotIn("tgcs", actions["schedule_install_dry_run"]["display_command"].lower())
        self.assertNotIn("tgcs", actions["schedule_remove_dry_run"]["display_command"].lower())
        self.assertNotIn("python", actions["sources_probe_access"]["display_command"].lower())
        self.assertEqual(actions["login_human"]["run_mode"], "needs_human")
        self.assertEqual(actions["live_delivery_human"]["run_mode"], "needs_human")
        self.assertEqual(actions["schedule_install_human"]["run_mode"], "needs_human")

    def test_run_desk_action_rejects_unknown_action_id(self):
        with self.assertRaises(dashboard_server.DashboardDeskActionError) as raised:
            dashboard_server.run_desk_action("not-a-real-action")

        self.assertIn("Unknown Desk action", str(raised.exception))

    def test_run_desk_action_ignores_arbitrary_command_payload_and_uses_fixed_entry(self):
        completed = subprocess.CompletedProcess(
            ["python"],
            0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "data": {
                        "status": "complete",
                        "html_path": "output/runs/run-1/report.html",
                        "next_step": "Open dashboard.",
                    },
                    "error": None,
                }
            ),
            stderr="",
        )

        with patch.object(dashboard_server.subprocess, "run", return_value=completed) as run_mock:
            result = dashboard_server.run_desk_action(
                "monitor_jobs_dry_run",
                body={"command": "powershell -NoProfile Remove-Item -Recurse ."},
            )

        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertEqual(Path(cmd[1]).name, "tgcs.py")
        self.assertIn("monitor", cmd)
        self.assertIn("run", cmd)
        self.assertNotIn("Remove-Item", " ".join(cmd))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["artifact_path"], "output/runs/run-1/report.html")
        self.assertEqual(result["next_action"], "Open dashboard.")

    def test_run_desk_action_returns_needs_human_without_subprocess_for_human_takeover(self):
        with patch.object(dashboard_server.subprocess, "run") as run_mock:
            results = {
                action_id: dashboard_server.run_desk_action(action_id)
                for action_id in ["login_human", "live_delivery_human", "schedule_install_human"]
            }

        run_mock.assert_not_called()
        self.assertEqual(results["login_human"]["status"], "needs_human")
        self.assertIn("tgcs login", results["login_human"]["display_command"])
        self.assertEqual(results["live_delivery_human"]["status"], "needs_human")
        self.assertIn("delivery test", results["live_delivery_human"]["display_command"])
        self.assertEqual(results["schedule_install_human"]["status"], "needs_human")
        self.assertIn("schedule print", results["schedule_install_human"]["display_command"])

    def test_schedule_preview_action_only_prints_scheduler_command(self):
        completed = subprocess.CompletedProcess(
            ["python"],
            0,
            stdout="schtasks /Create /SC MINUTE /MO 15 /TN TGCS-jobs-fast /TR \"tgcs.bat monitor run\"\n",
            stderr="",
        )

        with patch.object(dashboard_server.subprocess, "run", return_value=completed) as run_mock:
            result = dashboard_server.run_desk_action("schedule_preview")

        cmd = [str(part) for part in run_mock.call_args.args[0]]
        self.assertIn("schedule", cmd)
        self.assertIn("print", cmd)
        self.assertNotIn("/Create", cmd)
        self.assertIn("dry-run", cmd)
        self.assertNotIn("live", cmd)
        self.assertEqual(result["status"], "success")
        self.assertIn("practice scans would run every 15 minutes", result["detail"])
        self.assertNotIn("schtasks", result["detail"].lower())
        self.assertIn("Signal Desk", result["next_action"])

    def test_source_access_probe_action_returns_cached_counts_without_shell_commands(self):
        health = {
            "schema_version": dashboard_server.DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION,
            "checked_at": "2026-05-12T00:00:00Z",
            "source_count": 4,
            "checked_count": 4,
            "truncated_count": 0,
            "accessible_count": 2,
            "quiet_count": 1,
            "inaccessible_count": 1,
            "reason_counts": {"cannot_resolve_entity": 1, "empty_recent_window": 1},
            "sources": [],
        }

        with patch.object(dashboard_server, "probe_source_access", return_value=health):
            with patch.object(dashboard_server.subprocess, "run") as run_mock:
                result = dashboard_server.run_desk_action("sources_probe_access", body={"command": "ignored"})

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "success")
        self.assertIn("2 accessible", result["detail"])
        self.assertIn("cannot resolve 1", result["detail"])

    def test_desk_action_blocks_duplicate_long_running_scan(self):
        lock = dashboard_server._desk_action_lock("monitor_jobs_dry_run")
        self.assertTrue(lock.acquire(blocking=False))
        try:
            with patch.object(dashboard_server.subprocess, "run") as run_mock:
                result = dashboard_server.run_desk_action("monitor_jobs_dry_run")
        finally:
            lock.release()

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("already running", result["title"].lower())

    def test_source_access_repair_disables_cached_inaccessible_sources_only_after_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / ".tgcs" / "sources.json"
            sources = [
                dashboard_server.source_registry.source_from_channel("remote_jobs"),
                dashboard_server.source_registry.source_from_channel("quiet_jobs"),
                dashboard_server.source_registry.source_from_channel("good_jobs"),
            ]
            dashboard_server.source_registry.save_registry(
                registry_path,
                {"schema_version": dashboard_server.source_registry.SCHEMA_VERSION, "sources": sources},
            )
            health = {
                "schema_version": dashboard_server.DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION,
                "checked_at": datetime.now(UTC).isoformat(),
                "source_count": 3,
                "checked_count": 3,
                "truncated_count": 0,
                "accessible_count": 1,
                "quiet_count": 1,
                "inaccessible_count": 1,
                "reason_counts": {"cannot_resolve_entity": 1, "empty_recent_window": 1},
                "sources": [
                    {
                        "source_id": "telegram:remote_jobs",
                        "label": "remote_jobs",
                        "channel": "remote_jobs",
                        "status": "inaccessible",
                        "reason": "cannot_resolve_entity",
                    },
                    {
                        "source_id": "telegram:quiet_jobs",
                        "label": "quiet_jobs",
                        "channel": "quiet_jobs",
                        "status": "quiet",
                        "reason": "empty_recent_window",
                    },
                    {
                        "source_id": "telegram:good_jobs",
                        "label": "good_jobs",
                        "channel": "good_jobs",
                        "status": "accessible",
                        "reason": "recent_message_found",
                    },
                ],
            }

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server._write_source_access_health(health)
                with self.assertRaises(dashboard_server.DashboardDeskActionError):
                    dashboard_server.run_desk_action("sources_pause_inaccessible", body={"command": "ignored"})
                paused = dashboard_server.run_desk_action("sources_pause_inaccessible", body={"confirm": True})
                after_pause = dashboard_server.source_registry.load_registry(registry_path)
                kept = dashboard_server.run_desk_action("sources_keep_accessible", body={"confirm": True})
                after_keep = dashboard_server.source_registry.load_registry(registry_path)

        pause_enabled = {source["source_id"]: source["enabled"] for source in after_pause["sources"]}
        keep_enabled = {source["source_id"]: source["enabled"] for source in after_keep["sources"]}
        self.assertEqual(paused["status"], "success")
        self.assertFalse(pause_enabled["telegram:remote_jobs"])
        self.assertTrue(pause_enabled["telegram:quiet_jobs"])
        self.assertTrue(pause_enabled["telegram:good_jobs"])
        self.assertEqual(kept["status"], "success")
        self.assertFalse(keep_enabled["telegram:quiet_jobs"])
        self.assertTrue(keep_enabled["telegram:good_jobs"])

    def test_schedule_install_dry_run_requires_confirmation(self):
        with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
            with self.assertRaises(dashboard_server.DashboardDeskActionError) as raised:
                dashboard_server.run_desk_action("schedule_install_dry_run", body={})

        run_mock.assert_not_called()
        self.assertIn("confirmation", str(raised.exception))

    def test_schedule_install_dry_run_rejects_extra_payload_keys(self):
        with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
            with self.assertRaises(dashboard_server.DashboardDeskActionError) as raised:
                dashboard_server.run_desk_action(
                    "schedule_install_dry_run",
                    body={"confirm": True, "command": "powershell Remove-Item ."},
                )

        run_mock.assert_not_called()
        self.assertIn("confirmation flag", str(raised.exception))

    def test_schedule_install_dry_run_blocks_non_windows(self):
        with patch.object(dashboard_server.sys, "platform", "linux"):
            with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": ""}, clear=False):
                with patch.object(
                    dashboard_server,
                    "shutil",
                    SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                    create=True,
                ):
                    with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                        result = dashboard_server.run_desk_action("schedule_install_dry_run", body={"confirm": True})

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("crontab", result["detail"])
        self.assertIn("schedule print --platform cron", result["next_action"])

    def test_schedule_install_dry_run_blocks_when_launcher_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", Path(tmp)):
                    with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                        result = dashboard_server.run_desk_action("schedule_install_dry_run", body={"confirm": True})

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("launcher", result["detail"].lower())

    def test_schedule_install_dry_run_uses_fixed_schtasks_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "tgcs.bat").write_text("@echo off\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="SUCCESS\n", stderr="")

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                        result = dashboard_server.run_desk_action(
                            "schedule_install_dry_run",
                            body={"confirm": True},
                        )

        args = run_mock.call_args.args[0]
        self.assertEqual(args[0], "schtasks.exe")
        self.assertIn("/Create", args)
        self.assertIn(dashboard_server.DESK_SCHEDULER_TASK_NAME, args)
        trigger = args[args.index("/TR") + 1]
        self.assertIn("tgcs.bat", trigger)
        self.assertIn("--delivery-mode dry-run", trigger)
        self.assertNotIn("--delivery-mode live", trigger)
        self.assertEqual(result["status"], "success")
        self.assertNotIn(str(project_root), result["detail"])

    def test_schedule_remove_dry_run_uses_fixed_schtasks_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "tgcs.bat").write_text("@echo off\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="SUCCESS\n", stderr="")

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                        result = dashboard_server.run_desk_action(
                            "schedule_remove_dry_run",
                            body={"confirm": True},
                        )

        args = run_mock.call_args.args[0]
        self.assertEqual(args[:2], ["schtasks.exe", "/Delete"])
        self.assertIn(dashboard_server.DESK_SCHEDULER_TASK_NAME, args)
        self.assertEqual(result["status"], "success")

    def test_schedule_install_dry_run_failure_sanitizes_project_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "tgcs.bat").write_text("@echo off\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                ["schtasks.exe"],
                1,
                stdout="",
                stderr=f"ERROR: cannot use {project_root}\\tgcs.bat\n",
            )

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed):
                        result = dashboard_server.run_desk_action(
                            "schedule_install_dry_run",
                            body={"confirm": True},
                        )

        self.assertEqual(result["status"], "failed")
        self.assertNotIn(str(project_root), result["detail"])
        self.assertIn("project folder", result["detail"])

    def test_desk_scheduler_status_uses_manual_preview_on_non_systemd_linux_without_subprocess(self):
        with patch.object(dashboard_server.sys, "platform", "linux"):
            with patch.object(
                dashboard_server,
                "shutil",
                SimpleNamespace(which=lambda name: None),
                create=True,
            ):
                with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                    status = dashboard_server.desk_scheduler_status()

        run_mock.assert_not_called()
        self.assertFalse(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "manual")
        self.assertEqual(status["backend"], "manual_cron_preview")
        self.assertFalse(status["can_install"])
        self.assertFalse(status["can_remove"])

    def test_desk_scheduler_status_uses_manual_preview_when_linux_user_bus_is_missing(self):
        with patch.object(dashboard_server.sys, "platform", "linux"):
            with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": ""}, clear=False):
                with patch.object(
                    dashboard_server,
                    "shutil",
                    SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                    create=True,
                ):
                    with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                        status = dashboard_server.desk_scheduler_status()

        run_mock.assert_not_called()
        self.assertEqual(status["backend"], "manual_cron_preview")
        self.assertFalse(status["can_install"])

    def test_desk_scheduler_status_blocks_unsupported_platform_without_subprocess(self):
        with patch.object(dashboard_server.sys, "platform", "freebsd"):
            with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                status = dashboard_server.desk_scheduler_status()

        run_mock.assert_not_called()
        self.assertFalse(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "unavailable")
        self.assertEqual(status["backend"], "manual_cron_preview")

    def test_schedule_install_dry_run_writes_macos_launch_agent_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            home.mkdir()
            project_root.mkdir()
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root):
                        with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                            result = dashboard_server.run_desk_action(
                                "schedule_install_dry_run",
                                body={"confirm": True},
                            )

            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tgcs.jobs-fast.dry-run.plist"
            plist = plistlib.loads(plist_path.read_bytes())

        self.assertEqual(result["status"], "success")
        self.assertEqual(plist["Label"], "com.sapientropic.tgcs.jobs-fast.dry-run")
        self.assertEqual(
            plist["ProgramArguments"],
            [
                str(project_root / "tgcs"),
                "monitor",
                "run",
                "--profile-id",
                "jobs-fast",
                "--delivery-mode",
                "dry-run",
            ],
        )
        self.assertIn(["launchctl", "load", "-w", str(plist_path)], calls)

    def test_schedule_remove_dry_run_unloads_macos_launch_agent_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tgcs.jobs-fast.dry-run.plist"
            home.mkdir()
            project_root.mkdir()
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("placeholder", encoding="utf-8")
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root):
                        with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                            result = dashboard_server.run_desk_action(
                                "schedule_remove_dry_run",
                                body={"confirm": True},
                            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(calls, [["launchctl", "unload", "-w", str(plist_path)]])
        self.assertFalse(plist_path.exists())

    def test_schedule_install_dry_run_writes_linux_systemd_user_units_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            home.mkdir()
            project_root.mkdir()
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "linux"):
                with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": str(Path(tmp) / "runtime")}, clear=False):
                    with patch.object(
                        dashboard_server,
                        "shutil",
                        SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                        create=True,
                    ):
                        with patch.object(dashboard_server.Path, "home", return_value=home):
                            with patch.object(dashboard_server, "PROJECT_ROOT", project_root):
                                with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                    result = dashboard_server.run_desk_action(
                                        "schedule_install_dry_run",
                                        body={"confirm": True},
                                    )

            service_path = home / ".config" / "systemd" / "user" / "tgcs-jobs-fast-dry-run.service"
            timer_path = home / ".config" / "systemd" / "user" / "tgcs-jobs-fast-dry-run.timer"
            service_text = service_path.read_text(encoding="utf-8")
            timer_text = timer_path.read_text(encoding="utf-8")

        self.assertEqual(result["status"], "success")
        self.assertIn(f"ExecStart={project_root / 'tgcs'} monitor run --profile-id jobs-fast --delivery-mode dry-run", service_text)
        self.assertIn("OnUnitActiveSec=15min", timer_text)
        self.assertIn(["systemctl", "--user", "daemon-reload"], calls)
        self.assertIn(["systemctl", "--user", "enable", "--now", "tgcs-jobs-fast-dry-run.timer"], calls)

    def test_schedule_remove_dry_run_disables_linux_systemd_user_units_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            service_path = home / ".config" / "systemd" / "user" / "tgcs-jobs-fast-dry-run.service"
            timer_path = home / ".config" / "systemd" / "user" / "tgcs-jobs-fast-dry-run.timer"
            home.mkdir()
            project_root.mkdir()
            service_path.parent.mkdir(parents=True)
            service_path.write_text("[Service]\n", encoding="utf-8")
            timer_path.write_text("[Timer]\n", encoding="utf-8")
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "linux"):
                with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": str(Path(tmp) / "runtime")}, clear=False):
                    with patch.object(
                        dashboard_server,
                        "shutil",
                        SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                        create=True,
                    ):
                        with patch.object(dashboard_server.Path, "home", return_value=home):
                            with patch.object(dashboard_server, "PROJECT_ROOT", project_root):
                                with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                    result = dashboard_server.run_desk_action(
                                        "schedule_remove_dry_run",
                                        body={"confirm": True},
                                    )

        self.assertEqual(result["status"], "success")
        self.assertIn(["systemctl", "--user", "disable", "--now", "tgcs-jobs-fast-dry-run.timer"], calls)
        self.assertIn(["systemctl", "--user", "daemon-reload"], calls)
        self.assertFalse(service_path.exists())
        self.assertFalse(timer_path.exists())

    def test_desk_scheduler_status_queries_fixed_task_name(self):
        completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="TaskName: TGCS jobs-fast dry-run\n", stderr="")

        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                status = dashboard_server.desk_scheduler_status()

        args = run_mock.call_args.args[0]
        self.assertEqual(args, ["schtasks.exe", "/Query", "/TN", dashboard_server.DESK_SCHEDULER_TASK_NAME])
        self.assertTrue(status["available"])
        self.assertTrue(status["installed"])
        self.assertEqual(status["status"], "installed")
        self.assertIn("every 15 minutes", status["detail"])

    def test_desk_scheduler_status_reports_missing_task_without_leaking_output(self):
        completed = subprocess.CompletedProcess(
            ["schtasks.exe"],
            1,
            stdout="",
            stderr="ERROR: The system cannot find the file specified.\n",
        )

        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed):
                status = dashboard_server.desk_scheduler_status()

        self.assertTrue(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "not_installed")
        self.assertEqual(status["detail"], "Automatic practice scans are off.")
        self.assertNotIn("ERROR", json.dumps(status))

    def test_desk_scheduler_status_handles_timeout(self):
        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(
                dashboard_server,
                "_run_scheduler_command",
                side_effect=subprocess.TimeoutExpired(cmd=["schtasks.exe"], timeout=30),
            ):
                status = dashboard_server.desk_scheduler_status()

        self.assertTrue(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "unknown")
        self.assertIn("timed out", status["detail"])

    def test_desk_scheduler_status_handles_missing_schtasks(self):
        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(dashboard_server, "_run_scheduler_command", side_effect=OSError("not found")):
                status = dashboard_server.desk_scheduler_status()

        self.assertFalse(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "unavailable")
        self.assertNotIn("not found", json.dumps(status))

    def test_desk_scheduler_status_http_endpoint_requires_loopback(self):
        class FakeHandler:
            path = "/api/desk/scheduler-status"
            status = None
            payload = None
            client_address = ("192.168.1.10", 51000)

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(dashboard_server, "desk_scheduler_status") as status_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        status_mock.assert_not_called()
        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("localhost", handler.payload["error"])

    def test_desk_scheduler_status_http_endpoint_returns_status(self):
        class FakeHandler:
            path = "/api/desk/scheduler-status"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "desk_scheduler_status",
            return_value={
                "schema_version": "desk_scheduler_status_v1",
                "available": True,
                "installed": False,
                "status": "not_installed",
                "task_label": "jobs-fast dry-run",
                "interval_minutes": 15,
                "detail": "Automatic practice scans are off.",
                "next_action": "Turn on auto scan.",
                "checked_at": "2026-05-10T00:00:00Z",
            },
        ) as status_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        status_mock.assert_called_once()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["scheduler"]["schema_version"], "desk_scheduler_status_v1")

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
            self.assertFalse(status["session_ready"])
            self.assertNotIn("a" * 32, json.dumps(status))
            self.assertIn("api_hash", config_path.read_text(encoding="utf-8"))
            session_path.write_text("session-string", encoding="utf-8")
            status = dashboard_server.telegram_status(config_path=config_path, session_path=session_path)
            self.assertEqual(status["login_state"], "authorized")

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

    def test_desk_delivery_target_test_is_dry_run_only(self):
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
                        mode="dry-run",
                        ok=True,
                        status="dry_run",
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
        self.assertEqual(result["mode"], "dry-run")
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args.kwargs["chat_id"], "654321")
        self.assertEqual(send_mock.call_args.kwargs["mode"], "dry-run")

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

    def test_desk_source_import_preview_does_not_write_default_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.preview_desk_source_import(
                    {"sources": "@remote_jobs\nhttps://t.me/s/miniapps_jobs\n", "topic": "jobs"}
                )

            registry = root / ".tgcs" / "sources.json"

        self.assertFalse(registry.exists())
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["written"])
        self.assertEqual(result["added_count"], 2)
        self.assertEqual(result["topic"], "jobs")
        self.assertEqual(result["preview_sources"][0]["label"], "remote_jobs")
        self.assertEqual(result["preview_truncated_count"], 0)
        self.assertNotIn(str(root), json.dumps(result, ensure_ascii=False))

    def test_desk_source_import_writes_default_registry_without_accepting_paths_or_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                with self.assertRaises(ValueError):
                    dashboard_server.import_desk_sources(
                        {
                            "sources": "@remote_jobs",
                            "topic": "jobs",
                            "path": "C:/private/sources.json",
                            "command": "tgcs sources import evil.txt",
                        }
                    )
                result = dashboard_server.import_desk_sources({"sources": "@remote_jobs", "topic": "jobs"})

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertTrue(result["written"])
        self.assertEqual(result["added_count"], 1)
        self.assertEqual(result["registry_path"], ".tgcs/sources.json")
        self.assertEqual(payload["sources"][0]["username"], "remote_jobs")
        self.assertEqual(payload["sources"][0]["topics"], ["jobs"])
        self.assertNotIn("tgcs sources import", json.dumps(payload, ensure_ascii=False))

    def test_import_starter_sources_uses_packaged_jobs_list_without_browser_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starter = root / "channel_lists" / "jobs.txt"
            starter.parent.mkdir(parents=True)
            starter.write_text("remote_jobs\nfrontend_jobs\n", encoding="utf-8")
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                with self.assertRaises(ValueError):
                    dashboard_server.import_starter_sources({"topic": "jobs", "path": "private.txt"})
                result = dashboard_server.import_starter_sources({"topic": "jobs"})

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertTrue(result["written"])
        self.assertEqual(result["added_count"], 2)
        self.assertEqual(payload["sources"][0]["topics"], ["jobs"])

    def test_desk_source_import_rejects_non_telegram_like_identifiers(self):
        with self.assertRaises(ValueError):
            dashboard_server.preview_desk_source_import(
                {"sources": "remote_jobs\nnot a channel; rm -rf", "topic": "jobs"}
            )

    def test_desk_source_import_rejects_empty_sources_and_invalid_topic(self):
        with self.assertRaises(ValueError):
            dashboard_server.preview_desk_source_import({"sources": "  \n# only comments", "topic": "jobs"})
        with self.assertRaises(ValueError):
            dashboard_server.preview_desk_source_import({"sources": "remote_jobs", "topic": "../private"})

    def test_desk_source_import_merges_topic_into_existing_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / ".tgcs" / "sources.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [
                            {
                                "source_id": "telegram:remote_jobs",
                                "username": "remote_jobs",
                                "channel_id": None,
                                "label": "remote_jobs",
                                "topics": [],
                                "priority": "normal",
                                "expected_language": "",
                                "scan_window_hours": 24,
                                "enabled": True,
                                "notes": "",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.import_desk_sources({"sources": "remote_jobs", "topic": "jobs"})
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertEqual(result["added_count"], 0)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(payload["sources"][0]["topics"], ["jobs"])

    def test_desk_sources_lists_and_toggles_default_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "remote_jobs", "topic": "jobs"})
                listed = dashboard_server.desk_sources()
                updated = dashboard_server.set_desk_source_enabled(
                    "telegram:remote_jobs",
                    {"enabled": False},
                )

        self.assertEqual(listed["source_count"], 1)
        self.assertEqual(listed["enabled_count"], 1)
        self.assertEqual(listed["sources"][0]["label"], "remote_jobs")
        self.assertEqual(updated["enabled_count"], 0)
        self.assertFalse(updated["sources"][0]["enabled"])
        self.assertNotIn(str(root), json.dumps(updated, ensure_ascii=False))

    def test_desk_source_remove_requires_confirmation_and_fixed_source_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "remote_jobs", "topic": "jobs"})
                with self.assertRaises(ValueError):
                    dashboard_server.remove_desk_source("telegram:remote_jobs", {})
                updated = dashboard_server.remove_desk_source("telegram:remote_jobs", {"confirm": True})

        self.assertEqual(updated["source_count"], 0)

    def test_source_assistant_previews_and_applies_add_remove_without_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "old_jobs", "topic": "jobs"})
                with self.assertRaises(ValueError):
                    dashboard_server.run_source_assistant({"instruction": "add @remote_jobs", "command": "rm -rf ."})
                preview = dashboard_server.run_source_assistant(
                    {"instruction": "add @remote_jobs; remove @old_jobs", "topic": "jobs", "dry_run": True}
                )
                applied = dashboard_server.apply_source_assistant_resolved_plan(preview["resolved_plan"], "jobs")
                listed = dashboard_server.desk_sources()

        self.assertTrue(preview["dry_run"])
        self.assertEqual(preview["added_count"], 1)
        self.assertEqual(preview["removed_count"], 1)
        self.assertEqual(preview["resolved_plan"]["add"], ["remote_jobs"])
        self.assertEqual(preview["resolved_plan"]["remove"], ["telegram:old_jobs"])
        self.assertTrue(applied["written"])
        self.assertEqual(listed["source_count"], 1)
        self.assertEqual(listed["sources"][0]["channel"], "remote_jobs")

    def test_source_assistant_uses_ai_only_after_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "old_jobs\nweb3_jobs", "topic": "jobs"})
                with patch.object(
                    dashboard_server,
                    "_source_assistant_llm_plan",
                    return_value={"remove": ["telegram:old_jobs"], "disable": ["telegram:web3_jobs"], "enable": []},
                ) as planner:
                    local_preview = dashboard_server.run_source_assistant(
                        {"instruction": "remove stale sources and pause web3", "topic": "jobs", "dry_run": True}
                    )
                    planner.assert_not_called()
                    ai_preview = dashboard_server.run_source_assistant(
                        {
                            "instruction": "remove stale sources and pause web3",
                            "topic": "jobs",
                            "dry_run": True,
                            "confirm_external_ai": True,
                        }
                    )
                    applied = dashboard_server.run_source_assistant(
                        {
                            "instruction": "remove stale sources and pause web3",
                            "topic": "jobs",
                            "dry_run": False,
                            "confirm_external_ai": True,
                        }
                    )
                listed = dashboard_server.desk_sources()

        self.assertFalse(local_preview["llm_used"])
        self.assertEqual(local_preview["removed_count"], 0)
        self.assertTrue(ai_preview["llm_used"])
        self.assertEqual(ai_preview["removed_count"], 1)
        self.assertEqual(ai_preview["disabled_count"], 1)
        self.assertEqual(ai_preview["resolved_plan"]["remove"], ["telegram:old_jobs"])
        self.assertEqual(ai_preview["resolved_plan"]["disable"], ["telegram:web3_jobs"])
        self.assertTrue(applied["written"])
        self.assertEqual(listed["source_count"], 1)
        self.assertFalse(listed["sources"][0]["enabled"])

    def test_desk_source_topics_updates_default_registry_without_accepting_paths_or_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "remote_jobs", "topic": "jobs"})
                with self.assertRaises(ValueError):
                    dashboard_server.set_desk_source_topics(
                        "telegram:remote_jobs",
                        {"topics": ["remote-work"], "path": "C:/private/sources.json"},
                    )
                updated = dashboard_server.set_desk_source_topics(
                    "telegram:remote_jobs",
                    {"topics": ["remote-work", "jobs", "remote-work"]},
                )

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertEqual(updated["topics"], ["jobs", "remote-work"])
        self.assertEqual(updated["sources"][0]["topics"], ["remote-work", "jobs"])
        self.assertEqual(payload["sources"][0]["topics"], ["remote-work", "jobs"])
        self.assertNotIn(str(root), json.dumps(updated, ensure_ascii=False))

    def test_desk_source_topics_rejects_invalid_payloads(self):
        invalid_payloads = [
            {"topics": "jobs"},
            {"topics": []},
            {"topics": ["../private"]},
            {"topics": ["jobs", 123]},
            {"topics": [f"topic{i}" for i in range(9)]},
        ]
        for body in invalid_payloads:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    dashboard_server.set_desk_source_topics("telegram:remote_jobs", body)

    def test_desk_source_enabled_rejects_unexpected_fields(self):
        with self.assertRaises(ValueError):
            dashboard_server.set_desk_source_enabled(
                "telegram:remote_jobs",
                {"enabled": False, "path": "C:/private/sources.json"},
            )

    def test_desk_source_import_http_endpoints_use_specialized_api(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def __init__(self, path):
                self.path = path

            def _read_json_body(self):
                return {"sources": "@remote_jobs", "topic": "jobs"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        endpoint_functions = {
            "/api/desk/sources/preview": "preview_desk_source_import",
            "/api/desk/sources/import": "import_desk_sources",
        }
        for path, function_name in endpoint_functions.items():
            with self.subTest(path=path):
                with patch.object(
                    dashboard_server,
                    function_name,
                    return_value={
                        "schema_version": "desk_source_import_result_v1",
                        "dry_run": path.endswith("preview"),
                        "written": path.endswith("import"),
                        "topic": "jobs",
                        "added_count": 1,
                        "updated_count": 0,
                        "unchanged_count": 0,
                        "source_count": 1,
                        "registry_path": ".tgcs/sources.json",
                        "preview_sources": [{"label": "remote_jobs", "source_id": "telegram:remote_jobs"}],
                        "title": "Sources ready",
                        "detail": "ok",
                        "next_action": "Run source checks.",
                        "finished_at": "2026-05-10T00:00:00Z",
                    },
                ) as action_mock:
                    handler = FakeHandler(path)
                    dashboard_server.DashboardHandler.do_POST(handler)

                action_mock.assert_called_once_with({"sources": "@remote_jobs", "topic": "jobs"})
                self.assertEqual(handler.status, HTTPStatus.OK)
                self.assertEqual(handler.payload["result"]["schema_version"], "desk_source_import_result_v1")

    def test_desk_source_enabled_http_endpoint_uses_specialized_api(self):
        class FakeHandler:
            path = "/api/desk/sources/telegram%3Aremote_jobs/enabled"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"enabled": False}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "set_desk_source_enabled",
            return_value={"schema_version": "desk_sources_v1", "source_count": 1, "enabled_count": 0, "topics": [], "sources": []},
        ) as action_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        action_mock.assert_called_once_with("telegram:remote_jobs", {"enabled": False})
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["sources"]["schema_version"], "desk_sources_v1")

    def test_desk_source_topics_http_endpoint_uses_specialized_api(self):
        class FakeHandler:
            path = "/api/desk/sources/telegram%3Aremote_jobs/topics"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"topics": ["jobs", "remote-work"]}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "set_desk_source_topics",
            return_value={
                "schema_version": "desk_sources_v1",
                "source_count": 1,
                "enabled_count": 1,
                "topics": ["jobs", "remote-work"],
                "sources": [],
            },
        ) as action_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        action_mock.assert_called_once_with("telegram:remote_jobs", {"topics": ["jobs", "remote-work"]})
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["sources"]["schema_version"], "desk_sources_v1")

    def test_desk_source_topics_http_endpoint_rejects_encoded_invalid_source_ids(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def __init__(self, path):
                self.path = path

            def _read_json_body(self):
                return {"topics": ["jobs"]}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        paths = [
            "/api/desk/sources/telegram%3A..%2Fprivate/topics",
            "/api/desk/sources/telegram%3Aremote_jobs%00/topics",
            f"/api/desk/sources/telegram%3A{'a' * 65}/topics",
        ]
        for path in paths:
            with self.subTest(path=path):
                handler = FakeHandler(path)
                dashboard_server.DashboardHandler.do_POST(handler)

                self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                self.assertIn("Source id is not supported", handler.payload["error"])

    def test_profile_enabled_http_endpoint_updates_runtime_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tgcs.db"
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {
                        "id": "jobs-fast",
                        "path": "profiles/templates/jobs.md",
                        "enabled": True,
                    },
                )
            finally:
                conn.close()

            class FakeHandler:
                path = "/api/profiles/jobs-fast/enabled"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {"enabled": False}

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)
            conn = monitor_state.connect(db_path)
            try:
                snapshot = monitor_state.dashboard_snapshot(conn)
            finally:
                conn.close()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertFalse(handler.payload["profile"]["enabled"])
        self.assertFalse(snapshot["profiles"][0]["enabled"])

    def test_profile_enabled_http_endpoint_rejects_unexpected_fields(self):
        class FakeHandler:
            path = "/api/profiles/jobs-fast/enabled"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"enabled": False, "command": "tgcs monitor run"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("Unsupported profile setting field: command", handler.payload["error"])

    def test_profile_enabled_http_endpoint_requires_boolean(self):
        class FakeHandler:
            path = "/api/profiles/jobs-fast/enabled"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"enabled": "false"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("true or false", handler.payload["error"])

    def test_profile_runtime_settings_http_endpoint_updates_runtime_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tgcs.db"
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {
                        "id": "jobs-fast",
                        "path": "profiles/templates/jobs.md",
                        "enabled": True,
                        "scan_window_hours": 2,
                        "semantic_max_messages": 20,
                    },
                )
            finally:
                conn.close()

            class FakeHandler:
                path = "/api/profiles/jobs-fast/runtime-settings"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {"scan_window_hours": 6, "semantic_max_messages": 40}

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)
            conn = monitor_state.connect(db_path)
            try:
                snapshot = monitor_state.dashboard_snapshot(conn)
            finally:
                conn.close()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["profile"]["config"]["scan_window_hours"], 6)
        self.assertEqual(handler.payload["profile"]["config"]["semantic_max_messages"], 40)
        self.assertEqual(snapshot["profiles"][0]["scan_window_hours"], 6)
        self.assertEqual(snapshot["profiles"][0]["semantic_max_messages"], 40)

    def test_profile_runtime_settings_http_endpoint_rejects_extra_fields(self):
        class FakeHandler:
            path = "/api/profiles/jobs-fast/runtime-settings"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"scan_window_hours": 6, "command": "tgcs monitor run"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("Unsupported profile setting field: command", handler.payload["error"])

    def test_profile_runtime_settings_http_endpoint_rejects_out_of_range_values(self):
        class FakeConnection:
            def close(self):
                pass

        class FakeHandler:
            path = "/api/profiles/jobs-fast/runtime-settings"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _connect(self):
                return FakeConnection()

            def _read_json_body(self):
                return {"scan_window_hours": 0}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server.monitor_state,
            "update_profile_runtime_settings",
            side_effect=monitor_state.MonitorStateError("scan_window_hours must be between 1 and 168."),
        ) as update_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        update_mock.assert_called_once()
        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("between 1 and 168", handler.payload["error"])

    def test_profile_runtime_settings_http_endpoint_rejects_invalid_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tgcs.db"
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {"id": "jobs-fast", "path": "profiles/templates/jobs.md", "enabled": True},
                )
            finally:
                conn.close()

            class FakeHandler:
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def __init__(self, body, path="/api/profiles/jobs-fast/runtime-settings"):
                    self.body = body
                    self.path = path

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return self.body

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            cases = [
                ({}, "/api/profiles/jobs-fast/runtime-settings", "At least one profile setting is required"),
                ({"semantic_max_messages": 0}, "/api/profiles/jobs-fast/runtime-settings", "between 1 and 500"),
                ({"semantic_max_messages": 501}, "/api/profiles/jobs-fast/runtime-settings", "between 1 and 500"),
                ({"scan_window_hours": "six"}, "/api/profiles/jobs-fast/runtime-settings", "must be an integer"),
                ({"scan_window_hours": True}, "/api/profiles/jobs-fast/runtime-settings", "must be an integer"),
                ({"scan_window_hours": 6}, "/api/profiles/unknown/runtime-settings", "Profile is not registered"),
            ]
            for body, path, error_fragment in cases:
                with self.subTest(body=body, path=path):
                    handler = FakeHandler(body, path)
                    dashboard_server.DashboardHandler.do_POST(handler)

                    self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                    self.assertIn(error_fragment, handler.payload["error"])

    def test_profile_draft_note_http_endpoint_creates_reviewable_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "tgcs.db"
            profile_path = root / "profiles" / "jobs.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text("# Jobs profile\n", encoding="utf-8")
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {"id": "jobs-fast", "path": str(profile_path), "enabled": True},
                )
            finally:
                conn.close()

            class FakeHandler:
                path = "/api/profiles/jobs-fast/draft-note"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {"note": "Prefer senior remote AI engineering roles."}

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)
            conn = monitor_state.connect(db_path)
            try:
                patches = monitor_state.dashboard_snapshot(conn)["profile_patch_suggestions"]
            finally:
                conn.close()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["patch"]["status"], "pending")
        self.assertEqual(len(patches), 1)
        self.assertIn("Prefer senior remote", patches[0]["note"])

    def test_profile_draft_note_http_endpoint_rejects_invalid_payloads(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def __init__(self, body):
                self.body = body
                self.path = "/api/profiles/jobs-fast/draft-note"

            def _read_json_body(self):
                return self.body

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        for body, error_fragment in [
            ({}, "Profile note is required"),
            ({"note": "valid", "command": "tgcs monitor run"}, "Unsupported profile draft field"),
            ({"note": "x" * (dashboard_server.PROFILE_DRAFT_NOTE_MAX_LENGTH + 1)}, "characters or fewer"),
        ]:
            with self.subTest(body=list(body)):
                handler = FakeHandler(body)
                dashboard_server.DashboardHandler.do_POST(handler)

                self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                self.assertIn(error_fragment, handler.payload["error"])

    def test_profile_create_endpoint_writes_local_profile_and_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "tgcs.db"

            class FakeHandler:
                path = "/api/profiles/create"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {
                        "brief": "Senior remote AI engineering roles. Avoid unpaid internships and vague promos.",
                        "source_filename": "background.txt",
                        "source_text": "Prefer agent platforms, backend automation, and clear paid work.",
                    }

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                handler = FakeHandler()
                dashboard_server.DashboardHandler.do_POST(handler)
                conn = monitor_state.connect(db_path)
                try:
                    snapshot = monitor_state.dashboard_snapshot(conn)
                finally:
                    conn.close()

            profile = handler.payload["profile"]
            profile_path = root / profile["profile_path"]
            profile_body = profile_path.read_text(encoding="utf-8")
            config_exists = (root / ".tgcs" / "profiles.toml").exists()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(profile["schema_version"], "desk_profile_create_result_v1")
        self.assertIn("Senior remote AI engineering roles", profile_body)
        self.assertTrue(config_exists)
        self.assertEqual(snapshot["profiles"][0]["profile_id"], profile["profile_id"])

    def test_profile_create_endpoint_rejects_invalid_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tgcs.db"

            class FakeHandler:
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def __init__(self, body):
                    self.body = body
                    self.path = "/api/profiles/create"

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return self.body

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            for body, error_fragment in [
                ({}, "Describe the profile"),
                ({"brief": "valid", "command": "tgcs monitor run"}, "Unsupported profile creation field"),
                ({"brief": "x" * (dashboard_server.PROFILE_CREATE_MAX_TEXT_LENGTH + 1)}, "characters or fewer"),
            ]:
                with self.subTest(body=list(body)):
                    handler = FakeHandler(body)
                    dashboard_server.DashboardHandler.do_POST(handler)

                    self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                    self.assertIn(error_fragment, handler.payload["error"])

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
                "title": "Run practice scan",
                "detail": "done",
                "display_command": "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
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

    def test_health_endpoint_returns_json_before_static_fallback(self):
        class FakeServer:
            server_address = ("127.0.0.1", 8765)

        class FakeHandler:
            path = "/api/desk/health"
            status = None
            payload = None
            server = FakeServer()

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_GET(handler)

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["schema_version"], "desk_health_v1")
        self.assertEqual(handler.payload["app"], "tgcs-signal-desk")
        self.assertIn("desk_notification_token_v1", handler.payload["capabilities"])

    def test_notification_token_status_endpoint_requires_loopback_and_returns_status(self):
        class FakeHandler:
            path = "/api/desk/notification-token/status"
            client_address = ("127.0.0.1", 12345)
            status = None
            payload = None

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "desk_notification_token_status",
            return_value={"schema_version": "desk_notification_token_status_v1", "configured": False},
        ) as status_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        status_mock.assert_called_once_with()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertFalse(handler.payload["token"]["configured"])

    def test_ai_settings_status_endpoint_requires_loopback_and_returns_status(self):
        class FakeHandler:
            path = "/api/desk/ai-settings/status"
            client_address = ("127.0.0.1", 12345)
            status = None
            payload = None

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "desk_ai_settings_status",
            return_value={"schema_version": "desk_ai_settings_status_v1", "configured_count": 1},
        ) as status_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        status_mock.assert_called_once_with()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["ai"]["configured_count"], 1)

    def test_ai_settings_update_endpoint_uses_safe_body(self):
        class FakeHandler:
            path = "/api/desk/ai-settings"
            client_address = ("127.0.0.1", 12345)
            status = None
            payload = None

            def _read_json_body(self):
                return {"provider": "deepseek", "api_key": "sk-deepseek123"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "update_desk_ai_settings",
            return_value={"schema_version": "desk_ai_settings_status_v1", "configured_count": 1},
        ) as update_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        update_mock.assert_called_once_with({"provider": "deepseek", "api_key": "sk-deepseek123"})
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["ai"]["configured_count"], 1)

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

    def test_feedback_profile_suggestions_endpoint_calls_monitor_state(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        class FakeHandler:
            path = "/api/feedback/profile-suggestions"
            client_address = ("127.0.0.1", 12345)
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
            "create_feedback_profile_patch_suggestions",
            return_value={"schema_version": "feedback_profile_suggestions_result_v1", "created_count": 1},
        ) as suggestions_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        suggestions_mock.assert_called_once_with(handler.conn)
        self.assertTrue(handler.conn.closed)
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["suggestions"]["created_count"], 1)


if __name__ == "__main__":
    unittest.main()
