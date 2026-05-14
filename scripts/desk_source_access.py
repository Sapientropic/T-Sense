"""Source access health, probe, and repair helpers for Signal Desk."""

from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts import desk_scheduler, source_registry

DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION = "desk_source_access_health_v1"
DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES = 80
DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS = 24
DashboardDeskActionError = desk_scheduler.DashboardDeskActionError

LoadTelegramCredentials = Callable[[], tuple[int, str]]
DeskActionResult = Callable[..., dict]
ValidateSourceId = Callable[[str], str]


class SourceAccessProbeError(Exception):
    """Raised when a source access probe cannot start safely."""

    def __init__(self, message: str, *, next_action: str, status: str = "blocked") -> None:
        super().__init__(message)
        self.next_action = next_action
        self.status = status


def source_access_health_path(project_root: Path) -> Path:
    return project_root / ".tgcs" / "source-access-health.json"


def _source_access_health_loaded(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION:
        return None
    return payload


def _write_source_access_health(payload: dict, path: Path) -> None:
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


async def _probe_source_access_async(
    *,
    registry_path: Path,
    telegram_session_path: Path,
    load_telegram_credentials: LoadTelegramCredentials,
    max_sources: int,
    progress_callback=None,
) -> dict:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

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
        api_id, api_hash = load_telegram_credentials()
    except ValueError as exc:
        raise SourceAccessProbeError(
            "Telegram API credentials are not configured.",
            next_action="Connect Telegram from Start, then check source access again.",
        ) from exc
    session_string = telegram_session_path.read_text(encoding="utf-8").strip() if telegram_session_path.exists() else ""
    if not session_string:
        raise SourceAccessProbeError(
            "Telegram login is not complete.",
            next_action="Finish Telegram login from Start, then check source access again.",
        )

    checked_sources = sources[:max_sources]
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

    return _source_access_summary(
        records,
        total_source_count=len(sources),
        truncated_count=max(0, len(sources) - len(checked_sources)),
        checked_at=now.isoformat().replace("+00:00", "Z"),
    )


def probe_source_access(
    *,
    registry_path: Path,
    health_path: Path,
    telegram_session_path: Path,
    load_telegram_credentials: LoadTelegramCredentials,
    max_sources: int,
    progress_callback=None,
) -> dict:
    summary = asyncio.run(
        _probe_source_access_async(
            registry_path=registry_path,
            telegram_session_path=telegram_session_path,
            load_telegram_credentials=load_telegram_credentials,
            max_sources=max_sources,
            progress_callback=progress_callback,
        )
    )
    _write_source_access_health(summary, health_path)
    return summary


def _require_confirm_only(body: dict | None, *, action_label: str) -> None:
    body = body or {}
    unexpected = sorted(str(key) for key in body.keys() if key not in {"confirm"})
    if unexpected:
        raise DashboardDeskActionError(f"{action_label} only accepts an explicit confirmation flag.")
    if body.get("confirm") is not True:
        raise DashboardDeskActionError(f"{action_label} requires explicit confirmation.")


def _source_access_target_ids(payload: dict, *, keep_only_accessible: bool, validate_source_id: ValidateSourceId) -> list[str]:
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
            ids.append(validate_source_id(source_id))
        except ValueError:
            continue
        seen.add(source_id)
    return ids


def _disable_sources_from_access_health(source_ids: list[str], *, registry_path: Path) -> int:
    if not source_ids:
        return 0
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


def apply_source_access_repair(
    action_id: str,
    *,
    body: dict | None,
    health_path: Path,
    registry_path: Path,
    desk_action_result: DeskActionResult,
    validate_source_id: ValidateSourceId,
) -> dict:
    action_label = "Source access repair"
    _require_confirm_only(body, action_label=action_label)
    health = _source_access_health_loaded(health_path)
    if not health:
        return desk_action_result(
            action_id,
            status="blocked",
            title="Check source access first",
            detail="Signal Desk needs a recent source access check before it can safely disable sources.",
            next_action="Run Check source access, then retry this repair action.",
        )
    if not _source_access_health_is_fresh(health):
        return desk_action_result(
            action_id,
            status="blocked",
            title="Source access check is stale",
            detail="Run a fresh access check before changing the saved source list.",
            next_action="Run Check source access, then retry this repair action.",
        )
    keep_only_accessible = action_id == "sources_keep_accessible"
    target_ids = _source_access_target_ids(health, keep_only_accessible=keep_only_accessible, validate_source_id=validate_source_id)
    changed_count = _disable_sources_from_access_health(target_ids, registry_path=registry_path)
    if keep_only_accessible:
        title = "Recently active sources kept"
        detail = (
            f"Signal Desk disabled {changed_count} inaccessible or quiet sources from the latest access check. "
            "Quiet sources were readable, but had no recent messages in the probe window."
        )
    else:
        title = "Inaccessible sources paused"
        detail = f"Signal Desk disabled {changed_count} inaccessible sources from the latest access check."
    return desk_action_result(
        action_id,
        status="success",
        title=title,
        detail=detail,
        next_action="Run a fresh AI review to verify the narrowed source list.",
    )
