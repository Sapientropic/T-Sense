import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts import monitor, monitor_state


class MonitorTests(unittest.TestCase):
    def test_default_config_includes_fast_jobs_monitor(self):
        config = monitor.default_config(Path(".tgcs/profiles.toml"))

        jobs = config.profiles["jobs-fast"]

        self.assertEqual(jobs["path"], "profiles/templates/jobs.md")
        self.assertEqual(jobs["work_interval_minutes"], 15)
        self.assertEqual(jobs["scan_window_hours"], 2)
        self.assertEqual(jobs["alert_max_age_minutes"], 60)
        self.assertEqual(jobs["alert_schedule_mode"], "work_hours")
        self.assertEqual(jobs["delivery_targets"], ["telegram-bot-default"])
        self.assertTrue(jobs["prefilter_enabled"])
        self.assertIn("hiring", jobs["prefilter_keywords"])
        self.assertIn("freelance", jobs["prefilter_keywords"])
        self.assertIn("contract", jobs["prefilter_keywords"])
        self.assertIn("mini app", jobs["prefilter_keywords"])
        self.assertIn("ton", jobs["prefilter_keywords"])
        self.assertIn("外包", jobs["prefilter_keywords"])
        self.assertIn("接活", jobs["prefilter_keywords"])
        self.assertIn("预算", jobs["prefilter_keywords"])
        self.assertEqual(jobs["semantic_max_messages"], 20)
        self.assertEqual(jobs["semantic_max_tokens"], 2000)

    def test_effective_scan_hours_uses_profile_window_unless_cli_overrides(self):
        self.assertEqual(
            monitor.effective_scan_hours(Namespace(hours=None), {"scan_window_hours": 2}),
            2,
        )
        self.assertEqual(
            monitor.effective_scan_hours(Namespace(hours=24), {"scan_window_hours": 2}),
            24,
        )

    def test_source_registry_filter_keeps_legacy_untagged_sources_when_topic_filter_would_empty_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "sources.json"
            run_dir = root / "run"
            run_dir.mkdir()
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [
                            {"source_id": "telegram:a", "username": "a", "topics": []},
                            {"source_id": "telegram:b", "username": "b", "topics": []},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            filtered = monitor.filter_source_registry(registry, run_dir, {"source_topics": ["jobs"]})
            payload = json.loads(filtered.read_text(encoding="utf-8"))

        self.assertEqual(len(payload["sources"]), 2)
        self.assertEqual(payload["monitor_filter"]["mode"], "unfiltered_legacy_untagged")

    def test_source_freshness_is_annotated_from_scan_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan = Path(tmp) / "scan.jsonl"
            scan.write_text(
                json.dumps({"channel": "jobs", "id": 1, "date": "2026-05-08T08:30:00Z"}) + "\n",
                encoding="utf-8",
            )

            items = monitor.annotate_items_with_source_freshness(
                [{"topic": "Fast role", "source_message_refs": [{"channel": "jobs", "id": 1}]}],
                scan,
            )

        self.assertEqual(items[0]["monitor_freshness"]["freshest_source_at"], "2026-05-08T08:30:00Z")

    def test_muted_delivery_still_counts_alert_candidate_without_sending(self):
        card = {
            "card_id": "card-1",
            "status": "pending",
            "item": {
                "topic": "Fast role",
                "rating": "high",
                "decision_state": {"status": "new"},
            },
        }

        alert_count, events = monitor.run_delivery(
            conn=None,
            run_id_value="run-1",
            profile_id="jobs-fast",
            cards=[card],
            targets=[{"id": "telegram-bot-default", "type": "telegram_bot", "enabled": True, "chat_id": "123"}],
            mode="dry-run",
            alert_rule={"name": "high_new_or_changed"},
            delivery_enabled=False,
            report_path=None,
            dashboard_url="http://127.0.0.1:8765",
        )

        self.assertEqual(alert_count, 1)
        self.assertEqual(events, [])

    def test_dashboard_alert_mode_override_applies_to_next_monitor_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = root / "profiles" / "templates" / "market-news.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text("# Profile\n\n## Basic Info\n- **Role**: Market\n", encoding="utf-8")
            config_path = root / ".tgcs" / "profiles.toml"
            db_path = root / ".tgcs" / "tgcs.db"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        'schema_version = "profile_run_config_v1"',
                        "",
                        "[[profiles]]",
                        'id = "market-news"',
                        'path = "profiles/templates/market-news.md"',
                        "enabled = true",
                        'alert_schedule_mode = "all_day"',
                        'delivery_targets = ["telegram-bot-default"]',
                        "",
                        "[[delivery]]",
                        'id = "telegram-bot-default"',
                        'type = "telegram_bot"',
                        "enabled = true",
                        'chat_id = "123"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            scan = root / "scan.jsonl"
            scan.write_text(
                json.dumps({"channel": "market", "id": 7, "date": "2026-05-08T08:30:00Z"}) + "\n",
                encoding="utf-8",
            )
            output_dir = root / "output"
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {
                        "id": "market-news",
                        "path": str(profile_path),
                        "enabled": True,
                        "alert_schedule_mode": "muted",
                    },
                )
            finally:
                conn.close()

            def fake_run_json_command(cmd):
                run_dir = output_dir / "runs" / "run-muted"
                report_path = run_dir / "report.md"
                html_path = run_dir / "report.html"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text("# Report", encoding="utf-8")
                html_path.write_text("<html></html>", encoding="utf-8")
                return (
                    0,
                    {
                        "ok": True,
                        "data": {
                            "status": "complete",
                            "report_path": str(report_path),
                            "html_path": str(html_path),
                            "diagnostics": [
                                {
                                    "code": "scan_incomplete",
                                    "severity": "warning",
                                    "message": "One source may be incomplete.",
                                    "next_step": "Rerun with a narrower scan window.",
                                }
                            ],
                            "items": [
                                {
                                    "topic": "Urgent market lead",
                                    "rating": "high",
                                    "why": "Decision relevant.",
                                    "decision_state": {"status": "new", "semantic_cluster": "lead-1"},
                                    "source_message_refs": [{"channel": "market", "id": 7}],
                                }
                            ],
                        },
                    },
                    "",
                )

            stdout = io.StringIO()
            with patch.object(monitor, "PROJECT_ROOT", root):
                with patch.object(monitor, "run_json_command", side_effect=fake_run_json_command):
                    with patch("sys.stdout", stdout):
                        exit_code = monitor.main(
                            [
                                "run",
                                "--profile-id",
                                "market-news",
                                "--run-id",
                                "run-muted",
                                "--config",
                                str(config_path),
                                "--scan-input",
                                str(scan),
                                "--output-dir",
                                str(output_dir),
                                "--db",
                                str(db_path),
                                "--delivery-mode",
                                "dry-run",
                                "--format",
                                "json",
                            ]
                        )

            payload = json.loads(stdout.getvalue())
            manifest = json.loads((output_dir / "runs" / "run-muted" / "run-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["alert_count"], 1)
        self.assertEqual(payload["data"]["delivery_attempts"], [])
        self.assertEqual(manifest["alert_schedule"]["mode"], "muted")
        self.assertFalse(manifest["alert_schedule"]["delivery_enabled"])
        self.assertEqual(manifest["alert_schedule"]["suppressed_reason"], "muted")

    def test_feedback_export_writes_report_reusable_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / ".tgcs" / "tgcs.db"
            output = root / "output" / "dashboard-feedback.jsonl"
            conn = monitor_state.connect(db_path)
            try:
                cards = monitor_state.upsert_review_cards(
                    conn,
                    profile_id="jobs-fast",
                    run_id="run-1",
                    items=[
                        {
                            "topic": "TypeScript role",
                            "rating": "high",
                            "decision_state": {"status": "new", "semantic_cluster": "feedback-cli"},
                            "source_message_refs": [{"channel": "jobs", "id": 1}],
                        }
                    ],
                )
                monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="private note")
            finally:
                conn.close()

            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = monitor.main(
                    [
                        "feedback-export",
                        "--db",
                        str(db_path),
                        "--output",
                        str(output),
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["feedback_count"], 1)
        self.assertEqual(rows[0]["feedback"], "keep")
        self.assertEqual(rows[0]["note"], "")

    def test_prefilter_skips_semantic_stage_without_keyword_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles" / "templates").mkdir(parents=True)
            (root / "profiles" / "templates" / "jobs.md").write_text(
                "# Profile\n\n## Search Rules\n1. Keep jobs.\n",
                encoding="utf-8",
            )
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "sources.json").write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [
                            {
                                "source_id": "telegram:jobs",
                                "username": "jobs",
                                "channel_id": None,
                                "label": "Jobs",
                                "topics": ["jobs"],
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
            output_dir = root / "output"
            db_path = root / ".tgcs" / "tgcs.db"
            calls: list[list[str | Path]] = []

            def fake_run_json_command(cmd):
                calls.append(cmd)
                self.assertIn("scan.py", str(cmd[1]))
                output_path = Path(cmd[cmd.index("--output") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(
                        {
                            "id": 1,
                            "channel": "jobs",
                            "date": "2026-05-08T08:30:00Z",
                            "text": "Unrelated community chat with no role signal.",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                output_path.with_suffix(".meta.json").write_text(
                    json.dumps({"scan_window": "Last 2 hours", "source_health": []}),
                    encoding="utf-8",
                )
                return (
                    0,
                    {
                        "ok": True,
                        "data": {
                            "output_path": str(output_path),
                            "meta_path": str(output_path.with_suffix(".meta.json")),
                            "message_count": 1,
                            "source_health": [],
                        },
                    },
                    "",
                )

            stdout = io.StringIO()
            with patch.object(monitor, "PROJECT_ROOT", root):
                with patch.object(monitor, "run_json_command", side_effect=fake_run_json_command):
                    with patch("sys.stdout", stdout):
                        exit_code = monitor.main(
                            [
                                "run",
                                "--profile-id",
                                "jobs-fast",
                                "--run-id",
                                "run-prefilter",
                                "--output-dir",
                                str(output_dir),
                                "--db",
                                str(db_path),
                                "--format",
                                "json",
                            ]
                        )

            payload = json.loads(stdout.getvalue())
            manifest = json.loads(
                (output_dir / "runs" / "run-prefilter" / "run-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(payload["data"]["status"], "prefilter_no_match")
        self.assertEqual(payload["data"]["review_card_count"], 0)
        self.assertEqual(manifest["prefilter"]["matched_count"], 0)

    def test_scan_failure_manifest_keeps_scan_diagnostics_and_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles" / "templates").mkdir(parents=True)
            (root / "profiles" / "templates" / "jobs.md").write_text("# Jobs", encoding="utf-8")
            registry = root / ".tgcs" / "sources.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [{"source_id": "telegram:missing", "username": "missing", "topics": ["jobs"]}],
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "output"
            db_path = root / ".tgcs" / "tgcs.db"

            def fake_run_json_command(cmd):
                run_dir = output_dir / "runs" / "run-scan-failed"
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "scan.meta.json").write_text(
                    json.dumps(
                        {
                            "total_messages_collected": 0,
                            "failed_channels": ["missing"],
                            "failure_count": 1,
                            "source_health": [
                                {
                                    "channel": "missing",
                                    "failure": "ScanError",
                                    "last_error": "Cannot resolve channel: missing",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                (run_dir / "scan.errors.log").write_text("[missing] Cannot resolve channel", encoding="utf-8")
                return 1, {"ok": False, "error": {"code": "scan_failed"}}, "scan failed"

            stdout = io.StringIO()
            with patch.object(monitor, "PROJECT_ROOT", root):
                with patch.object(monitor, "run_json_command", side_effect=fake_run_json_command):
                    with patch("sys.stdout", stdout):
                        exit_code = monitor.main(
                            [
                                "run",
                                "--profile-id",
                                "jobs-fast",
                                "--run-id",
                                "run-scan-failed",
                                "--output-dir",
                                str(output_dir),
                                "--db",
                                str(db_path),
                                "--delivery-mode",
                                "dry-run",
                                "--format",
                                "json",
                            ]
                        )

            payload = json.loads(stdout.getvalue())
            manifest = json.loads(
                (output_dir / "runs" / "run-scan-failed" / "run-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(manifest["diagnostics"][0]["code"], "channel_failures")
        self.assertIn("no_messages_fetched", {item["code"] for item in manifest["diagnostics"]})
        self.assertIn("scan_meta", {item["type"] for item in manifest["artifacts"]})
        self.assertIn("scan_errors", {item["type"] for item in manifest["artifacts"]})

    def test_prefilter_runs_report_on_keyword_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles" / "templates").mkdir(parents=True)
            (root / "profiles" / "templates" / "jobs.md").write_text(
                "# Profile\n\n## Search Rules\n1. Keep jobs.\n",
                encoding="utf-8",
            )
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "sources.json").write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [
                            {
                                "source_id": "telegram:jobs",
                                "username": "jobs",
                                "topics": ["jobs"],
                                "scan_window_hours": 24,
                                "enabled": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "output"
            db_path = root / ".tgcs" / "tgcs.db"
            calls: list[list[str | Path]] = []

            def fake_run_json_command(cmd):
                calls.append(cmd)
                script = str(cmd[1])
                if "scan.py" in script:
                    output_path = Path(cmd[cmd.index("--output") + 1])
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(
                        json.dumps(
                            {
                                "id": 1,
                                "channel": "jobs",
                                "date": "2026-05-08T08:30:00Z",
                                "text": "We are hiring a TypeScript engineer.",
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    output_path.with_suffix(".meta.json").write_text(
                        json.dumps({"total_messages_collected": 1, "source_health": []}),
                        encoding="utf-8",
                    )
                    return (
                        0,
                        {
                            "ok": True,
                            "data": {
                                "output_path": str(output_path),
                                "message_count": 1,
                                "source_health": [],
                            },
                        },
                        "",
                    )
                self.assertIn("report.py", script)
                scan_input = Path(cmd[cmd.index("--input") + 1])
                self.assertEqual(scan_input.name, "prefiltered-scan.jsonl")
                self.assertEqual(cmd[cmd.index("--max-messages") + 1], "20")
                self.assertEqual(cmd[cmd.index("--max-tokens") + 1], "2000")
                report_path = output_dir / "runs" / "run-prefilter-hit" / "report.md"
                html_path = output_dir / "runs" / "run-prefilter-hit" / "report.html"
                report_path.write_text("# Report", encoding="utf-8")
                html_path.write_text("<html></html>", encoding="utf-8")
                return (
                    0,
                    {
                        "ok": True,
                        "data": {
                            "status": "complete",
                            "report_path": str(report_path),
                            "html_path": str(html_path),
                            "scan_path": str(scan_input),
                            "items": [
                                {
                                    "topic": "TypeScript engineer",
                                    "rating": "high",
                                    "decision_state": {"status": "new"},
                                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                                }
                            ],
                        },
                    },
                    "",
                )

            stdout = io.StringIO()
            with patch.object(monitor, "PROJECT_ROOT", root):
                with patch.object(monitor, "run_json_command", side_effect=fake_run_json_command):
                    with patch("sys.stdout", stdout):
                        exit_code = monitor.main(
                            [
                                "run",
                                "--profile-id",
                                "jobs-fast",
                                "--run-id",
                                "run-prefilter-hit",
                                "--output-dir",
                                str(output_dir),
                                "--db",
                                str(db_path),
                                "--format",
                                "json",
                            ]
                        )

            payload = json.loads(stdout.getvalue())
            manifest = json.loads(
                (output_dir / "runs" / "run-prefilter-hit" / "run-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(payload["data"]["review_card_count"], 1)
        self.assertEqual(manifest["prefilter"]["matched_count"], 1)
        self.assertEqual(manifest["prefilter"]["semantic_stage"], "report_ran")
        self.assertEqual(len(manifest["commands"]), 2)

    def test_monitor_run_with_scan_input_writes_manifest_and_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles" / "templates").mkdir(parents=True)
            (root / "profiles" / "templates" / "market-news.md").write_text(
                "# Profile\n\n## Search Rules\n1. Keep market items.\n",
                encoding="utf-8",
            )
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "sources.json").write_text(
                json.dumps({"schema_version": "source_registry_v1", "sources": []}),
                encoding="utf-8",
            )
            scan = root / "scan.jsonl"
            scan.write_text("{}", encoding="utf-8")
            output_dir = root / "output"
            db_path = root / ".tgcs" / "tgcs.db"
            report_path = output_dir / "runs" / "run-test" / "report.md"
            html_path = output_dir / "runs" / "run-test" / "report.html"

            def fake_run_json_command(cmd):
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text("# Report", encoding="utf-8")
                html_path.write_text("<html></html>", encoding="utf-8")
                return (
                    0,
                    {
                        "ok": True,
                        "data": {
                            "status": "complete",
                            "report_path": str(report_path),
                            "html_path": str(html_path),
                            "diagnostics": [
                                {
                                    "code": "scan_incomplete",
                                    "severity": "warning",
                                    "message": "One source may be incomplete.",
                                    "next_step": "Rerun with a narrower scan window.",
                                }
                            ],
                            "items": [
                                {
                                    "topic": "Exchange outage",
                                    "rating": "high",
                                    "why": "Decision relevant.",
                                    "text": "raw message body",
                                    "decision_state": {
                                        "status": "new",
                                        "semantic_cluster": "cluster-1",
                                    },
                                    "source_message_refs": [{"channel": "cointelegraph", "id": 123}],
                                }
                            ],
                        },
                    },
                    "",
                )

            stdout = io.StringIO()
            with patch.object(monitor, "PROJECT_ROOT", root):
                with patch.object(monitor, "run_json_command", side_effect=fake_run_json_command):
                    with patch("sys.stdout", stdout):
                        exit_code = monitor.main(
                            [
                                "run",
                                "--profile-id",
                                "market-news",
                                "--run-id",
                                "run-test",
                                "--scan-input",
                                str(scan),
                                "--output-dir",
                                str(output_dir),
                                "--db",
                                str(db_path),
                                "--delivery-mode",
                                "dry-run",
                                "--format",
                                "json",
                            ]
                        )

            payload = json.loads(stdout.getvalue())
            manifest = json.loads((output_dir / "runs" / "run-test" / "run-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["review_card_count"], 1)
        self.assertEqual(payload["data"]["alert_count"], 1)
        self.assertEqual(manifest["schema_version"], "run_manifest_v1")
        self.assertEqual(manifest["review_card_count"], 1)
        self.assertEqual(payload["data"]["diagnostics"][0]["code"], "scan_incomplete")
        self.assertEqual(manifest["diagnostics"][0]["code"], "scan_incomplete")

    def test_fast_jobs_scan_input_records_prefilter_bypass_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "profiles" / "templates").mkdir(parents=True)
            (root / "profiles" / "templates" / "jobs.md").write_text(
                "# Profile\n\n## Search Rules\n1. Keep jobs.\n",
                encoding="utf-8",
            )
            scan = root / "scan.jsonl"
            scan.write_text(
                json.dumps(
                    {
                        "id": 1,
                        "channel": "jobs",
                        "date": "2026-05-08T08:30:00Z",
                        "text": "We are hiring a TypeScript engineer.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "output"
            db_path = root / ".tgcs" / "tgcs.db"
            report_path = output_dir / "runs" / "run-scan-input" / "report.md"
            html_path = output_dir / "runs" / "run-scan-input" / "report.html"

            def fake_run_json_command(cmd):
                self.assertIn("report.py", str(cmd[1]))
                self.assertEqual(Path(cmd[cmd.index("--input") + 1]), scan)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text("# Report", encoding="utf-8")
                html_path.write_text("<html></html>", encoding="utf-8")
                return (
                    0,
                    {
                        "ok": True,
                        "data": {
                            "status": "complete",
                            "report_path": str(report_path),
                            "html_path": str(html_path),
                            "scan_path": str(scan),
                            "items": [],
                        },
                    },
                    "",
                )

            with patch.object(monitor, "PROJECT_ROOT", root):
                with patch.object(monitor, "run_json_command", side_effect=fake_run_json_command):
                    exit_code = monitor.main(
                        [
                            "run",
                            "--profile-id",
                            "jobs-fast",
                            "--run-id",
                            "run-scan-input",
                            "--scan-input",
                            str(scan),
                            "--output-dir",
                            str(output_dir),
                            "--db",
                            str(db_path),
                            "--format",
                            "json",
                        ]
                    )

            manifest = json.loads(
                (output_dir / "runs" / "run-scan-input" / "run-manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertFalse(manifest["prefilter"]["enabled"])
        self.assertEqual(manifest["prefilter"]["semantic_stage"], "bypassed_scan_input")
        self.assertEqual(manifest["prefilter"]["bypass_reason"], "scan_input")


if __name__ == "__main__":
    unittest.main()
