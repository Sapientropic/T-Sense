"""Review-card projection, sanitization, and persistence helpers."""

from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from scripts import desk_artifacts, source_insights as _source_insights
from scripts.item_display import display_item_title, is_placeholder_value
from scripts.monitor_common import (
    ACTION_TO_STATUS,
    LIFECYCLE_ACTIONS,
    LIFECYCLE_ACTION_TO_STATUS,
    MonitorStateError,
    OPEN_OPPORTUNITY_STATUS,
    PENDING_STATUS,
    PRIVATE_ITEM_FIELDS,
    PRIVATE_ITEM_FIELD_SUFFIXES,
    PROJECT_ROOT,
    RAW_ITEM_FIELDS,
    REVIEW_ACTIONS,
    REVIEW_CARD_SCHEMA_VERSION,
    parse_json,
    require_profile_text_without_private_fragments,
    sha256_text,
    stable_json,
    utc_now,
)
from scripts.profile_patches import REVIEW_LEARNING_PATCH_NOTE


def _source_refs(item: dict[str, Any]) -> list[dict[str, Any]]:
    refs = item.get("source_message_refs")
    if not isinstance(refs, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        channel = str(ref.get("channel") or "").strip()
        msg_id = ref.get("id")
        if channel and msg_id is not None:
            cleaned.append({"channel": channel, "id": msg_id})
    return cleaned


def _item_title(item: dict[str, Any]) -> str:
    return display_item_title(item, fallback="Telegram signal", max_len=160)


def _item_key(profile_id: str, item: dict[str, Any]) -> str:
    state = item.get("decision_state") if isinstance(item.get("decision_state"), dict) else {}
    semantic_cluster = str(state.get("semantic_cluster") or "").strip()
    if semantic_cluster:
        return semantic_cluster
    basis = {
        "profile_id": profile_id,
        "title": _item_title(item),
        "refs": _source_refs(item),
    }
    return "monitor:" + sha256_text(stable_json(basis))[:24]


def _is_raw_item_field(key: object) -> bool:
    normalized = str(key or "").strip().lower()
    return normalized in RAW_ITEM_FIELDS


def _is_private_item_field(key: object) -> bool:
    normalized = str(key or "").strip().lower()
    return normalized in PRIVATE_ITEM_FIELDS or normalized.endswith(PRIVATE_ITEM_FIELD_SUFFIXES)


def _sanitize_item_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_item_value(nested)
            for key, nested in value.items()
            if not _is_raw_item_field(key) and not _is_private_item_field(key)
        }
    if isinstance(value, list):
        return [_sanitize_item_value(item) for item in value]
    return value


def _sanitize_item(item: dict[str, Any]) -> dict[str, Any]:
    # Review-card item_json is reused by Dashboard and feedback export. Keep it
    # as a product decision projection; runner control fields, local paths, and
    # credentials belong in manifests or guarded setup contracts instead.
    sanitized = {
        key: _sanitize_item_value(value)
        for key, value in item.items()
        if not _is_raw_item_field(key) and not _is_private_item_field(key)
    }
    sanitized["schema_version"] = "monitor_item_projection_v1"
    return sanitized


def card_id_for_item(profile_id: str, item: dict[str, Any]) -> str:
    basis = {"profile_id": profile_id, "item_key": _item_key(profile_id, item), "refs": _source_refs(item)}
    return "card_" + sha256_text(stable_json(basis))[:24]


def upsert_review_cards(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    run_id: str,
    items: Iterable[dict[str, Any]],
    report_path: str | None = None,
    dashboard_url: str | None = None,
) -> list[dict[str, Any]]:
    now = utc_now()
    cards: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        card_id = card_id_for_item(profile_id, item)
        item_key = _item_key(profile_id, item)
        title = _item_title(item)
        rating = str(item.get("rating") or "unknown")
        state = item.get("decision_state") if isinstance(item.get("decision_state"), dict) else {}
        decision_status = str(state.get("status") or "unknown")
        refs = _source_refs(item)
        existing = conn.execute(
            """
            SELECT status, opportunity_status, opportunity_updated_at, duplicate_of_card_id,
                   first_run_id, created_at, handled_at
            FROM review_cards WHERE card_id = ?
            """,
            (card_id,),
        ).fetchone()
        status = existing["status"] if existing else PENDING_STATUS
        opportunity_status = existing["opportunity_status"] if existing else OPEN_OPPORTUNITY_STATUS
        opportunity_updated_at = existing["opportunity_updated_at"] if existing else ""
        duplicate_of_card_id = existing["duplicate_of_card_id"] if existing else None
        first_run_id = existing["first_run_id"] if existing else run_id
        created_at = existing["created_at"] if existing else now
        handled_at = existing["handled_at"] if existing else None
        conn.execute(
            """
            INSERT OR REPLACE INTO review_cards(
                card_id, profile_id, item_key, title, rating, decision_status,
                source_refs_json, item_json, status, opportunity_status,
                opportunity_updated_at, duplicate_of_card_id, first_run_id, last_run_id,
                report_path, dashboard_url, created_at, updated_at, handled_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                profile_id,
                item_key,
                title,
                rating,
                decision_status,
                stable_json(refs),
                stable_json(_sanitize_item(item)),
                status,
                opportunity_status,
                opportunity_updated_at,
                duplicate_of_card_id,
                first_run_id,
                run_id,
                report_path,
                dashboard_url,
                created_at,
                now,
                handled_at,
            ),
        )
        cards.append(get_review_card(conn, card_id))
    conn.commit()
    return cards


def get_review_card(conn: sqlite3.Connection, card_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM review_cards WHERE card_id = ?", (card_id,)).fetchone()
    if not row:
        raise MonitorStateError(f"Review card not found: {card_id}")
    return _card_from_row(row)


def set_card_action(
    conn: sqlite3.Connection,
    *,
    card_id: str,
    action: str,
    note: str = "",
    profile_path: Path | None = None,
) -> dict[str, Any]:
    if action not in REVIEW_ACTIONS:
        raise MonitorStateError(f"Unsupported review action: {action}")
    note = " ".join(str(note or "").split())
    if note:
        note = require_profile_text_without_private_fragments("Review note", note)
    card = get_review_card(conn, card_id)
    now = utc_now()
    if action in LIFECYCLE_ACTIONS:
        opportunity_status = LIFECYCLE_ACTION_TO_STATUS[action]
        handled_at = None if opportunity_status == OPEN_OPPORTUNITY_STATUS else now
        # Lifecycle actions are local processing state, not preference training.
        # Do not write feedback_events here; exports must only contain explicit
        # matching-learning choices such as keep/skip/false_positive/follow_up.
        conn.execute(
            """
            UPDATE review_cards
            SET opportunity_status = ?, opportunity_updated_at = ?, handled_at = ?, updated_at = ?
            WHERE card_id = ?
            """,
            (opportunity_status, now, handled_at, now, card_id),
        )
        conn.commit()
        return get_review_card(conn, card_id)
    if action == "follow_up" and not note:
        raise MonitorStateError("Follow-up note is required.")
    status = ACTION_TO_STATUS[action]
    conn.execute(
        "UPDATE review_cards SET status = ?, handled_at = ?, updated_at = ? WHERE card_id = ?",
        (status, now, now, card_id),
    )
    # Feedback is a current decision per review card, not an append-only click
    # log. Replacing the old row here keeps repeated clicks idempotent and
    # prevents stale choices from leaking into future report learning.
    conn.execute("DELETE FROM feedback_events WHERE card_id = ?", (card_id,))
    _delete_legacy_pending_profile_patches_for_card(conn, card_id=card_id)
    _delete_pending_review_learning_drafts_for_profile(conn, profile_id=card["profile_id"])
    conn.execute(
        """
        INSERT INTO feedback_events(event_id, card_id, profile_id, action, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("feedback_" + uuid.uuid4().hex, card_id, card["profile_id"], action, note, now),
    )
    conn.commit()
    return get_review_card(conn, card_id)


def undo_card_action(conn: sqlite3.Connection, *, card_id: str) -> dict[str, Any]:
    card = get_review_card(conn, card_id)
    now = utc_now()
    conn.execute("DELETE FROM feedback_events WHERE card_id = ?", (card_id,))
    _delete_legacy_pending_profile_patches_for_card(conn, card_id=card_id)
    _delete_pending_review_learning_drafts_for_profile(conn, profile_id=card["profile_id"])
    conn.execute(
        "UPDATE review_cards SET status = ?, handled_at = NULL, updated_at = ? WHERE card_id = ?",
        (PENDING_STATUS, now, card_id),
    )
    conn.commit()
    return get_review_card(conn, card_id)


def _delete_legacy_pending_profile_patches_for_card(conn: sqlite3.Connection, *, card_id: str) -> None:
    conn.execute(
        """
        DELETE FROM profile_patch_suggestions
        WHERE card_id = ?
          AND status = 'pending'
          AND note != ?
        """,
        (card_id, REVIEW_LEARNING_PATCH_NOTE),
    )


def _delete_pending_review_learning_drafts_for_profile(conn: sqlite3.Connection, *, profile_id: str) -> None:
    # Review feedback is collected first, then turned into one profile-level
    # draft from the current full set of tags and notes. When the underlying
    # evidence changes, remove only the pending generated draft so users do not
    # apply a stale profile suggestion by accident. Applied/reverted history is
    # left intact for audit and rollback.
    conn.execute(
        """
        DELETE FROM profile_patch_suggestions
        WHERE profile_id = ?
          AND status = 'pending'
          AND note = ?
        """,
        (profile_id, REVIEW_LEARNING_PATCH_NOTE),
    )


def _card_from_row(row: sqlite3.Row, source_link_lookup: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    item = parse_json(row["item_json"], {})
    title = str(row["title"] or "").strip()
    derived_title = display_item_title(item, fallback=title or "Telegram signal", max_len=160)
    if derived_title and not is_placeholder_value(derived_title):
        title = derived_title
    elif is_placeholder_value(title):
        title = derived_title
    source_refs = enrich_source_refs(parse_json(row["source_refs_json"], []), source_link_lookup or {})
    return {
        "schema_version": REVIEW_CARD_SCHEMA_VERSION,
        "card_id": row["card_id"],
        "profile_id": row["profile_id"],
        "item_key": row["item_key"],
        "title": title,
        "rating": row["rating"],
        "decision_status": row["decision_status"],
        "source_refs": source_refs,
        "item": item,
        "status": row["status"],
        "opportunity_status": row["opportunity_status"] or OPEN_OPPORTUNITY_STATUS,
        "opportunity_updated_at": row["opportunity_updated_at"] or "",
        "duplicate_of_card_id": row["duplicate_of_card_id"] or None,
        "first_run_id": row["first_run_id"],
        "last_run_id": row["last_run_id"],
        "report_path": preferred_report_path(str(row["report_path"] or "")),
        "dashboard_url": row["dashboard_url"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "handled_at": row["handled_at"],
    }


def enrich_source_refs(refs: object, source_link_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(refs, list):
        return []
    enriched: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        channel = str(ref.get("channel") or "").strip()
        msg_id = ref.get("id")
        if not channel or msg_id is None:
            continue
        item: dict[str, Any] = {"channel": channel, "id": msg_id}
        source_info = source_link_lookup.get(source_lookup_key(channel), {})
        url = telegram_source_ref_url(channel=channel, message_id=msg_id, source_info=source_info)
        if url:
            item["url"] = url
        enriched.append(item)
    return enriched


def source_lookup_key(value: object) -> str:
    return str(value or "").strip().casefold()


def source_link_lookup_from_runs(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    _source_insights.PROJECT_ROOT = PROJECT_ROOT
    for run in runs[:8]:
        payload = _source_insights.scan_meta_payload(run)
        source_health = payload.get("source_health") if isinstance(payload.get("source_health"), list) else []
        for row in source_health:
            if not isinstance(row, dict):
                continue
            source_info = {
                "username": str(row.get("username") or "").strip(),
                "channel_id": row.get("channel_id"),
            }
            for key_value in (row.get("channel"), row.get("username"), row.get("label"), row.get("source_id")):
                key = source_lookup_key(key_value)
                if key:
                    lookup.setdefault(key, source_info)
    return lookup


def telegram_source_ref_url(*, channel: str, message_id: object, source_info: dict[str, Any]) -> str:
    msg_text = str(message_id or "").strip()
    if not re.fullmatch(r"\d+", msg_text):
        return ""
    username = str(source_info.get("username") or "").strip().removeprefix("@")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", username):
        return f"https://t.me/{username}/{msg_text}"
    channel_name = str(channel or "").strip().removeprefix("@")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", channel_name):
        return f"https://t.me/{channel_name}/{msg_text}"
    channel_id_text = str(source_info.get("channel_id") or "").strip()
    if re.fullmatch(r"-?\d{5,20}", channel_id_text):
        return f"https://t.me/c/{channel_id_text.removeprefix('-100').removeprefix('-')}/{msg_text}"
    return ""


def preferred_report_path(report_path: str) -> str:
    normalized = _dashboard_report_path(report_path)
    if not normalized:
        return ""
    path = Path(normalized)
    if path.suffix.lower() != ".md":
        return normalized
    html_path = path.with_suffix(".html")
    html_path_for_exists = PROJECT_ROOT / html_path
    if not html_path_for_exists.exists():
        return normalized
    html_report_path = str(html_path).replace("\\", "/")
    if not desk_artifacts.is_dashboard_openable_artifact_path(html_report_path):
        return normalized
    return str(html_path).replace("\\", "/")


def _dashboard_report_path(report_path: str) -> str:
    raw = str(report_path or "").strip()
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            raw = str(candidate.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError:
            return ""
    normalized = raw.replace("\\", "/")
    # Review-card previews fetch the rendered report through the guarded local
    # artifact route. Returning only route-openable paths prevents old imports
    # from surfacing private absolute paths or report files the Desk cannot use
    # to recover original source snippets.
    if not desk_artifacts.is_dashboard_openable_artifact_path(normalized):
        return ""
    return normalized
