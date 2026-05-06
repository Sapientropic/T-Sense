"""Cross-platform Telegram channel scanner.

tgcli currently accepts date-only --after/--before values. This wrapper
over-reads from the UTC calendar day containing the precise cutoff, then
filters JSONL locally. It also treats a saturated --limit as incomplete and
keeps increasing the limit instead of silently dropping messages.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

DEFAULT_HOURS = 24
DEFAULT_INITIAL_LIMIT = 200
DEFAULT_MAX_LIMIT = 5000
DEFAULT_DELAY_SECONDS = 1.0


class ScanError(Exception):
    pass


@dataclass
class ChannelResult:
    channel: str
    messages: list[dict]
    raw_count: int
    skipped_invalid_json: int
    skipped_missing_date: int
    limit: int
    incomplete: bool
    stderr: str = ""


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def parse_message_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_since(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise argparse.ArgumentTypeError("--since cannot be empty")
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--since must be ISO-8601, e.g. 2026-05-06T07:30:00Z"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def cutoff_from_args(hours: int, since: datetime | None) -> datetime:
    if since is not None:
        return since
    return datetime.now(UTC) - timedelta(hours=hours)


def load_channel_list(path: Path) -> list[str]:
    channels: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            channels.append(line)
    return channels


def parse_jsonl(text: str) -> tuple[list[dict], int]:
    messages: list[dict] = []
    skipped = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if isinstance(parsed, dict):
            messages.append(parsed)
        else:
            skipped += 1
    return messages, skipped


def filter_messages(messages: Iterable[dict], cutoff: datetime) -> tuple[list[dict], int]:
    kept: list[dict] = []
    skipped_missing_date = 0
    cutoff_utc = cutoff.astimezone(UTC)
    for message in messages:
        message_date = parse_message_date(message.get("date"))
        if message_date is None:
            skipped_missing_date += 1
            continue
        if message_date >= cutoff_utc:
            kept.append(message)
    return kept, skipped_missing_date


def run_tg_read(channel: str, after_date: str, limit: int) -> tuple[list[dict], str]:
    completed = subprocess.run(
        ["tg", "read", channel, "--after", after_date, "--limit", str(limit)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise ScanError(completed.stderr.strip() or f"tg read failed for {channel}")
    messages, skipped = parse_jsonl(completed.stdout)
    stderr = completed.stderr.strip()
    if skipped:
        stderr = f"{stderr}\nSkipped {skipped} invalid JSONL lines.".strip()
    return messages, stderr


def read_channel_complete(
    channel: str,
    cutoff: datetime,
    initial_limit: int,
    max_limit: int,
    run_tg: Callable[[str, str, int], tuple[list[dict], str]] = run_tg_read,
) -> ChannelResult:
    if initial_limit > max_limit:
        raise ValueError("initial_limit cannot exceed max_limit")

    after_date = cutoff.astimezone(UTC).date().isoformat()
    limit = initial_limit

    while True:
        raw_messages, stderr = run_tg(channel, after_date, limit)
        filtered, skipped_missing_date = filter_messages(raw_messages, cutoff)
        raw_count = len(raw_messages)
        saturated = raw_count >= limit

        if not saturated:
            return ChannelResult(
                channel=channel,
                messages=filtered,
                raw_count=raw_count,
                skipped_invalid_json=0,
                skipped_missing_date=skipped_missing_date,
                limit=limit,
                incomplete=False,
                stderr=stderr,
            )

        if limit >= max_limit:
            return ChannelResult(
                channel=channel,
                messages=filtered,
                raw_count=raw_count,
                skipped_invalid_json=0,
                skipped_missing_date=skipped_missing_date,
                limit=limit,
                incomplete=True,
                stderr=stderr,
            )

        limit = min(limit * 2, max_limit)


def write_jsonl(path: Path, messages: Iterable[dict]) -> int:
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for message in messages:
            handle.write(json.dumps(message, ensure_ascii=False))
            handle.write("\n")
            count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan Telegram channels with tgcli.")
    parser.add_argument("channel_list", type=Path, help="Text file with one channel username per line")
    parser.add_argument(
        "hours",
        nargs="?",
        type=positive_int,
        default=DEFAULT_HOURS,
        help=f"Look back this many hours (default: {DEFAULT_HOURS})",
    )
    parser.add_argument(
        "--since",
        type=parse_since,
        help="Precise UTC/local ISO-8601 cutoff. Overrides hours. Example: 2026-05-06T07:30:00Z",
    )
    parser.add_argument(
        "--initial-limit",
        type=positive_int,
        default=positive_int(os.environ.get("SCAN_INITIAL_LIMIT", str(DEFAULT_INITIAL_LIMIT))),
        help=f"Initial tg read limit per channel (default: {DEFAULT_INITIAL_LIMIT})",
    )
    parser.add_argument(
        "--max-limit",
        type=positive_int,
        default=positive_int(os.environ.get("SCAN_MAX_LIMIT", str(DEFAULT_MAX_LIMIT))),
        help=f"Maximum tg read limit per channel before reporting incomplete (default: {DEFAULT_MAX_LIMIT})",
    )
    parser.add_argument(
        "--delay",
        type=non_negative_float,
        default=non_negative_float(os.environ.get("SCAN_DELAY", str(DEFAULT_DELAY_SECONDS))),
        help=f"Delay between channels in seconds (default: {DEFAULT_DELAY_SECONDS})",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Output directory")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Exit 0 even if a channel reaches --max-limit and may be incomplete",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.channel_list.exists():
        print(f"Error: Channel list not found: {args.channel_list}", file=sys.stderr)
        return 1
    if args.initial_limit > args.max_limit:
        print("Error: --initial-limit cannot exceed --max-limit", file=sys.stderr)
        return 1
    if shutil.which("tg") is None:
        print("Error: tg command not found. Run setup first and activate the venv.", file=sys.stderr)
        return 1

    try:
        channels = load_channel_list(args.channel_list)
    except OSError as exc:
        print(f"Error: Failed to read channel list: {exc}", file=sys.stderr)
        return 1

    cutoff = cutoff_from_args(args.hours, args.since)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"scan_{timestamp}.jsonl"
    errors_path = args.output_dir / f"scan_{timestamp}.errors.log"

    print(f"Scan started: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Precise cutoff: {cutoff.isoformat()}")
    print(f"tgcli date floor: {cutoff.astimezone(UTC).date().isoformat()}")
    print(f"Channel list: {args.channel_list}")
    print(f"Output: {output_path}")
    print("---")

    failures = 0
    incomplete = 0
    total_written = 0
    with errors_path.open("w", encoding="utf-8", newline="\n") as errors:
        for index, channel in enumerate(channels, start=1):
            print(f"[{index}] Reading: {channel}")
            try:
                result = read_channel_complete(
                    channel=channel,
                    cutoff=cutoff,
                    initial_limit=args.initial_limit,
                    max_limit=args.max_limit,
                )
            except ScanError as exc:
                failures += 1
                errors.write(f"[{channel}] ERROR: {exc}\n")
                print(f"  Failed: {channel} (see {errors_path.name})", file=sys.stderr)
            else:
                written = write_jsonl(output_path, result.messages)
                total_written += written
                if result.stderr:
                    errors.write(f"[{channel}] STDERR: {result.stderr}\n")
                if result.skipped_missing_date:
                    errors.write(f"[{channel}] skipped {result.skipped_missing_date} messages without parseable date\n")
                if result.incomplete:
                    incomplete += 1
                    errors.write(
                        f"[{channel}] INCOMPLETE: tg read returned {result.raw_count} rows at "
                        f"max limit {result.limit}; raise SCAN_MAX_LIMIT or narrow the window.\n"
                    )
                    print(f"  Incomplete at limit {result.limit}; see {errors_path.name}", file=sys.stderr)
                print(f"  {written} messages kept from {result.raw_count} rows (limit {result.limit})")
            if index < len(channels) and args.delay:
                time.sleep(args.delay)

    print("---")
    print(f"Done. {len(channels)} channels scanned, {total_written} messages collected.")
    if failures:
        print(f"{failures} channels failed. See: {errors_path}")
    if incomplete:
        print(f"{incomplete} channels may be incomplete. See: {errors_path}")
    print(f"Output: {output_path}")
    print("")
    print("Next: Summarize with your preferred AI:")
    print(f"  OpenAI/DeepSeek: python scripts/summarize.py --input {output_path} --profile profiles/YOUR_PROFILE.md")
    print(f"  Codex/Claude:    Point your agent at {output_path} + profiles/YOUR_PROFILE.md")

    if failures:
        return 1
    if incomplete and not args.allow_incomplete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
