import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import monitor_state, profile_patches


class MonitorStateProfilePatchTests(unittest.TestCase):
    def test_profile_patch_helpers_stay_available_from_monitor_state_facade(self):
        self.assertIs(monitor_state.create_profile_patch_suggestion, profile_patches.create_profile_patch_suggestion)
        self.assertIs(
            monitor_state.create_profile_preferences_patch_suggestion,
            profile_patches.create_profile_preferences_patch_suggestion,
        )
        self.assertIs(monitor_state.apply_profile_patch, profile_patches.apply_profile_patch)
        self.assertIs(monitor_state.revert_profile_patch, profile_patches.revert_profile_patch)
        self.assertIs(monitor_state.replay_profile_patch, profile_patches.replay_profile_patch)


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
            result = monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)

            self.assertEqual(result["status"], "applied")
            self.assertIn("## Follow-up Preferences", profile_path.read_text(encoding="utf-8"))
            self.assertIn("Prefer official incident updates.", profile_path.read_text(encoding="utf-8"))
            self.assertNotIn(str(profile_path), patch["diff_text"])


    def test_profile_patch_suggestions_reject_private_fragments(self):
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

            cases = [
                (
                    monitor_state.create_profile_patch_suggestion,
                    {"profile_id": "market-news", "card_id": None, "note": "token=123456:ABCDEF_secret", "profile_path": profile_path},
                ),
                (
                    monitor_state.create_profile_preferences_patch_suggestion,
                    {
                        "profile_id": "market-news",
                        "preferences_text": "Prefer remote work from C:\\Users\\Administrator\\private\\notes",
                    },
                ),
            ]
            for action, kwargs in cases:
                with self.subTest(action=action.__name__):
                    with self.assertRaisesRegex(monitor_state.MonitorStateError, "cannot include"):
                        action(conn, **kwargs)

            patch_count = conn.execute("SELECT COUNT(*) FROM profile_patch_suggestions").fetchone()[0]
            self.assertEqual(patch_count, 0)
            self.assertEqual(profile_path.read_text(encoding="utf-8"), original)


    def test_profile_text_private_fragment_detector_covers_common_dumps(self):
        cases = [
            'MY_SECRET="plain-secret-value"',
            "DATABASE_PASSWORD='plain-secret-value'",
            "ghp_1234567890abcdefABCDEF1234567890abcd",
            "github_pat_1234567890abcdefABCDEF_1234567890abcdefABCDEF123456",
            'argv ["tgcs","scan"]',
            "args=['tgcs','scan']",
            "\\\\server\\share\\secret.txt",
            "/tmp/private/secret.txt",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertIsNotNone(monitor_state.profile_text_private_fragment_reason(text))


    def test_profile_patch_rejects_existing_private_profile_text_before_storing_copy(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            original = "# Profile\n\nOPENAI_API_KEY=sk-localSecret12345\n"
            profile_path.write_text(original, encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "market-news", "path": str(profile_path), "enabled": True},
            )

            with patch.object(monitor_state, "PROJECT_ROOT", Path(tmp)):
                with self.assertRaisesRegex(monitor_state.MonitorStateError, "cannot include"):
                    monitor_state.create_profile_patch_suggestion(
                        conn,
                        profile_id="market-news",
                        card_id=None,
                        note="Prefer official incident updates.",
                        profile_path=profile_path,
                    )
                with self.assertRaisesRegex(monitor_state.MonitorStateError, "cannot include"):
                    monitor_state.create_profile_preferences_patch_suggestion(
                        conn,
                        profile_id="market-news",
                        preferences_text="Prefer official incident updates.",
                    )

            rows = conn.execute("SELECT note, diff_text, proposed_profile_text FROM profile_patch_suggestions").fetchall()
            self.assertEqual(rows, [])
            self.assertEqual(profile_path.read_text(encoding="utf-8"), original)


    def test_dashboard_profile_patch_refuses_db_path_outside_project(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "repo"
            outside_profile = Path(tmp) / "outside" / "profile.md"
            outside_profile.parent.mkdir(parents=True)
            original = "# Profile\n\n## Search Rules\n1. Keep useful items.\n"
            outside_profile.write_text(original, encoding="utf-8")
            monitor_state.upsert_profile(
                conn,
                {"id": "market-news", "path": str(outside_profile), "enabled": True},
            )
            suggestion = monitor_state.create_profile_patch_suggestion(
                conn,
                profile_id="market-news",
                card_id=None,
                note="Prefer official incident updates.",
                profile_path=outside_profile,
            )

            with patch.object(monitor_state, "PROJECT_ROOT", workspace):
                with self.assertRaises(monitor_state.MonitorStateError) as apply_error:
                    monitor_state.apply_profile_patch(conn, patch_id=suggestion["patch_id"])
                with self.assertRaises(monitor_state.MonitorStateError) as draft_error:
                    monitor_state.create_profile_preferences_patch_suggestion(
                        conn,
                        profile_id="market-news",
                        preferences_text="Prefer official incident updates.",
                    )

            self.assertIn("workspace", str(apply_error.exception))
            self.assertIn("workspace", str(draft_error.exception))
            self.assertEqual(outside_profile.read_text(encoding="utf-8"), original)


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
                monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)
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
            monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)

            result = monitor_state.revert_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)
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


    def test_reverted_profile_patch_can_replay_as_new_pending_patch(self):
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
            monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)
            monitor_state.revert_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)

            replay = monitor_state.replay_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)

        self.assertNotEqual(replay["patch_id"], patch["patch_id"])
        self.assertEqual(replay["status"], "pending")
        self.assertEqual(replay["replayed_from_patch_id"], patch["patch_id"])
        self.assertEqual(replay["base_profile_hash"], monitor_state.sha256_text(original))
        statuses = {
            row["patch_id"]: row["status"]
            for row in conn.execute("SELECT patch_id, status FROM profile_patch_suggestions").fetchall()
        }
        self.assertEqual(statuses[patch["patch_id"]], "reverted")
        self.assertEqual(statuses[replay["patch_id"]], "pending")


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
            monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)
            manually_edited = profile_path.read_text(encoding="utf-8") + "\nManual edit.\n"
            profile_path.write_text(manually_edited, encoding="utf-8")

            with self.assertRaisesRegex(monitor_state.MonitorStateError, "Profile changed after patch was applied"):
                monitor_state.revert_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)
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



if __name__ == "__main__":
    unittest.main()
