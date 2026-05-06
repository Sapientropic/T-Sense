import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from scripts import scan


def _make_mock_message(msg_id: int, date_str: str, text: str = ""):
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.sender_id = None
    msg.media = None
    msg.reply_to = None
    if date_str:
        text_date = date_str
        if text_date.endswith("Z"):
            text_date = f"{text_date[:-1]}+00:00"
        msg.date = datetime.fromisoformat(text_date)
    else:
        msg.date = None
    return msg


class AsyncIteratorMock:
    """Wrap a list as an async iterator for mocking iter_dialogs()."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


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

    def test_channel_read_doubles_limit_until_result_is_not_saturated(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        batch1 = [
            _make_mock_message(3, "2026-05-06T08:00:00+00:00"),
            _make_mock_message(2, "2026-05-06T07:30:00+00:00"),
        ]
        batch2 = [
            _make_mock_message(3, "2026-05-06T08:00:00+00:00"),
            _make_mock_message(2, "2026-05-06T07:30:00+00:00"),
            _make_mock_message(1, "2026-05-06T06:00:00+00:00"),
        ]

        client = MagicMock()
        client.get_messages = AsyncMock(side_effect=[batch1, batch2])

        result = asyncio.run(
            scan.read_channel(client, "entity", "jobs", cutoff, 2, 4)
        )

        self.assertFalse(result.incomplete)
        self.assertEqual(result.raw_count, 3)
        self.assertEqual([m["id"] for m in result.messages], [3, 2])

    def test_channel_read_reports_incomplete_when_max_limit_is_still_saturated(self):
        cutoff = datetime(2026, 5, 6, 7, 30, tzinfo=timezone.utc)
        msgs = [
            _make_mock_message(4, "2026-05-06T09:00:00+00:00"),
            _make_mock_message(3, "2026-05-06T08:00:00+00:00"),
            _make_mock_message(2, "2026-05-06T07:30:00+00:00"),
            _make_mock_message(1, "2026-05-06T06:00:00+00:00"),
        ]

        client = MagicMock()
        client.get_messages = AsyncMock(side_effect=[msgs[:2], msgs])

        result = asyncio.run(
            scan.read_channel(client, "entity", "jobs", cutoff, 2, 4)
        )

        self.assertTrue(result.incomplete)
        self.assertEqual(result.raw_count, 4)

    def test_load_channel_list_trims_whitespace_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "channels.txt"
            path.write_text(
                "\n# comment\n  jobs_a  \n\njobs_b\n", encoding="utf-8"
            )

            self.assertEqual(
                scan.load_channel_list(path), ["jobs_a", "jobs_b"]
            )

    def test_resolve_entity_by_username(self):
        entity = MagicMock()
        client = MagicMock()
        client.get_entity = AsyncMock(return_value=entity)

        result = asyncio.run(scan.resolve_entity(client, "remote_italic"))
        self.assertEqual(result, entity)

    def test_resolve_entity_by_display_name(self):
        entity = MagicMock()
        entity.username = "remote_italic"

        dialog = MagicMock()
        dialog.name = "Remote Italic"
        dialog.entity = entity

        client = MagicMock()
        client.get_entity = AsyncMock(side_effect=Exception("not found"))
        client.iter_dialogs = MagicMock(return_value=AsyncIteratorMock([dialog]))

        result = asyncio.run(scan.resolve_entity(client, "Remote Italic"))
        self.assertEqual(result, entity)

    def test_resolve_entity_raises_on_unknown(self):
        client = MagicMock()
        client.get_entity = AsyncMock(side_effect=Exception("not found"))
        client.iter_dialogs = MagicMock(return_value=AsyncIteratorMock([]))

        with self.assertRaises(scan.ScanError):
            asyncio.run(scan.resolve_entity(client, "nonexistent_channel"))

    def test_message_to_dict_extracts_media_fields(self):
        msg = MagicMock()
        msg.id = 42
        msg.date = datetime(2026, 5, 6, 8, 0, tzinfo=timezone.utc)
        msg.text = "hello"
        msg.sender_id = 123
        msg.reply_to = None
        msg.voice = False
        msg.video = False

        # Use a real MessageMediaPhoto instance for isinstance check
        from telethon.tl.types import MessageMediaPhoto as RealPhoto

        msg.media = RealPhoto(photo=MagicMock(), spoiler=False)

        result = scan.message_to_dict(msg, "test_channel")
        self.assertTrue(result["has_photo"])
        self.assertEqual(result["media_type"], "MessageMediaPhoto")
        self.assertEqual(result["media_group"], "photo")
        self.assertNotIn("media_path", result)


if __name__ == "__main__":
    unittest.main()
