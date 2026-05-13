"""Scheduler and Bot Gateway background helpers for Signal Desk."""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


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
    path = PROJECT_ROOT / ".tgcs" / DESK_BOT_GATEWAY_STATE_FILENAME
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def desk_bot_gateway_status(conn, *, now: datetime | None = None) -> dict:
    token_status = desk_notification_token_status()
    background = desk_bot_gateway_background_status(token_configured=bool(token_status.get("configured")))
    state = load_bot_gateway_state()
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    last_poll_at = _parse_utc_timestamp(state.get("last_poll_at")) if state else None
    if not state or state.get("schema_version") != "bot_gateway_state_v1":
        gateway_status = "not_detected"
    elif last_poll_at is None:
        gateway_status = "stale"
    elif current_time - last_poll_at > timedelta(seconds=DESK_BOT_GATEWAY_STALE_SECONDS):
        gateway_status = "stale"
    else:
        gateway_status = "running"

    raw_count = state.get("authorized_chat_count") if state else None
    try:
        authorized_chat_count = max(0, int(raw_count))
    except (TypeError, ValueError):
        authorized_chat_count = _enabled_telegram_bot_target_count(conn)
    last_error = _desk_safe_result_text(state.get("last_error")) if state else ""
    started_at = str(state.get("started_at") or "") if state else ""
    last_poll_text = str(state.get("last_poll_at") or "") if state else ""
    if not bool(token_status.get("configured")):
        safe_next_action = "Save bot credentials in Settings."
    elif gateway_status == "running":
        safe_next_action = "Bot Gateway is running."
    elif bool(background.get("installed")):
        safe_next_action = "Refresh after login, or restart background mode from Settings."
    else:
        safe_next_action = "Run tgcs bot run locally, or turn on background mode from Settings."

    return {
        "schema_version": "desk_bot_gateway_status_v1",
        "token_configured": bool(token_status.get("configured")),
        "authorized_chat_count": authorized_chat_count,
        "gateway_status": gateway_status,
        "commands_installed": bool(state.get("commands_installed")) if state else False,
        "supported_commands": list(DESK_BOT_SUPPORTED_COMMANDS),
        "local_first_note": (
            "Bot replies while the local gateway is running. Background mode starts it again at login."
            if bool(background.get("installed"))
            else "Bot replies only while tgcs bot run is running locally."
        ),
        "start_command": "./tgcs bot run",
        "last_update_at": last_poll_text or started_at,
        "last_error": last_error,
        "safe_next_action": safe_next_action,
        "background": background,
        "started_at": started_at,
        "last_poll_at": last_poll_text,
    }


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
    return PROJECT_ROOT / "scripts" / "bot_gateway.py"


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
    return [
        str(python_entry or pythonw_entry()),
        str(bot_gateway_script_path()),
        "run",
        "--poll-timeout",
        str(DESK_BOT_GATEWAY_POLL_TIMEOUT_SECONDS),
    ]


def bot_gateway_launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{DESK_BOT_GATEWAY_LAUNCHD_LABEL}.plist"


def bot_gateway_systemd_service_path() -> Path:
    return systemd_user_dir() / f"{DESK_BOT_GATEWAY_SYSTEMD_NAME}.service"


def bot_gateway_background_base(backend: str) -> dict:
    can_schedule = backend in {"windows_schtasks", "macos_launchd", "linux_systemd_user"}
    return {
        "schema_version": "desk_bot_gateway_background_status_v1",
        "backend": backend,
        "available": can_schedule,
        "installed": False,
        "status": "not_installed" if can_schedule else ("manual" if sys.platform.startswith("linux") else "unavailable"),
        "can_install": can_schedule,
        "can_remove": False,
        "detail": "Bot background mode is off." if can_schedule else "Bot background mode is not available on this machine.",
        "next_action": "Turn on bot background mode after setup is ready.",
        "checked_at": _utc_now(),
    }


def desk_bot_gateway_background_status(*, token_configured: bool | None = None) -> dict:
    token_ready = bool(desk_notification_token_status().get("configured")) if token_configured is None else bool(token_configured)
    backend = scheduler_backend()
    base = bot_gateway_background_base(backend)
    base["can_install"] = bool(base["available"] and token_ready)
    if not token_ready:
        base["detail"] = "Save Telegram bot credentials before turning on background mode."
        base["next_action"] = "Save bot credentials in Settings, then turn on bot background mode."

    if backend == "manual_cron_preview":
        return {
            **base,
            "detail": "Bot background mode needs Windows Task Scheduler, launchd, or systemd --user.",
            "next_action": "Keep Signal Desk open for now, or run tgcs bot run manually.",
        }
    if backend == "macos_launchd":
        installed = bot_gateway_launchd_plist_path().exists()
        return {
            **base,
            "installed": installed,
            "status": "installed" if installed else "not_installed",
            "can_remove": installed,
            "detail": "Bot Gateway starts at login." if installed else base["detail"],
            "next_action": "You can turn it off from Settings." if installed else base["next_action"],
        }
    if backend == "linux_systemd_user":
        installed = bot_gateway_systemd_service_path().exists()
        return {
            **base,
            "installed": installed,
            "status": "installed" if installed else "not_installed",
            "can_remove": installed,
            "detail": "Bot Gateway starts with your user session." if installed else base["detail"],
            "next_action": "You can turn it off from Settings." if installed else base["next_action"],
        }

    try:
        completed = _run_scheduler_command(["schtasks.exe", "/Query", "/TN", DESK_BOT_GATEWAY_TASK_NAME])
    except subprocess.TimeoutExpired:
        return {
            **base,
            "status": "unknown",
            "detail": "Signal Desk could not confirm bot background mode before the check timed out.",
            "next_action": "Retry refresh, or open Windows Task Scheduler if the status stays unknown.",
        }
    except OSError:
        return {
            **base,
            "available": False,
            "status": "unavailable",
            "can_install": False,
            "detail": "Signal Desk could not query Windows Task Scheduler on this machine.",
            "next_action": "Use manual bot runs until the local scheduler is available.",
        }
    installed = completed.returncode == 0
    return {
        **base,
        "installed": installed,
        "status": "installed" if installed else "not_installed",
        "can_remove": installed,
        "detail": "Bot Gateway starts at Windows login." if installed else base["detail"],
        "next_action": "You can turn it off from Settings." if installed else base["next_action"],
    }


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


def write_bot_gateway_launchd_plist(path: Path, python_entry: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": DESK_BOT_GATEWAY_LAUNCHD_LABEL,
        "ProgramArguments": fixed_bot_gateway_argv(python_entry),
        "RunAtLoad": True,
        "KeepAlive": {"Crashed": True},
        "WorkingDirectory": str(PROJECT_ROOT),
        "StandardOutPath": str(output_dir / "tsense-bot-gateway.log"),
        "StandardErrorPath": str(output_dir / "tsense-bot-gateway.err.log"),
    }
    with path.open("wb") as handle:
        plistlib.dump(payload, handle)


def write_bot_gateway_systemd_service(path: Path, python_entry: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    argv = fixed_bot_gateway_argv(python_entry)
    exec_start = " ".join(systemd_exec_path(Path(part)) if index < 2 else part for index, part in enumerate(argv))
    path.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=T-Sense Bot Gateway",
                "After=network-online.target",
                "",
                "[Service]",
                "Type=simple",
                f"WorkingDirectory={PROJECT_ROOT}",
                f"ExecStart={exec_start}",
                "Restart=on-failure",
                "RestartSec=30",
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_bot_gateway_autostart_action(action_id: str, *, body: dict | None = None) -> dict:
    if body is None:
        body = {}
    unexpected_keys = set(body) - {"confirm"}
    if unexpected_keys:
        raise DashboardDeskActionError("Bot Gateway background actions only accept an explicit confirmation flag.")
    if body.get("confirm") is not True:
        raise DashboardDeskActionError("Bot Gateway background changes require explicit confirmation.")
    if action_id not in {"bot_gateway_install_autostart", "bot_gateway_remove_autostart"}:
        raise DashboardDeskActionError(f"Unknown Bot Gateway background action: {action_id}")

    token_status = desk_notification_token_status()
    if action_id == "bot_gateway_install_autostart" and not bool(token_status.get("configured")):
        return bot_gateway_action_result(
            action_id,
            status="blocked",
            title="Bot token is missing",
            detail="Save a Telegram bot token before turning on background mode.",
            next_action="Save the bot token in Settings, then turn on bot background mode.",
        )

    backend = scheduler_backend()
    if backend == "manual_cron_preview":
        return bot_gateway_action_result(
            action_id,
            status="blocked",
            title="Bot background mode needs a local scheduler",
            detail="Signal Desk cannot install a Bot Gateway login task on this platform.",
            next_action="Keep Signal Desk open for now, or run tgcs bot run manually.",
        )

    bot_script = bot_gateway_script_path()
    python_entry = pythonw_entry()
    if not bot_script.exists() or not python_entry.exists():
        return bot_gateway_action_result(
            action_id,
            status="blocked",
            title="Bot Gateway launcher is missing",
            detail="Signal Desk could not find the local Bot Gateway runtime needed for background mode.",
            next_action="Repair the local install, then turn on bot background mode again.",
        )

    if backend == "windows_schtasks":
        if action_id == "bot_gateway_install_autostart":
            task_action = " ".join(f'"{part}"' if " " in part or "\\" in part else part for part in fixed_bot_gateway_argv(python_entry))
            args = [
                "schtasks.exe",
                "/Create",
                "/TN",
                DESK_BOT_GATEWAY_TASK_NAME,
                "/SC",
                "ONLOGON",
                "/TR",
                task_action,
                "/F",
            ]
            success_title = "Bot background mode is on"
            success_detail = "Windows Task Scheduler will start the local Bot Gateway at login."
            success_next = "You can close Signal Desk; Telegram bot actions will work after this user logs in."
        else:
            args = ["schtasks.exe", "/Delete", "/TN", DESK_BOT_GATEWAY_TASK_NAME, "/F"]
            success_title = "Bot background mode is off"
            success_detail = "Signal Desk removed the Bot Gateway login task."
            success_next = "Manual bot runs still work from Settings or the local CLI."
        try:
            completed = _run_scheduler_command(args)
        except subprocess.TimeoutExpired:
            return bot_gateway_action_result(
                action_id,
                status="failed",
                title="Bot background change timed out",
                detail="The local scheduler did not finish the requested change in time.",
                next_action="Check Windows Task Scheduler, then retry from Settings.",
            )
        except OSError:
            return bot_gateway_action_result(
                action_id,
                status="blocked",
                title="Local scheduler is unavailable",
                detail="Signal Desk could not start the local scheduler command on this machine.",
                next_action="Use manual bot runs until the scheduler is available.",
            )
        if completed.returncode == 0:
            if action_id == "bot_gateway_install_autostart":
                try:
                    start_result = _run_scheduler_command(["schtasks.exe", "/Run", "/TN", DESK_BOT_GATEWAY_TASK_NAME])
                except (OSError, subprocess.TimeoutExpired):
                    start_result = subprocess.CompletedProcess(["schtasks.exe"], 1, stdout="", stderr="could not start task")
                if start_result.returncode != 0:
                    failure = _desk_safe_result_text(start_result.stderr, start_result.stdout) or "The login task was created, but could not start immediately."
                    return bot_gateway_action_result(
                        action_id,
                        status="failed",
                        title="Bot background mode installed but not started",
                        detail=failure,
                        next_action="Log out and back in, or open Windows Task Scheduler and start the T-Sense Bot Gateway task.",
                        exit_code=start_result.returncode,
                    )
            return bot_gateway_action_result(
                action_id,
                status="success",
                title=success_title,
                detail=success_detail,
                next_action=success_next,
                exit_code=completed.returncode,
            )
        failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
        return bot_gateway_action_result(
            action_id,
            status="failed",
            title="Bot background change failed",
            detail=failure,
            next_action="Check scheduler permissions, then retry from Settings.",
            exit_code=completed.returncode,
        )

    if backend == "macos_launchd":
        plist_path = bot_gateway_launchd_plist_path()
        if action_id == "bot_gateway_install_autostart":
            write_bot_gateway_launchd_plist(plist_path, python_entry)
            args = ["launchctl", "load", "-w", str(plist_path)]
            success_title = "Bot background mode is on"
            success_detail = "launchd will start the local Bot Gateway at login."
            success_next = "You can close Signal Desk; bot actions resume when this user logs in."
        else:
            args = ["launchctl", "unload", "-w", str(plist_path)]
            success_title = "Bot background mode is off"
            success_detail = "Signal Desk removed the Bot Gateway LaunchAgent."
            success_next = "Manual bot runs still work from Settings or the local CLI."
    elif backend == "linux_systemd_user":
        service_path = bot_gateway_systemd_service_path()
        if action_id == "bot_gateway_install_autostart":
            write_bot_gateway_systemd_service(service_path, python_entry)
            try:
                reload_result = _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
            except (OSError, subprocess.TimeoutExpired):
                reload_result = subprocess.CompletedProcess(["systemctl"], 1, stdout="", stderr="systemctl --user daemon-reload failed")
            if reload_result.returncode != 0:
                failure = _desk_safe_result_text(reload_result.stderr, reload_result.stdout) or "systemd user daemon reload failed."
                return bot_gateway_action_result(
                    action_id,
                    status="failed",
                    title="Bot background change failed",
                    detail=failure,
                    next_action="Check systemd --user availability, then retry from Settings.",
                    exit_code=reload_result.returncode,
                )
            args = ["systemctl", "--user", "enable", "--now", f"{DESK_BOT_GATEWAY_SYSTEMD_NAME}.service"]
            success_title = "Bot background mode is on"
            success_detail = "systemd --user will start the local Bot Gateway with your user session."
            success_next = "You can close Signal Desk; bot actions resume with this user session."
        else:
            args = ["systemctl", "--user", "disable", "--now", f"{DESK_BOT_GATEWAY_SYSTEMD_NAME}.service"]
            success_title = "Bot background mode is off"
            success_detail = "Signal Desk removed the Bot Gateway user service."
            success_next = "Manual bot runs still work from Settings or the local CLI."
    else:
        raise DashboardDeskActionError(f"Unknown Bot Gateway background backend: {backend}")

    try:
        completed = _run_scheduler_command(args)
    except subprocess.TimeoutExpired:
        return bot_gateway_action_result(
            action_id,
            status="failed",
            title="Bot background change timed out",
            detail="The local scheduler did not finish the requested change in time.",
            next_action="Check the local scheduler, then retry from Settings.",
        )
    except OSError:
        return bot_gateway_action_result(
            action_id,
            status="blocked",
            title="Local scheduler is unavailable",
            detail="Signal Desk could not start the local scheduler command on this machine.",
            next_action="Use manual bot runs until the scheduler is available.",
        )

    if backend == "macos_launchd" and action_id == "bot_gateway_remove_autostart":
        bot_gateway_launchd_plist_path().unlink(missing_ok=True)
    if backend == "linux_systemd_user" and action_id == "bot_gateway_remove_autostart":
        bot_gateway_systemd_service_path().unlink(missing_ok=True)
        try:
            _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
        except (OSError, subprocess.TimeoutExpired):
            pass

    if completed.returncode == 0:
        return bot_gateway_action_result(
            action_id,
            status="success",
            title=success_title,
            detail=success_detail,
            next_action=success_next,
            exit_code=completed.returncode,
        )
    failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
    return bot_gateway_action_result(
        action_id,
        status="failed",
        title="Bot background change failed",
        detail=failure,
        next_action="Check scheduler permissions, then retry from Settings.",
        exit_code=completed.returncode,
    )
