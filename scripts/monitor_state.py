"""SQLite state for v0.5-alpha monitoring, inbox, alerts, and profile diffs.

The database is local private state under ``.tgcs/``.  It is allowed to keep
workflow notes and profile snapshots, but it must not become a second archive
of Telegram message bodies, credentials, bot tokens, or sessions.  Review cards
therefore keep source refs and extracted decision fields only.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from scripts.item_display import display_item_title, is_placeholder_value


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILENAME = "tgcs.db"
STATE_SCHEMA_VERSION = "monitor_state_v1"
REVIEW_CARD_SCHEMA_VERSION = "review_card_v1"
ALERT_EVENT_SCHEMA_VERSION = "alert_event_v1"
PROFILE_PATCH_SCHEMA_VERSION = "profile_patch_suggestion_v1"
DELIVERY_TARGET_SCHEMA_VERSION = "delivery_target_v1"
ALERT_SCHEDULE_MODES = {"work_hours", "all_day", "muted"}

PENDING_STATUS = "pending"
HANDLED_STATUSES = {"kept", "skipped", "false_positive", "follow_up"}
REVIEW_ACTIONS = {"keep", "skip", "false_positive", "follow_up"}
ACTION_TO_STATUS = {
    "keep": "kept",
    "skip": "skipped",
    "false_positive": "false_positive",
    "follow_up": "follow_up",
}
# Review-card item_json is a derived decision surface, not a transcript store.
# Keep provider/media text fields out even when OCR/STT is enabled upstream.
RAW_ITEM_FIELDS = {
    "text",
    "raw_text",
    "message",
    "message_text",
    "body",
    "content",
    "caption",
    "ocr_text",
    "media_text",
    "transcript",
    "transcription",
    "audio_transcript",
    "video_transcript",
}


class MonitorStateError(Exception):
    """Raised when monitor state cannot be loaded or updated safely."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profiles (
            profile_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            config_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profile_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            profile_path TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            profile_text TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            manifest_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_artifacts (
            artifact_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS review_cards (
            card_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            item_key TEXT NOT NULL,
            title TEXT NOT NULL,
            rating TEXT NOT NULL,
            decision_status TEXT NOT NULL,
            source_refs_json TEXT NOT NULL,
            item_json TEXT NOT NULL,
            status TEXT NOT NULL,
            first_run_id TEXT NOT NULL,
            last_run_id TEXT NOT NULL,
            report_path TEXT,
            dashboard_url TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            handled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback_events (
            event_id TEXT PRIMARY KEY,
            card_id TEXT,
            profile_id TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(card_id) REFERENCES review_cards(card_id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS profile_patch_suggestions (
            patch_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            card_id TEXT,
            note TEXT NOT NULL,
            status TEXT NOT NULL,
            diff_text TEXT NOT NULL,
            proposed_profile_text TEXT NOT NULL,
            base_profile_hash TEXT,
            created_at TEXT NOT NULL,
            applied_at TEXT,
            FOREIGN KEY(card_id) REFERENCES review_cards(card_id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS alert_events (
            alert_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            card_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            delivery_attempt_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
            FOREIGN KEY(card_id) REFERENCES review_cards(card_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS delivery_targets (
            target_id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    _ensure_column(conn, "profile_patch_suggestions", "base_profile_hash", "TEXT")
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (STATE_SCHEMA_VERSION, utc_now()),
    )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def upsert_profile(conn: sqlite3.Connection, config: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO profiles(profile_id, path, enabled, config_json, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(profile_id) DO UPDATE SET
            path = excluded.path,
            enabled = excluded.enabled,
            config_json = excluded.config_json,
            updated_at = excluded.updated_at
        """,
        (
            config["id"],
            str(config["path"]),
            1 if config.get("enabled", True) else 0,
            stable_json(config),
            now,
        ),
    )
    conn.commit()


def upsert_delivery_target(conn: sqlite3.Connection, target: dict[str, Any]) -> None:
    now = utc_now()
    sanitized = dict(target)
    sanitized.pop("token", None)
    sanitized.pop("bot_token", None)
    conn.execute(
        """
        INSERT INTO delivery_targets(target_id, target_type, enabled, config_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(target_id) DO UPDATE SET
            target_type = excluded.target_type,
            enabled = excluded.enabled,
            config_json = excluded.config_json,
            updated_at = excluded.updated_at
        """,
        (
            sanitized["id"],
            sanitized.get("type", "telegram_bot"),
            1 if sanitized.get("enabled", False) else 0,
            stable_json(sanitized),
            now,
            now,
        ),
    )
    conn.commit()


def _profile_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "profile_id": row["profile_id"],
        "path": row["path"],
        "enabled": bool(row["enabled"]),
        "config": parse_json(row["config_json"], {}),
        "updated_at": row["updated_at"],
    }


def update_profile_alert_mode(conn: sqlite3.Connection, *, profile_id: str, mode: str) -> dict[str, Any]:
    if mode not in ALERT_SCHEDULE_MODES:
        raise MonitorStateError(f"Unsupported alert schedule mode: {mode}")
    row = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    if not row:
        raise MonitorStateError(f"Profile is not registered: {profile_id}")
    config = parse_json(row["config_json"], {})
    if not isinstance(config, dict):
        config = {}
    # Dashboard changes are deliberately scoped to alert interruption policy.
    # The profile TOML remains the broad monitor contract; this local override
    # lets the dashboard mute or widen delivery without rewriting user files.
    config["alert_schedule_mode"] = mode
    now = utc_now()
    conn.execute(
        "UPDATE profiles SET config_json = ?, updated_at = ? WHERE profile_id = ?",
        (stable_json(config), now, profile_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    return _profile_from_row(updated)


def apply_profile_runtime_overrides(conn: sqlite3.Connection, profile: dict[str, Any]) -> dict[str, Any]:
    row = conn.execute("SELECT config_json FROM profiles WHERE profile_id = ?", (profile.get("id"),)).fetchone()
    if not row:
        return profile
    config = parse_json(row["config_json"], {})
    if not isinstance(config, dict):
        return profile
    mode = config.get("alert_schedule_mode")
    if mode not in ALERT_SCHEDULE_MODES:
        return profile
    merged = dict(profile)
    merged["alert_schedule_mode"] = mode
    return merged


def record_run(conn: sqlite3.Connection, manifest: dict[str, Any]) -> None:
    run_id = manifest["run_id"]
    now = utc_now()
    conn.execute(
        """
        INSERT OR REPLACE INTO runs(run_id, profile_id, status, started_at, completed_at, manifest_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM runs WHERE run_id = ?), ?))
        """,
        (
            run_id,
            manifest["profile_id"],
            manifest.get("status", "complete"),
            manifest.get("started_at") or now,
            manifest.get("completed_at"),
            stable_json(manifest),
            run_id,
            now,
        ),
    )
    for artifact in manifest.get("artifacts", []):
        if not isinstance(artifact, dict) or not artifact.get("path"):
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO run_artifacts(artifact_id, run_id, artifact_type, path, sha256, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.get("artifact_id") or f"{run_id}:{artifact.get('type')}:{artifact.get('path')}",
                run_id,
                artifact.get("type") or "artifact",
                artifact.get("path"),
                artifact.get("sha256"),
                now,
            ),
        )
    conn.commit()


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


def _sanitize_item(item: dict[str, Any]) -> dict[str, Any]:
    sanitized = {key: value for key, value in item.items() if key not in RAW_ITEM_FIELDS}
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
            "SELECT status, first_run_id, created_at, handled_at FROM review_cards WHERE card_id = ?",
            (card_id,),
        ).fetchone()
        status = existing["status"] if existing else PENDING_STATUS
        first_run_id = existing["first_run_id"] if existing else run_id
        created_at = existing["created_at"] if existing else now
        handled_at = existing["handled_at"] if existing else None
        conn.execute(
            """
            INSERT OR REPLACE INTO review_cards(
                card_id, profile_id, item_key, title, rating, decision_status,
                source_refs_json, item_json, status, first_run_id, last_run_id,
                report_path, dashboard_url, created_at, updated_at, handled_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _card_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = parse_json(row["item_json"], {})
    title = str(row["title"] or "").strip()
    derived_title = display_item_title(item, fallback=title or "Telegram signal", max_len=160)
    if derived_title and not is_placeholder_value(derived_title):
        title = derived_title
    elif is_placeholder_value(title):
        title = derived_title
    return {
        "schema_version": REVIEW_CARD_SCHEMA_VERSION,
        "card_id": row["card_id"],
        "profile_id": row["profile_id"],
        "item_key": row["item_key"],
        "title": title,
        "rating": row["rating"],
        "decision_status": row["decision_status"],
        "source_refs": parse_json(row["source_refs_json"], []),
        "item": item,
        "status": row["status"],
        "first_run_id": row["first_run_id"],
        "last_run_id": row["last_run_id"],
        "report_path": row["report_path"],
        "dashboard_url": row["dashboard_url"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "handled_at": row["handled_at"],
    }


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
        if card.get("status") in HANDLED_STATUSES:
            continue
        if (
            str(item.get("rating") or "").lower() == "high"
            and state.get("status") in {"new", "changed"}
            and _within_freshness_window(item, max_age, current_time)
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
    if action == "follow_up":
        note = " ".join(note.split())
        if not note:
            raise MonitorStateError("Follow-up note is required.")
    card = get_review_card(conn, card_id)
    now = utc_now()
    status = ACTION_TO_STATUS[action]
    conn.execute(
        "UPDATE review_cards SET status = ?, handled_at = ?, updated_at = ? WHERE card_id = ?",
        (status, now, now, card_id),
    )
    conn.execute(
        """
        INSERT INTO feedback_events(event_id, card_id, profile_id, action, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("feedback_" + uuid.uuid4().hex, card_id, card["profile_id"], action, note, now),
    )
    patch = None
    if action == "follow_up":
        patch = create_profile_patch_suggestion(
            conn,
            profile_id=card["profile_id"],
            card_id=card_id,
            note=note,
            profile_path=profile_path,
        )
    conn.commit()
    updated = get_review_card(conn, card_id)
    if patch:
        updated["profile_patch_suggestion"] = patch
    return updated


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


def feedback_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT f.action, c.rating, c.decision_status
        FROM feedback_events f
        LEFT JOIN review_cards c ON c.card_id = f.card_id
        WHERE f.action IN ('keep', 'skip', 'false_positive')
        """
    ).fetchall()
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
    return {
        "schema_version": "dashboard_feedback_summary_v1",
        "exportable_count": sum(by_action.values()),
        "by_action": by_action,
        "by_rating": by_rating,
        "by_decision_status": by_decision_status,
    }


def validation_summary(
    conn: sqlite3.Connection,
    *,
    days: int = 14,
    now: datetime | None = None,
) -> dict[str, Any]:
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
            "detail": "Run jobs-fast once in dry-run mode to begin the local validation window.",
            "command": "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
        }
    elif action_count == 0:
        next_action = {
            "label": "Review cards",
            "detail": "Mark keep, skip, false positive, or follow-up so the validation window has behavior evidence.",
            "command": "",
        }
    elif by_action.get("follow_up", 0) > 0:
        next_action = {
            "label": "Review profile diffs",
            "detail": "Follow-up feedback exists; review pending or applied profile diffs before the next run.",
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
            "detail": "Keep running jobs-fast and record concrete outcomes for kept opportunities.",
            "command": "tgcs schedule print --profile-id jobs-fast --interval-minutes 15",
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
        "keep_rate": (by_action.get("keep", 0) / action_count) if action_count else 0,
        "false_positive_rate": (by_action.get("false_positive", 0) / action_count) if action_count else 0,
        "next_action": next_action,
    }


def _append_follow_up_rule(profile_text: str, note: str) -> str:
    clean_note = " ".join(note.split())
    line = f"- {clean_note}" if clean_note else "- Follow up on similar future items."
    heading = "## Follow-up Preferences"
    if heading not in profile_text:
        suffix = "\n\n" if profile_text.endswith("\n") else "\n\n"
        return f"{profile_text}{suffix}{heading}\n{line}\n"
    lines = profile_text.splitlines()
    output: list[str] = []
    inserted = False
    in_section = False
    for raw in lines:
        if raw.strip() == heading:
            in_section = True
            output.append(raw)
            continue
        if in_section and raw.startswith("## "):
            output.append(line)
            inserted = True
            in_section = False
        output.append(raw)
    if in_section and not inserted:
        output.append(line)
    return "\n".join(output).rstrip() + "\n"


def create_profile_patch_suggestion(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    card_id: str | None,
    note: str,
    profile_path: Path | None,
) -> dict[str, Any]:
    if profile_path is None:
        row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
        if not row:
            raise MonitorStateError(f"Profile is not registered: {profile_id}")
        profile_path = Path(row["path"])
    if not profile_path.exists():
        raise MonitorStateError(f"Profile file not found: {profile_path}")
    current = profile_path.read_text(encoding="utf-8")
    base_profile_hash = sha256_text(current)
    proposed = _append_follow_up_rule(current, note)
    diff = "\n".join(
        difflib.unified_diff(
            current.splitlines(),
            proposed.splitlines(),
            fromfile=str(profile_path),
            tofile=str(profile_path),
            lineterm="",
        )
    )
    now = utc_now()
    patch = {
        "schema_version": PROFILE_PATCH_SCHEMA_VERSION,
        "patch_id": "patch_" + uuid.uuid4().hex,
        "profile_id": profile_id,
        "card_id": card_id,
        "note": note,
        "status": "pending",
        "diff_text": diff,
        "proposed_profile_text": proposed,
        "base_profile_hash": base_profile_hash,
        "created_at": now,
        "applied_at": None,
    }
    conn.execute(
        """
        INSERT INTO profile_patch_suggestions(
            patch_id, profile_id, card_id, note, status, diff_text,
            proposed_profile_text, base_profile_hash, created_at, applied_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patch["patch_id"],
            profile_id,
            card_id,
            note,
            "pending",
            diff,
            proposed,
            base_profile_hash,
            now,
            None,
        ),
    )
    return patch


def apply_profile_patch(conn: sqlite3.Connection, *, patch_id: str, profile_path: Path | None = None) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM profile_patch_suggestions WHERE patch_id = ?",
        (patch_id,),
    ).fetchone()
    if not row:
        raise MonitorStateError(f"Profile patch not found: {patch_id}")
    if row["status"] != "pending":
        raise MonitorStateError(f"Profile patch is not pending: {patch_id}")
    if profile_path is None:
        profile_row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (row["profile_id"],)).fetchone()
        if not profile_row:
            raise MonitorStateError(f"Profile is not registered: {row['profile_id']}")
        profile_path = Path(profile_row["path"])
    current = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    base_profile_hash = row["base_profile_hash"]
    if not base_profile_hash:
        raise MonitorStateError("Profile patch is missing its base hash; regenerate the profile diff.")
    if sha256_text(current) != base_profile_hash:
        raise MonitorStateError("Profile changed after patch was suggested; regenerate the profile diff.")
    snapshot_id = "snapshot_" + uuid.uuid4().hex
    now = utc_now()
    conn.execute(
        """
        INSERT INTO profile_snapshots(snapshot_id, profile_id, profile_path, profile_hash,
                                      profile_text, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (snapshot_id, row["profile_id"], str(profile_path), sha256_text(current), current, f"before {patch_id}", now),
    )
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(row["proposed_profile_text"], encoding="utf-8")
    conn.execute(
        "UPDATE profile_patch_suggestions SET status = ?, applied_at = ? WHERE patch_id = ?",
        ("applied", now, patch_id),
    )
    conn.commit()
    return {
        "patch_id": patch_id,
        "profile_id": row["profile_id"],
        "status": "applied",
        "snapshot_id": snapshot_id,
        "profile_path": str(profile_path),
        "applied_at": now,
    }


def revert_profile_patch(conn: sqlite3.Connection, *, patch_id: str, profile_path: Path | None = None) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM profile_patch_suggestions WHERE patch_id = ?",
        (patch_id,),
    ).fetchone()
    if not row:
        raise MonitorStateError(f"Profile patch not found: {patch_id}")
    if row["status"] != "applied":
        raise MonitorStateError(f"Profile patch is not applied: {patch_id}")
    snapshot = conn.execute(
        """
        SELECT * FROM profile_snapshots
        WHERE profile_id = ? AND reason = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (row["profile_id"], f"before {patch_id}"),
    ).fetchone()
    if not snapshot:
        raise MonitorStateError(f"Profile snapshot not found for patch: {patch_id}")
    if profile_path is None:
        profile_row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (row["profile_id"],)).fetchone()
        profile_path = Path(profile_row["path"] if profile_row else snapshot["profile_path"])
    current = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    # Do not silently erase manual profile edits made after an applied diff.
    # Revert is only automatic while the file still equals the patch proposal.
    if current != row["proposed_profile_text"]:
        raise MonitorStateError("Profile changed after patch was applied; manual revert required.")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(snapshot["profile_text"], encoding="utf-8")
    now = utc_now()
    conn.execute(
        "UPDATE profile_patch_suggestions SET status = ? WHERE patch_id = ?",
        ("reverted", patch_id),
    )
    conn.commit()
    return {
        "patch_id": patch_id,
        "profile_id": row["profile_id"],
        "status": "reverted",
        "snapshot_id": snapshot["snapshot_id"],
        "profile_path": str(profile_path),
        "reverted_at": now,
    }


def dashboard_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    profiles = [
        _profile_from_row(row)
        for row in conn.execute("SELECT * FROM profiles ORDER BY profile_id").fetchall()
    ]
    inbox = [
        _card_from_row(row)
        for row in conn.execute(
            "SELECT * FROM review_cards WHERE status = ? ORDER BY updated_at DESC LIMIT 200",
            (PENDING_STATUS,),
        ).fetchall()
    ]
    runs = [
        run_from_row(row)
        for row in conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 100").fetchall()
    ]
    delivery_targets = [
        {
            "schema_version": DELIVERY_TARGET_SCHEMA_VERSION,
            "target_id": row["target_id"],
            "type": row["target_type"],
            "enabled": bool(row["enabled"]),
            "config": parse_json(row["config_json"], {}),
            "updated_at": row["updated_at"],
        }
        for row in conn.execute("SELECT * FROM delivery_targets ORDER BY target_id").fetchall()
    ]
    patches = [
        {
            "schema_version": PROFILE_PATCH_SCHEMA_VERSION,
            "patch_id": row["patch_id"],
            "profile_id": row["profile_id"],
            "profile_path": row["profile_path"] or "",
            "card_id": row["card_id"],
            "card_title": patch_card_title(row),
            "note": row["note"],
            "status": row["status"],
            "diff_text": row["diff_text"],
            "base_profile_hash": row["base_profile_hash"] or "",
            "created_at": row["created_at"],
            "applied_at": row["applied_at"],
        }
        for row in conn.execute(
            """
            SELECT p.*, profiles.path AS profile_path, c.title AS card_title, c.item_json AS card_item_json
            FROM profile_patch_suggestions p
            LEFT JOIN profiles ON profiles.profile_id = p.profile_id
            LEFT JOIN review_cards c ON c.card_id = p.card_id
            ORDER BY p.created_at DESC
            LIMIT 100
            """
        ).fetchall()
    ]
    source_stats = source_value_stats(conn, runs=runs)
    setup_status = dashboard_setup_status(profiles=profiles, runs=runs, delivery_targets=delivery_targets)
    return {
        "schema_version": "dashboard_state_v1",
        "profiles": profiles,
        "inbox": inbox,
        "runs": runs,
        "delivery_targets": delivery_targets,
        "profile_patch_suggestions": patches,
        "source_stats": source_stats,
        "source_insights": source_value_insights_from_stats(source_stats),
        "feedback_summary": feedback_summary(conn),
        "validation_summary": validation_summary(conn),
        "setup_status": setup_status,
        "opportunity_summary": opportunity_summary(conn, runs),
    }


def run_from_row(row: sqlite3.Row) -> dict[str, Any]:
    manifest = parse_json(row["manifest_json"], {})
    return {
        "run_id": row["run_id"],
        "profile_id": row["profile_id"],
        "status": row["status"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "manifest": manifest,
        "quality": run_quality_summary(manifest),
    }


def patch_card_title(row: sqlite3.Row) -> str:
    item = parse_json(row["card_item_json"], {}) if "card_item_json" in row.keys() else {}
    fallback = str(row["card_title"] or "Review card") if "card_title" in row.keys() else "Review card"
    return display_item_title(item if isinstance(item, dict) else {}, fallback=fallback)


def run_quality_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    prefilter = manifest.get("prefilter") if isinstance(manifest.get("prefilter"), dict) else {}
    llm = manifest.get("llm") if isinstance(manifest.get("llm"), dict) else {}
    cache = llm.get("cache") if isinstance(llm.get("cache"), dict) else {}
    usage = llm.get("usage") if isinstance(llm.get("usage"), dict) else {}
    diagnostics = manifest.get("diagnostics") if isinstance(manifest.get("diagnostics"), list) else []
    diagnostic_counts = {"failure": 0, "warning": 0, "info": 0}
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "info").lower()
        if severity in diagnostic_counts:
            diagnostic_counts[severity] += 1
    raw_count = prefilter.get("raw_message_count")
    matched_count = prefilter.get("matched_count")
    prefilter_ratio = ""
    if raw_count is not None and matched_count is not None:
        prefilter_ratio = f"{matched_count}/{raw_count}"
    return {
        "prefilter": prefilter_ratio,
        "semantic_stage": prefilter.get("semantic_stage") or "",
        "llm_provider": llm.get("provider") or "",
        "cache_hit_rate": cache.get("hit_rate"),
        "latency_ms": llm.get("latency_ms"),
        "completion_tokens": usage.get("completion_tokens"),
        "diagnostic_count": len([item for item in diagnostics if isinstance(item, dict)]),
        "diagnostic_failure_count": diagnostic_counts["failure"],
        "diagnostic_warning_count": diagnostic_counts["warning"],
        "diagnostic_info_count": diagnostic_counts["info"],
        "top_diagnostic_code": next(
            (str(item.get("code") or "") for item in diagnostics if isinstance(item, dict)),
            "",
        ),
    }


def opportunity_summary(conn: sqlite3.Connection, runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {
            "schema_version": "dashboard_opportunity_summary_v1",
            "status": "no_runs",
            "run_id": "",
            "profile_id": "",
            "scanned_count": 0,
            "matched_count": 0,
            "review_card_count": 0,
            "alert_count": 0,
            "high_actionable_count": 0,
            "all_clear": False,
            "top_items": [],
            "next_action": {
                "label": "Run monitor",
                "detail": "Start with a dry-run monitor run.",
                "command": "tgcs monitor run --profile-id market-news --delivery-mode dry-run",
            },
        }

    latest = runs[0]
    manifest = latest.get("manifest") if isinstance(latest.get("manifest"), dict) else {}
    prefilter = manifest.get("prefilter") if isinstance(manifest.get("prefilter"), dict) else {}
    quality = latest.get("quality") if isinstance(latest.get("quality"), dict) else {}
    rows = conn.execute(
        "SELECT * FROM review_cards WHERE last_run_id = ? ORDER BY updated_at DESC",
        (latest["run_id"],),
    ).fetchall()
    cards = [_card_from_row(row) for row in rows]
    high_actionable = [
        card
        for card in cards
        if str(card.get("rating") or "").lower() == "high"
        and str(card.get("status") or "").lower() == PENDING_STATUS
        and str(card.get("decision_status") or "").lower() in {"new", "changed"}
    ]
    top_items = [
        opportunity_summary_item(card)
        for card in sorted(high_actionable, key=opportunity_rank_key, reverse=True)[:3]
    ]
    decision_counts = opportunity_decision_counts(cards)
    status = str(latest.get("status") or "")
    diagnostics = {
        "failure_count": int(quality.get("diagnostic_failure_count") or 0),
        "warning_count": int(quality.get("diagnostic_warning_count") or 0),
        "top_code": str(quality.get("top_diagnostic_code") or ""),
    }
    scanned_count = int(prefilter.get("raw_message_count") or 0)
    matched_count = int(prefilter.get("matched_count") or 0)
    if prefilter.get("semantic_stage") == "bypassed_scan_input":
        replay_total = scan_meta_total_messages(latest)
        if not scanned_count:
            scanned_count = replay_total
        if not matched_count:
            matched_count = replay_total
    all_clear = not high_actionable and status in {"complete", "prefilter_no_match"}
    return {
        "schema_version": "dashboard_opportunity_summary_v1",
        "status": status,
        "run_id": latest.get("run_id") or "",
        "profile_id": latest.get("profile_id") or "",
        "scanned_count": scanned_count,
        "matched_count": matched_count,
        "review_card_count": int(manifest.get("review_card_count") or len(cards)),
        "alert_count": int(manifest.get("alert_count") or 0),
        "high_actionable_count": len(high_actionable),
        "all_clear": all_clear,
        "top_items": top_items,
        "decision_counts": decision_counts,
        "diagnostics": diagnostics,
        "next_action": opportunity_next_action(
            profile_id=str(latest.get("profile_id") or ""),
            status=status,
            high_actionable_count=len(high_actionable),
            all_clear=all_clear,
            diagnostics=diagnostics,
        ),
    }


def opportunity_decision_counts(cards: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"new": 0, "changed": 0, "seen": 0, "recurring": 0, "expired": 0, "unknown": 0}
    for card in cards:
        status = str(card.get("decision_status") or "unknown").lower()
        if status not in counts:
            status = "unknown"
        counts[status] += 1
    return counts


def opportunity_next_action(
    *,
    profile_id: str,
    status: str,
    high_actionable_count: int,
    all_clear: bool,
    diagnostics: dict[str, Any],
) -> dict[str, str]:
    top_code = str(diagnostics.get("top_code") or "")
    doctor_profile = "jobs" if profile_id == "jobs-fast" else profile_id or "market-news"
    if int(diagnostics.get("failure_count") or 0) > 0 or status == "failed":
        detail = f"Top diagnostic: {top_code}" if top_code else "Open Runs for diagnostics before rerunning."
        return {
            "label": "Fix source access",
            "detail": detail,
            "command": f"tgcs doctor --profile {doctor_profile}",
        }
    if high_actionable_count > 0:
        noun = "card" if high_actionable_count == 1 else "cards"
        return {
            "label": "Review action signals",
            "detail": f"Review {high_actionable_count} high-priority new/changed {noun} in Inbox.",
            "command": "",
        }
    if all_clear:
        return {
            "label": "Keep cadence",
            "detail": "No immediate action; keep the monitor running on its review cadence.",
            "command": f"tgcs schedule print --profile-id {profile_id or 'market-news'} --interval-minutes 15",
        }
    return {
        "label": "Inspect run quality",
        "detail": "Open Runs to see why this scan produced no actionable cards.",
        "command": "",
    }


def opportunity_rank_key(card: dict[str, Any]) -> tuple[int, int, int, float]:
    rating_score = {"high": 3, "medium": 2, "low": 1}.get(
        str(card.get("rating") or "").lower(),
        0,
    )
    decision_score = {"new": 3, "changed": 2, "recurring": 1}.get(
        str(card.get("decision_status") or "").lower(),
        0,
    )
    status_score = 1 if card.get("status") == PENDING_STATUS else 0
    item = card.get("item") if isinstance(card.get("item"), dict) else {}
    freshness = item.get("monitor_freshness") if isinstance(item.get("monitor_freshness"), dict) else {}
    freshest = parse_iso_datetime(freshness.get("freshest_source_at"))
    freshness_score = freshest.timestamp() if freshest else 0.0
    return rating_score, decision_score, status_score, freshness_score


def opportunity_summary_item(card: dict[str, Any]) -> dict[str, Any]:
    item = card.get("item") if isinstance(card.get("item"), dict) else {}
    return {
        "card_id": card.get("card_id") or "",
        "title": card.get("title") or "Telegram signal",
        "rating": card.get("rating") or "unknown",
        "decision_status": card.get("decision_status") or "unknown",
        "status": card.get("status") or "unknown",
        "why": str(item.get("why") or "")[:240],
        "source_refs": card.get("source_refs") or [],
        "updated_at": card.get("updated_at") or "",
    }


def dashboard_setup_status(
    *,
    profiles: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    delivery_targets: list[dict[str, Any]],
) -> dict[str, Any]:
    active_profiles = [profile for profile in profiles if profile.get("enabled")]
    active_targets = [target for target in delivery_targets if target.get("enabled")]
    preferred = preferred_setup_profile(active_profiles)
    latest_source_attention = latest_run_needs_source_attention(runs[0]) if runs else False
    if not profiles:
        next_step = "tgcs monitor init-config"
        stage = "needs_profiles"
    elif not active_profiles:
        next_step = "Enable a profile in .tgcs/profiles.toml"
        stage = "needs_enabled_profile"
    elif not runs:
        next_step = f"tgcs monitor run --profile-id {preferred['profile_id']}"
        stage = "needs_first_run"
    elif latest_source_attention:
        profile = profile_for_run(active_profiles, runs[0])
        next_step = source_attention_next_step(profile)
        stage = "needs_source_access"
    elif not active_targets:
        next_step = "tgcs delivery test telegram-bot --delivery-mode dry-run"
        stage = "needs_delivery_target"
    else:
        next_step = "Review inbox"
        stage = "ready"
    return {
        "schema_version": "dashboard_setup_status_v1",
        "stage": stage,
        "next_step": next_step,
        "has_profiles": bool(profiles),
        "has_runs": bool(runs),
        "has_delivery_targets": bool(delivery_targets),
        "has_enabled_delivery_targets": bool(active_targets),
        "checks": setup_checklist(
            profiles=profiles,
            active_profiles=active_profiles,
            runs=runs,
            active_targets=active_targets,
            latest_source_attention=latest_source_attention,
        ),
    }


def setup_check(
    check_id: str,
    label: str,
    status: str,
    *,
    detail: str = "",
    command: str = "",
) -> dict[str, str]:
    payload = {"check_id": check_id, "label": label, "status": status}
    if detail:
        payload["detail"] = detail
    if command:
        payload["command"] = command
    return payload


def preferred_setup_profile(active_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    if not active_profiles:
        return {"profile_id": "market-news", "config": {"id": "market-news"}}
    return next(
        (profile for profile in active_profiles if profile.get("profile_id") == "jobs-fast"),
        active_profiles[0],
    )


def profile_for_run(active_profiles: list[dict[str, Any]], run: dict[str, Any]) -> dict[str, Any]:
    if not active_profiles:
        return preferred_setup_profile(active_profiles)
    return next(
        (
            item
            for item in active_profiles
            if item.get("profile_id") == run.get("profile_id")
        ),
        preferred_setup_profile(active_profiles),
    )


def setup_checklist(
    *,
    profiles: list[dict[str, Any]],
    active_profiles: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    active_targets: list[dict[str, Any]],
    latest_source_attention: bool,
) -> list[dict[str, str]]:
    preferred = preferred_setup_profile(active_profiles)
    first_run_command = f"tgcs monitor run --profile-id {preferred['profile_id']} --delivery-mode dry-run"
    source_command = source_attention_next_step(profile_for_run(active_profiles, runs[0])) if runs else ""

    if not profiles:
        profile_status = "active"
        profile_command = "tgcs monitor init-config"
        profile_detail = "Create local monitor profile config."
    elif not active_profiles:
        profile_status = "blocked"
        profile_command = "Enable a profile in .tgcs/profiles.toml"
        profile_detail = "At least one profile must be enabled before monitoring."
    else:
        profile_status = "done"
        profile_command = ""
        profile_detail = "Enabled profile config is registered."

    if latest_source_attention:
        source_status = "blocked"
        source_detail = "The latest run fetched no usable Telegram messages."
    elif runs:
        source_status = "done"
        source_detail = "The latest run reached the scan/report pipeline."
    elif active_profiles:
        source_status = "todo"
        source_detail = "Run doctor or import a real channel list before live monitoring."
    else:
        source_status = "todo"
        source_detail = "Configure profiles before source checks."

    if latest_source_attention:
        first_run_status = "blocked"
        first_run_detail = "Fix source access, then rerun the monitor."
    elif runs:
        first_run_status = "done"
        first_run_detail = "Run history exists in the local dashboard database."
    elif active_profiles:
        first_run_status = "active"
        first_run_detail = "Run once in dry-run mode before enabling live alerts."
    else:
        first_run_status = "todo"
        first_run_detail = "Profile setup is required first."

    delivery_status = "done" if active_targets else "todo"
    if not active_targets:
        delivery_detail = "Delivery is optional for reports, required for interrupt alerts."
        delivery_command = "tgcs delivery test telegram-bot --delivery-mode dry-run"
    else:
        delivery_detail = "At least one delivery target is enabled."
        delivery_command = ""

    return [
        setup_check(
            "profiles",
            "Profiles",
            profile_status,
            detail=profile_detail,
            command=profile_command,
        ),
        setup_check(
            "source_access",
            "Source access",
            source_status,
            detail=source_detail,
            command=source_command if latest_source_attention else "",
        ),
        setup_check(
            "first_run",
            "First monitor run",
            first_run_status,
            detail=first_run_detail,
            command=source_command if latest_source_attention else first_run_command,
        ),
        setup_check(
            "delivery",
            "Alert delivery",
            delivery_status,
            detail=delivery_detail,
            command=delivery_command,
        ),
    ]


def latest_run_needs_source_attention(run: dict[str, Any]) -> bool:
    if str(run.get("status") or "").lower() not in {"failed", "error"}:
        return False
    quality = run.get("quality") if isinstance(run.get("quality"), dict) else {}
    source_failure_codes = {"channel_failures", "no_messages_fetched"}
    if str(quality.get("semantic_stage") or "") == "scan_failed":
        return True
    return str(quality.get("top_diagnostic_code") or "") in source_failure_codes


def source_attention_next_step(profile: dict[str, Any]) -> str:
    config = profile.get("config") if isinstance(profile.get("config"), dict) else {}
    profile_id = str(profile.get("profile_id") or config.get("id") or "market-news")
    topics = [
        str(topic).strip()
        for topic in (config.get("source_topics") or config.get("topics") or [])
        if str(topic).strip()
    ]
    if not topics and profile_id == "jobs-fast":
        topics = ["jobs"]
    topic_args = " ".join(f"--topic {topic}" for topic in topics)
    list_name = "jobs.txt" if "jobs" in topics else "channels.txt"
    command = f"tgcs sources import channel_lists/{list_name}"
    if topic_args:
        command = f"{command} {topic_args}"
    return f"{command}; then tgcs monitor run --profile-id {profile_id} --delivery-mode dry-run"


def source_value_stats(conn: sqlite3.Connection, runs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    alert_rows = conn.execute("SELECT card_id, COUNT(*) AS count FROM alert_events GROUP BY card_id").fetchall()
    alerts_by_card = {row["card_id"]: int(row["count"] or 0) for row in alert_rows}
    stats: dict[str, dict[str, Any]] = {}
    run_list = runs or []
    latest_run_id = str(run_list[0].get("run_id") or "") if run_list else ""
    for channel, scan_stat in latest_source_scan_stats(run_list).items():
        item = stats.setdefault(channel, empty_source_stat(channel))
        item.update(scan_stat)
    rows = conn.execute("SELECT card_id, rating, status, source_refs_json, last_run_id FROM review_cards").fetchall()
    for row in rows:
        refs = parse_json(row["source_refs_json"], [])
        channels = sorted({str(ref.get("channel") or "").strip() for ref in refs if isinstance(ref, dict)})
        rating = str(row["rating"] or "unknown").lower()
        status = str(row["status"] or "unknown").lower()
        is_latest = bool(latest_run_id and row["last_run_id"] == latest_run_id)
        for channel in [item for item in channels if item]:
            item = stats.setdefault(channel, empty_source_stat(channel))
            item["card_count"] += 1
            if is_latest:
                item["latest_card_count"] += 1
            if rating == "high":
                item["high_count"] += 1
                if is_latest:
                    item["latest_high_count"] += 1
            elif rating == "medium":
                item["medium_count"] += 1
            elif rating == "low":
                item["low_count"] += 1
            if status == PENDING_STATUS:
                item["pending_count"] += 1
            else:
                item["handled_count"] += 1
            if status == "false_positive":
                item["false_positive_count"] += 1
            item["alert_count"] += alerts_by_card.get(row["card_id"], 0)
    for item in stats.values():
        total = int(item["card_count"] or 0)
        item["high_rate"] = round(int(item["high_count"] or 0) / total, 3) if total else 0.0
        kept_count = int(item.get("kept_count") or 0)
        latest_total = int(item.get("latest_card_count") or 0)
        item["card_yield_rate"] = round(latest_total / kept_count, 3) if kept_count else 0.0
    return sorted(
        stats.values(),
        key=lambda item: (
            -int(item["high_count"] or 0),
            -float(item["high_rate"] or 0),
            -int(item["card_count"] or 0),
            -int(item.get("kept_count") or 0),
            str(item["channel"]),
        ),
    )


def empty_source_stat(channel: str) -> dict[str, Any]:
    return {
        "channel": channel,
        "card_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "pending_count": 0,
        "handled_count": 0,
        "false_positive_count": 0,
        "alert_count": 0,
        "high_rate": 0.0,
        "latest_card_count": 0,
        "latest_high_count": 0,
        "raw_count": 0,
        "kept_count": 0,
        "scan_keep_rate": 0.0,
        "card_yield_rate": 0.0,
        "latest_run_id": "",
        "scan_failure": False,
        "scan_incomplete": False,
    }


def latest_source_scan_stats(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not runs:
        return {}
    latest = runs[0]
    payload = scan_meta_payload(latest)
    source_health = payload.get("source_health") if isinstance(payload.get("source_health"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for row in source_health:
        if not isinstance(row, dict):
            continue
        channel = str(row.get("channel") or row.get("username") or row.get("label") or "").strip()
        if not channel:
            continue
        raw_count = non_negative_int(row.get("raw_count"))
        kept_count = non_negative_int(row.get("kept_count"))
        result[channel] = {
            "raw_count": raw_count,
            "kept_count": kept_count,
            "scan_keep_rate": round(kept_count / raw_count, 3) if raw_count else 0.0,
            "latest_run_id": str(latest.get("run_id") or ""),
            "scan_failure": bool(row.get("failure")),
            "scan_incomplete": bool(row.get("incomplete")),
        }
    return result


def scan_meta_payload(run: dict[str, Any]) -> dict[str, Any]:
    manifest = run.get("manifest") if isinstance(run.get("manifest"), dict) else {}
    artifact = scan_meta_artifact(manifest)
    return load_scan_meta_counts(artifact.get("path")) if artifact else {}


def scan_meta_artifact(manifest: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in manifest.get("artifacts", [])
            if isinstance(item, dict)
            and (item.get("type") == "scan_meta" or str(item.get("artifact_id") or "").startswith("scan_meta:"))
            and item.get("path")
        ),
        None,
    )


def scan_meta_total_messages(run: dict[str, Any]) -> int:
    return non_negative_int(scan_meta_payload(run).get("total_messages_collected"))


def load_scan_meta_counts(path_value: object) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value.strip():
        return {}
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    # scan.meta.json contains source-level counters, not Telegram message bodies.
    # Keep this helper intentionally narrow so the dashboard does not become a
    # second raw-message surface.
    return {
        "source_health": payload.get("source_health"),
        "total_messages_collected": payload.get("total_messages_collected"),
    }


def non_negative_int(value: object) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def source_value_insights(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return source_value_insights_from_stats(source_value_stats(conn))


def source_value_insights_from_stats(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    for item in stats:
        channel = str(item["channel"])
        card_count = int(item["card_count"] or 0)
        high_count = int(item["high_count"] or 0)
        medium_count = int(item["medium_count"] or 0)
        false_positive_count = int(item["false_positive_count"] or 0)
        alert_count = int(item["alert_count"] or 0)
        high_rate = float(item["high_rate"] or 0)
        kept_count = int(item.get("kept_count") or 0)
        latest_card_count = int(item.get("latest_card_count") or 0)
        if item.get("scan_failure"):
            insights.append(
                {
                    "kind": "watch",
                    "channel": channel,
                    "label": "Access",
                    "reason": "Latest scan failed; check membership, handle, or Telegram session before judging value.",
                    "priority": 80,
                    "stats": item,
                }
            )
            continue
        if high_count >= 2:
            insights.append(
                {
                    "kind": "promote",
                    "channel": channel,
                    "label": "Promote",
                    "reason": f"{high_count} high signals across {card_count} cards.",
                    "priority": 90 + high_count + alert_count,
                    "stats": item,
                }
            )
            continue
        if high_count == 1:
            insights.append(
                {
                    "kind": "observe",
                    "channel": channel,
                    "label": "Observe",
                    "reason": "1 high signal so far; keep observing before promote.",
                    "priority": 60 + alert_count,
                    "stats": item,
                }
            )
            continue
        if false_positive_count >= 2 and high_count == 0:
            insights.append(
                {
                    "kind": "prune",
                    "channel": channel,
                    "label": "Prune",
                    "reason": f"{false_positive_count} false positives and no high signals.",
                    "priority": 70 + false_positive_count,
                    "stats": item,
                }
            )
            continue
        if kept_count >= 5 and latest_card_count == 0 and high_count == 0:
            insights.append(
                {
                    "kind": "watch",
                    "channel": channel,
                    "label": "Watch",
                    "reason": f"{kept_count} fresh messages in the latest scan, but no review cards.",
                    "priority": 45 + min(kept_count, 20),
                    "stats": item,
                }
            )
            continue
        if card_count >= 2 and high_rate < 0.5 and medium_count > 0:
            insights.append(
                {
                    "kind": "watch",
                    "channel": channel,
                    "label": "Watch",
                    "reason": f"{medium_count} medium signals, but high-rate is {round(high_rate * 100)}%.",
                    "priority": 50 + medium_count,
                    "stats": item,
                }
            )
    return sorted(insights, key=lambda item: (-int(item["priority"]), str(item["channel"])))[:12]
