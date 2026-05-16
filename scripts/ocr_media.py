"""Process media messages in scan output via shared vision/STT helpers.

This is the standalone re-processing path for JSONL files produced by
scan.py. It reuses scripts.media_ocr so inline scan OCR and later OCR keep the
same download, frame extraction, STT, and cleanup behavior.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tomllib
from pathlib import Path

import openai
from telethon import TelegramClient
from telethon.sessions import StringSession

# Ensure project root is importable when this file is executed directly.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.media_ocr import OCR_PROMPT, OcrConfig, process_message

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

DEFAULT_BASE_URL = "https://api.x.ai/v1"
# Keep standalone OCR aligned with scan.py's xAI default; retired fast Grok
# slugs now fail before image processing starts.
DEFAULT_MODEL = "grok-4.3"
DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_VIDEO_FRAMES = 3


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def load_telegram_config() -> tuple[int, str, str]:
    """Load api_id, api_hash, session_string from the scanner config."""
    api_id = api_hash = None
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
        print(f"Error: missing API credentials in {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    session_str = ""
    if SESSION_PATH.exists():
        session_str = SESSION_PATH.read_text(encoding="utf-8").strip()
    return api_id, api_hash, session_str


def load_jsonl(path: Path) -> list[dict]:
    messages: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def write_jsonl(path: Path, messages: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")


def _make_ocr_config(args, vision_client, stt_client) -> OcrConfig:
    return OcrConfig(
        client=vision_client,
        model=args.model,
        stt_client=stt_client,
        stt_model=args.stt_model,
        language=args.language,
        video_frames=args.video_frames,
        prompt=args.prompt,
        full_video=args.full_video,
    )


async def _run(args) -> int:
    messages = load_jsonl(args.input)
    todo = [
        (i, msg)
        for i, msg in enumerate(messages)
        if msg.get("media_group")
        and not msg.get("ocr_text")
        and msg.get("channel")
        and msg.get("id") is not None
    ]
    if not todo:
        print("No media messages to process.")
        return 0

    print(f"Found {len(todo)} media messages to process.")

    api_key = os.environ.get("XAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: set XAI_API_KEY or OPENAI_API_KEY", file=sys.stderr)
        return 1

    vision_client = openai.OpenAI(base_url=args.base_url, api_key=api_key)
    stt_client = openai.OpenAI(
        base_url=args.stt_base_url or args.base_url,
        api_key=api_key,
    )
    ocr = _make_ocr_config(args, vision_client, stt_client)

    api_id, api_hash, session_str = load_telegram_config()
    tg = TelegramClient(StringSession(session_str), api_id, api_hash)
    await tg.connect()
    if not await tg.is_user_authorized():
        print("Error: Telegram session not authorized. Run scan.py first.", file=sys.stderr)
        await tg.disconnect()
        return 1

    entity_cache: dict[str, object | None] = {}
    for _, msg in todo:
        channel = msg["channel"]
        if channel not in entity_cache:
            try:
                from scripts.scan import resolve_entity

                entity_cache[channel] = await resolve_entity(tg, channel)
            except Exception as exc:
                print(f"  Cannot resolve {channel}: {exc}", file=sys.stderr)
                entity_cache[channel] = None

    counts = {"photo": 0, "video": 0, "voice": 0}
    fail_count = 0
    try:
        for seq, (idx, msg) in enumerate(todo, 1):
            channel = msg["channel"]
            entity = entity_cache.get(channel)
            if not entity:
                fail_count += 1
                continue

            msg_id = msg["id"]
            try:
                tg_msg = await tg.get_messages(entity, ids=msg_id)
                if not tg_msg or not tg_msg.media:
                    continue
            except Exception as exc:
                fail_count += 1
                print(
                    f"  [{seq}/{len(todo)}] Fetch failed {channel}:{msg_id}: {exc}",
                    file=sys.stderr,
                )
                continue

            group = msg.get("media_group")
            try:
                text = await process_message(tg, tg_msg, ocr)
            except Exception as exc:
                fail_count += 1
                print(
                    f"  [{seq}/{len(todo)}] OCR failed {channel}:{msg_id}: {exc}",
                    file=sys.stderr,
                )
                continue
            if not text:
                print(
                    f"  [{seq}/{len(todo)}] OCR skipped {channel}:{msg_id}",
                    file=sys.stderr,
                )
                continue

            messages[idx]["ocr_text"] = text
            if group in counts:
                counts[group] += 1
            print(f"  [{seq}/{len(todo)}] {group} {channel}:{msg_id} -> {len(text)} chars")
    finally:
        await tg.disconnect()

    output = args.output or args.input
    write_jsonl(output, messages)

    total = sum(counts.values())
    print(
        f"Done. {total} media processed "
        f"({counts['photo']} photos, {counts['video']} videos, {counts['voice']} voice)."
    )
    if fail_count:
        print(f"{fail_count} failed.")
    print(f"Output: {output}")
    return 1 if fail_count and not total else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process media messages from scan output via vision/STT APIs.",
        allow_abbrev=False,
    )
    parser.add_argument("--input", type=Path, required=True, help="JSONL scan file")
    parser.add_argument("--output", type=Path, help="Output JSONL (default: overwrite input)")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--stt-model", default=DEFAULT_STT_MODEL)
    parser.add_argument("--stt-base-url", default=None)
    parser.add_argument("--language", help="Language hint for STT (e.g. 'ru', 'en')")
    parser.add_argument("--video-frames", type=positive_int, default=DEFAULT_VIDEO_FRAMES)
    parser.add_argument("--prompt", default=OCR_PROMPT)
    parser.add_argument(
        "--full-video",
        dest="full_video",
        action="store_true",
        help="Download full videos for frame extraction/STT. This uploads more media and may cost more.",
    )
    parser.add_argument(
        "--thumbnail-video",
        dest="full_video",
        action="store_false",
        help="Use video thumbnails only. Kept as an explicit compatibility alias for the default.",
    )
    parser.set_defaults(full_video=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
