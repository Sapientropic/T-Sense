"""First-run local project setup for tgcs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.tgcs_launchers import (
    CONFIG_NAME,
    LOCAL_DIR,
    PROFILES_CONFIG_NAME,
    _default_output_dir,
    _default_state_dir,
    _local_path,
    _python,
    _root_path,
    _run,
    _script,
    _asset_path,
)



INIT_STARTERS = {
    "default": {
        "profile": "market-news",
        "channel_list": "channel_lists/market-news.txt",
        "topics": ["market-news"],
    },
    "jobs": {
        "profile": "jobs",
        "channel_list": "channel_lists/jobs.txt",
        "topics": ["jobs"],
    },
}



def _print_init_next_steps(starter: str = "default") -> None:
    print("Local project defaults ready.")
    print("- Profiles: market-news, jobs-fast")
    if starter == "jobs":
        print("- Developer Opportunity starter is ready.")
    print("- Open Signal Desk: tgcs dashboard")
    print("- Start: generate the demo report, then create or select your monitor goal.")
    print("- Manage sources: Signal Desk Settings > Sources (starter set, public links, or Telegram folders).")
    if starter == "jobs":
        print("- Developer Opportunity reviews can be run from Start after Telegram is connected.")
    print("- Advanced CLI users: tgcs --help")



def _write_default_config(
    path: Path,
    *,
    force: bool = False,
    profile: str = "market-news",
    channel_list: str = "channel_lists/example.txt",
) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'channel_list = "{channel_list}"',
                'source_registry = ".tgcs/sources.json"',
                'output_dir = "output"',
                'state_dir = ".tgcs/state"',
                "",
            ]
        ),
        encoding="utf-8",
    )



def _write_default_profiles_config(path: Path, *, force: bool = False) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                'schema_version = "profile_run_config_v1"',
                "",
                "[defaults]",
                'output_dir = "output"',
                'state_dir = ".tgcs/state"',
                'database = ".tgcs/tgcs.db"',
                'dashboard_url = "http://127.0.0.1:8765"',
                "",
                "[[profiles]]",
                'id = "market-news"',
                'path = "profiles/templates/market-news.md"',
                "enabled = true",
                'timezone = "Asia/Shanghai"',
                "work_interval_minutes = 120",
                "off_hours_interval_minutes = 360",
                "scan_window_hours = 24",
                'source_registry = ".tgcs/sources.json"',
                'channel_list = "channel_lists/example.txt"',
                'source_topics = ["market-news"]',
                'alert_rule = "high_new_or_changed"',
                'alert_schedule_mode = "work_hours"',
                'delivery_targets = ["telegram-bot-default"]',
                "dashboard_visible = true",
                "",
                "[[profiles]]",
                'id = "jobs-fast"',
                'path = "profiles/templates/jobs.md"',
                "enabled = true",
                'timezone = "Asia/Shanghai"',
                'work_start = "09:00"',
                'work_end = "23:00"',
                "work_interval_minutes = 15",
                "off_hours_interval_minutes = 60",
                "scan_window_hours = 2",
                'source_registry = ".tgcs/sources.json"',
                'channel_list = "channel_lists/example.txt"',
                'source_topics = ["jobs"]',
                'alert_rule = "high_new_or_changed"',
                "alert_max_age_minutes = 60",
                'alert_schedule_mode = "work_hours"',
                'delivery_targets = ["telegram-bot-default"]',
                "dashboard_visible = true",
                "prefilter_enabled = true",
                "allow_partial_source_failures = true",
                "scan_concurrency = 3",
                "scan_delay_seconds = 0.2",
                "semantic_max_messages = 40",
                "semantic_max_tokens = 6000",
                "semantic_batch_size = 20",
                "semantic_concurrency = 2",
                "prefilter_keywords = [\"hiring\", \"we're hiring\", \"is hiring\", \"job opening\", \"open role\", \"remote\", \"apply\", \"frontend\", \"backend\", \"fullstack\", \"react\", \"typescript\", \"engineer\", \"developer\", \"freelance\", \"contract\", \"contractor\", \"gig\", \"bounty\", \"paid project\", \"mini app\", \"mini apps\", \"telegram mini app\", \"ton\", \"usdt\", \"budget\", \"招聘\", \"招人\", \"岗位\", \"职位\", \"远程\", \"外包\", \"兼职\", \"私活\", \"项目\", \"预算\"]",
                "",
                "[[delivery]]",
                'id = "telegram-bot-default"',
                'type = "telegram_bot"',
                "enabled = false",
                'chat_id = ""',
                "",
            ]
        ),
        encoding="utf-8",
    )



def run_init(args: argparse.Namespace) -> int:
    starter = INIT_STARTERS[args.starter]
    config_path = _local_path(CONFIG_NAME)
    profiles_config_path = _local_path(PROFILES_CONFIG_NAME)
    _local_path().mkdir(parents=True, exist_ok=True)
    _default_output_dir({}).mkdir(parents=True, exist_ok=True)
    _default_state_dir({}).mkdir(parents=True, exist_ok=True)
    _write_default_config(
        config_path,
        force=args.force,
        profile=str(starter["profile"]),
        channel_list=str(starter["channel_list"]),
    )
    _write_default_profiles_config(profiles_config_path, force=args.force)

    registry = _root_path(args.source_registry or f"{LOCAL_DIR}/sources.json")
    channel_list = _asset_path(args.channel_list or str(starter["channel_list"]))
    topics = list(args.topic or starter["topics"])
    if registry.exists() and not args.force:
        if args.starter == "jobs":
            print(f"Local config ready: {config_path}")
            if not channel_list.exists():
                print(f"Source registry already exists: {registry}")
                print(f"Channel list not found, skipped source import: {channel_list}", file=sys.stderr)
                _print_init_next_steps(args.starter)
                return 0
            print(f"Source registry already exists, merging starter sources: {registry}")
        else:
            print(f"Local config ready: {config_path}")
            print(f"Source registry already exists: {registry}")
            _print_init_next_steps(args.starter)
            return 0
    if not channel_list.exists():
        print(f"Local config ready: {config_path}")
        print(f"Channel list not found, skipped source import: {channel_list}", file=sys.stderr)
        _print_init_next_steps(args.starter)
        return 0
    cmd: list[str | Path] = [
        _python(),
        _script("source_registry.py"),
        "import-list",
        channel_list,
        "--source-registry",
        registry,
    ]
    for topic in topics:
        cmd.extend(["--topic", str(topic)])
    code = _run(cmd)
    if code == 0:
        _print_init_next_steps(args.starter)
    return code
