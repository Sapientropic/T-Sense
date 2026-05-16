"""Monitor profile configuration and schedule helpers."""

from __future__ import annotations

import argparse
import json
import tomllib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_RUN_CONFIG_SCHEMA_VERSION = "profile_run_config_v1"
RUN_MANIFEST_SCHEMA_VERSION = "run_manifest_v1"
DEFAULT_PROFILE_ID = "market-news"
DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8765"
DEFAULT_FEEDBACK_EXPORT_PATH = "output/feedback/review-feedback.jsonl"
DEFAULT_FAST_JOBS_PROFILE_ID = "jobs-fast"
DEFAULT_FAST_JOBS_SCAN_WINDOW_HOURS = 2
DEFAULT_FAST_JOBS_INTERVAL_MINUTES = 15
DEFAULT_FAST_JOBS_ALERT_MAX_AGE_MINUTES = 60
DEFAULT_FAST_JOBS_SEMANTIC_MAX_MESSAGES = 40
DEFAULT_FAST_JOBS_SEMANTIC_MAX_TOKENS = 6000
DEFAULT_FAST_JOBS_SCAN_CONCURRENCY = 3
DEFAULT_FAST_JOBS_SCAN_DELAY_SECONDS = 0.2
DEFAULT_FAST_JOBS_SEMANTIC_BATCH_SIZE = 20
DEFAULT_FAST_JOBS_SEMANTIC_CONCURRENCY = 2
DEFAULT_FAST_JOBS_PREFILTER_KEYWORDS = [
    "hiring",
    "we're hiring",
    "is hiring",
    "job opening",
    "open role",
    "remote",
    "apply",
    "frontend",
    "front-end",
    "frontend engineer",
    "react",
    "vue",
    "typescript",
    "ui engineer",
    "web app",
    "webgl",
    "engineer",
    "developer",
    "freelance",
    "contract",
    "contractor",
    "gig",
    "bounty",
    "paid project",
    "mini app",
    "mini apps",
    "telegram mini app",
    "ton",
    "usdt",
    "budget",
    "招聘",
    "招人",
    "岗位",
    "职位",
    "远程",
    "外包",
    "兼职",
    "私活",
    "项目",
    "预算",
]
ALERT_SCHEDULE_MODES = {"work_hours", "all_day", "muted"}



@dataclass
class MonitorConfig:
    path: Path
    profiles: dict[str, dict[str, Any]]
    delivery_targets: dict[str, dict[str, Any]]
    defaults: dict[str, Any]



def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"



def root_path(value: str | Path, root: Path | None = None) -> Path:
    base = PROJECT_ROOT if root is None else root
    path = Path(value)
    return path if path.is_absolute() else base / path



def relative_to_root(path: str | Path | None, root: Path | None = None) -> str | None:
    if path is None:
        return None
    base = PROJECT_ROOT if root is None else root
    candidate = Path(path)
    try:
        return str(candidate.resolve().relative_to(base.resolve())).replace("\\", "/")
    except ValueError:
        return str(candidate)



def default_config(config_path: Path) -> MonitorConfig:
    defaults = {
        "output_dir": "output",
        "state_dir": ".tgcs/state",
        "database": ".tgcs/tgcs.db",
        "dashboard_url": DEFAULT_DASHBOARD_URL,
    }
    market_profile = {
        "id": DEFAULT_PROFILE_ID,
        "path": "profiles/templates/market-news.md",
        "enabled": True,
        "timezone": "Asia/Shanghai",
        "work_interval_minutes": 120,
        "off_hours_interval_minutes": 360,
        "scan_window_hours": 24,
        "source_registry": ".tgcs/sources.json",
        "channel_list": "channel_lists/example.txt",
        "source_topics": ["market-news"],
        "alert_rule": "high_new_or_changed",
        "alert_schedule_mode": "work_hours",
        "delivery_targets": ["telegram-bot-default"],
        "dashboard_visible": True,
    }
    fast_jobs_profile = {
        "id": DEFAULT_FAST_JOBS_PROFILE_ID,
        "path": "profiles/templates/jobs.md",
        "enabled": True,
        "timezone": "Asia/Shanghai",
        "work_start": "09:00",
        "work_end": "23:00",
        "work_interval_minutes": DEFAULT_FAST_JOBS_INTERVAL_MINUTES,
        "off_hours_interval_minutes": 60,
        "scan_window_hours": DEFAULT_FAST_JOBS_SCAN_WINDOW_HOURS,
        "source_registry": ".tgcs/sources.json",
        "channel_list": "channel_lists/example.txt",
        "source_topics": ["jobs"],
        "alert_rule": "high_new_or_changed",
        "alert_max_age_minutes": DEFAULT_FAST_JOBS_ALERT_MAX_AGE_MINUTES,
        "alert_schedule_mode": "work_hours",
        "delivery_targets": ["telegram-bot-default"],
        "dashboard_visible": True,
        "prefilter_enabled": True,
        "allow_partial_source_failures": True,
        "prefilter_keywords": DEFAULT_FAST_JOBS_PREFILTER_KEYWORDS,
        "semantic_max_messages": DEFAULT_FAST_JOBS_SEMANTIC_MAX_MESSAGES,
        "semantic_max_tokens": DEFAULT_FAST_JOBS_SEMANTIC_MAX_TOKENS,
        "scan_concurrency": DEFAULT_FAST_JOBS_SCAN_CONCURRENCY,
        "scan_delay_seconds": DEFAULT_FAST_JOBS_SCAN_DELAY_SECONDS,
        "semantic_batch_size": DEFAULT_FAST_JOBS_SEMANTIC_BATCH_SIZE,
        "semantic_concurrency": DEFAULT_FAST_JOBS_SEMANTIC_CONCURRENCY,
    }
    target = {
        "id": "telegram-bot-default",
        "type": "telegram_bot",
        "enabled": False,
        "chat_id": "",
    }
    return MonitorConfig(
        path=config_path,
        profiles={market_profile["id"]: market_profile, fast_jobs_profile["id"]: fast_jobs_profile},
        delivery_targets={target["id"]: target},
        defaults=defaults,
    )



def load_config(config_path: Path, root: Path | None = None) -> MonitorConfig:
    base_root = PROJECT_ROOT if root is None else root
    if not config_path.exists():
        return default_config(config_path)
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Profile run config is not valid TOML: {exc}") from exc
    if payload.get("schema_version") not in {None, PROFILE_RUN_CONFIG_SCHEMA_VERSION}:
        raise ValueError(f"schema_version must be {PROFILE_RUN_CONFIG_SCHEMA_VERSION}")
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    base = default_config(config_path)
    merged_defaults = {**base.defaults, **defaults}
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raw_profiles = list(base.profiles.values())
    profiles: dict[str, dict[str, Any]] = {}
    for raw in raw_profiles:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        item = dict(raw)
        base_profile = base.profiles.get(str(item["id"]), {})
        item.setdefault("enabled", True)
        item.setdefault("alert_rule", "high_new_or_changed")
        item.setdefault("alert_schedule_mode", "work_hours")
        item.setdefault("dashboard_visible", True)
        item.setdefault("source_registry", merged_defaults.get("source_registry", ".tgcs/sources.json"))
        item.setdefault("channel_list", merged_defaults.get("channel_list", "channel_lists/example.txt"))
        item.setdefault("delivery_targets", ["telegram-bot-default"])
        if "prefilter_enabled" in base_profile:
            item.setdefault("prefilter_enabled", base_profile["prefilter_enabled"])
        if "allow_partial_source_failures" in base_profile:
            item.setdefault("allow_partial_source_failures", base_profile["allow_partial_source_failures"])
        if "prefilter_keywords" in base_profile:
            item.setdefault("prefilter_keywords", base_profile["prefilter_keywords"])
        if "semantic_max_messages" in base_profile:
            item.setdefault("semantic_max_messages", base_profile["semantic_max_messages"])
        if "semantic_max_tokens" in base_profile:
            item.setdefault("semantic_max_tokens", base_profile["semantic_max_tokens"])
        if "scan_concurrency" in base_profile:
            item.setdefault("scan_concurrency", base_profile["scan_concurrency"])
        if "scan_delay_seconds" in base_profile:
            item.setdefault("scan_delay_seconds", base_profile["scan_delay_seconds"])
        if "semantic_batch_size" in base_profile:
            item.setdefault("semantic_batch_size", base_profile["semantic_batch_size"])
        if "semantic_concurrency" in base_profile:
            item.setdefault("semantic_concurrency", base_profile["semantic_concurrency"])
        item.setdefault("prefilter_enabled", False)
        profiles[str(item["id"])] = item
    raw_targets = payload.get("delivery")
    if not isinstance(raw_targets, list) or not raw_targets:
        raw_targets = list(base.delivery_targets.values())
    targets: dict[str, dict[str, Any]] = {}
    for raw in raw_targets:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        item = dict(raw)
        item.setdefault("type", "telegram_bot")
        item.setdefault("enabled", False)
        targets[str(item["id"])] = item
    return MonitorConfig(
        path=root_path(config_path, base_root),
        profiles=profiles,
        delivery_targets=targets,
        defaults=merged_defaults,
    )



def profile_path(profile: dict[str, Any], root: Path | None = None) -> Path:
    return root_path(profile.get("path") or f"profiles/templates/{profile['id']}.md", root)



def source_input_args(profile: dict[str, Any], run_dir: Path, root: Path | None = None) -> list[str]:
    registry = root_path(profile.get("source_registry") or ".tgcs/sources.json", root)
    if registry.exists():
        filtered = filter_source_registry(registry, run_dir, profile)
        return ["--source-registry", str(filtered)]
    channel_list = root_path(profile.get("channel_list") or "channel_lists/example.txt", root)
    return [str(channel_list)] if channel_list.exists() else []



def filter_source_registry(registry: Path, run_dir: Path, profile: dict[str, Any]) -> Path:
    topics = {str(item) for item in profile.get("source_topics") or profile.get("topics") or []}
    source_ids = {str(item) for item in profile.get("source_ids") or []}
    if not topics and not source_ids:
        return registry
    payload = json.loads(registry.read_text(encoding="utf-8"))
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    filtered = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_topics = {str(item) for item in source.get("topics") or []}
        if source_ids and source.get("source_id") in source_ids:
            filtered.append(source)
        elif topics and source_topics.intersection(topics):
            filtered.append(source)
    filtered_payload = dict(payload)
    tagged_source_count = sum(
        1
        for source in sources
        if isinstance(source, dict) and bool(source.get("topics"))
    )
    if topics and not source_ids and not filtered and sources and tagged_source_count == 0:
        # Old registries created from plain channel lists did not tag sources.
        # Applying a topic filter to that shape would create an empty registry
        # and make the default v0.5 monitor fail before the first useful run.
        # Once any source has topics, respect the user's explicit taxonomy.
        filtered = [source for source in sources if isinstance(source, dict)]
        mode = "unfiltered_legacy_untagged"
    else:
        mode = "filtered"
    filtered_payload["sources"] = filtered
    filtered_payload["monitor_filter"] = {
        "mode": mode,
        "topics": sorted(topics),
        "source_ids": sorted(source_ids),
        "matched_count": len(filtered),
        "source_count": len(sources),
    }
    filtered_path = run_dir / "source-registry.filtered.json"
    filtered_path.write_text(json.dumps(filtered_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return filtered_path



def effective_scan_hours(args: argparse.Namespace, profile: dict[str, Any]) -> int:
    if args.hours is not None:
        return int(args.hours)
    configured = profile.get("scan_window_hours")
    if configured is not None:
        try:
            return max(1, int(configured))
        except (TypeError, ValueError):
            pass
    return 24



def alert_rule_for_profile(profile: dict[str, Any]) -> dict[str, Any]:
    rule: dict[str, Any] = {"name": str(profile.get("alert_rule") or "high_new_or_changed")}
    if profile.get("alert_max_age_minutes") is not None:
        rule["max_age_minutes"] = profile.get("alert_max_age_minutes")
    return rule



def parse_hhmm(value: object, fallback: time) -> time:
    if not isinstance(value, str) or ":" not in value:
        return fallback
    hour_text, minute_text = value.split(":", 1)
    try:
        return time(hour=max(0, min(23, int(hour_text))), minute=max(0, min(59, int(minute_text))))
    except ValueError:
        return fallback



def local_now_for_profile(profile: dict[str, Any], now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    tz_name = str(profile.get("timezone") or "UTC")
    try:
        zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        zone = UTC
    return current.astimezone(zone)



def is_work_time(profile: dict[str, Any], now: datetime | None = None) -> bool:
    local_now = local_now_for_profile(profile, now)
    workdays = profile.get("workdays")
    if isinstance(workdays, list) and workdays:
        weekday = local_now.strftime("%a").lower()[:3]
        allowed = {str(item).lower()[:3] for item in workdays}
        if weekday not in allowed:
            return False
    start = parse_hhmm(profile.get("work_start"), time(9, 0))
    end = parse_hhmm(profile.get("work_end"), time(23, 0))
    current = local_now.time().replace(second=0, microsecond=0)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end



def delivery_enabled_for_profile(profile: dict[str, Any], now: datetime | None = None) -> tuple[bool, str]:
    mode = str(profile.get("alert_schedule_mode") or "work_hours")
    if mode not in ALERT_SCHEDULE_MODES:
        mode = "work_hours"
    if mode == "muted":
        return False, "muted"
    if mode == "all_day":
        return True, "all_day"
    if is_work_time(profile, now):
        return True, "work_hours"
    return False, "outside_work_hours"
