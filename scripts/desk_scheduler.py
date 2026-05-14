"""Local automatic scan scheduler helpers for Signal Desk."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts import desk_bot_gateway_background
except ModuleNotFoundError:
    import desk_bot_gateway_background


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESK_BOT_GATEWAY_STATE_FILENAME = "bot-gateway-state.json"
DESK_BOT_GATEWAY_STALE_SECONDS = 120
DESK_BOT_SUPPORTED_COMMANDS = ["/status", "/latest", "/sources", "/profiles", "/scan"]
DESK_SCHEDULER_PROFILE_ID = "jobs-fast"
DESK_SCHEDULER_INTERVAL_MINUTES = 15
DESK_SCHEDULER_TASK_NAME = "TGCS jobs-fast dry-run"
DESK_SCHEDULER_LAUNCHD_LABEL = "com.sapientropic.tgcs.jobs-fast.dry-run"
DESK_SCHEDULER_SYSTEMD_NAME = "tgcs-jobs-fast-dry-run"
DESK_BOT_GATEWAY_TASK_NAME = "T-Sense Bot Gateway"
DESK_BOT_GATEWAY_LAUNCHD_LABEL = "com.sapientropic.tsense.bot-gateway"
DESK_BOT_GATEWAY_SYSTEMD_NAME = "tsense-bot-gateway"
DESK_BOT_GATEWAY_POLL_TIMEOUT_SECONDS = 8
DESK_ACTION_BY_ID: dict[str, dict[str, Any]] = {}


class DashboardDeskActionError(Exception):
    """Raised when a Signal Desk action request is not on the local allowlist."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _desk_safe_result_text(*parts: object) -> str:
    text = "\n".join(str(part or "") for part in parts).strip()
    return text.splitlines()[0][:500] if text else ""


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _enabled_telegram_bot_target_count(conn) -> int:
    return 0


def desk_notification_token_status() -> dict:
    return {"configured": False}


def run_scheduler_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    # Local scheduler commands should return quickly for query/create/delete.
    # Keep this bounded so a permission prompt or daemon hang cannot freeze
    # Signal Desk. Callers must pass fixed argv lists, never browser input.
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


_run_scheduler_command = run_scheduler_command


def load_bot_gateway_state() -> dict[str, object]:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.load_bot_gateway_state()


def desk_bot_gateway_status(conn, *, now: datetime | None = None) -> dict:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.desk_bot_gateway_status(conn, now=now)


def _sync_bot_gateway_context() -> None:
    # Bot Gateway background helpers share the scheduler backend but have a
    # separate product contract: local-first bot status, token-gated autostart,
    # and fixed launcher argv. Keep this sync layer so dashboard_server remains
    # the monkeypatch surface for tests and local callers after the split.
    desk_bot_gateway_background.PROJECT_ROOT = PROJECT_ROOT
    desk_bot_gateway_background.DESK_BOT_GATEWAY_STATE_FILENAME = DESK_BOT_GATEWAY_STATE_FILENAME
    desk_bot_gateway_background.DESK_BOT_GATEWAY_STALE_SECONDS = DESK_BOT_GATEWAY_STALE_SECONDS
    desk_bot_gateway_background.DESK_BOT_SUPPORTED_COMMANDS = DESK_BOT_SUPPORTED_COMMANDS
    desk_bot_gateway_background.DESK_BOT_GATEWAY_TASK_NAME = DESK_BOT_GATEWAY_TASK_NAME
    desk_bot_gateway_background.DESK_BOT_GATEWAY_LAUNCHD_LABEL = DESK_BOT_GATEWAY_LAUNCHD_LABEL
    desk_bot_gateway_background.DESK_BOT_GATEWAY_SYSTEMD_NAME = DESK_BOT_GATEWAY_SYSTEMD_NAME
    desk_bot_gateway_background.DESK_BOT_GATEWAY_POLL_TIMEOUT_SECONDS = DESK_BOT_GATEWAY_POLL_TIMEOUT_SECONDS
    desk_bot_gateway_background.DESK_ACTION_BY_ID = DESK_ACTION_BY_ID
    desk_bot_gateway_background.DashboardDeskActionError = DashboardDeskActionError
    desk_bot_gateway_background.shutil = shutil
    desk_bot_gateway_background._utc_now = _utc_now
    desk_bot_gateway_background._desk_safe_result_text = _desk_safe_result_text
    desk_bot_gateway_background._parse_utc_timestamp = _parse_utc_timestamp
    desk_bot_gateway_background._enabled_telegram_bot_target_count = _enabled_telegram_bot_target_count
    desk_bot_gateway_background.desk_notification_token_status = desk_notification_token_status
    desk_bot_gateway_background.run_scheduler_command = run_scheduler_command
    desk_bot_gateway_background._run_scheduler_command = _run_scheduler_command
    desk_bot_gateway_background.scheduler_backend = scheduler_backend
    desk_bot_gateway_background.systemd_user_dir = systemd_user_dir
    desk_bot_gateway_background.systemd_exec_path = systemd_exec_path
    desk_bot_gateway_background.pythonw_entry = pythonw_entry


def scheduler_result(
    action_id: str,
    *,
    status: str,
    title: str,
    detail: str,
    next_action: str,
    exit_code: int | None = None,
) -> dict:
    action = DESK_ACTION_BY_ID[action_id]
    return {
        "schema_version": "desk_action_result_v1",
        "action_id": action_id,
        "status": status,
        "title": title,
        "detail": detail,
        "display_command": action["display_command"],
        "exit_code": exit_code,
        "artifact_path": "",
        "next_action": next_action,
        "finished_at": _utc_now(),
    }


def scheduler_backend() -> str:
    if sys.platform.startswith("win"):
        return "windows_schtasks"
    if sys.platform == "darwin":
        return "macos_launchd"
    if sys.platform.startswith("linux") and shutil.which("systemctl") and os.environ.get("XDG_RUNTIME_DIR"):
        return "linux_systemd_user"
    return "manual_cron_preview"


def scheduler_base(backend: str) -> dict:
    can_install = backend in {"windows_schtasks", "macos_launchd", "linux_systemd_user"}
    return {
        "schema_version": "desk_scheduler_status_v1",
        "task_label": "jobs-fast dry-run",
        "interval_minutes": DESK_SCHEDULER_INTERVAL_MINUTES,
        "platform": sys.platform,
        "backend": backend,
        "can_install": can_install,
        "can_remove": can_install,
        "checked_at": _utc_now(),
    }


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{DESK_SCHEDULER_LAUNCHD_LABEL}.plist"


def systemd_user_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def systemd_service_path() -> Path:
    return systemd_user_dir() / f"{DESK_SCHEDULER_SYSTEMD_NAME}.service"


def systemd_timer_path() -> Path:
    return systemd_user_dir() / f"{DESK_SCHEDULER_SYSTEMD_NAME}.timer"


def posix_tgcs_entry() -> Path:
    return PROJECT_ROOT / "tgcs"


def bot_gateway_script_path() -> Path:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.bot_gateway_script_path()


def pythonw_entry() -> Path:
    executable = Path(sys.executable)
    if sys.platform.startswith("win") and executable.name.lower() == "python.exe":
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            return candidate
    return executable


_DEFAULT_PYTHONW_ENTRY = pythonw_entry


def fixed_monitor_argv(entry: Path) -> list[str]:
    return [
        str(entry),
        "monitor",
        "run",
        "--profile-id",
        DESK_SCHEDULER_PROFILE_ID,
        "--delivery-mode",
        "dry-run",
    ]


def systemd_exec_path(path: Path) -> str:
    text = str(path)
    if any(char.isspace() for char in text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def fixed_bot_gateway_argv(python_entry: Path | None = None) -> list[str]:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.fixed_bot_gateway_argv(python_entry)


def bot_gateway_launchd_plist_path() -> Path:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.bot_gateway_launchd_plist_path()


def bot_gateway_systemd_service_path() -> Path:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.bot_gateway_systemd_service_path()


def bot_gateway_background_base(backend: str) -> dict:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.bot_gateway_background_base(backend)


def desk_bot_gateway_background_status(*, token_configured: bool | None = None) -> dict:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.desk_bot_gateway_background_status(token_configured=token_configured)


def desk_scheduler_status() -> dict:
    backend = scheduler_backend()
    base = scheduler_base(backend)
    if backend == "manual_cron_preview":
        return {
            **base,
            "available": False,
            "installed": False,
            "status": "manual" if sys.platform.startswith("linux") else "unavailable",
            "detail": "Automatic scan install is not available on this machine; use the schedule preview or manual scans.",
            "next_action": "Run tgcs schedule print --platform cron for a no-side-effect crontab preview.",
        }

    if backend == "macos_launchd":
        installed = launchd_plist_path().exists()
        return {
            **base,
            "available": True,
            "installed": installed,
            "status": "installed" if installed else "not_installed",
            "detail": "Automatic practice scans are on every 15 minutes." if installed else "Automatic practice scans are off.",
            "next_action": (
                "You can turn them off from Signal Desk when you no longer need background checks."
                if installed
                else "Turn on auto scan from Signal Desk when you want background checks."
            ),
        }

    if backend == "linux_systemd_user":
        installed = systemd_timer_path().exists()
        return {
            **base,
            "available": True,
            "installed": installed,
            "status": "installed" if installed else "not_installed",
            "detail": "Automatic practice scans are on every 15 minutes." if installed else "Automatic practice scans are off.",
            "next_action": (
                "You can turn them off from Signal Desk when you no longer need background checks."
                if installed
                else "Turn on auto scan from Signal Desk when you want background checks."
            ),
        }

    try:
        completed = _run_scheduler_command(["schtasks.exe", "/Query", "/TN", DESK_SCHEDULER_TASK_NAME])
    except subprocess.TimeoutExpired:
        return {
            **base,
            "available": True,
            "installed": False,
            "status": "unknown",
            "detail": "Signal Desk could not confirm the automatic scan status before the check timed out.",
            "next_action": "Retry refresh, or open Windows Task Scheduler if the status stays unknown.",
        }
    except OSError:
        return {
            **base,
            "available": False,
            "installed": False,
            "status": "unavailable",
            "detail": "Signal Desk could not query the local scheduler on this machine.",
            "next_action": "Use manual scans from Signal Desk.",
        }

    if completed.returncode == 0:
        return {
            **base,
            "available": True,
            "installed": True,
            "status": "installed",
            "detail": "Automatic practice scans are on every 15 minutes.",
            "next_action": "You can turn them off from Signal Desk when you no longer need background checks.",
        }
    return {
        **base,
        "available": True,
        "installed": False,
        "status": "not_installed",
        "detail": "Automatic practice scans are off.",
        "next_action": "Turn on auto scan from Signal Desk when you want background checks.",
    }


def write_launchd_plist(path: Path, entry: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": DESK_SCHEDULER_LAUNCHD_LABEL,
        "ProgramArguments": fixed_monitor_argv(entry),
        "RunAtLoad": True,
        "StartInterval": DESK_SCHEDULER_INTERVAL_MINUTES * 60,
        "WorkingDirectory": str(PROJECT_ROOT),
        "StandardOutPath": str(PROJECT_ROOT / "output" / f"tgcs-{DESK_SCHEDULER_PROFILE_ID}.log"),
        "StandardErrorPath": str(PROJECT_ROOT / "output" / f"tgcs-{DESK_SCHEDULER_PROFILE_ID}.err.log"),
    }
    PROJECT_ROOT.joinpath("output").mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(payload, handle)


def write_systemd_units(service_path: Path, timer_path: Path, entry: Path) -> None:
    service_path.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_ROOT.joinpath("output").mkdir(parents=True, exist_ok=True)
    exec_start = " ".join(
        [
            systemd_exec_path(entry),
            "monitor",
            "run",
            "--profile-id",
            DESK_SCHEDULER_PROFILE_ID,
            "--delivery-mode",
            "dry-run",
        ]
    )
    service_path.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=T-Sense jobs-fast dry-run scan",
                "",
                "[Service]",
                "Type=oneshot",
                f"WorkingDirectory={PROJECT_ROOT}",
                f"ExecStart={exec_start}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    timer_path.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Run T-Sense jobs-fast dry-run scan every 15 minutes",
                "",
                "[Timer]",
                "OnBootSec=1min",
                f"OnUnitActiveSec={DESK_SCHEDULER_INTERVAL_MINUTES}min",
                f"Unit={DESK_SCHEDULER_SYSTEMD_NAME}.service",
                "",
                "[Install]",
                "WantedBy=timers.target",
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_desk_scheduler_action(action_id: str, *, body: dict | None = None) -> dict:
    if body is None:
        body = {}
    unexpected_keys = set(body) - {"confirm"}
    if unexpected_keys:
        raise DashboardDeskActionError("Scheduler actions only accept an explicit confirmation flag.")
    if body.get("confirm") is not True:
        raise DashboardDeskActionError("Automation changes require explicit confirmation.")
    backend = scheduler_backend()
    if backend == "manual_cron_preview":
        return scheduler_result(
            action_id,
            status="blocked",
            title="Auto scan needs a supported scheduler",
            detail="Signal Desk will not edit crontab directly. This machine can use the schedule preview or manual scans.",
            next_action="Run tgcs schedule print --platform cron for a no-side-effect crontab preview.",
        )

    tgcs_entry = PROJECT_ROOT / "tgcs.bat" if backend == "windows_schtasks" else posix_tgcs_entry()
    if not tgcs_entry.exists():
        return scheduler_result(
            action_id,
            status="blocked",
            title="Launcher file is missing",
            detail="Signal Desk could not find the local T-Sense launcher needed by the scheduler.",
            next_action="Repair the repo-local install, then turn on auto scan again.",
        )

    if action_id not in {"schedule_install_dry_run", "schedule_remove_dry_run"}:
        raise DashboardDeskActionError(f"Unknown scheduler action: {action_id}")

    if backend == "windows_schtasks":
        # Keep this as a single fixed /TR argument in a list argv call. Do not
        # refactor this path through shell=True: the browser must never be able
        # to turn scheduler setup into a local shell proxy.
        task_action = f'"{tgcs_entry}" monitor run --profile-id {DESK_SCHEDULER_PROFILE_ID} --delivery-mode dry-run'
        if action_id == "schedule_install_dry_run":
            args = [
                "schtasks.exe",
                "/Create",
                "/TN",
                DESK_SCHEDULER_TASK_NAME,
                "/SC",
                "MINUTE",
                "/MO",
                str(DESK_SCHEDULER_INTERVAL_MINUTES),
                "/TR",
                task_action,
                "/F",
            ]
            success_title = "Auto scan is on"
            success_detail = "Windows Task Scheduler will run local practice scans every 15 minutes. Live Telegram delivery is still off."
            success_next = "You can leave Signal Desk and return later to review new Inbox cards."
        else:
            args = ["schtasks.exe", "/Delete", "/TN", DESK_SCHEDULER_TASK_NAME, "/F"]
            success_title = "Auto scan is off"
            success_detail = "Signal Desk removed the Windows Task Scheduler task for automatic practice scans."
            success_next = "Manual scans still work from Signal Desk."

        try:
            completed = _run_scheduler_command(args)
        except subprocess.TimeoutExpired:
            return scheduler_result(
                action_id,
                status="failed",
                title="Scheduler change timed out",
                detail="The local scheduler did not finish the requested change in time.",
                next_action="Check the local scheduler, then retry from Signal Desk.",
            )
        except OSError:
            return scheduler_result(
                action_id,
                status="blocked",
                title="Scheduler is unavailable",
                detail="Signal Desk could not start the local scheduler command on this machine.",
                next_action="Use manual scans in Signal Desk, or install the task from the local scheduler.",
            )

        if completed.returncode == 0:
            return scheduler_result(
                action_id,
                status="success",
                title=success_title,
                detail=success_detail,
                next_action=success_next,
                exit_code=completed.returncode,
            )

        failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
        return scheduler_result(
            action_id,
            status="failed",
            title="Scheduler change failed",
            detail=failure,
            next_action="Check scheduler permissions, then retry from Signal Desk.",
            exit_code=completed.returncode,
        )

    if backend == "macos_launchd":
        plist_path = launchd_plist_path()
        if action_id == "schedule_install_dry_run":
            write_launchd_plist(plist_path, tgcs_entry)
            args = ["launchctl", "load", "-w", str(plist_path)]
            success_title = "Auto scan is on"
            success_detail = "launchd will run local practice scans every 15 minutes. Live Telegram delivery is still off."
            success_next = "You can leave Signal Desk and return later to review new Inbox cards."
        else:
            args = ["launchctl", "unload", "-w", str(plist_path)]
            success_title = "Auto scan is off"
            success_detail = "Signal Desk removed the launchd LaunchAgent for automatic practice scans."
            success_next = "Manual scans still work from Signal Desk."

    elif backend == "linux_systemd_user":
        service_path = systemd_service_path()
        timer_path = systemd_timer_path()
        if action_id == "schedule_install_dry_run":
            write_systemd_units(service_path, timer_path, tgcs_entry)
            try:
                reload_result = _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
            except (OSError, subprocess.TimeoutExpired):
                reload_result = subprocess.CompletedProcess(["systemctl"], 1, stdout="", stderr="systemctl --user daemon-reload failed")
            if reload_result.returncode != 0:
                failure = _desk_safe_result_text(reload_result.stderr, reload_result.stdout) or "systemd user daemon reload failed."
                return scheduler_result(
                    action_id,
                    status="failed",
                    title="Scheduler change failed",
                    detail=failure,
                    next_action="Check systemd --user availability, then retry from Signal Desk.",
                    exit_code=reload_result.returncode,
                )
            args = ["systemctl", "--user", "enable", "--now", f"{DESK_SCHEDULER_SYSTEMD_NAME}.timer"]
            success_title = "Auto scan is on"
            success_detail = "systemd --user will run local practice scans every 15 minutes. Live Telegram delivery is still off."
            success_next = "You can leave Signal Desk and return later to review new Inbox cards."
        else:
            args = ["systemctl", "--user", "disable", "--now", f"{DESK_SCHEDULER_SYSTEMD_NAME}.timer"]
            success_title = "Auto scan is off"
            success_detail = "Signal Desk removed the systemd user timer for automatic practice scans."
            success_next = "Manual scans still work from Signal Desk."
    else:
        raise DashboardDeskActionError(f"Unknown scheduler backend: {backend}")

    try:
        completed = _run_scheduler_command(args)
    except subprocess.TimeoutExpired:
        return scheduler_result(
            action_id,
            status="failed",
            title="Scheduler change timed out",
            detail="The local scheduler did not finish the requested change in time.",
            next_action="Check the local scheduler, then retry from Signal Desk.",
        )
    except OSError:
        return scheduler_result(
            action_id,
            status="blocked",
            title="Scheduler is unavailable",
            detail="Signal Desk could not start the local scheduler command on this machine.",
            next_action="Use manual scans in Signal Desk, or install the task from the local scheduler.",
        )

    if backend == "macos_launchd" and action_id == "schedule_remove_dry_run":
        launchd_plist_path().unlink(missing_ok=True)
    if backend == "linux_systemd_user" and action_id == "schedule_remove_dry_run":
        systemd_service_path().unlink(missing_ok=True)
        systemd_timer_path().unlink(missing_ok=True)
        try:
            _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
        except (OSError, subprocess.TimeoutExpired):
            pass

    if completed.returncode == 0:
        return scheduler_result(
            action_id,
            status="success",
            title=success_title,
            detail=success_detail,
            next_action=success_next,
            exit_code=completed.returncode,
        )

    failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
    return scheduler_result(
        action_id,
        status="failed",
        title="Scheduler change failed",
        detail=failure,
        next_action="Check scheduler permissions, then retry from Signal Desk.",
        exit_code=completed.returncode,
    )


def bot_gateway_action_result(
    action_id: str,
    *,
    status: str,
    title: str,
    detail: str,
    next_action: str,
    exit_code: int | None = None,
) -> dict:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.bot_gateway_action_result(
        action_id,
        status=status,
        title=title,
        detail=detail,
        next_action=next_action,
        exit_code=exit_code,
    )


def write_bot_gateway_launchd_plist(path: Path, python_entry: Path) -> None:
    _sync_bot_gateway_context()
    desk_bot_gateway_background.write_bot_gateway_launchd_plist(path, python_entry)


def write_bot_gateway_systemd_service(path: Path, python_entry: Path) -> None:
    _sync_bot_gateway_context()
    desk_bot_gateway_background.write_bot_gateway_systemd_service(path, python_entry)


def run_bot_gateway_autostart_action(action_id: str, *, body: dict | None = None) -> dict:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.run_bot_gateway_autostart_action(action_id, body=body)
