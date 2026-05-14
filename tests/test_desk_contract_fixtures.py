import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_server


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "contracts" / "desk_boundary_v1.json"
SELECTED_ACTION_IDS = {
    "sources_probe_access",
    "monitor_jobs_dry_run",
    "schedule_install_dry_run",
    "login_human",
    "live_delivery_human",
}
ACTION_CONTRACT_KEYS = ("schema_version", "action_id", "group", "run_mode", "display_command")
ACTION_DISPLAY_KEYS = ("title", "detail", "next_action")
ACTION_RESULT_CONTRACT_KEYS = (
    "schema_version",
    "action_id",
    "status",
    "display_command",
    "exit_code",
    "artifact_path",
)
ACTION_RESULT_DISPLAY_KEYS = ("title", "detail", "next_action")


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def selected_desk_actions(payload: dict) -> dict:
    return {
        "schema_version": payload.get("schema_version"),
        "actions": [
            action
            for action in payload.get("actions", [])
            if isinstance(action, dict) and action.get("action_id") in SELECTED_ACTION_IDS
        ],
    }


def desk_action_contract(payload: dict) -> dict:
    return {
        "schema_version": payload.get("schema_version"),
        "actions": [
            {key: action.get(key) for key in ACTION_CONTRACT_KEYS}
            for action in payload.get("actions", [])
            if isinstance(action, dict)
        ],
    }


def action_result_contract(result: dict) -> dict:
    return {key: result.get(key) for key in ACTION_RESULT_CONTRACT_KEYS}


def assert_display_fields(testcase: unittest.TestCase, payload: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        with testcase.subTest(display_key=key):
            testcase.assertIsInstance(payload.get(key), str)
            testcase.assertTrue(payload[key].strip())


def write_registry(root: Path) -> None:
    registry_path = root / ".tgcs" / "sources.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "source_registry_v1",
                "sources": [
                    {
                        "source_id": "telegram:jobs_good",
                        "username": "jobs_good",
                        "channel_id": None,
                        "label": "Jobs Good",
                        "topics": ["jobs"],
                        "priority": "high",
                        "expected_language": "en",
                        "scan_window_hours": 2,
                        "enabled": True,
                        "notes": "",
                    },
                    {
                        "source_id": "telegram:jobs_noise",
                        "username": "jobs_noise",
                        "channel_id": None,
                        "label": "Jobs Noise",
                        "topics": ["jobs", "watch"],
                        "priority": "low",
                        "expected_language": "en",
                        "scan_window_hours": 24,
                        "enabled": False,
                        "notes": "",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


class DeskContractFixtureTests(unittest.TestCase):
    def test_desk_actions_match_allowlist_fixture_without_backend_fields(self):
        fixture = load_fixture()
        payload = selected_desk_actions(dashboard_server.desk_actions())

        self.assertEqual(desk_action_contract(payload), desk_action_contract(fixture["desk_actions"]))
        for action in payload["actions"]:
            assert_display_fields(self, action, ACTION_DISPLAY_KEYS)
        surfaced = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("argv", surfaced)
        self.assertNotIn("artifact_keys", surfaced)
        self.assertNotIn("timeout", surfaced)

    def test_desk_action_result_matches_fixture_without_finished_at(self):
        fixture = load_fixture()
        result = dashboard_server._desk_action_result(
            "monitor_jobs_dry_run",
            status="success",
            title="AI review complete",
            detail="Report ready.",
            next_action="Open the generated report.",
            exit_code=0,
            artifact_path="output/runs/run-desk-contract/report.html",
        )

        self.assertEqual(action_result_contract(result), action_result_contract(fixture["desk_action_result"]))
        assert_display_fields(self, result, ACTION_RESULT_DISPLAY_KEYS)

    def test_desk_sources_match_registry_fixture_without_local_absolute_path(self):
        fixture = load_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_registry(root)
            with patch.object(dashboard_server, "PROJECT_ROOT", root):
                payload = dashboard_server.desk_sources()

        self.assertEqual(payload, fixture["desk_sources"])
        surfaced = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for denied in fixture["denied_strings"]:
            with self.subTest(denied=denied):
                self.assertNotIn(denied, surfaced)


if __name__ == "__main__":
    unittest.main()
