import subprocess
import unittest
import json
from unittest.mock import patch

from scripts import dashboard_server


class DashboardActionTests(unittest.TestCase):
    def test_run_desk_action_redacts_stdout_and_stderr_fallback_details(self):
        secret_token = "123456:ABCDEF_secret"
        secret_line = (
            f"OPENAI_API_KEY=sk-localSecret12345 token={secret_token} "
            "argv=['tgcs','doctor'] C:\\Users\\Administrator\\private\\state"
        )

        cases = [
            subprocess.CompletedProcess(["tgcs"], 0, stdout=secret_line, stderr=""),
            subprocess.CompletedProcess(["tgcs"], 1, stdout="", stderr=secret_line),
        ]
        for completed in cases:
            with self.subTest(returncode=completed.returncode):
                with patch.object(dashboard_server.subprocess, "run", return_value=completed):
                    result = dashboard_server.run_desk_action("doctor_jobs")

                rendered = json.dumps(result, ensure_ascii=False)
                self.assertNotIn(secret_token, rendered)
                self.assertNotIn("sk-localSecret12345", rendered)
                self.assertNotIn("C:\\Users\\Administrator", rendered)
                self.assertNotIn("['tgcs','doctor']", rendered)
                self.assertIn("[redacted", result["detail"])


    def test_run_desk_action_hides_python_traceback_from_setup_result(self):
        completed = subprocess.CompletedProcess(
            ["tgcs"],
            1,
            stdout="",
            stderr="Traceback (most recent call last):\n  File \"x.py\", line 1\nRuntimeError: provider exploded",
        )

        with patch.object(dashboard_server.subprocess, "run", return_value=completed):
            result = dashboard_server.run_desk_action("doctor_jobs")

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["detail"], "This setup check could not finish.")
        self.assertNotIn("Traceback", json.dumps(result))



if __name__ == "__main__":
    unittest.main()
