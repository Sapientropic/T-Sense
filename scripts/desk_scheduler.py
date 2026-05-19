"""Local automatic scan scheduler helpers for Signal Desk."""

from __future__ import annotations

import os
import plistlib
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts import desk_bot_gateway_background, monitor_config, monitor_state
except ModuleNotFoundError:
    import desk_bot_gateway_background
    import monitor_config
    import monitor_state


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODE_ROOT = PROJECT_ROOT
PROJECT_ROOT_ENV = "TGCS_PROJECT_ROOT"
TG_SCANNER_CONFIG_DIR_ENV = "TG_SCANNER_CONFIG_DIR"
TGCLI_CONFIG_DIR_ENV = "TGCLI_CONFIG_DIR"
DESK_BOT_GATEWAY_STATE_FILENAME = "bot-gateway-state.json"
DESK_BOT_GATEWAY_STALE_SECONDS = 120
DESK_BOT_SUPPORTED_COMMANDS = ["/status", "/latest", "/sources", "/profiles", "/scan"]
DESK_SCHEDULER_PROFILE_ID = "market-news"
DESK_SCHEDULER_INTERVAL_MINUTES = 15
DESK_SCHEDULER_TASK_NAME = "T-Sense auto review"
DESK_SCHEDULER_LEGACY_TASK_NAMES = ("TGCS jobs-fast dry-run",)
DESK_SCHEDULER_LAUNCHD_LABEL = "com.sapientropic.tsense.auto-review"
DESK_SCHEDULER_LEGACY_LAUNCHD_LABELS = ("com.sapientropic.tgcs.jobs-fast.dry-run",)
DESK_SCHEDULER_SYSTEMD_NAME = "tsense-auto-review"
DESK_SCHEDULER_LEGACY_SYSTEMD_NAMES = ("tgcs-jobs-fast-dry-run",)
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
    desk_bot_gateway_background.CODE_ROOT = CODE_ROOT
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


def _safe_profile_id(value: object) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", text):
        return ""
    return text


def _configured_profiles_with_runtime_overrides(config: monitor_config.MonitorConfig, root: Path) -> list[dict[str, Any]]:
    profiles = list(config.profiles.values())
    database = str(config.defaults.get("database") or ".tgcs/tgcs.db")
    db_path = Path(database)
    if not db_path.is_absolute():
        db_path = root / db_path
    if not db_path.exists():
        return profiles
    try:
        conn = monitor_state.connect(db_path)
    except Exception:
        return profiles
    try:
        return [monitor_state.apply_profile_runtime_overrides(conn, profile) for profile in profiles]
    finally:
        conn.close()


def scheduler_profile_selection(
    *,
    project_root: Path | None = None,
    fallback_profile_id: str | None = None,
) -> dict[str, Any]:
    fallback = _safe_profile_id(fallback_profile_id or DESK_SCHEDULER_PROFILE_ID) or DESK_SCHEDULER_PROFILE_ID
    root = PROJECT_ROOT if project_root is None else project_root
    try:
        config = monitor_config.load_config(root / ".tgcs" / "profiles.toml")
    except ValueError:
        return {"profile_id": fallback, "has_enabled_profile": True, "source": "fallback_config_unavailable"}

    profiles = _configured_profiles_with_runtime_overrides(config, root)
    active_profiles = [profile for profile in profiles if profile.get("enabled", True)]
    desk_profiles = [
        (index, profile)
        for index, profile in enumerate(active_profiles)
        if str(profile.get("path") or "").replace("\\", "/").startswith("profiles/desk/")
    ]
    if desk_profiles:
        # Signal Desk-created profiles are the user's current matching intent.
        # Prefer the newest `profiles/desk/*` record so manual scans, schedule
        # previews, and installed background scans do not silently split into
        # different profiles. Keep the OS task name stable; reinstalling updates
        # the fixed task instead of creating per-profile orphan tasks.
        _, profile = sorted(desk_profiles, key=lambda item: (str(item[1].get("updated_at") or ""), item[0]))[-1]
        return {
            "profile_id": _safe_profile_id(profile.get("id")) or fallback,
            "has_enabled_profile": True,
            "source": "desk_profile",
        }

    fallback_profile = next((profile for profile in profiles if _safe_profile_id(profile.get("id")) == fallback), None)
    if fallback_profile is None:
        active_profile_ids = [_safe_profile_id(profile.get("id")) for profile in active_profiles]
        active_profile_ids = [profile_id for profile_id in active_profile_ids if profile_id]
        if len(active_profile_ids) == 1:
            # Older workspaces can have only the legacy jobs-fast profile in
            # profiles.toml. Use that one enabled profile instead of reporting
            # auto review as broken just because the new market-news fallback is
            # not present in the legacy config.
            return {
                "profile_id": active_profile_ids[0],
                "has_enabled_profile": True,
                "source": "single_active_profile",
            }
        return {"profile_id": fallback, "has_enabled_profile": False, "source": "fallback_missing"}
    if fallback_profile.get("enabled", True):
        return {"profile_id": fallback, "has_enabled_profile": True, "source": "fallback_profile"}
    return {"profile_id": fallback, "has_enabled_profile": False, "source": "fallback_disabled"}


def preferred_scheduler_profile_id(
    *,
    project_root: Path | None = None,
    fallback_profile_id: str | None = None,
) -> str:
    return str(
        scheduler_profile_selection(project_root=project_root, fallback_profile_id=fallback_profile_id)["profile_id"]
    )


def schedule_display_command(profile_id: str) -> str:
    return (
        f"tgcs schedule print --profile-id {profile_id} "
        f"--interval-minutes {DESK_SCHEDULER_INTERVAL_MINUTES} --delivery-mode live"
    )


def scheduler_result(
    action_id: str,
    *,
    status: str,
    title: str,
    detail: str,
    next_action: str,
    exit_code: int | None = None,
    display_command: str | None = None,
) -> dict:
    action = DESK_ACTION_BY_ID[action_id]
    return {
        "schema_version": "desk_action_result_v1",
        "action_id": action_id,
        "status": status,
        "title": title,
        "detail": detail,
        "display_command": display_command or action["display_command"],
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


def scheduler_base(backend: str, *, profile_id: str | None = None, has_enabled_profile: bool | None = None) -> dict:
    selected_profile_id = profile_id or preferred_scheduler_profile_id()
    profile_available = True if has_enabled_profile is None else has_enabled_profile
    can_install = backend in {"windows_schtasks", "macos_launchd", "linux_systemd_user"}
    return {
        "schema_version": "desk_scheduler_status_v1",
        "task_label": f"{selected_profile_id} AI review",
        "profile_id": selected_profile_id,
        "has_enabled_profile": profile_available,
        "interval_minutes": DESK_SCHEDULER_INTERVAL_MINUTES,
        "platform": sys.platform,
        "backend": backend,
        "can_install": can_install and profile_available,
        "can_remove": can_install,
        "display_command": schedule_display_command(selected_profile_id),
        "checked_at": _utc_now(),
    }


def launchd_labels() -> list[str]:
    labels = [DESK_SCHEDULER_LAUNCHD_LABEL]
    for label in DESK_SCHEDULER_LEGACY_LAUNCHD_LABELS:
        if label and label not in labels:
            labels.append(label)
    return labels


def launchd_plist_path(label: str | None = None) -> Path:
    selected_label = label or DESK_SCHEDULER_LAUNCHD_LABEL
    return Path.home() / "Library" / "LaunchAgents" / f"{selected_label}.plist"


def launchd_plist_paths() -> list[tuple[str, Path]]:
    return [(label, launchd_plist_path(label)) for label in launchd_labels()]


def systemd_user_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def systemd_names() -> list[str]:
    names = [DESK_SCHEDULER_SYSTEMD_NAME]
    for name in DESK_SCHEDULER_LEGACY_SYSTEMD_NAMES:
        if name and name not in names:
            names.append(name)
    return names


def systemd_service_path(name: str | None = None) -> Path:
    selected_name = name or DESK_SCHEDULER_SYSTEMD_NAME
    return systemd_user_dir() / f"{selected_name}.service"


def systemd_timer_path(name: str | None = None) -> Path:
    selected_name = name or DESK_SCHEDULER_SYSTEMD_NAME
    return systemd_user_dir() / f"{selected_name}.timer"


def systemd_unit_paths() -> list[tuple[str, Path, Path]]:
    return [(name, systemd_service_path(name), systemd_timer_path(name)) for name in systemd_names()]


def posix_tgcs_entry() -> Path:
    return CODE_ROOT / "tgcs"


def tgcs_script_path() -> Path:
    return CODE_ROOT / "scripts" / "tgcs.py"


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


def fixed_monitor_argv(entry: Path, *, profile_id: str | None = None) -> list[str]:
    selected_profile_id = profile_id or preferred_scheduler_profile_id()
    return [
        str(entry),
        "monitor",
        "run",
        "--profile-id",
        selected_profile_id,
        "--delivery-mode",
        "live",
    ]


def fixed_monitor_python_argv(python_entry: Path | None = None, *, profile_id: str | None = None) -> list[str]:
    selected_profile_id = profile_id or preferred_scheduler_profile_id()
    return [
        str(python_entry or pythonw_entry()),
        str(tgcs_script_path()),
        "monitor",
        "run",
        "--profile-id",
        selected_profile_id,
        "--delivery-mode",
        "live",
    ]


def windows_task_action(argv: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part or "\\" in part else part for part in argv)


def _telegram_config_dir() -> Path:
    return PROJECT_ROOT / ".tgcs" / "telegram"


def app_runtime_environment() -> dict[str, str]:
    telegram_dir = _telegram_config_dir()
    return {
        PROJECT_ROOT_ENV: str(PROJECT_ROOT),
        TG_SCANNER_CONFIG_DIR_ENV: str(telegram_dir),
        TGCLI_CONFIG_DIR_ENV: str(telegram_dir),
    }


def systemd_env_assignment(key: str, value: str) -> str:
    escaped = f"{key}={value}".replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def launchd_log_path(filename: str) -> str:
    getuid = getattr(os, "getuid", None)
    uid = str(getuid()) if callable(getuid) else "user"
    log_dir_text = f"/tmp/tsense-launchd-{uid}"
    Path(log_dir_text).mkdir(parents=True, exist_ok=True)
    return f"{log_dir_text}/{filename}"


def windows_scheduler_task_names() -> list[str]:
    names = [DESK_SCHEDULER_TASK_NAME]
    for name in DESK_SCHEDULER_LEGACY_TASK_NAMES:
        if name and name not in names:
            names.append(name)
    return names


def _cleanup_legacy_windows_scheduler_tasks() -> None:
    for task_name in windows_scheduler_task_names()[1:]:
        try:
            _run_scheduler_command(["schtasks.exe", "/Delete", "/TN", task_name, "/F"])
        except (OSError, subprocess.TimeoutExpired):
            pass


def _cleanup_legacy_launchd_scheduler_tasks() -> None:
    for label, plist_path in launchd_plist_paths()[1:]:
        try:
            _run_scheduler_command(["launchctl", "unload", "-w", str(plist_path)])
        except (OSError, subprocess.TimeoutExpired):
            pass
        plist_path.unlink(missing_ok=True)


def _cleanup_legacy_systemd_scheduler_units() -> None:
    removed = False
    for name, service_path, timer_path in systemd_unit_paths()[1:]:
        try:
            _run_scheduler_command(["systemctl", "--user", "disable", "--now", f"{name}.timer"])
        except (OSError, subprocess.TimeoutExpired):
            pass
        if service_path.exists() or timer_path.exists():
            removed = True
        service_path.unlink(missing_ok=True)
        timer_path.unlink(missing_ok=True)
    if removed:
        try:
            _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
        except (OSError, subprocess.TimeoutExpired):
            pass


def _remove_launchd_scheduler_tasks() -> subprocess.CompletedProcess[str]:
    targets = [(label, path) for label, path in launchd_plist_paths() if path.exists()]
    if not targets:
        targets = [(DESK_SCHEDULER_LAUNCHD_LABEL, launchd_plist_path())]

    completed: subprocess.CompletedProcess[str] | None = None
    for _label, plist_path in targets:
        completed = _run_scheduler_command(["launchctl", "unload", "-w", str(plist_path)])
        # Remove the file even if launchctl reports that the job is not loaded:
        # stale LaunchAgent plists are exactly what keeps old auto-review jobs
        # coming back after users think they have turned the feature off.
        plist_path.unlink(missing_ok=True)
        if completed.returncode != 0:
            return completed
    return completed or subprocess.CompletedProcess(["launchctl"], 0, stdout="", stderr="")


def _remove_systemd_scheduler_units() -> subprocess.CompletedProcess[str]:
    targets = [
        (name, service_path, timer_path)
        for name, service_path, timer_path in systemd_unit_paths()
        if service_path.exists() or timer_path.exists()
    ]
    if not targets:
        targets = [(DESK_SCHEDULER_SYSTEMD_NAME, systemd_service_path(), systemd_timer_path())]

    completed: subprocess.CompletedProcess[str] | None = None
    removed = False
    for name, service_path, timer_path in targets:
        completed = _run_scheduler_command(["systemctl", "--user", "disable", "--now", f"{name}.timer"])
        if completed.returncode != 0:
            return completed
        if service_path.exists() or timer_path.exists():
            removed = True
        service_path.unlink(missing_ok=True)
        timer_path.unlink(missing_ok=True)

    if removed:
        try:
            _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
        except (OSError, subprocess.TimeoutExpired):
            pass
    return completed or subprocess.CompletedProcess(["systemctl"], 0, stdout="", stderr="")


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


def repair_installed_bot_gateway_background() -> dict:
    _sync_bot_gateway_context()
    return desk_bot_gateway_background.repair_installed_bot_gateway_background()


def desk_scheduler_status() -> dict:
    backend = scheduler_backend()
    selection = scheduler_profile_selection()
    profile_id = str(selection["profile_id"])
    has_enabled_profile = bool(selection["has_enabled_profile"])
    base = scheduler_base(backend, profile_id=profile_id, has_enabled_profile=has_enabled_profile)
    if backend == "manual_cron_preview":
        return {
            **base,
            "available": False,
            "installed": False,
            "status": "manual" if sys.platform.startswith("linux") else "unavailable",
            "detail": "Automatic review install is not available on this machine; use the schedule preview or manual reviews.",
            "next_action": "Run tgcs schedule print --platform cron for a no-side-effect crontab preview.",
        }

    if backend == "macos_launchd":
        installed_label = ""
        installed_path = None
        for label, path in launchd_plist_paths():
            if path.exists():
                installed_label = label
                installed_path = path
                break
        if installed_path is not None:
            if not has_enabled_profile:
                return {
                    **base,
                    "available": True,
                    "installed": True,
                    "status": "profile_disabled",
                    "detail": "Automatic AI reviews are installed, but no enabled profile is available.",
                    "next_action": "Turn off auto review, or enable a profile before background checks continue.",
                    "task_name": installed_label,
                    "legacy_task_name": installed_label != DESK_SCHEDULER_LAUNCHD_LABEL,
                }
            return launchd_scheduler_status(base, label=installed_label)
        return {
            **base,
            "available": True,
            "installed": False,
            "status": "not_installed",
            "detail": "Automatic AI reviews are off.",
            "next_action": "Turn on auto review from Signal Desk when you want background checks.",
        }

    if backend == "linux_systemd_user":
        installed_name = ""
        installed = False
        for name, _service_path, timer_path in systemd_unit_paths():
            if timer_path.exists():
                installed_name = name
                installed = True
                break
        if installed and not has_enabled_profile:
            return {
                **base,
                "available": True,
                "installed": True,
                "status": "profile_disabled",
                "detail": "Automatic AI reviews are installed, but no enabled profile is available.",
                "next_action": "Turn off auto review, or enable a profile before background checks continue.",
                "task_name": installed_name,
                "legacy_task_name": installed_name != DESK_SCHEDULER_SYSTEMD_NAME,
            }
        return {
            **base,
            "available": True,
            "installed": installed,
            "status": "installed" if installed else "not_installed",
            "detail": "Automatic AI reviews are on every 15 minutes." if installed else "Automatic AI reviews are off.",
            "next_action": (
                "You can turn them off from Signal Desk when you no longer need background checks."
                if installed
                else "Turn on auto review from Signal Desk when you want background checks."
            ),
            **({"task_name": installed_name, "legacy_task_name": installed_name != DESK_SCHEDULER_SYSTEMD_NAME} if installed else {}),
        }

    try:
        completed = None
        installed_task_name = ""
        for task_name in windows_scheduler_task_names():
            candidate = _run_scheduler_command(["schtasks.exe", "/Query", "/TN", task_name])
            completed = candidate
            if candidate.returncode == 0:
                installed_task_name = task_name
                break
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

    if completed and completed.returncode == 0:
        if not has_enabled_profile:
            return {
                **base,
                "available": True,
                "installed": True,
                "status": "profile_disabled",
                "detail": "Automatic AI reviews are installed, but no enabled profile is available.",
                "next_action": "Turn off auto review, or enable a profile before background checks continue.",
                "task_name": installed_task_name,
                "legacy_task_name": installed_task_name != DESK_SCHEDULER_TASK_NAME,
            }
        return {
            **base,
            "available": True,
            "installed": True,
            "status": "installed",
            "detail": "Automatic AI reviews are on every 15 minutes.",
            "next_action": "You can turn them off from Signal Desk when you no longer need background checks.",
            "task_name": installed_task_name,
            "legacy_task_name": installed_task_name != DESK_SCHEDULER_TASK_NAME,
        }
    return {
        **base,
        "available": True,
        "installed": False,
        "status": "not_installed",
        "detail": "Automatic AI reviews are off.",
        "next_action": "Turn on auto review from Signal Desk when you want background checks.",
    }


def launchd_service_target(label: str | None = None) -> str:
    selected_label = label or DESK_SCHEDULER_LAUNCHD_LABEL
    getuid = getattr(os, "getuid", None)
    if callable(getuid):
        return f"gui/{getuid()}/{selected_label}"
    return selected_label


def launchd_last_exit_code(output: str) -> int | None:
    match = re.search(r"last exit code\s*=\s*(-?\d+)", output, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def launchd_failure_detail(subject: str, last_exit_code: int) -> str:
    if last_exit_code == 78:
        return (
            f"{subject} is installed, but launchd exited with code 78 (EX_CONFIG). "
            "This usually means launchd could not open the LaunchAgent plist or stdio log path. "
            "Repair from Signal Desk rewrites launchd-safe logs under /tmp."
        )
    return f"{subject} is installed, but launchd last exited with code {last_exit_code}."


def launchd_scheduler_status(base: dict, *, label: str | None = None) -> dict:
    selected_label = label or DESK_SCHEDULER_LAUNCHD_LABEL
    legacy = selected_label != DESK_SCHEDULER_LAUNCHD_LABEL
    try:
        completed = _run_scheduler_command(["launchctl", "print", launchd_service_target(selected_label)])
    except subprocess.TimeoutExpired:
        return {
            **base,
            "available": True,
            "installed": True,
            "status": "unknown",
            "detail": "Automatic reviews are installed, but Signal Desk could not confirm launchd status before the check timed out.",
            "next_action": "If new Review cards stop arriving, repair auto review from Signal Desk.",
            "task_name": selected_label,
            "legacy_task_name": legacy,
        }
    except OSError:
        return {
            **base,
            "available": True,
            "installed": True,
            "status": "unknown",
            "detail": "Automatic reviews are installed, but Signal Desk could not query launchd on this machine.",
            "next_action": "If new Review cards stop arriving, repair auto review from Signal Desk.",
            "task_name": selected_label,
            "legacy_task_name": legacy,
        }

    output = "\n".join([completed.stdout or "", completed.stderr or ""])
    last_exit_code = launchd_last_exit_code(output)
    if completed.returncode != 0:
        return {
            **base,
            "available": True,
            "installed": True,
            "status": "failed",
            "detail": "Automatic reviews are installed, but launchd does not report the job as loaded.",
            "next_action": "Repair auto review from Signal Desk to rewrite and reload the LaunchAgent.",
            "task_name": selected_label,
            "legacy_task_name": legacy,
            **({"last_exit_code": last_exit_code} if last_exit_code is not None else {}),
        }
    if last_exit_code not in (None, 0):
        return {
            **base,
            "available": True,
            "installed": True,
            "status": "failed",
            "detail": launchd_failure_detail("Automatic reviews", last_exit_code),
            "next_action": "Repair auto review from Signal Desk to rewrite and reload the LaunchAgent.",
            "last_exit_code": last_exit_code,
            "task_name": selected_label,
            "legacy_task_name": legacy,
        }
    return {
        **base,
        "available": True,
        "installed": True,
        "status": "installed",
        "detail": "Automatic AI reviews are on every 15 minutes.",
        "next_action": "You can turn them off from Signal Desk when you no longer need background checks.",
        "task_name": selected_label,
        "legacy_task_name": legacy,
        **({"last_exit_code": last_exit_code} if last_exit_code is not None else {}),
    }


def write_launchd_plist(path: Path, python_entry: Path, *, profile_id: str | None = None) -> None:
    selected_profile_id = profile_id or preferred_scheduler_profile_id()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": DESK_SCHEDULER_LAUNCHD_LABEL,
        "ProgramArguments": fixed_monitor_python_argv(python_entry, profile_id=selected_profile_id),
        "RunAtLoad": True,
        "StartInterval": DESK_SCHEDULER_INTERVAL_MINUTES * 60,
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": app_runtime_environment(),
        # launchd opens stdio paths before exec. Project-local output paths can
        # make repair appear successful while the job exits with EX_CONFIG
        # before Python starts, so keep these logs in a pre-created /tmp dir.
        "StandardOutPath": launchd_log_path(f"tgcs-{selected_profile_id}.log"),
        "StandardErrorPath": launchd_log_path(f"tgcs-{selected_profile_id}.err.log"),
    }
    with path.open("wb") as handle:
        plistlib.dump(payload, handle)


def write_systemd_units(service_path: Path, timer_path: Path, entry: Path, *, profile_id: str | None = None) -> None:
    selected_profile_id = profile_id or preferred_scheduler_profile_id()
    service_path.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_ROOT.joinpath("output").mkdir(parents=True, exist_ok=True)
    exec_start = " ".join(
        [
            systemd_exec_path(entry),
            "monitor",
            "run",
            "--profile-id",
            selected_profile_id,
            "--delivery-mode",
            "live",
        ]
    )
    service_path.write_text(
        "\n".join(
            [
                "[Unit]",
                f"Description=T-Sense {selected_profile_id} AI review",
                "",
                "[Service]",
                "Type=oneshot",
                f"WorkingDirectory={PROJECT_ROOT}",
                *[
                    f"Environment={systemd_env_assignment(key, value)}"
                    for key, value in app_runtime_environment().items()
                ],
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
                f"Description=Run T-Sense {selected_profile_id} AI review every 15 minutes",
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
    selection = scheduler_profile_selection()
    profile_id = str(selection["profile_id"])
    has_enabled_profile = bool(selection["has_enabled_profile"])
    display_command = schedule_display_command(profile_id)
    backend = scheduler_backend()
    if backend == "manual_cron_preview":
        return scheduler_result(
            action_id,
            status="blocked",
            title="Auto scan needs a supported scheduler",
            detail="Signal Desk will not edit crontab directly. This machine can use the schedule preview or manual scans.",
            next_action="Run tgcs schedule print --platform cron for a no-side-effect crontab preview.",
            display_command=display_command,
        )

    tgcs_entry = CODE_ROOT / "tgcs.bat" if backend == "windows_schtasks" else posix_tgcs_entry()
    macos_tgcs_script = tgcs_script_path()
    required_entries = [macos_tgcs_script] if backend in {"windows_schtasks", "macos_launchd"} else [tgcs_entry]
    if action_id == "schedule_install_dry_run" and any(not entry.exists() for entry in required_entries):
        return scheduler_result(
            action_id,
            status="blocked",
            title="Launcher file is missing",
            detail="Signal Desk could not find the local T-Sense launcher or scheduler entry file.",
            next_action="Repair the repo-local install, then turn on auto scan again.",
            display_command=display_command,
        )

    if action_id not in {"schedule_install_dry_run", "schedule_remove_dry_run"}:
        raise DashboardDeskActionError(f"Unknown scheduler action: {action_id}")
    if action_id == "schedule_install_dry_run" and not has_enabled_profile:
        return scheduler_result(
            action_id,
            status="blocked",
            title="No enabled profile for auto review",
            detail="All matching profiles are paused, so Signal Desk will not install a background auto-review task.",
            next_action="Enable a profile, then turn on auto review again.",
            display_command=display_command,
        )

    if backend == "windows_schtasks":
        # Keep this as a single fixed /TR argument in a list argv call. Do not
        # refactor this path through shell=True: the browser must never be able
        # to turn scheduler setup into a local shell proxy.
        task_action = windows_task_action(fixed_monitor_python_argv(profile_id=profile_id))
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
            success_detail = f"Windows Task Scheduler will run {profile_id} AI reviews every 15 minutes. Telegram alerts use the saved notification target."
            success_next = "You can leave Signal Desk and return later to review new Inbox cards."
        else:
            args = ["schtasks.exe", "/Delete", "/TN", DESK_SCHEDULER_TASK_NAME, "/F"]
            success_title = "Auto scan is off"
            success_detail = "Signal Desk removed the Windows Task Scheduler task for automatic AI reviews."
            success_next = "Manual scans still work from Signal Desk."

        try:
            if action_id == "schedule_remove_dry_run":
                completed = None
                for task_name in windows_scheduler_task_names():
                    candidate = _run_scheduler_command(["schtasks.exe", "/Delete", "/TN", task_name, "/F"])
                    completed = candidate
                    if candidate.returncode == 0:
                        break
                if completed is None:
                    completed = subprocess.CompletedProcess(args, 1, stdout="", stderr="The local scheduler rejected the change.")
            else:
                completed = _run_scheduler_command(args)
        except subprocess.TimeoutExpired:
            return scheduler_result(
                action_id,
                status="failed",
                title="Scheduler change timed out",
                detail="The local scheduler did not finish the requested change in time.",
                next_action="Check the local scheduler, then retry from Signal Desk.",
                display_command=display_command,
            )
        except OSError:
            return scheduler_result(
                action_id,
                status="blocked",
                title="Scheduler is unavailable",
                detail="Signal Desk could not start the local scheduler command on this machine.",
                next_action="Use manual scans in Signal Desk, or install the task from the local scheduler.",
                display_command=display_command,
            )

        if completed.returncode == 0:
            if action_id == "schedule_install_dry_run":
                _cleanup_legacy_windows_scheduler_tasks()
            return scheduler_result(
                action_id,
                status="success",
                title=success_title,
                detail=success_detail,
                next_action=success_next,
                exit_code=completed.returncode,
                display_command=display_command,
            )

        failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
        return scheduler_result(
            action_id,
            status="failed",
            title="Scheduler change failed",
            detail=failure,
            next_action="Check scheduler permissions, then retry from Signal Desk.",
            exit_code=completed.returncode,
            display_command=display_command,
        )

    if backend == "macos_launchd":
        plist_path = launchd_plist_path()
        if action_id == "schedule_install_dry_run":
            write_launchd_plist(plist_path, pythonw_entry(), profile_id=profile_id)
            try:
                _run_scheduler_command(["launchctl", "unload", "-w", str(plist_path)])
            except (OSError, subprocess.TimeoutExpired):
                pass
            args = ["launchctl", "load", "-w", str(plist_path)]
            success_title = "Auto scan is on"
            success_detail = f"launchd will run {profile_id} AI reviews every 15 minutes. Telegram alerts use the saved notification target."
            success_next = "You can leave Signal Desk and return later to review new Inbox cards."
        else:
            args = ["launchctl", "unload", "-w", str(plist_path)]
            success_title = "Auto scan is off"
            success_detail = "Signal Desk removed the launchd LaunchAgent for automatic AI reviews."
            success_next = "Manual scans still work from Signal Desk."

    elif backend == "linux_systemd_user":
        service_path = systemd_service_path()
        timer_path = systemd_timer_path()
        if action_id == "schedule_install_dry_run":
            write_systemd_units(service_path, timer_path, tgcs_entry, profile_id=profile_id)
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
                    display_command=display_command,
                )
            args = ["systemctl", "--user", "enable", "--now", f"{DESK_SCHEDULER_SYSTEMD_NAME}.timer"]
            success_title = "Auto scan is on"
            success_detail = f"systemd --user will run {profile_id} AI reviews every 15 minutes. Telegram alerts use the saved notification target."
            success_next = "You can leave Signal Desk and return later to review new Inbox cards."
        else:
            args = ["systemctl", "--user", "disable", "--now", f"{DESK_SCHEDULER_SYSTEMD_NAME}.timer"]
            success_title = "Auto scan is off"
            success_detail = "Signal Desk removed the systemd user timer for automatic AI reviews."
            success_next = "Manual scans still work from Signal Desk."
    else:
        raise DashboardDeskActionError(f"Unknown scheduler backend: {backend}")

    try:
        if backend == "macos_launchd" and action_id == "schedule_remove_dry_run":
            completed = _remove_launchd_scheduler_tasks()
        elif backend == "linux_systemd_user" and action_id == "schedule_remove_dry_run":
            completed = _remove_systemd_scheduler_units()
        else:
            completed = _run_scheduler_command(args)
    except subprocess.TimeoutExpired:
        return scheduler_result(
            action_id,
            status="failed",
            title="Scheduler change timed out",
            detail="The local scheduler did not finish the requested change in time.",
            next_action="Check the local scheduler, then retry from Signal Desk.",
            display_command=display_command,
        )
    except OSError:
        return scheduler_result(
            action_id,
            status="blocked",
            title="Scheduler is unavailable",
            detail="Signal Desk could not start the local scheduler command on this machine.",
            next_action="Use manual scans in Signal Desk, or install the task from the local scheduler.",
            display_command=display_command,
        )

    if completed.returncode == 0:
        if action_id == "schedule_install_dry_run" and backend == "macos_launchd":
            health = launchd_scheduler_status(
                scheduler_base(backend, profile_id=profile_id, has_enabled_profile=has_enabled_profile),
            )
            if health.get("status") == "failed":
                return scheduler_result(
                    action_id,
                    status="failed",
                    title="Auto scan installed but launchd did not start",
                    detail=str(health.get("detail") or "launchd reported the LaunchAgent as failed."),
                    next_action=str(
                        health.get("next_action")
                        or "Repair auto review from Signal Desk to rewrite and reload the LaunchAgent."
                    ),
                    exit_code=health.get("last_exit_code") if isinstance(health.get("last_exit_code"), int) else None,
                    display_command=display_command,
                )
            _cleanup_legacy_launchd_scheduler_tasks()
        if action_id == "schedule_install_dry_run" and backend == "linux_systemd_user":
            _cleanup_legacy_systemd_scheduler_units()
        return scheduler_result(
            action_id,
            status="success",
            title=success_title,
            detail=success_detail,
            next_action=success_next,
            exit_code=completed.returncode,
            display_command=display_command,
        )

    failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
    return scheduler_result(
        action_id,
        status="failed",
        title="Scheduler change failed",
        detail=failure,
        next_action="Check scheduler permissions, then retry from Signal Desk.",
        exit_code=completed.returncode,
        display_command=display_command,
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
