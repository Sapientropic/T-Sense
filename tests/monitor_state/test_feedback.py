import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from scripts import monitor_feedback, monitor_state


class MonitorStateFeedbackTests(unittest.TestCase):
    def test_feedback_helpers_stay_available_from_monitor_state_facade(self):
        self.assertIs(monitor_state.clear_feedback_decisions, monitor_feedback.clear_feedback_decisions)
        self.assertIs(monitor_state.export_feedback_entries, monitor_feedback.export_feedback_entries)
        self.assertIs(
            monitor_state.create_feedback_profile_patch_suggestions,
            monitor_feedback.create_feedback_profile_patch_suggestions,
        )
        self.assertIs(monitor_state.record_feedback_export, monitor_feedback.record_feedback_export)
        self.assertIs(monitor_state.latest_feedback_export, monitor_feedback.latest_feedback_export)
        self.assertIs(monitor_state.feedback_summary, monitor_feedback.feedback_summary)
        self.assertIs(monitor_state.validation_summary, monitor_feedback.validation_summary)


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

            with patch.object(monitor_state, "PROJECT_ROOT", Path(tmp)):
                result = monitor_state.create_feedback_profile_patch_suggestions(conn)
                second_result = monitor_state.create_feedback_profile_patch_suggestions(conn)
            patch_row = conn.execute("SELECT * FROM profile_patch_suggestions").fetchone()
            summary = monitor_state.feedback_summary(conn)

        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["existing_count"], 0)
        self.assertEqual(second_result["created_count"], 0)
        self.assertEqual(second_result["existing_count"], 1)
        self.assertIn("Desk feedback tuning", patch_row["note"])
        self.assertIn("Extract the generalized matching patterns", patch_row["note"])
        self.assertNotIn("Kept TypeScript role", patch_row["note"])
        self.assertNotIn("Skipped internship", patch_row["note"])
        self.assertNotIn("Wrong crypto promo", patch_row["note"])
        self.assertIn("## Follow-up Preferences", patch_row["proposed_profile_text"])
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


    def test_feedback_summary_masks_legacy_unsafe_export_path(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.record_feedback_export(
            conn,
            output_path="C:/Users/Administrator/private/review-feedback.jsonl",
            feedback_count=0,
            exported_at="2026-05-10T00:00:01Z",
        )

        summary = monitor_state.feedback_summary(conn)
        rendered = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["last_export_path"], "output/feedback/review-feedback.jsonl")
        self.assertNotIn("Administrator", rendered)
        self.assertNotIn("private", rendered)


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


    def test_follow_up_private_note_rejects_before_feedback_write(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

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

        with self.assertRaisesRegex(monitor_state.MonitorStateError, "cannot include"):
            monitor_state.set_card_action(
                conn,
                card_id=cards[0]["card_id"],
                action="follow_up",
                note="DATABASE_PASSWORD='plain-secret-value'",
            )

        feedback_count = conn.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0]
        patch_count = conn.execute("SELECT COUNT(*) FROM profile_patch_suggestions").fetchone()[0]
        self.assertEqual(feedback_count, 0)
        self.assertEqual(patch_count, 0)
        self.assertEqual(monitor_state.get_review_card(conn, cards[0]["card_id"])["status"], monitor_state.PENDING_STATUS)


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
