import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_server, desk_profile_routes, desk_profiles, monitor_state


class DashboardProfileTests(unittest.TestCase):
    def test_profile_creation_helpers_stay_available_from_dashboard_server_facade(self):
        self.assertIs(dashboard_server.create_profile_from_brief, desk_profiles.create_profile_from_brief)
        self.assertIs(dashboard_server._profile_create_input_text, desk_profiles._profile_create_input_text)
        self.assertEqual(dashboard_server.PROFILE_CREATE_MAX_TEXT_LENGTH, desk_profiles.PROFILE_CREATE_MAX_TEXT_LENGTH)

    def test_profile_route_helpers_accept_dashboard_server_patch_paths(self):
        class FakeConnection:
            pass

        conn = FakeConnection()
        with patch.object(
            dashboard_server.monitor_state,
            "update_profile_enabled",
            return_value={"profile_id": "jobs-fast", "enabled": False},
        ) as update_mock:
            payload = desk_profile_routes.profile_enabled_payload(
                conn,
                path="/api/profiles/jobs-fast/enabled",
                body={"enabled": False},
                monitor_state_module=dashboard_server.monitor_state,
                allowed_fields=dashboard_server.PROFILE_ENABLED_ALLOWED_FIELDS,
            )

        update_mock.assert_called_once_with(conn, profile_id="jobs-fast", enabled=False)
        self.assertEqual(payload["profile"]["enabled"], False)

    def test_profile_create_facade_helper_patches_still_affect_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = monitor_state.connect(root / "tgcs.db")
            try:
                ai_payload = {
                    "title": "Patched Profile",
                    "goal": "Monitor patched profile brief.",
                    "search_rules": ["Include matching patched profile signals."],
                    "rejection_rules": ["Reject unrelated signals."],
                    "keywords": ["patched", "profile"],
                    "topic": "patched-profile",
                }
                with patch.object(dashboard_server, "PROJECT_ROOT", root):
                    with patch.object(dashboard_server.report, "llm_key_available", return_value=True):
                        with patch.object(dashboard_server, "_profile_ai_payload_from_text", return_value=ai_payload, create=True) as ai_mock:
                            with patch.object(
                                dashboard_server,
                                "_profile_text_from_base64_file",
                                return_value="Patched profile brief",
                            ) as text_mock:
                                with patch.object(dashboard_server, "_unique_profile_id", return_value="patched-profile") as id_mock:
                                    with patch.object(dashboard_server, "_append_profile_config") as append_mock:
                                        with patch.object(dashboard_server, "DESK_DELIVERY_TARGET_ID", "custom-target"):
                                            result = dashboard_server.create_profile_from_brief(
                                                conn,
                                                {"source_base64": "not-base64", "source_filename": "brief.txt"},
                                            )
                profile_exists = (root / "profiles" / "desk" / "patched-profile.md").exists()
            finally:
                conn.close()

        text_mock.assert_called_once_with("not-base64", "brief.txt")
        ai_mock.assert_called_once_with("Patched profile brief")
        id_mock.assert_called_once()
        append_mock.assert_called_once()
        self.assertEqual(result["profile_id"], "patched-profile")
        self.assertEqual(append_mock.call_args.args[0]["delivery_targets"], ["custom-target"])
        self.assertTrue(profile_exists)

    def test_profile_create_facade_constant_patch_still_affects_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = monitor_state.connect(Path(tmp) / "tgcs.db")
            try:
                with patch.object(dashboard_server, "PROFILE_CREATE_MAX_TEXT_LENGTH", 5):
                    with self.assertRaises(ValueError) as raised:
                        dashboard_server.create_profile_from_brief(conn, {"brief": "too long"})
            finally:
                conn.close()

        self.assertIn("5 characters or fewer", str(raised.exception))

    def test_profile_create_requires_ai_key_before_writing_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = monitor_state.connect(root / "tgcs.db")
            try:
                with patch.object(dashboard_server, "PROJECT_ROOT", root):
                    with patch.object(dashboard_server.report, "llm_key_available", return_value=False):
                        with self.assertRaises(ValueError) as raised:
                            dashboard_server.create_profile_from_brief(conn, {"brief": "Find senior AI roles."})
            finally:
                conn.close()

        self.assertIn("AI API key", str(raised.exception))
        self.assertFalse((root / "profiles" / "desk").exists())

    def test_profile_create_uses_ai_generated_matching_rules(self):
        ai_payload = {
            "title": "Senior AI Roles",
            "goal": "Find senior paid AI engineering roles with clear next steps.",
            "search_rules": [
                "Include only senior AI engineering roles with a paid engagement.",
                "Prefer posts with a clear contact path and work format.",
            ],
            "rejection_rules": ["Reject unpaid internships and vague promotion posts."],
            "keywords": ["ai", "senior", "remote", "agent"],
            "topic": "ai-roles",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = monitor_state.connect(root / "tgcs.db")
            try:
                with patch.object(dashboard_server, "PROJECT_ROOT", root):
                    with patch.object(dashboard_server.report, "llm_key_available", return_value=True):
                        with patch.object(dashboard_server, "_profile_ai_payload_from_text", return_value=ai_payload, create=True) as ai_mock:
                            result = dashboard_server.create_profile_from_brief(
                                conn,
                                {"brief": "I want remote AI jobs. Avoid unpaid internships."},
                            )
                profile_text = (root / result["profile_path"]).read_text(encoding="utf-8")
                config_text = (root / ".tgcs" / "profiles.toml").read_text(encoding="utf-8")
            finally:
                conn.close()

        ai_mock.assert_called_once()
        self.assertEqual(result["display_name"], "Senior AI Roles")
        self.assertIn("Include only senior AI engineering roles", profile_text)
        self.assertIn("Reject unpaid internships", profile_text)
        self.assertIn('source_topics = ["ai-roles"]', config_text)
        self.assertIn('prefilter_keywords = ["ai", "senior", "remote", "agent"]', config_text)

    def test_profile_enabled_http_endpoint_updates_runtime_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tgcs.db"
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {
                        "id": "jobs-fast",
                        "path": "profiles/templates/jobs.md",
                        "enabled": True,
                    },
                )
            finally:
                conn.close()

            class FakeHandler:
                path = "/api/profiles/jobs-fast/enabled"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {"enabled": False}

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)
            conn = monitor_state.connect(db_path)
            try:
                snapshot = monitor_state.dashboard_snapshot(conn)
            finally:
                conn.close()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertFalse(handler.payload["profile"]["enabled"])
        self.assertFalse(snapshot["profiles"][0]["enabled"])


    def test_profile_enabled_http_endpoint_rejects_unexpected_fields(self):
        class FakeHandler:
            path = "/api/profiles/jobs-fast/enabled"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"enabled": False, "command": "tgcs monitor run"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("Unsupported profile setting field: command", handler.payload["error"])


    def test_profile_enabled_http_endpoint_requires_boolean(self):
        class FakeHandler:
            path = "/api/profiles/jobs-fast/enabled"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"enabled": "false"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("true or false", handler.payload["error"])


    def test_profile_runtime_settings_http_endpoint_updates_runtime_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tgcs.db"
            conn = monitor_state.connect(db_path)
            try:
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
            finally:
                conn.close()

            class FakeHandler:
                path = "/api/profiles/jobs-fast/runtime-settings"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {"scan_window_hours": 6, "semantic_max_messages": 40}

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)
            conn = monitor_state.connect(db_path)
            try:
                snapshot = monitor_state.dashboard_snapshot(conn)
            finally:
                conn.close()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["profile"]["config"]["scan_window_hours"], 6)
        self.assertEqual(handler.payload["profile"]["config"]["semantic_max_messages"], 40)
        self.assertEqual(snapshot["profiles"][0]["scan_window_hours"], 6)
        self.assertEqual(snapshot["profiles"][0]["semantic_max_messages"], 40)


    def test_profile_runtime_settings_http_endpoint_rejects_extra_fields(self):
        class FakeHandler:
            path = "/api/profiles/jobs-fast/runtime-settings"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _read_json_body(self):
                return {"scan_window_hours": 6, "command": "tgcs monitor run"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        handler = FakeHandler()
        dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("Unsupported profile setting field: command", handler.payload["error"])


    def test_profile_runtime_settings_http_endpoint_rejects_out_of_range_values(self):
        class FakeConnection:
            def close(self):
                pass

        class FakeHandler:
            path = "/api/profiles/jobs-fast/runtime-settings"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _connect(self):
                return FakeConnection()

            def _read_json_body(self):
                return {"scan_window_hours": 0}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server.monitor_state,
            "update_profile_runtime_settings",
            side_effect=monitor_state.MonitorStateError("scan_window_hours must be between 1 and 168."),
        ) as update_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        update_mock.assert_called_once()
        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("between 1 and 168", handler.payload["error"])


    def test_profile_runtime_settings_http_endpoint_rejects_invalid_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tgcs.db"
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {"id": "jobs-fast", "path": "profiles/templates/jobs.md", "enabled": True},
                )
            finally:
                conn.close()

            class FakeHandler:
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def __init__(self, body, path="/api/profiles/jobs-fast/runtime-settings"):
                    self.body = body
                    self.path = path

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return self.body

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            cases = [
                ({}, "/api/profiles/jobs-fast/runtime-settings", "At least one profile setting is required"),
                ({"semantic_max_messages": 0}, "/api/profiles/jobs-fast/runtime-settings", "between 1 and 500"),
                ({"semantic_max_messages": 501}, "/api/profiles/jobs-fast/runtime-settings", "between 1 and 500"),
                ({"scan_window_hours": "six"}, "/api/profiles/jobs-fast/runtime-settings", "must be an integer"),
                ({"scan_window_hours": True}, "/api/profiles/jobs-fast/runtime-settings", "must be an integer"),
                ({"scan_window_hours": 6}, "/api/profiles/unknown/runtime-settings", "Profile is not registered"),
            ]
            for body, path, error_fragment in cases:
                with self.subTest(body=body, path=path):
                    handler = FakeHandler(body, path)
                    dashboard_server.DashboardHandler.do_POST(handler)

                    self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                    self.assertIn(error_fragment, handler.payload["error"])


    def test_profile_draft_note_http_endpoint_creates_reviewable_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "tgcs.db"
            profile_path = root / "profiles" / "jobs.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text("# Jobs profile\n", encoding="utf-8")
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {"id": "jobs-fast", "path": str(profile_path), "enabled": True},
                )
            finally:
                conn.close()

            class FakeHandler:
                path = "/api/profiles/jobs-fast/draft-note"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {"note": "Prefer senior remote AI engineering roles."}

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            with patch.object(monitor_state, "PROJECT_ROOT", root):
                handler = FakeHandler()
                dashboard_server.DashboardHandler.do_POST(handler)
                conn = monitor_state.connect(db_path)
                try:
                    patches = monitor_state.dashboard_snapshot(conn)["profile_patch_suggestions"]
                finally:
                    conn.close()

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["patch"]["status"], "pending")
        self.assertEqual(len(patches), 1)
        self.assertIn("Prefer senior remote", patches[0]["note"])


    def test_profile_draft_note_http_endpoint_rejects_invalid_payloads(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def __init__(self, body):
                self.body = body
                self.path = "/api/profiles/jobs-fast/draft-note"

            def _read_json_body(self):
                return self.body

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        for body, error_fragment in [
            ({}, "Profile note is required"),
            ({"note": "valid", "command": "tgcs monitor run"}, "Unsupported profile draft field"),
            ({"note": "x" * (dashboard_server.PROFILE_DRAFT_NOTE_MAX_LENGTH + 1)}, "characters or fewer"),
            ({"note": "OPENAI_API_KEY=sk-localSecret12345"}, "cannot include"),
        ]:
            with self.subTest(body=list(body)):
                handler = FakeHandler(body)
                dashboard_server.DashboardHandler.do_POST(handler)

                self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                self.assertIn(error_fragment, handler.payload["error"])


    def test_profile_draft_note_http_endpoint_uses_facade_length_patch(self):
        class FakeHandler:
            path = "/api/profiles/jobs-fast/draft-note"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _connect(self):
                raise AssertionError("oversized note should be rejected before state access")

            def _read_json_body(self):
                return {"note": "123456"}

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(dashboard_server, "PROFILE_DRAFT_NOTE_MAX_LENGTH", 5):
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("5 characters or fewer", handler.payload["error"])


    def test_profile_matching_preferences_http_endpoint_rejects_private_fragments(self):
        class FakeHandler:
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)
            path = "/api/profiles/jobs-fast/matching-preferences"

            def __init__(self, body):
                self.body = body

            def _connect(self):
                raise AssertionError("private preference text should be rejected before state access")

            def _read_json_body(self):
                return self.body

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        for body, error_fragment in [
            ({"preferences": "Prefer remote roles. argv=['tgcs','monitor']"}, "cannot include"),
            ({"preferences": "chat_id=12345678901"}, "cannot include"),
        ]:
            with self.subTest(body=list(body)):
                handler = FakeHandler(body)
                dashboard_server.DashboardHandler.do_POST(handler)

                self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                self.assertIn(error_fragment, handler.payload["error"])


    def test_profile_create_endpoint_writes_local_profile_and_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "tgcs.db"

            class FakeHandler:
                path = "/api/profiles/create"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {
                        "brief": "Senior remote AI engineering roles. Avoid unpaid internships and vague promos.",
                        "source_filename": "background.txt",
                        "source_text": "Prefer agent platforms, backend automation, and clear paid work.",
                    }

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            ai_payload = {
                "title": "Senior AI Roles",
                "goal": "Find senior remote AI engineering roles.",
                "search_rules": ["Include senior remote AI engineering roles with clear paid work."],
                "rejection_rules": ["Reject unpaid internships and vague promos."],
                "keywords": ["senior", "remote", "ai", "engineering"],
                "topic": "senior-ai",
            }
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                with patch.object(dashboard_server.report, "llm_key_available", return_value=True):
                    with patch.object(dashboard_server, "_profile_ai_payload_from_text", return_value=ai_payload, create=True):
                        handler = FakeHandler()
                        dashboard_server.DashboardHandler.do_POST(handler)
                        conn = monitor_state.connect(db_path)
                        try:
                            snapshot = monitor_state.dashboard_snapshot(conn)
                        finally:
                            conn.close()

            profile = handler.payload["profile"]
            profile_path = root / profile["profile_path"]
            profile_body = profile_path.read_text(encoding="utf-8")
            config_path = root / ".tgcs" / "profiles.toml"
            config_text = config_path.read_text(encoding="utf-8")

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(profile["schema_version"], "desk_profile_create_result_v1")
        self.assertIn("Include senior remote AI engineering roles", profile_body)
        self.assertIn("scan_concurrency = 3", config_text)
        self.assertIn("scan_delay_seconds = 0.2", config_text)
        self.assertIn("semantic_max_messages = 40", config_text)
        self.assertIn("semantic_batch_size = 20", config_text)
        self.assertIn("semantic_concurrency = 2", config_text)
        self.assertEqual(snapshot["profiles"][0]["profile_id"], profile["profile_id"])


    def test_profile_delete_endpoint_removes_profile_from_desk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "tgcs.db"
            profile_path = root / "profiles" / "desk" / "custom-monitor.md"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text("# Custom monitor\n", encoding="utf-8")
            config_path = root / ".tgcs" / "profiles.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        'schema_version = "profile_run_config_v1"',
                        "",
                        "[[profiles]]",
                        'id = "custom-monitor"',
                        'path = "profiles/desk/custom-monitor.md"',
                        "enabled = true",
                        "",
                        "[[profiles]]",
                        'id = "keep-me"',
                        'path = "profiles/templates/jobs.md"',
                        "enabled = true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            conn = monitor_state.connect(db_path)
            try:
                monitor_state.upsert_profile(
                    conn,
                    {
                        "id": "custom-monitor",
                        "path": str(profile_path),
                        "enabled": True,
                    },
                )
                conn.execute(
                    """
                    INSERT INTO review_cards(
                        card_id, profile_id, item_key, title, rating, decision_status,
                        source_refs_json, item_json, status, opportunity_status,
                        opportunity_updated_at, first_run_id, last_run_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "card-1",
                        "custom-monitor",
                        "item-1",
                        "Old card",
                        "high",
                        "new",
                        "[]",
                        "{}",
                        monitor_state.PENDING_STATUS,
                        "open",
                        "",
                        "run-1",
                        "run-1",
                        "2026-05-14T00:00:00Z",
                        "2026-05-14T00:00:00Z",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            class FakeHandler:
                path = "/api/profiles/custom-monitor/delete"
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return {"confirm": True}

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                handler = FakeHandler()
                dashboard_server.DashboardHandler.do_POST(handler)
                conn = monitor_state.connect(db_path)
                try:
                    snapshot = monitor_state.dashboard_snapshot(conn)
                finally:
                    conn.close()

            config_text = config_path.read_text(encoding="utf-8")

        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertTrue(handler.payload["profile"]["deleted"])
        self.assertEqual(handler.payload["profile"]["review_card_count"], 1)
        self.assertEqual(snapshot["profiles"], [])
        self.assertEqual(snapshot["inbox"], [])
        self.assertFalse(profile_path.exists())
        self.assertNotIn('id = "custom-monitor"', config_text)
        self.assertIn('id = "keep-me"', config_text)


    def test_profile_create_endpoint_rejects_invalid_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tgcs.db"

            class FakeHandler:
                status = None
                payload = None
                client_address = ("127.0.0.1", 51000)

                def __init__(self, body):
                    self.body = body
                    self.path = "/api/profiles/create"

                def _connect(self):
                    return monitor_state.connect(db_path)

                def _read_json_body(self):
                    return self.body

                def _json(self, status, payload):
                    self.status = status
                    self.payload = payload

            for body, error_fragment in [
                ({}, "Describe the profile"),
                ({"brief": "valid", "command": "tgcs monitor run"}, "Unsupported profile creation field"),
                ({"brief": "x" * (dashboard_server.PROFILE_CREATE_MAX_TEXT_LENGTH + 1)}, "characters or fewer"),
                ({"brief": "Authorization: Bearer sk-localSecret12345"}, "cannot include"),
            ]:
                with self.subTest(body=list(body)):
                    handler = FakeHandler(body)
                    dashboard_server.DashboardHandler.do_POST(handler)

                    self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
                    self.assertIn(error_fragment, handler.payload["error"])



if __name__ == "__main__":
    unittest.main()
