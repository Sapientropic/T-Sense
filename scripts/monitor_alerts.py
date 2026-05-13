"""Alert candidate selection and sent-alert suppression for monitor state."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any, Iterable

from scripts.monitor_common import (
    ALERT_EVENT_SCHEMA_VERSION,
    ALERT_RULES,
    HANDLED_STATUSES,
    OPEN_OPPORTUNITY_STATUS,
    parse_iso_datetime,
    parse_json,
    stable_json,
    utc_now,
)


def _within_freshness_window(item: dict[str, Any], max_age_minutes: int | None, now: datetime) -> bool:
    if max_age_minutes is None:
        return True
    freshness = item.get("monitor_freshness") if isinstance(item.get("monitor_freshness"), dict) else {}
    freshest_at = parse_iso_datetime(freshness.get("freshest_source_at"))
    if freshest_at is None:
        return False
    age_seconds = (now.astimezone(UTC) - freshest_at).total_seconds()
    return 0 <= age_seconds <= max_age_minutes * 60


def alert_candidates(
    cards: Iterable[dict[str, Any]],
    *,
    alert_rule: dict[str, Any] | None = None,
    now: datetime | None = None,
    suppressed_card_ids: Iterable[str] | None = None,
    suppressed_alert_keys: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    suppressed = set(suppressed_card_ids or [])
    suppressed_keys = set(suppressed_alert_keys or [])
    max_age = None
    rule_name = "high_new_or_changed"
    if isinstance(alert_rule, dict) and isinstance(alert_rule.get("name"), str):
        candidate_rule = str(alert_rule["name"]).strip()
        if candidate_rule in ALERT_RULES:
            rule_name = candidate_rule
    if isinstance(alert_rule, dict) and alert_rule.get("max_age_minutes") is not None:
        try:
            max_age = int(alert_rule["max_age_minutes"])
        except (TypeError, ValueError):
            max_age = None
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    for card in cards:
        card_id = str(card.get("card_id") or "")
        decision_status = str(card.get("decision_status") or "").strip().lower()
        if not decision_status:
            item_for_status = card.get("item") if isinstance(card.get("item"), dict) else {}
            state_for_status = item_for_status.get("decision_state") if isinstance(item_for_status.get("decision_state"), dict) else {}
            decision_status = str(state_for_status.get("status") or "unknown").strip().lower()
        if card_id in suppressed:
            continue
        if f"{card_id}:*" in suppressed_keys or f"{card_id}:{decision_status}" in suppressed_keys:
            continue
        item = card.get("item") if isinstance(card.get("item"), dict) else {}
        state = item.get("decision_state") if isinstance(item.get("decision_state"), dict) else {}
        # Opportunity lifecycle is real handling progress. Once a card is saved,
        # applied, dismissed, or marked duplicate it should not re-enter the
        # normal alert lane; preference feedback remains a separate learning
        # signal handled through feedback_events.
        opportunity_status = str(card.get("opportunity_status") or OPEN_OPPORTUNITY_STATUS).strip().lower()
        if opportunity_status != OPEN_OPPORTUNITY_STATUS:
            continue
        if card.get("status") in HANDLED_STATUSES:
            continue
        allowed_statuses = {"new"} if rule_name == "high_new_only" else {"new", "changed"}
        if (
            str(item.get("rating") or "").lower() == "high"
            and state.get("status") in allowed_statuses
            and _within_freshness_window(
                item,
                max_age,
                current_time,
            )
        ):
            candidates.append(card)
    return candidates


def sent_alert_card_ids(conn: sqlite3.Connection, *, profile_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT card_id FROM alert_events WHERE profile_id = ? AND status = ?",
        (profile_id, "sent"),
    ).fetchall()
    return {str(row["card_id"]) for row in rows}


def sent_alert_suppression_keys(conn: sqlite3.Connection, *, profile_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT card_id, payload_json FROM alert_events WHERE profile_id = ? AND status = ?",
        (profile_id, "sent"),
    ).fetchall()
    keys: set[str] = set()
    for row in rows:
        card_id = str(row["card_id"])
        payload = parse_json(row["payload_json"], {})
        decision_status = ""
        if isinstance(payload, dict):
            decision_status = str(payload.get("decision_status") or "").strip().lower()
        keys.add(f"{card_id}:{decision_status}" if decision_status in {"new", "changed"} else f"{card_id}:*")
    return keys


def record_alert_event(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    card_id: str,
    profile_id: str,
    target_id: str,
    status: str,
    payload: dict[str, Any],
    delivery_attempt: dict[str, Any],
) -> dict[str, Any]:
    event = {
        "schema_version": ALERT_EVENT_SCHEMA_VERSION,
        "alert_id": "alert_" + uuid.uuid4().hex,
        "run_id": run_id,
        "card_id": card_id,
        "profile_id": profile_id,
        "target_id": target_id,
        "status": status,
        "payload": payload,
        "delivery_attempt": delivery_attempt,
        "created_at": utc_now(),
    }
    conn.execute(
        """
        INSERT INTO alert_events(alert_id, run_id, card_id, profile_id, target_id, status,
                                 payload_json, delivery_attempt_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["alert_id"],
            run_id,
            card_id,
            profile_id,
            target_id,
            status,
            stable_json(payload),
            stable_json(delivery_attempt),
            event["created_at"],
        ),
    )
    conn.commit()
    return event
