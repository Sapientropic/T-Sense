"""SQLite state for v0.5-alpha monitoring, inbox, alerts, and profile diffs.

The database is local private state under ``.tgcs/``.  It is allowed to keep
workflow notes and profile snapshots, but it must not become a second archive
of Telegram message bodies, credentials, bot tokens, or sessions.  Review cards
therefore keep source refs and extracted decision fields only.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from scripts import monitor_db, source_insights as _source_insights
from scripts.monitor_alerts import (
    alert_candidates as alert_candidates,
    record_alert_event as record_alert_event,
    sent_alert_card_ids as sent_alert_card_ids,
    sent_alert_suppression_keys as sent_alert_suppression_keys,
)
from scripts.monitor_common import (
    ACTION_TO_STATUS as ACTION_TO_STATUS,
    ALERT_RULES,
    ALERT_SCHEDULE_MODES,
    DELIVERY_TARGET_SCHEMA_VERSION as DELIVERY_TARGET_SCHEMA_VERSION,
    LIFECYCLE_ACTIONS as LIFECYCLE_ACTIONS,
    LIFECYCLE_ACTION_TO_STATUS as LIFECYCLE_ACTION_TO_STATUS,
    MonitorStateError,
    OPEN_OPPORTUNITY_STATUS as OPEN_OPPORTUNITY_STATUS,
    OPPORTUNITY_STATUSES as OPPORTUNITY_STATUSES,
    PENDING_STATUS as PENDING_STATUS,
    PREFERENCE_ACTIONS as PREFERENCE_ACTIONS,
    PROFILE_PATCH_SCHEMA_VERSION as PROFILE_PATCH_SCHEMA_VERSION,
    PROFILE_RUNTIME_INT_LIMITS,
    PROFILE_RUNTIME_LIST_FIELDS as PROFILE_RUNTIME_LIST_FIELDS,
    PROFILE_RUNTIME_SETTING_LIMITS as PROFILE_RUNTIME_SETTING_LIMITS,
    PROFILE_RUNTIME_SETTINGS_ALLOWED,
    PROFILE_RUNTIME_STRING_FIELDS,
    PROFILE_WEEKDAYS,
    PROJECT_ROOT,
    REVIEW_ACTIONS as REVIEW_ACTIONS,
    parse_iso_datetime as parse_iso_datetime,
    parse_json,
    profile_text_private_fragment_reason as profile_text_private_fragment_reason,
    require_profile_text_without_private_fragments as require_profile_text_without_private_fragments,
    sha256_text as sha256_text,
    stable_json,
    utc_now,
)
from scripts.dashboard_projection import (
    _profile_from_row,
    artifact_format_from_path as artifact_format_from_path,
    compact_report_title as compact_report_title,
    dashboard_profile_projection as dashboard_profile_projection,
    dashboard_report_artifact as dashboard_report_artifact,
    dashboard_run_projection as dashboard_run_projection,
    dashboard_setup_status as dashboard_setup_status,
    dashboard_snapshot as dashboard_snapshot,
    delivery_target_detail as delivery_target_detail,
    delivery_target_display_name as delivery_target_display_name,
    delivery_target_from_row as delivery_target_from_row,
    display_profile_path as display_profile_path,
    is_dashboard_report_artifact_name as is_dashboard_report_artifact_name,
    is_dashboard_report_artifact_path as is_dashboard_report_artifact_path,
    latest_run_needs_source_attention as latest_run_needs_source_attention,
    opportunity_decision_counts as opportunity_decision_counts,
    opportunity_next_action as opportunity_next_action,
    opportunity_rank_key as opportunity_rank_key,
    opportunity_summary as opportunity_summary,
    opportunity_summary_item as opportunity_summary_item,
    patch_card_title as patch_card_title,
    preferred_setup_profile as preferred_setup_profile,
    profile_display_label as profile_display_label,
    profile_for_run as profile_for_run,
    profile_matching_summary as profile_matching_summary,
    profile_patch_apply_readiness as profile_patch_apply_readiness,
    report_artifact_display_name as report_artifact_display_name,
    report_artifact_display_path as report_artifact_display_path,
    report_artifact_priority as report_artifact_priority,
    report_title_from_profile_path as report_title_from_profile_path,
    run_from_row as run_from_row,
    run_quality_summary as run_quality_summary,
    setup_check as setup_check,
    setup_checklist as setup_checklist,
    source_attention_next_step as source_attention_next_step,
    top_diagnostic_code as top_diagnostic_code,
)
from scripts.monitor_feedback import (
    clear_feedback_decisions as clear_feedback_decisions,
    create_feedback_profile_patch_suggestions as create_feedback_profile_patch_suggestions,
    dashboard_feedback_export_display_path as dashboard_feedback_export_display_path,
    export_feedback_entries as export_feedback_entries,
    feedback_next_action as feedback_next_action,
    feedback_summary as feedback_summary,
    latest_feedback_export as latest_feedback_export,
    recent_feedback_impacts as recent_feedback_impacts,
    record_feedback_export as record_feedback_export,
    validation_summary as validation_summary,
)
from scripts.profile_patches import (
    apply_profile_patch as apply_profile_patch,
    create_profile_patch_suggestion as create_profile_patch_suggestion,
    create_profile_preferences_patch_suggestion as create_profile_preferences_patch_suggestion,
    dashboard_profile_file_path as dashboard_profile_file_path,
    replay_profile_patch as replay_profile_patch,
    revert_profile_patch as revert_profile_patch,
)
from scripts.review_cards import (
    card_id_for_item as card_id_for_item,
    enrich_source_refs as enrich_source_refs,
    get_review_card as get_review_card,
    preferred_report_path as preferred_report_path,
    set_card_action as set_card_action,
    source_lookup_key as source_lookup_key,
    telegram_source_ref_url as telegram_source_ref_url,
    undo_card_action as undo_card_action,
    upsert_review_cards as upsert_review_cards,
)


DB_FILENAME = monitor_db.DB_FILENAME
STATE_SCHEMA_VERSION = monitor_db.STATE_SCHEMA_VERSION


def _sync_source_insights_project_root() -> None:
    _source_insights.PROJECT_ROOT = PROJECT_ROOT


def source_value_stats(conn: sqlite3.Connection, runs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    _sync_source_insights_project_root()
    return _source_insights.source_value_stats(conn, runs)


def empty_source_stat(channel: str) -> dict[str, Any]:
    return _source_insights.empty_source_stat(channel)


def latest_source_scan_stats(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    _sync_source_insights_project_root()
    return _source_insights.latest_source_scan_stats(runs)


def scan_meta_payload(run: dict[str, Any]) -> dict[str, Any]:
    _sync_source_insights_project_root()
    return _source_insights.scan_meta_payload(run)


def scan_meta_artifact(manifest: dict[str, Any]) -> dict[str, Any] | None:
    return _source_insights.scan_meta_artifact(manifest)


def scan_meta_total_messages(run: dict[str, Any]) -> int:
    _sync_source_insights_project_root()
    return _source_insights.scan_meta_total_messages(run)


def load_scan_meta_counts(path_value: object) -> dict[str, Any]:
    _sync_source_insights_project_root()
    return _source_insights.load_scan_meta_counts(path_value)


def non_negative_int(value: object) -> int:
    return _source_insights.non_negative_int(value)


def display_channel_name(value: str) -> str:
    return _source_insights.display_channel_name(value)


def title_case_label(value: str) -> str:
    return _source_insights.title_case_label(value)


def source_value_insights(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    _sync_source_insights_project_root()
    return _source_insights.source_value_insights(conn)


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
    return _source_insights.source_insight(
        kind=kind,
        channel=channel,
        label=label,
        reason=reason,
        priority=priority,
        stats=stats,
        confidence=confidence,
        next_action_label=next_action_label,
        next_action_detail=next_action_detail,
        next_action_command=next_action_command,
    )


def source_value_insights_from_stats(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _source_insights.source_value_insights_from_stats(stats)


connect = monitor_db.connect
init_db = monitor_db.init_db
_ensure_column = monitor_db._ensure_column


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


def _clean_runtime_hhmm(key: str, value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value.strip()):
        raise MonitorStateError(f"{key} must use HH:MM format.")
    hour_text, minute_text = value.strip().split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour > 23 or minute > 59:
        raise MonitorStateError(f"{key} must use HH:MM format.")
    return f"{hour:02d}:{minute:02d}"


def _clean_runtime_timezone(value: object) -> str:
    if not isinstance(value, str):
        raise MonitorStateError("timezone must be a valid IANA timezone.")
    timezone = value.strip()
    if (
        not timezone
        or len(timezone) > 80
        or ".." in timezone
        or timezone.startswith(("/", "."))
        or "//" in timezone
        or not re.fullmatch(r"[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+)*", timezone)
    ):
        raise MonitorStateError("timezone must be a valid IANA timezone.")
    return timezone


def _clean_runtime_workdays(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise MonitorStateError("workdays must be a non-empty list of weekday names.")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise MonitorStateError("workdays must contain weekday names.")
        day = item.strip().lower()[:3]
        if day not in PROFILE_WEEKDAYS:
            raise MonitorStateError("workdays must contain weekday names.")
        if day not in cleaned:
            cleaned.append(day)
    return cleaned


def _clean_runtime_setting(key: str, value: object) -> Any:
    if key in PROFILE_RUNTIME_INT_LIMITS:
        if isinstance(value, bool) or not isinstance(value, int):
            raise MonitorStateError(f"{key} must be an integer.")
        lower, upper = PROFILE_RUNTIME_INT_LIMITS[key]
        if value < lower or value > upper:
            raise MonitorStateError(f"{key} must be between {lower} and {upper}.")
        return value
    if key == "timezone":
        return _clean_runtime_timezone(value)
    if key in {"work_start", "work_end"}:
        return _clean_runtime_hhmm(key, value)
    if key == "alert_rule":
        if not isinstance(value, str):
            raise MonitorStateError(f"alert_rule must be one of: {', '.join(sorted(ALERT_RULES))}.")
        alert_rule = value.strip()
        if alert_rule not in ALERT_RULES:
            raise MonitorStateError(f"alert_rule must be one of: {', '.join(sorted(ALERT_RULES))}.")
        return alert_rule
    if key == "workdays":
        return _clean_runtime_workdays(value)
    raise MonitorStateError(f"Unsupported profile setting field: {key}")


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
        if key not in PROFILE_RUNTIME_SETTINGS_ALLOWED:
            raise MonitorStateError(f"Unsupported profile setting field: {key}")
        config[key] = _clean_runtime_setting(key, value)
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
    for key in PROFILE_RUNTIME_INT_LIMITS:
        value = config.get(key)
        lower, upper = PROFILE_RUNTIME_INT_LIMITS[key]
        if isinstance(value, int) and not isinstance(value, bool) and lower <= value <= upper:
            merged[key] = value
    for key in PROFILE_RUNTIME_STRING_FIELDS:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value
    workdays = config.get("workdays")
    if isinstance(workdays, list) and workdays:
        merged["workdays"] = [str(day) for day in workdays if str(day).strip()]
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
