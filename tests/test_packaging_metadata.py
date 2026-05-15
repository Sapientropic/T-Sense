import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def load_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def requirement_lines(path: str) -> list[str]:
    return [
        line.strip()
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class PackagingMetadataTests(unittest.TestCase):
    def test_pyproject_exposes_only_the_canonical_cli_entrypoint(self):
        project = load_pyproject()["project"]

        self.assertEqual(project["requires-python"], ">=3.12")
        self.assertEqual(project["license"], "AGPL-3.0-or-later")
        self.assertEqual(project["license-files"], ["LICENSE"])
        self.assertEqual(project["scripts"], {"tgcs": "scripts.tgcs:main"})
        self.assertNotIn("signal-desk", project["scripts"])

    def test_pyproject_dependency_groups_match_requirement_files(self):
        project = load_pyproject()["project"]

        self.assertEqual(project["dependencies"], requirement_lines("requirements.txt"))
        self.assertEqual(project["optional-dependencies"]["llm"], requirement_lines("requirements-llm.txt"))
        self.assertIn("pypdf==6.10.2", project["optional-dependencies"]["llm"])
        self.assertEqual(
            project["optional-dependencies"]["desktop"],
            requirement_lines("requirements-desktop.txt"),
        )
        self.assertEqual(project["optional-dependencies"]["dev"], requirement_lines("requirements-dev.txt"))

    def test_setuptools_package_scope_excludes_local_runtime_and_dashboard_assets(self):
        setuptools_config = load_pyproject()["tool"]["setuptools"]
        config = setuptools_config["packages"]["find"]

        self.assertIs(setuptools_config["include-package-data"], False)
        self.assertEqual(config["include"], ["scripts*", "templates*", "profiles*", "channel_lists*"])
        self.assertIn("dashboard*", config["exclude"])
        self.assertIn("docs*", config["exclude"])
        self.assertEqual(
            setuptools_config["package-data"]["templates.demo.fixtures"],
            ["*.json", "*.jsonl", "*.md"],
        )
        self.assertEqual(
            setuptools_config["package-data"]["profiles"],
            ["README.md", "example-airdrop.md", "example.md"],
        )

    def test_manifest_excludes_runtime_state_tests_and_non_public_profiles(self):
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

        self.assertIn("prune .tgcs", manifest)
        self.assertIn("prune tests", manifest)
        self.assertNotIn("profiles/*.md", manifest)
        self.assertNotIn("aleksei-frontend", manifest)

    def test_docker_image_scope_is_local_only_and_state_free(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

        self.assertIn("FROM python:3.13-slim", dockerfile)
        self.assertIn('ENTRYPOINT ["tgcs"]', dockerfile)
        self.assertIn('CMD ["quickstart", "jobs"]', dockerfile)
        self.assertNotIn("COPY .", dockerfile)
        self.assertNotIn("TELEGRAM_API", dockerfile)
        self.assertIn(".tgcs", dockerignore)
        self.assertIn("*.session", dockerignore)
        self.assertIn(".env", dockerignore)
        self.assertIn("dashboard/dist", dockerignore)
        self.assertIn("output", dockerignore)


if __name__ == "__main__":
    unittest.main()
