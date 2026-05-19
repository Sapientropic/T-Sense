"""Source registry listing, import, and mutation helpers for Signal Desk."""

from __future__ import annotations

import json
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
PUBLIC_SOURCE_CANDIDATE_SCHEMA_VERSION = "public_source_candidates_v1"
DEFAULT_STARTER_TOPIC = "market-news"
JOBS_STARTER_TOPIC = "jobs"
PUBLIC_SOURCE_CANDIDATE_RAW_TEXT_KEYS = {
    "content",
    "message",
    "messages",
    "message_body",
    "message_text",
    "post",
    "post_body",
    "post_sample",
    "post_samples",
    "post_text",
    "posts",
    "raw_message",
    "raw_messages",
    "raw_text",
    "sample",
    "sample_message",
    "sample_messages",
    "sample_post",
    "sample_posts",
    "samples",
    "text",
}


def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("scripts.dashboard_server")
    return getattr(facade, name, default) if facade is not None else default


def _project_root() -> Path:
    return Path(_facade_attr("PROJECT_ROOT", PROJECT_ROOT))


def _code_root() -> Path:
    return Path(_facade_attr("CODE_ROOT", PROJECT_ROOT))


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
    topic = str(value or DEFAULT_STARTER_TOPIC).strip().casefold()
    if not topic:
        topic = DEFAULT_STARTER_TOPIC
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", topic):
        raise ValueError("Source topic must use letters, numbers, hyphen, or underscore.")
    return topic


def _source_import_payload(result: dict, *, topic: str, written: bool) -> dict:
    def source_label(source: dict) -> str:
        return str(source.get("label") or source.get("username") or source.get("channel_id") or "").strip()

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
        "removed_count": int(result.get("removed_count") or 0),
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
    record = {
        "schema_version": "desk_source_v1",
        "source_id": str(source.get("source_id") or ""),
        "label": label,
        "channel": channel,
        "enabled": bool(source.get("enabled", True)),
        "topics": source_registry.normalize_topics(source.get("topics") or []),
        "priority": str(source.get("priority") or "normal"),
        "scan_window_hours": int(source.get("scan_window_hours") or source_registry.DEFAULT_SCAN_WINDOW_HOURS),
    }
    expected_language = str(source.get("expected_language") or "").strip()
    notes = str(source.get("notes") or "").strip()
    if expected_language:
        record["expected_language"] = expected_language
    if notes:
        record["notes"] = notes
    return record


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


def _loads_public_source_candidates(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError("Public source candidate JSON is invalid.") from exc


def _public_source_candidate_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        schema_version = str(payload.get("schema_version") or "").strip()
        if schema_version and schema_version != PUBLIC_SOURCE_CANDIDATE_SCHEMA_VERSION:
            raise ValueError("Public source candidate JSON uses an unsupported schema version.")
        candidates = payload.get("candidates")
    else:
        raise ValueError("Public source candidate JSON must be an object or list.")
    if not isinstance(candidates, list):
        raise ValueError("Public source candidate JSON must include a candidates list.")
    if len(candidates) > _source_import_max_channels():
        raise ValueError("Paste fewer source candidates at a time.")
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Public source candidates must be objects.")
        rows.append(candidate)
    return rows


def _reject_public_candidate_raw_text(candidate: Any) -> None:
    if isinstance(candidate, list):
        for item in candidate:
            _reject_public_candidate_raw_text(item)
        return
    if not isinstance(candidate, dict):
        return
    for key, value in candidate.items():
        normalized = re.sub(r"[^a-z0-9]+", "_", str(key).strip().casefold()).strip("_")
        if normalized in PUBLIC_SOURCE_CANDIDATE_RAW_TEXT_KEYS:
            raise ValueError("Public source candidates must not include Telegram message text.")
        _reject_public_candidate_raw_text(value)


def _candidate_channel_value(candidate: dict[str, Any]) -> str:
    for field in ("channel", "handle", "username", "url"):
        channel = source_registry.normalize_channel_name(candidate.get(field))
        if channel:
            return channel
    return ""


def _compact_candidate_text(value: Any, *, max_length: int = 120) -> str:
    text = " ".join(str(value or "").split())
    return text[:max_length].strip()


def _candidate_language(value: Any) -> str:
    language = _compact_candidate_text(value, max_length=20)
    if re.fullmatch(r"[A-Za-z]{2,12}(?:[-_][A-Za-z0-9]{2,12})?", language):
        return language.casefold().replace("_", "-")
    return ""


def _candidate_quality_hints(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    hints: list[str] = []
    for key in sorted(value.keys()):
        if len(hints) >= 4:
            break
        hint_value = value.get(key)
        if isinstance(hint_value, str | int | float | bool):
            clean_key = _compact_candidate_text(key, max_length=40)
            clean_value = _compact_candidate_text(hint_value, max_length=80)
            if clean_key and clean_value:
                hints.append(f"{clean_key}: {clean_value}")
    return hints


def _candidate_source_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    label = _compact_candidate_text(
        candidate.get("title") or candidate.get("label") or candidate.get("name"),
        max_length=80,
    )
    if label:
        metadata["label"] = label
    language = _candidate_language(candidate.get("language") or candidate.get("lang"))
    if language:
        metadata["expected_language"] = language
    note_parts: list[str] = []
    recommendation = _compact_candidate_text(
        candidate.get("source_of_recommendation") or candidate.get("recommendation_source"),
        max_length=100,
    )
    if recommendation:
        note_parts.append(f"Recommended via {recommendation}")
    notes = _compact_candidate_text(candidate.get("notes"), max_length=160)
    if notes:
        note_parts.append(notes)
    note_parts.extend(_candidate_quality_hints(candidate.get("quality_hints")))
    if note_parts:
        metadata["notes"] = "; ".join(note_parts)[:300]
    return metadata


def _public_source_candidate_import_data(payload: Any) -> tuple[list[str], dict[str, dict[str, Any]]]:
    _reject_public_candidate_raw_text(payload)
    channels: list[str] = []
    metadata_by_channel: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for candidate in _public_source_candidate_rows(payload):
        channel = _candidate_channel_value(candidate)
        if not channel:
            continue
        key = channel.casefold()
        if key in seen:
            continue
        seen.add(key)
        channels.append(channel)
        metadata = _candidate_source_metadata(candidate)
        if metadata:
            metadata_by_channel[key] = metadata
    if not channels:
        raise ValueError("Public source candidates must include at least one Telegram channel handle or t.me URL.")
    return channels, metadata_by_channel


def _source_channels_from_text(text: str) -> tuple[list[str], str, dict[str, dict[str, Any]]]:
    public_candidate_payload = _loads_public_source_candidates(text)
    if public_candidate_payload is not None:
        channels, metadata = _public_source_candidate_import_data(public_candidate_payload)
        return channels, "public source candidates", metadata
    return source_registry.load_channel_text(text), "pasted sources", {}


def _desk_sources_from_body(body: dict) -> tuple[list[str], str, str, dict[str, dict[str, Any]]]:
    _reject_unexpected_source_fields(body)
    text = str(body.get("sources") or "")
    if len(text) > _source_import_max_text_length():
        raise ValueError("Paste fewer sources at a time.")
    channels, input_path, source_metadata = _source_channels_from_text(text)
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
    return channels, topic, input_path, source_metadata


def _starter_source_candidate_paths(topic: str = JOBS_STARTER_TOPIC) -> list[Path]:
    topic = _clean_source_topic(topic)
    project_root = _project_root()
    code_root = _code_root()
    try:
        same_root = project_root.resolve() == code_root.resolve()
    except OSError:
        same_root = project_root == code_root
    if topic == JOBS_STARTER_TOPIC:
        project_jobs = project_root / "channel_lists" / "jobs.txt"
        project_candidates = project_root / "channel_lists" / "jobs.public-candidates.json"
        project_example = project_root / "channel_lists" / "example.txt"
        code_candidates = code_root / "channel_lists" / "jobs.public-candidates.json"
        code_jobs = code_root / "channel_lists" / "jobs.txt"
        code_example = code_root / "channel_lists" / "example.txt"
        if same_root:
            return [code_candidates, code_jobs, code_example]
        return [project_jobs, project_candidates, project_example, code_candidates, code_jobs, code_example]
    project_candidates = project_root / "channel_lists" / f"{topic}.public-candidates.json"
    project_list = project_root / "channel_lists" / f"{topic}.txt"
    code_candidates = code_root / "channel_lists" / f"{topic}.public-candidates.json"
    code_list = code_root / "channel_lists" / f"{topic}.txt"
    if same_root:
        return [code_candidates, code_list]
    return [project_candidates, project_list, code_candidates, code_list]


def _starter_channels_and_metadata(path: Path) -> tuple[list[str], dict[str, dict[str, Any]], str]:
    if path.suffix.casefold() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Starter source candidate JSON is invalid.") from exc
        channels, metadata = _public_source_candidate_import_data(payload)
        return channels, metadata, "packaged public-source starter"
    channels = [
        channel
        for channel in source_registry.load_channel_list(path)
        if not source_registry.normalize_channel_name(channel).casefold().startswith("example_")
    ]
    return channels, {}, "packaged starter sources"


def _remove_example_placeholder_sources(registry_path: Path) -> int:
    try:
        payload = source_registry.load_registry(registry_path, missing_ok=True)
    except source_registry.RegistryError:
        return 0
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return 0
    kept_sources = [
        source
        for source in sources
        if not source_registry.normalize_channel_name(source.get("username") if isinstance(source, dict) else "").casefold().startswith("example_")
    ]
    removed_count = len(sources) - len(kept_sources)
    if removed_count <= 0:
        return 0
    payload["sources"] = kept_sources
    source_registry.save_registry(registry_path, payload)
    return removed_count


def import_starter_sources(body: dict) -> dict:
    _reject_unexpected_source_starter_fields(body)
    topic = _clean_source_topic(body.get("topic"))
    starter_candidates = _starter_source_candidate_paths(topic)
    starter_path = next((candidate for candidate in starter_candidates if candidate.exists()), starter_candidates[0])
    if not starter_path.exists():
        raise ValueError("Starter source list is missing from this checkout.")
    channels, source_metadata, input_path = _starter_channels_and_metadata(starter_path)
    registry_path = _project_root() / ".tgcs" / "sources.json"
    removed_count = _remove_example_placeholder_sources(registry_path)
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=False,
        topics=[topic],
        input_path=input_path,
        source_metadata=source_metadata,
    )
    if removed_count:
        result["removed_count"] = removed_count
    payload = _source_import_payload(result, topic=topic, written=True)
    payload["title"] = "Starter sources installed"
    payload["detail"] = (
        "Signal Desk refreshed the packaged public-source starter set. Review and prune noisy channels from Settings before relying on live scans."
    )
    return payload


def preview_desk_source_import(body: dict) -> dict:
    channels, topic, input_path, source_metadata = _desk_sources_from_body(body)
    registry_path = _project_root() / ".tgcs" / "sources.json"
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=True,
        topics=[topic],
        input_path=input_path,
        source_metadata=source_metadata,
    )
    return _source_import_payload(result, topic=topic, written=False)


def import_desk_sources(body: dict) -> dict:
    channels, topic, input_path, source_metadata = _desk_sources_from_body(body)
    registry_path = _project_root() / ".tgcs" / "sources.json"
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=False,
        topics=[topic],
        input_path=input_path,
        source_metadata=source_metadata,
    )
    return _source_import_payload(result, topic=topic, written=True)
