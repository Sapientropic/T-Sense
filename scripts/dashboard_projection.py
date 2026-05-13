"""Dashboard-facing projection helpers for monitor state."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from scripts import source_insights as _source_insights
from scripts.item_display import display_item_title
from scripts.monitor_common import (
    DELIVERY_TARGET_SCHEMA_VERSION,
    PENDING_STATUS,
    PROFILE_PATCH_SCHEMA_VERSION,
    PROJECT_ROOT,
    parse_iso_datetime,
    parse_json,
    sha256_text,
)
from scripts.monitor_feedback import feedback_summary, validation_summary
from scripts.profile_schema import parse_profile_config
from scripts.review_cards import _card_from_row, source_link_lookup_from_runs


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


def non_negative_int(value: object) -> int:
    return _source_insights.non_negative_int(value)


def title_case_label(value: str) -> str:
    return _source_insights.title_case_label(value)

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
        "timezone": str(config.get("timezone") or ""),
        "workdays": (
            [str(day) for day in config.get("workdays", []) if str(day).strip()]
            if isinstance(config.get("workdays"), list)
            else []
        ),
        "work_start": str(config.get("work_start") or ""),
        "work_end": str(config.get("work_end") or ""),
        "work_interval_minutes": non_negative_int(config.get("work_interval_minutes")),
        "off_hours_interval_minutes": non_negative_int(config.get("off_hours_interval_minutes")),
        "alert_rule": str(config.get("alert_rule") or "high_new_or_changed"),
        "alert_max_age_minutes": non_negative_int(config.get("alert_max_age_minutes")),
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
        path = _project_root() / path
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


def report_title_from_profile_path(profile_path: str) -> str:
    if not profile_path:
        return ""
    path = Path(profile_path)
    if not path.is_absolute():
        path = _project_root() / path
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
        if top_code in {"llm_output_truncated", "semantic_json_invalid"}:
            return {
                "label": "Fix semantic extraction",
                "detail": detail,
                "command": "",
            }
        if top_code not in {"channel_failures", "no_messages_fetched", "source_access_failed"}:
            return {
                "label": "Inspect run failure",
                "detail": detail,
                "command": "",
            }
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
