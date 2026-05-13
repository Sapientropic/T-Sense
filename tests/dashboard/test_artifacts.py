import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_server, desk_artifacts


class DashboardArtifactTests(unittest.TestCase):
    def test_dashboard_server_reexports_artifact_helpers(self):
        self.assertIs(dashboard_server.DashboardArtifactError, desk_artifacts.DashboardArtifactError)
        self.assertTrue(dashboard_server.is_dashboard_report_artifact_name("report.html"))
        self.assertTrue(desk_artifacts.is_dashboard_report_artifact_name("report.html"))


    def test_resolve_run_artifact_allows_encoded_output_runs_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            report = artifact_root / "run-1" / "report.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            resolved = dashboard_server.resolve_run_artifact_path(
                "output%2Fruns%2Frun-1%2Freport.html",
                artifact_root=artifact_root,
            )

        self.assertEqual(resolved, report.resolve())


    def test_resolve_run_artifact_allows_named_report_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            report = artifact_root / "run-1" / "jobs-fast-signal-report-2026-05-09-1225.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            resolved = dashboard_server.resolve_run_artifact_path(
                "output/runs/run-1/jobs-fast-signal-report-2026-05-09-1225.html",
                artifact_root=artifact_root,
            )

        self.assertEqual(resolved, report.resolve())


    def test_resolve_run_artifact_allows_named_brief_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            report = artifact_root / "run-1" / "market-news-signal-brief-2026-05-09-1225.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>brief</html>", encoding="utf-8")

            resolved = dashboard_server.resolve_run_artifact_path(
                "output/runs/run-1/market-news-signal-brief-2026-05-09-1225.html",
                artifact_root=artifact_root,
            )

        self.assertEqual(resolved, report.resolve())


    def test_resolve_run_artifact_allows_custom_output_dir_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "out" / "runs"
            report = artifact_root / "run-1" / "report.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            resolved = dashboard_server.resolve_run_artifact_path(
                "out/runs/run-1/report.html",
                artifact_root=artifact_root,
            )

        self.assertEqual(resolved, report.resolve())


    def test_resolve_run_artifact_defaults_to_output_dir_from_requested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "out" / "runs" / "run-1" / "report.html"
            report.parent.mkdir(parents=True)
            report.write_text("<html>report</html>", encoding="utf-8")

            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                resolved = dashboard_server.resolve_run_artifact_path("out/runs/run-1/report.html")

        self.assertEqual(resolved, report.resolve())


    def test_resolve_run_artifact_rejects_raw_scan_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            scan = artifact_root / "run-1" / "scan.jsonl"
            scan.parent.mkdir(parents=True)
            scan.write_text('{"text":"raw"}\n', encoding="utf-8")

            with self.assertRaises(dashboard_server.DashboardArtifactError):
                dashboard_server.resolve_run_artifact_path(
                    "output/runs/run-1/scan.jsonl",
                    artifact_root=artifact_root,
                )


    def test_resolve_run_artifact_rejects_non_report_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            other = artifact_root / "run-1" / "other.html"
            other.parent.mkdir(parents=True)
            other.write_text("<html>other</html>", encoding="utf-8")

            with self.assertRaises(dashboard_server.DashboardArtifactError):
                dashboard_server.resolve_run_artifact_path(
                    "output/runs/run-1/other.html",
                    artifact_root=artifact_root,
                )


    def test_resolve_run_artifact_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_root = root / "output" / "runs"
            artifact_root.mkdir(parents=True)
            (root / "output" / "secret.html").write_text("secret", encoding="utf-8")

            with self.assertRaises(dashboard_server.DashboardArtifactError):
                dashboard_server.resolve_run_artifact_path(
                    "output/runs/../secret.html",
                    artifact_root=artifact_root,
                )


    def test_resolve_static_path_rejects_sibling_prefix_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            static_dir = root / "dist"
            sibling = root / "dist_evil"
            static_dir.mkdir()
            sibling.mkdir()
            index = static_dir / "index.html"
            secret = sibling / "secret.txt"
            index.write_text("index", encoding="utf-8")
            secret.write_text("secret", encoding="utf-8")

            resolved = dashboard_server.resolve_static_path("/../dist_evil/secret.txt", static_dir=static_dir)

        self.assertEqual(resolved, index.resolve())



if __name__ == "__main__":
    unittest.main()
