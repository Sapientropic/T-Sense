import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSIX_LAUNCHERS = [
    "setup.sh",
    "scripts/scan.sh",
    "tgcs",
    "signal-desk",
    "Signal Desk.command",
]
SHELL_SYNTAX_FILES = [
    "setup.sh",
    "scripts/scan.sh",
    "tgcs",
    "signal-desk",
    "Signal Desk.command",
]


class PosixLauncherTests(unittest.TestCase):
    def test_gitattributes_pins_platform_line_endings(self):
        text = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

        self.assertIn("*.sh text eol=lf", text)
        self.assertIn("tgcs text eol=lf", text)
        self.assertIn("signal-desk text eol=lf", text)
        self.assertIn("*.bat text eol=crlf", text)

    def test_posix_launchers_are_lf_only(self):
        for rel_path in POSIX_LAUNCHERS:
            data = (PROJECT_ROOT / rel_path).read_bytes()
            self.assertNotIn(b"\r\n", data, rel_path)

    def test_posix_launchers_have_executable_git_mode(self):
        completed = subprocess.run(
            ["git", "ls-files", "--stage", *POSIX_LAUNCHERS],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        modes: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            mode, _, _, path = line.split(maxsplit=3)
            modes[path] = mode

        for rel_path in POSIX_LAUNCHERS:
            self.assertEqual(modes.get(rel_path), "100755", rel_path)

    def test_setup_completion_copy_is_app_first(self):
        text = (PROJECT_ROOT / "setup.sh").read_text(encoding="utf-8")

        self.assertIn("Signal Desk is ready.", text)
        self.assertIn("Next: open Signal Desk with ./signal-desk, then use Start.", text)
        self.assertIn("Advanced CLI users can run ./tgcs --help.", text)
        self.assertIn("Initializing local project defaults (market-news starter)...", text)
        self.assertIn("if ./tgcs init; then", text)
        self.assertNotIn("Setup complete. Next: edit config and run jobs-fast", text)
        self.assertNotIn("Initializing local project defaults (jobs starter)...", text)
        self.assertNotIn("if ./tgcs init --starter jobs; then", text)
        self.assertNotIn("Run:     ./tgcs doctor --profile jobs", text)
        self.assertNotIn("Schedule preview: ./tgcs schedule print --profile-id jobs-fast", text)

    def test_signal_desk_launcher_defaults_to_detached_dashboard(self):
        text = (PROJECT_ROOT / "signal-desk").read_text(encoding="utf-8")

        self.assertIn("TGCS_SIGNAL_DESK_FOREGROUND", text)
        self.assertIn("nohup", text)
        self.assertIn("output/signal-desk.log", text)
        self.assertIn(
            'if [ "${TGCS_SIGNAL_DESK_FOREGROUND:-0}" = "1" ]; then\n'
            '  exec "$ROOT_DIR/tgcs" dashboard --open "$@"\n'
            "fi\n",
            text,
        )
        self.assertLess(
            text.index('if [ "${TGCS_SIGNAL_DESK_FOREGROUND:-0}" = "1" ]; then'),
            text.index('nohup "$ROOT_DIR/tgcs" dashboard --open "$@"'),
        )

    @unittest.skipUnless(shutil.which("bash"), "bash is required for POSIX launcher smoke checks")
    @unittest.skipIf(os.name == "nt", "POSIX launcher smoke runs on Linux/macOS CI")
    def test_signal_desk_launcher_detaches_dashboard_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            root.mkdir()
            (root / ".venv" / "bin").mkdir(parents=True)
            (root / ".venv" / "bin" / "python").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (root / ".tgcs").mkdir()
            (root / ".tgcs" / "sources.json").write_text("{}", encoding="utf-8")
            (root / "signal-desk").write_bytes((PROJECT_ROOT / "signal-desk").read_bytes())
            tgcs_stub = root / "tgcs"
            tgcs_stub.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> tgcs.calls\nsleep 5\n",
                encoding="utf-8",
            )
            for launcher in [root / "signal-desk", tgcs_stub, root / ".venv" / "bin" / "python"]:
                launcher.chmod(0o755)

            result = subprocess.run(
                ["bash", "signal-desk"],
                cwd=root,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                text=True,
                timeout=2,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            deadline = time.monotonic() + 2
            while not (root / "tgcs.calls").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((root / "tgcs.calls").exists())
            self.assertIn("dashboard --open", (root / "tgcs.calls").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("bash"), "bash is required for POSIX launcher syntax checks")
    @unittest.skipIf(os.name == "nt", "POSIX syntax checks run on Linux/macOS CI")
    def test_posix_launchers_pass_bash_syntax_check(self):
        subprocess.run(
            ["bash", "-n", *SHELL_SYNTAX_FILES],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
        )

    @unittest.skipUnless(shutil.which("bash"), "bash is required for setup smoke checks")
    @unittest.skipIf(os.name == "nt", "setup smoke runs on POSIX CI")
    def test_setup_skip_install_smoke_initializes_config_and_jobs_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "checkout"
            root.mkdir()
            (root / "scripts").mkdir()
            (root / "setup.sh").write_bytes((PROJECT_ROOT / "setup.sh").read_bytes())
            (root / "config.example.toml").write_text("[telegram]\napi_id = 0\napi_hash = \"\"\n", encoding="utf-8")
            (root / "scripts" / "scan.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            tgcs_stub = root / "tgcs"
            tgcs_stub.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> tgcs.calls\n",
                encoding="utf-8",
            )
            for launcher in [root / "setup.sh", tgcs_stub, root / "scripts" / "scan.sh"]:
                launcher.chmod(0o755)

            config_dir = Path(tmp) / "config"
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": str(Path(tmp) / "home"),
                "SystemRoot": os.environ.get("SystemRoot", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", os.environ.get("SystemRoot", "")),
                "TEMP": tmp,
                "TMP": tmp,
                "TG_SCANNER_SETUP_SKIP_INSTALL": "1",
                "TG_SCANNER_CONFIG_DIR": str(config_dir),
            }
            result = subprocess.run(
                ["bash", "setup.sh"],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                text=True,
            )

            self.assertTrue((config_dir / "config.toml").exists())
            self.assertTrue((root / "output").is_dir())
            calls = (root / "tgcs.calls").read_text(encoding="utf-8")
            self.assertIn("init", calls)
            self.assertNotIn("init --starter jobs", calls)
            self.assertIn("Signal Desk is ready.", result.stdout)
            self.assertIn("Next: open Signal Desk with ./signal-desk, then use Start.", result.stdout)
            self.assertNotIn("./tgcs quickstart jobs", result.stdout)
            self.assertNotIn("./tgcs doctor --profile jobs", result.stdout)
            self.assertNotIn("./tgcs monitor run --profile-id jobs-fast", result.stdout)


if __name__ == "__main__":
    unittest.main()
