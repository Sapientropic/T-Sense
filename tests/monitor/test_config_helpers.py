import inspect
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts import monitor, monitor_delivery, monitor_execution, monitor_runner


class MonitorConfigHelperTests(unittest.TestCase):
    def test_delivery_helpers_stay_available_from_monitor_facade(self):
        self.assertIs(monitor.delivery_targets_for_profile, monitor_delivery.delivery_targets_for_profile)
        self.assertIs(monitor.apply_delivery_runtime_overrides, monitor_delivery.apply_delivery_runtime_overrides)
        self.assertIs(monitor.run_delivery, monitor_delivery.run_delivery)

    def test_command_helper_facades_keep_public_signatures(self):
        for helper_name in ("report_command_for_scan_input", "scan_command", "daily_report_command"):
            with self.subTest(helper=helper_name):
                self.assertEqual(
                    str(inspect.signature(getattr(monitor, helper_name))),
                    str(inspect.signature(getattr(monitor_execution, helper_name))),
                )
                self.assertEqual(
                    str(inspect.signature(getattr(monitor_runner, helper_name))),
                    str(inspect.signature(getattr(monitor_execution, helper_name))),
                )

    def test_command_helpers_respect_monitor_facade_project_root_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_file = root / "profiles" / "templates" / "jobs.md"
            profile_file.parent.mkdir(parents=True)
            profile_file.write_text("# Jobs", encoding="utf-8")
            run_dir = root / "output" / "runs" / "run-command"
            state_dir = root / ".tgcs" / "state"

            with patch.object(monitor, "PROJECT_ROOT", root):
                report_cmd = monitor.report_command_for_scan_input(
                    scan_input=root / "scan.jsonl",
                    profile_file=profile_file,
                    run_dir=run_dir,
                    state_dir=state_dir,
                    source_registry=None,
                    items_json=None,
                    profile_id="jobs-fast",
                    run_id="run-command",
                )
                scan_cmd = monitor.scan_command(
                    run_dir=run_dir,
                    source_args=["--source-registry", str(root / ".tgcs" / "sources.json")],
                    hours=2,
                    allow_incomplete=False,
                )
                daily_cmd = monitor.daily_report_command(
                    profile={},
                    profile_file=profile_file,
                    run_dir=run_dir,
                    state_dir=state_dir,
                    source_args=["--source-registry", str(root / ".tgcs" / "sources.json")],
                    hours=2,
                    items_json=None,
                    allow_incomplete=False,
                    profile_id="jobs-fast",
                    run_id="run-command",
                )

        self.assertEqual(Path(report_cmd[1]), root / "scripts" / "report.py")
        self.assertEqual(Path(scan_cmd[1]), root / "scripts" / "scan.py")
        self.assertEqual(Path(daily_cmd[1]), root / "scripts" / "daily_report.py")
        self.assertEqual(monitor_execution.PROJECT_ROOT, root)

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
        self.assertIn("预算", jobs["prefilter_keywords"])
        self.assertNotIn("简历", jobs["prefilter_keywords"])
        self.assertNotIn("接活", jobs["prefilter_keywords"])
        self.assertEqual(jobs["semantic_max_messages"], 40)
        self.assertEqual(jobs["semantic_max_tokens"], 6000)
        self.assertEqual(jobs["scan_concurrency"], 3)
        self.assertEqual(jobs["scan_delay_seconds"], 0.2)
        self.assertEqual(jobs["semantic_batch_size"], 20)
        self.assertEqual(jobs["semantic_concurrency"], 2)

    def test_effective_scan_hours_uses_profile_window_unless_cli_overrides(self):
        self.assertEqual(
            monitor.effective_scan_hours(Namespace(hours=None), {"scan_window_hours": 2}),
            2,
        )
        self.assertEqual(
            monitor.effective_scan_hours(Namespace(hours=24), {"scan_window_hours": 2}),
            24,
        )

    def test_report_command_uses_human_readable_report_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "runs" / "run_20260509T122524Z_a85fdfaa"
            profile_file = root / "profiles" / "templates" / "jobs.md"
            profile_file.parent.mkdir(parents=True)
            profile_file.write_text(
                '## Report Labels\nreport_title: "Developer Opportunity Signal Report"\n',
                encoding="utf-8",
            )
            cmd = monitor.report_command_for_scan_input(
                scan_input=root / "scan.jsonl",
                profile_file=profile_file,
                run_dir=run_dir,
                state_dir=root / ".tgcs" / "state",
                source_registry=None,
                items_json=None,
                profile_id="jobs-fast",
                run_id="run_20260509T122524Z_a85fdfaa",
            )

        markdown_path = Path(cmd[cmd.index("--output") + 1])
        html_path = Path(cmd[cmd.index("--html-output") + 1])
        self.assertEqual(markdown_path.name, "developer-opportunity-signal-report-2026-05-09-1225.md")
        self.assertEqual(html_path.name, "developer-opportunity-signal-report-2026-05-09-1225.html")

    def test_report_artifact_metadata_has_user_facing_name_and_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "output" / "runs" / "run_20260509T122524Z_a85fdfaa" / "jobs-fast-signal-report-2026-05-09-1225.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            with patch.object(monitor, "PROJECT_ROOT", root):
                artifact = monitor.artifact(
                    report,
                    "report_html",
                    profile_id="jobs-fast",
                    run_id="run_20260509T122524Z_a85fdfaa",
                    report_title="Developer Opportunity Signal Report",
                )

        self.assertEqual(artifact["category"], "reports")
        self.assertEqual(artifact["format"], "HTML")
        self.assertEqual(artifact["display_name"], "Developer Opportunity Signal Report")
        self.assertEqual(artifact["display_path"], "Reports/jobs-fast-signal-report-2026-05-09-1225.html")

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

    def test_live_delivery_attaches_card_actions_to_telegram_alerts(self):
        class FakeAttempt:
            ok = True
            status = "sent"

            @staticmethod
            def to_dict():
                return {"status": "sent"}

        card = {
            "card_id": "card-1",
            "status": "pending",
            "decision_status": "open",
            "item_key": "item-1",
            "item": {
                "topic": "Fast role",
                "rating": "high",
                "decision_state": {"status": "new"},
            },
        }

        with patch.object(monitor_delivery.delivery, "send_telegram_bot_message", return_value=FakeAttempt()) as send_mock:
            with patch.object(monitor_delivery.monitor_state, "record_alert_event", return_value={"status": "sent"}):
                alert_count, events = monitor.run_delivery(
                    conn=None,
                    run_id_value="run-1",
                    profile_id="jobs-fast",
                    cards=[card],
                    targets=[{"id": "telegram-bot-default", "type": "telegram_bot", "enabled": True, "chat_id": "123"}],
                    mode="live",
                    alert_rule={"name": "high_new_or_changed"},
                    delivery_enabled=True,
                    report_path=None,
                    dashboard_url="http://127.0.0.1:8765",
                )

        self.assertEqual(alert_count, 1)
        self.assertEqual(events, [{"status": "sent"}])
        reply_markup = send_mock.call_args.kwargs["reply_markup"]
        rendered = json.dumps(reply_markup, ensure_ascii=False)
        self.assertIn("card:applied:card-1", rendered)
        self.assertIn("card:saved:card-1", rendered)



if __name__ == "__main__":
    unittest.main()
