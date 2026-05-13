import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts import monitor_state


class MonitorStateReviewCardsAlertsTests(unittest.TestCase):
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


    def test_lifecycle_action_suppresses_alerts_without_feedback_export(self):
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
                    "decision_state": {"status": "new", "semantic_cluster": "role-1"},
                    "monitor_freshness": {"freshest_source_at": "2026-05-08T08:30:00Z"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )

        updated = monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="applied")

        self.assertEqual(updated["opportunity_status"], "applied")
        self.assertIsNotNone(updated["opportunity_updated_at"])
        self.assertEqual(monitor_state.export_feedback_entries(conn), [])
        self.assertEqual(monitor_state.feedback_summary(conn)["exportable_count"], 0)
        self.assertEqual(
            monitor_state.alert_candidates(
                [updated],
                alert_rule={"max_age_minutes": 60},
                now=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            ),
            [],
        )


    def test_reopen_lifecycle_restores_actionable_open_status(self):
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
                    "decision_state": {"status": "new", "semantic_cluster": "role-1"},
                    "monitor_freshness": {"freshest_source_at": "2026-05-08T08:30:00Z"},
                    "source_message_refs": [{"channel": "jobs", "id": 1}],
                }
            ],
        )

        monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="dismissed")
        reopened = monitor_state.set_card_action(conn, card_id=cards[0]["card_id"], action="reopen")

        self.assertEqual(reopened["opportunity_status"], "open")
        self.assertEqual(
            [card["card_id"] for card in monitor_state.alert_candidates([reopened])],
            [cards[0]["card_id"]],
        )


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


    def test_high_new_only_alert_rule_excludes_changed_cards(self):
        now = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)
        cards = [
            {
                "card_id": "new-card",
                "status": "pending",
                "opportunity_status": "open",
                "item": {
                    "rating": "high",
                    "decision_state": {"status": "new"},
                    "monitor_freshness": {"freshest_source_at": now.isoformat().replace("+00:00", "Z")},
                },
            },
            {
                "card_id": "changed-card",
                "status": "pending",
                "opportunity_status": "open",
                "item": {
                    "rating": "high",
                    "decision_state": {"status": "changed"},
                    "monitor_freshness": {"freshest_source_at": now.isoformat().replace("+00:00", "Z")},
                },
            },
        ]

        candidates = monitor_state.alert_candidates(
            cards,
            alert_rule={"name": "high_new_only", "max_age_minutes": 60},
            now=now,
        )

        self.assertEqual([card["card_id"] for card in candidates], ["new-card"])



if __name__ == "__main__":
    unittest.main()
