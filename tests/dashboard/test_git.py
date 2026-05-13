import subprocess
import unittest
import json
from contextlib import AbstractContextManager
from unittest.mock import patch

from scripts import dashboard_server, desk_git


class DashboardGitTests(unittest.TestCase):
    def test_dashboard_server_reexports_git_error(self):
        self.assertIs(dashboard_server.DashboardGitError, desk_git.DashboardGitError)


    def test_close_after_use_closes_connection_handle(self):
        class FakeConnection:
            closed = False

            def close(self):
                self.closed = True

        fake = FakeConnection()

        with dashboard_server.close_after_use(fake) as conn:
            self.assertIs(conn, fake)
            self.assertIsInstance(dashboard_server.close_after_use(fake), AbstractContextManager)

        self.assertTrue(fake.closed)


    def test_run_git_wraps_timeout(self):
        with patch.object(
            dashboard_server.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["git", "fetch"], timeout=1),
        ):
            with self.assertRaises(dashboard_server.DashboardGitError) as raised:
                dashboard_server._run_git(["fetch"], timeout=1)

        self.assertIn("git fetch timed out", str(raised.exception))


    def test_run_git_wraps_missing_git_binary(self):
        with patch.object(dashboard_server.subprocess, "run", side_effect=OSError("git not found")):
            with self.assertRaises(dashboard_server.DashboardGitError) as raised:
                dashboard_server._run_git(["status"])

        self.assertIn("Unable to run git", str(raised.exception))


    def test_update_status_blocks_pull_when_worktree_is_dirty(self):
        outputs = {
            ("rev-parse", "--abbrev-ref", "HEAD"): "main\n",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/main\n",
            ("config", "--get", "remote.origin.url"): "git@github.com:Sapientropic/T-Sense.git\n",
            ("status", "--porcelain"): " M dashboard/src/main.tsx\n",
            ("fetch", "--prune", "origin"): "",
            ("rev-parse", "--short", "HEAD"): "abc123\n",
            ("rev-parse", "--short", "origin/main"): "def456\n",
            ("rev-list", "--left-right", "--count", "HEAD...origin/main"): "0\t2\n",
        }

        def fake_run(args, *, timeout=dashboard_server.GIT_TIMEOUT_SECONDS):
            return subprocess.CompletedProcess(args, 0, stdout=outputs[tuple(args)])

        with patch.object(dashboard_server, "_run_git", side_effect=fake_run):
            status = dashboard_server._git_update_status(fetch=True)

        self.assertEqual(status["status"], "behind")
        self.assertTrue(status["dirty"])
        self.assertFalse(status["pull_allowed"])
        self.assertEqual(status["dirty_count"], 1)
        self.assertEqual(status["repo_url"], "https://github.com/Sapientropic/T-Sense")
        self.assertIn("Commit or stash", status["message"])


    def test_git_update_status_redacts_remote_and_fetch_error(self):
        secret_token = "123456:ABCDEF_secret"
        outputs = {
            ("rev-parse", "--abbrev-ref", "HEAD"): "main\n",
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"): "origin/main\n",
            ("config", "--get", "remote.origin.url"): "https://ghp_private@github.com/Sapientropic/T-Sense.git\n",
            ("status", "--porcelain"): "",
            ("rev-parse", "--short", "HEAD"): "abc123\n",
            ("rev-parse", "--short", "origin/main"): "def456\n",
        }

        def fake_run(args, *, timeout=dashboard_server.GIT_TIMEOUT_SECONDS):
            if args == ["fetch", "--prune", "origin"]:
                return subprocess.CompletedProcess(
                    args,
                    1,
                    stdout="",
                    stderr=(
                        f"fatal token {secret_token} OPENAI_API_KEY=sk-localSecret12345 "
                        "argv=['git','fetch'] C:\\Users\\Administrator\\private\\repo"
                    ),
                )
            return subprocess.CompletedProcess(args, 0, stdout=outputs[tuple(args)])

        with patch.object(dashboard_server, "_run_git", side_effect=fake_run):
            status = dashboard_server._git_update_status(fetch=True)

        rendered = json.dumps(status, ensure_ascii=False)
        self.assertEqual(status["status"], "fetch_failed")
        self.assertEqual(status["repo_url"], "https://github.com/Sapientropic/T-Sense")
        self.assertNotIn("remote_url", status)
        self.assertNotIn("ghp_private", rendered)
        self.assertNotIn(secret_token, rendered)
        self.assertNotIn("sk-localSecret12345", rendered)
        self.assertNotIn("C:\\Users\\Administrator", rendered)
        self.assertNotIn("['git','fetch']", rendered)


    def test_pull_latest_uses_fast_forward_only_after_clean_check(self):
        before = {
            "dirty": False,
            "status": "behind",
            "pull_allowed": True,
            "message": "1 upstream commit available.",
        }
        after = {
            "dirty": False,
            "status": "up_to_date",
            "pull_allowed": False,
            "message": "Local branch is up to date with upstream.",
        }

        with patch.object(dashboard_server, "_git_update_status", side_effect=[before, after]):
            with patch.object(
                dashboard_server,
                "_run_git",
                return_value=subprocess.CompletedProcess(["pull"], 0, stdout="Fast-forward\n"),
            ) as run_mock:
                result = dashboard_server._git_pull_latest()

        run_mock.assert_called_once_with(["pull", "--ff-only"], timeout=60)
        self.assertEqual(result["status"], "up_to_date")
        self.assertEqual(result["pull_output"], "Fast-forward")



if __name__ == "__main__":
    unittest.main()
