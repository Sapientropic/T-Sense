import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts import scan


class FakeTg:
    def __init__(self, batches):
        self.batches = batches
        self.calls = []

    def __call__(self, channel, after_date, limit):
        self.calls.append((channel, after_date, limit))
        return self.batches[limit], ""


class ScanTests(unittest.TestCase):
    def test_precise_time_filter_keeps_only_messages_at_or_after_cutoff(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        rows = [
            {"id": 1, "date": "2026-05-06T07:29:59+00:00", "text": "old"},
            {"id": 2, "date": "2026-05-06T07:30:00+00:00", "text": "boundary"},
            {"id": 3, "date": "2026-05-06T08:00:00Z", "text": "new"},
        ]

        kept, skipped = scan.filter_messages(rows, cutoff)

        self.assertEqual([row["id"] for row in kept], [2, 3])
        self.assertEqual(skipped, 0)

    def test_channel_read_doubles_limit_until_tgcli_result_is_not_truncated(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        first = [
            {"id": 3, "date": "2026-05-06T08:00:00+00:00"},
            {"id": 2, "date": "2026-05-06T07:30:00+00:00"},
        ]
        second = first + [{"id": 1, "date": "2026-05-06T06:00:00+00:00"}]
        fake = FakeTg({2: first, 4: second})

        result = scan.read_channel_complete(
            channel="jobs",
            cutoff=cutoff,
            initial_limit=2,
            max_limit=4,
            run_tg=fake,
        )

        self.assertEqual(fake.calls, [("jobs", "2026-05-06", 2), ("jobs", "2026-05-06", 4)])
        self.assertEqual([row["id"] for row in result.messages], [3, 2])
        self.assertEqual(result.raw_count, 3)
        self.assertFalse(result.incomplete)

    def test_channel_read_reports_incomplete_when_max_limit_is_still_saturated(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        rows = [
            {"id": 4, "date": "2026-05-06T09:00:00+00:00"},
            {"id": 3, "date": "2026-05-06T08:00:00+00:00"},
            {"id": 2, "date": "2026-05-06T07:30:00+00:00"},
            {"id": 1, "date": "2026-05-06T06:00:00+00:00"},
        ]
        fake = FakeTg({2: rows[:2], 4: rows})

        result = scan.read_channel_complete(
            channel="jobs",
            cutoff=cutoff,
            initial_limit=2,
            max_limit=4,
            run_tg=fake,
        )

        self.assertTrue(result.incomplete)
        self.assertEqual(result.raw_count, 4)

    def test_load_channel_list_trims_whitespace_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "channels.txt"
            path.write_text("\n# comment\n  jobs_a  \n\njobs_b\n", encoding="utf-8")

            self.assertEqual(scan.load_channel_list(path), ["jobs_a", "jobs_b"])


if __name__ == "__main__":
    unittest.main()
