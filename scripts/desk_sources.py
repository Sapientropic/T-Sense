"""Source registry, source access, and source assistant helpers for Signal Desk."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts import desk_scheduler, desk_source_assistant, source_registry


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
DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION = "desk_source_access_health_v1"
DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES = _positive_int_env("TGCS_SOURCE_ACCESS_PROBE_MAX_SOURCES", 80)
DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS = 24
DESK_SOURCE_IMPORT_ALLOWED_FIELDS = {"sources", "topic"}
DESK_SOURCE_STARTER_ALLOWED_FIELDS = {"topic"}
DESK_SOURCE_ASSISTANT_ALLOWED_FIELDS = desk_source_assistant.DESK_SOURCE_ASSISTANT_ALLOWED_FIELDS
DESK_SOURCE_UPDATE_ALLOWED_FIELDS = {"enabled"}
DESK_SOURCE_TOPIC_ALLOWED_FIELDS = {"topics"}
DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH = 20000
DESK_SOURCE_IMPORT_MAX_CHANNELS = 500
DashboardDeskActionError = desk_scheduler.DashboardDeskActionError


class SourceAccessProbeError(Exception):
    """Raised when a source access probe cannot start safely."""

    def __init__(self, message: str, *, next_action: str, status: str = "blocked") -> None:
        super().__init__(message)
        self.next_action = next_action
        self.status = status


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

def _reject_unexpected_source_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_IMPORT_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source import field: {', '.join(unexpected)}")


def _reject_unexpected_source_starter_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_STARTER_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported starter source field: {', '.join(unexpected)}")


def _reject_unexpected_source_assistant_fields(body: dict) -> None:
    desk_source_assistant._reject_unexpected_source_assistant_fields(body)


def _clean_source_topic(value: object) -> str:
    topic = str(value or "jobs").strip().casefold()
    if not topic:
        topic = "jobs"
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", topic):
        raise ValueError("Source topic must use letters, numbers, hyphen, or underscore.")
    return topic


def _source_import_payload(result: dict, *, topic: str, written: bool) -> dict:
    def source_label(source: dict) -> str:
        return str(source.get("username") or source.get("channel_id") or source.get("label") or "").strip()

    raw_preview_sources = [
        source
        for collection in (result.get("sources"), result.get("updated_sources"), result.get("unchanged_sources"))
        for source in (collection or [])
        if isinstance(source, dict)
    ]
    preview_sources = [
        {"label": source_label(source), "source_id": str(source.get("source_id") or "")}
        for source in raw_preview_sources[:12]
    ]
    preview_truncated_count = max(0, len(raw_preview_sources) - len(preview_sources))
    return {
        "schema_version": "desk_source_import_result_v1",
        "dry_run": bool(result.get("dry_run")),
        "written": written,
        "topic": topic,
        "added_count": int(result.get("added_count") or 0),
        "updated_count": int(result.get("updated_count") or 0),
        "unchanged_count": int(result.get("unchanged_count") or 0),
        "source_count": int(result.get("source_count") or 0),
        "registry_path": _dashboard_relative_path(Path(str(result.get("registry_path") or ".tgcs/sources.json"))),
        "preview_sources": preview_sources,
        "preview_truncated_count": preview_truncated_count,
        "title": "Sources ready" if written else "Source preview ready",
        "detail": (
            "Sources were saved to the local registry."
            if written
            else "Review the preview, then import when it looks right."
        ),
        "next_action": "Run source checks, then run a scan from Start.",
        "finished_at": _utc_now(),
    }


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
    channel = source_registry.channel_value(source)
    label = str(source.get("label") or channel or source.get("source_id") or "").strip()
    return {
        "schema_version": "desk_source_v1",
        "source_id": str(source.get("source_id") or ""),
        "label": label,
        "channel": channel,
        "enabled": bool(source.get("enabled", True)),
        "topics": source_registry.normalize_topics(source.get("topics") or []),
        "priority": str(source.get("priority") or "normal"),
        "scan_window_hours": int(source.get("scan_window_hours") or source_registry.DEFAULT_SCAN_WINDOW_HOURS),
    }


def desk_sources() -> dict:
    registry_path = _project_root() / ".tgcs" / "sources.json"
    result = source_registry.registry_sources(registry_path)
    return {
        "schema_version": "desk_sources_v1",
        "source_count": int(result.get("source_count") or 0),
        "enabled_count": int(result.get("enabled_count") or 0),
        "topics": [str(topic) for topic in result.get("topics") or []],
        "registry_path": _dashboard_relative_path(Path(str(result.get("registry_path") or registry_path))),
        "sources": [_desk_source_record(source) for source in (result.get("sources") or []) if isinstance(source, dict)],
    }


def _validate_desk_source_id(source_id: str) -> str:
    clean = str(source_id or "").strip()
    if not re.fullmatch(r"telegram:(?:[A-Za-z0-9_]{5,64}|-?[0-9]{5,20})", clean):
        raise ValueError("Source id is not supported by Signal Desk.")
    return clean


def set_desk_source_enabled(source_id: str, body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_UPDATE_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source setting field: {', '.join(unexpected)}")
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("Source enabled value must be true or false.")
    registry_path = _project_root() / ".tgcs" / "sources.json"
    source_registry.update_source_enabled(
        registry_path,
        source_id=_validate_desk_source_id(source_id),
        enabled=enabled,
    )
    return desk_sources()


def _clean_source_topics(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Source topics must be a list.")
    if len(value) > 8:
        raise ValueError("Use fewer topic tags.")
    topics: list[str] = []
    seen: set[str] = set()
    for raw_topic in value:
        if not isinstance(raw_topic, str):
            raise ValueError("Source topic tags must be text.")
        topic = raw_topic.strip().casefold()
        if not topic:
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", topic):
            raise ValueError("Source topic must use letters, numbers, hyphen, or underscore.")
        if topic in seen:
            continue
        seen.add(topic)
        topics.append(topic)
    if not topics:
        raise ValueError("Add at least one source topic.")
    return topics


def set_desk_source_topics(source_id: str, body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_TOPIC_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source topic field: {', '.join(unexpected)}")
    topics = _clean_source_topics(body.get("topics"))
    registry_path = _project_root() / ".tgcs" / "sources.json"
    source_registry.update_source_topics(
        registry_path,
        source_id=_validate_desk_source_id(source_id),
        topics=topics,
    )
    return desk_sources()


def remove_desk_source(source_id: str, body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in {"confirm"})
    if unexpected:
        raise ValueError(f"Unsupported source remove field: {', '.join(unexpected)}")
    if body.get("confirm") is not True:
        raise ValueError("Source removal requires confirmation.")
    registry_path = _project_root() / ".tgcs" / "sources.json"
    source_registry.remove_sources(registry_path, source_ids=[_validate_desk_source_id(source_id)])
    return desk_sources()


def source_access_health_path() -> Path:
    return _project_root() / ".tgcs" / "source-access-health.json"


def _source_access_health_loaded() -> dict | None:
    path = source_access_health_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION:
        return None
    return payload


def _write_source_access_health(payload: dict) -> None:
    path = source_access_health_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _source_access_checked_at(payload: dict) -> datetime | None:
    text = str(payload.get("checked_at") or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _source_access_health_is_fresh(payload: dict, *, max_age_hours: int = DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS) -> bool:
    checked_at = _source_access_checked_at(payload)
    if checked_at is None:
        return False
    return checked_at >= datetime.now(UTC) - timedelta(hours=max_age_hours)


def _source_access_reason_label(reason: str) -> str:
    return {
        "cannot_resolve_entity": "cannot resolve",
        "permission_or_private": "private or permission",
        "rate_limited": "rate limited",
        "empty_recent_window": "quiet",
        "source_missing_identifier": "missing identifier",
        "timeout": "timeout",
        "access_error": "access error",
    }.get(reason, reason.replace("_", " "))


def _source_access_health_detail(payload: dict) -> str:
    accessible = int(payload.get("accessible_count") or 0)
    quiet = int(payload.get("quiet_count") or 0)
    inaccessible = int(payload.get("inaccessible_count") or 0)
    checked = int(payload.get("checked_count") or 0)
    truncated = int(payload.get("truncated_count") or 0)
    window_min = int(payload.get("probe_window_hours_min") or payload.get("probe_window_hours") or 0)
    window_max = int(payload.get("probe_window_hours_max") or payload.get("probe_window_hours") or 0)
    window_text = ""
    if window_min and window_max and window_min == window_max:
        window_text = f" in the last {window_max}h"
    elif window_min and window_max:
        window_text = f" in each source window ({window_min}-{window_max}h)"
    reason_counts = payload.get("reason_counts") if isinstance(payload.get("reason_counts"), dict) else {}
    issue_parts = [
        f"{_source_access_reason_label(str(reason))} {int(count)}"
        for reason, count in sorted(reason_counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[:3]
        if int(count or 0) > 0
    ]
    detail = (
        f"Access check: {accessible} recently active, {quiet} quiet{window_text}, "
        f"{inaccessible} inaccessible across {checked} checked sources."
    )
    if issue_parts:
        detail += f" Notes: {', '.join(issue_parts)}."
    if truncated:
        detail += f" {truncated} additional enabled sources were not checked by the bounded probe."
    return detail


def _source_access_action_summary(payload: dict) -> dict:
    reason_counts = payload.get("reason_counts") if isinstance(payload.get("reason_counts"), dict) else {}
    window_min = int(payload.get("probe_window_hours_min") or payload.get("probe_window_hours") or 0)
    window_max = int(payload.get("probe_window_hours_max") or payload.get("probe_window_hours") or 0)
    summary = {
        "schema_version": DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION,
        "checked_at": str(payload.get("checked_at") or ""),
        "source_count": int(payload.get("source_count") or 0),
        "checked_count": int(payload.get("checked_count") or 0),
        "accessible_count": int(payload.get("accessible_count") or 0),
        "quiet_count": int(payload.get("quiet_count") or 0),
        "inaccessible_count": int(payload.get("inaccessible_count") or 0),
        "truncated_count": int(payload.get("truncated_count") or 0),
        "reason_counts": {
            str(reason): int(count or 0)
            for reason, count in reason_counts.items()
            if int(count or 0) > 0
        },
    }
    if window_min and window_max:
        summary["probe_window_hours_min"] = window_min
        summary["probe_window_hours_max"] = window_max
        if window_min == window_max:
            summary["probe_window_hours"] = window_max
    return summary


def _source_access_record_base(source: dict) -> dict:
    channel = source_registry.channel_value(source)
    label = str(source.get("label") or channel or source.get("source_id") or "Unknown source").strip()
    return {
        "source_id": str(source.get("source_id") or ""),
        "label": label,
        "channel": channel,
        "topics": source_registry.normalize_topics(source.get("topics") or []),
        "scan_window_hours": int(source.get("scan_window_hours") or source_registry.DEFAULT_SCAN_WINDOW_HOURS),
    }


def _source_access_error_reason(exc: Exception) -> str:
    name = exc.__class__.__name__.casefold()
    text = str(exc).casefold()
    if "floodwait" in name or "flood wait" in text or "too many requests" in text:
        return "rate_limited"
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return "timeout"
    if any(marker in text for marker in ("cannot resolve", "could not find the input entity", "no user has")):
        return "cannot_resolve_entity"
    if any(marker in text for marker in ("private", "forbidden", "not a participant", "invite", "permission")):
        return "permission_or_private"
    return "access_error"


def _source_access_failure_record(source: dict, exc: Exception) -> dict:
    reason = _source_access_error_reason(exc)
    return {
        **_source_access_record_base(source),
        "status": "inaccessible",
        "reason": reason,
        "detail": f"Telegram returned {exc.__class__.__name__}.",
        "latest_message_at": "",
    }


async def _resolve_probe_entity(client, channel: str):
    clean = channel.strip()
    if clean.lstrip("-").isdigit():
        entity_id = int(clean)
        try:
            return await client.get_entity(entity_id)
        except Exception as first_error:
            async for dialog in client.iter_dialogs():
                if getattr(dialog.entity, "id", None) == entity_id:
                    return dialog.entity
            raise ValueError(f"Cannot resolve entity: {clean}") from first_error
    try:
        return await client.get_entity(clean)
    except Exception as first_error:
        clean_lower = clean.casefold()
        async for dialog in client.iter_dialogs():
            name = str(getattr(dialog, "name", "") or "").casefold()
            if name == clean_lower:
                return dialog.entity
        raise ValueError(f"Cannot resolve entity: {clean}") from first_error


def _message_datetime(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


async def _probe_one_source_access(client, source: dict, *, now: datetime) -> dict:
    base = _source_access_record_base(source)
    channel = base["channel"]
    if not channel:
        return {
            **base,
            "status": "inaccessible",
            "reason": "source_missing_identifier",
            "detail": "Source has no Telegram handle or numeric chat id.",
            "latest_message_at": "",
        }
    try:
        entity = await _resolve_probe_entity(client, channel)
        messages = await client.get_messages(entity, limit=1)
    except Exception as exc:
        return _source_access_failure_record(source, exc)

    latest = messages[0] if messages else None
    latest_at = _message_datetime(getattr(latest, "date", None)) if latest is not None else None
    window_hours = int(base.get("scan_window_hours") or source_registry.DEFAULT_SCAN_WINDOW_HOURS)
    if latest_at is None:
        return {
            **base,
            "status": "quiet",
            "reason": "empty_recent_window",
            "detail": "Telegram access works, but no recent message timestamp was found.",
            "latest_message_at": "",
        }
    if latest_at < now - timedelta(hours=window_hours):
        return {
            **base,
            "status": "quiet",
            "reason": "empty_recent_window",
            "detail": f"Telegram access works, but no messages were found in the last {window_hours} hours.",
            "latest_message_at": latest_at.isoformat().replace("+00:00", "Z"),
        }
    return {
        **base,
        "status": "accessible",
        "reason": "recent_message_found",
        "detail": "Telegram access works for the current scan window.",
        "latest_message_at": latest_at.isoformat().replace("+00:00", "Z"),
    }


def _source_access_summary(records: list[dict], *, total_source_count: int, truncated_count: int, checked_at: str) -> dict:
    status_counts = Counter(str(record.get("status") or "unknown") for record in records)
    reason_counts = Counter(
        str(record.get("reason") or "unknown")
        for record in records
        if str(record.get("status") or "") in {"inaccessible", "quiet"}
    )
    window_values = [
        int(record.get("scan_window_hours") or 0)
        for record in records
        if int(record.get("scan_window_hours") or 0) > 0
    ]
    summary = {
        "schema_version": DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION,
        "checked_at": checked_at,
        "source_count": total_source_count,
        "checked_count": len(records),
        "truncated_count": truncated_count,
        "accessible_count": int(status_counts.get("accessible", 0)),
        "quiet_count": int(status_counts.get("quiet", 0)),
        "inaccessible_count": int(status_counts.get("inaccessible", 0)),
        "reason_counts": dict(sorted(reason_counts.items())),
        "sources": records,
    }
    if window_values:
        summary["probe_window_hours_min"] = min(window_values)
        summary["probe_window_hours_max"] = max(window_values)
        if min(window_values) == max(window_values):
            summary["probe_window_hours"] = max(window_values)
    return summary


async def _probe_source_access_async(progress_callback=None) -> dict:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    registry_path = _project_root() / ".tgcs" / "sources.json"
    try:
        registry = source_registry.load_registry(registry_path)
        issues = source_registry.validate_registry(registry)
    except (OSError, source_registry.RegistryError) as exc:
        raise SourceAccessProbeError(
            str(exc),
            next_action="Prepare Signal Desk files or repair the source registry, then check source access again.",
        ) from exc
    if issues:
        raise SourceAccessProbeError(
            source_registry.validation_message(issues),
            next_action="Run Check source syntax or repair starter sources before access probing.",
        )
    sources = [
        source
        for source in source_registry.enabled_sources(registry)
        if isinstance(source, dict)
    ]
    if not sources:
        raise SourceAccessProbeError(
            "No enabled sources are saved.",
            next_action="Add or enable at least one source, then check source access again.",
        )

    try:
        api_id, api_hash = _load_telegram_credentials()
    except ValueError as exc:
        raise SourceAccessProbeError(
            "Telegram API credentials are not configured.",
            next_action="Connect Telegram from Start, then check source access again.",
        ) from exc
    session_string = _telegram_session_path().read_text(encoding="utf-8").strip() if _telegram_session_path().exists() else ""
    if not session_string:
        raise SourceAccessProbeError(
            "Telegram login is not complete.",
            next_action="Finish Telegram login from Start, then check source access again.",
        )

    checked_sources = sources[:DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES]
    now = datetime.now(UTC)
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SourceAccessProbeError(
                "Telegram login is not authorized.",
                next_action="Reconnect Telegram from Start, then check source access again.",
            )
        records = []
        for index, source in enumerate(checked_sources, start=1):
            records.append(await _probe_one_source_access(client, source, now=now))
            if progress_callback:
                progress_callback(index, len(checked_sources))
    finally:
        await client.disconnect()

    summary = _source_access_summary(
        records,
        total_source_count=len(sources),
        truncated_count=max(0, len(sources) - len(checked_sources)),
        checked_at=now.isoformat().replace("+00:00", "Z"),
    )
    _write_source_access_health(summary)
    return summary


def probe_source_access(progress_callback=None) -> dict:
    return asyncio.run(_probe_source_access_async(progress_callback=progress_callback))


def _require_confirm_only(body: dict | None, *, action_label: str) -> None:
    body = body or {}
    unexpected = sorted(str(key) for key in body.keys() if key not in {"confirm"})
    if unexpected:
        raise DashboardDeskActionError(f"{action_label} only accepts an explicit confirmation flag.")
    if body.get("confirm") is not True:
        raise DashboardDeskActionError(f"{action_label} requires explicit confirmation.")


def _source_access_target_ids(payload: dict, *, keep_only_accessible: bool) -> list[str]:
    wanted_statuses = {"inaccessible", "quiet"} if keep_only_accessible else {"inaccessible"}
    ids: list[str] = []
    seen: set[str] = set()
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    for record in sources:
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "") not in wanted_statuses:
            continue
        source_id = str(record.get("source_id") or "").strip()
        if not source_id or source_id in seen:
            continue
        try:
            ids.append(_validate_desk_source_id(source_id))
        except ValueError:
            continue
        seen.add(source_id)
    return ids


def _disable_sources_from_access_health(source_ids: list[str]) -> int:
    if not source_ids:
        return 0
    registry_path = _project_root() / ".tgcs" / "sources.json"
    try:
        payload = source_registry.load_registry(registry_path)
    except (OSError, source_registry.RegistryError) as exc:
        raise DashboardDeskActionError(str(exc)) from exc
    issues = source_registry.validate_registry(payload)
    if issues:
        raise DashboardDeskActionError(source_registry.validation_message(issues))
    target_ids = set(source_ids)
    changed = 0
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        if source.get("source_id") in target_ids and source.get("enabled", True):
            source["enabled"] = False
            changed += 1
    if changed:
        source_registry.save_registry(registry_path, payload)
    return changed


def apply_source_access_repair(action_id: str, *, body: dict | None = None) -> dict:
    action_label = "Source access repair"
    _require_confirm_only(body, action_label=action_label)
    health = _source_access_health_loaded()
    if not health:
        return _desk_action_result(
            action_id,
            status="blocked",
            title="Check source access first",
            detail="Signal Desk needs a recent source access check before it can safely disable sources.",
            next_action="Run Check source access, then retry this repair action.",
        )
    if not _source_access_health_is_fresh(health):
        return _desk_action_result(
            action_id,
            status="blocked",
            title="Source access check is stale",
            detail="Run a fresh access check before changing the saved source list.",
            next_action="Run Check source access, then retry this repair action.",
        )
    keep_only_accessible = action_id == "sources_keep_accessible"
    target_ids = _source_access_target_ids(health, keep_only_accessible=keep_only_accessible)
    changed_count = _disable_sources_from_access_health(target_ids)
    if keep_only_accessible:
        title = "Recently active sources kept"
        detail = (
            f"Signal Desk disabled {changed_count} inaccessible or quiet sources from the latest access check. "
            "Quiet sources were readable, but had no recent messages in the probe window."
        )
    else:
        title = "Inaccessible sources paused"
        detail = f"Signal Desk disabled {changed_count} inaccessible sources from the latest access check."
    return _desk_action_result(
        action_id,
        status="success",
        title=title,
        detail=detail,
        next_action="Run a fresh practice scan to verify the narrowed source list.",
    )


def _desk_sources_from_body(body: dict) -> tuple[list[str], str]:
    _reject_unexpected_source_fields(body)
    text = str(body.get("sources") or "")
    if len(text) > DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH:
        raise ValueError("Paste fewer sources at a time.")
    channels = source_registry.load_channel_text(text)
    if not channels:
        raise ValueError("Paste at least one Telegram channel handle or t.me link.")
    if len(channels) > DESK_SOURCE_IMPORT_MAX_CHANNELS:
        raise ValueError("Paste fewer sources at a time.")
    invalid_channels = [
        channel
        for channel in channels
        if not re.fullmatch(r"(?:[A-Za-z0-9_]{5,64}|-?[0-9]{5,20})", channel)
    ]
    if invalid_channels:
        raise ValueError("Source import only accepts Telegram channel handles or numeric chat IDs.")
    topic = _clean_source_topic(body.get("topic"))
    return channels, topic


def import_starter_sources(body: dict) -> dict:
    _reject_unexpected_source_starter_fields(body)
    topic = _clean_source_topic(body.get("topic"))
    starter_path = _project_root() / "channel_lists" / "jobs.txt"
    if not starter_path.exists():
        starter_path = _project_root() / "channel_lists" / "example.txt"
    if not starter_path.exists():
        raise ValueError("Starter source list is missing from this checkout.")
    channels = source_registry.load_channel_list(starter_path)
    registry_path = _project_root() / ".tgcs" / "sources.json"
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=False,
        topics=[topic],
        input_path="packaged starter sources",
    )
    payload = _source_import_payload(result, topic=topic, written=True)
    payload["title"] = "Starter sources installed"
    payload["detail"] = "Signal Desk added the packaged starter source set. Replace or prune it from Settings as you learn what works."
    return payload


def preview_desk_source_import(body: dict) -> dict:
    channels, topic = _desk_sources_from_body(body)
    registry_path = _project_root() / ".tgcs" / "sources.json"
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=True,
        topics=[topic],
        input_path="pasted sources",
    )
    return _source_import_payload(result, topic=topic, written=False)


def import_desk_sources(body: dict) -> dict:
    channels, topic = _desk_sources_from_body(body)
    registry_path = _project_root() / ".tgcs" / "sources.json"
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=False,
        topics=[topic],
        input_path="pasted sources",
    )
    return _source_import_payload(result, topic=topic, written=True)


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


def _source_assistant_llm_plan(instruction: str, topic: str, existing: dict[str, dict]) -> dict[str, list[str]]:
    return desk_source_assistant._source_assistant_llm_plan(
        instruction,
        topic,
        existing,
        validate_source_id=_validate_desk_source_id,
    )


def run_source_assistant(body: dict) -> dict:
    return desk_source_assistant.run_source_assistant(
        body,
        registry_path=_project_root() / ".tgcs" / "sources.json",
        clean_source_topic=_clean_source_topic,
        source_operation_payload=_source_operation_payload,
        desk_source_record=_desk_source_record,
        validate_source_id=_validate_desk_source_id,
        llm_plan_fn=_facade_attr("_source_assistant_llm_plan", _source_assistant_llm_plan),
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
