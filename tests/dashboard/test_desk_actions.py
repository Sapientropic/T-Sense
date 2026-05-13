import subprocess
import tempfile
import unittest
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_server, desk_actions, desk_sources


class DashboardDeskActionCatalogTests(unittest.TestCase):
    def test_desk_source_helpers_stay_available_from_dashboard_server_facade(self):
        self.assertIs(dashboard_server.SourceAccessProbeError, desk_sources.SourceAccessProbeError)
        self.assertIs(dashboard_server.desk_sources, desk_sources.desk_sources)
        self.assertIs(dashboard_server.probe_source_access, desk_sources.probe_source_access)
        self.assertIs(dashboard_server.apply_source_access_repair, desk_sources.apply_source_access_repair)
        self.assertIs(dashboard_server.run_source_assistant, desk_sources.run_source_assistant)


    def test_desk_action_helpers_stay_available_from_dashboard_server_facade(self):
        self.assertIs(dashboard_server.DESK_ACTIONS, desk_actions.DESK_ACTIONS)
        self.assertIs(dashboard_server.desk_actions, desk_actions.desk_actions)
        self.assertIs(dashboard_server.run_desk_action, desk_actions.run_desk_action)
        self.assertIs(dashboard_server.desk_active_actions, desk_actions.desk_active_actions)
        self.assertIs(dashboard_server._desk_safe_result_text, desk_actions._desk_safe_result_text)


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


    def test_run_desk_action_only_returns_openable_report_artifacts(self):
        cases = [
            ("demo_render", {"html_path": "output/demo-report.html"}, "output/demo-report.html"),
            ("feedback_export", {"output_path": "output/feedback/review-feedback.jsonl"}, ""),
            ("monitor_jobs_dry_run", {"html_path": "output/runs/run-1/../secret-report.html"}, ""),
            ("monitor_jobs_dry_run", {"html_path": "C:/Users/Administrator/private/report.html"}, ""),
        ]
        for action_id, data, expected_artifact in cases:
            with self.subTest(action_id=action_id, artifact=data):
                completed = subprocess.CompletedProcess(
                    ["python"],
                    0,
                    stdout=json.dumps({"ok": True, "data": {"status": "complete", **data}, "error": None}),
                    stderr="",
                )
                with patch.object(dashboard_server.subprocess, "run", return_value=completed):
                    result = dashboard_server.run_desk_action(action_id)

                self.assertEqual(result["status"], "success")
                self.assertEqual(result["artifact_path"], expected_artifact)


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
            "probe_window_hours": 24,
            "probe_window_hours_min": 24,
            "probe_window_hours_max": 24,
            "reason_counts": {"cannot_resolve_entity": 1, "empty_recent_window": 1},
            "sources": [],
        }

        with patch.object(dashboard_server, "probe_source_access", return_value=health):
            with patch.object(dashboard_server.subprocess, "run") as run_mock:
                result = dashboard_server.run_desk_action("sources_probe_access", body={"command": "ignored"})

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "success")
        self.assertIn("2 recently active", result["detail"])
        self.assertIn("cannot resolve 1", result["detail"])
        self.assertEqual(result["source_access"]["accessible_count"], 2)
        self.assertEqual(result["source_access"]["inaccessible_count"], 1)
        self.assertEqual(result["source_access"]["probe_window_hours"], 24)


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


    def test_active_desk_action_state_exposes_progress_without_shell_commands(self):
        dashboard_server._desk_mark_action_started("sources_probe_access", title="Check source access")
        try:
            dashboard_server._desk_update_action_progress(
                "sources_probe_access",
                checked_count=17,
                total_count=68,
                detail="Source access check running; checked 17/68 sources. Keep Signal Desk open.",
            )
            active = dashboard_server.desk_active_actions()
        finally:
            dashboard_server._desk_mark_action_finished("sources_probe_access")

        self.assertEqual(active[0]["action_id"], "sources_probe_access")
        self.assertEqual(active[0]["checked_count"], 17)
        self.assertEqual(active[0]["total_count"], 68)
        self.assertIn("checked 17/68", active[0]["detail"])


    def test_dashboard_state_includes_structured_cached_source_access_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            health = {
                "schema_version": dashboard_server.DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION,
                "checked_at": datetime.now(UTC).isoformat(),
                "source_count": 8,
                "checked_count": 8,
                "truncated_count": 0,
                "accessible_count": 2,
                "quiet_count": 1,
                "inaccessible_count": 5,
                "probe_window_hours": 24,
                "probe_window_hours_min": 24,
                "probe_window_hours_max": 24,
                "reason_counts": {"cannot_resolve_entity": 5, "empty_recent_window": 1},
                "sources": [],
            }
            snapshot = {
                "setup_status": {
                    "checks": [
                        {
                            "check_id": "source_access",
                            "label": "Source access",
                            "status": "blocked",
                            "detail": "The latest run fetched no usable Telegram messages.",
                        }
                    ]
                }
            }
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server._write_source_access_health(health)
                with patch.object(dashboard_server.monitor_state, "dashboard_snapshot", return_value=snapshot):
                    payload = dashboard_server.dashboard_state_payload(object())

        check = payload["setup_status"]["checks"][0]
        self.assertIn("2 recently active", check["detail"])
        self.assertEqual(check["source_access"]["quiet_count"], 1)
        self.assertEqual(check["source_access"]["probe_window_hours"], 24)


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



if __name__ == "__main__":
    unittest.main()
