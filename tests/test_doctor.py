import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class DoctorTests(unittest.TestCase):
    def test_json_reports_missing_credentials_as_failure(self):
        from scripts import doctor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_list = root / "channels.txt"
            profile = root / "profile.md"
            output_dir = root / "output"
            channel_list.write_text("remote_jobs\n", encoding="utf-8")
            profile.write_text("# Profile\n\n## Basic Info\n- **Role**: Frontend\n", encoding="utf-8")
            stdout = io.StringIO()

            with patch.dict("os.environ", {}, clear=True):
                with patch("sys.stdout", stdout):
                    exit_code = doctor.main(
                        [
                            "--channel-list",
                            str(channel_list),
                            "--profile",
                            str(profile),
                            "--output-dir",
                            str(output_dir),
                            "--config-path",
                            str(root / "missing.toml"),
                            "--session-path",
                            str(root / "missing.session"),
                            "--json",
                        ]
                    )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["summary"]["fail"], 1)
        self.assertEqual(payload["checks"]["telegram_credentials"]["status"], "fail")

    def test_env_credentials_pass_and_missing_session_is_warning_only(self):
        from scripts import doctor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_list = root / "channels.txt"
            profile = root / "profile.md"
            channel_list.write_text("remote_jobs\n", encoding="utf-8")
            profile.write_text("# Profile\n\n## Basic Info\n- **Role**: Frontend\n", encoding="utf-8")
            stdout = io.StringIO()

            with patch.dict(
                "os.environ",
                {"TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "hash", "OPENAI_API_KEY": "sk-test"},
                clear=True,
            ):
                with patch("sys.stdout", stdout):
                    exit_code = doctor.main(
                        [
                            "--channel-list",
                            str(channel_list),
                            "--profile",
                            str(profile),
                            "--output-dir",
                            str(root / "output"),
                            "--config-path",
                            str(root / "missing.toml"),
                            "--session-path",
                            str(root / "missing.session"),
                            "--json",
                        ]
                    )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["checks"]["telegram_credentials"]["status"], "pass")
        self.assertEqual(payload["checks"]["telegram_session"]["status"], "warn")
        self.assertEqual(payload["checks"]["llm_provider"]["status"], "pass")

    def test_empty_channel_list_and_output_file_are_failures(self):
        from scripts import doctor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_list = root / "channels.txt"
            profile = root / "profile.md"
            output_file = root / "output-as-file"
            channel_list.write_text("\n# nothing here\n", encoding="utf-8")
            profile.write_text("# Profile\n\n## Basic Info\n- **Role**: Frontend\n", encoding="utf-8")
            output_file.write_text("not a directory", encoding="utf-8")
            stdout = io.StringIO()

            with patch.dict(
                "os.environ",
                {"TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "hash"},
                clear=True,
            ):
                with patch("sys.stdout", stdout):
                    exit_code = doctor.main(
                        [
                            "--channel-list",
                            str(channel_list),
                            "--profile",
                            str(profile),
                            "--output-dir",
                            str(output_file),
                            "--config-path",
                            str(root / "missing.toml"),
                            "--session-path",
                            str(root / "missing.session"),
                            "--json",
                        ]
                    )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["checks"]["channel_list"]["status"], "fail")
        self.assertEqual(payload["checks"]["output_directory"]["status"], "fail")

    def test_channel_list_warns_about_duplicates_and_invite_links(self):
        from scripts import doctor

        with tempfile.TemporaryDirectory() as tmp:
            channel_list = Path(tmp) / "channels.txt"
            channel_list.write_text(
                "@frontend_jobs\nhttps://t.me/frontend_jobs\nhttps://t.me/+privateInvite\n",
                encoding="utf-8",
            )

            result = doctor.check_channel_list(channel_list)

        self.assertEqual(result.status, "warn")
        self.assertIn("needs review", result.message)
        self.assertEqual(result.details["count"], 3)
        self.assertEqual(result.details["duplicate_count"], 1)
        self.assertEqual(result.details["unsupported_invite_count"], 1)

    def test_online_telegram_check_is_explicit_and_non_interactive(self):
        from scripts import doctor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel_list = root / "channels.txt"
            profile = root / "profile.md"
            channel_list.write_text("remote_jobs\n", encoding="utf-8")
            profile.write_text("# Profile\n\n## Basic Info\n- **Role**: Frontend\n", encoding="utf-8")
            stdout = io.StringIO()

            with patch.dict(
                "os.environ",
                {"TELEGRAM_API_ID": "123", "TELEGRAM_API_HASH": "hash"},
                clear=True,
            ):
                with patch.object(
                    doctor,
                    "check_online_telegram",
                    return_value=doctor.CheckResult(
                        "telegram_online", "warn", "session is not authorized"
                    ),
                ) as online:
                    with patch("builtins.input", side_effect=AssertionError("doctor must not prompt")):
                        with patch("sys.stdout", stdout):
                            exit_code = doctor.main(
                                [
                                    "--channel-list",
                                    str(channel_list),
                                    "--profile",
                                    str(profile),
                                    "--output-dir",
                                    str(root / "output"),
                                    "--config-path",
                                    str(root / "missing.toml"),
                                    "--session-path",
                                    str(root / "session"),
                                    "--online-telegram",
                                    "--json",
                                ]
                            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        online.assert_called_once()
        self.assertEqual(payload["checks"]["telegram_online"]["status"], "warn")

    def test_minimax_key_counts_as_llm_provider(self):
        from scripts import doctor

        with patch.dict("os.environ", {"MINIMAX_TOKEN_PLAN_KEY": "test-key"}, clear=True):
            result = doctor.check_llm_provider()

        self.assertEqual(result.status, "pass")
        self.assertIn("minimax", result.details["providers"])
        self.assertEqual(result.details["minimax_key_type"], "token_plan")
        self.assertEqual(result.details["minimax_base_url"], "https://api.minimaxi.com/v1")

    def test_source_registry_warns_when_only_placeholder_sources_exist(self):
        from scripts import doctor

        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "sources.json"
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
                                "topics": [],
                                "priority": "normal",
                                "expected_language": "",
                                "scan_window_hours": 24,
                                "enabled": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = doctor.check_source_registry(registry)

        self.assertEqual(result.status, "warn")
        self.assertIn("placeholder", result.message)
        self.assertIn("tgcs init --starter jobs --force", result.next_step)
        self.assertIn("tgcs sources import channel_lists/jobs.txt --topic jobs", result.next_step)
        self.assertEqual(result.details["placeholder_count"], 1)

    def test_dashboard_assets_pass_when_dist_index_exists(self):
        from scripts import doctor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dashboard" / "dist").mkdir(parents=True)
            (root / "dashboard" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

            with patch.object(doctor, "PROJECT_ROOT", root):
                result = doctor.check_dashboard_assets()

        self.assertEqual(result.status, "pass")
        self.assertEqual(Path(result.details["static_dir"]), root / "dashboard" / "dist")

    def test_dashboard_assets_warns_with_auto_build_next_step(self):
        from scripts import doctor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dashboard").mkdir()
            (root / "dashboard" / "package.json").write_text("{}", encoding="utf-8")

            with patch.object(doctor, "PROJECT_ROOT", root):
                with patch.object(doctor.shutil, "which", return_value="C:\\node\\npm.cmd"):
                    result = doctor.check_dashboard_assets()

        self.assertEqual(result.status, "warn")
        self.assertIn("tgcs dashboard", result.next_step)


if __name__ == "__main__":
    unittest.main()
