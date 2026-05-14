"""Source registry, source access, and source assistant helpers for Signal Desk."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import (
    desk_scheduler,
    desk_source_access,
    desk_source_assistant,
    desk_source_discovery,
    desk_source_registry,
    monitor_config,
)


def _positive_int_env(name: str, fallback: int) -> int:
    try:
        parsed = int(os.environ.get(name, ""))
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TELEGRAM_SESSION_PATH = Path(
    os.environ.get("TG_SCANNER_CONFIG_DIR")
    or os.environ.get("TGCLI_CONFIG_DIR")
    or os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".config", "tgcli")
) / "session"
DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION = desk_source_access.DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION
DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES = _positive_int_env(
    "TGCS_SOURCE_ACCESS_PROBE_MAX_SOURCES",
    desk_source_access.DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES,
)
DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS = desk_source_access.DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS
DESK_SOURCE_IMPORT_ALLOWED_FIELDS = desk_source_registry.DESK_SOURCE_IMPORT_ALLOWED_FIELDS
DESK_SOURCE_STARTER_ALLOWED_FIELDS = desk_source_registry.DESK_SOURCE_STARTER_ALLOWED_FIELDS
DESK_SOURCE_ASSISTANT_ALLOWED_FIELDS = desk_source_assistant.DESK_SOURCE_ASSISTANT_ALLOWED_FIELDS
DESK_SOURCE_UPDATE_ALLOWED_FIELDS = desk_source_registry.DESK_SOURCE_UPDATE_ALLOWED_FIELDS
DESK_SOURCE_TOPIC_ALLOWED_FIELDS = desk_source_registry.DESK_SOURCE_TOPIC_ALLOWED_FIELDS
DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH = desk_source_registry.DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH
DESK_SOURCE_IMPORT_MAX_CHANNELS = desk_source_registry.DESK_SOURCE_IMPORT_MAX_CHANNELS
DashboardDeskActionError = desk_scheduler.DashboardDeskActionError
SourceAccessProbeError = desk_source_access.SourceAccessProbeError


def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("scripts.dashboard_server")
    return getattr(facade, name, default) if facade is not None else default


def _project_root() -> Path:
    return Path(_facade_attr("PROJECT_ROOT", PROJECT_ROOT))


def _telegram_session_path() -> Path:
    return Path(_facade_attr("TELEGRAM_SESSION_PATH", TELEGRAM_SESSION_PATH))


def _utc_now() -> str:
    now_fn = _facade_attr("_utc_now", None)
    if callable(now_fn) and now_fn is not _utc_now:
        return str(now_fn())
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dashboard_relative_path(path: Path) -> str:
    helper = _facade_attr("dashboard_relative_path", None)
    if callable(helper):
        return str(helper(path))
    try:
        return str(path.resolve().relative_to(_project_root().resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _desk_action_result(*args: Any, **kwargs: Any) -> dict:
    helper = _facade_attr("_desk_action_result", None)
    if callable(helper) and helper is not _desk_action_result:
        return helper(*args, **kwargs)
    raise DashboardDeskActionError("Desk action result projection is unavailable.")


def _load_telegram_credentials(*args: Any, **kwargs: Any) -> tuple[int, str]:
    helper = _facade_attr("_load_telegram_credentials", None)
    if not callable(helper):
        raise ValueError("Telegram app credentials are missing.")
    return helper(*args, **kwargs)


def _sync_source_registry_context() -> None:
    # Source registry endpoints are still exposed through dashboard_server.
    # Keep constants and root/path helpers facade-aware so tests and local Desk
    # integrations can keep patching the public surface after this split.
    desk_source_registry.PROJECT_ROOT = _project_root()
    desk_source_registry.DESK_SOURCE_IMPORT_ALLOWED_FIELDS = _facade_attr(
        "DESK_SOURCE_IMPORT_ALLOWED_FIELDS",
        DESK_SOURCE_IMPORT_ALLOWED_FIELDS,
    )
    desk_source_registry.DESK_SOURCE_STARTER_ALLOWED_FIELDS = _facade_attr(
        "DESK_SOURCE_STARTER_ALLOWED_FIELDS",
        DESK_SOURCE_STARTER_ALLOWED_FIELDS,
    )
    desk_source_registry.DESK_SOURCE_UPDATE_ALLOWED_FIELDS = _facade_attr(
        "DESK_SOURCE_UPDATE_ALLOWED_FIELDS",
        DESK_SOURCE_UPDATE_ALLOWED_FIELDS,
    )
    desk_source_registry.DESK_SOURCE_TOPIC_ALLOWED_FIELDS = _facade_attr(
        "DESK_SOURCE_TOPIC_ALLOWED_FIELDS",
        DESK_SOURCE_TOPIC_ALLOWED_FIELDS,
    )
    desk_source_registry.DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH = int(
        _facade_attr("DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH", DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH)
    )
    desk_source_registry.DESK_SOURCE_IMPORT_MAX_CHANNELS = int(
        _facade_attr("DESK_SOURCE_IMPORT_MAX_CHANNELS", DESK_SOURCE_IMPORT_MAX_CHANNELS)
    )
    desk_source_registry._utc_now = _utc_now
    desk_source_registry._dashboard_relative_path = _dashboard_relative_path


def _reject_unexpected_source_fields(body: dict) -> None:
    _sync_source_registry_context()
    return desk_source_registry._reject_unexpected_source_fields(body)


def _reject_unexpected_source_starter_fields(body: dict) -> None:
    _sync_source_registry_context()
    return desk_source_registry._reject_unexpected_source_starter_fields(body)


def _reject_unexpected_source_assistant_fields(body: dict) -> None:
    desk_source_assistant._reject_unexpected_source_assistant_fields(body)


def _clean_source_topic(value: object) -> str:
    _sync_source_registry_context()
    return desk_source_registry._clean_source_topic(value)


def _source_import_payload(result: dict, *, topic: str, written: bool) -> dict:
    _sync_source_registry_context()
    return desk_source_registry._source_import_payload(result, topic=topic, written=written)


def _source_operation_payload(
    *,
    action: str,
    topic: str,
    dry_run: bool,
    added_count: int = 0,
    updated_count: int = 0,
    unchanged_count: int = 0,
    removed_count: int = 0,
    enabled_count: int = 0,
    disabled_count: int = 0,
    preview_sources: list[dict] | None = None,
    resolved_plan: dict[str, list[str]] | None = None,
    title: str,
    detail: str,
    llm_used: bool = False,
) -> dict:
    return {
        "schema_version": "desk_source_import_result_v1",
        "dry_run": dry_run,
        "written": not dry_run,
        "action": action,
        "topic": topic,
        "added_count": added_count,
        "updated_count": updated_count,
        "unchanged_count": unchanged_count,
        "removed_count": removed_count,
        "enabled_count": enabled_count,
        "disabled_count": disabled_count,
        "source_count": desk_sources()["source_count"],
        "registry_path": ".tgcs/sources.json",
        "preview_sources": preview_sources or [],
        "preview_truncated_count": 0,
        "resolved_plan": resolved_plan or {"add": [], "remove": [], "disable": [], "enable": []},
        "llm_used": llm_used,
        "title": title,
        "detail": detail,
        "next_action": "Run source checks, then run a scan from Start.",
        "finished_at": _utc_now(),
    }


def _desk_source_record(source: dict) -> dict:
    _sync_source_registry_context()
    return desk_source_registry._desk_source_record(source)


def desk_sources() -> dict:
    _sync_source_registry_context()
    return desk_source_registry.desk_sources()


def _validate_desk_source_id(source_id: str) -> str:
    _sync_source_registry_context()
    return desk_source_registry._validate_desk_source_id(source_id)


def set_desk_source_enabled(source_id: str, body: dict) -> dict:
    _sync_source_registry_context()
    return desk_source_registry.set_desk_source_enabled(source_id, body)


def _clean_source_topics(value: object) -> list[str]:
    _sync_source_registry_context()
    return desk_source_registry._clean_source_topics(value)


def set_desk_source_topics(source_id: str, body: dict) -> dict:
    _sync_source_registry_context()
    return desk_source_registry.set_desk_source_topics(source_id, body)


def remove_desk_source(source_id: str, body: dict) -> dict:
    _sync_source_registry_context()
    return desk_source_registry.remove_desk_source(source_id, body)


def source_access_health_path() -> Path:
    return desk_source_access.source_access_health_path(_project_root())


def _source_access_health_loaded() -> dict | None:
    return desk_source_access._source_access_health_loaded(source_access_health_path())


def _write_source_access_health(payload: dict) -> None:
    desk_source_access._write_source_access_health(payload, source_access_health_path())


def _source_access_checked_at(payload: dict) -> datetime | None:
    return desk_source_access._source_access_checked_at(payload)


def _source_access_health_is_fresh(payload: dict, *, max_age_hours: int = DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS) -> bool:
    return desk_source_access._source_access_health_is_fresh(payload, max_age_hours=max_age_hours)


def _source_access_reason_label(reason: str) -> str:
    return desk_source_access._source_access_reason_label(reason)


def _source_access_health_detail(payload: dict) -> str:
    return desk_source_access._source_access_health_detail(payload)


def _source_access_action_summary(payload: dict) -> dict:
    return desk_source_access._source_access_action_summary(payload)


def _source_access_record_base(source: dict) -> dict:
    return desk_source_access._source_access_record_base(source)


def _source_access_error_reason(exc: Exception) -> str:
    return desk_source_access._source_access_error_reason(exc)


def _source_access_failure_record(source: dict, exc: Exception) -> dict:
    return desk_source_access._source_access_failure_record(source, exc)


async def _resolve_probe_entity(client, channel: str):
    return await desk_source_access._resolve_probe_entity(client, channel)


def _message_datetime(value: object) -> datetime | None:
    return desk_source_access._message_datetime(value)


async def _probe_one_source_access(client, source: dict, *, now: datetime) -> dict:
    return await desk_source_access._probe_one_source_access(client, source, now=now)


def _source_access_summary(records: list[dict], *, total_source_count: int, truncated_count: int, checked_at: str) -> dict:
    return desk_source_access._source_access_summary(
        records,
        total_source_count=total_source_count,
        truncated_count=truncated_count,
        checked_at=checked_at,
    )


async def _probe_source_access_async(progress_callback=None) -> dict:
    summary = await desk_source_access._probe_source_access_async(
        registry_path=_project_root() / ".tgcs" / "sources.json",
        telegram_session_path=_telegram_session_path(),
        load_telegram_credentials=_load_telegram_credentials,
        max_sources=DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES,
        progress_callback=progress_callback,
    )
    _write_source_access_health(summary)
    return summary


def probe_source_access(progress_callback=None) -> dict:
    return desk_source_access.probe_source_access(
        registry_path=_project_root() / ".tgcs" / "sources.json",
        health_path=source_access_health_path(),
        telegram_session_path=_telegram_session_path(),
        load_telegram_credentials=_load_telegram_credentials,
        max_sources=DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES,
        progress_callback=progress_callback,
    )


def _require_confirm_only(body: dict | None, *, action_label: str) -> None:
    desk_source_access._require_confirm_only(body, action_label=action_label)


def _source_access_target_ids(payload: dict, *, keep_only_accessible: bool) -> list[str]:
    return desk_source_access._source_access_target_ids(
        payload,
        keep_only_accessible=keep_only_accessible,
        validate_source_id=_validate_desk_source_id,
    )


def _disable_sources_from_access_health(source_ids: list[str]) -> int:
    return desk_source_access._disable_sources_from_access_health(
        source_ids,
        registry_path=_project_root() / ".tgcs" / "sources.json",
    )


def apply_source_access_repair(action_id: str, *, body: dict | None = None) -> dict:
    return desk_source_access.apply_source_access_repair(
        action_id,
        body=body,
        health_path=source_access_health_path(),
        registry_path=_project_root() / ".tgcs" / "sources.json",
        desk_action_result=_desk_action_result,
        validate_source_id=_validate_desk_source_id,
    )


def _desk_sources_from_body(body: dict) -> tuple[list[str], str]:
    _sync_source_registry_context()
    return desk_source_registry._desk_sources_from_body(body)


def import_starter_sources(body: dict) -> dict:
    _sync_source_registry_context()
    return desk_source_registry.import_starter_sources(body)


def preview_desk_source_import(body: dict) -> dict:
    _sync_source_registry_context()
    return desk_source_registry.preview_desk_source_import(body)


def import_desk_sources(body: dict) -> dict:
    _sync_source_registry_context()
    return desk_source_registry.import_desk_sources(body)


def _extract_source_channels_from_text(text: str) -> list[str]:
    return desk_source_assistant._extract_source_channels_from_text(text)


def _source_id_from_channel(channel: str) -> str:
    return desk_source_assistant._source_id_from_channel(channel)


def _source_assistant_action(text: str) -> str:
    return desk_source_assistant._source_assistant_action(text)


def _source_assistant_plan(instruction: str) -> dict[str, list[str]]:
    return desk_source_assistant._source_assistant_plan(instruction)


def _source_assistant_has_plan(plan: dict[str, list[str]]) -> bool:
    return desk_source_assistant._source_assistant_has_plan(plan)


def _source_assistant_requested_existing_actions(instruction: str) -> set[str]:
    return desk_source_assistant._source_assistant_requested_existing_actions(instruction)


def _source_assistant_should_use_llm_plan(instruction: str, plan: dict[str, list[str]]) -> bool:
    return desk_source_assistant._source_assistant_should_use_llm_plan(instruction, plan)


def _dedupe_source_ids(source_ids: list[str]) -> list[str]:
    return desk_source_assistant._dedupe_source_ids(source_ids, validate_source_id=_validate_desk_source_id)


def _dedupe_source_channels(channels: list[str]) -> list[str]:
    return desk_source_assistant._dedupe_source_channels(channels)


def _clean_resolved_source_plan(plan: dict) -> dict[str, list[str]]:
    return desk_source_assistant._clean_resolved_source_plan(plan, validate_source_id=_validate_desk_source_id)


def _source_assistant_llm_plan(
    instruction: str,
    topic: str,
    existing: dict[str, dict],
    *,
    profile_text: str = "",
    candidates: list[dict] | None = None,
) -> dict[str, list[str]]:
    return desk_source_assistant._source_assistant_llm_plan(
        instruction,
        topic,
        existing,
        validate_source_id=_validate_desk_source_id,
        profile_text=profile_text,
        candidates=candidates,
    )


def _discover_source_channels(*, folder_name: str = "", folder_id: int | None = None) -> list[dict]:
    return desk_source_discovery.discover_source_channels(folder_name=folder_name, folder_id=folder_id)


def _source_assistant_profile_context(profile_id: str = "") -> dict[str, str]:
    root = _project_root()
    config = monitor_config.load_config(root / ".tgcs" / "profiles.toml", root=root)
    profiles = [profile for profile in config.profiles.values() if profile.get("enabled", True)]
    if not profiles:
        raise ValueError("Create an AI-generated profile before discovering sources.")
    selected = None
    requested = str(profile_id or "").strip()
    if requested:
        selected = config.profiles.get(requested)
        if selected is None:
            raise ValueError(f"Profile id not found: {requested}")
    if selected is None:
        selected = next(
            (profile for profile in profiles if str(profile.get("path") or "").replace("\\", "/").startswith("profiles/desk/")),
            profiles[0],
        )
    profile_path = monitor_config.profile_path(selected, root=root)
    if not profile_path.exists():
        raise ValueError(f"Profile file not found: {selected.get('path') or profile_path}")
    source_topics = selected.get("source_topics") if isinstance(selected.get("source_topics"), list) else []
    topic = str(source_topics[0]) if source_topics else str(selected.get("id") or "sources")
    return {
        "profile_id": str(selected.get("id") or requested),
        "profile_text": profile_path.read_text(encoding="utf-8"),
        "topic": _clean_source_topic(topic),
    }


def run_source_assistant(body: dict) -> dict:
    return desk_source_assistant.run_source_assistant(
        body,
        registry_path=_project_root() / ".tgcs" / "sources.json",
        clean_source_topic=_clean_source_topic,
        source_operation_payload=_source_operation_payload,
        desk_source_record=_desk_source_record,
        validate_source_id=_validate_desk_source_id,
        llm_plan_fn=_facade_attr("_source_assistant_llm_plan", _source_assistant_llm_plan),
        discover_source_channels_fn=_facade_attr("_discover_source_channels", _discover_source_channels),
        profile_context_fn=_facade_attr("_source_assistant_profile_context", _source_assistant_profile_context),
    )


def apply_source_assistant_resolved_plan(plan: dict, topic: str) -> dict:
    return desk_source_assistant.apply_source_assistant_resolved_plan(
        plan,
        topic,
        registry_path=_project_root() / ".tgcs" / "sources.json",
        clean_source_topic=_clean_source_topic,
        source_operation_payload=_source_operation_payload,
        desk_source_record=_desk_source_record,
        validate_source_id=_validate_desk_source_id,
    )
