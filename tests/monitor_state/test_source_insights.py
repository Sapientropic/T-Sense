import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import monitor_state


class MonitorStateSourceInsightsTests(unittest.TestCase):
    def test_dashboard_snapshot_includes_source_value_stats(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "Senior React",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "a"},
                    "source_message_refs": [{"channel": "jobs_a", "id": 1}],
                },
                {
                    "topic": "Boundary role",
                    "rating": "low",
                    "decision_state": {"status": "new", "semantic_cluster": "b"},
                    "source_message_refs": [{"channel": "jobs_a", "id": 2}],
                },
                {
                    "topic": "Platform role",
                    "rating": "medium",
                    "decision_state": {"status": "new", "semantic_cluster": "c"},
                    "source_message_refs": [{"channel": "jobs_b", "id": 3}],
                },
            ],
        )
        monitor_state.record_alert_event(
            conn,
            run_id="run-1",
            card_id=cards[0]["card_id"],
            profile_id="jobs-fast",
            target_id="telegram-bot-default",
            status="dry_run",
            payload={"text": "redacted"},
            delivery_attempt={"ok": True, "status": "dry_run"},
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["source_stats"][0]["channel"], "jobs_a")
        self.assertEqual(snapshot["source_stats"][0]["card_count"], 2)
        self.assertEqual(snapshot["source_stats"][0]["high_count"], 1)
        self.assertEqual(snapshot["source_stats"][0]["alert_count"], 1)
        self.assertEqual(snapshot["source_stats"][0]["high_rate"], 0.5)


    def test_dashboard_snapshot_merges_latest_scan_yield_into_source_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan_meta_path = root / "scan.meta.json"
            scan_meta_path.write_text(
                json.dumps(
                    {
                        "source_health": [
                            {"channel": "jobs_a", "raw_count": 6, "kept_count": 3},
                            {"channel": "jobs_empty", "raw_count": 5, "kept_count": 0},
                            {
                                "channel": "jobs_failed",
                                "raw_count": 0,
                                "kept_count": 0,
                                "failure": "ChannelPrivateError",
                                "failure_reason": "permission_or_private",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            monitor_state.init_db(conn)
            monitor_state.record_run(
                conn,
                {
                    "run_id": "run-1",
                    "profile_id": "jobs-fast",
                    "status": "complete",
                    "started_at": "2026-05-09T08:00:00Z",
                    "completed_at": "2026-05-09T08:01:00Z",
                    "artifacts": [
                        {
                            "artifact_id": "scan_meta:scan.meta.json",
                            "type": "scan_meta",
                            "path": str(scan_meta_path),
                        }
                    ],
                },
            )
            monitor_state.upsert_review_cards(
                conn,
                profile_id="jobs-fast",
                run_id="run-1",
                items=[
                    {
                        "topic": "Senior React",
                        "rating": "high",
                        "decision_state": {"status": "new", "semantic_cluster": "a"},
                        "source_message_refs": [{"channel": "jobs_a", "id": 1}],
                    }
                ],
            )

            snapshot = monitor_state.dashboard_snapshot(conn)

        sources = {item["channel"]: item for item in snapshot["source_stats"]}
        self.assertEqual(snapshot["source_stats"][0]["channel"], "jobs_failed")
        self.assertTrue(sources["jobs_failed"]["scan_failure"])
        self.assertEqual(sources["jobs_failed"]["scan_failure_reason"], "permission_or_private")
        self.assertEqual(sources["jobs_a"]["raw_count"], 6)
        self.assertEqual(sources["jobs_a"]["kept_count"], 3)
        self.assertEqual(sources["jobs_a"]["latest_card_count"], 1)
        self.assertEqual(sources["jobs_a"]["latest_high_count"], 1)
        self.assertEqual(sources["jobs_a"]["scan_keep_rate"], 0.5)
        self.assertEqual(sources["jobs_a"]["card_yield_rate"], 0.333)
        self.assertEqual(sources["jobs_a"]["latest_run_id"], "run-1")
        self.assertEqual(sources["jobs_empty"]["card_count"], 0)
        self.assertEqual(sources["jobs_empty"]["raw_count"], 5)
        self.assertEqual(sources["jobs_empty"]["kept_count"], 0)


    def test_dashboard_snapshot_enriches_source_ref_links_from_scan_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan_meta_path = root / "scan.meta.json"
            scan_meta_path.write_text(
                json.dumps(
                    {
                        "source_health": [
                            {
                                "source_id": "telegram:1674506295",
                                "channel": "Remocate: релокация, удалёнка, работа и вакансии",
                                "username": None,
                                "channel_id": 1674506295,
                                "label": "1674506295",
                                "raw_count": 3,
                                "kept_count": 2,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            monitor_state.init_db(conn)
            monitor_state.record_run(
                conn,
                {
                    "run_id": "run-1",
                    "profile_id": "jobs-fast",
                    "status": "complete",
                    "started_at": "2026-05-11T14:00:00Z",
                    "completed_at": "2026-05-11T14:01:00Z",
                    "artifacts": [
                        {
                            "artifact_id": "scan_meta:scan.meta.json",
                            "type": "scan_meta",
                            "path": str(scan_meta_path),
                        }
                    ],
                },
            )
            monitor_state.upsert_review_cards(
                conn,
                profile_id="jobs-fast",
                run_id="run-1",
                items=[
                    {
                        "topic": "Senior backend",
                        "rating": "high",
                        "decision_state": {"status": "new", "semantic_cluster": "remocate-backend"},
                        "source_message_refs": [
                            {"channel": "Remocate: релокация, удалёнка, работа и вакансии", "id": 5900}
                        ],
                    }
                ],
            )

            snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["inbox"][0]["source_refs"][0]["url"], "https://t.me/c/1674506295/5900")


    def test_dashboard_snapshot_includes_actionable_source_insights(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "Great TypeScript role",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "promote-1"},
                    "source_message_refs": [{"channel": "jobs_good", "id": 1}],
                },
                {
                    "topic": "Another platform role",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "promote-2"},
                    "source_message_refs": [{"channel": "jobs_good", "id": 2}],
                },
                {
                    "topic": "Generic chatter",
                    "rating": "low",
                    "decision_state": {"status": "new", "semantic_cluster": "cleanup-1"},
                    "source_message_refs": [{"channel": "jobs_noise", "id": 3}],
                },
                {
                    "topic": "Misleading repost",
                    "rating": "low",
                    "decision_state": {"status": "new", "semantic_cluster": "cleanup-2"},
                    "source_message_refs": [{"channel": "jobs_noise", "id": 4}],
                },
                {
                    "topic": "Borderline listing",
                    "rating": "medium",
                    "decision_state": {"status": "new", "semantic_cluster": "watch-1"},
                    "source_message_refs": [{"channel": "jobs_maybe", "id": 5}],
                },
                {
                    "topic": "Low signal role",
                    "rating": "low",
                    "decision_state": {"status": "new", "semantic_cluster": "watch-2"},
                    "source_message_refs": [{"channel": "jobs_maybe", "id": 6}],
                },
            ],
        )
        monitor_state.record_alert_event(
            conn,
            run_id="run-1",
            card_id=cards[0]["card_id"],
            profile_id="jobs-fast",
            target_id="telegram-bot-default",
            status="dry_run",
            payload={"text": "redacted"},
            delivery_attempt={"ok": True, "status": "dry_run"},
        )
        monitor_state.set_card_action(conn, card_id=cards[2]["card_id"], action="false_positive")
        monitor_state.set_card_action(conn, card_id=cards[3]["card_id"], action="false_positive")

        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(
            [(item["channel"], item["kind"]) for item in snapshot["source_insights"]],
            [
                ("jobs_good", "promote"),
                ("jobs_noise", "prune"),
                ("jobs_maybe", "watch"),
            ],
        )
        self.assertIn("2 high", snapshot["source_insights"][0]["reason"])
        self.assertIn("2 false positives", snapshot["source_insights"][1]["reason"])


    def test_source_value_insights_can_reuse_precomputed_stats(self):
        stats = [
            {
                "channel": "jobs_good",
                "card_count": 2,
                "high_count": 2,
                "medium_count": 0,
                "low_count": 0,
                "pending_count": 2,
                "handled_count": 0,
                "false_positive_count": 0,
                "alert_count": 1,
                "high_rate": 1.0,
            }
        ]

        insights = monitor_state.source_value_insights_from_stats(stats)

        self.assertEqual(insights[0]["channel"], "jobs_good")
        self.assertEqual(insights[0]["kind"], "promote")
        self.assertIs(insights[0]["stats"], stats[0])
        self.assertEqual(insights[0]["confidence"], "medium")
        self.assertEqual(insights[0]["next_action"]["label"], "Keep source")


    def test_source_value_insights_marks_single_high_source_as_observe(self):
        stats = [
            {
                "channel": "jobs_new",
                "card_count": 1,
                "high_count": 1,
                "medium_count": 0,
                "low_count": 0,
                "pending_count": 1,
                "handled_count": 0,
                "false_positive_count": 0,
                "alert_count": 0,
                "high_rate": 1.0,
            }
        ]

        insights = monitor_state.source_value_insights_from_stats(stats)

        self.assertEqual(insights[0]["channel"], "jobs_new")
        self.assertEqual(insights[0]["kind"], "observe")
        self.assertEqual(insights[0]["label"], "Observe")
        self.assertEqual(insights[0]["confidence"], "low")
        self.assertEqual(insights[0]["next_action"]["label"], "Need more data")
        self.assertIn("1 high signal", insights[0]["reason"])
        self.assertLess(insights[0]["priority"], 90)


    def test_source_value_insights_marks_fresh_zero_card_source_as_watch(self):
        stats = [
            {
                "channel": "jobs_busy_noise",
                "card_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "pending_count": 0,
                "handled_count": 0,
                "false_positive_count": 0,
                "alert_count": 0,
                "high_rate": 0.0,
                "latest_card_count": 0,
                "latest_high_count": 0,
                "raw_count": 9,
                "kept_count": 7,
                "scan_keep_rate": 0.778,
                "card_yield_rate": 0.0,
            }
        ]

        insights = monitor_state.source_value_insights_from_stats(stats)

        self.assertEqual(insights[0]["channel"], "jobs_busy_noise")
        self.assertEqual(insights[0]["kind"], "watch")
        self.assertEqual(insights[0]["next_action"]["label"], "Tune profile")
        self.assertIn("7 fresh messages", insights[0]["reason"])
        self.assertIn("no review cards", insights[0]["reason"])


    def test_source_value_insights_marks_source_access_failure_as_watch(self):
        stats = [
            {
                "channel": "jobs_private",
                "card_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "pending_count": 0,
                "handled_count": 0,
                "false_positive_count": 0,
                "alert_count": 0,
                "high_rate": 0.0,
                "latest_card_count": 0,
                "latest_high_count": 0,
                "raw_count": 0,
                "kept_count": 0,
                "scan_keep_rate": 0.0,
                "card_yield_rate": 0.0,
                "scan_failure": True,
            }
        ]

        insights = monitor_state.source_value_insights_from_stats(stats)

        self.assertEqual(insights[0]["channel"], "jobs_private")
        self.assertEqual(insights[0]["kind"], "watch")
        self.assertEqual(insights[0]["label"], "Access")
        self.assertEqual(insights[0]["confidence"], "high")
        self.assertEqual(insights[0]["next_action"]["label"], "Fix access")
        self.assertIn("Latest scan failed", insights[0]["reason"])


    def test_dashboard_scan_meta_relative_paths_resolve_from_project_root_when_cwd_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            run_dir = project_root / "output" / "runs" / "run-replay"
            run_dir.mkdir(parents=True)
            (run_dir / "scan.meta.json").write_text(
                json.dumps({"total_messages_collected": 7, "source_health": []}),
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
                    "prefilter": {"semantic_stage": "bypassed_scan_input", "bypass_reason": "scan_input"},
                    "artifacts": [
                        {
                            "artifact_id": "scan_meta:scan.meta.json",
                            "type": "scan_meta",
                            "path": "output/runs/run-replay/scan.meta.json",
                        }
                    ],
                    "alert_count": 0,
                    "review_card_count": 0,
                },
            )
            outside = root / "outside"
            outside.mkdir()

            with patch.object(monitor_state, "PROJECT_ROOT", project_root):
                original_cwd = Path.cwd()
                try:
                    os.chdir(outside)
                    summary = monitor_state.dashboard_snapshot(conn)["opportunity_summary"]
                finally:
                    os.chdir(original_cwd)

        self.assertEqual(summary["scanned_count"], 7)
        self.assertEqual(summary["matched_count"], 7)


    def test_dashboard_source_stats_include_user_facing_channel_names(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "Remote TypeScript role",
                    "rating": "high",
                    "source_message_refs": [{"channel": "jobs_in_it_remoute", "id": 7}],
                }
            ],
        )

        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["source_stats"][0]["channel"], "jobs_in_it_remoute")
        self.assertEqual(snapshot["source_stats"][0]["display_name"], "Jobs In IT Remote")
        self.assertEqual(snapshot["source_insights"][0]["display_name"], "Jobs In IT Remote")
        self.assertEqual(monitor_state.display_channel_name("runello_rus_webdevelopment"), "Runello RU Web Development")



if __name__ == "__main__":
    unittest.main()
