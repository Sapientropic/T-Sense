"""v0.5-alpha profile monitor runner.

The monitor is a thin orchestration layer over the existing scan/report
contract.  It adds repeatable run manifests, SQLite-backed review/alert state,
and delivery hooks without changing the stable v0.4 report CLI.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from scripts import agent_cli, delivery, monitor_state
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import agent_cli, delivery, monitor_state


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_RUN_CONFIG_SCHEMA_VERSION = "profile_run_config_v1"
RUN_MANIFEST_SCHEMA_VERSION = "run_manifest_v1"
DEFAULT_PROFILE_ID = "market-news"
DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8765"
DEFAULT_FAST_JOBS_PROFILE_ID = "jobs-fast"
DEFAULT_FAST_JOBS_SCAN_WINDOW_HOURS = 2
DEFAULT_FAST_JOBS_INTERVAL_MINUTES = 15
DEFAULT_FAST_JOBS_ALERT_MAX_AGE_MINUTES = 60
DEFAULT_FAST_JOBS_SEMANTIC_MAX_MESSAGES = 20
DEFAULT_FAST_JOBS_SEMANTIC_MAX_TOKENS = 2000
DEFAULT_FAST_JOBS_PREFILTER_KEYWORDS = [
    "hiring",
    "we're hiring",
    "is hiring",
    "job opening",
    "open role",
    "remote",
    "apply",
    "frontend",
    "backend",
    "fullstack",
    "react",
    "typescript",
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
    "简历",
    "外包",
    "接活",
    "兼职",
    "私活",
    "项目",
    "预算",
]
PREFILTER_TEXT_FIELDS = ("text", "message", "raw_text", "caption", "ocr_text", "media_text")
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


def file_hash(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return monitor_state.sha256_text(path.read_text(encoding="utf-8"))


def artifact(path: Path, artifact_type: str) -> dict[str, Any]:
    return {
        "artifact_id": f"{artifact_type}:{path.name}",
        "type": artifact_type,
        "path": relative_to_root(path),
        "sha256": file_hash(path),
    }


def scan_sidecar_paths(scan_path: Path | None, run_dir: Path) -> tuple[Path, Path]:
    base = scan_path or (run_dir / "scan.jsonl")
    return base.with_suffix(".meta.json"), base.with_suffix(".errors.log")


def load_scan_meta(scan_path: Path | None, run_dir: Path) -> dict[str, Any]:
    meta_path, _ = scan_sidecar_paths(scan_path, run_dir)
    if not meta_path.exists():
        return {}
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def diagnostics_from_scan_meta(meta: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    failure_count = int(meta.get("failure_count") or 0)
    failed_channels = meta.get("failed_channels") if isinstance(meta.get("failed_channels"), list) else []
    if failure_count:
        hint = ", ".join(str(channel) for channel in failed_channels[:5]) or f"{failure_count} channels"
        diagnostics.append(
            {
                "code": "channel_failures",
                "severity": "warning",
                "message": f"{failure_count} channels failed during scan: {hint}.",
                "next_step": "Open scan.errors.log and fix access, username, invite-link, or FloodWait issues.",
            }
        )
    if int(meta.get("total_messages_collected") or 0) == 0:
        diagnostics.append(
            {
                "code": "no_messages_fetched",
                "severity": "failure",
                "message": "No Telegram messages were fetched for this monitor run.",
                "next_step": "Check source names, login/session state, scan window, and scan.errors.log.",
            }
        )
    return diagnostics


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
        "prefilter_keywords": DEFAULT_FAST_JOBS_PREFILTER_KEYWORDS,
        "semantic_max_messages": DEFAULT_FAST_JOBS_SEMANTIC_MAX_MESSAGES,
        "semantic_max_tokens": DEFAULT_FAST_JOBS_SEMANTIC_MAX_TOKENS,
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
        if "prefilter_keywords" in base_profile:
            item.setdefault("prefilter_keywords", base_profile["prefilter_keywords"])
        if "semantic_max_messages" in base_profile:
            item.setdefault("semantic_max_messages", base_profile["semantic_max_messages"])
        if "semantic_max_tokens" in base_profile:
            item.setdefault("semantic_max_tokens", base_profile["semantic_max_tokens"])
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


def parse_message_date(value: object) -> datetime | None:
    return monitor_state.parse_iso_datetime(value)


def source_ref_dates(scan_path: Path | None) -> dict[tuple[str, object], str]:
    if not scan_path or not scan_path.exists():
        return {}
    refs: dict[tuple[str, object], str] = {}
    with scan_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            channel = str(message.get("channel") or "").strip()
            msg_id = message.get("id")
            parsed = parse_message_date(message.get("date"))
            if channel and msg_id is not None and parsed is not None:
                stamped = parsed.isoformat().replace("+00:00", "Z")
                refs[(channel, msg_id)] = stamped
                refs[(channel, str(msg_id))] = stamped
    return refs


def annotate_items_with_source_freshness(items: list[dict[str, Any]], scan_path: Path | None) -> list[dict[str, Any]]:
    dates_by_ref = source_ref_dates(scan_path)
    if not dates_by_ref:
        return items
    annotated: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        dates = []
        for ref in item.get("source_message_refs") or []:
            if not isinstance(ref, dict):
                continue
            channel = str(ref.get("channel") or "").strip()
            msg_id = ref.get("id")
            if (channel, msg_id) in dates_by_ref:
                dates.append(dates_by_ref[(channel, msg_id)])
        if not dates:
            annotated.append(item)
            continue
        copy = dict(item)
        freshness = dict(copy.get("monitor_freshness") or {})
        freshness["freshest_source_at"] = max(dates)
        copy["monitor_freshness"] = freshness
        annotated.append(copy)
    return annotated


def parse_agent_stdout(completed: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    if not completed.stdout:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def run_json_command(cmd: list[str | Path]) -> tuple[int, dict[str, Any] | None, str]:
    completed = subprocess.run(
        [str(part) for part in cmd],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, parse_agent_stdout(completed), completed.stderr or ""


def report_command_for_scan_input(
    *,
    scan_input: Path,
    profile_file: Path,
    run_dir: Path,
    state_dir: Path,
    source_registry: Path | None,
    items_json: str | None,
    max_messages: int | None = None,
    max_tokens: int | None = None,
) -> list[str | Path]:
    report_output = run_dir / "report.md"
    html_output = run_dir / "report.html"
    cmd: list[str | Path] = [
        sys.executable,
        PROJECT_ROOT / "scripts" / "report.py",
        "--input",
        scan_input,
        "--profile",
        profile_file,
        "--output",
        report_output,
        "--html-output",
        html_output,
        "--state-dir",
        state_dir,
        "--format",
        "json",
    ]
    if source_registry and source_registry.exists():
        cmd.extend(["--source-registry", source_registry])
    if items_json:
        cmd.extend(["--items-json", items_json])
    if max_messages:
        cmd.extend(["--max-messages", str(max_messages)])
    if max_tokens:
        cmd.extend(["--max-tokens", str(max_tokens)])
    return cmd


def scan_command(
    *,
    run_dir: Path,
    source_args: list[str],
    hours: int,
    allow_incomplete: bool,
) -> list[str | Path]:
    scan_output = run_dir / "scan.jsonl"
    cmd: list[str | Path] = [
        sys.executable,
        PROJECT_ROOT / "scripts" / "scan.py",
        *source_args,
        "--hours",
        str(hours),
        "--output-dir",
        run_dir,
        "--output",
        scan_output,
        "--format",
        "json",
    ]
    if allow_incomplete:
        cmd.append("--allow-incomplete")
    return cmd


def daily_report_command(
    *,
    profile: dict[str, Any],
    profile_file: Path,
    run_dir: Path,
    state_dir: Path,
    source_args: list[str],
    hours: int,
    items_json: str | None,
    allow_incomplete: bool,
    max_messages: int | None = None,
) -> list[str | Path]:
    report_output = run_dir / "report.md"
    cmd: list[str | Path] = [
        sys.executable,
        PROJECT_ROOT / "scripts" / "daily_report.py",
        *source_args,
        "--profile",
        profile_file,
        "--hours",
        str(hours),
        "--output-dir",
        run_dir,
        "--report-output",
        report_output,
        "--html",
        "--state-dir",
        state_dir,
        "--format",
        "json",
    ]
    if profile.get("next_scan_note"):
        cmd.extend(["--next-scan-note", str(profile["next_scan_note"])])
    if items_json:
        cmd.extend(["--items-json", items_json])
    if allow_incomplete:
        cmd.append("--allow-incomplete")
    if max_messages:
        cmd.extend(["--max-messages", str(max_messages)])
    return cmd


def source_registry_from_args(source_args: list[str]) -> Path | None:
    try:
        index = source_args.index("--source-registry")
    except ValueError:
        return None
    if index + 1 >= len(source_args):
        return None
    return Path(source_args[index + 1])


def prefilter_keywords(profile: dict[str, Any]) -> list[str]:
    raw_keywords = profile.get("prefilter_keywords") or []
    if isinstance(raw_keywords, str):
        raw_keywords = [raw_keywords]
    if not isinstance(raw_keywords, list):
        return []
    keywords: list[str] = []
    seen: set[str] = set()
    for keyword in raw_keywords:
        text = str(keyword or "").strip()
        marker = text.casefold()
        if not text or marker in seen:
            continue
        keywords.append(text)
        seen.add(marker)
    return keywords


def semantic_max_messages(profile: dict[str, Any]) -> int | None:
    raw_value = profile.get("semantic_max_messages")
    if raw_value in {None, ""}:
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    # The fast interrupt lane should keep LLM batches small. If this is removed,
    # 30+ keyword hits can push Flash/Pro into multi-second tail latency even
    # when prompt cache hits; use a separate backfill/audit lane for exhaustive
    # catch-up instead of silently widening high-frequency alert batches.
    return value if value > 0 else None


def semantic_max_tokens(profile: dict[str, Any]) -> int | None:
    raw_value = profile.get("semantic_max_tokens")
    if raw_value in {None, ""}:
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def message_text_for_prefilter(message: dict[str, Any]) -> str:
    pieces: list[str] = []
    for field in PREFILTER_TEXT_FIELDS:
        value = message.get(field)
        if isinstance(value, str):
            pieces.append(value)
        elif isinstance(value, list):
            pieces.extend(str(item) for item in value if item)
    return "\n".join(pieces)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def keyword_prefilter_matches(
    scan_path: Path,
    keywords: list[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    lowered = [(keyword, keyword.casefold()) for keyword in keywords if keyword.strip()]
    counts = {keyword: 0 for keyword, _ in lowered}
    matches: list[dict[str, Any]] = []
    for message in load_jsonl(scan_path):
        haystack = message_text_for_prefilter(message).casefold()
        matched = [keyword for keyword, marker in lowered if marker and marker in haystack]
        if not matched:
            continue
        for keyword in matched:
            counts[keyword] += 1
        copy = dict(message)
        # This is a cheap gate, not a ranking signal. Downstream LLM/report rules
        # still decide whether the item is high-value enough to interrupt.
        copy["monitor_prefilter"] = {"matched_keywords": matched}
        matches.append(copy)
    return matches, {keyword: count for keyword, count in counts.items() if count > 0}


def write_prefiltered_scan(
    *,
    source_scan_path: Path,
    run_dir: Path,
    matches: list[dict[str, Any]],
    keywords: list[str],
    keyword_counts: dict[str, int],
) -> Path:
    filtered_path = run_dir / "prefiltered-scan.jsonl"
    filtered_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in matches),
        encoding="utf-8",
    )
    meta_path = source_scan_path.with_suffix(".meta.json")
    filtered_meta = {}
    if meta_path.exists():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                filtered_meta = loaded
        except json.JSONDecodeError:
            filtered_meta = {}
    original_total = filtered_meta.get("total_messages_collected")
    filtered_meta["output_path"] = str(filtered_path)
    filtered_meta["total_messages_collected"] = len(matches)
    filtered_meta["prefilter"] = {
        "enabled": True,
        "source_scan_path": str(source_scan_path),
        "source_total_messages_collected": original_total,
        "keyword_count": len(keywords),
        "matched_count": len(matches),
        "matched_keywords": keyword_counts,
    }
    filtered_path.with_suffix(".meta.json").write_text(
        json.dumps(filtered_meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return filtered_path


def delivery_targets_for_profile(config: MonitorConfig, profile: dict[str, Any]) -> list[dict[str, Any]]:
    target_ids = profile.get("delivery_targets") or profile.get("delivery_target") or []
    if isinstance(target_ids, str):
        target_ids = [target_ids]
    targets = [config.delivery_targets[item] for item in target_ids if item in config.delivery_targets]
    if targets:
        return targets
    return [target for target in config.delivery_targets.values() if target.get("type") == "telegram_bot"]


def run_delivery(
    *,
    conn,
    run_id_value: str,
    profile_id: str,
    cards: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    mode: str,
    alert_rule: dict[str, Any],
    delivery_enabled: bool,
    report_path: str | None,
    dashboard_url: str,
) -> tuple[int, list[dict[str, Any]]]:
    suppressed_alert_keys = (
        monitor_state.sent_alert_suppression_keys(conn, profile_id=profile_id) if conn is not None else set()
    )
    candidates = monitor_state.alert_candidates(
        cards,
        alert_rule=alert_rule,
        suppressed_alert_keys=suppressed_alert_keys,
    )
    events: list[dict[str, Any]] = []
    if mode == "off" or not delivery_enabled:
        return len(candidates), events
    for card in candidates:
        item = card.get("item") if isinstance(card.get("item"), dict) else {}
        for target in targets:
            if target.get("type") != "telegram_bot" or not target.get("enabled", False):
                continue
            text = delivery.build_telegram_alert_text(
                item=item,
                card=card,
                report_url=report_path,
                dashboard_url=dashboard_url,
            )
            attempt = delivery.send_telegram_bot_message(
                target_id=target["id"],
                chat_id=str(target.get("chat_id") or ""),
                text=text,
                mode=mode,
            )
            event = monitor_state.record_alert_event(
                conn,
                run_id=run_id_value,
                card_id=card["card_id"],
                profile_id=profile_id,
                target_id=target["id"],
                status=attempt.status,
                payload={
                    "text": text,
                    "decision_status": card.get("decision_status"),
                    "item_key": card.get("item_key"),
                },
                delivery_attempt=attempt.to_dict(),
            )
            events.append(event)
    return len(candidates), events


def write_latest_pointer(output_dir: Path, manifest_path: Path) -> None:
    latest = output_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    pointer = latest / "run-manifest.path"
    pointer.write_text(str(manifest_path), encoding="utf-8")


def run_profile(args: argparse.Namespace) -> int:
    config_path = root_path(args.config)
    try:
        config = load_config(config_path)
    except ValueError as exc:
        agent_cli.emit_error(
            args,
            code="profile_run_config_invalid",
            message=str(exc),
            retryable=False,
            next_step="Fix .tgcs/profiles.toml or pass --config with a valid profile_run_config_v1 file.",
        )
        return agent_cli.EXIT_VALIDATION
    profile = config.profiles.get(args.profile_id)
    if not profile:
        agent_cli.emit_error(
            args,
            code="profile_not_found",
            message=f"Profile id not found: {args.profile_id}",
            retryable=False,
            next_step="Add the profile to .tgcs/profiles.toml or choose an existing profile id.",
        )
        return agent_cli.EXIT_VALIDATION
    if not profile.get("enabled", True):
        agent_cli.emit_error(
            args,
            code="profile_disabled",
            message=f"Profile is disabled: {args.profile_id}",
            retryable=False,
            next_step="Enable the profile before running it.",
        )
        return agent_cli.EXIT_VALIDATION

    started_at = utc_now()
    current_run_id = args.run_id or run_id()
    output_dir = root_path(args.output_dir or config.defaults.get("output_dir", "output"))
    run_dir = output_dir / "runs" / current_run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        agent_cli.emit_error(
            args,
            code="run_id_exists",
            message=f"Run output already exists: {run_dir}",
            retryable=False,
            next_step="Choose a different --run-id or let monitor.py generate one.",
        )
        return agent_cli.EXIT_VALIDATION
    state_dir = root_path(args.state_dir or config.defaults.get("state_dir", ".tgcs/state"))
    db_path = root_path(args.db or config.defaults.get("database", ".tgcs/tgcs.db"))
    dashboard_url = args.dashboard_url or str(config.defaults.get("dashboard_url") or DEFAULT_DASHBOARD_URL)
    conn = monitor_state.connect(db_path)
    profile = monitor_state.apply_profile_runtime_overrides(conn, profile)
    profile_file = profile_path(profile)
    if not profile_file.exists():
        conn.close()
        agent_cli.emit_error(
            args,
            code="profile_file_not_found",
            message=f"Profile file not found: {profile_file}",
            retryable=False,
            next_step="Create the local profile copy or fix the profile path.",
        )
        return agent_cli.EXIT_VALIDATION

    source_registry = root_path(profile.get("source_registry") or ".tgcs/sources.json")
    scan_window_hours = effective_scan_hours(args, profile)
    keywords = prefilter_keywords(profile)
    profile_prefilter_enabled = bool(profile.get("prefilter_enabled")) and bool(keywords)
    prefilter_context: dict[str, Any] = {
        "enabled": profile_prefilter_enabled and not args.scan_input,
        "keyword_count": len(keywords),
        "matched_count": None,
        "semantic_stage": "disabled",
    }
    if args.scan_input:
        # scan-input is a deliberate replay/debug lane. Keep the manifest
        # explicit so fast-lane evals do not mistake this path for a cheap
        # keyword-gated monitor run.
        prefilter_context["semantic_stage"] = "bypassed_scan_input" if profile_prefilter_enabled else "not_applicable"
        if profile_prefilter_enabled:
            prefilter_context["bypass_reason"] = "scan_input"
    commands_executed: list[list[str | Path]] = []
    cmd: list[str | Path] = []
    exit_code = 0
    payload: dict[str, Any] | None = None
    stderr = ""
    report_data: dict[str, Any] = {}
    status = "complete"
    report_path: Path | None = None
    html_path: Path | None = None
    scan_path: Path | None = None
    raw_scan_path: Path | None = None
    items: list[dict[str, Any]] = []
    semantic_limit = semantic_max_messages(profile)
    token_limit = semantic_max_tokens(profile)

    if args.scan_input:
        cmd = report_command_for_scan_input(
            scan_input=root_path(args.scan_input),
            profile_file=profile_file,
            run_dir=run_dir,
            state_dir=state_dir,
            source_registry=source_registry,
            items_json=args.items_json,
            max_messages=semantic_limit,
            max_tokens=token_limit,
        )
        commands_executed.append(cmd)
        exit_code, payload, stderr = run_json_command(cmd)
    else:
        source_args = source_input_args(profile, run_dir)
        if not source_args:
            conn.close()
            agent_cli.emit_error(
                args,
                code="source_input_missing",
                message="Missing source input for monitor run.",
                retryable=False,
                next_step="Create .tgcs/sources.json, configure source_registry, or provide a channel list.",
            )
            return agent_cli.EXIT_VALIDATION
        if profile.get("prefilter_enabled") and keywords and not args.items_json:
            prefilter_context["semantic_stage"] = "scan_pending"
            cmd = scan_command(
                run_dir=run_dir,
                source_args=source_args,
                hours=scan_window_hours,
                allow_incomplete=args.allow_incomplete,
            )
            raw_scan_path = run_dir / "scan.jsonl"
            scan_path = raw_scan_path
            commands_executed.append(cmd)
            exit_code, payload, stderr = run_json_command(cmd)
            scan_data = payload.get("data", {}) if payload and payload.get("ok") else {}
            if scan_data.get("output_path"):
                raw_scan_path = root_path(scan_data.get("output_path"), PROJECT_ROOT)
            scan_path = raw_scan_path
            prefilter_context["raw_scan_path"] = relative_to_root(raw_scan_path) if raw_scan_path else None
            if exit_code == 0 and raw_scan_path and raw_scan_path.exists():
                matches, keyword_counts = keyword_prefilter_matches(raw_scan_path, keywords)
                prefilter_context.update(
                    {
                        "matched_count": len(matches),
                        "matched_keywords": keyword_counts,
                        "raw_message_count": scan_data.get("message_count"),
                    }
                )
                if not matches:
                    status = "prefilter_no_match"
                    prefilter_context["semantic_stage"] = "skipped_no_keyword_match"
                    report_data = {"status": status, "source_health": scan_data.get("source_health")}
                else:
                    filtered_scan_path = write_prefiltered_scan(
                        source_scan_path=raw_scan_path,
                        run_dir=run_dir,
                        matches=matches,
                        keywords=keywords,
                        keyword_counts=keyword_counts,
                    )
                    scan_path = filtered_scan_path
                    prefilter_context["filtered_scan_path"] = relative_to_root(filtered_scan_path)
                    prefilter_context["semantic_stage"] = "report_pending"
                    effective_registry = source_registry_from_args(source_args) or source_registry
                    cmd = report_command_for_scan_input(
                        scan_input=filtered_scan_path,
                        profile_file=profile_file,
                        run_dir=run_dir,
                        state_dir=state_dir,
                        source_registry=effective_registry,
                        items_json=args.items_json,
                        max_messages=semantic_limit,
                        max_tokens=token_limit,
                    )
                    commands_executed.append(cmd)
                    exit_code, payload, stderr = run_json_command(cmd)
            else:
                status = "failed"
                prefilter_context["semantic_stage"] = "scan_failed"
        else:
            if profile.get("prefilter_enabled") and keywords and args.items_json:
                prefilter_context["semantic_stage"] = "bypassed_items_json"
            cmd = daily_report_command(
                profile=profile,
                profile_file=profile_file,
                run_dir=run_dir,
                state_dir=state_dir,
                source_args=source_args,
                hours=scan_window_hours,
                items_json=args.items_json,
                allow_incomplete=args.allow_incomplete,
                max_messages=semantic_limit,
            )
            commands_executed.append(cmd)
            exit_code, payload, stderr = run_json_command(cmd)

    if payload and payload.get("ok"):
        report_data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
    if status != "prefilter_no_match":
        status = report_data.get("status") or ("complete" if exit_code == 0 else "failed")
    if prefilter_context.get("semantic_stage") == "report_pending":
        prefilter_context["semantic_stage"] = (
            "agent_extraction_required"
            if status == "agent_extraction_required"
            else "report_ran"
            if exit_code == 0
            else "report_failed"
        )
    report_path = root_path(report_data.get("report_path"), PROJECT_ROOT) if report_data.get("report_path") else None
    html_path = root_path(report_data.get("html_path"), PROJECT_ROOT) if report_data.get("html_path") else None
    if report_data.get("scan_path"):
        scan_path = root_path(report_data.get("scan_path"), PROJECT_ROOT)
    elif args.scan_input:
        scan_path = root_path(args.scan_input)
    items = report_data.get("items") if isinstance(report_data.get("items"), list) else []
    items = annotate_items_with_source_freshness(items, scan_path)

    monitor_state.upsert_profile(conn, {**profile, "path": str(profile_file)})
    for target in config.delivery_targets.values():
        monitor_state.upsert_delivery_target(conn, target)
    monitor_state.record_run(
        conn,
        {
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "run_id": current_run_id,
            "profile_id": args.profile_id,
            "status": "running",
            "started_at": started_at,
            "completed_at": None,
            "artifacts": [],
        },
    )

    cards: list[dict[str, Any]] = []
    alert_count = 0
    alert_events: list[dict[str, Any]] = []
    if exit_code == 0 and status != "agent_extraction_required":
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id=args.profile_id,
            run_id=current_run_id,
            items=items,
            report_path=relative_to_root(report_path) if report_path else None,
            dashboard_url=dashboard_url,
        )
        delivery_enabled, delivery_suppressed_reason = delivery_enabled_for_profile(profile)
        alert_count, alert_events = run_delivery(
            conn=conn,
            run_id_value=current_run_id,
            profile_id=args.profile_id,
            cards=cards,
            targets=delivery_targets_for_profile(config, profile),
            mode=args.delivery_mode,
            alert_rule=alert_rule_for_profile(profile),
            delivery_enabled=delivery_enabled,
            report_path=relative_to_root(report_path) if report_path else None,
            dashboard_url=dashboard_url,
        )
    else:
        delivery_enabled, delivery_suppressed_reason = delivery_enabled_for_profile(profile)

    completed_at = utc_now()
    manifest_diagnostics = report_data.get("diagnostics") if isinstance(report_data.get("diagnostics"), list) else []
    if not manifest_diagnostics:
        manifest_diagnostics = diagnostics_from_scan_meta(load_scan_meta(raw_scan_path or scan_path, run_dir))
    artifacts = []
    if raw_scan_path and raw_scan_path.exists() and raw_scan_path != scan_path:
        artifacts.append(artifact(raw_scan_path, "raw_scan"))
    for path, kind in ((scan_path, "scan"), (report_path, "report_markdown"), (html_path, "report_html")):
        if path and path.exists():
            artifacts.append(artifact(path, kind))
    meta_path, errors_path = scan_sidecar_paths(raw_scan_path or scan_path, run_dir)
    if meta_path.exists():
        artifacts.append(artifact(meta_path, "scan_meta"))
    if errors_path.exists():
        artifacts.append(artifact(errors_path, "scan_errors"))
    manifest = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": current_run_id,
        "profile_id": args.profile_id,
        "profile_path": relative_to_root(profile_file),
        "profile_hash": file_hash(profile_file),
        "source_registry_path": relative_to_root(source_registry) if source_registry.exists() else None,
        "source_registry_hash": file_hash(source_registry) if source_registry.exists() else None,
        "scan_window": {"hours": scan_window_hours},
        "source_filters": {
            "topics": profile.get("source_topics") or profile.get("topics") or [],
            "source_ids": profile.get("source_ids") or [],
        },
        "alert_rule": alert_rule_for_profile(profile),
        "semantic": {"max_messages": semantic_limit, "max_tokens": token_limit},
        "alert_schedule": {
            "mode": profile.get("alert_schedule_mode") or "work_hours",
            "delivery_enabled": delivery_enabled,
            "suppressed_reason": "" if delivery_enabled else delivery_suppressed_reason,
        },
        "prefilter": prefilter_context,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "artifacts": artifacts,
        "report_status": status,
        "alert_count": alert_count,
        "review_card_count": len(cards),
        "diagnostics": manifest_diagnostics,
        "error_summary": None if exit_code == 0 else {"exit_code": exit_code, "stderr": stderr[-2000:]},
        "llm": report_data.get("llm"),
        "delivery_attempts": [event["delivery_attempt"] for event in alert_events],
        "command": [str(part) for part in cmd],
        "commands": [[str(part) for part in command] for command in commands_executed],
    }
    manifest_path = run_dir / "run-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_latest_pointer(output_dir, manifest_path)
    monitor_state.record_run(conn, manifest)
    conn.close()

    data = {
        "schema_version": "monitor_run_result_v1",
        "status": status,
        "run_id": current_run_id,
        "manifest_path": relative_to_root(manifest_path),
        "db_path": relative_to_root(db_path),
        "report_path": relative_to_root(report_path) if report_path else None,
        "html_path": relative_to_root(html_path) if html_path else None,
        "review_card_count": len(cards),
        "alert_count": alert_count,
        "prefilter": prefilter_context,
        "semantic": {"max_messages": semantic_limit, "max_tokens": token_limit},
        "diagnostics": manifest_diagnostics,
        "llm": report_data.get("llm"),
        "delivery_attempts": [event["delivery_attempt"] for event in alert_events],
        "extraction_request_path": report_data.get("extraction_request_path") or report_data.get("request_path"),
        "items_output_path": report_data.get("items_output_path"),
    }
    if agent_cli.is_json_format(args):
        if exit_code == 0:
            agent_cli.print_json(agent_cli.envelope_success(data))
        else:
            agent_cli.print_json(
                agent_cli.envelope_error(
                    code="monitor_run_failed",
                    message=f"Monitor run failed with exit code {exit_code}.",
                    retryable=exit_code in {agent_cli.EXIT_RUNTIME, agent_cli.EXIT_INCOMPLETE},
                    next_step="Inspect the run manifest and rerun the failing scan/report command if needed.",
                    details=data,
                )
            )
    else:
        print(f"Monitor run saved: {manifest_path}")
    return exit_code


def test_telegram_bot(args: argparse.Namespace) -> int:
    chat_id = args.chat_id or ""
    if not chat_id:
        agent_cli.emit_error(
            args,
            code="telegram_bot_chat_id_missing",
            message="Telegram bot chat_id is required for delivery test.",
            retryable=False,
            next_step="Pass --chat-id or add a chat_id to .tgcs/profiles.toml.",
        )
        return agent_cli.EXIT_VALIDATION
    attempt = delivery.send_telegram_bot_message(
        target_id=args.target_id,
        chat_id=chat_id,
        text="TGCS delivery test.",
        mode=args.delivery_mode,
    )
    if agent_cli.is_json_format(args):
        agent_cli.print_json(agent_cli.envelope_success({"attempt": attempt.to_dict()}))
    else:
        print(f"Telegram bot delivery test: {attempt.status}")
    return agent_cli.EXIT_SUCCESS if attempt.ok else agent_cli.EXIT_RUNTIME


def write_default_config(args: argparse.Namespace) -> int:
    config_path = root_path(args.config)
    if config_path.exists() and not args.force:
        if not agent_cli.is_json_format(args):
            print(f"Profile run config already exists: {config_path}")
        return agent_cli.EXIT_SUCCESS
    config_path.parent.mkdir(parents=True, exist_ok=True)
    text = """schema_version = "profile_run_config_v1"

[defaults]
output_dir = "output"
state_dir = ".tgcs/state"
database = ".tgcs/tgcs.db"
dashboard_url = "http://127.0.0.1:8765"

[[profiles]]
id = "market-news"
path = "profiles/templates/market-news.md"
enabled = true
timezone = "Asia/Shanghai"
work_interval_minutes = 120
off_hours_interval_minutes = 360
scan_window_hours = 24
source_registry = ".tgcs/sources.json"
channel_list = "channel_lists/example.txt"
source_topics = ["market-news"]
alert_rule = "high_new_or_changed"
alert_schedule_mode = "work_hours"
delivery_targets = ["telegram-bot-default"]
dashboard_visible = true

[[profiles]]
id = "jobs-fast"
path = "profiles/templates/jobs.md"
enabled = true
timezone = "Asia/Shanghai"
work_start = "09:00"
work_end = "23:00"
work_interval_minutes = 15
off_hours_interval_minutes = 60
scan_window_hours = 2
source_registry = ".tgcs/sources.json"
channel_list = "channel_lists/example.txt"
source_topics = ["jobs"]
alert_rule = "high_new_or_changed"
alert_max_age_minutes = 60
alert_schedule_mode = "work_hours"
delivery_targets = ["telegram-bot-default"]
dashboard_visible = true
prefilter_enabled = true
# Keep high-frequency alert batches bounded; use a separate backfill/audit lane
# if you need exhaustive semantic extraction over a larger catch-up window.
semantic_max_messages = 20
semantic_max_tokens = 2000
prefilter_keywords = [
  "hiring",
  "we're hiring",
  "is hiring",
  "job opening",
  "open role",
  "remote",
  "apply",
  "frontend",
  "backend",
  "fullstack",
  "react",
  "typescript",
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
  "简历",
  "外包",
  "接活",
  "兼职",
  "私活",
  "项目",
  "预算",
]

[[delivery]]
id = "telegram-bot-default"
type = "telegram_bot"
enabled = false
chat_id = ""
"""
    config_path.write_text(text, encoding="utf-8")
    data = {"schema_version": PROFILE_RUN_CONFIG_SCHEMA_VERSION, "config_path": relative_to_root(config_path)}
    if agent_cli.is_json_format(args):
        agent_cli.print_json(agent_cli.envelope_success(data))
    else:
        print(f"Profile run config written: {config_path}")
    return agent_cli.EXIT_SUCCESS


def export_feedback(args: argparse.Namespace) -> int:
    db_path = root_path(args.db)
    output_path = root_path(args.output)
    conn = monitor_state.connect(db_path)
    try:
        entries = monitor_state.export_feedback_entries(conn)
    finally:
        conn.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    output_path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

    data = {
        "schema_version": "feedback_export_result_v1",
        "feedback_count": len(entries),
        "output_path": relative_to_root(output_path),
    }
    if agent_cli.is_json_format(args):
        agent_cli.print_json(agent_cli.envelope_success(data))
    else:
        print(f"Feedback exported: {output_path} ({len(entries)} rows)")
    return agent_cli.EXIT_SUCCESS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run v0.5-alpha TGCS profile monitors.", allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-config", help="Write a starter .tgcs/profiles.toml.")
    init.add_argument("--config", default=".tgcs/profiles.toml")
    init.add_argument("--force", action="store_true")
    agent_cli.add_format_argument(init)
    init.set_defaults(func=write_default_config)

    run = subparsers.add_parser("run", help="Run one profile monitor.")
    run.add_argument("--profile-id", default=DEFAULT_PROFILE_ID)
    run.add_argument("--config", default=".tgcs/profiles.toml")
    run.add_argument("--db")
    run.add_argument("--output-dir")
    run.add_argument("--state-dir")
    run.add_argument("--run-id")
    run.add_argument("--hours", type=int)
    run.add_argument("--scan-input", type=Path, help="Use an existing JSONL scan file instead of scanning Telegram.")
    run.add_argument("--items-json", help="Use semantic_items_v1 JSON for report generation.")
    run.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD_URL)
    run.add_argument("--delivery-mode", choices=("off", "dry-run", "live"), default="dry-run")
    run.add_argument("--allow-incomplete", action="store_true")
    agent_cli.add_format_argument(run)
    run.set_defaults(func=run_profile)

    feedback_export = subparsers.add_parser(
        "feedback-export",
        help="Export dashboard feedback as reusable report feedback JSONL.",
    )
    feedback_export.add_argument("--db", default=".tgcs/tgcs.db")
    feedback_export.add_argument("--output", default="output/dashboard-feedback.jsonl")
    agent_cli.add_format_argument(feedback_export)
    feedback_export.set_defaults(func=export_feedback)

    delivery_parser = subparsers.add_parser("delivery-test", help="Test a delivery adapter.")
    delivery_subparsers = delivery_parser.add_subparsers(dest="delivery_command", required=True)
    bot = delivery_subparsers.add_parser("telegram-bot", help="Send or dry-run a Telegram bot test.")
    bot.add_argument("--target-id", default="telegram-bot-default")
    bot.add_argument("--chat-id")
    bot.add_argument("--delivery-mode", choices=("dry-run", "live"), default="dry-run")
    agent_cli.add_format_argument(bot)
    bot.set_defaults(func=test_telegram_bot)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
