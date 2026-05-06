"""Cross-platform Telegram channel scanner with optional media OCR.

Uses Telethon (MTProto user client) to read channel messages directly.
When OCR is explicitly enabled, media messages (photos, videos, voice)
are downloaded to temp files, OCR'd, and cleaned up in one pass.

Reads config and session from ~/.config/tgcli/ for backward compatibility.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

# Ensure project root is importable for scripts.media_ocr
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.media_ocr import OcrConfig, process_message

DEFAULT_HOURS = 24
DEFAULT_INITIAL_LIMIT = 200
DEFAULT_MAX_LIMIT = 5000
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_MAX_FLOOD_WAIT_SECONDS = 300

DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_XAI_OCR_MODEL = "grok-4.1-fast"
DEFAULT_OPENAI_OCR_MODEL = "gpt-4o-mini"
DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_VIDEO_FRAMES = 3

CONFIG_DIR = Path(
    os.environ.get("TG_SCANNER_CONFIG_DIR")
    or os.environ.get("TGCLI_CONFIG_DIR")
    or os.path.join(
        os.environ.get("USERPROFILE", os.path.expanduser("~")),
        ".config",
        "tgcli",
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
    ocr_count: int = 0
    stderr: str = ""


@dataclass
class ScannerConfig:
    api_id: int
    api_hash: str
    session_string: str


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

class EnvAwareArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._env_default_validators: list[tuple[str, Callable[[str], object]]] = []

    def register_env_default(self, name: str, converter) -> None:
        self._env_default_validators.append((name, converter))

    def parse_known_args(self, args=None, namespace=None):
        # Validate environment-backed defaults before argparse handles --help.
        # Otherwise a bad SCAN_* value can either hide behind help output or
        # fail later with a traceback, depending on argparse internals.
        for name, converter in self._env_default_validators:
            value = os.environ.get(name)
            if value is None:
                continue
            try:
                converter(value)
            except argparse.ArgumentTypeError as exc:
                self.error(str(exc))
        return super().parse_known_args(args, namespace)


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


def positive_int_with_label(label: str):
    def convert(value: str) -> int:
        try:
            return positive_int(value)
        except argparse.ArgumentTypeError as exc:
            raise argparse.ArgumentTypeError(f"{label} {exc}") from exc

    return convert


def non_negative_float_with_label(label: str):
    def convert(value: str) -> float:
        try:
            return non_negative_float(value)
        except argparse.ArgumentTypeError as exc:
            raise argparse.ArgumentTypeError(f"{label} {exc}") from exc

    return convert


def env_default(name: str, fallback: int | float | str) -> str:
    return os.environ.get(name, str(fallback))


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


def _filter_raw_messages(
    messages: list, cutoff: datetime
) -> tuple[list, int]:
    """Filter Telethon Message objects by cutoff."""
    cutoff_utc = cutoff.astimezone(UTC)
    kept: list = []
    skipped = 0
    for m in messages:
        if m.date is None:
            skipped += 1
            continue
        d = m.date if m.date.tzinfo else m.date.replace(tzinfo=UTC)
        if d.astimezone(UTC) >= cutoff_utc:
            kept.append(m)
    return kept, skipped


def write_jsonl(path: Path, messages: Iterable[dict]) -> int:
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for message in messages:
            handle.write(json.dumps(message, ensure_ascii=False))
            handle.write("\n")
            count += 1
    return count


def meta_path_for_output(output_path: Path) -> Path:
    return output_path.with_suffix(".meta.json")


def build_scan_metadata(
    *,
    started_at: datetime,
    completed_at: datetime,
    cutoff: datetime,
    channel_list_path: Path,
    channels: list[str],
    output_path: Path,
    errors_path: Path,
    total_written: int,
    failed_channels: list[str],
    incomplete_channels: list[str],
    total_ocr: int,
    ocr_enabled: bool,
    hours: int,
) -> dict:
    return {
        "scan_date": started_at.astimezone(UTC).date().isoformat(),
        "scan_started_at": started_at.astimezone(UTC).isoformat(),
        "scan_completed_at": completed_at.astimezone(UTC).isoformat(),
        "scan_window": f"Last {hours} hours",
        "cutoff": cutoff.astimezone(UTC).isoformat(),
        "channel_list_path": str(channel_list_path),
        "channels": channels,
        "channel_count": len(channels),
        "total_messages_collected": total_written,
        "failed_channels": failed_channels,
        "failure_count": len(failed_channels),
        "incomplete_channels": incomplete_channels,
        "incomplete_count": len(incomplete_channels),
        "ocr_enabled": ocr_enabled,
        "ocr_count": total_ocr,
        "output_path": str(output_path),
        "errors_path": str(errors_path),
    }


def write_scan_metadata(path: Path, metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Config & auth
# ---------------------------------------------------------------------------

def load_config() -> ScannerConfig:
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


def _resolve_ocr_settings(args) -> tuple[str, str, str, str]:
    xai_key = os.environ.get("XAI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    provider = args.ocr_provider
    if provider is None:
        if xai_key:
            provider = "xai"
        elif openai_key:
            provider = "openai"
        else:
            provider = "xai"

    if provider == "xai":
        if not xai_key:
            raise ScanError("OCR provider xai requires XAI_API_KEY.")
        base_url = args.ocr_base_url or DEFAULT_XAI_BASE_URL
        model = args.ocr_model or DEFAULT_XAI_OCR_MODEL
        return provider, xai_key, base_url, model

    if provider == "openai":
        if not openai_key:
            raise ScanError("OCR provider openai requires OPENAI_API_KEY.")
        base_url = args.ocr_base_url or DEFAULT_OPENAI_BASE_URL
        model = args.ocr_model or DEFAULT_OPENAI_OCR_MODEL
        return provider, openai_key, base_url, model

    api_key = xai_key or openai_key
    if not api_key:
        raise ScanError("OCR provider custom requires XAI_API_KEY or OPENAI_API_KEY.")
    if not args.ocr_base_url:
        raise ScanError("OCR provider custom requires --ocr-base-url.")
    model = args.ocr_model or DEFAULT_OPENAI_OCR_MODEL
    return provider, api_key, args.ocr_base_url, model


def _make_ocr_config(args) -> OcrConfig | None:
    """Create OcrConfig only when OCR is explicitly enabled."""
    if args.no_ocr or not args.ocr:
        return None
    if openai is None:
        raise ScanError("OCR requires optional dependency: pip install -r requirements-llm.txt")

    provider, api_key, base_url, model = _resolve_ocr_settings(args)
    stt_base_url = args.ocr_stt_base_url or base_url
    args.ocr_effective_provider = provider
    args.ocr_effective_base_url = base_url

    vision_client = openai.OpenAI(base_url=base_url, api_key=api_key)
    stt_client = openai.OpenAI(
        base_url=stt_base_url, api_key=api_key,
    )
    return OcrConfig(
        client=vision_client,
        model=model,
        stt_client=stt_client,
        stt_model=args.ocr_stt_model,
        language=args.ocr_language,
        full_video=args.ocr_full_video,
        video_frames=args.ocr_video_frames,
        prompt=args.ocr_prompt,
    )


async def interactive_login(client: TelegramClient) -> None:
    print("No active Telegram session. Starting interactive login...")
    phone = input("Enter your phone number (with country code): ").strip()
    if not phone:
        raise ScanError("Phone number required for login.")

    await client.send_code_request(phone)
    code = input("Enter the verification code sent to your Telegram: ").strip()
    if not code:
        raise ScanError("Verification code required.")

    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        password = getpass.getpass("Enter your Telegram 2FA password: ").strip()
        if not password:
            raise ScanError("Two-factor password required for login.") from None
        await client.sign_in(password=password)

    session_string = StringSession.save(client.session)
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(session_string, encoding="utf-8")
    print(f"Session saved to {SESSION_PATH}")


# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------

async def resolve_entity(client: TelegramClient, name: str):
    name = name.strip()
    if name.lstrip("-").isdigit():
        entity_id = int(name)
        try:
            return await client.get_entity(entity_id)
        except Exception:
            pass
        # Fallback: search dialogs for matching ID
        async for dialog in client.iter_dialogs():
            if dialog.entity.id == entity_id:
                return dialog.entity
        raise ScanError(f"Cannot resolve entity: {name}")
    try:
        return await client.get_entity(name)
    except Exception:
        pass
    name_lower = name.lower()
    async for dialog in client.iter_dialogs():
        if dialog.name.lower() == name_lower:
            return dialog.entity
    raise ScanError(f"Cannot resolve channel: {name}")


# ---------------------------------------------------------------------------
# Message conversion & reading
# ---------------------------------------------------------------------------

def _extract_video_meta(msg) -> dict | None:
    """Extract video metadata (duration, size, dimensions) from a message."""
    doc = getattr(msg.media, "document", None)
    if not doc:
        return None
    from telethon.tl.types import DocumentAttributeVideo
    for attr in (doc.attributes or []):
        if isinstance(attr, DocumentAttributeVideo):
            return {
                "video_duration": round(attr.duration, 1),
                "video_width": attr.w,
                "video_height": attr.h,
                "video_file_size": doc.size,
            }
    return None


def message_to_dict(msg, channel_name: str) -> dict:
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

    forward = None
    if msg.forward:
        fwd = msg.forward
        forward = {}
        if hasattr(fwd, 'from_id') and fwd.from_id:
            forward["from_id"] = str(fwd.from_id)
        if getattr(fwd, 'channel_post', None):
            forward["channel_post"] = fwd.channel_post
        if getattr(fwd, 'from_name', None):
            forward["from_name"] = fwd.from_name
        if fwd.date:
            forward["date"] = fwd.date.isoformat()

    result = {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "text": msg.text or "",
        "sender_id": msg.sender_id,
        "channel": channel_name,
        "reply_to_msg_id": reply_to_msg_id,
        "has_photo": has_photo,
        "media_type": media_type,
        "media_group": media_group,
        "forward": forward,
    }

    # Attach video metadata for "is this worth watching?" decisions
    if media_group == "video":
        video_meta = _extract_video_meta(msg)
        if video_meta:
            result.update(video_meta)

    return result


async def _fetch_with_retry(
    client: TelegramClient,
    entity,
    channel_name: str,
    limit: int,
    max_retries: int = 5,
    max_flood_wait_seconds: int = DEFAULT_MAX_FLOOD_WAIT_SECONDS,
) -> list:
    for attempt in range(1, max_retries + 1):
        try:
            return await client.get_messages(entity, limit=limit)
        except FloodWaitError as exc:
            if exc.seconds > max_flood_wait_seconds:
                raise ScanError(
                    f"FloodWait {exc.seconds}s for {channel_name} exceeds "
                    f"configured maximum {max_flood_wait_seconds}s."
                ) from exc
            if attempt == max_retries:
                raise ScanError(
                    f"FloodWait: {max_retries} retries exceeded for {channel_name}"
                ) from exc
            wait = exc.seconds
            print(f"  FloodWait: sleeping {wait}s (retry {attempt}/{max_retries})...")
            await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# Channel reading (with integrated OCR)
# ---------------------------------------------------------------------------

async def read_channel(
    client: TelegramClient,
    entity,
    channel_name: str,
    cutoff: datetime,
    initial_limit: int,
    max_limit: int,
    ocr: OcrConfig | None = None,
    max_flood_wait_seconds: int = DEFAULT_MAX_FLOOD_WAIT_SECONDS,
) -> ChannelResult:
    """Stream messages via iter_messages, stop immediately at cutoff.

    Uses iter_messages with early termination: as soon as we encounter a
    message older than cutoff, we break — no exponential doubling, no
    over-fetching. max_limit serves as a safety cap against runaway reads.
    """
    cutoff_utc = cutoff.astimezone(UTC)
    safety_cap = max_limit

    kept_msgs: list = []
    raw_count = 0
    skipped_missing_date = 0
    hit_cap = False

    async for msg in client.iter_messages(entity, limit=safety_cap):
        raw_count += 1
        if msg.date is None:
            skipped_missing_date += 1
            continue
        d = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=UTC)
        if d.astimezone(UTC) < cutoff_utc:
            break
        kept_msgs.append(msg)

    hit_cap = raw_count >= safety_cap

    # OCR media
    ocr_texts: dict[int, str] = {}
    ocr_count = 0
    ocr_errors: list[str] = []
    if ocr:
        for m in kept_msgs:
            if m.media:
                try:
                    text = await process_message(client, m, ocr)
                except Exception as exc:
                    ocr_errors.append(f"OCR failed for message {m.id}: {exc}")
                    continue
                if text:
                    ocr_texts[m.id] = text
                    ocr_count += 1
                    print(f"    OCR [{channel_name}:{m.id}] -> {len(text)} chars")

    dicts = [message_to_dict(m, channel_name) for m in kept_msgs]
    for d in dicts:
        if d["id"] in ocr_texts:
            d["ocr_text"] = ocr_texts[d["id"]]

    return ChannelResult(
        channel=channel_name,
        messages=dicts,
        raw_count=raw_count,
        skipped_missing_date=skipped_missing_date,
        limit=safety_cap,
        incomplete=hit_cap,
        ocr_count=ocr_count,
        stderr="\n".join(ocr_errors),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = EnvAwareArgumentParser(
        description="Scan Telegram channels via Telethon with optional media OCR.",
        allow_abbrev=False,
    )
    initial_limit_type = positive_int_with_label("SCAN_INITIAL_LIMIT")
    max_limit_type = positive_int_with_label("SCAN_MAX_LIMIT")
    delay_type = non_negative_float_with_label("SCAN_DELAY")
    max_flood_wait_type = positive_int_with_label("SCAN_MAX_FLOOD_WAIT_SECONDS")
    parser.register_env_default("SCAN_INITIAL_LIMIT", initial_limit_type)
    parser.register_env_default("SCAN_MAX_LIMIT", max_limit_type)
    parser.register_env_default("SCAN_DELAY", delay_type)
    parser.register_env_default("SCAN_MAX_FLOOD_WAIT_SECONDS", max_flood_wait_type)
    parser.add_argument(
        "channel_list", type=Path,
        help="Text file with one channel username per line",
    )
    parser.add_argument(
        "hours", nargs="?", type=positive_int, default=DEFAULT_HOURS,
        help=f"Look back this many hours (default: {DEFAULT_HOURS})",
    )
    parser.add_argument("--since", type=parse_since, help="Precise ISO-8601 cutoff.")
    parser.add_argument(
        "--initial-limit", type=initial_limit_type,
        default=env_default("SCAN_INITIAL_LIMIT", DEFAULT_INITIAL_LIMIT),
    )
    parser.add_argument(
        "--max-limit", type=max_limit_type,
        default=env_default("SCAN_MAX_LIMIT", DEFAULT_MAX_LIMIT),
    )
    parser.add_argument(
        "--delay", type=delay_type,
        default=env_default("SCAN_DELAY", DEFAULT_DELAY_SECONDS),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--max-flood-wait-seconds",
        type=max_flood_wait_type,
        default=env_default("SCAN_MAX_FLOOD_WAIT_SECONDS", DEFAULT_MAX_FLOOD_WAIT_SECONDS),
        help=(
            "Maximum FloodWait seconds to sleep before failing the channel "
            f"(default: {DEFAULT_MAX_FLOOD_WAIT_SECONDS})"
        ),
    )

    # OCR options
    ocr_group = parser.add_argument_group(
        "OCR", "Media OCR is off by default; pass --ocr to upload media to an OCR API."
    )
    ocr_group.add_argument("--ocr", action="store_true", help="Enable media OCR/STT")
    ocr_group.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable media OCR/STT (compatibility alias; default behavior)",
    )
    ocr_group.add_argument(
        "--ocr-provider",
        choices=("xai", "openai", "custom"),
        default=None,
        help="OCR provider. Defaults to xai if XAI_API_KEY is set, otherwise openai if OPENAI_API_KEY is set.",
    )
    ocr_group.add_argument(
        "--ocr-base-url",
        default=os.environ.get("OCR_BASE_URL") or os.environ.get("OPENAI_BASE_URL"),
        help="Override the OCR API base URL; required for --ocr-provider custom.",
    )
    ocr_group.add_argument("--ocr-model", default=None)
    ocr_group.add_argument("--ocr-stt-base-url", default=None)
    ocr_group.add_argument("--ocr-stt-model", default=DEFAULT_STT_MODEL)
    ocr_group.add_argument("--ocr-language", default=None, help="Language hint for voice STT (e.g. 'ru', 'en')")
    ocr_group.add_argument("--ocr-full-video", action="store_true", help="Download full video for audio STT (default: thumbnail only)")
    ocr_group.add_argument("--ocr-video-frames", type=positive_int, default=DEFAULT_VIDEO_FRAMES)
    ocr_group.add_argument("--ocr-prompt", default=(
        "Extract all text from this image exactly as written. "
        "Output only the extracted text, nothing else."
    ))

    return parser


async def _run_scan(args) -> int:
    config = load_config()

    client = TelegramClient(
        StringSession(config.session_string),
        config.api_id,
        config.api_hash,
        flood_sleep_threshold=0,
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

    try:
        ocr = _make_ocr_config(args)
    except ScanError as exc:
        await client.disconnect()
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if ocr:
        print(
            "OCR enabled: "
            f"{ocr.model} @ {args.ocr_effective_base_url} "
            f"({args.ocr_effective_provider})"
        )
    else:
        print("OCR disabled: pass --ocr to upload media to an OCR/STT API")

    cutoff = cutoff_from_args(args.hours, args.since)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"scan_{timestamp}.jsonl"
    errors_path = args.output_dir / f"scan_{timestamp}.errors.log"
    meta_path = meta_path_for_output(output_path)

    print(f"Scan started: {started_at.isoformat(timespec='seconds')}")
    print(f"Precise cutoff: {cutoff.isoformat()}")
    print(f"Channel list: {args.channel_list}")
    print(f"Output: {output_path}")
    print("---")

    failures = 0
    incomplete = 0
    total_written = 0
    total_ocr = 0
    failed_channels: list[str] = []
    incomplete_channels: list[str] = []

    with errors_path.open("w", encoding="utf-8", newline="\n") as errors:
        for index, channel_name in enumerate(channels, start=1):
            print(f"[{index}] Reading: {channel_name}")
            try:
                entity = await resolve_entity(client, channel_name)
                # Use title for display if channel_name is a bare numeric ID
                display_name = channel_name
                if channel_name.lstrip("-").isdigit():
                    title = getattr(entity, "title", None) or getattr(entity, "first_name", None)
                    if title:
                        display_name = title
                result = await read_channel(
                    client=client,
                    entity=entity,
                    channel_name=display_name,
                    cutoff=cutoff,
                    initial_limit=args.initial_limit,
                    max_limit=args.max_limit,
                    ocr=ocr,
                    max_flood_wait_seconds=args.max_flood_wait_seconds,
                )
            except ScanError as exc:
                failures += 1
                failed_channels.append(channel_name)
                errors.write(f"[{channel_name}] ERROR: {exc}\n")
                print(f"  Failed: {channel_name} (see {errors_path.name})", file=sys.stderr)
            except Exception as exc:
                failures += 1
                failed_channels.append(channel_name)
                errors.write(f"[{channel_name}] ERROR: {exc}\n")
                print(f"  Failed: {channel_name}: {exc} (see {errors_path.name})", file=sys.stderr)
            else:
                written = write_jsonl(output_path, result.messages)
                total_written += written
                total_ocr += result.ocr_count
                if result.skipped_missing_date:
                    errors.write(
                        f"[{channel_name}] skipped {result.skipped_missing_date} "
                        "messages without parseable date\n"
                    )
                if result.stderr:
                    for line in result.stderr.splitlines():
                        errors.write(f"[{channel_name}] {line}\n")
                if result.incomplete:
                    incomplete += 1
                    incomplete_channels.append(channel_name)
                    errors.write(
                        f"[{channel_name}] INCOMPLETE: read {result.raw_count} rows at "
                        f"max limit {result.limit}; raise SCAN_MAX_LIMIT or narrow the window.\n"
                    )
                    print(f"  Incomplete at limit {result.limit}; see {errors_path.name}", file=sys.stderr)
                ocr_info = f", {result.ocr_count} media OCR'd" if result.ocr_count else ""
                print(f"  {written} messages kept from {result.raw_count} rows (limit {result.limit}){ocr_info}")

            if index < len(channels) and args.delay:
                await asyncio.sleep(args.delay)

    await client.disconnect()
    completed_at = datetime.now(UTC)
    metadata = build_scan_metadata(
        started_at=started_at,
        completed_at=completed_at,
        cutoff=cutoff,
        channel_list_path=args.channel_list,
        channels=channels,
        output_path=output_path,
        errors_path=errors_path,
        total_written=total_written,
        failed_channels=failed_channels,
        incomplete_channels=incomplete_channels,
        total_ocr=total_ocr,
        ocr_enabled=ocr is not None,
        hours=args.hours,
    )
    write_scan_metadata(meta_path, metadata)

    print("---")
    print(f"Done. {len(channels)} channels scanned, {total_written} messages collected.")
    if total_ocr:
        print(f"{total_ocr} media messages OCR'd.")
    if failures:
        print(f"{failures} channels failed. See: {errors_path}")
    if incomplete:
        print(f"{incomplete} channels may be incomplete. See: {errors_path}")
    print(f"Output: {output_path}")
    print(f"Metadata: {meta_path}")
    print("")
    print("Next: Summarize with your preferred AI:")
    print(
        f"  python scripts/summarize.py "
        f"--input {output_path} --profile profiles/YOUR_PROFILE.md"
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
        print(f"Error: Channel list not found: {args.channel_list}", file=sys.stderr)
        return 1
    if args.initial_limit > args.max_limit:
        print("Error: --initial-limit cannot exceed --max-limit", file=sys.stderr)
        return 1

    return asyncio.run(_run_scan(args))


if __name__ == "__main__":
    raise SystemExit(main())
