"""Dashboard-facing projection helpers for monitor state."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from scripts import (
    dashboard_opportunities as _dashboard_opportunities,
    dashboard_profiles as _dashboard_profiles,
    dashboard_setup as _dashboard_setup,
    report as report,
    source_insights as _source_insights,
)
from scripts.item_display import display_item_title
from scripts.monitor_common import (
    DELIVERY_TARGET_SCHEMA_VERSION,
    PENDING_STATUS,
    PROFILE_PATCH_SCHEMA_VERSION,
    PROJECT_ROOT,
    parse_json,
)
from scripts.monitor_feedback import feedback_summary, validation_summary
from scripts.profile_patches import REVIEW_LEARNING_PATCH_NOTE
from scripts.review_cards import _card_from_row, source_link_lookup_from_runs


ALERT_SUMMARY_SCHEMA_VERSION = "review_card_alert_summary_v1"


def _project_root() -> Path:
    facade = sys.modules.get("scripts.monitor_state")
    root = getattr(facade, "PROJECT_ROOT", PROJECT_ROOT) if facade is not None else PROJECT_ROOT
    return Path(root)


def _sync_source_insights_project_root() -> None:
    _source_insights.PROJECT_ROOT = _project_root()


def scan_meta_total_messages(run: dict[str, Any]) -> int:
    _sync_source_insights_project_root()
    return _source_insights.scan_meta_total_messages(run)


def source_value_insights(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    _sync_source_insights_project_root()
    return _source_insights.source_value_insights(conn)


def source_value_stats(conn: sqlite3.Connection, runs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    _sync_source_insights_project_root()
    return _source_insights.source_value_stats(conn, runs)


def source_value_insights_from_stats(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _source_insights.source_value_insights_from_stats(stats)


non_negative_int = _dashboard_profiles.non_negative_int
title_case_label = _dashboard_profiles.title_case_label
dashboard_profile_projection = _dashboard_profiles.dashboard_profile_projection
profile_matching_summary = _dashboard_profiles.profile_matching_summary
_markdown_sections = _dashboard_profiles._markdown_sections
_clean_markdown_items = _dashboard_profiles._clean_markdown_items
display_profile_path = _dashboard_profiles.display_profile_path
report_title_from_profile_path = _dashboard_profiles.report_title_from_profile_path
profile_display_label = _dashboard_profiles.profile_display_label
compact_report_title = _dashboard_profiles.compact_report_title
opportunity_summary = _dashboard_opportunities.opportunity_summary
opportunity_decision_counts = _dashboard_opportunities.opportunity_decision_counts
opportunity_next_action = _dashboard_opportunities.opportunity_next_action
opportunity_rank_key = _dashboard_opportunities.opportunity_rank_key
opportunity_summary_item = _dashboard_opportunities.opportunity_summary_item
dashboard_setup_status = _dashboard_setup.dashboard_setup_status
setup_check = _dashboard_setup.setup_check
preferred_setup_profile = _dashboard_setup.preferred_setup_profile
profile_for_run = _dashboard_setup.profile_for_run
setup_checklist = _dashboard_setup.setup_checklist
latest_run_needs_source_attention = _dashboard_setup.latest_run_needs_source_attention
source_attention_next_step = _dashboard_setup.source_attention_next_step


def _profile_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "profile_id": row["profile_id"],
        "path": row["path"],
        "display_path": display_profile_path(str(row["path"] or "")),
        "enabled": bool(row["enabled"]),
        "config": parse_json(row["config_json"], {}),
        "updated_at": row["updated_at"],
    }


def _safe_alert_token(value: object, *, fallback: str = "unknown", max_len: int = 80) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", text):
        return fallback
    return text[:max_len]


def alert_summary_by_card(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Return safe per-card alert/delivery health for the dashboard.

    Alert payloads may carry rendered notification text, and delivery attempts
    may carry redacted free-form errors. Review cards only need operational
    proof that an alert was attempted, so keep this projection to enum-like
    fields and counts. Do not add payload text, chat ids, tokens, or errors here
    as a convenience.
    """

    summaries: dict[str, dict[str, Any]] = {}
    rows = conn.execute(
        """
        SELECT card_id, run_id, target_id, status, delivery_attempt_json, created_at
        FROM alert_events
        ORDER BY created_at ASC, alert_id ASC
        """
    ).fetchall()
    for row in rows:
        card_id = str(row["card_id"] or "")
        if not card_id:
            continue
        attempt = parse_json(row["delivery_attempt_json"], {})
        if not isinstance(attempt, dict):
            attempt = {}
        previous = summaries.get(card_id, {})
        summaries[card_id] = {
            "schema_version": ALERT_SUMMARY_SCHEMA_VERSION,
            "alert_count": int(previous.get("alert_count") or 0) + 1,
            "latest_status": _safe_alert_token(row["status"]),
            "latest_run_id": _safe_alert_token(row["run_id"], fallback=""),
            "latest_target_id": _safe_alert_token(row["target_id"], fallback=""),
            "latest_target_type": _safe_alert_token(attempt.get("target_type")),
            "latest_delivery_mode": _safe_alert_token(attempt.get("mode")),
            "latest_delivery_status": _safe_alert_token(attempt.get("status")),
            "latest_delivery_ok": bool(attempt.get("ok")) if isinstance(attempt.get("ok"), bool) else False,
            "latest_alerted_at": str(row["created_at"] or ""),
        }
    return summaries



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
    alert_summaries = alert_summary_by_card(conn)
    inbox = [
        {
            **_card_from_row(row, source_link_lookup),
            "alert_summary": alert_summaries.get(
                str(row["card_id"] or ""),
                {
                    "schema_version": ALERT_SUMMARY_SCHEMA_VERSION,
                    "alert_count": 0,
                },
            ),
        }
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
    patches = dashboard_profile_patch_suggestions(conn)
    source_stats = source_value_stats(conn, runs=internal_runs)
    setup_status = dashboard_setup_status(
        profiles=internal_profiles,
        runs=internal_runs,
        delivery_targets=delivery_targets,
        ai_configured=report.llm_key_available(),
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
        if (
            isinstance(item, dict)
            and item.get("path")
            and item.get("type") in {"report_html", "report_markdown"}
            and is_dashboard_report_artifact_path(str(item.get("path") or ""))
        )
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


def is_dashboard_report_artifact_path(path: str) -> bool:
    cleaned = str(path or "").strip().replace("\\", "/")
    if not cleaned or cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        return False
    parts = PurePosixPath(cleaned).parts
    if not parts or ".." in parts or "runs" not in parts:
        return False
    run_index = parts.index("runs")
    if run_index >= len(parts) - 2:
        return False
    return is_dashboard_report_artifact_name(parts[-1])


def is_dashboard_report_artifact_name(name: str) -> bool:
    lower = str(name or "").strip().lower()
    if lower in {"report.html", "report.md"}:
        return True
    path = PurePosixPath(lower)
    if path.suffix not in {".html", ".md"}:
        return False
    return any(token in path.stem.split("-") for token in {"report", "brief"})


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
    if "card_item_json" in row.keys():
        item = parse_json(row["card_item_json"], {})
    elif "item_json" in row.keys():
        item = parse_json(row["item_json"], {})
    else:
        item = {}
    if "card_title" in row.keys():
        fallback = str(row["card_title"] or "Review card")
    elif "title" in row.keys():
        fallback = str(row["title"] or "Review card")
    else:
        fallback = "Review card"
    return display_item_title(item if isinstance(item, dict) else {}, fallback=fallback)


def dashboard_profile_patch_suggestions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.*, profiles.path AS profile_path, c.title AS card_title, c.item_json AS card_item_json
        FROM profile_patch_suggestions p
        LEFT JOIN profiles ON profiles.profile_id = p.profile_id
        LEFT JOIN review_cards c ON c.card_id = p.card_id
        WHERE p.status = 'pending'
        ORDER BY p.created_at DESC, p.patch_id DESC
        LIMIT 100
        """
    ).fetchall()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        readiness = profile_patch_apply_readiness(
            status=str(row["status"] or ""),
            profile_path=str(row["profile_path"] or ""),
            base_profile_hash=str(row["base_profile_hash"] or ""),
        )
        patch = {
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
            "apply_readiness": readiness,
            "created_at": row["created_at"],
            "applied_at": row["applied_at"],
        }
        grouped.setdefault((str(row["profile_id"] or ""), str(row["note"] or "")), []).append(patch)

    patches: list[dict[str, Any]] = []
    for (profile_id, note), candidates in grouped.items():
        representative = max(candidates, key=profile_patch_projection_rank)
        patch = dict(representative)
        context = profile_patch_source_context(
            conn,
            profile_id=profile_id,
            note=note,
            fallback_title=str(representative.get("card_title") or ""),
            fallback_card_id=str(representative.get("card_id") or ""),
        )
        patch.update(context)
        patch["duplicate_patch_count"] = len(candidates)
        if context["source_card_count"] > 1:
            patch["card_title"] = f"{context['source_card_count']} Review choices"
        patches.append(patch)
    return sorted(patches, key=lambda item: (str(item.get("created_at") or ""), str(item.get("patch_id") or "")), reverse=True)


def profile_patch_projection_rank(patch: dict[str, Any]) -> tuple[int, str, str]:
    readiness = patch.get("apply_readiness") if isinstance(patch.get("apply_readiness"), dict) else {}
    status = str(readiness.get("status") or "")
    readiness_rank = {"ready": 3, "unknown": 2, "blocked": 1}.get(status, 0)
    return readiness_rank, str(patch.get("created_at") or ""), str(patch.get("patch_id") or "")


def profile_patch_source_context(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    note: str,
    fallback_title: str,
    fallback_card_id: str,
) -> dict[str, Any]:
    rows = conn.execute(
        f"""
        SELECT f.card_id, c.title, c.item_json
        FROM feedback_events f
        LEFT JOIN review_cards c ON c.card_id = f.card_id
        WHERE f.profile_id = ?
          AND f.action = 'follow_up'
          {"AND f.note = ?" if note != REVIEW_LEARNING_PATCH_NOTE else ""}
        ORDER BY f.created_at DESC, f.event_id DESC
        LIMIT 24
        """,
        (profile_id, note) if note != REVIEW_LEARNING_PATCH_NOTE else (profile_id,),
    ).fetchall()
    titles: list[str] = []
    seen_titles: set[str] = set()
    for row in rows:
        title = patch_card_title(row)
        key = title.casefold()
        if title and key not in seen_titles:
            titles.append(title)
            seen_titles.add(key)
    if not rows and fallback_card_id and fallback_title:
        titles = [fallback_title]
    return {
        "source_card_count": len(rows) if rows else (1 if fallback_card_id else 0),
        "source_card_titles": titles[:3],
    }


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
    # The Desk treats profile changes as reviewable suggestions that can be
    # edited, applied, or cleared. Do not surface base-hash drift as a blocker:
    # apply_profile_patch snapshots the current file before writing the proposal.
    _ = profile_path, base_profile_hash
    return {
        "status": "ready",
        "label": "Ready",
        "detail": "Review or edit the suggestion, then apply or clear it.",
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
