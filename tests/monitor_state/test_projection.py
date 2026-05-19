import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_opportunities, dashboard_profiles, dashboard_projection, dashboard_setup, monitor_state


class MonitorStateProjectionTests(unittest.TestCase):
    def setUp(self):
        self.llm_key_patcher = patch.object(dashboard_projection.report, "llm_key_available", return_value=True)
        self.llm_key_available = self.llm_key_patcher.start()
        self.addCleanup(self.llm_key_patcher.stop)

    def test_dashboard_projection_helpers_stay_available_from_monitor_state_facade(self):
        self.assertIs(monitor_state.dashboard_snapshot, dashboard_projection.dashboard_snapshot)
        self.assertIs(monitor_state.dashboard_setup_status, dashboard_projection.dashboard_setup_status)
        self.assertIs(monitor_state.dashboard_run_projection, dashboard_projection.dashboard_run_projection)
        self.assertIs(monitor_state.dashboard_profile_projection, dashboard_projection.dashboard_profile_projection)
        self.assertIs(dashboard_projection.dashboard_profile_projection, dashboard_profiles.dashboard_profile_projection)
        self.assertIs(dashboard_projection.profile_matching_summary, dashboard_profiles.profile_matching_summary)
        self.assertIs(dashboard_projection.opportunity_summary, dashboard_opportunities.opportunity_summary)
        self.assertIs(dashboard_projection.opportunity_next_action, dashboard_opportunities.opportunity_next_action)
        self.assertIs(dashboard_projection.dashboard_setup_status, dashboard_setup.dashboard_setup_status)
        self.assertIs(dashboard_projection.setup_checklist, dashboard_setup.setup_checklist)
        self.assertIs(monitor_state.delivery_target_from_row, dashboard_projection.delivery_target_from_row)
        self.assertIs(monitor_state.display_profile_path, dashboard_projection.display_profile_path)

    def test_dashboard_profile_helpers_respect_projection_project_root_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = root / "profiles" / "desk" / "custom.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                "\n".join(
                    [
                        "# Custom",
                        "",
                        "## Report Labels",
                        'report_title: "Patched Root Signal Report"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(dashboard_projection, "PROJECT_ROOT", root):
                title = dashboard_projection.report_title_from_profile_path("profiles/desk/custom.md")

        self.assertEqual(title, "Patched Root Signal Report")

    def test_template_profile_does_not_expose_desk_tuning_prompt_as_preference(self):
        profile_text = Path("profiles/templates/jobs.md").read_text(encoding="utf-8")

        self.assertNotIn("Desk feedback tuning:", profile_text)

    def test_profile_matching_summary_resolves_learned_full_stack_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            profile_path.write_text(
                "\n".join(
                    [
                        "# Profile",
                        "",
                        "## Basic Info",
                        "- **Role**: Frontend / full-stack developer opportunities worth acting on",
                        "- **Level**: Middle to senior contract work",
                        "",
                        "## Search Rules",
                        "1. Include frontend and full-stack roles when actionable.",
                        "",
                        "## Follow-up Preferences",
                        "- not full stack",
                        "- i don't want full stack",
                        "- not lead",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            summary = dashboard_profiles.profile_matching_summary(str(profile_path))

        serialized = json.dumps(summary, ensure_ascii=False)
        self.assertIn("Role: Frontend developer opportunities worth acting on", serialized)
        self.assertIn("not full stack", serialized)
        self.assertNotIn("Frontend / full-stack", serialized)
        self.assertNotIn("Include frontend and full-stack roles", serialized)


    def test_dashboard_snapshot_includes_first_run_setup_status(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        self.llm_key_available.return_value = False
        empty_snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(empty_snapshot["setup_status"]["stage"], "needs_ai_key")
        self.assertIn("Open Start", empty_snapshot["setup_status"]["next_step"])
        self.assertIn("demo report", empty_snapshot["setup_status"]["next_step"])
        self.assertFalse(empty_snapshot["setup_status"]["has_profiles"])
        self.assertFalse(empty_snapshot["setup_status"]["has_runs"])
        self.assertEqual(empty_snapshot["setup_status"]["checks"][0]["check_id"], "ai_api")
        self.assertEqual(empty_snapshot["setup_status"]["checks"][0]["status"], "todo")

        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "alert_schedule_mode": "work_hours",
            },
        )
        self.llm_key_available.return_value = True
        profile_snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(
            profile_snapshot["setup_status"]["next_step"],
            "Open Start and run the first AI review for jobs-fast.",
        )
        self.assertTrue(profile_snapshot["setup_status"]["has_profiles"])
        self.assertFalse(profile_snapshot["setup_status"]["has_runs"])
        checks = {item["check_id"]: item for item in profile_snapshot["setup_status"]["checks"]}
        self.assertEqual(checks["profiles"]["status"], "done")
        self.assertEqual(checks["first_run"]["status"], "active")
        self.assertEqual(
            checks["first_run"]["command"],
            "tgcs monitor run --profile-id jobs-fast --delivery-mode live",
        )


    def test_dashboard_setup_status_does_not_block_local_setup_without_ai_key(self):
        status = dashboard_setup.dashboard_setup_status(
            profiles=[],
            runs=[],
            delivery_targets=[],
            ai_configured=False,
        )

        self.assertEqual(status["stage"], "needs_ai_key")
        self.assertIn("Open Start", status["next_step"])
        checks = {item["check_id"]: item for item in status["checks"]}
        self.assertEqual(list(checks)[0], "ai_api")
        self.assertEqual(checks["ai_api"]["status"], "todo")
        self.assertIn("first AI review", checks["ai_api"]["detail"])
        self.assertEqual(checks["profiles"]["status"], "active")
        self.assertNotIn("before creating", checks["profiles"]["detail"])
        self.assertIn("local", checks["profiles"]["detail"].lower())


    def test_dashboard_setup_status_distinguishes_packaged_profiles_from_user_goal(self):
        status = dashboard_setup.dashboard_setup_status(
            profiles=[
                {
                    "profile_id": "market-news",
                    "config": {"id": "market-news", "path": "profiles/templates/market-news.md"},
                    "enabled": True,
                },
                {
                    "profile_id": "jobs-fast",
                    "config": {"id": "jobs-fast", "path": "profiles/templates/jobs.md"},
                    "enabled": True,
                },
            ],
            runs=[],
            delivery_targets=[],
            ai_configured=False,
        )

        self.assertTrue(status["has_profiles"])
        self.assertFalse(status["has_user_goal"])
        self.assertIn("create or choose", status["next_step"].lower())
        checks = {item["check_id"]: item for item in status["checks"]}
        self.assertEqual(checks["profiles"]["status"], "active")


    def test_dashboard_setup_status_treats_desk_profile_as_user_goal(self):
        status = dashboard_setup.dashboard_setup_status(
            profiles=[
                {
                    "profile_id": "custom-monitor",
                    "config": {"id": "custom-monitor", "path": "profiles/desk/custom-monitor.md"},
                    "enabled": True,
                },
            ],
            runs=[],
            delivery_targets=[],
            ai_configured=False,
        )

        self.assertTrue(status["has_profiles"])
        self.assertTrue(status["has_user_goal"])
        self.assertIn("AI API key", status["next_step"])


    def test_dashboard_setup_prefers_latest_desk_profile_for_first_run(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "alert_schedule_mode": "work_hours",
            },
        )
        monitor_state.upsert_profile(
            conn,
            {
                "id": "frontend-only",
                "path": "profiles/desk/frontend-only.md",
                "enabled": True,
                "source_topics": ["jobs"],
                "alert_schedule_mode": "work_hours",
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(
            snapshot["setup_status"]["next_step"],
            "Open Start and run the first AI review for frontend-only.",
        )
        checks = {item["check_id"]: item for item in snapshot["setup_status"]["checks"]}
        self.assertEqual(
            checks["first_run"]["command"],
            "tgcs monitor run --profile-id frontend-only --delivery-mode live",
        )


    def test_dashboard_setup_status_handles_all_profiles_disabled(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": False,
                "alert_schedule_mode": "work_hours",
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["setup_status"]["stage"], "needs_enabled_profile")
        self.assertEqual(snapshot["setup_status"]["next_step"], "Enable a profile in .tgcs/profiles.toml")
        self.assertTrue(snapshot["setup_status"]["has_profiles"])
        self.assertFalse(snapshot["setup_status"]["has_runs"])
        checks = {item["check_id"]: item for item in snapshot["setup_status"]["checks"]}
        self.assertEqual(checks["profiles"]["status"], "blocked")
        self.assertIn(".tgcs/profiles.toml", checks["profiles"]["command"])


    def test_dashboard_setup_status_prioritizes_latest_source_failure(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "source_topics": ["jobs"],
                "alert_schedule_mode": "work_hours",
            },
        )
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-source-failed",
                "profile_id": "jobs-fast",
                "status": "failed",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "prefilter": {"semantic_stage": "scan_failed"},
                "diagnostics": [
                    {
                        "code": "channel_failures",
                        "severity": "warning",
                        "message": "14 channels failed.",
                    },
                    {
                        "code": "no_messages_fetched",
                        "severity": "failure",
                        "message": "No messages were fetched.",
                    },
                ],
                "alert_count": 0,
                "review_card_count": 0,
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["setup_status"]["stage"], "needs_source_access")
        self.assertIn("Settings > Sources", snapshot["setup_status"]["next_step"])
        self.assertIn("discover Telegram channels with AI", snapshot["setup_status"]["next_step"])
        self.assertTrue(snapshot["setup_status"]["has_runs"])
        checks = {item["check_id"]: item for item in snapshot["setup_status"]["checks"]}
        self.assertEqual(checks["source_access"]["status"], "blocked")
        self.assertEqual(checks["first_run"]["status"], "blocked")
        self.assertNotIn("command", checks["source_access"])


    def test_dashboard_runs_include_prefilter_and_llm_quality_summary(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-1",
                "profile_id": "jobs-fast",
                "status": "complete",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "prefilter": {
                    "raw_message_count": 120,
                    "matched_count": 9,
                    "semantic_stage": "report_ran",
                },
                "llm": {
                    "provider": "deepseek",
                    "latency_ms": 703,
                    "cache": {"hit_rate": 0.9656},
                    "usage": {"completion_tokens": 7},
                },
                "diagnostics": [
                    {
                        "code": "scan_incomplete",
                        "severity": "warning",
                        "message": "One channel may be incomplete.",
                        "next_step": "Rerun with a smaller window.",
                    },
                    {
                        "code": "ocr_disabled_media_present",
                        "severity": "info",
                        "message": "Media was present while OCR was disabled.",
                        "next_step": "Enable OCR only when needed.",
                    },
                ],
                "alert_count": 1,
                "review_card_count": 4,
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        quality = snapshot["runs"][0]["quality"]
        self.assertEqual(quality["prefilter"], "9/120")
        self.assertEqual(quality["semantic_stage"], "report_ran")
        self.assertEqual(quality["llm_provider"], "deepseek")
        self.assertEqual(quality["cache_hit_rate"], 0.9656)
        self.assertEqual(quality["latency_ms"], 703)
        self.assertEqual(quality["completion_tokens"], 7)
        self.assertEqual(quality["diagnostic_count"], 2)
        self.assertEqual(quality["diagnostic_warning_count"], 1)
        self.assertEqual(quality["diagnostic_failure_count"], 0)
        self.assertEqual(quality["top_diagnostic_code"], "scan_incomplete")


    def test_dashboard_runs_project_report_artifact_without_full_manifest(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-1",
                "profile_id": "jobs-fast",
                "status": "complete",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "source_registry_path": ".tgcs/sources.json",
                "profile_path": "profiles/templates/jobs.md",
                "alert_count": 2,
                "review_card_count": 4,
                "artifacts": [
                    {
                        "type": "raw_scan",
                        "path": "output/runs/run-1/prefiltered-scan.jsonl",
                        "sha256": "raw-hash",
                    },
                    {
                        "type": "scan_meta",
                        "path": "output/runs/run-1/scan.meta.json",
                        "sha256": "meta-hash",
                    },
                    {
                        "type": "report_html",
                        "path": "output/runs/run-1/jobs-fast-signal-report-2026-05-09-0300.html",
                        "sha256": "report-hash",
                        "category": "reports",
                        "format": "HTML",
                        "display_name": "Jobs Fast Signal Report",
                        "display_path": "Reports/jobs-fast-signal-report-2026-05-09-0300.html",
                    },
                ],
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        run = snapshot["runs"][0]
        report = run["report_artifact"]
        snapshot_text = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("manifest", run)
        self.assertEqual(run["review_card_count"], 4)
        self.assertEqual(run["alert_count"], 2)
        self.assertEqual(report["display_name"], "Frontend Opportunity Signal Report")
        self.assertEqual(report["display_path"], "Reports/jobs-fast-signal-report-2026-05-09-0300.html")
        self.assertEqual(report["format"], "HTML")
        self.assertNotIn("sha256", report)
        self.assertNotIn("prefiltered-scan.jsonl", snapshot_text)
        self.assertNotIn("scan.meta.json", snapshot_text)
        self.assertNotIn(".tgcs/sources.json", snapshot_text)


    def test_dashboard_runs_prefer_html_report_artifact_for_click_target(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-1",
                "profile_id": "market-news",
                "status": "complete",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "artifacts": [
                    {
                        "type": "report_markdown",
                        "path": "output/runs/run-1/market-news-signal-brief-2026-05-09-0300.md",
                        "display_name": "Market News Signal Brief",
                    },
                    {
                        "type": "report_html",
                        "path": "output/runs/run-1/market-news-signal-brief-2026-05-09-0300.html",
                        "display_name": "Market News Signal Brief",
                    },
                ],
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        report = snapshot["runs"][0]["report_artifact"]
        self.assertEqual(report["type"], "report_html")
        self.assertEqual(report["format"], "HTML")
        self.assertEqual(report["path"], "output/runs/run-1/market-news-signal-brief-2026-05-09-0300.html")


    def test_dashboard_report_artifact_rejects_non_report_paths(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-unsafe",
                "profile_id": "jobs-fast",
                "profile_path": "profiles/templates/jobs.md",
                "status": "complete",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "artifacts": [
                    {"type": "report_html", "path": "C:/Users/Administrator/private/report.html"},
                    {"type": "report_markdown", "path": "output/runs/run-unsafe/../secret-report.md"},
                    {"type": "report_html", "path": "output/runs/run-unsafe/scan.html"},
                    {"type": "raw_scan", "path": "output/runs/run-unsafe/report.html"},
                ],
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertIsNone(snapshot["runs"][0]["report_artifact"])


    def test_dashboard_runs_include_human_profile_display_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profiles" / "market-news.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                '## Report Labels\nreport_title: "Market News Signal Brief"\n',
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            monitor_state.init_db(conn)
            monitor_state.upsert_profile(
                conn,
                {
                    "id": "market-news",
                    "path": str(profile_path),
                    "enabled": True,
                },
            )
            monitor_state.record_run(
                conn,
                {
                    "schema_version": "run_manifest_v1",
                    "run_id": "run-1",
                    "profile_id": "market-news",
                    "profile_path": str(profile_path),
                    "status": "complete",
                    "started_at": "2026-05-09T03:00:00Z",
                    "completed_at": "2026-05-09T03:01:00Z",
                    "artifacts": [],
                },
            )

            snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["runs"][0]["display_name"], "Market News")
        self.assertEqual(snapshot["profiles"][0]["display_name"], "Market News")
        self.assertEqual(snapshot["profiles"][0]["report_display_name"], "Market News Signal Brief")


    def test_dashboard_run_report_artifact_humanizes_legacy_report_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profiles" / "jobs.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                '## Report Labels\nreport_title: "Developer Opportunity Signal Report"\n',
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            monitor_state.init_db(conn)
            monitor_state.record_run(
                conn,
                {
                    "schema_version": "run_manifest_v1",
                    "run_id": "run-legacy",
                    "profile_id": "jobs-fast",
                    "profile_path": str(profile_path),
                    "status": "complete",
                    "started_at": "2026-05-09T03:00:00Z",
                    "completed_at": "2026-05-09T03:01:00Z",
                    "artifacts": [
                        {
                            "type": "report_markdown",
                            "path": "output/runs/run-legacy/report.md",
                        },
                    ],
                },
            )

            snapshot = monitor_state.dashboard_snapshot(conn)

            report = snapshot["runs"][0]["report_artifact"]
            self.assertEqual(report["display_name"], "Developer Opportunity Signal Report")
            self.assertEqual(report["display_path"], "Reports/Developer Opportunity Signal Report.md")
            self.assertEqual(report["format"], "Markdown")


    def test_dashboard_run_report_artifact_preserves_manual_report_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profiles" / "market-news.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                '## Report Labels\nreport_title: "Market News Signal Brief"\n',
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            monitor_state.init_db(conn)
            monitor_state.record_run(
                conn,
                {
                    "schema_version": "run_manifest_v1",
                    "run_id": "run-manual",
                    "profile_id": "market-news",
                    "profile_path": str(profile_path),
                    "status": "complete",
                    "started_at": "2026-05-09T03:00:00Z",
                    "completed_at": "2026-05-09T03:01:00Z",
                    "artifacts": [
                        {
                            "type": "report_html",
                            "path": "output/runs/run-manual/report.html",
                        },
                    ],
                },
            )

            snapshot = monitor_state.dashboard_snapshot(conn)

            report = snapshot["runs"][0]["report_artifact"]
            self.assertEqual(report["display_name"], "Market News Signal Brief")
            self.assertEqual(report["display_path"], "Reports/Market News Signal Brief.html")
            self.assertEqual(report["format"], "HTML")


    def test_dashboard_run_quality_prefers_failure_diagnostic_for_top_code(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "source_topics": ["jobs"],
            },
        )
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-failed-source",
                "profile_id": "jobs-fast",
                "status": "failed",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "diagnostics": [
                    {
                        "code": "scan_incomplete",
                        "severity": "warning",
                        "message": "One channel may be incomplete.",
                    },
                    {
                        "code": "channel_failures",
                        "severity": "failure",
                        "message": "No accessible source produced messages.",
                    },
                ],
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        quality = snapshot["runs"][0]["quality"]
        self.assertEqual(quality["top_diagnostic_code"], "channel_failures")
        self.assertEqual(snapshot["setup_status"]["stage"], "needs_source_access")
        self.assertIn("Settings > Sources", snapshot["setup_status"]["next_step"])


    def test_dashboard_snapshot_includes_opportunity_summary_top_items(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        profile_path = Path(tmpdir.name) / "jobs.md"
        profile_path.write_text(
            '# Profile\n\n## Report Labels\nreport_title: "Developer Opportunity Signal Report"\n',
            encoding="utf-8",
        )
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": str(profile_path),
                "enabled": True,
            },
        )
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-opportunities",
                "profile_id": "jobs-fast",
                "status": "complete",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "prefilter": {
                    "raw_message_count": 120,
                    "matched_count": 9,
                    "semantic_stage": "report_ran",
                },
                "alert_count": 2,
                "review_card_count": 3,
            },
        )
        monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-opportunities",
            items=[
                {
                    "topic": "Low priority digest",
                    "rating": "low",
                    "why": "General news, no action needed.",
                    "decision_state": {"status": "seen"},
                    "source_message_refs": [{"channel": "noise", "id": 3}],
                },
                {
                    "topic": "TypeScript mini app contract",
                    "rating": "high",
                    "why": "Paid Mini App work with a clear budget.",
                    "decision_state": {"status": "new"},
                    "monitor_freshness": {"freshest_source_at": "2026-05-09T02:45:00Z"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                    "text": "raw telegram text must not leak",
                },
                {
                    "topic": "Backend role changed",
                    "rating": "high",
                    "why": "The deadline and stack changed since last run.",
                    "decision_state": {"status": "changed"},
                    "monitor_freshness": {"freshest_source_at": "2026-05-09T02:30:00Z"},
                    "source_message_refs": [{"channel": "jobs", "id": 2}],
                },
            ],
        )

        snapshot = monitor_state.dashboard_snapshot(conn)
        summary = snapshot["opportunity_summary"]

        self.assertEqual(summary["run_id"], "run-opportunities")
        self.assertEqual(summary["profile_id"], "jobs-fast")
        self.assertEqual(summary["display_name"], "Developer Opportunity")
        self.assertEqual(summary["scanned_count"], 120)
        self.assertEqual(summary["matched_count"], 9)
        self.assertEqual(summary["high_actionable_count"], 2)
        self.assertFalse(summary["all_clear"])
        self.assertEqual(len(summary["top_items"]), 2)
        self.assertEqual(summary["top_items"][0]["title"], "TypeScript mini app contract")
        self.assertEqual(summary["top_items"][0]["decision_status"], "new")
        self.assertEqual(summary["next_action"]["label"], "Review priority cards")
        self.assertIn("2 high-priority", summary["next_action"]["detail"])
        self.assertEqual(summary["decision_counts"]["new"], 1)
        self.assertEqual(summary["decision_counts"]["changed"], 1)
        self.assertEqual(summary["decision_counts"]["seen"], 1)
        self.assertNotIn("Low priority digest", json.dumps(summary, ensure_ascii=False))
        self.assertNotIn("raw telegram text", json.dumps(summary, ensure_ascii=False))

    def test_dashboard_snapshot_excludes_handled_cards_from_opportunity_actions(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-handled",
                "profile_id": "jobs-fast",
                "status": "complete",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "prefilter": {"raw_message_count": 10, "matched_count": 1, "semantic_stage": "report_ran"},
                "review_card_count": 1,
            },
        )
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-handled",
            items=[
                {
                    "topic": "Already dismissed role",
                    "rating": "high",
                    "why": "Initially looked relevant.",
                    "decision_state": {"status": "new"},
                    "source_message_refs": [{"channel": "jobs", "id": 10}],
                },
            ],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="dismissed")

        summary = monitor_state.dashboard_snapshot(conn)["opportunity_summary"]

        self.assertEqual(summary["high_actionable_count"], 0)
        self.assertEqual(summary["top_items"], [])
        self.assertNotEqual(summary["next_action"]["label"], "Review priority cards")

    def test_dashboard_snapshot_marks_opportunity_summary_all_clear(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-clear",
                "profile_id": "jobs-fast",
                "status": "prefilter_no_match",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "prefilter": {
                    "raw_message_count": 80,
                    "matched_count": 0,
                    "semantic_stage": "prefilter_no_match",
                },
                "alert_count": 0,
                "review_card_count": 0,
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)
        summary = snapshot["opportunity_summary"]

        self.assertTrue(summary["all_clear"])
        self.assertEqual(summary["top_items"], [])
        self.assertEqual(summary["scanned_count"], 80)
        self.assertEqual(summary["matched_count"], 0)
        self.assertEqual(summary["next_action"]["label"], "Keep cadence")
        self.assertIn("tgcs schedule print --profile-id jobs-fast", summary["next_action"]["command"])


    def test_opportunity_summary_uses_scan_meta_totals_for_scan_input_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan_meta_path = root / "prefiltered-scan.meta.json"
            scan_meta_path.write_text(
                json.dumps({"total_messages_collected": 12, "source_health": []}),
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            monitor_state.init_db(conn)
            monitor_state.record_run(
                conn,
                {
                    "schema_version": "run_manifest_v1",
                    "run_id": "run-replay",
                    "profile_id": "jobs-fast",
                    "status": "complete",
                    "started_at": "2026-05-09T03:00:00Z",
                    "completed_at": "2026-05-09T03:01:00Z",
                    "prefilter": {
                        "enabled": False,
                        "matched_count": None,
                        "semantic_stage": "bypassed_scan_input",
                        "bypass_reason": "scan_input",
                    },
                    "artifacts": [
                        {
                            "artifact_id": "scan_meta:prefiltered-scan.meta.json",
                            "type": "scan_meta",
                            "path": str(scan_meta_path),
                        }
                    ],
                    "alert_count": 0,
                    "review_card_count": 2,
                },
            )
            monitor_state.upsert_review_cards(
                conn,
                profile_id="jobs-fast",
                run_id="run-replay",
                items=[
                    {"topic": "Recurring A", "rating": "medium", "source_message_refs": [{"channel": "jobs", "id": 1}]},
                    {"topic": "Recurring B", "rating": "low", "source_message_refs": [{"channel": "jobs", "id": 2}]},
                ],
            )

            summary = monitor_state.dashboard_snapshot(conn)["opportunity_summary"]

        self.assertEqual(summary["scanned_count"], 12)
        self.assertEqual(summary["matched_count"], 12)
        self.assertEqual(summary["review_card_count"], 2)


    def test_opportunity_summary_excludes_handled_high_actionable_cards(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-handled",
                "profile_id": "jobs-fast",
                "status": "complete",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "prefilter": {"raw_message_count": 2, "matched_count": 1},
                "alert_count": 0,
                "review_card_count": 1,
            },
        )
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-handled",
            items=[
                {
                    "topic": "Handled high role",
                    "rating": "high",
                    "decision_state": {"status": "new"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")

        summary = monitor_state.dashboard_snapshot(conn)["opportunity_summary"]

        self.assertEqual(summary["high_actionable_count"], 0)
        self.assertEqual(summary["top_items"], [])
        self.assertEqual(summary["next_action"]["label"], "Keep cadence")


    def test_dashboard_snapshot_marks_opportunity_summary_failure_next_action(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-failed",
                "profile_id": "jobs-fast",
                "status": "failed",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "prefilter": {
                    "raw_message_count": 0,
                    "matched_count": 0,
                    "semantic_stage": "scan_failed",
                },
                "alert_count": 0,
                "review_card_count": 0,
                "diagnostics": [
                    {
                        "code": "source_access_failed",
                        "severity": "failure",
                        "message": "No source could be scanned.",
                        "next_step": "Check Telegram login and source list.",
                    }
                ],
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)
        summary = snapshot["opportunity_summary"]

        self.assertEqual(summary["next_action"]["label"], "Fix source access")
        self.assertIn("source_access_failed", summary["next_action"]["detail"])
        self.assertEqual(summary["next_action"]["command"], "tgcs doctor --profile jobs")


    def test_dashboard_snapshot_marks_llm_failure_next_action(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-llm-failed",
                "profile_id": "jobs-fast",
                "status": "failed",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
                "prefilter": {
                    "raw_message_count": 120,
                    "matched_count": 15,
                    "semantic_stage": "report_failed",
                },
                "alert_count": 0,
                "review_card_count": 0,
                "diagnostics": [
                    {
                        "code": "llm_output_truncated",
                        "severity": "failure",
                        "message": "The LLM response ended before complete JSON.",
                        "next_step": "Raise semantic_max_tokens or lower semantic_max_messages.",
                    }
                ],
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)
        summary = snapshot["opportunity_summary"]

        self.assertEqual(summary["next_action"]["label"], "Fix AI matching")
        self.assertIn("llm_output_truncated", summary["next_action"]["detail"])
        self.assertEqual(summary["next_action"]["command"], "")
        self.assertNotEqual(snapshot["setup_status"]["stage"], "needs_source_access")


    def test_dashboard_delivery_targets_include_user_facing_labels(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_delivery_target(
            conn,
            {
                "id": "telegram-bot-default",
                "type": "telegram_bot",
                "enabled": False,
                "chat_id": "123456",
                "bot_token": "secret-token",
            },
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        target = snapshot["delivery_targets"][0]
        self.assertEqual(target["display_name"], "Telegram Bot")
        self.assertEqual(target["status_label"], "Muted")
        self.assertEqual(target["detail"], "Chat connected; delivery is muted.")
        self.assertNotIn("secret-token", json.dumps(target, ensure_ascii=False))


    def test_dashboard_profiles_include_user_facing_display_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            monitor_state.init_db(conn)
            profile_path = Path(tmp) / "profiles" / "templates" / "jobs.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                '# Profile\n\n## Report Labels\nreport_title: "Developer Opportunity Signal Report"\n',
                encoding="utf-8",
            )
            monitor_state.upsert_profile(
                conn,
                {
                    "id": "jobs-fast",
                    "path": str(profile_path),
                    "enabled": True,
                },
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="jobs-fast",
                run_id="run-1",
                items=[
                    {
                        "topic": "Useful role",
                        "rating": "high",
                        "source_message_refs": [{"channel": "jobs", "id": 1}],
                    }
                ],
            )
            with patch.object(monitor_state, "PROJECT_ROOT", Path(tmp)):
                monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="follow_up", note="Prefer remote roles.")
                monitor_state.sync_review_learning_profile_patch_suggestion(
                    conn,
                    profile_id="jobs-fast",
                    profile_path=profile_path,
                )
                conn.commit()
                snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["profiles"][0]["display_path"], "Profiles/jobs.md")
        self.assertEqual(snapshot["profiles"][0]["display_name"], "Developer Opportunity")
        self.assertEqual(snapshot["profiles"][0]["report_display_name"], "Developer Opportunity Signal Report")
        self.assertEqual(snapshot["profile_patch_suggestions"][0]["profile_display_path"], "Profiles/jobs.md")
        self.assertNotIn("path", snapshot["profiles"][0])
        self.assertNotIn("config", snapshot["profiles"][0])
        self.assertNotIn("profile_path", snapshot["profile_patch_suggestions"][0])



if __name__ == "__main__":
    unittest.main()
