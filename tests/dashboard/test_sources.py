import tempfile
import unittest
import json
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_server, desk_source_assistant, desk_source_registry, desk_sources


class DashboardSourcesTests(unittest.TestCase):
    def test_source_assistant_split_preserves_dashboard_facade_helpers(self):
        self.assertIs(dashboard_server.run_source_assistant, desk_sources.run_source_assistant)
        self.assertIs(dashboard_server.preview_desk_source_import, desk_sources.preview_desk_source_import)
        self.assertEqual(desk_sources._clean_source_topic("Jobs"), desk_source_registry._clean_source_topic("Jobs"))
        self.assertEqual(
            dashboard_server._source_assistant_plan("add @remote_jobs; pause @web3_jobs"),
            desk_source_assistant._source_assistant_plan("add @remote_jobs; pause @web3_jobs"),
        )
        self.assertEqual(
            dashboard_server._clean_resolved_source_plan(
                {"add": ["@remote_jobs"], "remove": ["telegram:old_jobs"], "disable": [], "enable": []}
            ),
            {"add": ["remote_jobs"], "remove": ["telegram:old_jobs"], "disable": [], "enable": []},
        )


    def test_source_registry_split_uses_dashboard_facade_limits_after_split(self):
        with patch.object(dashboard_server, "DESK_SOURCE_IMPORT_MAX_CHANNELS", 1):
            with self.assertRaises(ValueError):
                dashboard_server.preview_desk_source_import(
                    {"sources": "@remote_jobs\n@web3_jobs", "topic": "jobs"}
                )


    def test_source_registry_split_uses_dashboard_facade_projection_helpers_after_split(self):
        with patch.object(dashboard_server, "_utc_now", return_value="2026-05-14T02:00:00Z"):
            with patch.object(dashboard_server, "dashboard_relative_path", return_value="patched/sources.json"):
                result = dashboard_server.preview_desk_source_import({"sources": "@remote_jobs", "topic": "jobs"})

        self.assertEqual(result["finished_at"], "2026-05-14T02:00:00Z")
        self.assertEqual(result["registry_path"], "patched/sources.json")

    def test_desk_source_import_preview_does_not_write_default_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.preview_desk_source_import(
                    {"sources": "@remote_jobs\nhttps://t.me/s/miniapps_jobs\n", "topic": "jobs"}
                )

            registry = root / ".tgcs" / "sources.json"

        self.assertFalse(registry.exists())
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["written"])
        self.assertEqual(result["added_count"], 2)
        self.assertEqual(result["topic"], "jobs")
        self.assertEqual(result["preview_sources"][0]["label"], "remote_jobs")
        self.assertEqual(result["preview_truncated_count"], 0)
        self.assertNotIn(str(root), json.dumps(result, ensure_ascii=False))


    def test_desk_source_import_writes_default_registry_without_accepting_paths_or_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                with self.assertRaises(ValueError):
                    dashboard_server.import_desk_sources(
                        {
                            "sources": "@remote_jobs",
                            "topic": "jobs",
                            "path": "C:/private/sources.json",
                            "command": "tgcs sources import evil.txt",
                        }
                    )
                result = dashboard_server.import_desk_sources({"sources": "@remote_jobs", "topic": "jobs"})

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertTrue(result["written"])
        self.assertEqual(result["added_count"], 1)
        self.assertEqual(result["registry_path"], ".tgcs/sources.json")
        self.assertEqual(payload["sources"][0]["username"], "remote_jobs")
        self.assertEqual(payload["sources"][0]["topics"], ["jobs"])
        self.assertNotIn("tgcs sources import", json.dumps(payload, ensure_ascii=False))


    def test_import_starter_sources_uses_packaged_jobs_list_without_browser_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starter = root / "channel_lists" / "jobs.txt"
            starter.parent.mkdir(parents=True)
            starter.write_text("remote_jobs\nfrontend_jobs\n", encoding="utf-8")
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                with self.assertRaises(ValueError):
                    dashboard_server.import_starter_sources({"topic": "jobs", "path": "private.txt"})
                result = dashboard_server.import_starter_sources({"topic": "jobs"})

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertTrue(result["written"])
        self.assertEqual(result["added_count"], 2)
        self.assertEqual(payload["sources"][0]["topics"], ["jobs"])

    def test_import_starter_sources_uses_topic_specific_market_news_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starter_dir = root / "channel_lists"
            starter_dir.mkdir(parents=True)
            (starter_dir / "jobs.public-candidates.json").write_text(
                json.dumps(
                    {
                        "schema_version": "public_source_candidates_v1",
                        "topic": "jobs",
                        "candidates": [{"handle": "@remote_jobs", "title": "Remote Jobs"}],
                    }
                ),
                encoding="utf-8",
            )
            (starter_dir / "market-news.public-candidates.json").write_text(
                json.dumps(
                    {
                        "schema_version": "public_source_candidates_v1",
                        "topic": "market-news",
                        "candidates": [{"handle": "@market_updates", "title": "Market Updates"}],
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.import_starter_sources({"topic": "market-news"})

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertTrue(result["written"])
        self.assertEqual(result["added_count"], 1)
        self.assertEqual(result["topic"], "market-news")
        self.assertEqual(payload["sources"][0]["username"], "market_updates")
        self.assertEqual(payload["sources"][0]["topics"], ["market-news"])
        self.assertNotIn("remote_jobs", json.dumps(payload, ensure_ascii=False))

    def test_import_starter_sources_skips_packaged_example_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starter = root / "channel_lists" / "jobs.txt"
            starter.parent.mkdir(parents=True)
            starter.write_text("example_remote_jobs\nreal_remote_jobs\n", encoding="utf-8")
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.import_starter_sources({"topic": "jobs"})

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertEqual(result["added_count"], 1)
        self.assertEqual([source["username"] for source in payload["sources"]], ["real_remote_jobs"])


    def test_import_starter_sources_falls_back_to_code_root_from_app_state_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_root = root / "Application Support" / "T-Sense"
            code_root = root / "bundle-code"
            starter = code_root / "channel_lists" / "jobs.txt"
            starter.parent.mkdir(parents=True)
            starter.write_text("remote_jobs\nfrontend_jobs\n", encoding="utf-8")

            with patch.object(dashboard_server, "PROJECT_ROOT", state_root):
                with patch.object(dashboard_server, "CODE_ROOT", code_root, create=True):
                    result = dashboard_server.import_starter_sources({"topic": "jobs"})

            registry = state_root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertTrue(result["written"])
        self.assertEqual(result["added_count"], 2)
        self.assertFalse((state_root / "channel_lists").exists())
        self.assertEqual(payload["sources"][0]["topics"], ["jobs"])


    def test_packaged_jobs_starter_contains_public_recommendations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.import_starter_sources({"topic": "jobs"})

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertGreaterEqual(result["added_count"], 3)
        self.assertEqual(result["source_count"], result["added_count"])
        self.assertTrue(
            all(
                not str(source["username"]).casefold().startswith("example_")
                for source in payload["sources"]
            )
        )
        self.assertTrue(all(source["topics"] == ["jobs"] for source in payload["sources"]))


    def test_packaged_jobs_starter_preserves_public_recommendation_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.import_starter_sources({"topic": "jobs"})
                listed = dashboard_server.desk_sources()

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertGreaterEqual(result["added_count"], 3)
        self.assertEqual(result["preview_sources"][0]["label"], "Remote Front-End Jobs")
        first = payload["sources"][0]
        self.assertEqual(first["label"], "Remote Front-End Jobs")
        self.assertEqual(first["expected_language"], "en")
        self.assertIn("public Telegram page", first["notes"])
        self.assertEqual(listed["sources"][0]["label"], "Remote Front-End Jobs")
        self.assertEqual(listed["sources"][0]["expected_language"], "en")


    def test_import_starter_sources_removes_existing_example_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / ".tgcs" / "sources.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [
                            {
                                "source_id": "telegram:example_remote_jobs",
                                "username": "example_remote_jobs",
                                "channel_id": None,
                                "label": "example_remote_jobs",
                                "topics": ["jobs"],
                                "priority": "normal",
                                "expected_language": "",
                                "scan_window_hours": 24,
                                "enabled": False,
                                "notes": "",
                            },
                            {
                                "source_id": "telegram:kept_real_jobs",
                                "username": "kept_real_jobs",
                                "channel_id": None,
                                "label": "Kept Real Jobs",
                                "topics": ["jobs"],
                                "priority": "normal",
                                "expected_language": "",
                                "scan_window_hours": 24,
                                "enabled": True,
                                "notes": "",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.import_starter_sources({"topic": "jobs"})

            payload = json.loads(registry.read_text(encoding="utf-8"))

        usernames = [source["username"] for source in payload["sources"]]
        self.assertNotIn("example_remote_jobs", usernames)
        self.assertIn("kept_real_jobs", usernames)
        self.assertIn("remote_frontend_jobs", usernames)
        self.assertEqual(result["removed_count"], 1)


    def test_desk_source_import_rejects_non_telegram_like_identifiers(self):
        with self.assertRaises(ValueError):
            dashboard_server.preview_desk_source_import(
                {"sources": "remote_jobs\nnot a channel; rm -rf", "topic": "jobs"}
            )


    def test_desk_source_import_rejects_empty_sources_and_invalid_topic(self):
        with self.assertRaises(ValueError):
            dashboard_server.preview_desk_source_import({"sources": "  \n# only comments", "topic": "jobs"})
        with self.assertRaises(ValueError):
            dashboard_server.preview_desk_source_import({"sources": "remote_jobs", "topic": "../private"})


    def test_desk_source_import_accepts_public_candidate_metadata_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = {
                "schema_version": "public_source_candidates_v1",
                "topic": "jobs",
                "candidates": [
                    {
                        "handle": "@remote_jobs",
                        "url": "https://t.me/remote_jobs",
                        "title": "Remote Jobs",
                        "language": "en",
                        "source_of_recommendation": "public catalog",
                    },
                    {
                        "channel": "frontend_jobs",
                        "notes": "metadata only",
                    },
                ],
            }
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                preview = dashboard_server.preview_desk_source_import(
                    {"sources": json.dumps(candidates), "topic": "jobs"}
                )
                applied = dashboard_server.import_desk_sources({"sources": json.dumps(candidates), "topic": "jobs"})
                listed = dashboard_server.desk_sources()

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertFalse(preview["written"])
        self.assertEqual(preview["added_count"], 2)
        self.assertTrue(applied["written"])
        self.assertEqual([source["username"] for source in payload["sources"]], ["remote_jobs", "frontend_jobs"])
        self.assertEqual(payload["sources"][0]["label"], "Remote Jobs")
        self.assertEqual(payload["sources"][0]["expected_language"], "en")
        self.assertIn("public catalog", payload["sources"][0]["notes"])
        self.assertEqual(payload["sources"][0]["topics"], ["jobs"])
        self.assertEqual(listed["sources"][0]["expected_language"], "en")
        self.assertIn("public catalog", listed["sources"][0]["notes"])


    def test_desk_source_import_rejects_public_candidate_message_bodies(self):
        candidates = {
            "schema_version": "public_source_candidates_v1",
            "candidates": [
                {
                    "handle": "@remote_jobs",
                    "quality_hints": {
                        "raw_text": "raw Telegram post body should not be part of source recommendations"
                    },
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "must not include Telegram message text"):
            dashboard_server.preview_desk_source_import({"sources": json.dumps(candidates), "topic": "jobs"})


    def test_desk_source_import_merges_topic_into_existing_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / ".tgcs" / "sources.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": "source_registry_v1",
                        "sources": [
                            {
                                "source_id": "telegram:remote_jobs",
                                "username": "remote_jobs",
                                "channel_id": None,
                                "label": "remote_jobs",
                                "topics": [],
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

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                result = dashboard_server.import_desk_sources({"sources": "remote_jobs", "topic": "jobs"})
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertEqual(result["added_count"], 0)
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(payload["sources"][0]["topics"], ["jobs"])


    def test_desk_sources_lists_and_toggles_default_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "remote_jobs", "topic": "jobs"})
                listed = dashboard_server.desk_sources()
                updated = dashboard_server.set_desk_source_enabled(
                    "telegram:remote_jobs",
                    {"enabled": False},
                )

        self.assertEqual(listed["source_count"], 1)
        self.assertEqual(listed["enabled_count"], 1)
        self.assertEqual(listed["sources"][0]["label"], "remote_jobs")
        self.assertEqual(updated["enabled_count"], 0)
        self.assertFalse(updated["sources"][0]["enabled"])
        self.assertNotIn(str(root), json.dumps(updated, ensure_ascii=False))


    def test_desk_source_remove_requires_confirmation_and_fixed_source_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "remote_jobs", "topic": "jobs"})
                with self.assertRaises(ValueError):
                    dashboard_server.remove_desk_source("telegram:remote_jobs", {})
                updated = dashboard_server.remove_desk_source("telegram:remote_jobs", {"confirm": True})

        self.assertEqual(updated["source_count"], 0)


    def test_source_assistant_previews_and_applies_add_remove_without_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "old_jobs", "topic": "jobs"})
                with self.assertRaises(ValueError):
                    dashboard_server.run_source_assistant({"instruction": "add @remote_jobs", "command": "rm -rf ."})
                preview = dashboard_server.run_source_assistant(
                    {"instruction": "add @remote_jobs; remove @old_jobs", "topic": "jobs", "dry_run": True}
                )
                applied = dashboard_server.apply_source_assistant_resolved_plan(preview["resolved_plan"], "jobs")
                listed = dashboard_server.desk_sources()

        self.assertTrue(preview["dry_run"])
        self.assertEqual(preview["added_count"], 1)
        self.assertEqual(preview["removed_count"], 1)
        self.assertEqual(preview["resolved_plan"]["add"], ["remote_jobs"])
        self.assertEqual(preview["resolved_plan"]["remove"], ["telegram:old_jobs"])
        self.assertTrue(applied["written"])
        self.assertEqual(listed["source_count"], 1)
        self.assertEqual(listed["sources"][0]["channel"], "remote_jobs")


    def test_source_assistant_uses_ai_only_after_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "old_jobs\nweb3_jobs", "topic": "jobs"})
                with patch.object(
                    dashboard_server,
                    "_source_assistant_llm_plan",
                    return_value={"remove": ["telegram:old_jobs"], "disable": ["telegram:web3_jobs"], "enable": []},
                ) as planner:
                    local_preview = dashboard_server.run_source_assistant(
                        {"instruction": "remove stale sources and pause web3", "topic": "jobs", "dry_run": True}
                    )
                    planner.assert_not_called()
                    ai_preview = dashboard_server.run_source_assistant(
                        {
                            "instruction": "remove stale sources and pause web3",
                            "topic": "jobs",
                            "dry_run": True,
                            "confirm_external_ai": True,
                        }
                    )
                    applied = dashboard_server.run_source_assistant(
                        {
                            "instruction": "remove stale sources and pause web3",
                            "topic": "jobs",
                            "dry_run": False,
                            "confirm_external_ai": True,
                        }
                    )
                listed = dashboard_server.desk_sources()

        self.assertFalse(local_preview["llm_used"])
        self.assertEqual(local_preview["removed_count"], 0)
        self.assertTrue(ai_preview["llm_used"])
        self.assertEqual(ai_preview["removed_count"], 1)
        self.assertEqual(ai_preview["disabled_count"], 1)
        self.assertEqual(ai_preview["resolved_plan"]["remove"], ["telegram:old_jobs"])
        self.assertEqual(ai_preview["resolved_plan"]["disable"], ["telegram:web3_jobs"])
        self.assertTrue(applied["written"])
        self.assertEqual(listed["source_count"], 1)
        self.assertFalse(listed["sources"][0]["enabled"])


    def test_source_assistant_skips_confirmed_ai_when_local_plan_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "old_jobs", "topic": "jobs"})
                with patch.object(
                    dashboard_server,
                    "_source_assistant_llm_plan",
                    return_value={"remove": [], "disable": [], "enable": []},
                ) as planner:
                    preview = dashboard_server.run_source_assistant(
                        {
                            "instruction": "remove @old_jobs",
                            "topic": "jobs",
                            "dry_run": True,
                            "confirm_external_ai": True,
                        }
                    )

        planner.assert_not_called()
        self.assertFalse(preview["llm_used"])
        self.assertEqual(preview["removed_count"], 1)
        self.assertEqual(preview["resolved_plan"]["remove"], ["telegram:old_jobs"])


    def test_source_assistant_uses_confirmed_ai_for_mixed_add_and_existing_source_mentions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "old_jobs\nweb3_jobs", "topic": "jobs"})
                with patch.object(
                    dashboard_server,
                    "_source_assistant_llm_plan",
                    return_value={"remove": ["telegram:old_jobs"], "disable": ["telegram:web3_jobs"], "enable": []},
                ) as planner:
                    preview = dashboard_server.run_source_assistant(
                        {
                            "instruction": "add @remote_jobs; remove stale sources and pause web3",
                            "topic": "jobs",
                            "dry_run": True,
                            "confirm_external_ai": True,
                        }
                    )

        planner.assert_called_once()
        self.assertTrue(preview["llm_used"])
        self.assertEqual(preview["added_count"], 1)
        self.assertEqual(preview["removed_count"], 1)
        self.assertEqual(preview["disabled_count"], 1)
        self.assertEqual(preview["resolved_plan"]["add"], ["remote_jobs"])
        self.assertEqual(preview["resolved_plan"]["remove"], ["telegram:old_jobs"])
        self.assertEqual(preview["resolved_plan"]["disable"], ["telegram:web3_jobs"])


    def test_source_assistant_discovers_all_channels_and_ai_filters_by_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = root / "profiles" / "desk" / "ai-roles.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text("# Senior AI Roles\n\nInclude paid agent engineering roles.\n", encoding="utf-8")
            config_path = root / ".tgcs" / "profiles.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        'schema_version = "profile_run_config_v1"',
                        "",
                        "[[profiles]]",
                        'id = "ai-roles"',
                        'path = "profiles/desk/ai-roles.md"',
                        "enabled = true",
                        'source_topics = ["ai-roles"]',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            discovered = [
                {"channel": "remote_ai_jobs", "label": "Remote AI Jobs", "title": "Remote AI Jobs"},
                {"channel": "coupon_spam", "label": "Coupon Spam", "title": "Daily coupons"},
            ]
            ai_plan = {"add": ["remote_ai_jobs"], "remove": [], "disable": [], "enable": []}
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                with patch.object(dashboard_server.report, "llm_key_available", return_value=True):
                    with patch.object(dashboard_server, "_discover_source_channels", return_value=discovered, create=True) as discover_mock:
                        with patch.object(dashboard_server, "_source_assistant_llm_plan", return_value=ai_plan) as planner:
                            preview = dashboard_server.run_source_assistant(
                                {
                                    "instruction": "scan all Telegram channels for this profile",
                                    "profile_id": "ai-roles",
                                    "topic": "ai-roles",
                                    "dry_run": True,
                                    "confirm_external_ai": True,
                                }
                            )
                            applied = dashboard_server.apply_source_assistant_resolved_plan(preview["resolved_plan"], "ai-roles")

        discover_mock.assert_called_once()
        self.assertEqual(discover_mock.call_args.kwargs.get("folder_name"), "")
        planner.assert_called_once()
        self.assertIn("Senior AI Roles", planner.call_args.kwargs["profile_text"])
        self.assertEqual([item["channel"] for item in planner.call_args.kwargs["candidates"]], ["remote_ai_jobs", "coupon_spam"])
        self.assertTrue(preview["llm_used"])
        self.assertEqual(preview["added_count"], 1)
        self.assertEqual(preview["resolved_plan"]["add"], ["remote_ai_jobs"])
        self.assertTrue(applied["written"])


    def test_source_assistant_discovers_named_telegram_folder_before_ai_filtering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_path = root / "profiles" / "desk" / "ai-roles.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text("# Senior AI Roles\n", encoding="utf-8")
            config_path = root / ".tgcs" / "profiles.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        'schema_version = "profile_run_config_v1"',
                        "",
                        "[[profiles]]",
                        'id = "ai-roles"',
                        'path = "profiles/desk/ai-roles.md"',
                        "enabled = true",
                        'source_topics = ["ai-roles"]',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                with patch.object(dashboard_server.report, "llm_key_available", return_value=True):
                    with patch.object(
                        dashboard_server,
                        "_discover_source_channels",
                        return_value=[{"channel": "ai_folder_jobs", "label": "AI Folder Jobs"}],
                        create=True,
                    ) as discover_mock:
                        with patch.object(
                            dashboard_server,
                            "_source_assistant_llm_plan",
                            return_value={"add": ["ai_folder_jobs"], "remove": [], "disable": [], "enable": []},
                        ):
                            preview = dashboard_server.run_source_assistant(
                                {
                                    "instruction": "use my Jobs folder",
                                    "folder_name": "Jobs",
                                    "profile_id": "ai-roles",
                                    "topic": "ai-roles",
                                    "dry_run": True,
                                    "confirm_external_ai": True,
                                }
                            )

        discover_mock.assert_called_once()
        self.assertEqual(discover_mock.call_args.kwargs.get("folder_name"), "Jobs")
        self.assertEqual(preview["resolved_plan"]["add"], ["ai_folder_jobs"])


    def test_desk_source_topics_updates_default_registry_without_accepting_paths_or_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                dashboard_server.import_desk_sources({"sources": "remote_jobs", "topic": "jobs"})
                with self.assertRaises(ValueError):
                    dashboard_server.set_desk_source_topics(
                        "telegram:remote_jobs",
                        {"topics": ["remote-work"], "path": "C:/private/sources.json"},
                    )
                updated = dashboard_server.set_desk_source_topics(
                    "telegram:remote_jobs",
                    {"topics": ["remote-work", "jobs", "remote-work"]},
                )

            registry = root / ".tgcs" / "sources.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertEqual(updated["topics"], ["jobs", "remote-work"])
        self.assertEqual(updated["sources"][0]["topics"], ["remote-work", "jobs"])
        self.assertEqual(payload["sources"][0]["topics"], ["remote-work", "jobs"])
        self.assertNotIn(str(root), json.dumps(updated, ensure_ascii=False))


    def test_desk_source_topics_rejects_invalid_payloads(self):
        invalid_payloads = [
            {"topics": "jobs"},
            {"topics": []},
            {"topics": ["../private"]},
            {"topics": ["jobs", 123]},
            {"topics": [f"topic{i}" for i in range(9)]},
        ]
        for body in invalid_payloads:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    dashboard_server.set_desk_source_topics("telegram:remote_jobs", body)


    def test_desk_source_enabled_rejects_unexpected_fields(self):
        with self.assertRaises(ValueError):
            dashboard_server.set_desk_source_enabled(
                "telegram:remote_jobs",
                {"enabled": False, "path": "C:/private/sources.json"},
            )


    def test_desk_source_import_http_endpoints_use_specialized_api(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def __init__(self, path):
                self.path = path

            def _read_json_body(self):
                return {"sources": "@remote_jobs", "topic": "jobs"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        endpoint_functions = {
            "/api/desk/sources/preview": "preview_desk_source_import",
            "/api/desk/sources/import": "import_desk_sources",
        }
        for path, function_name in endpoint_functions.items():
            with self.subTest(path=path):
                with patch.object(
                    dashboard_server,
                    function_name,
                    return_value={
                        "schema_version": "desk_source_import_result_v1",
                        "dry_run": path.endswith("preview"),
                        "written": path.endswith("import"),
                        "topic": "jobs",
                        "added_count": 1,
                        "updated_count": 0,
                        "unchanged_count": 0,
                        "source_count": 1,
                        "registry_path": ".tgcs/sources.json",
                        "preview_sources": [{"label": "remote_jobs", "source_id": "telegram:remote_jobs"}],
                        "title": "Sources ready",
                        "detail": "ok",
                        "next_action": "Run source checks.",
                        "finished_at": "2026-05-10T00:00:00Z",
                    },
                ) as action_mock:
                    handler = FakeHandler(path)
                    dashboard_server.DashboardHandler.do_POST(handler)

                action_mock.assert_called_once_with({"sources": "@remote_jobs", "topic": "jobs"})
                self.assertEqual(handler.status, HTTPStatus.OK)
                self.assertEqual(handler.payload["result"]["schema_version"], "desk_source_import_result_v1")


    def test_desk_source_enabled_http_endpoint_uses_specialized_api(self):
        class FakeHandler:
            path = "/api/desk/sources/telegram%3Aremote_jobs/enabled"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"enabled": False}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "set_desk_source_enabled",
            return_value={"schema_version": "desk_sources_v1", "source_count": 1, "enabled_count": 0, "topics": [], "sources": []},
        ) as action_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        action_mock.assert_called_once_with("telegram:remote_jobs", {"enabled": False})
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["sources"]["schema_version"], "desk_sources_v1")


    def test_desk_source_topics_http_endpoint_uses_specialized_api(self):
        class FakeHandler:
            path = "/api/desk/sources/telegram%3Aremote_jobs/topics"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"topics": ["jobs", "remote-work"]}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "set_desk_source_topics",
            return_value={
                "schema_version": "desk_sources_v1",
                "source_count": 1,
                "enabled_count": 1,
                "topics": ["jobs", "remote-work"],
                "sources": [],
            },
        ) as action_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        action_mock.assert_called_once_with("telegram:remote_jobs", {"topics": ["jobs", "remote-work"]})
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["sources"]["schema_version"], "desk_sources_v1")


    def test_desk_source_topics_http_endpoint_rejects_encoded_invalid_source_ids(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def __init__(self, path):
                self.path = path

            def _read_json_body(self):
                return {"topics": ["jobs"]}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        paths = [
            "/api/desk/sources/telegram%3A..%2Fprivate/topics",
            "/api/desk/sources/telegram%3Aremote_jobs%00/topics",
            f"/api/desk/sources/telegram%3A{'a' * 65}/topics",
        ]
        for path in paths:
            with self.subTest(path=path):
                handler = FakeHandler(path)
                dashboard_server.DashboardHandler.do_POST(handler)

                self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                self.assertIn("Source id is not supported", handler.payload["error"])



if __name__ == "__main__":
    unittest.main()
