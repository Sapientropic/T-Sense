"""Source value stats and insight projections for the dashboard.

This module only reads derived monitor metadata and review-card counters. It
must not load Telegram message bodies or become a raw transcript surface.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PENDING_STATUS = "pending"


def parse_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default

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
