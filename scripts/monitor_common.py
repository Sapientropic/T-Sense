"""Shared monitor-state constants and private-data guards.

The split monitor modules all write into the same local SQLite contract. Keep
privacy filters and status enums in one place so review cards, alerts, feedback,
and profile patches do not drift while ``monitor_state`` remains the public
compatibility facade.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

REVIEW_CARD_SCHEMA_VERSION = "review_card_v1"
ALERT_EVENT_SCHEMA_VERSION = "alert_event_v1"
PROFILE_PATCH_SCHEMA_VERSION = "profile_patch_suggestion_v1"
DELIVERY_TARGET_SCHEMA_VERSION = "delivery_target_v1"
DEFAULT_FEEDBACK_EXPORT_PATH = "output/feedback/review-feedback.jsonl"

ALERT_SCHEDULE_MODES = {"work_hours", "all_day", "muted"}
ALERT_RULES = {"high_new_or_changed", "high_new_only"}
PROFILE_RUNTIME_INT_LIMITS = {
    "scan_window_hours": (1, 168),
    "semantic_max_messages": (1, 500),
    "work_interval_minutes": (1, 1440),
    "off_hours_interval_minutes": (1, 1440),
    "alert_max_age_minutes": (1, 10080),
}
PROFILE_RUNTIME_SETTING_LIMITS = PROFILE_RUNTIME_INT_LIMITS
PROFILE_RUNTIME_STRING_FIELDS = {"timezone", "work_start", "work_end", "alert_rule"}
PROFILE_RUNTIME_LIST_FIELDS = {"workdays"}
PROFILE_RUNTIME_SETTINGS_ALLOWED = set(PROFILE_RUNTIME_INT_LIMITS) | PROFILE_RUNTIME_STRING_FIELDS | PROFILE_RUNTIME_LIST_FIELDS
PROFILE_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}

PENDING_STATUS = "pending"
HANDLED_STATUSES = {"kept", "skipped", "false_positive", "follow_up"}
OPEN_OPPORTUNITY_STATUS = "open"
OPPORTUNITY_STATUSES = {"open", "saved", "applied", "contacted", "dismissed", "duplicate"}
LIFECYCLE_ACTIONS = {"applied", "contacted", "saved", "dismissed", "duplicate", "reopen"}
PREFERENCE_ACTIONS = {"keep", "skip", "false_positive", "follow_up"}
REVIEW_ACTIONS = PREFERENCE_ACTIONS | LIFECYCLE_ACTIONS
ACTION_TO_STATUS = {
    "keep": "kept",
    "skip": "skipped",
    "false_positive": "false_positive",
    "follow_up": "follow_up",
}
LIFECYCLE_ACTION_TO_STATUS = {
    "applied": "applied",
    "contacted": "contacted",
    "saved": "saved",
    "dismissed": "dismissed",
    "duplicate": "duplicate",
    "reopen": OPEN_OPPORTUNITY_STATUS,
}

# Review-card item_json is a derived decision surface, not a transcript store.
# Keep provider/media text fields out even when OCR/STT is enabled upstream.
RAW_ITEM_FIELDS = {
    "text",
    "raw_text",
    "message",
    "message_text",
    "body",
    "content",
    "caption",
    "ocr_text",
    "media_text",
    "transcript",
    "transcription",
    "audio_transcript",
    "video_transcript",
}
PRIVATE_ITEM_FIELDS = {
    "api_key",
    "args",
    "argv",
    "artifact_path",
    "authorization",
    "bot_token",
    "client_secret",
    "command",
    "cookie",
    "cookies",
    "cwd",
    "debug",
    "env",
    "environment",
    "headers",
    "metadata",
    "password",
    "path",
    "profile_path",
    "raw",
    "registry_path",
    "request",
    "response",
    "scan_path",
    "secret",
    "session",
    "session_path",
    "token",
    "trace",
}
PRIVATE_ITEM_FIELD_SUFFIXES = (
    "_api_key",
    "_client_secret",
    "_password",
    "_secret",
    "_session_path",
    "_token",
)

PROFILE_TEXT_PRIVATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bot token", re.compile(r"\b\d{5,12}:[A-Za-z0-9_-]{10,}\b")),
    ("provider/API key", re.compile(r"\b(?:sk|sk-proj|sk-ant|ak)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE)),
    ("access token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{12,})\b", re.IGNORECASE)),
    ("authorization header", re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("secret environment assignment", re.compile(r"(?i)\b[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)\b\s*=\s*(?:\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s`'\"]+)")),
    ("secret key/value", re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*(?:\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s`'\"]+)")),
    ("argv dump", re.compile(r"(?i)\b(?:argv|args)\b\s*(?::|=)?\s*\[[^\]]*\]|\b(?:argv|args)\b\s*[:=]\s*[^\r\n]+")),
    ("chat id", re.compile(r"\bchat[_ -]?id\b\s*[:=]?\s*-?\d{5,20}\b", re.IGNORECASE)),
)
PROFILE_TEXT_LOCAL_PATH_RE = re.compile(r"(?i)(?:\b[A-Z]:\\|\\\\[^\\\s]+\\|/(?:Users|home|tmp|var/tmp|private/tmp)/)[^\r\n\"<>|]+")


class MonitorStateError(Exception):
    """Raised when monitor state cannot be loaded or updated safely."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def profile_text_private_fragment_reason(text: object) -> str | None:
    value = str(text or "")
    if not value:
        return None
    for reason, pattern in PROFILE_TEXT_PRIVATE_PATTERNS:
        if pattern.search(value):
            return reason
    if PROFILE_TEXT_LOCAL_PATH_RE.search(value):
        return "local path"
    path_roots = {PROJECT_ROOT}
    try:
        path_roots.add(PROJECT_ROOT.resolve())
    except OSError:
        pass
    try:
        home = Path.home()
        path_roots.add(home)
        path_roots.add(home.resolve())
    except OSError:
        pass
    for root in path_roots:
        raw = str(root)
        if raw and raw in value:
            return "local path"
    return None


def require_profile_text_without_private_fragments(label: str, text: object) -> str:
    value = str(text or "")
    reason = profile_text_private_fragment_reason(value)
    if reason:
        raise MonitorStateError(
            f"{label} cannot include {reason}; remove credentials, local paths, argv dumps, or raw chat identifiers before saving."
        )
    return value


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def non_negative_int(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def display_channel_name(value: str) -> str:
    return str(value or "").strip().lstrip("@") or "unknown"


def title_case_label(value: str) -> str:
    cleaned = re.sub(r"[_-]+", " ", str(value or "")).strip()
    return cleaned.title() if cleaned else "Unknown"
