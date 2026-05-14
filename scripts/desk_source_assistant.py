"""Source assistant planning helpers for Signal Desk.

This module owns the free-text and optional LLM source planning flow. Registry
mutation remains in ``desk_sources`` through injected callbacks so the assistant
cannot silently bypass the dashboard facade gates or monkeypatch-compatible
helpers that tests and desktop routes rely on.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import report, source_registry

DESK_SOURCE_ASSISTANT_ALLOWED_FIELDS = {
    "instruction",
    "topic",
    "dry_run",
    "confirm_external_ai",
    "resolved_plan",
    "profile_id",
    "folder_name",
    "folder_id",
}

SourceOperationPayload = Callable[..., dict]
DeskSourceRecord = Callable[[dict], dict]
ValidateSourceId = Callable[[str], str]
CleanSourceTopic = Callable[[object], str]
LlmPlan = Callable[[str, str, dict[str, dict]], dict[str, list[str]]]
DiscoverSourceChannels = Callable[..., list[dict]]
ProfileContext = Callable[[str], dict[str, str]]


def _reject_unexpected_source_assistant_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_ASSISTANT_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source assistant field: {', '.join(unexpected)}")


def _extract_source_channels_from_text(text: str) -> list[str]:
    channels: list[str] = []
    for match in re.finditer(r"(?:https?://)?t\.me/(?:s/)?([A-Za-z0-9_]{5,64}|-?[0-9]{5,20})", text, re.IGNORECASE):
        channels.append(match.group(1))
    for match in re.finditer(r"@([A-Za-z0-9_]{5,64})", text):
        channels.append(match.group(1))
    for line in text.splitlines():
        clean = source_registry.normalize_channel_name(line)
        if re.fullmatch(r"(?:[A-Za-z0-9_]{5,64}|-?[0-9]{5,20})", clean):
            channels.append(clean)
    deduped: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        key = channel.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(channel)
    return deduped


def _source_id_from_channel(channel: str) -> str:
    source = source_registry.source_from_channel(channel)
    return str(source["source_id"])


def _source_assistant_action(text: str) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ("delete", "remove", "prune", "drop", "删", "删除", "移除", "清掉", "去掉")):
        return "remove"
    if any(word in lowered for word in ("pause", "disable", "mute", "stop", "暂停", "停用", "禁用")):
        return "disable"
    if any(word in lowered for word in ("enable", "resume", "use", "restore", "启用", "恢复", "使用")):
        return "enable"
    return "add"


def _source_assistant_plan(instruction: str) -> dict[str, list[str]]:
    plan = {"add": [], "remove": [], "disable": [], "enable": []}
    segments = [segment.strip() for segment in re.split(r"[\n;；。]+", instruction) if segment.strip()]
    for segment in segments or [instruction]:
        action = _source_assistant_action(segment)
        channels = _extract_source_channels_from_text(segment)
        if not channels:
            continue
        plan[action].extend(channels)
    for key, values in plan.items():
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = source_registry.normalize_channel_name(value)
            marker = normalized.casefold()
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(normalized)
        plan[key] = deduped
    return plan


def _source_assistant_has_plan(plan: dict[str, list[str]]) -> bool:
    return any(bool(values) for values in plan.values())


def _source_assistant_requested_existing_actions(instruction: str) -> set[str]:
    requested: set[str] = set()
    segments = [segment.strip() for segment in re.split(r"[\n;；。]+", instruction) if segment.strip()]
    for segment in segments or [instruction]:
        action = _source_assistant_action(segment)
        if action in {"remove", "disable", "enable"}:
            requested.add(action)
    return requested


def _source_assistant_should_use_llm_plan(instruction: str, plan: dict[str, list[str]]) -> bool:
    if not _source_assistant_has_plan(plan):
        return True
    requested_existing_actions = _source_assistant_requested_existing_actions(instruction)
    return any(not plan[action] for action in requested_existing_actions)


def _dedupe_source_ids(source_ids: list[str], *, validate_source_id: ValidateSourceId) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        clean = validate_source_id(source_id)
        marker = clean.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(clean)
    return deduped


def _dedupe_source_channels(channels: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        clean = source_registry.normalize_channel_name(channel)
        if not clean:
            continue
        marker = clean.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(clean)
    return deduped


def _clean_resolved_source_plan(plan: dict, *, validate_source_id: ValidateSourceId) -> dict[str, list[str]]:
    if not isinstance(plan, dict):
        raise ValueError("Source plan must be an object.")
    return {
        "add": _dedupe_source_channels([str(value) for value in plan.get("add") or []]),
        "remove": _dedupe_source_ids([str(value) for value in plan.get("remove") or []], validate_source_id=validate_source_id),
        "disable": _dedupe_source_ids([str(value) for value in plan.get("disable") or []], validate_source_id=validate_source_id),
        "enable": _dedupe_source_ids([str(value) for value in plan.get("enable") or []], validate_source_id=validate_source_id),
    }


def _clean_folder_id(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("Telegram folder ID must be a number.")
    try:
        folder_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Telegram folder ID must be a number.") from exc
    if folder_id <= 0:
        raise ValueError("Telegram folder ID must be a positive number.")
    return folder_id


def _source_discovery_requested(body: dict, instruction: str) -> bool:
    if str(body.get("profile_id") or "").strip():
        return True
    if str(body.get("folder_name") or "").strip() or body.get("folder_id") not in (None, ""):
        return True
    lowered = instruction.casefold()
    return any(token in lowered for token in ("scan all", "discover", "telegram channels", "folder", "扫", "扫描", "频道", "文件夹"))


def _sanitize_discovered_candidates(candidates: list[dict]) -> list[dict]:
    sanitized: list[dict] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        channel = source_registry.normalize_channel_name(candidate.get("channel"))
        if not channel:
            continue
        marker = channel.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        sanitized.append(
            {
                "channel": channel,
                "label": str(candidate.get("label") or candidate.get("title") or channel).strip(),
                "title": str(candidate.get("title") or candidate.get("label") or channel).strip(),
                "folder": str(candidate.get("folder") or "").strip(),
            }
        )
    return sanitized


def _source_assistant_llm_plan(
    instruction: str,
    topic: str,
    existing: dict[str, dict],
    *,
    validate_source_id: ValidateSourceId,
    profile_text: str = "",
    candidates: list[dict] | None = None,
) -> dict[str, list[str]]:
    if not report.llm_key_available():
        raise ValueError("Save an AI API key in Settings before using AI source planning.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("Install optional LLM dependencies before using AI source planning.") from exc

    base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)
    provider = report.llm_provider(base_url, model)
    api_key = report.api_key_for_provider(provider)
    if not api_key:
        raise ValueError("Save an AI API key in Settings before using AI source planning.")

    sources = [
        {
            "source_id": source_id,
            "label": str(source.get("label") or ""),
            "channel": source_registry.channel_value(source),
            "topics": source_registry.normalize_topics(source.get("topics") or []),
            "enabled": bool(source.get("enabled", True)),
        }
        for source_id, source in sorted(existing.items())
    ][:300]
    candidate_sources = [
        {
            "channel": source_registry.normalize_channel_name(candidate.get("channel")),
            "label": str(candidate.get("label") or candidate.get("title") or candidate.get("channel") or ""),
            "title": str(candidate.get("title") or candidate.get("label") or candidate.get("channel") or ""),
            "folder": str(candidate.get("folder") or ""),
        }
        for candidate in (candidates or [])
        if isinstance(candidate, dict) and source_registry.normalize_channel_name(candidate.get("channel"))
    ][:500]
    system_prompt = (
        "You plan local Telegram source registry changes. Return JSON only with keys "
        "add, remove, disable, enable. add must contain Telegram channel values copied "
        "exactly from candidate_sources.channel. remove/disable/enable must contain source_id "
        "strings copied exactly from existing_sources.source_id. Select channels semantically "
        "against the profile text; do not invent channels, ids, commands, paths, argv, or tokens."
    )
    user_prompt = json.dumps(
        {
            "instruction": instruction,
            "topic": topic,
            "profile_text": profile_text[:12000],
            "candidate_sources": candidate_sources,
            "existing_sources": sources,
            "output_schema": {
                "add": ["candidate channel"],
                "remove": ["telegram:..."],
                "disable": ["telegram:..."],
                "enable": ["telegram:..."],
            },
        },
        ensure_ascii=False,
    )
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": report.llm_temperature(provider),
    }
    if provider in {"deepseek", "openai"}:
        create_kwargs["response_format"] = {"type": "json_object"}
    thinking_extra = report.minimax_thinking_extra(provider) or report.deepseek_thinking_extra(provider, model)
    if thinking_extra:
        create_kwargs["extra_body"] = thinking_extra
    report.add_token_limit(create_kwargs, provider=provider, max_tokens=700)

    try:
        response = OpenAI(api_key=api_key, base_url=base_url).chat.completions.create(**create_kwargs)
    except Exception as exc:
        raise ValueError(f"AI source planning failed: {exc}") from exc
    raw = response.choices[0].message.content or ""
    try:
        payload = json.loads(report.strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("AI source planning did not return valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("AI source planning must return a JSON object.")

    existing_ids = set(existing)
    candidate_channels = {
        source_registry.normalize_channel_name(candidate.get("channel")).casefold(): source_registry.normalize_channel_name(candidate.get("channel"))
        for candidate in candidate_sources
    }
    plan: dict[str, list[str]] = {"add": [], "remove": [], "disable": [], "enable": []}
    for action in plan:
        values = payload.get(action) or []
        if not isinstance(values, list):
            raise ValueError("AI source planning returned an invalid action list.")
        for value in values:
            if action == "add":
                channel = source_registry.normalize_channel_name(str(value))
                matched = candidate_channels.get(channel.casefold())
                if matched:
                    plan[action].append(matched)
                continue
            source_id = validate_source_id(str(value))
            if source_id in existing_ids:
                plan[action].append(source_id)
    return {
        "add": _dedupe_source_channels(plan["add"]),
        "remove": _dedupe_source_ids(plan["remove"], validate_source_id=validate_source_id),
        "disable": _dedupe_source_ids(plan["disable"], validate_source_id=validate_source_id),
        "enable": _dedupe_source_ids(plan["enable"], validate_source_id=validate_source_id),
    }


def run_source_assistant(
    body: dict,
    *,
    registry_path: Path,
    clean_source_topic: CleanSourceTopic,
    source_operation_payload: SourceOperationPayload,
    desk_source_record: DeskSourceRecord,
    validate_source_id: ValidateSourceId,
    llm_plan_fn: LlmPlan | None,
    discover_source_channels_fn: DiscoverSourceChannels | None = None,
    profile_context_fn: ProfileContext | None = None,
) -> dict:
    _reject_unexpected_source_assistant_fields(body)
    instruction = str(body.get("instruction") or "").strip()
    if len(instruction) > 4000:
        raise ValueError("Source instruction is too long.")
    if not instruction:
        raise ValueError("Describe what to add, pause, or remove.")
    topic_input = str(body.get("topic") or "").strip()
    topic = clean_source_topic(topic_input or "sources")
    dry_run = body.get("dry_run") is not False
    confirm_external_ai = body.get("confirm_external_ai", False)
    if not isinstance(confirm_external_ai, bool):
        raise ValueError("AI source planning confirmation must be true or false.")
    resolved_plan = body.get("resolved_plan")
    if resolved_plan is not None and not isinstance(resolved_plan, dict):
        raise ValueError("Resolved source plan must be an object.")
    if not dry_run and resolved_plan is not None:
        return apply_source_assistant_resolved_plan(
            resolved_plan,
            topic,
            registry_path=registry_path,
            clean_source_topic=clean_source_topic,
            source_operation_payload=source_operation_payload,
            desk_source_record=desk_source_record,
            validate_source_id=validate_source_id,
        )

    payload = source_registry.load_registry(registry_path, missing_ok=True)
    existing = {str(source.get("source_id")): source for source in payload.get("sources", []) if isinstance(source, dict)}

    if _source_discovery_requested(body, instruction):
        if not confirm_external_ai:
            raise ValueError("Confirm AI source discovery before sending Telegram channel names to the configured model.")
        if discover_source_channels_fn is None or profile_context_fn is None:
            raise ValueError("Telegram source discovery is not available.")
        profile_context = profile_context_fn(str(body.get("profile_id") or ""))
        profile_text = str(profile_context.get("profile_text") or "")
        topic = clean_source_topic(topic_input or profile_context.get("topic") or profile_context.get("profile_id") or "sources")
        folder_name = str(body.get("folder_name") or "").strip()
        folder_id = _clean_folder_id(body.get("folder_id"))
        candidates = _sanitize_discovered_candidates(discover_source_channels_fn(folder_name=folder_name, folder_id=folder_id))
        planner = llm_plan_fn or (
            lambda plan_instruction, plan_topic, plan_existing, **kwargs: _source_assistant_llm_plan(
                plan_instruction,
                plan_topic,
                plan_existing,
                validate_source_id=validate_source_id,
                **kwargs,
            )
        )
        llm_plan = planner(
            instruction,
            topic,
            existing,
            profile_text=profile_text,
            candidates=candidates,
        )
        clean_plan = _clean_resolved_source_plan(llm_plan, validate_source_id=validate_source_id)
        preview_sources: list[dict] = []
        added_count = updated_count = unchanged_count = removed_count = enabled_count = disabled_count = 0
        if clean_plan["add"]:
            result = source_registry.import_channels(
                clean_plan["add"],
                registry_path,
                dry_run=dry_run,
                topics=[topic],
                input_path=f"Telegram folder: {folder_name}" if folder_name else "Telegram channel discovery",
            )
            added_count += int(result.get("added_count") or 0)
            updated_count += int(result.get("updated_count") or 0)
            unchanged_count += int(result.get("unchanged_count") or 0)
            for source in (result.get("sources") or []) + (result.get("updated_sources") or []) + (result.get("unchanged_sources") or []):
                if isinstance(source, dict):
                    preview_sources.append(desk_source_record(source))
        operation_count = added_count + updated_count + unchanged_count
        return source_operation_payload(
            action="assistant",
            topic=topic,
            dry_run=dry_run,
            added_count=added_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            removed_count=removed_count,
            enabled_count=enabled_count,
            disabled_count=disabled_count,
            preview_sources=preview_sources[:12],
            resolved_plan=clean_plan,
            title="AI source plan ready" if dry_run else "AI source plan applied",
            detail=(
                "AI selected Telegram channels for this profile. Review the plan, then apply it."
                if operation_count
                else "AI did not select any Telegram channels for this profile."
            )
            if dry_run
            else "Signal Desk saved the AI-selected Telegram sources.",
            llm_used=True,
        )

    plan = _source_assistant_plan(instruction)
    preview_sources: list[dict] = []
    added_count = updated_count = unchanged_count = removed_count = enabled_count = disabled_count = 0
    llm_used = False
    resolved_plan = {"add": list(plan["add"]), "remove": [], "disable": [], "enable": []}

    if plan["add"]:
        result = source_registry.import_channels(
            plan["add"],
            registry_path,
            dry_run=dry_run,
            topics=[topic],
            input_path="source assistant",
        )
        added_count += int(result.get("added_count") or 0)
        updated_count += int(result.get("updated_count") or 0)
        unchanged_count += int(result.get("unchanged_count") or 0)
        for source in (result.get("sources") or []) + (result.get("updated_sources") or []) + (result.get("unchanged_sources") or []):
            if isinstance(source, dict):
                preview_sources.append(desk_source_record(source))

    llm_plan = {"add": [], "remove": [], "disable": [], "enable": []}
    if confirm_external_ai and _source_assistant_should_use_llm_plan(instruction, plan):
        # This branch sends the local source inventory to a configured model.
        # Keep it behind an explicit confirmation and an injected planner so
        # dashboard facade monkeypatches remain the single testable privacy gate.
        planner = llm_plan_fn or (
            lambda plan_instruction, plan_topic, plan_existing, **kwargs: _source_assistant_llm_plan(
                plan_instruction,
                plan_topic,
                plan_existing,
                validate_source_id=validate_source_id,
                **kwargs,
            )
        )
        llm_plan = planner(instruction, topic, existing)
        llm_used = True

    def source_ids(values: list[str]) -> list[str]:
        return [_source_id_from_channel(value) for value in values]

    disable_ids = _dedupe_source_ids(source_ids(plan["disable"]) + llm_plan["disable"], validate_source_id=validate_source_id)
    resolved_plan["disable"] = list(disable_ids)
    for source_id in disable_ids:
        source = existing.get(source_id)
        if not source:
            continue
        disabled_count += 1
        preview_sources.append(desk_source_record({**source, "enabled": False}))
        if not dry_run:
            source_registry.update_source_enabled(registry_path, source_id=source_id, enabled=False)
    enable_ids = _dedupe_source_ids(source_ids(plan["enable"]) + llm_plan["enable"], validate_source_id=validate_source_id)
    resolved_plan["enable"] = list(enable_ids)
    for source_id in enable_ids:
        source = existing.get(source_id)
        if not source:
            continue
        enabled_count += 1
        preview_sources.append(desk_source_record({**source, "enabled": True}))
        if not dry_run:
            source_registry.update_source_enabled(registry_path, source_id=source_id, enabled=True)
    remove_ids = [
        source_id
        for source_id in _dedupe_source_ids(source_ids(plan["remove"]) + llm_plan["remove"], validate_source_id=validate_source_id)
        if source_id in existing
    ]
    resolved_plan["remove"] = list(remove_ids)
    removed_count += len(remove_ids)
    for source_id in remove_ids:
        preview_sources.append(desk_source_record(existing[source_id]))
    if remove_ids and not dry_run:
        source_registry.remove_sources(registry_path, source_ids=remove_ids)

    operation_count = added_count + updated_count + unchanged_count + removed_count + enabled_count + disabled_count
    if operation_count == 0:
        ai_hint = (
            " AI keys are configured, but Signal Desk still needs an explicit discovery request before sending channel names to the model."
            if report.llm_key_available()
            else ""
        )
        return source_operation_payload(
            action="assistant",
            topic=topic,
            dry_run=True,
            title="No source changes found",
            detail=f"Choose a profile, then discover all Telegram channels or a named folder for AI source planning.{ai_hint}",
            llm_used=llm_used,
            resolved_plan=resolved_plan,
        )
    return source_operation_payload(
        action="assistant",
        topic=topic,
        dry_run=dry_run,
        added_count=added_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        removed_count=removed_count,
        enabled_count=enabled_count,
        disabled_count=disabled_count,
        preview_sources=preview_sources[:12],
        resolved_plan=resolved_plan,
        title="Source plan ready" if dry_run else "Source plan applied",
        detail="Review the plan, then apply it." if dry_run else "Signal Desk updated the local source registry.",
        llm_used=llm_used,
    )


def apply_source_assistant_resolved_plan(
    plan: dict,
    topic: str,
    *,
    registry_path: Path,
    clean_source_topic: CleanSourceTopic,
    source_operation_payload: SourceOperationPayload,
    desk_source_record: DeskSourceRecord,
    validate_source_id: ValidateSourceId,
) -> dict:
    clean_plan = _clean_resolved_source_plan(plan, validate_source_id=validate_source_id)
    clean_topic = clean_source_topic(topic)
    preview_sources: list[dict] = []
    added_count = updated_count = unchanged_count = removed_count = enabled_count = disabled_count = 0

    if clean_plan["add"]:
        result = source_registry.import_channels(
            clean_plan["add"],
            registry_path,
            dry_run=False,
            topics=[clean_topic],
            input_path="source assistant confirmation",
        )
        added_count += int(result.get("added_count") or 0)
        updated_count += int(result.get("updated_count") or 0)
        unchanged_count += int(result.get("unchanged_count") or 0)
        for source in (result.get("sources") or []) + (result.get("updated_sources") or []) + (result.get("unchanged_sources") or []):
            if isinstance(source, dict):
                preview_sources.append(desk_source_record(source))

    payload = source_registry.load_registry(registry_path, missing_ok=True)
    existing = {str(source.get("source_id")): source for source in payload.get("sources", []) if isinstance(source, dict)}

    for source_id in clean_plan["disable"]:
        source = existing.get(source_id)
        if not source:
            continue
        disabled_count += 1
        updated = source_registry.update_source_enabled(registry_path, source_id=source_id, enabled=False)
        preview_sources.append(desk_source_record(updated))

    for source_id in clean_plan["enable"]:
        source = existing.get(source_id)
        if not source:
            continue
        enabled_count += 1
        updated = source_registry.update_source_enabled(registry_path, source_id=source_id, enabled=True)
        preview_sources.append(desk_source_record(updated))

    removable_ids = [source_id for source_id in clean_plan["remove"] if source_id in existing]
    removed_count += len(removable_ids)
    for source_id in removable_ids:
        preview_sources.append(desk_source_record(existing[source_id]))
    if removable_ids:
        source_registry.remove_sources(registry_path, source_ids=removable_ids)

    return source_operation_payload(
        action="assistant",
        topic=clean_topic,
        dry_run=False,
        added_count=added_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        removed_count=removed_count,
        enabled_count=enabled_count,
        disabled_count=disabled_count,
        preview_sources=preview_sources[:12],
        resolved_plan=clean_plan,
        title="Source plan applied",
        detail="Signal Desk updated the local source registry from the confirmed plan.",
    )
