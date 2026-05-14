"""Dashboard opportunity summary projection."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

from scripts import source_insights as _source_insights
from scripts.dashboard_profiles import profile_display_label
from scripts.monitor_common import OPEN_OPPORTUNITY_STATUS, PENDING_STATUS, PROJECT_ROOT, parse_iso_datetime
from scripts.review_cards import _card_from_row


def _project_root() -> Path:
    facade = sys.modules.get("scripts.monitor_state")
    root = getattr(facade, "PROJECT_ROOT", PROJECT_ROOT) if facade is not None else PROJECT_ROOT
    return Path(root)


def _sync_source_insights_project_root() -> None:
    _source_insights.PROJECT_ROOT = _project_root()


def scan_meta_total_messages(run: dict[str, Any]) -> int:
    _sync_source_insights_project_root()
    return _source_insights.scan_meta_total_messages(run)


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
                "label": "Run AI review",
                "detail": "Start with an AI review run.",
                "command": "tgcs monitor run --profile-id market-news --delivery-mode live",
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
        and str(card.get("opportunity_status") or OPEN_OPPORTUNITY_STATUS).lower() == OPEN_OPPORTUNITY_STATUS
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
        detail = f"Run issue: {top_code}" if top_code else "Open Runs before rerunning."
        if top_code in {"llm_output_truncated", "semantic_json_invalid"}:
            return {
                "label": "Fix AI matching",
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
            "label": "Review priority cards",
            "detail": f"Review {high_actionable_count} high-priority new or updated {noun}.",
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
