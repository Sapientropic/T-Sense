"""Cross-platform Telegram channel scanner.

Uses Telethon (MTProto user client) to read channel messages directly,
with precise UTC cutoff filtering and completeness detection.

Reads config and session from ~/.config/tgcli/ for backward compatibility.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto

DEFAULT_HOURS = 24
DEFAULT_INITIAL_LIMIT = 200
DEFAULT_MAX_LIMIT = 5000
DEFAULT_DELAY_SECONDS = 1.0

CONFIG_DIR = Path(
    os.environ.get(
        "TGCLI_CONFIG_DIR",
        os.path.join(
            os.environ.get("USERPROFILE", os.path.expanduser("~")),
            ".config",
            "tgcli",
        ),
    )
)
CONFIG_PATH = CONFIG_DIR / "config.toml"
SESSION_PATH = CONFIG_DIR / "session"


class ScanError(Exception):
    pass


@dataclass
class ChannelResult:
    channel: str
    messages: list[dict]
    raw_count: int
    skipped_missing_date: int
    limit: int
    incomplete: bool
    stderr: str = ""


@dataclass
class ScannerConfig:
    api_id: int
    api_hash: str
    session_string: str


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Pure helpers (sync, no Telethon dependency)
# ---------------------------------------------------------------------------

def load_channel_list(path: Path) -> list[str]:
    channels: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            channels.append(line)
    return channels


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


def filter_messages(
    messages: Iterable[dict], cutoff: datetime
) -> tuple[list[dict], int]:
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


def write_jsonl(path: Path, messages: Iterable[dict]) -> int:
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for message in messages:
            handle.write(json.dumps(message, ensure_ascii=False))
            handle.write("\n")
            count += 1
    return count


# ---------------------------------------------------------------------------
# Config & auth
# ---------------------------------------------------------------------------

def load_config() -> ScannerConfig:
    """Load Telegram API credentials from config.toml + session file.

    Falls back to TELEGRAM_API_ID / TELEGRAM_API_HASH env vars.
    """
    api_id: int | None = None
    api_hash: str | None = None

    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as f:
            cfg = tomllib.load(f)
        api_id = cfg.get("api_id")
        api_hash = cfg.get("api_hash")

    env_id = os.environ.get("TELEGRAM_API_ID")
    if env_id and not api_id:
        api_id = int(env_id)
    env_hash = os.environ.get("TELEGRAM_API_HASH")
    if env_hash and not api_hash:
        api_hash = env_hash

    if not api_id or not api_hash:
        raise ScanError(
            f"Missing API credentials. Edit {CONFIG_PATH} "
            "or set TELEGRAM_API_ID / TELEGRAM_API_HASH."
        )

    session_string = ""
    if SESSION_PATH.exists():
        session_string = SESSION_PATH.read_text(encoding="utf-8").strip()

    return ScannerConfig(
        api_id=api_id, api_hash=api_hash, session_string=session_string
    )


async def interactive_login(client: TelegramClient) -> None:
    """Interactive phone + code login. Saves StringSession on success."""
    print("No active Telegram session. Starting interactive login...")
    phone = input("Enter your phone number (with country code): ").strip()
    if not phone:
        raise ScanError("Phone number required for login.")

    await client.send_code_request(phone)
    code = input("Enter the verification code sent to your Telegram: ").strip()
    if not code:
        raise ScanError("Verification code required.")

    await client.sign_in(phone, code)

    session_string = StringSession.save(client.session)
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(session_string, encoding="utf-8")
    print(f"Session saved to {SESSION_PATH}")


# ---------------------------------------------------------------------------
# Entity resolution (ported from tgcli)
# ---------------------------------------------------------------------------

async def resolve_entity(client: TelegramClient, name: str):
    """Resolve a channel identifier to a Telethon entity.

    Supports: @username, plain username, numeric ID, display name.
    """
    name = name.strip()

    # Numeric ID
    if name.lstrip("-").isdigit():
        return await client.get_entity(int(name))

    # Username (with or without @)
    try:
        return await client.get_entity(name)
    except Exception:
        pass

    # Display name — case-insensitive exact match via dialog scan
    name_lower = name.lower()
    async for dialog in client.iter_dialogs():
        if dialog.name.lower() == name_lower:
            return dialog.entity

    raise ScanError(f"Cannot resolve channel: {name}")


# ---------------------------------------------------------------------------
# Message conversion & reading
# ---------------------------------------------------------------------------

def message_to_dict(msg, channel_name: str) -> dict:
    """Convert a Telethon Message to a JSONL-compatible dict."""
    media_type = None
    has_photo = False
    media_group = None
    if msg.media:
        media_type = type(msg.media).__name__
        has_photo = isinstance(msg.media, MessageMediaPhoto)
        if msg.voice:
            media_group = "voice"
        elif msg.video:
            media_group = "video"
        elif has_photo:
            media_group = "photo"

    reply_to_msg_id = None
    if msg.reply_to:
        reply_to_msg_id = msg.reply_to.reply_to_msg_id

    return {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "text": msg.text or "",
        "sender_id": msg.sender_id,
        "channel": channel_name,
        "reply_to_msg_id": reply_to_msg_id,
        "has_photo": has_photo,
        "media_type": media_type,
        "media_group": media_group,
    }


async def _fetch_with_retry(
    client: TelegramClient,
    entity,
    channel_name: str,
    limit: int,
    max_retries: int = 5,
) -> list:
    """Fetch messages with FloodWait retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            return await client.get_messages(entity, limit=limit)
        except FloodWaitError as exc:
            if attempt == max_retries:
                raise ScanError(
                    f"FloodWait: {max_retries} retries exceeded for {channel_name}"
                ) from exc
            wait = min(exc.seconds, 60)
            print(
                f"  FloodWait: sleeping {wait}s (retry {attempt}/{max_retries})..."
            )
            await asyncio.sleep(wait)


async def read_channel(
    client: TelegramClient,
    entity,
    channel_name: str,
    cutoff: datetime,
    initial_limit: int,
    max_limit: int,
) -> ChannelResult:
    """Read messages from a channel with completeness detection."""
    if initial_limit > max_limit:
        raise ValueError("initial_limit cannot exceed max_limit")

    limit = initial_limit

    while True:
        messages = await _fetch_with_retry(client, entity, channel_name, limit)
        raw_count = len(messages)
        dicts = [message_to_dict(m, channel_name) for m in messages]
        filtered, skipped_missing_date = filter_messages(dicts, cutoff)
        saturated = raw_count >= limit

        if not saturated:
            return ChannelResult(
                channel=channel_name,
                messages=filtered,
                raw_count=raw_count,
                skipped_missing_date=skipped_missing_date,
                limit=limit,
                incomplete=False,
            )

        if limit >= max_limit:
            return ChannelResult(
                channel=channel_name,
                messages=filtered,
                raw_count=raw_count,
                skipped_missing_date=skipped_missing_date,
                limit=limit,
                incomplete=True,
            )

        limit = min(limit * 2, max_limit)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan Telegram channels via Telethon."
    )
    parser.add_argument(
        "channel_list",
        type=Path,
        help="Text file with one channel username per line",
    )
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
        help="Precise UTC/local ISO-8601 cutoff. Overrides hours.",
    )
    parser.add_argument(
        "--initial-limit",
        type=positive_int,
        default=positive_int(
            os.environ.get("SCAN_INITIAL_LIMIT", str(DEFAULT_INITIAL_LIMIT))
        ),
        help=f"Initial message limit per channel (default: {DEFAULT_INITIAL_LIMIT})",
    )
    parser.add_argument(
        "--max-limit",
        type=positive_int,
        default=positive_int(
            os.environ.get("SCAN_MAX_LIMIT", str(DEFAULT_MAX_LIMIT))
        ),
        help=f"Max message limit before reporting incomplete (default: {DEFAULT_MAX_LIMIT})",
    )
    parser.add_argument(
        "--delay",
        type=non_negative_float,
        default=non_negative_float(
            os.environ.get("SCAN_DELAY", str(DEFAULT_DELAY_SECONDS))
        ),
        help=f"Delay between channels in seconds (default: {DEFAULT_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Exit 0 even if a channel reaches --max-limit and may be incomplete",
    )
    return parser


async def _run_scan(args) -> int:
    """Async scan core."""
    config = load_config()

    client = TelegramClient(
        StringSession(config.session_string),
        config.api_id,
        config.api_hash,
    )
    await client.connect()

    try:
        if not await client.is_user_authorized():
            await interactive_login(client)
    except ScanError:
        await client.disconnect()
        raise

    try:
        channels = load_channel_list(args.channel_list)
    except OSError as exc:
        await client.disconnect()
        print(f"Error: Failed to read channel list: {exc}", file=sys.stderr)
        return 1

    cutoff = cutoff_from_args(args.hours, args.since)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"scan_{timestamp}.jsonl"
    errors_path = args.output_dir / f"scan_{timestamp}.errors.log"

    print(f"Scan started: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Precise cutoff: {cutoff.isoformat()}")
    print(f"Channel list: {args.channel_list}")
    print(f"Output: {output_path}")
    print("---")

    failures = 0
    incomplete = 0
    total_written = 0

    with errors_path.open("w", encoding="utf-8", newline="\n") as errors:
        for index, channel_name in enumerate(channels, start=1):
            print(f"[{index}] Reading: {channel_name}")
            try:
                entity = await resolve_entity(client, channel_name)
                result = await read_channel(
                    client=client,
                    entity=entity,
                    channel_name=channel_name,
                    cutoff=cutoff,
                    initial_limit=args.initial_limit,
                    max_limit=args.max_limit,
                )
            except ScanError as exc:
                failures += 1
                errors.write(f"[{channel_name}] ERROR: {exc}\n")
                print(
                    f"  Failed: {channel_name} (see {errors_path.name})",
                    file=sys.stderr,
                )
            except Exception as exc:
                failures += 1
                errors.write(f"[{channel_name}] ERROR: {exc}\n")
                print(
                    f"  Failed: {channel_name}: {exc} (see {errors_path.name})",
                    file=sys.stderr,
                )
            else:
                written = write_jsonl(output_path, result.messages)
                total_written += written
                if result.skipped_missing_date:
                    errors.write(
                        f"[{channel_name}] skipped {result.skipped_missing_date} "
                        "messages without parseable date\n"
                    )
                if result.incomplete:
                    incomplete += 1
                    errors.write(
                        f"[{channel_name}] INCOMPLETE: read {result.raw_count} rows at "
                        f"max limit {result.limit}; raise SCAN_MAX_LIMIT or narrow the window.\n"
                    )
                    print(
                        f"  Incomplete at limit {result.limit}; see {errors_path.name}",
                        file=sys.stderr,
                    )
                print(
                    f"  {written} messages kept from {result.raw_count} rows (limit {result.limit})"
                )

            if index < len(channels) and args.delay:
                await asyncio.sleep(args.delay)

    await client.disconnect()

    print("---")
    print(f"Done. {len(channels)} channels scanned, {total_written} messages collected.")
    if failures:
        print(f"{failures} channels failed. See: {errors_path}")
    if incomplete:
        print(f"{incomplete} channels may be incomplete. See: {errors_path}")
    print(f"Output: {output_path}")
    print("")
    print("Next: Summarize with your preferred AI:")
    print(
        f"  OpenAI/DeepSeek: python scripts/summarize.py "
        f"--input {output_path} --profile profiles/YOUR_PROFILE.md"
    )
    print(
        f"  Codex/Claude:    Point your agent at {output_path} "
        f"+ profiles/YOUR_PROFILE.md"
    )

    if failures:
        return 1
    if incomplete and not args.allow_incomplete:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.channel_list.exists():
        print(
            f"Error: Channel list not found: {args.channel_list}", file=sys.stderr
        )
        return 1
    if args.initial_limit > args.max_limit:
        print(
            "Error: --initial-limit cannot exceed --max-limit", file=sys.stderr
        )
        return 1

    return asyncio.run(_run_scan(args))


if __name__ == "__main__":
    raise SystemExit(main())
