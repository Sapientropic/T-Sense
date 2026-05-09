"""Display helpers for semantic Telegram items.

Models are instructed to use placeholders such as ``Unknown`` and
``Not specified`` when a field is missing.  Those placeholders are useful in
detail tables, but they must not become the primary title shown in alerts,
dashboard cards, or feedback keys.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence


MISSING_VALUE_MARKERS = {
    "",
    "unknown",
    "not specified",
    "not provided",
    "unspecified",
    "n/a",
    "na",
    "none",
    "null",
    "tbd",
    "see source",
    "see telegram",
}


def _squash(value: object) -> str:
    return " ".join(str(value or "").split())


def is_placeholder_value(value: object) -> bool:
    text = _squash(value).casefold().strip(" \t\r\n-_:.,;")
    return text in MISSING_VALUE_MARKERS or text.startswith("unknown ")


def truncate_text(text: str, *, max_len: int | None = None) -> str:
    if not max_len or len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def meaningful_text(value: object, *, max_len: int | None = None) -> str:
    if isinstance(value, dict):
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = meaningful_text(item, max_len=max_len)
            if text:
                return text
        return ""
    text = _squash(value)
    if is_placeholder_value(text):
        return ""
    return truncate_text(text, max_len=max_len)


def display_title_parts(
    item: dict[str, Any],
    *,
    dedup_fields: Sequence[str] | None = None,
    fallback: str = "Telegram signal",
) -> tuple[str, str]:
    role = meaningful_text(item.get("role")) or meaningful_text(item.get("title"))
    company = meaningful_text(item.get("company"))
    if role:
        return role, company

    project = meaningful_text(item.get("project"))
    event = meaningful_text(item.get("event"))
    if project:
        return project, event

    topic = meaningful_text(item.get("topic"))
    if topic:
        return topic, event

    if company:
        return company, ""

    title = meaningful_text(item.get("title"))
    if title:
        return title, ""

    parts: list[str] = []
    for field in dedup_fields or []:
        value = meaningful_text(item.get(field))
        if value and value not in parts:
            parts.append(value)
        if len(parts) >= 2:
            break
    if parts:
        return parts[0], parts[1] if len(parts) > 1 else ""

    return fallback, ""


def source_ref_title(refs: object, *, max_len: int | None = None) -> str:
    if not isinstance(refs, list):
        return ""
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        channel = meaningful_text(ref.get("channel"))
        msg_id = ref.get("id")
        if channel and msg_id not in (None, ""):
            return truncate_text(f"{channel}#{msg_id}", max_len=max_len)
    return ""


def display_item_title(
    item: dict[str, Any],
    *,
    dedup_fields: Sequence[str] | None = None,
    fallback: str = "Telegram signal",
    max_len: int | None = 160,
) -> str:
    primary, secondary = display_title_parts(item, dedup_fields=dedup_fields, fallback="")
    parts = [part for part in (primary, secondary) if meaningful_text(part)]
    if parts:
        return truncate_text(" - ".join(parts), max_len=max_len)

    ref_title = source_ref_title(item.get("source_message_refs"), max_len=max_len)
    if ref_title:
        return ref_title
    return truncate_text(fallback, max_len=max_len)


def meaningful_dedup_pairs(item: dict[str, Any], fields: Iterable[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for field in fields:
        value = meaningful_text(item.get(field))
        if value:
            pairs.append((field, value))
    return pairs
