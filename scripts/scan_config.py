"""Scanner configuration, argument validation, and credential helpers."""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

try:
    from scripts import local_credentials
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts import local_credentials

DEFAULT_HOURS = 24
DEFAULT_MAX_LIMIT = 5000
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_SCAN_CONCURRENCY = 2
DEFAULT_MAX_FLOOD_WAIT_SECONDS = 300
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
# Use xAI's current chat+image model for OCR. Older fast Grok slugs have been
# retired or removed from the API, so pinning them makes live OCR fail at setup.
DEFAULT_XAI_OCR_MODEL = "grok-4.3"
DEFAULT_OPENAI_OCR_MODEL = "gpt-4o-mini"
DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_VIDEO_FRAMES = 3
LOCAL_OCR_SECRET_TARGETS = {
    "OPENAI_API_KEY": "tgcs.signal-desk.openai-api-key",
    "XAI_API_KEY": "tgcs.signal-desk.xai-api-key",
}
LOGIN_QUIT_COMMANDS = {"q", "quit", "exit", "cancel"}
LOGIN_RESEND_COMMANDS = {"r", "resend"}
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
class ScannerConfig:
    api_id: int
    api_hash: str
    session_string: str



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



def ai_secret(env_name: str) -> str | None:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    target = LOCAL_OCR_SECRET_TARGETS.get(env_name)
    if not target:
        return None
    try:
        stored = local_credentials.read_secret(target)
    except local_credentials.CredentialStoreError:
        return None
    return stored.secret.strip() if stored and stored.secret.strip() else None
