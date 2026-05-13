import json
import unittest
from pathlib import Path

from scripts import dashboard_server


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "contracts" / "desk_source_access_health_v1.summary.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class DeskSourceAccessContractTests(unittest.TestCase):
    def test_source_access_action_summary_matches_fixture_without_per_source_private_data(self):
        fixture = load_fixture()
        full_health = dashboard_server._source_access_summary(
            [
                {
                    "source_id": "telegram:jobs_good",
                    "label": "Jobs Good",
                    "channel": "jobs_good",
                    "status": "accessible",
                    "reason": "recent_message_found",
                    "scan_window_hours": 2,
                    "detail": "Telegram access works for the current scan window.",
                    "latest_message_at": "2026-05-13T00:00:00Z",
                },
                {
                    "source_id": "telegram:jobs_quiet",
                    "label": "Jobs Quiet",
                    "channel": "jobs_quiet",
                    "status": "quiet",
                    "reason": "empty_recent_window",
                    "scan_window_hours": 24,
                    "detail": "RAW_SOURCE_ACCESS_SHOULD_NOT_SURFACE",
                    "path": "C:/Users/Administrator/private/source-access.json",
                },
                {
                    "source_id": "telegram:jobs_private",
                    "label": "Jobs Private",
                    "channel": "jobs_private",
                    "status": "inaccessible",
                    "reason": "cannot_resolve_entity",
                    "scan_window_hours": 24,
                    "detail": "SECRET_SOURCE_ACCESS_TOKEN_SHOULD_NOT_SURFACE",
                    "argv": ["--private-argv"],
                },
            ],
            total_source_count=4,
            truncated_count=1,
            checked_at="2026-05-13T00:00:00Z",
        )

        summary = dashboard_server._source_access_action_summary(full_health)

        self.assertEqual(summary, fixture["source_access"])
        surfaced = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        for denied in fixture["denied_strings"]:
            with self.subTest(denied=denied):
                self.assertNotIn(denied, surfaced)


if __name__ == "__main__":
    unittest.main()
