"""Cross-run item memory and decision-state enrichment."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Iterable

from scripts.item_display import display_item_title, meaningful_dedup_pairs, meaningful_text
from scripts.profile_schema import ProfileConfig


DECISION_STATE_SCHEMA_VERSION = "decision_state_v1"
SUMMARY_KEYS = ("new", "seen", "changed", "recurring", "expired")
VOLATILE_FINGERPRINT_FIELDS = {
    "decision_state",
    "source_message_ids",
    "source_message_refs",
    "origin_message_refs",
    "sources",
    "source",
}


def normalize_text(value: object) -> str:
    text = meaningful_text(value).casefold().strip()
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"[^\w\u0400-\u04ff\u4e00-\u9fff]+", "-", text).strip("-")


def legacy_normalize_text(value: object) -> str:
    text = str(value or "").casefold().strip()
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"[^\w\u0400-\u04ff\u4e00-\u9fff]+", "-", text).strip("-")


def profile_key(profile: str) -> str:
    digest = hashlib.sha256(profile.encode("utf-8")).hexdigest()[:16]
    return f"profile:{digest}"


def source_ref_key(channel: object, message_id: object) -> str:
    return f"{str(channel or '').casefold()}:{str(message_id or '')}"


def clean_source_refs(value: object) -> list[dict]:
    refs: list[dict] = []
    seen: set[str] = set()
    if not isinstance(value, list):
        return refs
    for ref in value:
        if not isinstance(ref, dict):
            continue
        channel = str(ref.get("channel") or "").strip()
        message_id = ref.get("id")
        if not channel or message_id in (None, ""):
            continue
        marker = source_ref_key(channel, message_id)
        if marker in seen:
            continue
        seen.add(marker)
        refs.append({"channel": channel, "id": message_id})
    return refs


def item_title(item: dict, dedup_fields: list[str]) -> str:
    return display_item_title(item, dedup_fields=dedup_fields, fallback="Unknown item")


def item_key(item: dict, profile_config: ProfileConfig, profile_text: str) -> str:
    key_prefix = profile_key(profile_text)
    dedup_fields = profile_config.mode.dedup_fields or []
    dedup_pairs = [
        (field, normalize_text(value))
        for field, value in meaningful_dedup_pairs(item, dedup_fields)
    ]
    if dedup_pairs:
        field_part = "|".join(
            f"{field}:{value}" for field, value in dedup_pairs
        )
        return f"{key_prefix}:{field_part}"
    refs = clean_source_refs(item.get("source_message_refs"))
    if refs:
        ref_part = "|".join(
            sorted(source_ref_key(ref["channel"], ref["id"]) for ref in refs)
        )
        return f"{key_prefix}:refs:{ref_part}"
    digest = hashlib.sha256(
        json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"{key_prefix}:item:{digest}"


def legacy_placeholder_item_key(item: dict, profile_config: ProfileConfig, profile_text: str) -> str | None:
    key_prefix = profile_key(profile_text)
    dedup_fields = profile_config.mode.dedup_fields or []
    dedup_values = [legacy_normalize_text(item.get(field)) for field in dedup_fields]
    if not any(dedup_values):
        return None
    meaningful_values = [normalize_text(item.get(field)) for field in dedup_fields]
    if dedup_values == meaningful_values:
        return None
    field_part = "|".join(
        f"{field}:{value}" for field, value in zip(dedup_fields, dedup_values, strict=False)
    )
    return f"{key_prefix}:{field_part}"


def source_ref_memory_key(item: dict, state_items: dict) -> str | None:
    refs = clean_source_refs(item.get("source_message_refs"))
    if not refs:
        return None
    current_markers = {source_ref_key(ref["channel"], ref["id"]) for ref in refs}
    if not current_markers:
        return None
    for key, previous in state_items.items():
        if not isinstance(previous, dict):
            continue
        previous_refs = clean_source_refs(previous.get("source_message_refs"))
        previous_markers = {source_ref_key(ref["channel"], ref["id"]) for ref in previous_refs}
        if current_markers & previous_markers:
            return str(key)
    return None


def fingerprint_item(item: dict) -> str:
    stable = fingerprint_fields(item)
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def fingerprint_fields(item: dict) -> dict:
    return {
        key: value
        for key, value in item.items()
        if key not in VOLATILE_FINGERPRINT_FIELDS
    }


def material_change_fields(previous_fields: object, current_fields: dict) -> list[str]:
    previous = previous_fields if isinstance(previous_fields, dict) else {}
    changed: list[str] = []
    for key, value in current_fields.items():
        if previous.get(key) != value:
            changed.append(str(key))
    for key in previous:
        if key not in current_fields:
            changed.append(str(key))
    return changed


def parse_observed_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC).replace(microsecond=0)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime.fromisoformat(text).replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _deadline_date(item: dict) -> date | None:
    value = item.get("deadline_or_time") or item.get("deadline") or item.get("expires_at")
    text = str(value or "")
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if not match:
        if "expired" in text.casefold():
            return date.min
        return None
    return date.fromisoformat(match.group(1))


def is_expired(item: dict, observed_at: datetime) -> bool:
    deadline = _deadline_date(item)
    return bool(deadline and deadline < observed_at.date())


def _feedback_matches(entry: dict, item: dict, title: str) -> bool:
    entry_refs = clean_source_refs(entry.get("source_message_refs"))
    item_refs = clean_source_refs(item.get("source_message_refs"))
    if entry_refs and item_refs:
        entry_markers = {source_ref_key(ref["channel"], ref["id"]) for ref in entry_refs}
        item_markers = {source_ref_key(ref["channel"], ref["id"]) for ref in item_refs}
        if entry_markers & item_markers:
            return True
    entry_title = str(entry.get("item_title") or "").strip()
    return bool(entry_title and entry_title == title)


def feedback_counts_for_item(
    feedback_entries: Iterable[dict],
    item: dict,
    title: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in feedback_entries:
        feedback = str(entry.get("feedback") or "").strip()
        if not feedback or not _feedback_matches(entry, item, title):
            continue
        counts[feedback] = counts.get(feedback, 0) + 1
    return counts


def _source_priority(item: dict, source_registry: dict | None) -> str:
    if not source_registry:
        return "unknown"
    lookup: dict[str, str] = {}
    for source in source_registry.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        priority = str(source.get("priority") or "normal")
        username = str(source.get("username") or "").casefold()
        label = str(source.get("label") or "").casefold()
        source_id = str(source.get("source_id") or "").casefold()
        for key in (username, label, source_id):
            if key:
                lookup[key] = priority
    for ref in clean_source_refs(item.get("source_message_refs")):
        priority = lookup.get(str(ref["channel"]).casefold())
        if priority:
            return priority
    return "unknown"


def _explanations(
    *,
    item: dict,
    status: str,
    source_priority: str,
) -> dict:
    explanations = {
        "novelty": status,
        "match_confidence": str(item.get("rating") or "unknown"),
        "urgency": str(item.get("urgency") or item.get("deadline_or_time") or "unknown"),
        "source_priority": source_priority,
    }
    negative = item.get("negative_evidence")
    if negative:
        explanations["negative_evidence"] = negative
        explanations["exclusions"] = negative
    factors = item.get("decision_factors")
    if factors:
        explanations["decision_factors"] = factors
    return explanations


def enrich_items(
    items: list[dict],
    *,
    profile: str,
    profile_config: ProfileConfig,
    state: dict,
    feedback_entries: Iterable[dict] | None = None,
    observed_at: str | None = None,
    source_registry: dict | None = None,
) -> tuple[list[dict], dict, dict]:
    observed = parse_observed_at(observed_at)
    observed_iso = iso_utc(observed)
    profile_id = profile_key(profile)
    summary = {key: 0 for key in SUMMARY_KEYS}
    summary["total"] = 0
    feedback_entries = list(feedback_entries or [])
    state.setdefault("items", {})

    enriched: list[dict] = []
    for item in items:
        current = dict(item)
        key = item_key(current, profile_config, profile)
        title = item_title(current, profile_config.mode.dedup_fields or [])
        current_fingerprint_fields = fingerprint_fields(current)
        fingerprint = fingerprint_item(current)
        previous = state["items"].get(key)
        legacy_key = None
        if previous is None:
            legacy_key = legacy_placeholder_item_key(current, profile_config, profile)
            if legacy_key and legacy_key != key:
                previous = state["items"].get(legacy_key)
        if previous is None:
            legacy_key = source_ref_memory_key(current, state["items"])
            if legacy_key and legacy_key != key:
                previous = state["items"].get(legacy_key)
        changed = bool(previous and previous.get("fingerprint") != fingerprint)
        changed_fields = material_change_fields(
            previous.get("fingerprint_fields") if previous else {},
            current_fingerprint_fields,
        ) if changed else []
        expired = is_expired(current, observed)

        if previous is None:
            status = "new"
        elif changed:
            status = "changed"
        elif int(previous.get("seen_count") or 0) >= 2:
            status = "recurring"
        else:
            status = "seen"
        if expired:
            status = "expired"

        signals = [status]
        if changed and "changed" not in signals:
            signals.append("changed")
        if len(clean_source_refs(current.get("source_message_refs"))) > 1:
            signals.append("cross_channel_cluster")
        feedback_counts = feedback_counts_for_item(feedback_entries, current, title)
        if feedback_counts:
            signals.append("feedback_present")

        priority = _source_priority(current, source_registry)
        current["decision_state"] = {
            "schema_version": DECISION_STATE_SCHEMA_VERSION,
            "status": status,
            "signals": signals,
            "semantic_cluster": key,
            "first_seen_at": previous.get("first_seen_at") if previous else observed_iso,
            "last_seen_at": observed_iso,
            "seen_count": int(previous.get("seen_count") or 0) + 1 if previous else 1,
            "explanations": _explanations(
                item=current,
                status=status,
                source_priority=priority,
            ),
        }
        if changed_fields:
            current["decision_state"]["material_change_fields"] = changed_fields

        existing_feedback = dict(previous.get("feedback_counts") or {}) if previous else {}
        for feedback, count in feedback_counts.items():
            existing_feedback[feedback] = existing_feedback.get(feedback, 0) + count

        rating_history = list(previous.get("rating_history") or []) if previous else []
        rating_history.append({"at": observed_iso, "rating": str(current.get("rating") or "unknown")})
        state["items"][key] = {
            "item_key": key,
            "profile_key": profile_id,
            "source_message_refs": clean_source_refs(current.get("source_message_refs")),
            "first_seen_at": previous.get("first_seen_at") if previous else observed_iso,
            "last_seen_at": observed_iso,
            "seen_count": current["decision_state"]["seen_count"],
            "rating_history": rating_history[-20:],
            "fingerprint": fingerprint,
            "fingerprint_fields": current_fingerprint_fields,
            "feedback_counts": existing_feedback,
        }
        if legacy_key and legacy_key != key:
            state["items"].pop(legacy_key, None)
        summary[status] += 1
        summary["total"] += 1
        enriched.append(current)

    return enriched, state, summary
