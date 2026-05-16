"""CLI facade for the Telegram scanner.

The scanner is split into source loading, metadata, media projection, config,
and Telethon runtime modules.  This file keeps the historical `scripts.scan`
API stable for tests and source-checkout launchers.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

try:
    from scripts import agent_cli
    from scripts import scan_config as _scan_config
    from scripts import scan_media_projection as _scan_media_projection
    from scripts import scan_metadata as _scan_metadata
    from scripts import scan_sources as _scan_sources
    from scripts import telegram_scan as _telegram_scan
except ModuleNotFoundError:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts import agent_cli
    from scripts import scan_config as _scan_config
    from scripts import scan_media_projection as _scan_media_projection
    from scripts import scan_metadata as _scan_metadata
    from scripts import scan_sources as _scan_sources
    from scripts import telegram_scan as _telegram_scan

DEFAULT_HOURS = _scan_config.DEFAULT_HOURS
DEFAULT_MAX_LIMIT = _scan_config.DEFAULT_MAX_LIMIT
DEFAULT_DELAY_SECONDS = _scan_config.DEFAULT_DELAY_SECONDS
DEFAULT_SCAN_CONCURRENCY = _scan_config.DEFAULT_SCAN_CONCURRENCY
DEFAULT_MAX_FLOOD_WAIT_SECONDS = _scan_config.DEFAULT_MAX_FLOOD_WAIT_SECONDS
DEFAULT_XAI_BASE_URL = _scan_config.DEFAULT_XAI_BASE_URL
DEFAULT_OPENAI_BASE_URL = _scan_config.DEFAULT_OPENAI_BASE_URL
DEFAULT_XAI_OCR_MODEL = _scan_config.DEFAULT_XAI_OCR_MODEL
DEFAULT_OPENAI_OCR_MODEL = _scan_config.DEFAULT_OPENAI_OCR_MODEL
DEFAULT_STT_MODEL = _scan_config.DEFAULT_STT_MODEL
DEFAULT_VIDEO_FRAMES = _scan_config.DEFAULT_VIDEO_FRAMES
LOCAL_OCR_SECRET_TARGETS = _scan_config.LOCAL_OCR_SECRET_TARGETS
LOGIN_QUIT_COMMANDS = _scan_config.LOGIN_QUIT_COMMANDS
LOGIN_RESEND_COMMANDS = _scan_config.LOGIN_RESEND_COMMANDS
CONFIG_DIR = _scan_config.CONFIG_DIR
CONFIG_PATH = _scan_config.CONFIG_PATH
SESSION_PATH = _scan_config.SESSION_PATH

ScanError = _scan_config.ScanError
ScannerConfig = _scan_config.ScannerConfig
EnvAwareArgumentParser = _scan_config.EnvAwareArgumentParser
positive_int = _scan_config.positive_int
non_negative_float = _scan_config.non_negative_float
positive_int_with_label = _scan_config.positive_int_with_label
non_negative_float_with_label = _scan_config.non_negative_float_with_label
env_default = _scan_config.env_default
parse_since = _scan_config.parse_since
cutoff_from_args = _scan_config.cutoff_from_args
ai_secret = _scan_config.ai_secret

ChannelResult = _scan_sources.ChannelResult
ScanSource = _scan_sources.ScanSource
load_channel_list = _scan_sources.load_channel_list
source_from_channel_list_entry = _scan_sources.source_from_channel_list_entry
source_from_registry_entry = _scan_sources.source_from_registry_entry
load_scan_sources = _scan_sources.load_scan_sources
scan_hours = _scan_sources.scan_hours
parse_message_date = _scan_sources.parse_message_date
filter_messages = _scan_sources.filter_messages
_filter_raw_messages = _scan_sources._filter_raw_messages
write_jsonl = _scan_sources.write_jsonl
_source_health_base = _scan_sources._source_health_base
source_access_failure_reason = _scan_sources.source_access_failure_reason
_health_from_result = _scan_sources._health_from_result
_health_from_failure = _scan_sources._health_from_failure

meta_path_for_output = _scan_metadata.meta_path_for_output
build_scan_metadata = _scan_metadata.build_scan_metadata
write_scan_metadata = _scan_metadata.write_scan_metadata

_resolve_ocr_settings = _scan_media_projection._resolve_ocr_settings
_extract_video_meta = _scan_media_projection._extract_video_meta
message_to_dict = _scan_media_projection.message_to_dict

_load_config_impl = _scan_config.load_config
_make_ocr_config_impl = _scan_media_projection._make_ocr_config
_interactive_login_impl = _telegram_scan.interactive_login
_resolve_entity_impl = _telegram_scan.resolve_entity
_read_channel_impl = _telegram_scan.read_channel
_run_scan_impl = _telegram_scan._run_scan


def load_config() -> ScannerConfig:
    _sync_modules()
    return _load_config_impl()


def _make_ocr_config(args: argparse.Namespace):
    _sync_modules()
    return _make_ocr_config_impl(args)


async def interactive_login(client: TelegramClient, *, max_attempts: int = 3) -> None:
    _sync_modules()
    return await _interactive_login_impl(client, max_attempts=max_attempts)


async def resolve_entity(client: TelegramClient, name: str):
    _sync_modules()
    return await _resolve_entity_impl(client, name)


async def read_channel(
    client: TelegramClient,
    entity,
    channel_name: str,
    cutoff,
    max_limit: int,
    ocr=None,
) -> ChannelResult:
    _sync_modules()
    return await _read_channel_impl(client, entity, channel_name, cutoff, max_limit, ocr)


async def _run_scan(args: argparse.Namespace) -> int:
    _sync_modules()
    return await _run_scan_impl(args)


_LOAD_CONFIG_WRAPPER = load_config
_MAKE_OCR_CONFIG_WRAPPER = _make_ocr_config
_INTERACTIVE_LOGIN_WRAPPER = interactive_login
_RESOLVE_ENTITY_WRAPPER = resolve_entity
_READ_CHANNEL_WRAPPER = read_channel


def _patched_or_impl(name: str, wrapper, impl):
    value = globals()[name]
    return impl if value is wrapper else value


def _sync_modules() -> None:
    _scan_config.CONFIG_PATH = CONFIG_PATH
    _scan_config.SESSION_PATH = SESSION_PATH
    _scan_media_projection.openai = openai
    _telegram_scan.SESSION_PATH = SESSION_PATH
    _telegram_scan.StringSession = StringSession
    _telegram_scan.TelegramClient = TelegramClient
    _telegram_scan.load_config = _patched_or_impl("load_config", _LOAD_CONFIG_WRAPPER, _load_config_impl)
    _telegram_scan._make_ocr_config = _patched_or_impl(
        "_make_ocr_config",
        _MAKE_OCR_CONFIG_WRAPPER,
        _make_ocr_config_impl,
    )
    _telegram_scan.interactive_login = _patched_or_impl(
        "interactive_login",
        _INTERACTIVE_LOGIN_WRAPPER,
        _interactive_login_impl,
    )
    _telegram_scan.resolve_entity = _patched_or_impl("resolve_entity", _RESOLVE_ENTITY_WRAPPER, _resolve_entity_impl)
    _telegram_scan.read_channel = _patched_or_impl("read_channel", _READ_CHANNEL_WRAPPER, _read_channel_impl)


def build_parser() -> argparse.ArgumentParser:
    parser = EnvAwareArgumentParser(
        description="Scan Telegram channels via Telethon with optional media OCR.",
        allow_abbrev=False,
    )
    max_limit_type = positive_int_with_label("SCAN_MAX_LIMIT")
    scan_concurrency_type = positive_int_with_label("SCAN_CONCURRENCY")
    delay_type = non_negative_float_with_label("SCAN_DELAY")
    max_flood_wait_type = positive_int_with_label("SCAN_MAX_FLOOD_WAIT_SECONDS")
    parser.register_env_default("SCAN_MAX_LIMIT", max_limit_type)
    parser.register_env_default("SCAN_DELAY", delay_type)
    parser.register_env_default("SCAN_CONCURRENCY", scan_concurrency_type)
    parser.register_env_default("SCAN_MAX_FLOOD_WAIT_SECONDS", max_flood_wait_type)
    parser.add_argument(
        "channel_list",
        nargs="?",
        type=Path,
        help="Text file with one channel username per line",
    )
    parser.add_argument(
        "hours",
        nargs="?",
        type=positive_int,
        default=None,
        help=f"Look back this many hours (default: {DEFAULT_HOURS})",
    )
    parser.add_argument("--hours", dest="hours_flag", type=positive_int)
    parser.add_argument("--source-registry", type=Path, help="Private source registry JSON.")
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="Complete interactive Telegram login and exit without scanning.",
    )
    parser.add_argument("--since", type=parse_since, help="Precise ISO-8601 cutoff.")
    parser.add_argument("--initial-limit", default=os.environ.get("SCAN_INITIAL_LIMIT"), help=argparse.SUPPRESS)
    parser.add_argument("--max-limit", type=max_limit_type, default=env_default("SCAN_MAX_LIMIT", DEFAULT_MAX_LIMIT))
    parser.add_argument("--delay", type=delay_type, default=env_default("SCAN_DELAY", DEFAULT_DELAY_SECONDS))
    parser.add_argument(
        "--scan-concurrency",
        type=scan_concurrency_type,
        default=env_default("SCAN_CONCURRENCY", DEFAULT_SCAN_CONCURRENCY),
        help=f"Maximum sources to scan concurrently (default: {DEFAULT_SCAN_CONCURRENCY})",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--output",
        type=Path,
        help="Explicit JSONL output path. Defaults to output/scan_YYYYMMDD_HHMMSS.jsonl.",
    )
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--allow-partial-failures",
        action="store_true",
        help="Return success when at least one source produced messages and other sources failed.",
    )
    parser.add_argument(
        "--max-flood-wait-seconds",
        type=max_flood_wait_type,
        default=env_default("SCAN_MAX_FLOOD_WAIT_SECONDS", DEFAULT_MAX_FLOOD_WAIT_SECONDS),
        help=(
            "Maximum FloodWait seconds to sleep before failing the channel "
            f"(default: {DEFAULT_MAX_FLOOD_WAIT_SECONDS})"
        ),
    )

    ocr_group = parser.add_argument_group(
        "OCR",
        "Media OCR is off by default; pass --ocr to upload media to an OCR API.",
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
    ocr_group.add_argument(
        "--ocr-full-video",
        action="store_true",
        help="Download full video for audio STT (default: thumbnail only)",
    )
    ocr_group.add_argument("--ocr-video-frames", type=positive_int, default=DEFAULT_VIDEO_FRAMES)
    ocr_group.add_argument(
        "--ocr-prompt",
        default=(
            "Extract all text from this image exactly as written. "
            "Output only the extracted text, nothing else."
        ),
    )
    agent_cli.add_format_argument(parser)
    return parser


def warn_deprecated_options(argv: list[str] | None, args: argparse.Namespace) -> None:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    has_initial_limit_arg = any(
        value == "--initial-limit" or value.startswith("--initial-limit=")
        for value in raw_args
    )
    if has_initial_limit_arg or os.environ.get("SCAN_INITIAL_LIMIT") is not None:
        print(
            "Warning: --initial-limit/SCAN_INITIAL_LIMIT is deprecated and ignored; "
            "scan.py streams until --max-limit.",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    warn_deprecated_options(argv, args)

    if not args.login_only and not args.channel_list and not args.source_registry:
        agent_cli.emit_error(
            args,
            code="source_input_missing",
            message="Missing source input.",
            retryable=False,
            next_step="Pass a channel list or --source-registry .tgcs/sources.json.",
        )
        return agent_cli.EXIT_VALIDATION
    if not args.login_only and args.channel_list and not args.channel_list.exists():
        agent_cli.emit_error(
            args,
            code="channel_list_not_found",
            message=f"Channel list not found: {args.channel_list}",
            retryable=False,
            next_step="Create the channel list or pass --source-registry.",
        )
        return agent_cli.EXIT_VALIDATION

    try:
        return asyncio.run(_run_scan(args))
    except ScanError as exc:
        agent_cli.emit_error(
            args,
            code="scan_failed",
            message=str(exc),
            retryable=True,
            next_step="Fix scan configuration or Telegram login state, then rerun.",
        )
        return agent_cli.EXIT_AUTH


if __name__ == "__main__":
    raise SystemExit(main())
