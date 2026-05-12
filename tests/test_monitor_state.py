import json
import os
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts import monitor_state


class MonitorStateTests(unittest.TestCase):
    def test_init_db_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        monitor_state.init_db(conn)
        monitor_state.init_db(conn)

        row = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (monitor_state.STATE_SCHEMA_VERSION,),
        ).fetchone()
        self.assertIsNotNone(row)

    def test_review_card_dedupe_preserves_handled_status(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        item = {
            "topic": "Exchange outage",
            "rating": "high",
            "decision_state": {"status": "new", "semantic_cluster": "cluster-1"},
            "source_message_refs": [{"channel": "cointelegraph", "id": 1}],
        }

        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="market-news",
            run_id="run-1",
            items=[item],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="market-news",
            run_id="run-2",
            items=[item],
        )

        self.assertEqual(cards[0]["status"], "kept")
        self.assertEqual(cards[0]["last_run_id"], "run-2")
        self.assertEqual(monitor_state.alert_candidates(cards), [])

    def test_review_card_title_uses_role_when_company_is_placeholder(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "company": "Unknown",
                    "role": "AI Engineer",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "ai-role"},
                    "source_message_refs": [{"channel": "jobs", "id": 42}],
                }
            ],
        )

        self.assertEqual(cards[0]["title"], "AI Engineer")

    def test_review_card_report_path_prefers_html_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_md = root / "output" / "runs" / "run-1" / "report.md"
            report_html = report_md.with_suffix(".html")
            report_html.parent.mkdir(parents=True)
            report_md.write_text("# Report\n", encoding="utf-8")
            report_html.write_text("<html>Report</html>", encoding="utf-8")
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            monitor_state.init_db(conn)

            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="market-news",
                run_id="run-1",
                items=[
                    {
                        "topic": "Market event",
                        "rating": "high",
                        "source_message_refs": [{"channel": "news", "id": 1}],
                    }
                ],
                report_path=str(report_md),
            )

        self.assertEqual(cards[0]["report_path"], str(report_html).replace("\\", "/"))

    def test_legacy_unknown_review_card_title_is_recovered_from_item_json(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "company": "Unknown",
                    "role": "AI Engineer",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "legacy-ai-role"},
                    "source_message_refs": [{"channel": "jobs", "id": 42}],
                }
            ],
        )
        conn.execute("UPDATE review_cards SET title = ? WHERE card_id = ?", ("Unknown", cards[0]["card_id"]))
        conn.commit()

        recovered = monitor_state.get_review_card(conn, cards[0]["card_id"])

        self.assertEqual(recovered["title"], "AI Engineer")

    def test_legacy_single_field_review_card_title_is_expanded_from_item_json(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "company": "IREV",
                    "role": "Backend Developer",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "legacy-irev"},
                    "source_message_refs": [{"channel": "jobs", "id": 43}],
                }
            ],
        )
        conn.execute("UPDATE review_cards SET title = ? WHERE card_id = ?", ("IREV", cards[0]["card_id"]))
        conn.commit()

        recovered = monitor_state.get_review_card(conn, cards[0]["card_id"])

        self.assertEqual(recovered["title"], "Backend Developer - IREV")

    def test_review_card_item_sanitizer_strips_raw_media_text_fields(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "Frontend role",
                    "rating": "high",
                    "decision_state": {"status": "new"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                    "text": "raw text should not persist",
                    "caption": "raw caption should not persist",
                    "ocr_text": "raw ocr should not persist",
                    "media_text": "raw media text should not persist",
                }
            ],
        )
        card_text = json.dumps(monitor_state.get_review_card(conn, cards[0]["card_id"]), ensure_ascii=False)
        snapshot_text = json.dumps(monitor_state.dashboard_snapshot(conn), ensure_ascii=False)
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="private note")
        feedback_text = json.dumps(monitor_state.export_feedback_entries(conn), ensure_ascii=False)

        self.assertNotIn("raw text should not persist", card_text)
        self.assertNotIn("raw caption should not persist", card_text)
        self.assertNotIn("raw ocr should not persist", card_text)
        self.assertNotIn("raw media text should not persist", card_text)
        self.assertNotIn("raw text should not persist", snapshot_text)
        self.assertNotIn("raw caption should not persist", snapshot_text)
        self.assertNotIn("raw ocr should not persist", snapshot_text)
        self.assertNotIn("raw media text should not persist", snapshot_text)
        self.assertNotIn("raw caption should not persist", feedback_text)

    def test_alert_candidates_respect_freshness_window(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        fresh_item = {
            "topic": "Fast role",
            "rating": "high",
            "decision_state": {"status": "new", "semantic_cluster": "fresh"},
            "monitor_freshness": {"freshest_source_at": "2026-05-08T08:30:00Z"},
            "source_message_refs": [{"channel": "jobs", "id": 1}],
        }
        stale_item = {
            "topic": "Old role",
            "rating": "high",
            "decision_state": {"status": "new", "semantic_cluster": "stale"},
            "monitor_freshness": {"freshest_source_at": "2026-05-08T07:00:00Z"},
            "source_message_refs": [{"channel": "jobs", "id": 2}],
        }
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[fresh_item, stale_item],
        )

        candidates = monitor_state.alert_candidates(
            cards,
            alert_rule={"max_age_minutes": 60},
            now=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        )

        self.assertEqual([card["title"] for card in candidates], ["Fast role"])

    def test_alert_candidates_can_suppress_cards_already_sent_to_user(self):
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
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "Fast role",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "fresh"},
                    "monitor_freshness": {"freshest_source_at": "2026-05-08T08:30:00Z"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )
        monitor_state.record_alert_event(
            conn,
            run_id="run-1",
            card_id=cards[0]["card_id"],
            profile_id="jobs-fast",
            target_id="telegram-bot-default",
            status="sent",
            payload={"text": "redacted"},
            delivery_attempt={"ok": True, "status": "sent"},
        )

        candidates = monitor_state.alert_candidates(
            cards,
            alert_rule={"max_age_minutes": 60},
            now=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            suppressed_card_ids=monitor_state.sent_alert_card_ids(conn, profile_id="jobs-fast"),
        )

        self.assertEqual(candidates, [])

    def test_dry_run_alert_events_do_not_suppress_future_live_alerts(self):
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
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "Fast role",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "fresh"},
                    "monitor_freshness": {"freshest_source_at": "2026-05-08T08:30:00Z"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
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

        candidates = monitor_state.alert_candidates(
            cards,
            alert_rule={"max_age_minutes": 60},
            now=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            suppressed_card_ids=monitor_state.sent_alert_card_ids(conn, profile_id="jobs-fast"),
        )

        self.assertEqual([card["title"] for card in candidates], ["Fast role"])

    def test_sent_new_alert_does_not_suppress_later_changed_status(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        base_item = {
            "topic": "Fast role",
            "rating": "high",
            "decision_state": {"status": "new", "semantic_cluster": "same-role"},
            "monitor_freshness": {"freshest_source_at": "2026-05-08T08:30:00Z"},
            "source_message_refs": [{"channel": "jobs", "id": 1}],
        }
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[base_item],
        )
        monitor_state.record_alert_event(
            conn,
            run_id="run-1",
            card_id=cards[0]["card_id"],
            profile_id="jobs-fast",
            target_id="telegram-bot-default",
            status="sent",
            payload={"text": "redacted", "decision_status": "new"},
            delivery_attempt={"ok": True, "status": "sent"},
        )
        changed_item = {
            **base_item,
            "decision_state": {"status": "changed", "semantic_cluster": "same-role"},
        }
        changed_cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-2",
            items=[changed_item],
        )

        candidates = monitor_state.alert_candidates(
            changed_cards,
            alert_rule={"max_age_minutes": 60},
            now=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            suppressed_alert_keys=monitor_state.sent_alert_suppression_keys(conn, profile_id="jobs-fast"),
        )

        self.assertEqual([card["decision_status"] for card in candidates], ["changed"])

    def test_sent_new_alert_suppresses_same_new_status(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "Fast role",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "same-role"},
                    "monitor_freshness": {"freshest_source_at": "2026-05-08T08:30:00Z"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )
        monitor_state.record_alert_event(
            conn,
            run_id="run-1",
            card_id=cards[0]["card_id"],
            profile_id="jobs-fast",
            target_id="telegram-bot-default",
            status="sent",
            payload={"text": "redacted", "decision_status": "new"},
            delivery_attempt={"ok": True, "status": "sent"},
        )

        candidates = monitor_state.alert_candidates(
            cards,
            alert_rule={"max_age_minutes": 60},
            now=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            suppressed_alert_keys=monitor_state.sent_alert_suppression_keys(conn, profile_id="jobs-fast"),
        )

        self.assertEqual(candidates, [])

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

    def test_dashboard_snapshot_includes_first_run_setup_status(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        empty_snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(empty_snapshot["setup_status"]["next_step"], "tgcs monitor init-config")
        self.assertFalse(empty_snapshot["setup_status"]["has_profiles"])
        self.assertFalse(empty_snapshot["setup_status"]["has_runs"])
        self.assertEqual(empty_snapshot["setup_status"]["checks"][0]["check_id"], "profiles")
        self.assertEqual(empty_snapshot["setup_status"]["checks"][0]["status"], "active")

        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "alert_schedule_mode": "work_hours",
            },
        )
        profile_snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(
            profile_snapshot["setup_status"]["next_step"],
            "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
        )
        self.assertTrue(profile_snapshot["setup_status"]["has_profiles"])
        self.assertFalse(profile_snapshot["setup_status"]["has_runs"])
        checks = {item["check_id"]: item for item in profile_snapshot["setup_status"]["checks"]}
        self.assertEqual(checks["profiles"]["status"], "done")
        self.assertEqual(checks["first_run"]["status"], "active")
        self.assertEqual(
            checks["first_run"]["command"],
            "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
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
        self.assertIn("Source assistant", snapshot["setup_status"]["next_step"])
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
        self.assertEqual(report["display_name"], "Developer Opportunity Signal Report")
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
        self.assertEqual(summary["next_action"]["label"], "Review action signals")
        self.assertIn("2 high-priority", summary["next_action"]["detail"])
        self.assertEqual(summary["decision_counts"]["new"], 1)
        self.assertEqual(summary["decision_counts"]["changed"], 1)
        self.assertEqual(summary["decision_counts"]["seen"], 1)
        self.assertNotIn("Low priority digest", json.dumps(summary, ensure_ascii=False))
        self.assertNotIn("raw telegram text", json.dumps(summary, ensure_ascii=False))

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

    def test_validation_summary_counts_recent_actions_without_note_bodies(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            profile_path.write_text("# Profile\n", encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "jobs-fast", "path": str(profile_path), "enabled": True},
            )
            monitor_state.record_run(
                conn,
                {
                    "schema_version": "run_manifest_v1",
                    "run_id": "run-recent",
                    "profile_id": "jobs-fast",
                    "status": "complete",
                    "started_at": "2026-05-09T03:00:00Z",
                    "completed_at": "2026-05-09T03:01:00Z",
                    "prefilter": {"raw_message_count": 10, "matched_count": 6},
                    "alert_count": 1,
                    "review_card_count": 3,
                },
            )
            monitor_state.record_run(
                conn,
                {
                    "schema_version": "run_manifest_v1",
                    "run_id": "run-old",
                    "profile_id": "jobs-fast",
                    "status": "complete",
                    "started_at": "2026-04-01T03:00:00Z",
                    "completed_at": "2026-04-01T03:01:00Z",
                    "prefilter": {"raw_message_count": 5, "matched_count": 2},
                    "alert_count": 0,
                    "review_card_count": 1,
                },
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="jobs-fast",
                run_id="run-recent",
                items=[
                    {"topic": "Apply A", "rating": "high", "source_message_refs": [{"channel": "jobs", "id": 1}]},
                    {"topic": "Apply B", "rating": "high", "source_message_refs": [{"channel": "jobs", "id": 2}]},
                    {"topic": "Maybe C", "rating": "medium", "source_message_refs": [{"channel": "jobs", "id": 3}]},
                ],
            )
            monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="private note")
            monitor_state.set_card_action(conn, card_id=cards[1]["card_id"], action="false_positive", note="")
            monitor_state.set_card_action(
                conn,
                card_id=cards[2]["card_id"],
                action="follow_up",
                note="private follow-up note",
                profile_path=profile_path,
            )

            summary = monitor_state.validation_summary(
                conn,
                now=datetime(2026, 5, 9, tzinfo=UTC),
            )

        summary_text = json.dumps(summary, ensure_ascii=False)
        self.assertEqual(summary["runs_count"], 1)
        self.assertEqual(summary["high_card_count"], 2)
        self.assertEqual(summary["action_count"], 3)
        self.assertEqual(summary["by_action"], {"false_positive": 1, "follow_up": 1, "keep": 1})
        self.assertEqual(summary["triage_rate"], 1.0)
        self.assertEqual(summary["next_action"]["label"], "Review preference drafts")
        self.assertNotIn("private note", summary_text)
        self.assertNotIn("private follow-up note", summary_text)

    def test_validation_summary_uses_display_name_in_user_facing_copy(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "schema_version": "run_manifest_v1",
                "run_id": "run-recent",
                "profile_id": "jobs-fast",
                "status": "complete",
                "started_at": "2026-05-09T03:00:00Z",
                "completed_at": "2026-05-09T03:01:00Z",
            },
        )
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-recent",
            items=[{"topic": "Apply A", "rating": "high", "source_message_refs": [{"channel": "jobs", "id": 1}]}],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="")

        summary = monitor_state.validation_summary(conn, now=datetime(2026, 5, 9, tzinfo=UTC))

        self.assertIn("Jobs Fast", summary["next_action"]["detail"])
        self.assertNotIn("jobs-fast", summary["next_action"]["detail"])

    def test_export_feedback_jsonl_entries_reuse_report_feedback_schema_without_notes(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "TypeScript role",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "feedback-1"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="private note")

        entries = monitor_state.export_feedback_entries(conn)

        self.assertEqual(entries[0]["schema_version"], "v1")
        self.assertEqual(entries[0]["profile_label"], "jobs-fast")
        self.assertEqual(entries[0]["source_message_refs"], [{"channel": "jobs", "id": 1}])
        self.assertEqual(entries[0]["feedback"], "keep")
        self.assertEqual(entries[0]["rating"], "high")
        self.assertEqual(entries[0]["decision_status"], "new")
        self.assertEqual(entries[0]["item_title"], "TypeScript role")
        self.assertEqual(entries[0]["note"], "")
        self.assertNotIn("private note", json.dumps(entries, ensure_ascii=False))

    def test_feedback_action_is_idempotent_per_card(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "TypeScript role",
                    "rating": "high",
                    "decision_state": {"status": "new", "semantic_cluster": "feedback-1"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )

        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")

        entries = monitor_state.export_feedback_entries(conn)
        summary = monitor_state.feedback_summary(conn)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["feedback"], "keep")
        self.assertEqual(summary["current_decision_count"], 1)
        self.assertEqual(summary["exportable_count"], 1)
        self.assertEqual(summary["by_action"], {"keep": 1})

    def test_feedback_action_change_replaces_previous_card_decision(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[{"topic": "TypeScript role", "rating": "high", "source_message_refs": [{"channel": "jobs", "id": 1}]}],
        )

        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")
        updated = monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="false_positive")

        entries = monitor_state.export_feedback_entries(conn)
        summary = monitor_state.feedback_summary(conn)

        self.assertEqual(updated["status"], "false_positive")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["feedback"], "false_positive")
        self.assertEqual(summary["by_action"], {"false_positive": 1})

    def test_confirmed_feedback_generates_idempotent_profile_suggestion(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "jobs.md"
            profile_path.write_text("# Jobs profile\n", encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "jobs-fast", "path": str(profile_path), "enabled": True},
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="jobs-fast",
                run_id="run-1",
                items=[
                    {"topic": "Kept TypeScript role", "rating": "high", "source_message_refs": [{"channel": "jobs", "id": 1}]},
                    {"topic": "Skipped internship", "rating": "low", "source_message_refs": [{"channel": "jobs", "id": 2}]},
                    {"topic": "Wrong crypto promo", "rating": "medium", "source_message_refs": [{"channel": "jobs", "id": 3}]},
                ],
            )
            monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")
            monitor_state.set_card_action(conn, card_id=cards[1]["card_id"], action="skip")
            monitor_state.set_card_action(conn, card_id=cards[2]["card_id"], action="false_positive")

            result = monitor_state.create_feedback_profile_patch_suggestions(conn)
            second_result = monitor_state.create_feedback_profile_patch_suggestions(conn)
            patch = conn.execute("SELECT * FROM profile_patch_suggestions").fetchone()
            summary = monitor_state.feedback_summary(conn)

        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["existing_count"], 0)
        self.assertEqual(second_result["created_count"], 0)
        self.assertEqual(second_result["existing_count"], 1)
        self.assertIn("Desk feedback tuning", patch["note"])
        self.assertIn("Extract the generalized matching patterns", patch["note"])
        self.assertNotIn("Kept TypeScript role", patch["note"])
        self.assertNotIn("Skipped internship", patch["note"])
        self.assertNotIn("Wrong crypto promo", patch["note"])
        self.assertIn("## Follow-up Preferences", patch["proposed_profile_text"])
        self.assertEqual(summary["next_action"]["label"], "Apply profile drafts")
        self.assertEqual(summary["next_action"]["target_tab"], "profiles")

    def test_feedback_summary_tracks_changes_since_last_export(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[{"topic": "TypeScript role", "rating": "high", "source_message_refs": [{"channel": "jobs", "id": 1}]}],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")
        conn.execute("UPDATE feedback_events SET created_at = ?", ("2026-05-10T00:00:00Z",))

        monitor_state.record_feedback_export(
            conn,
            output_path="output/feedback/review-feedback.jsonl",
            feedback_count=1,
            exported_at="2026-05-10T00:00:01Z",
        )
        exported_summary = monitor_state.feedback_summary(conn)
        conn.execute("UPDATE feedback_events SET created_at = ?", ("2026-05-10T00:00:02Z",))
        changed_summary = monitor_state.feedback_summary(conn)

        self.assertFalse(exported_summary["changed_since_last_export"])
        self.assertEqual(exported_summary["last_export_path"], "output/feedback/review-feedback.jsonl")
        self.assertTrue(changed_summary["changed_since_last_export"])

    def test_undo_card_feedback_restores_pending_review_state(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[{"topic": "TypeScript role", "rating": "high", "source_message_refs": [{"channel": "jobs", "id": 1}]}],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")

        restored = monitor_state.undo_card_action(conn, card_id=cards[0]["card_id"])

        self.assertEqual(restored["status"], monitor_state.PENDING_STATUS)
        self.assertEqual(monitor_state.export_feedback_entries(conn), [])
        self.assertEqual(monitor_state.feedback_summary(conn)["current_decision_count"], 0)

    def test_clear_feedback_decisions_restores_cards_without_removing_runs(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_run(
            conn,
            {
                "run_id": "run-1",
                "profile_id": "jobs-fast",
                "status": "complete",
                "started_at": "2026-05-10T00:00:00Z",
                "completed_at": "2026-05-10T00:01:00Z",
            },
        )
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {"topic": "Kept role", "rating": "high", "source_message_refs": [{"channel": "jobs", "id": 1}]},
                {"topic": "Skipped role", "rating": "low", "source_message_refs": [{"channel": "jobs", "id": 2}]},
            ],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep")
        monitor_state.set_card_action(conn, card_id=cards[1]["card_id"], action="skip")

        result = monitor_state.clear_feedback_decisions(conn)

        statuses = [
            row["status"]
            for row in conn.execute("SELECT status FROM review_cards ORDER BY title").fetchall()
        ]
        run_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        self.assertEqual(result["cleared_count"], 2)
        self.assertEqual(statuses, [monitor_state.PENDING_STATUS, monitor_state.PENDING_STATUS])
        self.assertEqual(run_count, 1)
        self.assertEqual(monitor_state.export_feedback_entries(conn), [])

    def test_clear_feedback_decisions_keeps_preference_draft_history(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            profile_path.write_text("# Profile\n", encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "jobs-fast", "path": str(profile_path), "enabled": True},
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="jobs-fast",
                run_id="run-1",
                items=[{"topic": "Draft role", "rating": "medium", "source_message_refs": [{"channel": "jobs", "id": 1}]}],
            )
            monitor_state.set_card_action(
                conn,
                card_id=cards[0]["card_id"],
                action="follow_up",
                note="prefer remote TypeScript contracts",
                profile_path=profile_path,
            )

            result = monitor_state.clear_feedback_decisions(conn)

        patch_count = conn.execute("SELECT COUNT(*) FROM profile_patch_suggestions").fetchone()[0]
        self.assertEqual(result["cleared_count"], 1)
        self.assertEqual(patch_count, 1)

    def test_feedback_export_recovers_legacy_placeholder_titles(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "company": "Unknown",
                    "role": "AI Engineer",
                    "rating": "high",
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )
        conn.execute("UPDATE review_cards SET title = ? WHERE card_id = ?", ("Unknown", cards[0]["card_id"]))
        conn.commit()
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="private note")

        entries = monitor_state.export_feedback_entries(conn)

        self.assertEqual(entries[0]["item_title"], "AI Engineer")

    def test_dashboard_snapshot_includes_exportable_feedback_count(self):
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
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id="jobs-fast",
            run_id="run-1",
            items=[
                {
                    "topic": "Kept role",
                    "rating": "high",
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                },
                {
                    "topic": "Follow up role",
                    "rating": "medium",
                    "source_message_refs": [{"channel": "jobs", "id": 2}],
                },
                {
                    "topic": "Skipped role",
                    "rating": "low",
                    "source_message_refs": [{"channel": "jobs", "id": 3}],
                },
                {
                    "topic": "False positive role",
                    "rating": "medium",
                    "source_message_refs": [{"channel": "jobs", "id": 4}],
                },
            ],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="private")
        monitor_state.set_card_action(conn, card_id=cards[1]["card_id"], action="follow_up", note="profile tweak")
        monitor_state.set_card_action(conn, card_id=cards[2]["card_id"], action="skip", note="")
        monitor_state.set_card_action(conn, card_id=cards[3]["card_id"], action="false_positive", note="")

        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["feedback_summary"]["exportable_count"], 3)
        self.assertEqual(snapshot["feedback_summary"]["non_exportable_follow_up_count"], 1)
        self.assertEqual(snapshot["feedback_summary"]["profile_diff_count"], 1)
        self.assertEqual(snapshot["feedback_summary"]["pending_profile_diff_count"], 1)
        self.assertEqual(snapshot["feedback_summary"]["applied_profile_diff_count"], 0)
        self.assertEqual(snapshot["feedback_summary"]["reverted_profile_diff_count"], 0)
        self.assertIn("follow_up becomes preference drafts", snapshot["feedback_summary"]["export_scope_note"])
        self.assertEqual(snapshot["feedback_summary"]["by_action"], {"false_positive": 1, "keep": 1, "skip": 1})
        self.assertEqual(snapshot["feedback_summary"]["by_rating"], {"high": 1, "low": 1, "medium": 1})
        self.assertEqual(snapshot["feedback_summary"]["by_decision_status"], {"unknown": 3})
        self.assertEqual(snapshot["feedback_summary"]["next_action"]["label"], "Apply profile drafts")
        impacts = {item["item_title"]: item for item in snapshot["feedback_summary"]["recent_impacts"]}
        self.assertEqual(impacts["Kept role"]["impact_type"], "profile_tuning_source")
        self.assertEqual(impacts["Kept role"]["impact_status"], "ready")
        self.assertEqual(impacts["Kept role"]["impact_label"], "Ready for profile draft")
        self.assertEqual(impacts["Follow up role"]["impact_type"], "profile_diff")
        self.assertEqual(impacts["Follow up role"]["impact_status"], "pending")
        self.assertEqual(impacts["Follow up role"]["impact_label"], "Preference draft pending")
        self.assertNotIn("profile tweak", json.dumps(snapshot["feedback_summary"], ensure_ascii=False))

    def test_dashboard_feedback_export_copy_is_user_facing(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
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
                    "decision_state": {"status": "new"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )
        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="keep", note="")

        snapshot = monitor_state.dashboard_snapshot(conn)

        feedback_json = json.dumps(snapshot["feedback_summary"], ensure_ascii=False)
        self.assertEqual(snapshot["feedback_summary"]["next_action"]["label"], "Generate profile suggestions")
        self.assertNotIn("decision-memory import", feedback_json)
        self.assertNotIn("note-free", feedback_json)
        self.assertIn("profile drafts", snapshot["feedback_summary"]["next_action"]["detail"])
        self.assertEqual(snapshot["feedback_summary"]["recent_impacts"][0]["impact_label"], "Ready for profile draft")
        self.assertIn("future reports learn", snapshot["feedback_summary"]["recent_impacts"][0]["impact_detail"])

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
            monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="follow_up", note="Prefer remote roles.")

            snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(snapshot["profiles"][0]["display_path"], "Profiles/jobs.md")
        self.assertEqual(snapshot["profiles"][0]["display_name"], "Developer Opportunity")
        self.assertEqual(snapshot["profiles"][0]["report_display_name"], "Developer Opportunity Signal Report")
        self.assertEqual(snapshot["profile_patch_suggestions"][0]["profile_display_path"], "Profiles/jobs.md")
        self.assertNotIn("path", snapshot["profiles"][0])
        self.assertNotIn("config", snapshot["profiles"][0])
        self.assertNotIn("profile_path", snapshot["profile_patch_suggestions"][0])

    def test_profile_alert_mode_update_persists_dashboard_override(self):
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

        profile = monitor_state.update_profile_alert_mode(conn, profile_id="jobs-fast", mode="muted")
        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(profile["config"]["alert_schedule_mode"], "muted")
        self.assertEqual(snapshot["profiles"][0]["alert_schedule_mode"], "muted")
        self.assertNotIn("config", snapshot["profiles"][0])

    def test_profile_enabled_update_persists_dashboard_override(self):
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

        profile = monitor_state.update_profile_enabled(conn, profile_id="jobs-fast", enabled=False)
        overridden = monitor_state.apply_profile_runtime_overrides(
            conn,
            {"id": "jobs-fast", "path": "profiles/templates/jobs.md", "enabled": True},
        )
        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertFalse(profile["enabled"])
        self.assertFalse(overridden["enabled"])
        self.assertFalse(snapshot["profiles"][0]["enabled"])
        self.assertEqual(profile["config"]["enabled"], False)
        self.assertNotIn("config", snapshot["profiles"][0])

    def test_profile_runtime_settings_update_persists_dashboard_override(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
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

        profile = monitor_state.update_profile_runtime_settings(
            conn,
            profile_id="jobs-fast",
            settings={"scan_window_hours": 6, "semantic_max_messages": 40},
        )
        overridden = monitor_state.apply_profile_runtime_overrides(
            conn,
            {"id": "jobs-fast", "path": "profiles/templates/jobs.md", "scan_window_hours": 2, "semantic_max_messages": 20},
        )
        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(profile["config"]["scan_window_hours"], 6)
        self.assertEqual(profile["config"]["semantic_max_messages"], 40)
        self.assertEqual(overridden["scan_window_hours"], 6)
        self.assertEqual(overridden["semantic_max_messages"], 40)
        self.assertEqual(snapshot["profiles"][0]["scan_window_hours"], 6)
        self.assertEqual(snapshot["profiles"][0]["semantic_max_messages"], 40)
        self.assertNotIn("config", snapshot["profiles"][0])

    def test_profile_runtime_settings_rejects_invalid_values(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {"id": "jobs-fast", "path": "profiles/templates/jobs.md", "enabled": True},
        )

        invalid_settings = [
            {"scan_window_hours": 0},
            {"scan_window_hours": 169},
            {"semantic_max_messages": 0},
            {"semantic_max_messages": 501},
            {"scan_window_hours": True},
            {"command": "tgcs monitor run"},
        ]
        for settings in invalid_settings:
            with self.subTest(settings=settings):
                with self.assertRaises(monitor_state.MonitorStateError):
                    monitor_state.update_profile_runtime_settings(conn, profile_id="jobs-fast", settings=settings)

    def test_follow_up_patch_can_apply_to_profile_file(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            profile_path.write_text("# Profile\n\n## Search Rules\n1. Keep useful items.\n", encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "market-news", "path": str(profile_path), "enabled": True},
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="market-news",
                run_id="run-1",
                items=[
                    {
                        "topic": "New rule",
                        "rating": "high",
                        "decision_state": {"status": "new"},
                        "source_message_refs": [{"channel": "source", "id": 1}],
                    }
                ],
            )
            card = monitor_state.set_card_action(
                conn,
                card_id=cards[0]["card_id"],
                action="follow_up",
                note="Prefer official incident updates.",
                profile_path=profile_path,
            )
            patch = card["profile_patch_suggestion"]
            result = monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"])

            self.assertEqual(result["status"], "applied")
            self.assertIn("## Follow-up Preferences", profile_path.read_text(encoding="utf-8"))
            self.assertIn("Prefer official incident updates.", profile_path.read_text(encoding="utf-8"))

    def test_apply_profile_patch_refuses_when_profile_changed_after_suggestion(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            original = "# Profile\n\n## Search Rules\n1. Keep useful items.\n"
            profile_path.write_text(original, encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "market-news", "path": str(profile_path), "enabled": True},
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="market-news",
                run_id="run-1",
                items=[
                    {
                        "topic": "New rule",
                        "rating": "high",
                        "decision_state": {"status": "new"},
                        "source_message_refs": [{"channel": "source", "id": 1}],
                    }
                ],
            )
            card = monitor_state.set_card_action(
                conn,
                card_id=cards[0]["card_id"],
                action="follow_up",
                note="Prefer official incident updates.",
                profile_path=profile_path,
            )
            patch = card["profile_patch_suggestion"]
            manually_edited = original + "\nManual edit before apply.\n"
            profile_path.write_text(manually_edited, encoding="utf-8")

            with self.assertRaisesRegex(monitor_state.MonitorStateError, "Profile changed after patch was suggested"):
                monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"])
            remaining_text = profile_path.read_text(encoding="utf-8")

        self.assertEqual(remaining_text, manually_edited)
        self.assertEqual(
            conn.execute(
                "SELECT status FROM profile_patch_suggestions WHERE patch_id = ?",
                (patch["patch_id"],),
            ).fetchone()[0],
            "pending",
        )

    def test_applied_profile_patch_can_revert_to_snapshot_when_file_unchanged(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            original = "# Profile\n\n## Search Rules\n1. Keep useful items.\n"
            profile_path.write_text(original, encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "market-news", "path": str(profile_path), "enabled": True},
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="market-news",
                run_id="run-1",
                items=[
                    {
                        "topic": "New rule",
                        "rating": "high",
                        "decision_state": {"status": "new"},
                        "source_message_refs": [{"channel": "source", "id": 1}],
                    }
                ],
            )
            card = monitor_state.set_card_action(
                conn,
                card_id=cards[0]["card_id"],
                action="follow_up",
                note="Prefer official incident updates.",
                profile_path=profile_path,
            )
            patch = card["profile_patch_suggestion"]
            monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"])

            result = monitor_state.revert_profile_patch(conn, patch_id=patch["patch_id"])
            reverted_text = profile_path.read_text(encoding="utf-8")

        self.assertEqual(result["status"], "reverted")
        self.assertEqual(reverted_text, original)
        self.assertEqual(
            conn.execute(
                "SELECT status FROM profile_patch_suggestions WHERE patch_id = ?",
                (patch["patch_id"],),
            ).fetchone()[0],
            "reverted",
        )

    def test_revert_profile_patch_refuses_when_profile_changed_after_apply(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            profile_path.write_text("# Profile\n", encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "market-news", "path": str(profile_path), "enabled": True},
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="market-news",
                run_id="run-1",
                items=[
                    {
                        "topic": "New rule",
                        "rating": "high",
                        "decision_state": {"status": "new"},
                        "source_message_refs": [{"channel": "source", "id": 1}],
                    }
                ],
            )
            card = monitor_state.set_card_action(
                conn,
                card_id=cards[0]["card_id"],
                action="follow_up",
                note="Prefer official incident updates.",
                profile_path=profile_path,
            )
            patch = card["profile_patch_suggestion"]
            monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"])
            manually_edited = profile_path.read_text(encoding="utf-8") + "\nManual edit.\n"
            profile_path.write_text(manually_edited, encoding="utf-8")

            with self.assertRaisesRegex(monitor_state.MonitorStateError, "Profile changed after patch was applied"):
                monitor_state.revert_profile_patch(conn, patch_id=patch["patch_id"])
            remaining_text = profile_path.read_text(encoding="utf-8")

        self.assertEqual(remaining_text, manually_edited)
        self.assertEqual(
            conn.execute(
                "SELECT status FROM profile_patch_suggestions WHERE patch_id = ?",
                (patch["patch_id"],),
            ).fetchone()[0],
            "applied",
        )

    def test_dashboard_profile_patch_projection_includes_card_context(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            profile_path.write_text("# Profile\n", encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "jobs-fast", "path": str(profile_path), "enabled": True},
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="jobs-fast",
                run_id="run-1",
                items=[
                    {
                        "company": "Unknown",
                        "role": "AI Engineer",
                        "rating": "high",
                        "source_message_refs": [{"channel": "jobs", "id": 1}],
                    }
                ],
            )
            monitor_state.set_card_action(
                conn,
                card_id=cards[0]["card_id"],
                action="follow_up",
                note="Prefer roles with explicit frontend ownership.",
                profile_path=profile_path,
            )

            snapshot = monitor_state.dashboard_snapshot(conn)
            profile_path.write_text("# Profile\n\nManual edit after suggestion.\n", encoding="utf-8")
            changed_snapshot = monitor_state.dashboard_snapshot(conn)

        patch = snapshot["profile_patch_suggestions"][0]
        self.assertEqual(patch["profile_display_path"], "Profiles/profile.md")
        self.assertNotIn("profile_path", patch)
        self.assertEqual(patch["card_title"], "AI Engineer")
        self.assertEqual(patch["card_id"], cards[0]["card_id"])
        self.assertEqual(patch["apply_readiness"]["status"], "ready")
        self.assertEqual(patch["apply_readiness"]["label"], "Safe to apply")
        self.assertEqual(len(patch["base_profile_short_hash"]), 12)

        changed_patch = changed_snapshot["profile_patch_suggestions"][0]
        self.assertEqual(changed_patch["apply_readiness"]["status"], "blocked")
        self.assertIn("changed since this diff was suggested", changed_patch["apply_readiness"]["detail"])

    def test_follow_up_requires_a_non_empty_note(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            profile_path.write_text("# Profile\n", encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "market-news", "path": str(profile_path), "enabled": True},
            )
            cards = monitor_state.upsert_review_cards(
                conn,
                profile_id="market-news",
                run_id="run-1",
                items=[
                    {
                        "topic": "New rule",
                        "rating": "high",
                        "decision_state": {"status": "new"},
                        "source_message_refs": [{"channel": "source", "id": 1}],
                    }
                ],
            )

            with self.assertRaisesRegex(monitor_state.MonitorStateError, "Follow-up note is required"):
                monitor_state.set_card_action(
                    conn,
                    card_id=cards[0]["card_id"],
                    action="follow_up",
                    note="   ",
                    profile_path=profile_path,
                )

            recovered = monitor_state.get_review_card(conn, cards[0]["card_id"])
            self.assertEqual(recovered["status"], "pending")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM profile_patch_suggestions").fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
