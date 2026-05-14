"""Quickstart status projection for starter workflows."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tomllib
from pathlib import Path
from typing import Any

from scripts.tgcs_launchers import (
    CONFIG_NAME,
    DEFAULT_TGCLI_CONFIG_PATH,
    DEFAULT_SESSION_PATH,
    PROFILES_CONFIG_NAME,
    _local_path,
)



def _quickstart_check(check_id: str, label: str, status: str, detail: str, command: str = "") -> dict[str, str]:
    payload = {
        "check_id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
    }
    if command:
        payload["command"] = command
    return payload



def _jobs_sources_ready(registry_path: Path) -> bool:
    if not registry_path.exists():
        return False
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        return False
    for source in sources:
        if not isinstance(source, dict) or source.get("enabled") is False:
            continue
        topics = source.get("topics")
        if isinstance(topics, list) and any(str(topic).casefold() == "jobs" for topic in topics):
            return True
    return False



def _telegram_credentials_ready(config_path: Path | None = None) -> bool:
    config_path = config_path or DEFAULT_TGCLI_CONFIG_PATH
    env_id = os.environ.get("TELEGRAM_API_ID")
    env_hash = os.environ.get("TELEGRAM_API_HASH")
    if env_id and env_hash:
        try:
            int(env_id)
            return True
        except ValueError:
            return False
    if not config_path.exists():
        return False
    try:
        with config_path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    api_id = payload.get("api_id") if isinstance(payload, dict) else None
    api_hash = str(payload.get("api_hash") or "") if isinstance(payload, dict) else ""
    return bool(api_id and api_hash and api_hash != "your_api_hash_here")



def _telegram_session_ready(session_path: Path | None = None) -> bool:
    session_path = session_path or DEFAULT_SESSION_PATH
    try:
        return bool(session_path.exists() and session_path.read_text(encoding="utf-8").strip())
    except OSError:
        return False



def _monitor_has_runs(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False
    return bool(row and int(row[0] or 0) > 0)



def quickstart_jobs_status() -> dict[str, Any]:
    config_path = _local_path(CONFIG_NAME)
    profiles_config_path = _local_path(PROFILES_CONFIG_NAME)
    registry_path = _local_path("sources.json")
    db_path = _local_path("tgcs.db")
    local_defaults = config_path.exists() and profiles_config_path.exists()
    jobs_sources = _jobs_sources_ready(registry_path)
    credentials = _telegram_credentials_ready()
    session = _telegram_session_ready()
    has_runs = _monitor_has_runs(db_path)

    if not local_defaults:
        stage = "init_required"
        next_command = "tgcs init --starter jobs"
        next_app_step = "Open Signal Desk Start; first launch prepares the jobs starter files automatically."
        why = "Local .tgcs defaults are missing."
    elif not jobs_sources:
        stage = "source_import_required"
        next_command = "tgcs dashboard"
        next_app_step = "Open Signal Desk Settings > Sources, then use the starter set or Source assistant."
        why = "The local source registry does not yet have enabled jobs-topic sources; use Settings > Sources to install or edit them."
    elif not credentials:
        stage = "doctor_required"
        next_command = "tgcs doctor --profile jobs"
        next_app_step = "Open Signal Desk Start and save your Telegram app ID/hash."
        why = "Telegram API credentials are not visible to the local scanner."
    elif not session:
        stage = "login_required"
        next_command = "tgcs login"
        next_app_step = "Open Signal Desk Start and finish Telegram login with the code sent to your account."
        why = "Telegram credentials exist, but the local session file is missing."
    elif not has_runs:
        stage = "first_review_required"
        next_command = "tgcs monitor run --profile-id jobs-fast --delivery-mode live"
        next_app_step = "Open Signal Desk Start and run the first AI review."
        why = "Jobs sources and Telegram login are ready; run one AI review so Signal Desk can create Review cards and send alerts when notifications are enabled."
    else:
        stage = "dashboard_ready"
        next_command = "tgcs dashboard"
        next_app_step = "Open Signal Desk Review and triage the latest Inbox cards."
        why = "A previous monitor run exists; open the review inbox."

    def status_for(check_id: str) -> str:
        order = [
            ("local_defaults", local_defaults),
            ("jobs_sources", jobs_sources),
            ("telegram_credentials", credentials),
            ("telegram_login", session),
            ("first_ai_review", has_runs),
        ]
        for current_id, is_done in order:
            if current_id == check_id:
                return "done" if is_done else "next"
            if not is_done:
                return "todo"
        return "next" if check_id == "dashboard" else "done"

    checks = [
        _quickstart_check(
            "local_defaults",
            "Local defaults",
            status_for("local_defaults"),
            "Create .tgcs config, profiles, and local source registry defaults.",
            "tgcs init --starter jobs",
        ),
        _quickstart_check(
            "jobs_sources",
            "Jobs sources",
            status_for("jobs_sources"),
            "Install the packaged starter set, then add/pause/remove real channels from Signal Desk Settings > Sources.",
            "tgcs init --starter jobs",
        ),
        _quickstart_check(
            "telegram_credentials",
            "Telegram credentials",
            status_for("telegram_credentials"),
            "Verify TELEGRAM_API_ID / TELEGRAM_API_HASH or ~/.config/tgcli/config.toml.",
            "tgcs doctor --profile jobs",
        ),
        _quickstart_check(
            "telegram_login",
            "Telegram login",
            status_for("telegram_login"),
            "Create the local MTProto session without scanning channels.",
            "tgcs login",
        ),
        _quickstart_check(
            "first_ai_review",
            "First AI review",
            status_for("first_ai_review"),
            "Run jobs-fast once so Signal Desk can create Review cards and send enabled Telegram alerts.",
            "tgcs monitor run --profile-id jobs-fast --delivery-mode live",
        ),
        _quickstart_check(
            "dashboard",
            "Review inbox",
            status_for("dashboard"),
            "Open the local dashboard after at least one monitor run exists.",
            "tgcs dashboard",
        ),
    ]
    return {
        "schema_version": "tgcs_quickstart_v1",
        "vertical": "jobs",
        "label": "Developer Opportunity quickstart",
        "stage": stage,
        "next_command": next_command,
        "next_app_step": next_app_step,
        "why": why,
        "checks": checks,
    }



def run_quickstart(args: argparse.Namespace) -> int:
    if args.vertical != "jobs":
        raise AssertionError(f"Unsupported quickstart vertical: {args.vertical}")
    payload = quickstart_jobs_status()
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(payload["label"])
    print(f"Stage: {payload['stage']}")
    print(f"Next: {payload['next_command']}")
    print(f"App: {payload['next_app_step']}")
    print(f"Why: {payload['why']}")
    print("Checklist:")
    for check in payload["checks"]:
        print(f"- {check['label']}: {check['status']}")
    return 0
