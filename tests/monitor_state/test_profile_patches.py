import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import monitor_state, profile_patches


class MonitorStateProfilePatchTests(unittest.TestCase):
    def test_profile_patch_helpers_stay_available_from_monitor_state_facade(self):
        self.assertIs(monitor_state.REVIEW_LEARNING_PATCH_NOTE, profile_patches.REVIEW_LEARNING_PATCH_NOTE)
        self.assertIs(monitor_state.create_profile_patch_suggestion, profile_patches.create_profile_patch_suggestion)
        self.assertIs(
            monitor_state.create_profile_preferences_patch_suggestion,
            profile_patches.create_profile_preferences_patch_suggestion,
        )
        self.assertIs(monitor_state.apply_profile_patch, profile_patches.apply_profile_patch)
        self.assertIs(monitor_state.revert_profile_patch, profile_patches.revert_profile_patch)
        self.assertIs(monitor_state.replay_profile_patch, profile_patches.replay_profile_patch)
        self.assertIs(
            monitor_state.sync_review_learning_profile_patch_suggestion,
            profile_patches.sync_review_learning_profile_patch_suggestion,
        )


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
            with patch.object(
                profile_patches,
                "_llm_profile_patch_preference_lines",
                return_value=[
                    "Prioritize official incident update channels.",
                    "Exclude unofficial incident reports unless independently verified.",
                ],
            ) as llm_mock:
                card = monitor_state.set_card_action(
                    conn,
                    card_id=cards[0]["card_id"],
                    action="follow_up",
                    note="Prefer official incident updates.",
                    profile_path=profile_path,
                )
            suggestion = card["profile_patch_suggestion"]
            result = monitor_state.apply_profile_patch(conn, patch_id=suggestion["patch_id"], profile_path=profile_path)

            self.assertEqual(result["status"], "applied")
            profile_text = profile_path.read_text(encoding="utf-8")
            self.assertIn("## Follow-up Preferences", profile_text)
            self.assertIn("Prioritize official incident update channels.", profile_text)
            self.assertNotIn("Prefer official incident updates.", profile_text)
            self.assertNotIn(str(profile_path), suggestion["diff_text"])
            llm_mock.assert_called_once()
            llm_call = llm_mock.call_args.kwargs
            self.assertIn("# Profile", llm_call["profile_text"])
            self.assertEqual(llm_call["note"], profile_patches.REVIEW_LEARNING_PATCH_NOTE)
            self.assertEqual(llm_call["feedback_context"][0]["note"], "Prefer official incident updates.")
            self.assertEqual(llm_call["feedback_context"][0]["title"], "New rule")


    def test_profile_patch_llm_rewrites_raw_note_into_preference_lines(self):
        captured: dict = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=(
                                    '{"preferences":['
                                    '"not full stack",'
                                    '"Exclude full-stack roles; prefer focused frontend, backend, or specialist roles."'
                                    "]}"
                                )
                            )
                        )
                    ],
                    usage={},
                )

        class FakeOpenAI:
            def __init__(self, *, api_key, base_url):
                captured["api_key"] = api_key
                captured["base_url"] = base_url
                self.chat = SimpleNamespace(completions=FakeCompletions())

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test", "TGCS_PROFILE_PATCH_DISABLE_LLM": ""}, clear=False):
            with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}):
                lines = profile_patches._llm_profile_patch_preference_lines(
                    profile_text="# Profile\n\nRole: frontend developer opportunities only.\n",
                    note=profile_patches.REVIEW_LEARNING_PATCH_NOTE,
                    feedback_context=[
                        {
                            "action": "follow_up",
                            "title": "Senior Full Stack Developer",
                            "note": "not full stack",
                            "card": {"role": "Senior Full Stack Developer", "stack": ["TypeScript", "Nuxt"]},
                        }
                    ],
                )

        self.assertEqual(lines, ["Exclude full-stack roles; prefer focused frontend, backend, or specialist roles."])
        self.assertEqual(captured["api_key"], "sk-test")
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        user_payload = json.loads(captured["messages"][1]["content"])
        self.assertIn("frontend developer opportunities only", user_payload["current_profile"])
        self.assertEqual(user_payload["draft_source"], profile_patches.REVIEW_LEARNING_PATCH_NOTE)
        self.assertEqual(user_payload["review_learning_signals"][0]["note"], "not full stack")
        self.assertEqual(user_payload["review_learning_signals"][0]["card"]["role"], "Senior Full Stack Developer")


    def test_distinct_follow_up_notes_batch_into_one_profile_level_draft(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)

        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.md"
            profile_path.write_text(
                "# Profile\n\n## Search Rules\n1. Find frontend developer opportunities.\n",
                encoding="utf-8",
            )
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
                        "company": "Studio A",
                        "role": "Full Stack Developer",
                        "summary": "Own a TypeScript frontend and backend platform.",
                        "rating": "medium",
                        "source_message_refs": [{"channel": "source", "id": 1}],
                    },
                    {
                        "company": "Clideo",
                        "role": "Senior Full Stack Developer (TS/Nuxt, Video Editing)",
                        "summary": "Full-stack SaaS role focused on browser video editing workflows.",
                        "rating": "medium",
                        "source_message_refs": [{"channel": "source", "id": 2}],
                    },
                ],
            )
            llm_calls: list[dict] = []

            def fake_llm_profile_patch(**kwargs):
                llm_calls.append(kwargs)
                if len(kwargs["feedback_context"]) == 1:
                    return ["Exclude full-stack roles; prefer focused frontend roles."]
                return [
                    "Exclude full-stack roles; prefer focused frontend roles aligned with the profile.",
                    "Down-rank video-editing-heavy SaaS roles unless the profile explicitly asks for that domain.",
                ]

            with patch.object(profile_patches, "_llm_profile_patch_preference_lines", side_effect=fake_llm_profile_patch):
                first = monitor_state.set_card_action(
                    conn,
                    card_id=cards[0]["card_id"],
                    action="follow_up",
                    note="not full stack",
                    profile_path=profile_path,
                )["profile_patch_suggestion"]
                second = monitor_state.set_card_action(
                    conn,
                    card_id=cards[1]["card_id"],
                    action="follow_up",
                    note="too much video editing, not my target",
                    profile_path=profile_path,
                )["profile_patch_suggestion"]

            snapshot = monitor_state.dashboard_snapshot(conn)
            feedback_summary = monitor_state.feedback_summary(conn)

        self.assertEqual(first["patch_id"], second["patch_id"])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM profile_patch_suggestions").fetchone()[0], 1)
        patches = snapshot["profile_patch_suggestions"]
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["card_title"], "2 Review choices")
        self.assertEqual(patches[0]["source_card_count"], 2)
        self.assertCountEqual(
            patches[0]["source_card_titles"],
            ["Full Stack Developer - Studio A", "Senior Full Stack Developer (TS/Nuxt, Video Editing) - Clideo"],
        )
        self.assertEqual(patches[0]["note"], profile_patches.REVIEW_LEARNING_PATCH_NOTE)
        self.assertNotIn("not full stack", patches[0]["diff_text"].casefold())
        self.assertNotIn("too much video editing, not my target", patches[0]["diff_text"].casefold())
        self.assertIn("Exclude full-stack roles", patches[0]["diff_text"])
        self.assertIn("Down-rank video-editing-heavy SaaS roles", patches[0]["diff_text"])
        self.assertEqual(len(llm_calls), 2)
        self.assertEqual(llm_calls[-1]["note"], profile_patches.REVIEW_LEARNING_PATCH_NOTE)
        self.assertIn("Find frontend developer opportunities", llm_calls[-1]["profile_text"])
        self.assertCountEqual(
            [item["note"] for item in llm_calls[-1]["feedback_context"]],
            ["not full stack", "too much video editing, not my target"],
        )
        self.assertTrue(
            any(item["card"].get("role") == "Full Stack Developer" for item in llm_calls[-1]["feedback_context"])
        )
        impacts = {item["item_title"]: item for item in feedback_summary["recent_impacts"]}
        self.assertEqual(impacts["Full Stack Developer - Studio A"]["patch_id"], first["patch_id"])
        self.assertEqual(impacts["Senior Full Stack Developer (TS/Nuxt, Video Editing) - Clideo"]["patch_id"], first["patch_id"])
        self.assertEqual(impacts["Senior Full Stack Developer (TS/Nuxt, Video Editing) - Clideo"]["impact_status"], "pending")


    def test_applying_profile_patch_removes_legacy_duplicate_pending_drafts(self):
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
            patch = monitor_state.create_profile_patch_suggestion(
                conn,
                profile_id="market-news",
                card_id=None,
                note="not full stack",
                profile_path=profile_path,
            )
            conn.execute(
                """
                INSERT INTO profile_patch_suggestions(
                    patch_id, profile_id, card_id, note, status, diff_text,
                    proposed_profile_text, base_profile_hash, created_at, applied_at
                )
                SELECT ?, profile_id, card_id, note, status, diff_text,
                       proposed_profile_text, base_profile_hash, created_at, applied_at
                FROM profile_patch_suggestions
                WHERE patch_id = ?
                """,
                ("patch_legacy_duplicate", patch["patch_id"]),
            )
            conn.commit()
            legacy_summary = monitor_state.feedback_summary(conn)

            result = monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)
            snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(legacy_summary["pending_profile_diff_count"], 1)
        self.assertEqual(result["duplicate_draft_count"], 1)
        self.assertEqual(snapshot["profile_patch_suggestions"], [])
        statuses = {
            row["status"]: row["count"]
            for row in conn.execute("SELECT status, COUNT(*) AS count FROM profile_patch_suggestions GROUP BY status").fetchall()
        }
        self.assertEqual(statuses, {"applied": 1})


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


    def test_apply_profile_patch_snapshots_current_file_when_profile_changed_after_suggestion(self):
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

            result = monitor_state.apply_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)
            applied_text = profile_path.read_text(encoding="utf-8")
            monitor_state.revert_profile_patch(conn, patch_id=patch["patch_id"], profile_path=profile_path)
            reverted_text = profile_path.read_text(encoding="utf-8")

        self.assertEqual(result["status"], "applied")
        self.assertIn("Follow-up Preferences", applied_text)
        self.assertEqual(reverted_text, manually_edited)
        self.assertEqual(
            conn.execute(
                "SELECT status FROM profile_patch_suggestions WHERE patch_id = ?",
                (patch["patch_id"],),
            ).fetchone()[0],
            "reverted",
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


    def test_pending_profile_patch_can_clear_without_apply_step(self):
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
            patch = monitor_state.create_profile_patch_suggestion(
                conn,
                profile_id="market-news",
                card_id=None,
                note="Prefer official incident updates.",
                profile_path=profile_path,
            )

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
        self.assertEqual(patch["apply_readiness"]["label"], "Ready")
        self.assertEqual(len(patch["base_profile_short_hash"]), 12)
        self.assertEqual(patch["source_card_count"], 1)
        self.assertEqual(patch["source_card_titles"], ["AI Engineer"])

        changed_patch = changed_snapshot["profile_patch_suggestions"][0]
        self.assertEqual(changed_patch["apply_readiness"]["status"], "ready")
        self.assertNotIn("changed since this diff was suggested", changed_patch["apply_readiness"]["detail"])



if __name__ == "__main__":
    unittest.main()
