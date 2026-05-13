"""Pure JSON contract helpers for report generation.

Keep this module free of provider, CLI, Markdown, and HTML concerns. It is the
small shared boundary that agent-produced JSON must pass before report.py can
turn it into product artifacts.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


AGENT_EXTRACTION_REQUEST_SCHEMA_VERSION = "agent_extraction_request_v1"
SEMANTIC_ITEMS_SCHEMA_VERSION = "semantic_items_v1"

SEMANTIC_ITEM_PRIVATE_FIELDS = {
    "api_key",
    "args",
    "argv",
    "artifact_path",
    "authorization",
    "body",
    "bot_token",
    "caption",
    "client_secret",
    "command",
    "content",
    "cookie",
    "cookies",
    "cwd",
    "debug",
    "env",
    "environment",
    "headers",
    "media_text",
    "message",
    "message_text",
    "ocr_text",
    "password",
    "path",
    "raw",
    "raw_message",
    "raw_text",
    "request",
    "response",
    "secret",
    "session",
    "session_path",
    "text",
    "token",
    "trace",
    "transcript",
    "transcription",
}

SEMANTIC_ITEM_PRIVATE_FIELD_SUFFIXES = (
    "_api_key",
    "_client_secret",
    "_password",
    "_path",
    "_raw_text",
    "_secret",
    "_session",
    "_session_path",
    "_token",
    "_transcript",
)


def _as_list(value: object) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def _source_ref_key(channel: object, message_id: object) -> str:
    return f"{channel}\x1f{message_id}"


def _clean_source_ref(channel: object, message_id: object) -> dict | None:
    channel_text = str(channel or "").strip()
    if not channel_text:
        return None
    try:
        parsed_id = int(message_id)
    except (TypeError, ValueError):
        return None
    return {"channel": channel_text, "id": parsed_id}


def _build_message_lookup(messages: Iterable[dict] | None) -> dict:
    by_ref: dict[str, dict] = {}
    for message in messages or []:
        ref = _clean_source_ref(message.get("channel"), message.get("id"))
        if ref is None:
            continue
        by_ref[_source_ref_key(ref["channel"], ref["id"])] = message
    return {"by_ref": by_ref}


def _merge_source_refs(existing: Iterable, incoming: Iterable) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        ref = _clean_source_ref(item.get("channel"), item.get("id"))
        if ref is None:
            continue
        marker = _source_ref_key(ref["channel"], ref["id"])
        if marker in seen:
            continue
        result.append(ref)
        seen.add(marker)
    return result


def semantic_item_private_field_path(value: Any, prefix: str) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            normalized = re.sub(r"[^a-z0-9]+", "_", key_text.casefold()).strip("_")
            current_path = f"{prefix}.{key_text}"
            if normalized in SEMANTIC_ITEM_PRIVATE_FIELDS or normalized.endswith(SEMANTIC_ITEM_PRIVATE_FIELD_SUFFIXES):
                return current_path
            nested_path = semantic_item_private_field_path(nested, current_path)
            if nested_path:
                return nested_path
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            nested_path = semantic_item_private_field_path(nested, f"{prefix}[{index}]")
            if nested_path:
                return nested_path
    return None


def validate_semantic_items(items: list, messages: list[dict]) -> list[str]:
    lookup = _build_message_lookup(messages)
    issues: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(f"items[{index}] must be an object")
            continue
        private_field = semantic_item_private_field_path(item, f"items[{index}]")
        if private_field:
            issues.append(f"{private_field} is not allowed in {SEMANTIC_ITEMS_SCHEMA_VERSION}")
        refs = _merge_source_refs([], _as_list(item.get("source_message_refs")))
        if not refs:
            issues.append(f"items[{index}].source_message_refs is required")
            continue
        for ref in refs:
            marker = _source_ref_key(ref["channel"], ref["id"])
            if marker not in lookup["by_ref"]:
                issues.append(
                    f"items[{index}].source_message_refs contains unknown ref "
                    f"{ref['channel']}:{ref['id']}"
                )
    return issues


def extraction_prompt_meta(meta: dict | None) -> dict:
    if not isinstance(meta, dict):
        return {}
    # Agent/LLM extraction gets only a small cache-friendly run summary. Full
    # scan sidecars can contain source-health rows, timestamps, and local paths;
    # those belong in manifests and diagnostics, not in provider or fallback
    # extraction contracts.
    stable_keys = (
        "scan_date",
        "scan_window",
        "channel_count",
        "total_messages_collected",
        "failure_count",
        "incomplete_count",
        "ocr_enabled",
        "ocr_count",
    )
    summary: dict[str, Any] = {}
    for key in stable_keys:
        value = meta.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
    return summary


def extraction_prompt_messages(messages: Iterable[dict]) -> list[dict]:
    prompt_keys = (
        "channel",
        "id",
        "date",
        "text",
        "origin_channel",
        "origin_url",
        "origin_message_ref",
    )
    prompt_messages: list[dict] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        item: dict[str, Any] = {}
        for key in prompt_keys:
            value = message.get(key)
            if value not in (None, "", [], {}):
                item[key] = value
        prompt_messages.append(item)
    return prompt_messages


def profile_field_contract(profile_config: Any) -> list[dict]:
    return [
        {
            "name": field.name,
            "required": field.required,
            "type": field.type,
            "values": field.values,
            "extract_all": field.extract_all,
        }
        for field in profile_config.mode.fields
    ]
