"""Source registry listing, import, and mutation helpers for Signal Desk."""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import source_registry


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESK_SOURCE_IMPORT_ALLOWED_FIELDS = {"sources", "topic"}
DESK_SOURCE_STARTER_ALLOWED_FIELDS = {"topic"}
DESK_SOURCE_UPDATE_ALLOWED_FIELDS = {"enabled"}
DESK_SOURCE_TOPIC_ALLOWED_FIELDS = {"topics"}
DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH = 20000
DESK_SOURCE_IMPORT_MAX_CHANNELS = 500


def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("scripts.dashboard_server")
    return getattr(facade, name, default) if facade is not None else default


def _project_root() -> Path:
    return Path(_facade_attr("PROJECT_ROOT", PROJECT_ROOT))


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


def _source_import_allowed_fields() -> set[str]:
    return set(_facade_attr("DESK_SOURCE_IMPORT_ALLOWED_FIELDS", DESK_SOURCE_IMPORT_ALLOWED_FIELDS))


def _source_starter_allowed_fields() -> set[str]:
    return set(_facade_attr("DESK_SOURCE_STARTER_ALLOWED_FIELDS", DESK_SOURCE_STARTER_ALLOWED_FIELDS))


def _source_update_allowed_fields() -> set[str]:
    return set(_facade_attr("DESK_SOURCE_UPDATE_ALLOWED_FIELDS", DESK_SOURCE_UPDATE_ALLOWED_FIELDS))


def _source_topic_allowed_fields() -> set[str]:
    return set(_facade_attr("DESK_SOURCE_TOPIC_ALLOWED_FIELDS", DESK_SOURCE_TOPIC_ALLOWED_FIELDS))


def _source_import_max_text_length() -> int:
    return int(_facade_attr("DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH", DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH))


def _source_import_max_channels() -> int:
    return int(_facade_attr("DESK_SOURCE_IMPORT_MAX_CHANNELS", DESK_SOURCE_IMPORT_MAX_CHANNELS))


def _reject_unexpected_source_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in _source_import_allowed_fields())
    if unexpected:
        raise ValueError(f"Unsupported source import field: {', '.join(unexpected)}")


def _reject_unexpected_source_starter_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in _source_starter_allowed_fields())
    if unexpected:
        raise ValueError(f"Unsupported starter source field: {', '.join(unexpected)}")


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
    unexpected = sorted(str(key) for key in body.keys() if key not in _source_update_allowed_fields())
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
    unexpected = sorted(str(key) for key in body.keys() if key not in _source_topic_allowed_fields())
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


def _desk_sources_from_body(body: dict) -> tuple[list[str], str]:
    _reject_unexpected_source_fields(body)
    text = str(body.get("sources") or "")
    if len(text) > _source_import_max_text_length():
        raise ValueError("Paste fewer sources at a time.")
    channels = source_registry.load_channel_text(text)
    if not channels:
        raise ValueError("Paste at least one Telegram channel handle or t.me link.")
    if len(channels) > _source_import_max_channels():
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
    channels = [
        channel
        for channel in source_registry.load_channel_list(starter_path)
        if not source_registry.normalize_channel_name(channel).casefold().startswith("example_")
    ]
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
    payload["detail"] = (
        "Signal Desk refreshed the packaged starter source set. Example placeholders are skipped; add real channels from Settings when needed."
    )
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
