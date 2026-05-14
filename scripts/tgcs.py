"""Human-oriented T-Sense CLI facade.

The implementation is split into launchers, setup, quickstart, and scheduler
modules.  This file remains the packaged `tgcs` console script and compatibility
surface for tests that patch project paths or subprocess behavior.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from scripts import tgcs_launchers as _launchers
    from scripts import tgcs_quickstart as _quickstart
    from scripts import tgcs_schedule as _schedule
    from scripts import tgcs_setup as _setup
except ModuleNotFoundError:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts import tgcs_launchers as _launchers
    from scripts import tgcs_quickstart as _quickstart
    from scripts import tgcs_schedule as _schedule
    from scripts import tgcs_setup as _setup

_EXPORTED_MODULES = (os, shutil, subprocess, sys)

PACKAGE_ROOT = _launchers.PACKAGE_ROOT
PROJECT_ROOT = _launchers.PROJECT_ROOT
LOCAL_DIR = _launchers.LOCAL_DIR
CONFIG_NAME = _launchers.CONFIG_NAME
PROFILES_CONFIG_NAME = _launchers.PROFILES_CONFIG_NAME
DEFAULT_PROFILE = _launchers.DEFAULT_PROFILE
DEFAULT_FEEDBACK_EXPORT_PATH = _launchers.DEFAULT_FEEDBACK_EXPORT_PATH
DEFAULT_TGCLI_CONFIG_PATH = _launchers.DEFAULT_TGCLI_CONFIG_PATH
DEFAULT_SESSION_PATH = _launchers.DEFAULT_SESSION_PATH
SCHEDULER_LAUNCHD_LABEL = _schedule.SCHEDULER_LAUNCHD_LABEL
SCHEDULER_SYSTEMD_NAME = _schedule.SCHEDULER_SYSTEMD_NAME
PROFILE_ALIASES = _launchers.PROFILE_ALIASES
INIT_STARTERS = _setup.INIT_STARTERS


def _sync_modules() -> None:
    _launchers.PACKAGE_ROOT = PACKAGE_ROOT
    _launchers.PROJECT_ROOT = PROJECT_ROOT
    _launchers.DEFAULT_SESSION_PATH = DEFAULT_SESSION_PATH
    _quickstart.DEFAULT_SESSION_PATH = DEFAULT_SESSION_PATH
    _schedule.PROJECT_ROOT = PROJECT_ROOT


def _running_from_source_checkout() -> bool:
    _sync_modules()
    return _launchers._running_from_source_checkout()


def _default_project_root() -> Path:
    _sync_modules()
    return _launchers._default_project_root()


def _python() -> str:
    return _launchers._python()


def _root_path(value: str | Path) -> Path:
    _sync_modules()
    return _launchers._root_path(value)


def _asset_path(value: str | Path) -> Path:
    _sync_modules()
    return _launchers._asset_path(value)


def _script(name: str) -> Path:
    _sync_modules()
    return _launchers._script(name)


def _local_path(*parts: str) -> Path:
    _sync_modules()
    return _launchers._local_path(*parts)


def _read_config() -> dict[str, Any]:
    _sync_modules()
    return _launchers._read_config()


def _configured_path(config: dict[str, Any], key: str, default: str) -> Path:
    _sync_modules()
    return _launchers._configured_path(config, key, default)


def _profile_path(value: str | None, config: dict[str, Any]) -> Path:
    _sync_modules()
    return _launchers._profile_path(value, config)


def _default_source_registry(config: dict[str, Any]) -> Path:
    _sync_modules()
    return _launchers._default_source_registry(config)


def _default_channel_list(config: dict[str, Any]) -> Path:
    _sync_modules()
    return _launchers._default_channel_list(config)


def _default_output_dir(config: dict[str, Any]) -> Path:
    _sync_modules()
    return _launchers._default_output_dir(config)


def _default_state_dir(config: dict[str, Any]) -> Path:
    _sync_modules()
    return _launchers._default_state_dir(config)


def _source_args(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    _sync_modules()
    return _launchers._source_args(args, config)


def _doctor_source_args(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    _sync_modules()
    return _launchers._doctor_source_args(args, config)


def _run(cmd: list[str | Path], *, cwd: Path | None = None) -> int:
    _sync_modules()
    return _launchers._run(cmd, cwd=cwd)


def _parse_node_version(raw: str) -> tuple[int, int, int] | None:
    return _launchers._parse_node_version(raw)


def _node_version_satisfies_dashboard_contract(version: tuple[int, int, int]) -> bool:
    return _launchers._node_version_satisfies_dashboard_contract(version)


def _dashboard_build_prerequisite_error() -> str:
    _sync_modules()
    return _launchers._dashboard_build_prerequisite_error()


def _quickstart_check(check_id: str, label: str, status: str, detail: str, command: str = "") -> dict[str, str]:
    return _quickstart._quickstart_check(check_id, label, status, detail, command)


def _jobs_sources_ready(registry_path: Path) -> bool:
    return _quickstart._jobs_sources_ready(registry_path)


def _telegram_credentials_ready(config_path: Path | None = None) -> bool:
    return _quickstart._telegram_credentials_ready(config_path)


def _telegram_session_ready(session_path: Path | None = None) -> bool:
    _sync_modules()
    return _quickstart._telegram_session_ready(session_path)


def _monitor_has_runs(db_path: Path) -> bool:
    return _quickstart._monitor_has_runs(db_path)


def quickstart_jobs_status() -> dict[str, Any]:
    _sync_modules()
    return _quickstart.quickstart_jobs_status()


def run_quickstart(args: argparse.Namespace) -> int:
    _sync_modules()
    return _quickstart.run_quickstart(args)


def _print_init_next_steps(starter: str = "default") -> None:
    return _setup._print_init_next_steps(starter)


def _write_default_config(
    path: Path,
    *,
    force: bool = False,
    profile: str = "market-news",
    channel_list: str = "channel_lists/example.txt",
) -> None:
    _sync_modules()
    return _setup._write_default_config(path, force=force, profile=profile, channel_list=channel_list)


def _write_default_profiles_config(path: Path, *, force: bool = False) -> None:
    return _setup._write_default_profiles_config(path, force=force)


def run_demo(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_demo(args)


def run_init(args: argparse.Namespace) -> int:
    _sync_modules()
    return _setup.run_init(args)


def run_login(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_login(args)


def run_doctor(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_doctor(args)


def run_daily(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_daily(args)


def run_sources(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_sources(args)


def run_monitor(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_monitor(args)


def run_dashboard(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_dashboard(args)


def run_feedback(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_feedback(args)


def _windows_preview_quote(value: str | Path) -> str:
    return _schedule._windows_preview_quote(value)


def _windows_task_quote(value: str | Path) -> str:
    return _schedule._windows_task_quote(value)


def _cron_prefix(interval_minutes: int) -> str:
    return _schedule._cron_prefix(interval_minutes)


def _schedule_platform(value: str | None) -> str:
    return _schedule._schedule_platform(value)


def _load_monitor_profile(profile_id: str) -> dict[str, Any]:
    _sync_modules()
    return _schedule._load_monitor_profile(profile_id)


def _schedule_interval_minutes(args: argparse.Namespace, profile: dict[str, Any]) -> int:
    return _schedule._schedule_interval_minutes(args, profile)


def run_schedule(args: argparse.Namespace) -> int:
    _sync_modules()
    return _schedule.run_schedule(args)


def run_delivery(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_delivery(args)


def run_bot(args: argparse.Namespace) -> int:
    _sync_modules()
    return _launchers.run_bot(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tgcs",
        description="Human-friendly T-Sense command facade.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Render the offline demo report.")
    demo.add_argument("--output", help="HTML output path. Defaults to output/demo-report.html.")
    demo.set_defaults(func=run_demo)

    init = subparsers.add_parser("init", help="Create .tgcs defaults and import the example sources.")
    init.add_argument("--starter", choices=tuple(INIT_STARTERS), default="default", help="Choose first-run defaults.")
    init.add_argument("--channel-list", help="Channel list to import into .tgcs/sources.json.")
    init.add_argument("--source-registry", help="Source registry path. Defaults to .tgcs/sources.json.")
    init.add_argument("--topic", action="append", default=[], help="Attach a topic tag to imported sources.")
    init.add_argument("--force", action="store_true", help="Overwrite local config and source registry.")
    init.set_defaults(func=run_init)

    quickstart = subparsers.add_parser("quickstart", help="Show the single next action for a starter workflow.")
    quickstart.add_argument("vertical", choices=("jobs",), help="Starter workflow to inspect.")
    quickstart.add_argument("--format", choices=("human", "json"), default="human")
    quickstart.set_defaults(func=run_quickstart)

    login = subparsers.add_parser("login", help="Complete Telegram login without scanning.")
    login.add_argument("--format", choices=("human", "json"), default="human")
    login.set_defaults(func=run_login)

    doctor = subparsers.add_parser("doctor", help="Run first-run checks with local defaults.")
    doctor.add_argument("--profile", help="Profile alias or path. Defaults to market-news.")
    doctor.add_argument("--source-registry", help="Source registry path.")
    doctor.add_argument("--channel-list", help="Channel list path used when no registry exists.")
    doctor.add_argument("--output-dir", help="Output directory. Defaults to output.")
    doctor.add_argument("--online-telegram", action="store_true")
    doctor.add_argument("--format", choices=("human", "json"), default="human")
    doctor.set_defaults(func=run_doctor)

    run = subparsers.add_parser("run", help="Scan sources and generate today's report.")
    run.add_argument("--profile", help="Profile alias or path. Defaults to market-news.")
    run.add_argument("--hours", type=int, default=24)
    run.add_argument("--source-registry", help="Source registry path.")
    run.add_argument("--channel-list", help="Channel list path used when no registry exists.")
    run.add_argument("--output-dir", help="Output directory. Defaults to output.")
    run.add_argument("--no-html", action="store_true", help="Skip HTML output.")
    run.add_argument("--no-state", action="store_true", help="Disable v0.4 local decision memory.")
    run.add_argument("--state-dir", help="State directory. Defaults to .tgcs/state.")
    run.add_argument("--state-read-only", action="store_true")
    run.add_argument("--feedback-jsonl", action="append", default=[])
    run.add_argument("--items-json")
    run.add_argument("--extractor", choices=("auto", "llm", "agent"))
    run.add_argument("--allow-incomplete", action="store_true")
    run.add_argument("--format", choices=("human", "json"), default="human")
    run.set_defaults(func=run_daily)

    sources = subparsers.add_parser("sources", help="Maintain the local source registry.")
    source_subparsers = sources.add_subparsers(dest="sources_command", required=True)
    source_import = source_subparsers.add_parser("import", help="Import a channel list.")
    source_import.add_argument("channel_list")
    source_import.add_argument("--source-registry")
    source_import.add_argument("--dry-run", action="store_true")
    source_import.add_argument("--topic", action="append", default=[], help="Attach a topic tag to imported sources.")
    source_import.add_argument("--format", choices=("human", "json"), default="human")
    source_import.set_defaults(func=run_sources)
    source_list = source_subparsers.add_parser("list", help="List sources.")
    source_list.add_argument("--source-registry")
    source_list.add_argument("--topic", action="append", default=[], help="Filter sources by topic tag.")
    source_list.add_argument("--format", choices=("human", "json"), default="human")
    source_list.set_defaults(func=run_sources)
    source_validate = source_subparsers.add_parser("validate", help="Validate sources.")
    source_validate.add_argument("--source-registry")
    source_validate.add_argument("--format", choices=("human", "json"), default="human")
    source_validate.set_defaults(func=run_sources)
    source_export = source_subparsers.add_parser("export", help="Export sources as a channel list.")
    source_export.add_argument("--output", required=True)
    source_export.add_argument("--source-registry")
    source_export.add_argument("--topic", action="append", default=[], help="Filter exported sources by topic tag.")
    source_export.add_argument("--format", choices=("human", "json"), default="human")
    source_export.set_defaults(func=run_sources)

    monitor = subparsers.add_parser("monitor", help="Run v0.5-alpha profile monitors.")
    monitor_subparsers = monitor.add_subparsers(dest="monitor_command", required=True)
    monitor_init = monitor_subparsers.add_parser("init-config", help="Write .tgcs/profiles.toml.")
    monitor_init.add_argument("--config")
    monitor_init.add_argument("--force", action="store_true")
    monitor_init.add_argument("--format", choices=("human", "json"), default="human")
    monitor_init.set_defaults(func=run_monitor)
    monitor_run = monitor_subparsers.add_parser("run", help="Run one configured profile monitor.")
    monitor_run.add_argument("--profile-id", default=DEFAULT_PROFILE)
    monitor_run.add_argument("--config")
    monitor_run.add_argument("--hours", type=int)
    monitor_run.add_argument("--scan-input")
    monitor_run.add_argument("--items-json")
    monitor_run.add_argument("--output-dir")
    monitor_run.add_argument("--db")
    monitor_run.add_argument("--delivery-mode", choices=("off", "dry-run", "live"), default="dry-run")
    monitor_run.add_argument("--format", choices=("human", "json"), default="human")
    monitor_run.set_defaults(func=run_monitor)

    dashboard = subparsers.add_parser("dashboard", help="Serve the local review dashboard.")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument(
        "--port",
        type=int,
        default=None,
        help="Strict port. Omit to reuse Signal Desk or auto-select 8765-8799.",
    )
    dashboard.add_argument("--db")
    dashboard.add_argument("--static-dir")
    dashboard.add_argument("--no-build", action="store_true", help="Do not auto-build dashboard/dist before serving.")
    dashboard.add_argument("--open", action="store_true", help="Open Signal Desk in the default browser after the server starts.")
    dashboard.set_defaults(func=run_dashboard)

    feedback = subparsers.add_parser("feedback", help="Export reusable feedback from the local dashboard.")
    feedback_subparsers = feedback.add_subparsers(dest="feedback_command", required=True)
    feedback_export = feedback_subparsers.add_parser("export", help="Export dashboard feedback as JSONL.")
    feedback_export.add_argument("--db")
    feedback_export.add_argument("--output")
    feedback_export.add_argument("--format", choices=("human", "json"), default="human")
    feedback_export.set_defaults(func=run_feedback)

    schedule = subparsers.add_parser("schedule", help="Print local scheduler commands without installing them.")
    schedule_subparsers = schedule.add_subparsers(dest="schedule_command", required=True)
    schedule_print = schedule_subparsers.add_parser("print", help="Print a local scheduler command without installing it.")
    schedule_print.add_argument("--platform", choices=("auto", "windows", "launchd", "systemd", "cron"), default="auto")
    schedule_print.add_argument("--profile-id", default=DEFAULT_PROFILE)
    schedule_print.add_argument("--interval-minutes", type=int)
    schedule_print.add_argument("--delivery-mode", choices=("off", "dry-run", "live"), default="dry-run")
    schedule_print.add_argument("--task-name")
    schedule_print.set_defaults(func=run_schedule)

    delivery_parser = subparsers.add_parser("delivery", help="Manage delivery adapters.")
    delivery_subparsers = delivery_parser.add_subparsers(dest="delivery_command", required=True)
    delivery_test = delivery_subparsers.add_parser("test", help="Test one delivery adapter.")
    delivery_test.add_argument("adapter", choices=("telegram-bot",))
    delivery_test.add_argument("--chat-id")
    delivery_test.add_argument("--delivery-mode", choices=("dry-run", "live"), default="dry-run")
    delivery_test.add_argument("--format", choices=("human", "json"), default="human")
    delivery_test.set_defaults(func=run_delivery)

    bot = subparsers.add_parser("bot", help="Run the local Telegram Bot gateway.")
    bot_subparsers = bot.add_subparsers(dest="bot_command", required=True)
    bot_run = bot_subparsers.add_parser("run", help="Poll Telegram Bot updates and run safe local actions.")
    bot_run.add_argument("--db")
    bot_run.add_argument("--state")
    bot_run.add_argument("--allow-chat-id", action="append", default=[])
    bot_run.add_argument("--poll-timeout", type=int, default=0)
    bot_run.add_argument("--install-menu", action="store_true", help="Install the bot command menu before polling; this is now the default.")
    bot_run.add_argument("--skip-menu", action="store_true", help="Skip command menu installation before polling.")
    bot_run.add_argument("--llm", action="store_true", help="Use AI routing and knowledge answers when an AI API key is configured; this is the default.")
    bot_run.add_argument("--no-llm", action="store_true", help="Keep free-form routing and knowledge answers local-only.")
    bot_run.set_defaults(func=run_bot)
    bot_menu = bot_subparsers.add_parser("install-menu", help="Install the Telegram Bot command menu.")
    bot_menu.set_defaults(func=run_bot)
    bot_install_autostart = bot_subparsers.add_parser("install-autostart", help="Start the local Bot Gateway automatically at login.")
    bot_install_autostart.set_defaults(func=run_bot)
    bot_remove_autostart = bot_subparsers.add_parser("remove-autostart", help="Remove the local Bot Gateway login task.")
    bot_remove_autostart.set_defaults(func=run_bot)
    bot_status = bot_subparsers.add_parser("status", help="Show local Bot Gateway and background status.")
    bot_status.set_defaults(func=run_bot)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
