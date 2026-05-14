"""Bot-facing action facade and final Telegram reply redaction."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts import bot_intents, bot_knowledge, dashboard_server
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import bot_intents, bot_knowledge, dashboard_server


BOT_TOKEN_RE = re.compile(r"\b\d{5,12}:[A-Za-z0-9_-]{10,}\b")
PROVIDER_KEY_RE = re.compile(r"\b(?:sk|sk-proj|sk-ant|ak)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE)
ACCESS_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{12,})\b", re.IGNORECASE)
AUTHORIZATION_RE = re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]{8,}")
ENV_SECRET_RE = re.compile(r"(?i)\b[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)\b\s*=\s*(?:\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s`'\"]+)")
KEY_VALUE_SECRET_RE = re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*(?:\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s`'\"]+)")
ARGV_DUMP_RE = re.compile(r"(?i)\b(?:argv|args)\b\s*(?::|=)?\s*\[[^\]]*\]|\b(?:argv|args)\b\s*[:=]\s*[^\r\n]+")
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s`'\"]+")
UNC_PATH_RE = re.compile(r"\\\\[^\\\s]+\\[^\s`'\"]+")
POSIX_PRIVATE_PATH_RE = re.compile(r"(?<!\w)/(?:home|Users|users|var|tmp|etc|private/tmp)/[^\s`'\"]+")
CHAT_ID_FIELD_RE = re.compile(r"\bchat[_ -]?id\b\s*[:=]?\s*-?\d{5,20}\b", re.IGNORECASE)
BARE_CHAT_ID_RE = re.compile(r"(?<![\w:])-?\d{8,20}(?!\w)")
TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\):.*", re.IGNORECASE | re.DOTALL)
RAW_MESSAGE_FIELD_RE = re.compile(r'(?i)"(?:text|message|raw_message|body)"\s*:\s*"[^"]{12,}"')
KNOWLEDGE_REPLY_MARKUP = {
    "inline_keyboard": [
        [
            {"text": "Status", "callback_data": "status"},
            {"text": "Latest", "callback_data": "latest"},
        ],
        [
            {"text": "Sources", "callback_data": "sources"},
        ],
        [
            {"text": "Profiles", "callback_data": "profiles"},
            {"text": "Settings", "callback_data": "settings"},
        ],
    ]
}


@dataclass(frozen=True)
class BotActionResult:
    text: str
    reply_markup: dict[str, Any] | None = None
    error_category: str = ""


def redact_telegram_reply(text: object) -> str:
    clean = str(text or "")
    clean = TRACEBACK_RE.sub("Local action failed. Open Signal Desk Runs or Settings for details.", clean)
    clean = BOT_TOKEN_RE.sub("[redacted-token]", clean)
    clean = PROVIDER_KEY_RE.sub("[redacted-key]", clean)
    clean = ACCESS_TOKEN_RE.sub("[redacted-token]", clean)
    clean = AUTHORIZATION_RE.sub("Authorization: Bearer [redacted-key]", clean)
    clean = ENV_SECRET_RE.sub(lambda match: f"{match.group(0).split('=')[0].strip()}=[redacted-secret]", clean)
    clean = KEY_VALUE_SECRET_RE.sub(lambda match: re.split(r"[:=]", match.group(0), maxsplit=1)[0].strip() + "=[redacted-secret]", clean)
    clean = ARGV_DUMP_RE.sub("argv=[redacted-argv]", clean)
    clean = WINDOWS_PATH_RE.sub("[redacted-path]", clean)
    clean = UNC_PATH_RE.sub("[redacted-path]", clean)
    clean = POSIX_PRIVATE_PATH_RE.sub("[redacted-path]", clean)
    clean = CHAT_ID_FIELD_RE.sub("chat_id [redacted-chat-id]", clean)
    clean = RAW_MESSAGE_FIELD_RE.sub('"text":"[redacted-message]"', clean)
    clean = BARE_CHAT_ID_RE.sub("[redacted-chat-id]", clean)
    return clean.strip() or "Done."


class BotActionRegistry:
    def __init__(self, *, knowledge: bot_knowledge.BotKnowledge | None = None):
        self.knowledge = knowledge or bot_knowledge.BotKnowledge()

    def execute(self, intent: bot_intents.BotIntent) -> BotActionResult:
        if intent.action == "knowledge_answer":
            if intent.safe_reply:
                return BotActionResult(redact_telegram_reply(intent.safe_reply), reply_markup=KNOWLEDGE_REPLY_MARKUP)
            question = str(intent.args.get("question") or "")
            answer = self.knowledge.answer(question, use_llm=intent.source != "deterministic-no-llm")
            return BotActionResult(redact_telegram_reply(answer.text), reply_markup=KNOWLEDGE_REPLY_MARKUP)
        if intent.action == "scan_profile_dry_run":
            return self._scan_profile_dry_run(intent)
        return BotActionResult(
            "I can only run allowlisted T-Sense bot actions. Send /help to see what is available.",
            error_category="unsupported_request",
        )

    def _scan_profile_dry_run(self, intent: bot_intents.BotIntent) -> BotActionResult:
        profile_id = intent.profile_id
        if profile_id != "jobs-fast":
            return BotActionResult(
                "Telegram AI reviews are limited to jobs-fast in v1. Open Signal Desk for other profiles.",
                error_category="unsupported_request",
            )
        try:
            result = dashboard_server.run_desk_action("monitor_jobs_dry_run")
        except Exception:
            return BotActionResult(
                "Local AI review failed. Open Signal Desk Runs or Settings for details.",
                error_category="local_failure",
            )
        status = str(result.get("status") or "")
        if status == "blocked":
            detail = str(result.get("detail") or "Another local action is already running.")
            next_action = str(result.get("next_action") or "Wait for the current action to finish, then retry.")
            return BotActionResult(redact_telegram_reply(f"{detail}\n\nNext: {next_action}"), error_category="action_busy")
        if status != "success":
            detail = str(result.get("detail") or "Local AI review failed.")
            next_action = str(result.get("next_action") or "Open Signal Desk Runs or Settings.")
            return BotActionResult(redact_telegram_reply(f"{detail}\n\nNext: {next_action}"), error_category="local_failure")
        detail = str(result.get("detail") or result.get("title") or "AI review finished.")
        next_action = str(result.get("next_action") or "")
        text = detail if not next_action else f"{detail}\n\nNext: {next_action}"
        return BotActionResult(redact_telegram_reply(text))
