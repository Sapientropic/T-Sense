"""Process media messages in scan output via vision/STT APIs.

Reads JSONL from scan.py, connects to Telegram, downloads media on-demand
(temp file → OCR → delete), and adds ocr_text to each record.

Supports: xAI Grok (default), OpenAI, or any OpenAI-compatible endpoint.

Usage:
  export XAI_API_KEY=your-key
  python scripts/ocr_media.py --input output/scan_XXXX.jsonl

  # With OpenAI:
  OPENAI_API_KEY=sk-xxx python scripts/ocr_media.py \\
    --input output/scan_XXXX.jsonl \\
    --base-url https://api.openai.com/v1 --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import openai
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto

# ---------------------------------------------------------------------------
# Config (reuses scan.py's config location)
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(
    os.environ.get(
        "TGCLI_CONFIG_DIR",
        os.path.join(
            os.environ.get("USERPROFILE", os.path.expanduser("~")),
            ".config", "tgcli",
        ),
    )
)
CONFIG_PATH = CONFIG_DIR / "config.toml"
SESSION_PATH = CONFIG_DIR / "session"

DEFAULT_BASE_URL = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-4.1-fast"
DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_VIDEO_FRAMES = 3
MAX_MEDIA_SIZE = 50 * 1024 * 1024  # skip files > 50 MB

OCR_PROMPT = (
    "Extract all text from this image exactly as written. "
    "Output only the extracted text, nothing else."
)
VIDEO_PROMPT = (
    "These are frames from a video. "
    "Extract all visible text exactly as written. "
    "Output only the extracted text, nothing else."
)


def load_telegram_config() -> tuple[int, str, str]:
    """Load api_id, api_hash, session_string from config."""
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


# ---------------------------------------------------------------------------
# Media helpers
# ---------------------------------------------------------------------------

async def download_to_temp(client: TelegramClient, msg, ext: str) -> Path | None:
    """Download media to a temp file. Caller is responsible for cleanup."""
    # Size check
    doc = getattr(msg.media, "document", None)
    if doc:
        size = getattr(doc, "size", 0) or 0
        if size > MAX_MEDIA_SIZE:
            return None
    fd, path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        await client.download_media(msg, file=path)
        if os.path.getsize(path) == 0:
            os.unlink(path)
            return None
        return Path(path)
    except Exception:
        if os.path.exists(path):
            os.unlink(path)
        return None


def extract_video_frames(video_path: Path, max_frames: int = 3) -> list[Path]:
    """Extract key frames via ffmpeg."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(probe.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        duration = 10.0

    frames: list[Path] = []
    tmp = tempfile.mkdtemp()
    for i in range(max_frames):
        t = duration * (i + 1) / (max_frames + 1)
        out = Path(tmp) / f"frame_{i}.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-ss", str(t), "-i", str(video_path),
                 "-frames:v", "1", "-q:v", "2", str(out)],
                capture_output=True, timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        if out.exists() and out.stat().st_size > 0:
            frames.append(out)
    return frames


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def ocr_image(client: openai.OpenAI, model: str, path: Path, prompt: str) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{b64}",
            }},
        ]}],
    )
    return resp.choices[0].message.content or ""


def ocr_video(client: openai.OpenAI, model: str, path: Path) -> str:
    frames = extract_video_frames(path)
    if not frames:
        return ""
    content: list[dict] = [{"type": "text", "text": VIDEO_PROMPT}]
    for fp in frames:
        b64 = base64.b64encode(fp.read_bytes()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
        fp.unlink(missing_ok=True)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
    )
    return resp.choices[0].message.content or ""


def transcribe_audio(
    client: openai.OpenAI, path: Path, stt_model: str, language: str | None,
) -> str:
    with open(path, "rb") as f:
        kwargs: dict = {"model": stt_model, "file": f}
        if language:
            kwargs["language"] = language
        resp = client.audio.transcriptions.create(**kwargs)
    return resp.text


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

async def _run(args) -> int:
    # Read JSONL
    messages: list[dict] = []
    with args.input.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))

    # Filter to messages that need processing
    todo = [
        (i, msg) for i, msg in enumerate(messages)
        if msg.get("media_group") and not msg.get("ocr_text")
           and msg.get("channel") and msg.get("id")
    ]
    if not todo:
        print("No media messages to process.")
        return 0

    print(f"Found {len(todo)} media messages to process.")

    # Setup API clients
    api_key = os.environ.get("XAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: set XAI_API_KEY or OPENAI_API_KEY", file=sys.stderr)
        return 1

    vision_client = openai.OpenAI(base_url=args.base_url, api_key=api_key)
    stt_client = openai.OpenAI(
        base_url=args.stt_base_url or args.base_url, api_key=api_key,
    )

    # Setup Telegram client
    api_id, api_hash, session_str = load_telegram_config()
    tg = TelegramClient(StringSession(session_str), api_id, api_hash)
    await tg.connect()
    if not await tg.is_user_authorized():
        print("Error: Telegram session not authorized. Run scan.py first.", file=sys.stderr)
        await tg.disconnect()
        return 1

    # Resolve channels → entities (cache to avoid re-resolving)
    entity_cache: dict[str, object] = {}
    for idx, msg in todo:
        channel = msg["channel"]
        if channel not in entity_cache:
            try:
                from scripts.scan import resolve_entity
                entity_cache[channel] = await resolve_entity(tg, channel)
            except Exception as exc:
                print(f"  Cannot resolve {channel}: {exc}", file=sys.stderr)
                entity_cache[channel] = None

    # Process
    counts = {"photo": 0, "video": 0, "voice": 0}
    fail_count = 0
    temp_files: list[Path] = []

    try:
        for seq, (idx, msg) in enumerate(todo, 1):
            channel = msg["channel"]
            entity = entity_cache.get(channel)
            if not entity:
                continue

            group = msg["media_group"]
            msg_id = msg["id"]

            # Fetch the original message
            try:
                tg_msg = await tg.get_messages(entity, ids=msg_id)
                if not tg_msg or not tg_msg.media:
                    continue
            except Exception as exc:
                print(f"  [{seq}/{len(todo)}] Fetch failed {channel}:{msg_id}: {exc}", file=sys.stderr)
                fail_count += 1
                continue

            # Determine extension
            if tg_msg.voice:
                ext = ".ogg"
            elif tg_msg.video:
                ext = ".mp4"
            elif isinstance(tg_msg.media, MessageMediaPhoto):
                ext = ".jpg"
            else:
                continue

            # Download to temp
            path = await download_to_temp(tg, tg_msg, ext)
            if not path:
                print(f"  [{seq}/{len(todo)}] Download skipped {channel}:{msg_id}", file=sys.stderr)
                continue
            temp_files.append(path)

            # Process
            try:
                if group == "photo":
                    text = ocr_image(vision_client, args.model, path, args.prompt)
                    counts["photo"] += 1
                elif group == "video":
                    text = ocr_video(vision_client, args.model, path)
                    counts["video"] += 1
                elif group == "voice":
                    text = transcribe_audio(stt_client, path, args.stt_model, args.language)
                    counts["voice"] += 1
                else:
                    continue

                messages[idx]["ocr_text"] = text
                print(f"  [{seq}/{len(todo)}] {group} {channel}:{msg_id} -> {len(text)} chars")

            except Exception as exc:
                fail_count += 1
                print(f"  [{seq}/{len(todo)}] OCR failed {channel}:{msg_id}: {exc}", file=sys.stderr)

            # Clean up temp file immediately
            path.unlink(missing_ok=True)
            if path in temp_files:
                temp_files.remove(path)

    finally:
        # Ensure all temp files are cleaned up
        for p in temp_files:
            p.unlink(missing_ok=True)
        await tg.disconnect()

    # Write output
    output = args.output or args.input
    with output.open("w", encoding="utf-8", newline="\n") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    total = sum(counts.values())
    print(f"Done. {total} media processed "
          f"({counts['photo']} photos, {counts['video']} videos, {counts['voice']} voice).")
    if fail_count:
        print(f"{fail_count} failed.")
    print(f"Output: {output}")
    return 1 if fail_count and not total else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process media messages from scan output via vision/STT APIs."
    )
    parser.add_argument("--input", type=Path, required=True, help="JSONL scan file")
    parser.add_argument("--output", type=Path, help="Output JSONL (default: overwrite input)")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--stt-model", default=DEFAULT_STT_MODEL)
    parser.add_argument("--stt-base-url", default=None)
    parser.add_argument("--language", help="Language hint for STT (e.g. 'ru', 'en')")
    parser.add_argument("--video-frames", type=int, default=DEFAULT_VIDEO_FRAMES)
    parser.add_argument("--prompt", default=OCR_PROMPT)
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
