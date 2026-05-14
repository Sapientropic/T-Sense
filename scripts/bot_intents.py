"""Typed intent routing for the local T-Sense Telegram Bot assistant.

The router deliberately returns product-shaped intents, never command strings.
LLM output is treated as untrusted JSON and is accepted only when it matches the
small bot_intent_v1 schema exactly. Keep button-only actions out of free-text
routing so Telegram text cannot bypass confirmation or local state checks.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from scripts import report, source_registry
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import report, source_registry


BOT_INTENT_SCHEMA_VERSION = "bot_intent_v1"

ALLOWED_INTENT_ACTIONS = {
    "help",
    "knowledge_answer",
    "status",
    "latest",
    "profiles",
    "settings",
    "sources_summary",
    "sources_plan",
    "sources_apply_confirmed",
    "scan_profile_dry_run",
    "card_lifecycle_update",
}

LLM_ROUTABLE_ACTIONS = {
    "help",
    "knowledge_answer",
    "status",
    "latest",
    "profiles",
    "settings",
    "sources_summary",
    "sources_plan",
    "scan_profile_dry_run",
}

INTENT_TOP_LEVEL_FIELDS = {
    "schema_version",
    "action",
    "confidence",
    "source",
    "args",
    "needs_confirmation",
    "safe_reply",
}

CONFIDENCE_VALUES = {"low", "medium", "high"}
SOURCE_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,80}$")
COMMAND_OR_PATH_RE = re.compile(
    r"(\b(?:powershell|cmd(?:\.exe)?|bash|sh|python|node|rm|del|remove-item|subprocess|argv)\b|"
    r"[A-Za-z]:\\|(?:^|\s)/(?:home|users|etc|var|tmp)/)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BotIntent:
    action: str
    confidence: str = "high"
    source: str = "deterministic"
    args: dict[str, Any] = field(default_factory=dict)
    needs_confirmation: bool = False
    safe_reply: str = ""
    schema_version: str = BOT_INTENT_SCHEMA_VERSION

    @property
    def profile_id(self) -> str:
        return str(self.args.get("profile_id") or "jobs-fast")

    @property
    def topic(self) -> str:
        return clean_topic(self.args.get("topic"))

    @property
    def instruction(self) -> str:
        return str(self.args.get("instruction") or "")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "confidence": self.confidence,
            "source": self.source,
            "args": dict(self.args),
            "needs_confirmation": self.needs_confirmation,
            "safe_reply": self.safe_reply,
        }


def clean_topic(value: object) -> str:
    topic = str(value or "jobs").strip().casefold()
    if not topic:
        return "jobs"
    try:
        normalized = source_registry.normalize_topics([topic])
    except source_registry.RegistryError:
        return "jobs"
    return normalized[0] if normalized else "jobs"


def _unsafe_reply() -> str:
    return (
        "Telegram is not a shell gateway. I can't run shell commands, accept file paths, or build argv from Telegram. "
        "Use Signal Desk or a trusted local terminal for that."
    )


def _looks_unsafe(text: str) -> bool:
    return bool(COMMAND_OR_PATH_RE.search(text))


def _is_question_or_usage_request(text: str) -> bool:
    lowered = text.casefold()
    usage_markers = (
        "?",
        "？",
        "how",
        "what",
        "why",
        "where",
        "can i",
        "怎么",
        "如何",
        "怎样",
        "什么",
        "为什么",
        "哪里",
        "能不能",
        "可以",
        "教程",
        "说明",
        "帮助我",
        "用法",
    )
    return any(marker in lowered for marker in usage_markers)


def _topic_from_source_instruction(text: str) -> str:
    # Keep deterministic topic parsing narrow: Telegram text may describe a source
    # in many ways, but the bot must only accept existing registry topics and must
    # not invent source ids, paths, or command-like payloads from loose wording.
    for pattern in (
        r"(?:\bto\b|\btopic\b|主题|到)\s+([a-z0-9][a-z0-9_-]{1,40})",
        r"([a-z0-9][a-z0-9_-]{1,40})\s*(?:topic|主题)",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_topic(match.group(1))
    return "jobs"


def deterministic_intent(text: str) -> BotIntent | None:
    clean = text.strip()
    lowered = clean.casefold()
    if not clean or lowered in {"/start", "start", "menu", "/help", "help", "帮助"}:
        return BotIntent(action="help")
    if _looks_unsafe(clean):
        return BotIntent(action="knowledge_answer", confidence="high", safe_reply=_unsafe_reply())
    status_markers = (
        "配置好",
        "配置情况",
        "有没有配置",
        "是否配置",
        "ready",
        "readiness",
        "configured",
        "setup status",
        "health",
    )
    if lowered.startswith("/status") or lowered in {"status", "状态"} or any(marker in lowered for marker in status_markers):
        return BotIntent(action="status")
    if (
        lowered.startswith("/latest")
        or lowered in {"latest", "最近", "最新"}
        or any(marker in lowered for marker in ("最新结果", "最近结果", "最新卡片", "latest result", "latest card"))
    ):
        return BotIntent(action="latest")
    if lowered.startswith("/profiles") or lowered in {"profiles", "profile", "配置"}:
        return BotIntent(action="profiles")
    if lowered.startswith("/settings") or lowered in {"settings", "设置"}:
        return BotIntent(action="settings")
    scan_markers = (
        "dry scan",
        "dry run",
        "dry-run",
        "practice run",
        "practice scan",
        "fresh scan",
        "run scan",
        "test run",
        "跑一次",
        "跑一遍",
        "扫描",
    )
    if lowered.startswith("/scan") or any(marker in lowered for marker in scan_markers):
        match = re.search(r"(?:/scan|profile)\s+([A-Za-z0-9][A-Za-z0-9_-]{1,80})", clean)
        profile_id = match.group(1) if match else "jobs-fast"
        return BotIntent(action="scan_profile_dry_run", args={"profile_id": profile_id})
    if lowered.startswith("/sources") and len(clean.split()) <= 1:
        return BotIntent(action="sources_summary")
    source_words = (
        "source",
        "sources",
        "add ",
        "remove ",
        "delete ",
        "pause ",
        "disable ",
        "enable ",
        "resume ",
        "添加",
        "删除",
        "移除",
        "暂停",
        "启用",
    )
    has_handle = bool(re.search(r"(?:@|t\.me/)[A-Za-z0-9_]{5,64}|-?\d{5,20}", clean))
    if lowered.startswith("/sources") or (has_handle and any(word in lowered for word in source_words)):
        instruction = re.sub(r"^/sources\s*", "", clean, flags=re.IGNORECASE).strip() or clean
        return BotIntent(
            action="sources_plan",
            args={"instruction": instruction, "topic": _topic_from_source_instruction(instruction)},
            needs_confirmation=True,
        )
    if _is_question_or_usage_request(clean):
        return BotIntent(action="knowledge_answer", confidence="medium", args={"question": clean})
    return None


def _clean_args(action: str, args: object, *, source: str) -> dict[str, Any] | None:
    if not isinstance(args, dict):
        return None
    unknown_arg_keys = sorted(set(args) - {"profile_id", "topic", "instruction", "question"})
    if unknown_arg_keys:
        return None
    cleaned: dict[str, Any] = {}
    if action == "scan_profile_dry_run":
        profile_id = str(args.get("profile_id") or "jobs-fast").strip()
        if profile_id != "jobs-fast" or not PROFILE_ID_RE.fullmatch(profile_id):
            return None
        cleaned["profile_id"] = profile_id
    elif action == "sources_plan":
        instruction = str(args.get("instruction") or "").strip()
        if not instruction or _looks_unsafe(instruction):
            return None
        cleaned["instruction"] = instruction[:4000]
        topic = str(args.get("topic") or "jobs").strip().casefold()
        if not SOURCE_TOPIC_RE.fullmatch(topic):
            cleaned["topic"] = "jobs"
            if source == "llm":
                cleaned["topic_warning"] = "[⚠️] Topic was not valid, so I used jobs."
        else:
            cleaned["topic"] = topic
    elif action == "knowledge_answer":
        question = str(args.get("question") or "").strip()
        if question:
            cleaned["question"] = question[:1000]
    return cleaned


def validate_llm_intent_payload(payload: object) -> BotIntent | None:
    if not isinstance(payload, dict):
        return None
    if set(payload) != INTENT_TOP_LEVEL_FIELDS:
        return None
    if payload.get("schema_version") != BOT_INTENT_SCHEMA_VERSION:
        return None
    if payload.get("source") != "llm":
        return None
    if not isinstance(payload.get("needs_confirmation"), bool):
        return None
    if not isinstance(payload.get("safe_reply"), str):
        return None
    action = str(payload.get("action") or "").strip()
    if action not in LLM_ROUTABLE_ACTIONS:
        return None
    confidence = str(payload.get("confidence") or "medium").strip().lower()
    if confidence not in CONFIDENCE_VALUES:
        return None
    args = _clean_args(action, payload.get("args") or {}, source="llm")
    if args is None:
        return None
    safe_reply = str(payload.get("safe_reply") or "").strip()
    if _looks_unsafe(safe_reply):
        safe_reply = ""
    topic_warning = str(args.pop("topic_warning", "") or "")
    if topic_warning:
        safe_reply = f"{topic_warning} {safe_reply}".strip()
    needs_confirmation = bool(payload.get("needs_confirmation")) or action == "sources_plan"
    return BotIntent(
        action=action,
        confidence=confidence,
        source="llm",
        args=args,
        needs_confirmation=needs_confirmation,
        safe_reply=safe_reply[:500],
    )


def llm_intent(text: str) -> BotIntent | None:
    if not report.llm_key_available():
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)
    provider = report.llm_provider(base_url, model)
    api_key = report.api_key_for_provider(provider)
    if not api_key:
        return None
    system_prompt = (
        "Map one Telegram message to bot_intent_v1 JSON only. "
        f"Allowed actions: {', '.join(sorted(LLM_ROUTABLE_ACTIONS))}. "
        "Never return commands, file paths, shell, argv, tokens, chat ids, or raw Telegram message data. "
        "For readiness, health, setup, configured, or 有没有配置好 questions, use action status. "
        "For AI review, scan, or run-now requests, use action scan_profile_dry_run with "
        "args.profile_id exactly jobs-fast. "
        "For source changes, set action sources_plan, keep the original instruction, and infer a topic only "
        "when the user clearly names one."
    )
    user_prompt = json.dumps(
        {
            "message": text[:2000],
            "schema": {
                "schema_version": BOT_INTENT_SCHEMA_VERSION,
                "action": "knowledge_answer",
                "confidence": "medium",
                "source": "llm",
                "args": {"question": text[:1000]},
                "needs_confirmation": False,
                "safe_reply": "",
            },
        },
        ensure_ascii=False,
    )
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": report.llm_temperature(provider),
    }
    if provider in {"deepseek", "openai"}:
        create_kwargs["response_format"] = {"type": "json_object"}
    thinking_extra = report.minimax_thinking_extra(provider) or report.deepseek_thinking_extra(provider, model)
    if thinking_extra:
        create_kwargs["extra_body"] = thinking_extra
    report.add_token_limit(create_kwargs, provider=provider, max_tokens=500)
    try:
        response = OpenAI(api_key=api_key, base_url=base_url).chat.completions.create(**create_kwargs)
        payload = json.loads(report.strip_json_fence(response.choices[0].message.content or "{}"))
    except Exception:
        return None
    return validate_llm_intent_payload(payload)


def route_text_to_intent(text: str, *, use_llm: bool = False) -> BotIntent:
    deterministic = deterministic_intent(text)
    if deterministic:
        if deterministic.action == "knowledge_answer" and not use_llm and not deterministic.safe_reply:
            return BotIntent(
                action=deterministic.action,
                confidence=deterministic.confidence,
                source="deterministic-no-llm",
                args=deterministic.args,
                needs_confirmation=deterministic.needs_confirmation,
                safe_reply=deterministic.safe_reply,
            )
        return deterministic
    if use_llm:
        routed = llm_intent(text)
        if routed:
            return routed
    return BotIntent(
        action="knowledge_answer",
        confidence="low",
        source="deterministic-no-llm",
        args={"question": text.strip()[:1000]},
    )
