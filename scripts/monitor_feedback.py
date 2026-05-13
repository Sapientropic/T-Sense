"""Feedback export, profile suggestion, and validation summary helpers."""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any

from scripts.item_display import display_item_title
from scripts.monitor_common import (
    DEFAULT_FEEDBACK_EXPORT_PATH,
    MonitorStateError,
    PENDING_STATUS,
    parse_iso_datetime,
    parse_json,
    title_case_label,
    utc_now,
)
from scripts.profile_patches import create_profile_patch_suggestion


def clear_feedback_decisions(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT DISTINCT card_id FROM feedback_events WHERE card_id IS NOT NULL").fetchall()
    card_ids = [str(row["card_id"]) for row in rows if row["card_id"]]
    cleared_count = len(card_ids)
    now = utc_now()
    conn.execute("DELETE FROM feedback_events")
    if card_ids:
        placeholders = ",".join("?" for _ in card_ids)
        conn.execute(
            f"UPDATE review_cards SET status = ?, handled_at = NULL, updated_at = ? WHERE card_id IN ({placeholders})",
            [PENDING_STATUS, now, *card_ids],
        )
    conn.commit()
    return {
        "schema_version": "feedback_clear_result_v1",
        "cleared_count": cleared_count,
    }


def export_feedback_entries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT f.created_at, f.profile_id, f.action, c.title, c.rating, c.decision_status, c.source_refs_json, c.item_json
        FROM feedback_events f
        LEFT JOIN review_cards c ON c.card_id = f.card_id
        WHERE f.action IN ('keep', 'skip', 'false_positive')
        ORDER BY f.created_at ASC, f.event_id ASC
        """
    ).fetchall()
    entries: list[dict[str, Any]] = []
    for row in rows:
        item = parse_json(row["item_json"], {})
        item_title = display_item_title(item, fallback=row["title"] or "", max_len=160)
        state = item.get("decision_state") if isinstance(item, dict) and isinstance(item.get("decision_state"), dict) else {}
        entries.append(
            {
                "schema_version": "v1",
                "created_at": row["created_at"],
                "report_id": "",
                "profile_label": row["profile_id"],
                "source_message_refs": parse_json(row["source_refs_json"], []),
                "feedback": row["action"],
                "rating": row["rating"] or (item.get("rating") if isinstance(item, dict) else "") or "unknown",
                "decision_status": row["decision_status"] or state.get("status") or "unknown",
                # Dashboard notes may contain private workflow context. The
                # decision-memory import path only needs action + item identity,
                # so keep note bodies out of exported reusable feedback by default.
                "note": "",
                "item_title": item_title,
            }
        )
    return entries


def _feedback_titles_by_action(rows: list[sqlite3.Row], *, limit_per_action: int) -> dict[str, list[str]]:
    titles: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        action = str(row["action"] or "")
        if action not in {"keep", "skip", "false_positive"}:
            continue
        if len(titles.get(action, [])) >= limit_per_action:
            continue
        item = parse_json(row["item_json"], {})
        title = display_item_title(item if isinstance(item, dict) else {}, fallback=row["title"] or "Review card", max_len=72)
        title = " ".join(str(title or "").split())
        if not title:
            continue
        key = (action, title.casefold())
        if key in seen:
            continue
        seen.add(key)
        titles.setdefault(action, []).append(title)
    return titles


def _feedback_profile_suggestion_note(rows: list[sqlite3.Row]) -> str:
    titles = _feedback_titles_by_action(rows, limit_per_action=1)
    if not titles:
        return ""
    return "Desk feedback tuning: Analyze the recent Keep/Skip/Wrong Match feedback. Extract the generalized matching patterns, industry preferences, and explicit exclusions. Do not list specific card titles. Write broad, reusable rules."


def _existing_profile_patch_for_note(conn: sqlite3.Connection, *, profile_id: str, note: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT patch_id, status
        FROM profile_patch_suggestions
        WHERE profile_id = ?
          AND note = ?
          AND status IN ('pending', 'applied')
        ORDER BY created_at DESC, patch_id DESC
        LIMIT 1
        """,
        (profile_id, note),
    ).fetchone()


def create_feedback_profile_patch_suggestions(
    conn: sqlite3.Connection,
    *,
    limit_per_profile: int = 24,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT f.event_id, f.card_id, f.profile_id, f.action, c.title, c.item_json
        FROM feedback_events f
        LEFT JOIN review_cards c ON c.card_id = f.card_id
        WHERE f.action IN ('keep', 'skip', 'false_positive')
        ORDER BY f.profile_id ASC, f.created_at ASC, f.event_id ASC
        """
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        profile_id = str(row["profile_id"] or "")
        if not profile_id:
            continue
        bucket = grouped.setdefault(profile_id, [])
        if len(bucket) < limit_per_profile:
            bucket.append(row)

    created: list[dict[str, str]] = []
    existing: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for profile_id, profile_rows in grouped.items():
        note = _feedback_profile_suggestion_note(profile_rows)
        if not note:
            skipped.append({"profile_id": profile_id, "reason": "no_feedback_titles"})
            continue
        existing_row = _existing_profile_patch_for_note(conn, profile_id=profile_id, note=note)
        if existing_row:
            existing.append(
                {
                    "profile_id": profile_id,
                    "patch_id": str(existing_row["patch_id"] or ""),
                    "status": str(existing_row["status"] or ""),
                }
            )
            continue
        try:
            patch = create_profile_patch_suggestion(
                conn,
                profile_id=profile_id,
                card_id=str(profile_rows[0]["card_id"] or "") or None,
                note=note,
                profile_path=None,
            )
        except MonitorStateError as exc:
            skipped.append({"profile_id": profile_id, "reason": str(exc)})
            continue
        created.append({"profile_id": profile_id, "patch_id": str(patch["patch_id"])})
    conn.commit()

    created_count = len(created)
    existing_count = len(existing)
    skipped_count = len(skipped)
    if created_count:
        detail = f"Created {created_count} profile draft{'s' if created_count != 1 else ''} from confirmed feedback."
    elif existing_count:
        detail = "Profile drafts already exist for the current confirmed feedback."
    elif skipped_count:
        detail = "No profile drafts were created; check profile files before applying feedback."
    else:
        detail = "No confirmed feedback decisions are ready for profile tuning."
    return {
        "schema_version": "feedback_profile_suggestions_result_v1",
        "created_count": created_count,
        "existing_count": existing_count,
        "skipped_count": skipped_count,
        "patch_ids": [item["patch_id"] for item in [*created, *existing] if item.get("patch_id")],
        "profile_ids": sorted(grouped),
        "detail": detail,
        "created": created,
        "existing": existing,
        "skipped": skipped,
        "generated_at": utc_now(),
    }


def record_feedback_export(
    conn: sqlite3.Connection,
    *,
    output_path: str,
    feedback_count: int,
    exported_at: str | None = None,
) -> dict[str, Any]:
    exported_at = exported_at or utc_now()
    row = {
        "schema_version": "feedback_export_record_v1",
        "export_id": "feedback_export_" + uuid.uuid4().hex,
        "output_path": output_path,
        "feedback_count": int(feedback_count),
        "exported_at": exported_at,
    }
    conn.execute(
        """
        INSERT INTO feedback_exports(export_id, output_path, feedback_count, exported_at)
        VALUES (?, ?, ?, ?)
        """,
        (row["export_id"], output_path, int(feedback_count), exported_at),
    )
    conn.commit()
    return row


def latest_feedback_export(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT output_path, feedback_count, exported_at
        FROM feedback_exports
        ORDER BY exported_at DESC, export_id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    return {
        "output_path": row["output_path"] or "",
        "feedback_count": int(row["feedback_count"] or 0),
        "exported_at": row["exported_at"] or "",
    }


def feedback_next_action(exportable_count: int, follow_up_count: int, patch_counts: dict[str, int]) -> dict[str, str]:
    pending_diffs = patch_counts.get("pending", 0)
    applied_diffs = patch_counts.get("applied", 0)
    if pending_diffs:
        return {
            "label": "Apply profile drafts",
            "detail": "Profile drafts are ready; review or apply them before the next tuning pass.",
            "target_tab": "profiles",
            "action_id": "review_preference_drafts",
        }
    if exportable_count:
        return {
            "label": "Generate profile suggestions",
            "detail": "Turn confirmed review decisions into local profile drafts. JSON export is only for CLI fallback.",
            "target_tab": "settings",
            "action_id": "feedback_profile_suggestions",
        }
    if follow_up_count and applied_diffs:
        return {
            "label": "Run with tuned preferences",
            "detail": "Applied preference drafts are in place; run the profile again and watch false positives.",
            "target_tab": "actions",
            "action_id": "monitor_jobs_dry_run",
        }
    return {
        "label": "Collect feedback",
        "detail": "Mark keep, skip, false positive, or draft a preference change after reviewing cards.",
        "target_tab": "inbox",
        "action_id": "review_cards",
    }


def recent_feedback_impacts(conn: sqlite3.Connection, *, limit: int = 6) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            f.event_id,
            f.card_id,
            f.created_at,
            f.profile_id,
            f.action,
            c.title,
            c.rating,
            c.decision_status,
            c.item_json,
            p.patch_id,
            p.status AS patch_status
        FROM feedback_events f
        LEFT JOIN review_cards c ON c.card_id = f.card_id
        LEFT JOIN profile_patch_suggestions p ON p.card_id = f.card_id AND f.action = 'follow_up'
        ORDER BY f.created_at DESC, f.event_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    impacts: list[dict[str, Any]] = []
    for row in rows:
        item = parse_json(row["item_json"], {})
        title = display_item_title(item if isinstance(item, dict) else {}, fallback=row["title"] or "", max_len=120)
        decision_state = item.get("decision_state") if isinstance(item, dict) and isinstance(item.get("decision_state"), dict) else {}
        action = str(row["action"] or "unknown")
        impact = {
            "created_at": row["created_at"],
            "card_id": row["card_id"] or "",
            "profile_id": row["profile_id"],
            "action": action,
            "item_title": title,
            "rating": row["rating"] or (item.get("rating") if isinstance(item, dict) else "") or "unknown",
            "decision_status": row["decision_status"] or decision_state.get("status") or "unknown",
        }
        if action in {"keep", "skip", "false_positive"}:
            impact.update(
                {
                    "impact_type": "profile_tuning_source",
                    "impact_status": "ready",
                    "impact_label": "Ready for profile draft",
                    "impact_detail": "Generate profile suggestions so future reports learn from this choice.",
                }
            )
        elif action == "follow_up":
            patch_status = str(row["patch_status"] or "missing")
            impact.update(
                {
                    "impact_type": "profile_diff",
                    "impact_status": patch_status,
                    "impact_label": {
                        "pending": "Preference draft pending",
                        "applied": "Preference draft applied",
                        "reverted": "Preference draft reverted",
                    }.get(patch_status, "Preference draft missing"),
                    "impact_detail": {
                        "pending": "Review and apply or leave the generated preference draft in Learning.",
                        "applied": "This feedback has already changed the local profile.",
                        "reverted": "This feedback changed the profile and was later reverted.",
                    }.get(patch_status, "Regenerate the follow-up draft if this feedback still matters."),
                    "patch_id": row["patch_id"] or "",
                }
            )
        else:
            impact.update(
                {
                    "impact_type": "unknown",
                    "impact_status": "unknown",
                    "impact_label": "Unknown feedback",
                    "impact_detail": "This feedback action is not part of the current dashboard learning loop.",
                }
            )
        impacts.append(impact)
    return impacts


def feedback_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT f.action, c.rating, c.decision_status
        FROM feedback_events f
        LEFT JOIN review_cards c ON c.card_id = f.card_id
        WHERE f.action IN ('keep', 'skip', 'false_positive')
        """
    ).fetchall()
    follow_up_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM feedback_events WHERE action = 'follow_up'",
        ).fetchone()[0]
        or 0
    )
    patch_rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM profile_patch_suggestions
        GROUP BY status
        """
    ).fetchall()
    patch_counts = {str(row["status"] or "unknown"): int(row["count"] or 0) for row in patch_rows}
    by_action: dict[str, int] = {}
    by_rating: dict[str, int] = {}
    by_decision_status: dict[str, int] = {}
    for row in rows:
        action = str(row["action"] or "unknown")
        rating = str(row["rating"] or "unknown").lower()
        decision_status = str(row["decision_status"] or "unknown").lower()
        by_action[action] = by_action.get(action, 0) + 1
        by_rating[rating] = by_rating.get(rating, 0) + 1
        by_decision_status[decision_status] = by_decision_status.get(decision_status, 0) + 1
    exportable_count = sum(by_action.values())
    latest_export = latest_feedback_export(conn)
    last_export_path = (
        dashboard_feedback_export_display_path(latest_export["output_path"])
        if latest_export
        else DEFAULT_FEEDBACK_EXPORT_PATH
    )
    if latest_export and latest_export.get("exported_at"):
        changed_since_last_export = bool(
            conn.execute(
                """
                SELECT 1
                FROM feedback_events
                WHERE action IN ('keep', 'skip', 'false_positive')
                  AND created_at > ?
                LIMIT 1
                """,
                (latest_export["exported_at"],),
            ).fetchone()
        )
    else:
        changed_since_last_export = exportable_count > 0
    return {
        "schema_version": "dashboard_feedback_summary_v2",
        "current_decision_count": exportable_count + follow_up_count,
        "exportable_count": exportable_count,
        "changed_since_last_export": changed_since_last_export,
        "last_export_path": last_export_path,
        "non_exportable_follow_up_count": follow_up_count,
        "profile_diff_count": sum(patch_counts.values()),
        "pending_profile_diff_count": patch_counts.get("pending", 0),
        "applied_profile_diff_count": patch_counts.get("applied", 0),
        "reverted_profile_diff_count": patch_counts.get("reverted", 0),
        "next_action": feedback_next_action(exportable_count, follow_up_count, patch_counts),
        "recent_impacts": recent_feedback_impacts(conn),
        "export_scope_note": (
            "keep/skip/false_positive export to decision memory; "
            "follow_up becomes preference drafts for review."
        ),
        "by_action": by_action,
        "by_rating": by_rating,
        "by_decision_status": by_decision_status,
    }


def dashboard_feedback_export_display_path(path: object) -> str:
    cleaned = str(path or "").strip().replace("\\", "/")
    if (
        not cleaned
        or cleaned.startswith("/")
        or re.match(r"^[A-Za-z]:", cleaned)
        or re.match(r"^[a-z][a-z0-9+.-]*://", cleaned, flags=re.IGNORECASE)
        or re.search(r"[\x00-\x1f\x7f]", cleaned)
    ):
        return DEFAULT_FEEDBACK_EXPORT_PATH
    parts = PurePosixPath(cleaned).parts
    if not parts or ".." in parts:
        return DEFAULT_FEEDBACK_EXPORT_PATH
    return cleaned


def validation_summary(
    conn: sqlite3.Connection,
    *,
    days: int = 14,
    now: datetime | None = None,
) -> dict[str, Any]:
    default_profile_id = "jobs-fast"
    default_profile_label = title_case_label(default_profile_id)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    since = current - timedelta(days=days)

    def in_window(value: object) -> bool:
        parsed = parse_iso_datetime(value)
        return bool(parsed and parsed >= since)

    run_rows = conn.execute("SELECT started_at FROM runs").fetchall()
    card_rows = conn.execute("SELECT rating, status, created_at FROM review_cards").fetchall()
    feedback_rows = conn.execute("SELECT action, created_at FROM feedback_events").fetchall()

    recent_cards = [row for row in card_rows if in_window(row["created_at"])]
    recent_feedback = [row for row in feedback_rows if in_window(row["created_at"])]
    by_action: dict[str, int] = {}
    for row in recent_feedback:
        action = str(row["action"] or "unknown")
        by_action[action] = by_action.get(action, 0) + 1
    by_action = {key: by_action[key] for key in sorted(by_action)}
    action_count = sum(by_action.values())
    runs_count = len([row for row in run_rows if in_window(row["started_at"])])
    high_card_count = len([row for row in recent_cards if str(row["rating"] or "").lower() == "high"])
    pending_count = len([row for row in recent_cards if str(row["status"] or "").lower() == PENDING_STATUS])
    if runs_count == 0:
        next_action = {
            "label": "Start validation",
            "detail": f"Run {default_profile_label} once in dry-run mode to begin the local validation window.",
            "command": f"tgcs monitor run --profile-id {default_profile_id} --delivery-mode dry-run",
        }
    elif action_count == 0:
        next_action = {
            "label": "Review cards",
            "detail": "Mark keep, skip, false positive, or follow-up so the validation window has behavior evidence.",
            "command": "",
        }
    elif by_action.get("follow_up", 0) > 0:
        next_action = {
            "label": "Review preference drafts",
            "detail": "Follow-up feedback exists; review pending or applied preference drafts before the next run.",
            "command": "",
        }
    elif by_action.get("false_positive", 0) > 0:
        next_action = {
            "label": "Tune false positives",
            "detail": "False positives were marked in this window; consider a follow-up note for recurring patterns.",
            "command": "",
        }
    else:
        next_action = {
            "label": "Keep validation cadence",
            "detail": f"Keep running {default_profile_label} and record concrete outcomes for kept opportunities.",
            "command": f"tgcs schedule print --profile-id {default_profile_id} --interval-minutes 15",
        }
    return {
        "schema_version": "dashboard_validation_summary_v1",
        "window_days": days,
        "since": since.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "runs_count": runs_count,
        "card_count": len(recent_cards),
        "high_card_count": high_card_count,
        "pending_count": pending_count,
        "action_count": action_count,
        "by_action": by_action,
        "triage_rate": (action_count / len(recent_cards)) if recent_cards else 0,
        "keep_rate": (by_action.get("keep", 0) / action_count) if action_count else 0,
        "false_positive_rate": (by_action.get("false_positive", 0) / action_count) if action_count else 0,
        "next_action": next_action,
    }
