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
import re
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from scripts.item_display import display_item_title, is_placeholder_value
from scripts.profile_schema import parse_profile_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILENAME = "tgcs.db"
STATE_SCHEMA_VERSION = "monitor_state_v1"
REVIEW_CARD_SCHEMA_VERSION = "review_card_v1"
ALERT_EVENT_SCHEMA_VERSION = "alert_event_v1"
PROFILE_PATCH_SCHEMA_VERSION = "profile_patch_suggestion_v1"
DELIVERY_TARGET_SCHEMA_VERSION = "delivery_target_v1"
ALERT_SCHEDULE_MODES = {"work_hours", "all_day", "muted"}
PROFILE_RUNTIME_SETTING_LIMITS = {
    "scan_window_hours": (1, 168),
    "semantic_max_messages": (1, 500),
}

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
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
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

        CREATE TABLE IF NOT EXISTS feedback_exports (
            export_id TEXT PRIMARY KEY,
            output_path TEXT NOT NULL,
            feedback_count INTEGER NOT NULL,
            exported_at TEXT NOT NULL
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
        "display_path": display_profile_path(str(row["path"] or "")),
        "enabled": bool(row["enabled"]),
        "config": parse_json(row["config_json"], {}),
        "updated_at": row["updated_at"],
    }


def dashboard_profile_projection(profile: dict[str, Any], *, report_title: str = "") -> dict[str, Any]:
    config = profile.get("config") if isinstance(profile.get("config"), dict) else {}
    profile_path = str(profile.get("path") or "")
    source_topics = config.get("source_topics")
    if not isinstance(source_topics, list):
        source_topics = []
    delivery_targets = config.get("delivery_targets")
    if not isinstance(delivery_targets, list):
        delivery_targets = []
    alert_schedule_mode = config.get("alert_schedule_mode")
    return {
        "schema_version": "dashboard_profile_v1",
        "profile_id": profile["profile_id"],
        "display_name": profile_display_label(str(profile["profile_id"]), profile_path=profile_path, report_title=report_title),
        "report_display_name": report_title or f"{profile_display_label(str(profile['profile_id']), profile_path=profile_path)} Report",
        "display_path": profile.get("display_path") or display_profile_path(profile_path),
        "enabled": bool(profile.get("enabled")),
        "alert_schedule_mode": alert_schedule_mode if isinstance(alert_schedule_mode, str) else "work_hours",
        "source_topics": [str(topic) for topic in source_topics if str(topic).strip()],
        "scan_window_hours": non_negative_int(config.get("scan_window_hours")),
        "semantic_max_messages": non_negative_int(config.get("semantic_max_messages")),
        "delivery_target_count": len(delivery_targets),
        "matching_profile": profile_matching_summary(profile_path),
        "updated_at": profile.get("updated_at"),
    }


def profile_matching_summary(profile_path: str) -> dict[str, Any]:
    """Project profile Markdown into app-readable matching rules.

    The dashboard is the human surface, so it should expose the criteria the
    scanner is actually using without forcing users into raw Markdown or YAML.
    Keep this parser deliberately conservative: unknown sections remain in the
    source file, while the UI shows only short bullets from stable profile
    sections that influence matching.
    """
    path = Path(profile_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"schema_version": "profile_matching_profile_v1", "sections": [], "learned_preferences": []}
    sections = _markdown_sections(text)
    basics = _clean_markdown_items(sections.get("Basic Info", []), limit=6)
    search_rules = _clean_markdown_items(sections.get("Search Rules", []), limit=7)
    report_preferences = _clean_markdown_items(sections.get("Report Preferences", []), limit=5)
    learned = _clean_markdown_items(sections.get("Follow-up Preferences", []), limit=12)
    output_sections: list[dict[str, Any]] = []
    for key, label, items in [
        ("basics", "Match profile", basics),
        ("rules", "How cards are judged", search_rules),
        ("learned", "Learned preferences", learned),
        ("report", "Report preferences", report_preferences),
    ]:
        if items:
            output_sections.append({"key": key, "label": label, "items": items})
    return {
        "schema_version": "profile_matching_profile_v1",
        "summary": basics[0] if basics else "",
        "sections": output_sections,
        "learned_preferences": learned,
        "editable_text": "\n".join(f"- {item}" for item in learned),
    }


def _markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(line)
    return sections


def _clean_markdown_items(lines: list[str], *, limit: int) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("mode:", "top_level_key:", "dedup_fields:", "fields:", "system_prompt:", "report_title:", "section_", "stats_label:", "output_filename:", "profile_section_title:", "methodology_label:")):
            continue
        line = re.sub(r"^\d+\.\s+", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\+\s*", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = line.replace("`", "").strip()
        if not line or line in {"|", "fields:"}:
            continue
        normalized = " ".join(line.split())
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        items.append(normalized)
        if len(items) >= limit:
            break
    return items


def display_profile_path(profile_path: str) -> str:
    """Return a stable UI label without exposing machine-specific absolute paths."""
    parts = [part for part in re.split(r"[\\/]+", profile_path) if part]
    lowered = [part.lower() for part in parts]
    if "profiles" in lowered:
        index = len(lowered) - 1 - lowered[::-1].index("profiles")
        tail = parts[index + 1 :]
        if tail and tail[0].lower() == "templates":
            tail = tail[1:]
        if tail:
            return "Profiles/" + "/".join(tail)
    name = Path(profile_path).name if profile_path else ""
    return f"Profiles/{name}" if name else "Profile path unavailable"


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


def update_profile_enabled(conn: sqlite3.Connection, *, profile_id: str, enabled: bool) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    if not row:
        raise MonitorStateError(f"Profile is not registered: {profile_id}")
    config = parse_json(row["config_json"], {})
    if not isinstance(config, dict):
        config = {}
    # Store the Desk toggle as a runtime override beside the profile snapshot.
    # Monitor runs merge this before the disabled-profile gate, so a user can
    # pause a profile from the Desk without editing TOML or profile templates.
    config["enabled"] = enabled
    now = utc_now()
    conn.execute(
        "UPDATE profiles SET enabled = ?, config_json = ?, updated_at = ? WHERE profile_id = ?",
        (1 if enabled else 0, stable_json(config), now, profile_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    return _profile_from_row(updated)


def update_profile_runtime_settings(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    if not row:
        raise MonitorStateError(f"Profile is not registered: {profile_id}")
    if not settings:
        raise MonitorStateError("At least one profile setting is required.")
    config = parse_json(row["config_json"], {})
    if not isinstance(config, dict):
        config = {}
    for key, value in settings.items():
        if key not in PROFILE_RUNTIME_SETTING_LIMITS:
            raise MonitorStateError(f"Unsupported profile setting field: {key}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise MonitorStateError(f"{key} must be an integer.")
        lower, upper = PROFILE_RUNTIME_SETTING_LIMITS[key]
        if value < lower or value > upper:
            raise MonitorStateError(f"{key} must be between {lower} and {upper}.")
        config[key] = value
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
    merged = dict(profile)
    enabled = config.get("enabled")
    if isinstance(enabled, bool):
        merged["enabled"] = enabled
    mode = config.get("alert_schedule_mode")
    if mode in ALERT_SCHEDULE_MODES:
        merged["alert_schedule_mode"] = mode
    for key in PROFILE_RUNTIME_SETTING_LIMITS:
        value = config.get(key)
        lower, upper = PROFILE_RUNTIME_SETTING_LIMITS[key]
        if isinstance(value, int) and not isinstance(value, bool) and lower <= value <= upper:
            merged[key] = value
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
    for run in runs[:8]:
        payload = scan_meta_payload(run)
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
    if not report_path:
        return ""
    path = Path(report_path)
    if path.suffix.lower() != ".md":
        return report_path
    html_path = path.with_suffix(".html")
    html_path_for_exists = html_path if html_path.is_absolute() else PROJECT_ROOT / html_path
    if not html_path_for_exists.exists():
        return report_path
    return str(html_path).replace("\\", "/")


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
    # Feedback is a current decision per review card, not an append-only click
    # log. Replacing the old row here keeps repeated clicks idempotent and
    # prevents stale choices from leaking into future report learning.
    conn.execute("DELETE FROM feedback_events WHERE card_id = ?", (card_id,))
    conn.execute(
        "DELETE FROM profile_patch_suggestions WHERE card_id = ? AND status = 'pending'",
        (card_id,),
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


def undo_card_action(conn: sqlite3.Connection, *, card_id: str) -> dict[str, Any]:
    get_review_card(conn, card_id)
    now = utc_now()
    conn.execute("DELETE FROM feedback_events WHERE card_id = ?", (card_id,))
    conn.execute(
        "DELETE FROM profile_patch_suggestions WHERE card_id = ? AND status = 'pending'",
        (card_id,),
    )
    conn.execute(
        "UPDATE review_cards SET status = ?, handled_at = NULL, updated_at = ? WHERE card_id = ?",
        (PENDING_STATUS, now, card_id),
    )
    conn.commit()
    return get_review_card(conn, card_id)


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
    last_export_path = latest_export["output_path"] if latest_export else "output/feedback/review-feedback.jsonl"
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


def _normalize_preference_lines(text: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = re.sub(r"^\s*[-*]\s+", "", raw).strip()
        line = re.sub(r"^\d+\.\s+", "", line)
        line = " ".join(line.split())
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines[:24]


def _replace_follow_up_preferences(profile_text: str, preferences_text: str) -> str:
    lines_to_write = [f"- {line}" for line in _normalize_preference_lines(preferences_text)]
    if not lines_to_write:
        lines_to_write = ["- No extra learned preferences yet."]
    heading = "## Follow-up Preferences"
    replacement = [heading, *lines_to_write]
    lines = profile_text.splitlines()
    output: list[str] = []
    index = 0
    replaced = False
    while index < len(lines):
        raw = lines[index]
        if raw.strip() == heading:
            output.extend(replacement)
            replaced = True
            index += 1
            while index < len(lines) and not lines[index].startswith("## "):
                index += 1
            continue
        output.append(raw)
        index += 1
    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.extend(replacement)
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


def create_profile_preferences_patch_suggestion(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    preferences_text: str,
) -> dict[str, Any]:
    clean_lines = _normalize_preference_lines(preferences_text)
    if not clean_lines:
        raise MonitorStateError("At least one matching preference is required.")
    row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    if not row:
        raise MonitorStateError(f"Profile is not registered: {profile_id}")
    profile_path = Path(row["path"])
    if not profile_path.is_absolute():
        profile_path = PROJECT_ROOT / profile_path
    if not profile_path.exists():
        raise MonitorStateError(f"Profile file not found: {profile_path}")
    current = profile_path.read_text(encoding="utf-8")
    base_profile_hash = sha256_text(current)
    proposed = _replace_follow_up_preferences(current, "\n".join(clean_lines))
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
    note = "User edited matching preferences in Signal Desk."
    patch = {
        "schema_version": PROFILE_PATCH_SCHEMA_VERSION,
        "patch_id": "patch_" + uuid.uuid4().hex,
        "profile_id": profile_id,
        "card_id": None,
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
            None,
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
    internal_profiles = [
        _profile_from_row(row)
        for row in conn.execute("SELECT * FROM profiles ORDER BY profile_id").fetchall()
    ]
    profile_report_titles = {
        str(profile.get("profile_id") or ""): report_title_from_profile_path(str(profile.get("path") or ""))
        for profile in internal_profiles
    }
    profiles = [
        dashboard_profile_projection(
            profile,
            report_title=profile_report_titles.get(str(profile.get("profile_id") or ""), ""),
        )
        for profile in internal_profiles
    ]
    internal_runs = [
        run_from_row(row)
        for row in conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 100").fetchall()
    ]
    source_link_lookup = source_link_lookup_from_runs(internal_runs)
    inbox = [
        _card_from_row(row, source_link_lookup)
        for row in conn.execute(
            "SELECT * FROM review_cards WHERE status = ? ORDER BY updated_at DESC LIMIT 200",
            (PENDING_STATUS,),
        ).fetchall()
    ]
    runs = [dashboard_run_projection(run, profile_report_titles=profile_report_titles) for run in internal_runs]
    delivery_targets = [
        delivery_target_from_row(row)
        for row in conn.execute("SELECT * FROM delivery_targets ORDER BY target_id").fetchall()
    ]
    patches = [
        {
            "schema_version": PROFILE_PATCH_SCHEMA_VERSION,
            "patch_id": row["patch_id"],
            "profile_id": row["profile_id"],
            "profile_display_path": display_profile_path(str(row["profile_path"] or "")),
            "card_id": row["card_id"],
            "card_title": patch_card_title(row),
            "note": row["note"],
            "status": row["status"],
            "diff_text": row["diff_text"],
            "base_profile_hash": row["base_profile_hash"] or "",
            "base_profile_short_hash": str(row["base_profile_hash"] or "")[:12],
            "apply_readiness": profile_patch_apply_readiness(
                status=str(row["status"] or ""),
                profile_path=str(row["profile_path"] or ""),
                base_profile_hash=str(row["base_profile_hash"] or ""),
            ),
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
    source_stats = source_value_stats(conn, runs=internal_runs)
    setup_status = dashboard_setup_status(
        profiles=internal_profiles,
        runs=internal_runs,
        delivery_targets=delivery_targets,
    )
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
        "opportunity_summary": opportunity_summary(
            conn,
            internal_runs,
            profile_report_titles=profile_report_titles,
        ),
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


def dashboard_run_projection(
    run: dict[str, Any],
    *,
    profile_report_titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    manifest = run.get("manifest") if isinstance(run.get("manifest"), dict) else {}
    profile_id = str(run.get("profile_id") or manifest.get("profile_id") or "")
    return {
        "run_id": run["run_id"],
        "profile_id": run["profile_id"],
        "display_name": profile_display_label(
            profile_id,
            report_title=(profile_report_titles or {}).get(profile_id, ""),
        ),
        "status": run["status"],
        "started_at": run["started_at"],
        "completed_at": run["completed_at"],
        "review_card_count": non_negative_int(manifest.get("review_card_count")),
        "alert_count": non_negative_int(manifest.get("alert_count")),
        "report_artifact": dashboard_report_artifact(
            manifest.get("artifacts"),
            profile_id=profile_id,
            profile_path=str(manifest.get("profile_path") or ""),
            profile_report_title=(profile_report_titles or {}).get(profile_id, ""),
        ),
        "quality": run.get("quality") if isinstance(run.get("quality"), dict) else {},
    }


def dashboard_report_artifact(
    artifacts: object,
    *,
    profile_id: str = "",
    profile_path: str = "",
    profile_report_title: str = "",
) -> dict[str, str] | None:
    if not isinstance(artifacts, list):
        return None
    report_candidates = [
        item
        for item in artifacts
        if isinstance(item, dict) and item.get("path") and item.get("type") in {"report_html", "report_markdown"}
    ]
    report_candidates.sort(key=report_artifact_priority)
    report = report_candidates[0] if report_candidates else None
    if not report:
        return None
    path = str(report.get("path") or "")
    artifact_type = str(report.get("type") or "")
    profile_report_title = profile_report_title or report_title_from_profile_path(profile_path)
    display_name = report_artifact_display_name(
        report,
        path=path,
        profile_id=profile_id,
        profile_report_title=profile_report_title,
    )
    return {
        "type": artifact_type,
        "path": path,
        "category": str(report.get("category") or "reports"),
        "format": str(report.get("format") or artifact_format_from_path(path)),
        "display_name": display_name,
        "display_path": report_artifact_display_path(report, path=path, display_name=display_name),
    }


def report_artifact_priority(report: dict[str, Any]) -> int:
    # Dashboard links should favor the phone-friendly rendered report. Markdown
    # remains available as a durable source artifact, but it should not be the
    # default click target when an HTML sibling exists in the same run.
    if report.get("type") == "report_html":
        return 0
    if report.get("type") == "report_markdown":
        return 1
    return 2


def report_artifact_display_name(
    report: dict[str, Any],
    *,
    path: str,
    profile_id: str,
    profile_report_title: str = "",
) -> str:
    explicit = str(report.get("display_name") or "").strip()
    if explicit:
        legacy_lane_title = f"{title_case_label(profile_id)} Signal Report" if profile_id else ""
        if profile_report_title and explicit == legacy_lane_title:
            return profile_report_title
        return explicit
    if profile_report_title:
        return profile_report_title
    stem = Path(path).stem.strip()
    stem = re.sub(r"[-_ ]?20\d{2}[-_]\d{2}[-_]\d{2}[-_]\d{4,6}$", "", stem)
    stem = re.sub(r"[-_ ]?\d{8}T\d{4,6}Z?$", "", stem)
    if stem and stem.lower() != "report":
        return title_case_label(stem)
    profile_label = title_case_label(profile_id)
    return f"{profile_label} Signal Report" if profile_label else "Signal Report"


def report_artifact_display_path(report: dict[str, Any], *, path: str, display_name: str) -> str:
    explicit = str(report.get("display_path") or "").strip()
    if explicit:
        return explicit
    file_name = Path(path).name
    if file_name.lower() in {"report.html", "report.md"} and display_name.strip():
        suffix = Path(file_name).suffix or Path(path).suffix
        human_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", display_name).strip()
        human_name = re.sub(r"\s+", " ", human_name)
        if human_name:
            return f"Reports/{human_name}{suffix}"
    return f"Reports/{file_name}"


def report_title_from_profile_path(profile_path: str) -> str:
    if not profile_path:
        return ""
    path = Path(profile_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        profile_text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not re.search(r"^##\s+Report Labels\b", profile_text, flags=re.MULTILINE):
        return ""
    title = parse_profile_config(profile_text).labels.report_title.strip()
    return title


def profile_display_label(profile_id: str, *, profile_path: str = "", report_title: str = "") -> str:
    title = report_title or report_title_from_profile_path(profile_path)
    if title:
        return compact_report_title(title)
    return title_case_label(profile_id)


def compact_report_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title).strip()
    for suffix in (
        "Signal Report",
        "Signal Brief",
        "Scan Report",
        "Report",
        "Brief",
    ):
        if text.casefold().endswith(suffix.casefold()):
            text = text[: -len(suffix)].strip()
            break
    return text or title.strip()


def artifact_format_from_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".html":
        return "HTML"
    if suffix == ".md":
        return "Markdown"
    return suffix.lstrip(".").upper() or "Artifact"


def delivery_target_from_row(row: sqlite3.Row) -> dict[str, Any]:
    target_type = str(row["target_type"] or "")
    enabled = bool(row["enabled"])
    config = parse_json(row["config_json"], {})
    if not isinstance(config, dict):
        config = {}
    config.pop("token", None)
    config.pop("bot_token", None)
    display_name = delivery_target_display_name(target_type, str(row["target_id"] or ""))
    return {
        "schema_version": DELIVERY_TARGET_SCHEMA_VERSION,
        "target_id": row["target_id"],
        "type": target_type,
        "enabled": enabled,
        "config": config,
        "display_name": display_name,
        "status_label": "Live" if enabled else "Muted",
        "detail": delivery_target_detail(target_type=target_type, enabled=enabled, config=config),
        "updated_at": row["updated_at"],
    }


def delivery_target_display_name(target_type: str, target_id: str) -> str:
    normalized = target_type.lower().strip()
    if normalized == "telegram_bot":
        return "Telegram Bot"
    return title_case_label(normalized or target_id)


def delivery_target_detail(*, target_type: str, enabled: bool, config: dict[str, Any]) -> str:
    normalized = target_type.lower().strip()
    has_chat = bool(str(config.get("chat_id") or "").strip())
    if normalized == "telegram_bot":
        if has_chat and enabled:
            return "Chat connected; live delivery is on."
        if has_chat:
            return "Chat connected; delivery is muted."
        return "Live target not connected."
    return "Delivery target is active." if enabled else "Delivery target is muted."


def patch_card_title(row: sqlite3.Row) -> str:
    item = parse_json(row["card_item_json"], {}) if "card_item_json" in row.keys() else {}
    fallback = str(row["card_title"] or "Review card") if "card_title" in row.keys() else "Review card"
    return display_item_title(item if isinstance(item, dict) else {}, fallback=fallback)


def profile_patch_apply_readiness(
    *,
    status: str,
    profile_path: str,
    base_profile_hash: str,
) -> dict[str, str]:
    if status != "pending":
        return {
            "status": status or "unknown",
            "label": "Not pending",
            "detail": "This diff is not waiting for apply.",
        }
    if not base_profile_hash:
        return {
            "status": "unknown",
            "label": "Needs check",
            "detail": "No base profile hash was recorded for this diff.",
        }
    path = Path(profile_path)
    if not path.exists():
        return {
            "status": "blocked",
            "label": "Profile missing",
            "detail": "The profile file could not be found, so this diff cannot be applied safely.",
        }
    current_hash = sha256_text(path.read_text(encoding="utf-8"))
    if current_hash != base_profile_hash:
        return {
            "status": "blocked",
            "label": "Profile changed",
            "detail": "The profile file changed since this diff was suggested; review the file before applying.",
        }
    return {
        "status": "ready",
        "label": "Safe to apply",
        "detail": "The profile still matches the base hash captured when this diff was suggested.",
    }


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
        "top_diagnostic_code": top_diagnostic_code(diagnostics),
    }


def top_diagnostic_code(diagnostics: list[Any]) -> str:
    # The dashboard uses this code to choose recovery flow; prefer severity
    # over manifest order so source failures cannot be hidden by earlier warnings.
    severity_rank = {"failure": 0, "warning": 1, "info": 2}
    ranked: list[tuple[int, int, str]] = []
    for index, item in enumerate(diagnostics):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "")
        if not code:
            continue
        severity = str(item.get("severity") or "info").lower()
        ranked.append((severity_rank.get(severity, severity_rank["info"]), index, code))
    if not ranked:
        return ""
    return min(ranked)[2]


def opportunity_summary(
    conn: sqlite3.Connection,
    runs: list[dict[str, Any]],
    *,
    profile_report_titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not runs:
        return {
            "schema_version": "dashboard_opportunity_summary_v1",
            "status": "no_runs",
            "run_id": "",
            "profile_id": "",
            "display_name": "",
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
    profile_id = str(latest.get("profile_id") or manifest.get("profile_id") or "")
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
        "profile_id": profile_id,
        "display_name": profile_display_label(
            profile_id,
            report_title=(profile_report_titles or {}).get(profile_id, ""),
        ),
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
        next_step = f"tgcs monitor run --profile-id {preferred['profile_id']} --delivery-mode dry-run"
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
            command="",
        ),
        setup_check(
            "first_run",
            "First monitor run",
            first_run_status,
            detail=first_run_detail,
            command="" if latest_source_attention else first_run_command,
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
    return (
        "Open Signal Desk Settings > Sources, use starter sources or Source assistant, "
        f"then run a dry scan for {profile_id}."
    )


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
            -int(bool(item.get("scan_failure"))),
            -int(bool(item.get("scan_incomplete"))),
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
        "display_name": display_channel_name(channel),
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
        "scan_failure_reason": "",
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
            "scan_failure_reason": str(row.get("failure_reason") or row.get("failure") or ""),
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


def display_channel_name(value: str) -> str:
    cleaned = value.strip().lstrip("@")
    if not cleaned:
        return "Unknown Source"
    return title_case_label(cleaned)


def title_case_label(value: str) -> str:
    token_overrides = {
        "ai": "AI",
        "api": "API",
        "css": "CSS",
        "eu": "EU",
        "golang": "Go",
        "html": "HTML",
        "hr": "HR",
        "it": "IT",
        "js": "JS",
        "javascript": "JavaScript",
        "nodejs": "Node.js",
        "pm": "PM",
        "qa": "QA",
        "react": "React",
        "remoute": "Remote",
        "rus": "RU",
        "ts": "TS",
        "typescript": "TypeScript",
        "ui": "UI",
        "us": "US",
        "ux": "UX",
        "webdevelopment": "Web Development",
    }
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    return " ".join(
        token_overrides.get(part.lower(), part[:1].upper() + part[1:])
        for part in spaced.replace("_", " ").replace("-", " ").split()
        if part
    )


def source_value_insights(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return source_value_insights_from_stats(source_value_stats(conn))


def source_insight(
    *,
    kind: str,
    channel: str,
    label: str,
    reason: str,
    priority: int,
    stats: dict[str, Any],
    confidence: str,
    next_action_label: str,
    next_action_detail: str,
    next_action_command: str = "",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "channel": channel,
        "display_name": display_channel_name(channel),
        "label": label,
        "reason": reason,
        "priority": priority,
        "confidence": confidence,
        "next_action": {
            "label": next_action_label,
            "detail": next_action_detail,
            "command": next_action_command,
        },
        "stats": stats,
    }


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
            failure_reason = str(item.get("scan_failure_reason") or "access_error").replace("_", " ")
            insights.append(
                source_insight(
                    kind="watch",
                    channel=channel,
                    label="Access",
                    reason=f"Latest scan failed ({failure_reason}); check membership, handle, or Telegram session before judging value.",
                    priority=80,
                    stats=item,
                    confidence="high",
                    next_action_label="Fix access",
                    next_action_detail="Verify the source handle, membership, and Telegram session before pruning it.",
                    next_action_command="tgcs doctor --profile jobs",
                )
            )
            continue
        if high_count >= 2:
            insights.append(
                source_insight(
                    kind="promote",
                    channel=channel,
                    label="Promote",
                    reason=f"{high_count} high signals across {card_count} cards.",
                    priority=90 + high_count + alert_count,
                    stats=item,
                    confidence="high" if high_count >= 3 else "medium",
                    next_action_label="Keep source",
                    next_action_detail="Keep this source in the active lane and look for similar channels before expanding cadence.",
                )
            )
            continue
        if high_count == 1:
            insights.append(
                source_insight(
                    kind="observe",
                    channel=channel,
                    label="Observe",
                    reason="1 high signal so far; keep observing before promote.",
                    priority=60 + alert_count,
                    stats=item,
                    confidence="low",
                    next_action_label="Need more data",
                    next_action_detail="Keep the source for a few more runs; one high signal is not enough to promote cadence.",
                )
            )
            continue
        if false_positive_count >= 2 and high_count == 0:
            insights.append(
                source_insight(
                    kind="prune",
                    channel=channel,
                    label="Prune",
                    reason=f"{false_positive_count} false positives and no high signals.",
                    priority=70 + false_positive_count,
                    stats=item,
                    confidence="medium",
                    next_action_label="Review source",
                    next_action_detail="Check whether this channel should be removed or whether the profile needs a narrower reject rule.",
                    next_action_command="tgcs sources list --topic jobs",
                )
            )
            continue
        if kept_count >= 5 and latest_card_count == 0 and high_count == 0:
            insights.append(
                source_insight(
                    kind="watch",
                    channel=channel,
                    label="Watch",
                    reason=f"{kept_count} fresh messages in the latest scan, but no review cards.",
                    priority=45 + min(kept_count, 20),
                    stats=item,
                    confidence="medium",
                    next_action_label="Tune profile",
                    next_action_detail="Inspect whether prefilter keywords or profile rules are excluding useful posts before pruning.",
                )
            )
            continue
        if card_count >= 2 and high_rate < 0.5 and medium_count > 0:
            insights.append(
                source_insight(
                    kind="watch",
                    channel=channel,
                    label="Watch",
                    reason=f"{medium_count} medium signals, but high-rate is {round(high_rate * 100)}%.",
                    priority=50 + medium_count,
                    stats=item,
                    confidence="medium",
                    next_action_label="Review fit",
                    next_action_detail="Check a few medium cards before deciding whether this source deserves profile tuning.",
                )
            )
    return sorted(insights, key=lambda item: (-int(item["priority"]), str(item["channel"])))[:12]
