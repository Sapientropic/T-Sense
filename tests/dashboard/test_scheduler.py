import subprocess
import tempfile
import unittest
import json
import plistlib
from types import SimpleNamespace
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_server, monitor_state


def write_enabled_jobs_profile(root: Path) -> None:
    config_dir = root / ".tgcs"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "profiles.toml").write_text(
        "\n".join(
            [
                'schema_version = "profile_run_config_v1"',
                "",
                "[[profiles]]",
                'id = "jobs-fast"',
                'path = "profiles/templates/jobs.md"',
                "enabled = true",
                "",
            ]
        ),
        encoding="utf-8",
    )


class DashboardSchedulerTests(unittest.TestCase):
    def test_schedule_install_dry_run_requires_confirmation(self):
        with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
            with self.assertRaises(dashboard_server.DashboardDeskActionError) as raised:
                dashboard_server.run_desk_action("schedule_install_dry_run", body={})

        run_mock.assert_not_called()
        self.assertIn("confirmation", str(raised.exception))


    def test_schedule_install_dry_run_rejects_extra_payload_keys(self):
        with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
            with self.assertRaises(dashboard_server.DashboardDeskActionError) as raised:
                dashboard_server.run_desk_action(
                    "schedule_install_dry_run",
                    body={"confirm": True, "command": "powershell Remove-Item ."},
                )

        run_mock.assert_not_called()
        self.assertIn("confirmation flag", str(raised.exception))


    def test_schedule_install_dry_run_blocks_non_windows(self):
        with patch.object(dashboard_server.sys, "platform", "linux"):
            with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": ""}, clear=False):
                with patch.object(
                    dashboard_server,
                    "shutil",
                    SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                    create=True,
                ):
                    with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                        result = dashboard_server.run_desk_action("schedule_install_dry_run", body={"confirm": True})

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("crontab", result["detail"])
        self.assertIn("schedule print --platform cron", result["next_action"])


    def test_schedule_install_dry_run_blocks_when_launcher_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", Path(tmp)), patch.object(dashboard_server, "CODE_ROOT", Path(tmp)):
                    with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                        result = dashboard_server.run_desk_action("schedule_install_dry_run", body={"confirm": True})

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("launcher", result["detail"].lower())


    def test_schedule_install_dry_run_uses_fixed_schtasks_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "scripts").mkdir()
            (project_root / "scripts" / "tgcs.py").write_text("# tgcs entry\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="SUCCESS\n", stderr="")

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                        result = dashboard_server.run_desk_action(
                            "schedule_install_dry_run",
                            body={"confirm": True},
                        )

        args = run_mock.call_args_list[0].args[0]
        self.assertEqual(args[0], "schtasks.exe")
        self.assertIn("/Create", args)
        self.assertIn(dashboard_server.DESK_SCHEDULER_TASK_NAME, args)
        trigger = args[args.index("/TR") + 1]
        self.assertIn("tgcs.py", trigger)
        self.assertIn("--profile-id market-news", trigger)
        self.assertIn("--delivery-mode live", trigger)
        self.assertNotIn("--delivery-mode dry-run", trigger)
        self.assertEqual(result["status"], "success")
        self.assertNotIn(str(project_root), result["detail"])
        self.assertIn(
            ["schtasks.exe", "/Delete", "/TN", "TGCS jobs-fast dry-run", "/F"],
            [call.args[0] for call in run_mock.call_args_list],
        )


    def test_schedule_install_dry_run_prefers_latest_desk_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "scripts").mkdir()
            (project_root / "scripts" / "tgcs.py").write_text("# tgcs entry\n", encoding="utf-8")
            config_path = project_root / ".tgcs" / "profiles.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        'schema_version = "profile_run_config_v1"',
                        "",
                        "[[profiles]]",
                        'id = "jobs-fast"',
                        'path = "profiles/templates/jobs.md"',
                        "enabled = true",
                        "",
                        "[[profiles]]",
                        'id = "frontend-only"',
                        'path = "profiles/desk/frontend-only.md"',
                        "enabled = true",
                    ]
                ),
                encoding="utf-8",
            )
            completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="SUCCESS\n", stderr="")

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                        result = dashboard_server.run_desk_action(
                            "schedule_install_dry_run",
                            body={"confirm": True},
                        )

        args = run_mock.call_args_list[0].args[0]
        trigger = args[args.index("/TR") + 1]
        self.assertIn("--profile-id frontend-only", trigger)
        self.assertEqual(
            result["display_command"],
            "tgcs schedule print --profile-id frontend-only --interval-minutes 15 --delivery-mode live",
        )
        self.assertIn("frontend-only AI reviews", result["detail"])


    def test_schedule_install_dry_run_blocks_when_profile_paused_in_desk_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "scripts").mkdir()
            (project_root / "scripts" / "tgcs.py").write_text("# tgcs entry\n", encoding="utf-8")
            config_path = project_root / ".tgcs" / "profiles.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        'schema_version = "profile_run_config_v1"',
                        "",
                        "[[profiles]]",
                        'id = "jobs-fast"',
                        'path = "profiles/templates/jobs.md"',
                        "enabled = true",
                    ]
                ),
                encoding="utf-8",
            )
            conn = monitor_state.connect(project_root / ".tgcs" / "tgcs.db")
            try:
                monitor_state.upsert_profile(
                    conn,
                    {"id": "jobs-fast", "path": str(project_root / "profiles" / "templates" / "jobs.md"), "enabled": True},
                )
                monitor_state.update_profile_enabled(conn, profile_id="jobs-fast", enabled=False)
            finally:
                conn.close()

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                        result = dashboard_server.run_desk_action(
                            "schedule_install_dry_run",
                            body={"confirm": True},
                        )

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("No enabled profile", result["title"])


    def test_schedule_remove_dry_run_uses_fixed_schtasks_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "scripts").mkdir()
            (project_root / "scripts" / "tgcs.py").write_text("# tgcs entry\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="SUCCESS\n", stderr="")

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                        result = dashboard_server.run_desk_action(
                            "schedule_remove_dry_run",
                            body={"confirm": True},
                        )

        args = run_mock.call_args.args[0]
        self.assertEqual(args[:2], ["schtasks.exe", "/Delete"])
        self.assertIn(dashboard_server.DESK_SCHEDULER_TASK_NAME, args)
        self.assertEqual(result["status"], "success")


    def test_schedule_remove_dry_run_removes_legacy_windows_task_when_new_name_is_missing(self):
        calls: list[list[str]] = []

        def fake_run(args):
            calls.append(args)
            if args[args.index("/TN") + 1] == "TGCS jobs-fast dry-run":
                return subprocess.CompletedProcess(args, 0, stdout="SUCCESS\n", stderr="")
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="ERROR: missing\n")

        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                result = dashboard_server.run_desk_action("schedule_remove_dry_run", body={"confirm": True})

        self.assertEqual(result["status"], "success")
        self.assertEqual(calls[0], ["schtasks.exe", "/Delete", "/TN", dashboard_server.DESK_SCHEDULER_TASK_NAME, "/F"])
        self.assertEqual(calls[1], ["schtasks.exe", "/Delete", "/TN", "TGCS jobs-fast dry-run", "/F"])


    def test_schedule_install_dry_run_failure_sanitizes_project_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "scripts").mkdir()
            (project_root / "scripts" / "tgcs.py").write_text("# tgcs entry\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                ["schtasks.exe"],
                1,
                stdout="",
                stderr=f"ERROR: cannot use {project_root}\\tgcs.bat\n",
            )

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed):
                        result = dashboard_server.run_desk_action(
                            "schedule_install_dry_run",
                            body={"confirm": True},
                        )

        self.assertEqual(result["status"], "failed")
        self.assertNotIn(str(project_root), result["detail"])
        self.assertIn("project folder", result["detail"])


    def test_bot_gateway_autostart_install_requires_confirmation(self):
        with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
            with self.assertRaises(dashboard_server.DashboardDeskActionError) as raised:
                dashboard_server.run_desk_action("bot_gateway_install_autostart", body={})

        run_mock.assert_not_called()
        self.assertIn("confirmation", str(raised.exception))


    def test_bot_gateway_argv_uses_dashboard_facade_patch_after_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            scripts_dir = project_root / "scripts"
            scripts_dir.mkdir()
            bot_script = scripts_dir / "bot_gateway.py"
            bot_script.write_text("# bot gateway\n", encoding="utf-8")
            pythonw = project_root / "pythonw.exe"
            pythonw.write_text("", encoding="utf-8")

            with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                with patch.object(dashboard_server, "_pythonw_entry", return_value=pythonw):
                    argv = dashboard_server._fixed_bot_gateway_argv()

        self.assertEqual(
            argv,
            [
                str(pythonw),
                str(bot_script),
                "run",
                "--db",
                str(project_root / ".tgcs" / "tgcs.db"),
                "--state",
                str(project_root / ".tgcs" / "bot-gateway-state.json"),
                "--lock",
                str(project_root / ".tgcs" / "bot-gateway.lock"),
                "--poll-timeout",
                "8",
            ],
        )


    def test_bot_gateway_background_status_uses_dashboard_scheduler_patch_after_split(self):
        completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="TaskName: private path\n", stderr="")

        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                status = dashboard_server.desk_bot_gateway_background_status(token_configured=True)

        run_mock.assert_called_once_with(["schtasks.exe", "/Query", "/TN", dashboard_server.DESK_BOT_GATEWAY_TASK_NAME])
        self.assertEqual(status["schema_version"], "desk_bot_gateway_background_status_v1")
        self.assertTrue(status["installed"])
        self.assertTrue(status["can_remove"])


    def test_bot_gateway_autostart_install_uses_fixed_windows_login_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            scripts_dir = project_root / "scripts"
            scripts_dir.mkdir()
            bot_script = scripts_dir / "bot_gateway.py"
            bot_script.write_text("# bot gateway\n", encoding="utf-8")
            pythonw = project_root / "pythonw.exe"
            pythonw.write_text("", encoding="utf-8")
            completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="SUCCESS\n", stderr="")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return completed

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(dashboard_server, "_pythonw_entry", return_value=pythonw):
                        with patch.object(
                            dashboard_server,
                            "desk_notification_token_status",
                            return_value={"configured": True, "source": "keyring"},
                        ):
                            with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                result = dashboard_server.run_desk_action(
                                    "bot_gateway_install_autostart",
                                    body={"confirm": True},
                                )

        args = calls[0]
        trigger = args[args.index("/TR") + 1]
        self.assertEqual(args[0], "schtasks.exe")
        self.assertIn("/Create", args)
        self.assertIn("/SC", args)
        self.assertIn("ONLOGON", args)
        self.assertIn(dashboard_server.DESK_BOT_GATEWAY_TASK_NAME, args)
        self.assertIn(str(pythonw), trigger)
        self.assertIn(str(bot_script), trigger)
        self.assertIn("run --db", trigger)
        self.assertIn("--poll-timeout 8", trigger)
        self.assertNotIn("123456", trigger)
        self.assertNotIn("token", trigger.lower())
        self.assertEqual(calls[1], ["schtasks.exe", "/End", "/TN", dashboard_server.DESK_BOT_GATEWAY_TASK_NAME])
        self.assertEqual(calls[2], ["schtasks.exe", "/Run", "/TN", dashboard_server.DESK_BOT_GATEWAY_TASK_NAME])
        self.assertEqual(result["status"], "success")
        self.assertNotIn(str(project_root), result["detail"])

    def test_bot_gateway_repair_only_restarts_existing_windows_task(self):
        calls: list[list[str]] = []

        def fake_run(args):
            calls.append(args)
            if "/Query" in args:
                return subprocess.CompletedProcess(args, 0, stdout="READY\n", stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="SUCCESS\n", stderr="")

        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                result = dashboard_server.repair_installed_bot_gateway_background()

        self.assertEqual(result["status"], "started")
        self.assertTrue(result["ok"])
        self.assertEqual(calls[0], ["schtasks.exe", "/Query", "/TN", dashboard_server.DESK_BOT_GATEWAY_TASK_NAME])
        self.assertEqual(calls[1], ["schtasks.exe", "/End", "/TN", dashboard_server.DESK_BOT_GATEWAY_TASK_NAME])
        self.assertEqual(calls[2], ["schtasks.exe", "/Run", "/TN", dashboard_server.DESK_BOT_GATEWAY_TASK_NAME])
        self.assertNotIn("/Create", json.dumps(calls))


    def test_bot_gateway_autostart_blocks_when_token_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "scripts").mkdir()
            (project_root / "scripts" / "bot_gateway.py").write_text("# bot gateway\n", encoding="utf-8")

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(
                        dashboard_server,
                        "desk_notification_token_status",
                        return_value={"configured": False, "source": "not_configured"},
                    ):
                        with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                            result = dashboard_server.run_desk_action(
                                "bot_gateway_install_autostart",
                                body={"confirm": True},
                            )

        run_mock.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("token", result["detail"].lower())
        self.assertNotIn(str(project_root), json.dumps(result, ensure_ascii=False))


    def test_bot_gateway_autostart_status_is_included_with_gateway_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = monitor_state.connect(root / ".tgcs" / "tgcs.db")
            completed = subprocess.CompletedProcess(
                ["schtasks.exe"],
                0,
                stdout=f"TaskName: {root}\\private\\bot\n",
                stderr="",
            )
            try:
                with patch.object(dashboard_server.sys, "platform", "win32"):
                    with patch.object(dashboard_server, "PROJECT_ROOT", root), patch.object(dashboard_server, "CODE_ROOT", root):
                        with patch.object(
                            dashboard_server,
                            "desk_notification_token_status",
                            return_value={"configured": True, "source": "keyring"},
                        ):
                            with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed):
                                status = dashboard_server.desk_bot_gateway_status(conn)
            finally:
                conn.close()

        rendered = json.dumps(status, ensure_ascii=False)
        self.assertTrue(status["background"]["installed"])
        self.assertEqual(status["background"]["status"], "installed")
        self.assertTrue(status["background"]["can_remove"])
        self.assertIn("Repair alerts", status["safe_next_action"])
        self.assertNotIn(str(root), rendered)


    def test_bot_gateway_autostart_writes_macos_launch_agent_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            code_root = Path(tmp) / "bundle-code"
            project_root = Path(tmp) / "Application Support" / "T-Sense"
            home.mkdir()
            (code_root / "scripts").mkdir(parents=True)
            bot_script = code_root / "scripts" / "bot_gateway.py"
            bot_script.write_text("# bot gateway\n", encoding="utf-8")
            python = code_root / "python"
            python.write_text("", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", code_root):
                        with patch.object(dashboard_server, "_pythonw_entry", return_value=python):
                            with patch.object(
                                dashboard_server,
                                "desk_notification_token_status",
                                return_value={"configured": True, "source": "keyring"},
                            ):
                                with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                    result = dashboard_server.run_desk_action(
                                        "bot_gateway_install_autostart",
                                        body={"confirm": True},
                                    )

            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tsense.bot-gateway.plist"
            plist = plistlib.loads(plist_path.read_bytes())

        self.assertEqual(result["status"], "success")
        self.assertEqual(plist["Label"], "com.sapientropic.tsense.bot-gateway")
        self.assertEqual(
            plist["ProgramArguments"],
            [
                str(python),
                str(bot_script),
                "run",
                "--db",
                str(project_root / ".tgcs" / "tgcs.db"),
                "--state",
                str(project_root / ".tgcs" / "bot-gateway-state.json"),
                "--lock",
                str(project_root / ".tgcs" / "bot-gateway.lock"),
                "--poll-timeout",
                "8",
            ],
        )
        self.assertEqual(plist["KeepAlive"], {"Crashed": True})
        self.assertEqual(plist["WorkingDirectory"], str(project_root))
        self.assertEqual(plist["EnvironmentVariables"]["TGCS_PROJECT_ROOT"], str(project_root))
        self.assertEqual(plist["EnvironmentVariables"]["TG_SCANNER_CONFIG_DIR"], str(project_root / ".tgcs" / "telegram"))
        self.assertEqual(plist["EnvironmentVariables"]["TGCLI_CONFIG_DIR"], str(project_root / ".tgcs" / "telegram"))
        self.assertTrue(plist["StandardOutPath"].endswith("/tsense-bot-gateway.log"))
        self.assertIn("/tmp/tsense-launchd-", plist["StandardOutPath"])
        self.assertTrue(plist["StandardErrorPath"].endswith("/tsense-bot-gateway.err.log"))
        self.assertIn("/tmp/tsense-launchd-", plist["StandardErrorPath"])
        self.assertIn(["launchctl", "unload", "-w", str(plist_path)], calls)
        self.assertIn(["launchctl", "load", "-w", str(plist_path)], calls)

    def test_bot_gateway_autostart_reports_macos_launchd_ex_config_after_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            code_root = Path(tmp) / "bundle-code"
            project_root = Path(tmp) / "Application Support" / "T-Sense"
            home.mkdir()
            (code_root / "scripts").mkdir(parents=True)
            (code_root / "scripts" / "bot_gateway.py").write_text("# bot gateway\n", encoding="utf-8")
            python = code_root / "python"
            python.write_text("", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                if args[:2] == ["launchctl", "print"]:
                    return subprocess.CompletedProcess(
                        args,
                        0,
                        stdout="state = exited\nlast exit code = 78: EX_CONFIG\n",
                        stderr="",
                    )
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", code_root):
                        with patch.object(dashboard_server, "_pythonw_entry", return_value=python):
                            with patch.object(
                                dashboard_server,
                                "desk_notification_token_status",
                                return_value={"configured": True, "source": "keyring"},
                            ):
                                with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                    result = dashboard_server.run_desk_action(
                                        "bot_gateway_install_autostart",
                                        body={"confirm": True},
                                    )

        self.assertEqual(result["status"], "failed")
        self.assertIn("EX_CONFIG", result["detail"])
        self.assertIn("stdio log path", result["detail"])
        self.assertTrue(any(call[:2] == ["launchctl", "print"] for call in calls))

    def test_bot_gateway_background_status_surfaces_macos_launchd_ex_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tsense.bot-gateway.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("placeholder", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                ["launchctl"],
                0,
                stdout="state = exited\nlast exit code = 78: EX_CONFIG\n",
                stderr="",
            )

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                        with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed):
                            status = dashboard_server.desk_bot_gateway_background_status(token_configured=True)

        self.assertTrue(status["installed"])
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["last_exit_code"], 78)
        self.assertIn("EX_CONFIG", status["detail"])
        self.assertIn("stdio log path", status["detail"])


    def test_bot_gateway_autostart_writes_linux_systemd_service_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            runtime_dir = Path(tmp) / "runtime"
            home.mkdir()
            runtime_dir.mkdir()
            (project_root / "scripts").mkdir(parents=True)
            bot_script = project_root / "scripts" / "bot_gateway.py"
            bot_script.write_text("# bot gateway\n", encoding="utf-8")
            python = project_root / "python"
            python.write_text("", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "linux"):
                with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": str(runtime_dir)}, clear=False):
                    with patch.object(
                        dashboard_server,
                        "shutil",
                        SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                        create=True,
                    ):
                        with patch.object(dashboard_server.Path, "home", return_value=home):
                            with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                                with patch.object(dashboard_server, "_pythonw_entry", return_value=python):
                                    with patch.object(
                                        dashboard_server,
                                        "desk_notification_token_status",
                                        return_value={"configured": True, "source": "keyring"},
                                    ):
                                        with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                            result = dashboard_server.run_desk_action(
                                                "bot_gateway_install_autostart",
                                                body={"confirm": True},
                                            )

            service_path = home / ".config" / "systemd" / "user" / "tsense-bot-gateway.service"
            service_text = service_path.read_text(encoding="utf-8")

        self.assertEqual(result["status"], "success")
        self.assertIn(str(python), service_text)
        self.assertIn(str(bot_script), service_text)
        self.assertIn("Restart=on-failure", service_text)
        self.assertIn(["systemctl", "--user", "daemon-reload"], calls)
        self.assertIn(["systemctl", "--user", "enable", "--now", "tsense-bot-gateway.service"], calls)
        self.assertIn(["systemctl", "--user", "restart", "tsense-bot-gateway.service"], calls)


    def test_desk_scheduler_status_uses_manual_preview_on_non_systemd_linux_without_subprocess(self):
        with patch.object(dashboard_server.sys, "platform", "linux"):
            with patch.object(
                dashboard_server,
                "shutil",
                SimpleNamespace(which=lambda name: None),
                create=True,
            ):
                with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                    status = dashboard_server.desk_scheduler_status()

        run_mock.assert_not_called()
        self.assertFalse(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "manual")
        self.assertEqual(status["backend"], "manual_cron_preview")
        self.assertFalse(status["can_install"])
        self.assertFalse(status["can_remove"])


    def test_desk_scheduler_status_uses_manual_preview_when_linux_user_bus_is_missing(self):
        with patch.object(dashboard_server.sys, "platform", "linux"):
            with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": ""}, clear=False):
                with patch.object(
                    dashboard_server,
                    "shutil",
                    SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                    create=True,
                ):
                    with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                        status = dashboard_server.desk_scheduler_status()

        run_mock.assert_not_called()
        self.assertEqual(status["backend"], "manual_cron_preview")
        self.assertFalse(status["can_install"])


    def test_desk_scheduler_status_blocks_unsupported_platform_without_subprocess(self):
        with patch.object(dashboard_server.sys, "platform", "freebsd"):
            with patch.object(dashboard_server, "_run_scheduler_command") as run_mock:
                status = dashboard_server.desk_scheduler_status()

        run_mock.assert_not_called()
        self.assertFalse(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "unavailable")
        self.assertEqual(status["backend"], "manual_cron_preview")


    def test_schedule_install_dry_run_writes_macos_launch_agent_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            code_root = Path(tmp) / "bundle-code"
            project_root = Path(tmp) / "Application Support" / "T-Sense"
            home.mkdir()
            (code_root / "scripts").mkdir(parents=True)
            tgcs_script = code_root / "scripts" / "tgcs.py"
            tgcs_script.write_text("# tgcs entry\n", encoding="utf-8")
            python = code_root / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", code_root):
                        with patch.object(dashboard_server, "_pythonw_entry", return_value=python):
                            with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                result = dashboard_server.run_desk_action(
                                    "schedule_install_dry_run",
                                    body={"confirm": True},
                                )

            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tsense.auto-review.plist"
            plist = plistlib.loads(plist_path.read_bytes())

        self.assertEqual(result["status"], "success")
        self.assertEqual(plist["Label"], "com.sapientropic.tsense.auto-review")
        self.assertEqual(
            plist["ProgramArguments"],
            [
                str(python),
                str(tgcs_script),
                "monitor",
                "run",
                "--profile-id",
                "market-news",
                "--delivery-mode",
                "live",
            ],
        )
        self.assertEqual(plist["WorkingDirectory"], str(project_root))
        self.assertEqual(plist["EnvironmentVariables"]["TGCS_PROJECT_ROOT"], str(project_root))
        self.assertEqual(plist["EnvironmentVariables"]["TG_SCANNER_CONFIG_DIR"], str(project_root / ".tgcs" / "telegram"))
        self.assertEqual(plist["EnvironmentVariables"]["TGCLI_CONFIG_DIR"], str(project_root / ".tgcs" / "telegram"))
        self.assertTrue(plist["StandardOutPath"].endswith("/tgcs-market-news.log"))
        self.assertIn("/tmp/tsense-launchd-", plist["StandardOutPath"])
        self.assertTrue(plist["StandardErrorPath"].endswith("/tgcs-market-news.err.log"))
        self.assertIn("/tmp/tsense-launchd-", plist["StandardErrorPath"])
        self.assertIn(["launchctl", "unload", "-w", str(plist_path)], calls)
        self.assertIn(["launchctl", "load", "-w", str(plist_path)], calls)

    def test_schedule_install_reports_macos_launchd_ex_config_after_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            code_root = Path(tmp) / "bundle-code"
            project_root = Path(tmp) / "Application Support" / "T-Sense"
            home.mkdir()
            (code_root / "scripts").mkdir(parents=True)
            (code_root / "scripts" / "tgcs.py").write_text("# tgcs entry\n", encoding="utf-8")
            python = code_root / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                if args[:2] == ["launchctl", "print"]:
                    return subprocess.CompletedProcess(
                        args,
                        0,
                        stdout="state = exited\nlast exit code = 78: EX_CONFIG\n",
                        stderr="",
                    )
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", code_root):
                        with patch.object(dashboard_server, "_pythonw_entry", return_value=python):
                            with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                result = dashboard_server.run_desk_action(
                                    "schedule_install_dry_run",
                                    body={"confirm": True},
                                )

        self.assertEqual(result["status"], "failed")
        self.assertIn("EX_CONFIG", result["detail"])
        self.assertIn("stdio log path", result["detail"])
        self.assertTrue(any(call[:2] == ["launchctl", "print"] for call in calls))


    def test_desk_scheduler_status_surfaces_failing_macos_launch_agent_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tsense.auto-review.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("placeholder", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                ["launchctl"],
                0,
                stdout="state = exited\nlast exit code = 126\n",
                stderr="",
            )

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                        with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                            status = dashboard_server.desk_scheduler_status()

        self.assertTrue(status["installed"])
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["last_exit_code"], 126)
        self.assertIn("last exited with code 126", status["detail"])
        self.assertIn("Repair auto review", status["next_action"])
        args = run_mock.call_args.args[0]
        self.assertEqual(args[0:2], ["launchctl", "print"])
        self.assertIn("com.sapientropic.tsense.auto-review", args[-1])

    def test_desk_scheduler_status_explains_macos_launch_agent_ex_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tsense.auto-review.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("placeholder", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                ["launchctl"],
                0,
                stdout="state = exited\nlast exit code = 78: EX_CONFIG\n",
                stderr="",
            )

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                        with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed):
                            status = dashboard_server.desk_scheduler_status()

        self.assertTrue(status["installed"])
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["last_exit_code"], 78)
        self.assertIn("EX_CONFIG", status["detail"])
        self.assertIn("stdio log path", status["detail"])


    def test_desk_scheduler_status_detects_legacy_macos_launch_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tgcs.jobs-fast.dry-run.plist"
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("placeholder", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="state = running\n", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                        with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                            status = dashboard_server.desk_scheduler_status()

        self.assertTrue(status["installed"])
        self.assertTrue(status["legacy_task_name"])
        self.assertEqual(status["task_name"], "com.sapientropic.tgcs.jobs-fast.dry-run")
        self.assertIn("com.sapientropic.tgcs.jobs-fast.dry-run", calls[0][-1])


    def test_schedule_remove_dry_run_unloads_macos_launch_agent_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tsense.auto-review.plist"
            home.mkdir()
            project_root.mkdir()
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("placeholder", encoding="utf-8")
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                        with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                            result = dashboard_server.run_desk_action(
                                "schedule_remove_dry_run",
                                body={"confirm": True},
                            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(calls, [["launchctl", "unload", "-w", str(plist_path)]])
        self.assertFalse(plist_path.exists())


    def test_schedule_remove_dry_run_unloads_legacy_macos_launch_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            plist_path = home / "Library" / "LaunchAgents" / "com.sapientropic.tgcs.jobs-fast.dry-run.plist"
            home.mkdir()
            project_root.mkdir()
            plist_path.parent.mkdir(parents=True)
            plist_path.write_text("placeholder", encoding="utf-8")
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "darwin"):
                with patch.object(dashboard_server.Path, "home", return_value=home):
                    with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                        with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                            result = dashboard_server.run_desk_action(
                                "schedule_remove_dry_run",
                                body={"confirm": True},
                            )

        self.assertEqual(result["status"], "success")
        self.assertIn(["launchctl", "unload", "-w", str(plist_path)], calls)
        self.assertFalse(plist_path.exists())


    def test_schedule_install_dry_run_writes_linux_systemd_user_units_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            home.mkdir()
            project_root.mkdir()
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "linux"):
                with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": str(Path(tmp) / "runtime")}, clear=False):
                    with patch.object(
                        dashboard_server,
                        "shutil",
                        SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                        create=True,
                    ):
                        with patch.object(dashboard_server.Path, "home", return_value=home):
                            with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                                with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                    result = dashboard_server.run_desk_action(
                                        "schedule_install_dry_run",
                                        body={"confirm": True},
                                    )

            service_path = home / ".config" / "systemd" / "user" / "tsense-auto-review.service"
            timer_path = home / ".config" / "systemd" / "user" / "tsense-auto-review.timer"
            service_text = service_path.read_text(encoding="utf-8")
            timer_text = timer_path.read_text(encoding="utf-8")

        self.assertEqual(result["status"], "success")
        self.assertIn(f"ExecStart={project_root / 'tgcs'} monitor run --profile-id market-news --delivery-mode live", service_text)
        self.assertIn("OnUnitActiveSec=15min", timer_text)
        self.assertIn(["systemctl", "--user", "daemon-reload"], calls)
        self.assertIn(["systemctl", "--user", "enable", "--now", "tsense-auto-review.timer"], calls)


    def test_schedule_remove_dry_run_disables_linux_systemd_user_units_with_fixed_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            service_path = home / ".config" / "systemd" / "user" / "tsense-auto-review.service"
            timer_path = home / ".config" / "systemd" / "user" / "tsense-auto-review.timer"
            home.mkdir()
            project_root.mkdir()
            service_path.parent.mkdir(parents=True)
            service_path.write_text("[Service]\n", encoding="utf-8")
            timer_path.write_text("[Timer]\n", encoding="utf-8")
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "linux"):
                with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": str(Path(tmp) / "runtime")}, clear=False):
                    with patch.object(
                        dashboard_server,
                        "shutil",
                        SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                        create=True,
                    ):
                        with patch.object(dashboard_server.Path, "home", return_value=home):
                            with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                                with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                    result = dashboard_server.run_desk_action(
                                        "schedule_remove_dry_run",
                                        body={"confirm": True},
                                    )

        self.assertEqual(result["status"], "success")
        self.assertIn(["systemctl", "--user", "disable", "--now", "tsense-auto-review.timer"], calls)
        self.assertIn(["systemctl", "--user", "daemon-reload"], calls)
        self.assertFalse(service_path.exists())
        self.assertFalse(timer_path.exists())


    def test_schedule_remove_dry_run_disables_legacy_linux_systemd_user_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            project_root = Path(tmp) / "repo"
            service_path = home / ".config" / "systemd" / "user" / "tgcs-jobs-fast-dry-run.service"
            timer_path = home / ".config" / "systemd" / "user" / "tgcs-jobs-fast-dry-run.timer"
            home.mkdir()
            project_root.mkdir()
            service_path.parent.mkdir(parents=True)
            service_path.write_text("[Service]\n", encoding="utf-8")
            timer_path.write_text("[Timer]\n", encoding="utf-8")
            (project_root / "tgcs").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with patch.object(dashboard_server.sys, "platform", "linux"):
                with patch.dict(dashboard_server.os.environ, {"XDG_RUNTIME_DIR": str(Path(tmp) / "runtime")}, clear=False):
                    with patch.object(
                        dashboard_server,
                        "shutil",
                        SimpleNamespace(which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None),
                        create=True,
                    ):
                        with patch.object(dashboard_server.Path, "home", return_value=home):
                            with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                                with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                                    result = dashboard_server.run_desk_action(
                                        "schedule_remove_dry_run",
                                        body={"confirm": True},
                                    )

        self.assertEqual(result["status"], "success")
        self.assertIn(["systemctl", "--user", "disable", "--now", "tgcs-jobs-fast-dry-run.timer"], calls)
        self.assertFalse(service_path.exists())
        self.assertFalse(timer_path.exists())


    def test_desk_scheduler_status_queries_fixed_task_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            write_enabled_jobs_profile(project_root)
            completed = subprocess.CompletedProcess(["schtasks.exe"], 0, stdout="TaskName: T-Sense auto review\n", stderr="")

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed) as run_mock:
                        status = dashboard_server.desk_scheduler_status()

        args = run_mock.call_args.args[0]
        self.assertEqual(args, ["schtasks.exe", "/Query", "/TN", dashboard_server.DESK_SCHEDULER_TASK_NAME])
        self.assertTrue(status["available"])
        self.assertTrue(status["installed"])
        self.assertEqual(status["status"], "installed")
        self.assertIn("every 15 minutes", status["detail"])


    def test_desk_scheduler_status_detects_legacy_windows_task_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            write_enabled_jobs_profile(project_root)
            calls: list[list[str]] = []

            def fake_run(args):
                calls.append(args)
                if args[args.index("/TN") + 1] == "TGCS jobs-fast dry-run":
                    return subprocess.CompletedProcess(args, 0, stdout="TaskName: TGCS jobs-fast dry-run\n", stderr="")
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="ERROR: missing\n")

            with patch.object(dashboard_server.sys, "platform", "win32"):
                with patch.object(dashboard_server, "PROJECT_ROOT", project_root), patch.object(dashboard_server, "CODE_ROOT", project_root):
                    with patch.object(dashboard_server, "_run_scheduler_command", side_effect=fake_run):
                        status = dashboard_server.desk_scheduler_status()

        self.assertTrue(status["installed"])
        self.assertTrue(status["legacy_task_name"])
        self.assertEqual(status["task_name"], "TGCS jobs-fast dry-run")
        self.assertEqual(calls[0], ["schtasks.exe", "/Query", "/TN", dashboard_server.DESK_SCHEDULER_TASK_NAME])
        self.assertEqual(calls[1], ["schtasks.exe", "/Query", "/TN", "TGCS jobs-fast dry-run"])


    def test_desk_scheduler_status_reports_missing_task_without_leaking_output(self):
        completed = subprocess.CompletedProcess(
            ["schtasks.exe"],
            1,
            stdout="",
            stderr="ERROR: The system cannot find the file specified.\n",
        )

        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(dashboard_server, "_run_scheduler_command", return_value=completed):
                status = dashboard_server.desk_scheduler_status()

        self.assertTrue(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "not_installed")
        self.assertEqual(status["detail"], "Automatic AI reviews are off.")
        self.assertNotIn("ERROR", json.dumps(status))


    def test_desk_scheduler_status_handles_timeout(self):
        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(
                dashboard_server,
                "_run_scheduler_command",
                side_effect=subprocess.TimeoutExpired(cmd=["schtasks.exe"], timeout=30),
            ):
                status = dashboard_server.desk_scheduler_status()

        self.assertTrue(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "unknown")
        self.assertIn("timed out", status["detail"])


    def test_desk_scheduler_status_handles_missing_schtasks(self):
        with patch.object(dashboard_server.sys, "platform", "win32"):
            with patch.object(dashboard_server, "_run_scheduler_command", side_effect=OSError("not found")):
                status = dashboard_server.desk_scheduler_status()

        self.assertFalse(status["available"])
        self.assertFalse(status["installed"])
        self.assertEqual(status["status"], "unavailable")
        self.assertNotIn("not found", json.dumps(status))


    def test_desk_scheduler_status_http_endpoint_requires_loopback(self):
        class FakeHandler:
            path = "/api/desk/scheduler-status"
            status = None
            payload = None
            client_address = ("192.168.1.10", 51000)

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(dashboard_server, "desk_scheduler_status") as status_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        status_mock.assert_not_called()
        self.assertEqual(handler.status, HTTPStatus.BAD_REQUEST)
        self.assertIn("localhost", handler.payload["error"])


    def test_desk_scheduler_status_http_endpoint_returns_status(self):
        class FakeHandler:
            path = "/api/desk/scheduler-status"
            status = None
            payload = None
            client_address = ("127.0.0.1", 51000)

            def _json(self, status, payload):
                self.status = status
                self.payload = payload

        with patch.object(
            dashboard_server,
            "desk_scheduler_status",
            return_value={
                "schema_version": "desk_scheduler_status_v1",
                "available": True,
                "installed": False,
                "status": "not_installed",
                "task_label": "jobs-fast AI review",
                "interval_minutes": 15,
                "detail": "Automatic AI reviews are off.",
                "next_action": "Turn on auto review.",
                "checked_at": "2026-05-10T00:00:00Z",
            },
        ) as status_mock:
            handler = FakeHandler()
            dashboard_server.DashboardHandler.do_GET(handler)

        status_mock.assert_called_once()
        self.assertEqual(handler.status, HTTPStatus.OK)
        self.assertEqual(handler.payload["scheduler"]["schema_version"], "desk_scheduler_status_v1")



if __name__ == "__main__":
    unittest.main()
