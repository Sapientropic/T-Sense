"""Local scheduler command preview helpers."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from scripts.tgcs_launchers import PROJECT_ROOT, _local_path

SCHEDULER_LAUNCHD_LABEL = "com.sapientropic.tgcs.jobs-fast.dry-run"
SCHEDULER_SYSTEMD_NAME = "tgcs-jobs-fast-dry-run"
PROFILES_CONFIG_NAME = "profiles.toml"
DEFAULT_PROFILE = "market-news"



def _windows_preview_quote(value: str | Path) -> str:
    text = str(value)
    return f'"{text}"'



def _windows_task_quote(value: str | Path) -> str:
    return f'\\"{value}\\"'



def _cron_prefix(interval_minutes: int) -> str:
    if interval_minutes < 60:
        return f"*/{interval_minutes} * * * *"
    if interval_minutes % 60 == 0:
        return f"0 */{interval_minutes // 60} * * *"
    raise SystemExit("cron intervals above 59 minutes must be whole hours")



def _schedule_platform(value: str | None) -> str:
    if value and value != "auto":
        return value
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "launchd"
    # Keep auto aligned with the dashboard installer: systemd is only the
    # default when a per-user runtime exists. Headless Linux or CI boxes often
    # have systemctl on PATH but no user manager, so auto must stay preview-only
    # via cron instead of implying install support that will fail at runtime.
    if sys.platform.startswith("linux") and shutil.which("systemctl") and os.environ.get("XDG_RUNTIME_DIR"):
        return "systemd"
    return "cron"



def _load_monitor_profile(profile_id: str) -> dict[str, Any]:
    try:
        from scripts import monitor
    except ModuleNotFoundError:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from scripts import monitor

    config_path = _local_path(PROFILES_CONFIG_NAME)
    try:
        config = monitor.load_config(config_path, root=PROJECT_ROOT)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    profile = config.profiles.get(profile_id)
    if not profile:
        raise SystemExit(f"Profile id not found: {profile_id}")
    return profile



def _schedule_interval_minutes(args: argparse.Namespace, profile: dict[str, Any]) -> int:
    if args.interval_minutes is not None:
        return args.interval_minutes
    raw = profile.get("work_interval_minutes")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 15



def run_schedule(args: argparse.Namespace) -> int:
    if args.schedule_command != "print":
        raise AssertionError(f"Unsupported schedule command: {args.schedule_command}")
    profile_id = args.profile_id
    profile = _load_monitor_profile(profile_id)
    interval_minutes = _schedule_interval_minutes(args, profile)
    if interval_minutes < 1:
        raise SystemExit("--interval-minutes must be at least 1")

    delivery_mode = args.delivery_mode
    platform = _schedule_platform(args.platform)

    if platform == "windows":
        task_name = args.task_name or f"TGCS {profile_id}"
        tgcs_path = PROJECT_ROOT / "tgcs.bat"
        task_command = (
            f"{_windows_task_quote(tgcs_path)} monitor run --profile-id {profile_id} "
            f"--delivery-mode {delivery_mode}"
        )
        preview_command = (
            f"{_windows_preview_quote(tgcs_path)} monitor run --profile-id {profile_id} "
            f"--delivery-mode {delivery_mode}"
        )
        print("Task Scheduler command:")
        print(
            f'schtasks /Create /TN "{task_name}" /SC MINUTE /MO {interval_minutes} '
            f'/TR "{task_command}" /F'
        )
        print("Preview command:")
        print(preview_command)
        return 0

    if platform == "launchd":
        tgcs_path = PROJECT_ROOT / "tgcs"
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{SCHEDULER_LAUNCHD_LABEL}.plist"
        preview_command = f'"{tgcs_path}" monitor run --profile-id {profile_id} --delivery-mode {delivery_mode}'
        print("LaunchAgent plist path:")
        print(plist_path)
        print("ProgramArguments:")
        print(f"{tgcs_path} monitor run --profile-id {profile_id} --delivery-mode {delivery_mode}")
        print("StartInterval seconds:")
        print(interval_minutes * 60)
        print("Install command:")
        print(f"launchctl load -w {plist_path}")
        print("Preview command:")
        print(preview_command)
        return 0

    if platform == "systemd":
        tgcs_path = PROJECT_ROOT / "tgcs"
        user_dir = Path.home() / ".config" / "systemd" / "user"
        service_path = user_dir / f"{SCHEDULER_SYSTEMD_NAME}.service"
        timer_path = user_dir / f"{SCHEDULER_SYSTEMD_NAME}.timer"
        preview_command = f'"{tgcs_path}" monitor run --profile-id {profile_id} --delivery-mode {delivery_mode}'
        print("systemd user service:")
        print(service_path)
        print("systemd user timer:")
        print(timer_path)
        print("ExecStart:")
        print(f"{tgcs_path} monitor run --profile-id {profile_id} --delivery-mode {delivery_mode}")
        print("Timer interval:")
        print(f"OnUnitActiveSec={interval_minutes}min")
        print("Install commands:")
        print("systemctl --user daemon-reload")
        print(f"systemctl --user enable --now {SCHEDULER_SYSTEMD_NAME}.timer")
        print("Preview command:")
        print(preview_command)
        return 0

    cron_prefix = _cron_prefix(interval_minutes)
    log_path = f"output/tgcs-{profile_id}.log"
    print("Crontab line:")
    print(
        f'{cron_prefix} cd "{PROJECT_ROOT}" && ./tgcs monitor run --profile-id {profile_id} '
        f"--delivery-mode {delivery_mode} >> {log_path} 2>&1"
    )
    return 0
