"""Desk action catalog, execution, progress, and result projection helpers."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from scripts import desk_scheduler, desk_sources


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESK_ACTION_TIMEOUT_SECONDS = 180
SECRET_TOKEN_RE = re.compile(r"\b\d{5,12}:[A-Za-z0-9_-]{10,}\b")
PROVIDER_KEY_RE = re.compile(r"\b(?:sk|sk-proj|sk-ant|ak)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE)
BEARER_SECRET_RE = re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]{8,}")
ENV_SECRET_RE = re.compile(r"(?i)\b[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)\b\s*=\s*[^\s`'\"]+")
KEY_VALUE_SECRET_RE = re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*[^\s`'\"]+")
ARGV_DUMP_RE = re.compile(r"(?i)\bargv\s*[:=]\s*(?:\[[^\]]*\]|[^\r\n]+)")
CHAT_ID_FIELD_RE = re.compile(r"\bchat[_ -]?id\b\s*[:=]?\s*-?\d{5,20}\b", re.IGNORECASE)
WINDOWS_PATH_RE = re.compile(r"(?i)\b[A-Z]:\\[^\r\n\"<>|]+")
UNC_PATH_RE = re.compile(r"\\\\[^\\\s]+\\[^\r\n\"<>|]+")
POSIX_PRIVATE_PATH_RE = re.compile(r"(?<!\w)/(?:home|Users|users|var|tmp|etc|private/tmp)/[^\s`'\"]+")
DashboardDeskActionError = desk_scheduler.DashboardDeskActionError
SourceAccessProbeError = desk_sources.SourceAccessProbeError

def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("scripts.dashboard_server")
    return getattr(facade, name, default) if facade is not None else default


def _project_root() -> Path:
    return Path(_facade_attr("PROJECT_ROOT", PROJECT_ROOT))


def _utc_now() -> str:
    now_fn = _facade_attr("_utc_now", None)
    if callable(now_fn) and now_fn is not _utc_now:
        return str(now_fn())
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_dashboard_openable_artifact_path(path: str) -> bool:
    helper = _facade_attr("is_dashboard_openable_artifact_path", None)
    if callable(helper):
        return bool(helper(path))
    cleaned = str(path or "").replace("\\", "/")
    return bool(cleaned and not cleaned.startswith("/") and ".." not in Path(cleaned).parts)


def _desk_action_env() -> dict[str, str]:
    helper = _facade_attr("desk_action_env", None)
    return helper() if callable(helper) else dict()


def _subprocess_module():
    return _facade_attr("subprocess", subprocess)


def _probe_source_access(progress_callback=None) -> dict:
    helper = _facade_attr("probe_source_access", desk_sources.probe_source_access)
    return helper(progress_callback=progress_callback)


def _source_access_health_detail(health: dict) -> str:
    helper = _facade_attr("_source_access_health_detail", desk_sources._source_access_health_detail)
    return str(helper(health))


def _source_access_action_summary(health: dict) -> dict:
    helper = _facade_attr("_source_access_action_summary", desk_sources._source_access_action_summary)
    return helper(health)


def _apply_source_access_repair(action_id: str, *, body: dict | None = None) -> dict:
    helper = _facade_attr("apply_source_access_repair", desk_sources.apply_source_access_repair)
    return helper(action_id, body=body)


def _run_desk_scheduler_action(action_id: str, *, body: dict | None = None) -> dict:
    helper = _facade_attr("run_desk_scheduler_action", None)
    if callable(helper):
        return helper(action_id, body=body)
    return desk_scheduler.run_desk_scheduler_action(action_id, body=body)


def _run_bot_gateway_autostart_action(action_id: str, *, body: dict | None = None) -> dict:
    helper = _facade_attr("run_bot_gateway_autostart_action", None)
    if callable(helper):
        return helper(action_id, body=body)
    return desk_scheduler.run_bot_gateway_autostart_action(action_id, body=body)


def _safe_profile_id(value: object) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", text):
        return ""
    return text


def _profile_id_from_body(body: dict | None) -> str:
    return _safe_profile_id((body or {}).get("profile_id"))


def _scan_window_hours_from_body(body: dict | None) -> int | None:
    payload = body or {}
    if "scan_window_hours" not in payload and "hours" not in payload:
        return None
    value = payload.get("scan_window_hours", payload.get("hours"))
    if isinstance(value, bool):
        raise DashboardDeskActionError("Scan window must be a whole number of hours from 1 to 168.")
    if isinstance(value, int):
        hours = value
    elif isinstance(value, str) and re.fullmatch(r"\d{1,3}", value.strip()):
        hours = int(value.strip())
    else:
        raise DashboardDeskActionError("Scan window must be a whole number of hours from 1 to 168.")
    if hours < 1 or hours > 168:
        raise DashboardDeskActionError("Scan window must be between 1 and 168 hours.")
    return hours


def _set_or_append_argv_option(argv: list[str], option: str, value: str) -> None:
    try:
        index = argv.index(option)
    except ValueError:
        argv.extend([option, value])
        return
    if index + 1 < len(argv):
        argv[index + 1] = value


def _preferred_monitor_profile_id(body: dict | None = None) -> str:
    requested = _profile_id_from_body(body)
    if requested:
        return requested
    fallback_profile_id = str(
        _facade_attr("DESK_SCHEDULER_PROFILE_ID", desk_scheduler.DESK_SCHEDULER_PROFILE_ID)
        or desk_scheduler.DESK_SCHEDULER_PROFILE_ID
    )
    return desk_scheduler.preferred_scheduler_profile_id(
        project_root=_project_root(),
        fallback_profile_id=fallback_profile_id,
    )


def _argv_for_action(action_id: str, action: dict, body: dict | None) -> list[str]:
    argv = [str(part) for part in action["argv"]]
    if action_id in {"monitor_jobs_dry_run", "schedule_preview"}:
        profile_id = _preferred_monitor_profile_id(body)
        try:
            index = argv.index("--profile-id")
        except ValueError:
            return argv
        if index + 1 < len(argv):
            argv[index + 1] = profile_id
    if action_id == "monitor_jobs_dry_run":
        hours = _scan_window_hours_from_body(body)
        if hours is not None:
            _set_or_append_argv_option(argv, "--hours", str(hours))
    return argv


def _display_command_for_argv(action: dict, argv: list[str]) -> str:
    if argv[:2] == ["monitor", "run"] and "--profile-id" in argv:
        profile_id = argv[argv.index("--profile-id") + 1]
        delivery_mode = "live"
        if "--delivery-mode" in argv:
            delivery_mode = argv[argv.index("--delivery-mode") + 1]
        hours = ""
        if "--hours" in argv and argv.index("--hours") + 1 < len(argv):
            hours = f" --hours {argv[argv.index('--hours') + 1]}"
        return f"tgcs monitor run --profile-id {profile_id} --delivery-mode {delivery_mode}{hours}"
    if argv[:2] == ["schedule", "print"] and "--profile-id" in argv:
        profile_id = argv[argv.index("--profile-id") + 1]
        interval_minutes = str(desk_scheduler.DESK_SCHEDULER_INTERVAL_MINUTES)
        delivery_mode = "live"
        if "--interval-minutes" in argv:
            interval_minutes = argv[argv.index("--interval-minutes") + 1]
        if "--delivery-mode" in argv:
            delivery_mode = argv[argv.index("--delivery-mode") + 1]
        return f"tgcs schedule print --profile-id {profile_id} --interval-minutes {interval_minutes} --delivery-mode {delivery_mode}"
    return str(action["display_command"])

_DESK_ACTION_LOCKS: dict[str, Lock] = {}
_DESK_ACTION_LOCKS_GUARD = Lock()
_DESK_LONG_RUNNING_ACTIONS = {"monitor_jobs_dry_run", "sources_probe_access"}
_DESK_ACTIVE_ACTIONS: dict[str, dict] = {}
_DESK_ACTIVE_ACTIONS_GUARD = Lock()

DESK_ACTIONS: tuple[dict, ...] = (
    {
        "action_id": "init_jobs",
        "group": "Setup",
        "title": "Prepare Signal Desk files",
        "detail": "Create the private local settings and starter channel list Signal Desk uses for scans.",
        "run_mode": "execute",
        "display_command": "tgcs init --starter jobs",
        "argv": ["init", "--starter", "jobs"],
        "next_action": "Check setup before scanning.",
    },
    {
        "action_id": "demo_render",
        "group": "Setup",
        "title": "Render offline demo",
        "detail": "Build output/demo-report.html without Telegram login or LLM keys.",
        "run_mode": "execute",
        "display_command": "tgcs demo",
        "argv": ["demo", "--output", "output/demo-report.html"],
        "artifact_keys": ["html_path", "output_path"],
        "next_action": "Open the demo report, then initialize real sources.",
    },
    {
        "action_id": "doctor_jobs",
        "group": "Setup",
        "title": "Check setup",
        "detail": "Check Telegram login, profiles, source list, and AI keys before a scan.",
        "run_mode": "execute",
        "display_command": "tgcs doctor --profile jobs",
        "argv": ["doctor", "--profile", "jobs", "--format", "json"],
        "next_action": "Fix anything marked blocked, then run an AI review.",
    },
    {
        "action_id": "sources_validate",
        "group": "Sources",
        "title": "Check source syntax",
        "detail": "Validate the saved source registry format without contacting Telegram.",
        "run_mode": "execute",
        "display_command": "tgcs sources validate",
        "argv": ["sources", "validate", "--format", "json"],
        "next_action": "Then run Check source access to test the real Telegram session.",
    },
    {
        "action_id": "sources_probe_access",
        "group": "Sources",
        "title": "Check source access",
        "detail": "Test whether enabled sources can be resolved and read by the local Telegram session. Message text is not stored.",
        "run_mode": "execute",
        "display_command": "Signal Desk source access check",
        "next_action": "Pause inaccessible sources or run an AI review after access looks healthy.",
    },
    {
        "action_id": "sources_pause_inaccessible",
        "group": "Sources",
        "title": "Pause inaccessible sources",
        "detail": "Disable sources from the latest access check that Telegram could not resolve or read.",
        "run_mode": "confirm_execute",
        "display_command": "Signal Desk: pause inaccessible sources",
        "next_action": "Run a fresh AI review after pausing inaccessible sources.",
    },
    {
        "action_id": "sources_keep_accessible",
        "group": "Sources",
        "title": "Keep only recently active sources",
        "detail": "Disable inaccessible and quiet sources from the latest access check. Quiet sources are readable, but had no recent messages in the probe window.",
        "run_mode": "confirm_execute",
        "display_command": "Signal Desk: keep recently active sources",
        "next_action": "Run a fresh AI review after narrowing the source list.",
    },
    {
        "action_id": "sources_import_jobs",
        "group": "Sources",
        "title": "Repair starter sources",
        "detail": "Restore or refresh the starter Telegram channels for the jobs monitor.",
        "run_mode": "execute",
        "display_command": "tgcs sources import channel_lists/jobs.txt --topic jobs",
        "argv": ["sources", "import", "channel_lists/jobs.txt", "--topic", "jobs", "--format", "json"],
        "next_action": "Check setup again, then run an AI review.",
    },
    {
        "action_id": "monitor_jobs_dry_run",
        "group": "Run",
        "title": "Run AI review",
        "detail": "Fetch latest source messages, create Review cards, and send Telegram alerts when notifications are enabled.",
        "run_mode": "execute",
        "display_command": "tgcs monitor run --profile-id jobs-fast --delivery-mode live",
        "argv": [
            "monitor",
            "run",
            "--profile-id",
            "jobs-fast",
            "--delivery-mode",
            "live",
            "--format",
            "json",
        ],
        "artifact_keys": ["html_path", "report_path", "manifest_path"],
        "timeout": 300,
        "next_action": "Review the new cards in Signal Desk or act on the Telegram alert buttons.",
    },
    {
        "action_id": "feedback_export",
        "group": "Feedback",
        "title": "Save learning file",
        "detail": "Advanced export for review decisions; Desk can generate profile drafts directly.",
        "run_mode": "execute",
        "display_command": "tgcs feedback export",
        "argv": ["feedback", "export", "--format", "json"],
        "artifact_keys": ["output_path"],
        "next_action": "Use Desk Learning to generate profile drafts, or keep the learning file for advanced workflows.",
    },
    {
        "action_id": "schedule_preview",
        "group": "Schedule",
        "title": "Preview auto review",
        "detail": "Preview the automatic AI-review cadence before turning it on.",
        "run_mode": "execute",
        "display_command": "tgcs schedule print --profile-id jobs-fast --interval-minutes 15 --delivery-mode live",
        "argv": [
            "schedule",
            "print",
            "--profile-id",
            "jobs-fast",
            "--interval-minutes",
            "15",
            "--delivery-mode",
            "live",
        ],
        "next_action": "Turn on automatic AI reviews from Signal Desk when ready.",
    },
    {
        "action_id": "schedule_install_dry_run",
        "group": "Schedule",
        "title": "Turn on auto review",
        "detail": "Create a local scheduler task for AI reviews and Telegram alerts when notifications are enabled.",
        "run_mode": "confirm_execute",
        "display_command": "Local scheduler: jobs-fast AI review",
        "next_action": "Signal Desk will run local AI reviews automatically every 15 minutes.",
    },
    {
        "action_id": "schedule_remove_dry_run",
        "group": "Schedule",
        "title": "Turn off auto review",
        "detail": "Remove the automatic AI review task created by Signal Desk.",
        "run_mode": "confirm_execute",
        "display_command": "Local scheduler: remove jobs-fast AI review",
        "next_action": "Automatic AI reviews are removed. Manual reviews still work in Signal Desk.",
    },
    {
        "action_id": "bot_gateway_install_autostart",
        "group": "Bot Gateway",
        "title": "Turn on bot background mode",
        "detail": "Start the local T-Sense Bot Gateway automatically at user login. It uses the saved local token and exposes no shell commands.",
        "run_mode": "confirm_execute",
        "display_command": "Local scheduler: T-Sense Bot Gateway",
        "next_action": "Close Signal Desk when you want; the local bot gateway will start again at login.",
    },
    {
        "action_id": "bot_gateway_remove_autostart",
        "group": "Bot Gateway",
        "title": "Turn off bot background mode",
        "detail": "Remove the login task for the local T-Sense Bot Gateway. Manual bot runs still work.",
        "run_mode": "confirm_execute",
        "display_command": "Local scheduler: remove T-Sense Bot Gateway",
        "next_action": "Start the bot manually from Signal Desk or the local CLI when needed.",
    },
    {
        "action_id": "login_human",
        "group": "Human takeover",
        "title": "Terminal login fallback",
        "detail": "Use the terminal login only if the built-in Desk login cannot complete on this machine.",
        "run_mode": "needs_human",
        "display_command": "tgcs login",
        "next_action": "Run tgcs login in a trusted terminal, then return to Signal Desk and check again.",
    },
    {
        "action_id": "live_delivery_human",
        "group": "Human takeover",
        "title": "Live delivery",
        "detail": "Live Telegram Bot delivery requires an intentional chat target and local token in Settings.",
        "run_mode": "needs_human",
        "display_command": "tgcs delivery test telegram-bot --delivery-mode live --chat-id <chat_id>",
        "next_action": "Save the token and chat id in Settings only when you intend to send live messages.",
    },
    {
        "action_id": "schedule_install_human",
        "group": "Human takeover",
        "title": "Live scheduler fallback",
        "detail": "Live delivery schedules still need an intentional terminal setup.",
        "run_mode": "needs_human",
        "display_command": "tgcs schedule print --profile-id jobs-fast --interval-minutes 15 --delivery-mode live",
        "next_action": "Only install a live schedule after Telegram delivery is intentionally configured.",
    },
)


DESK_ACTION_BY_ID = {action["action_id"]: action for action in DESK_ACTIONS}

def desk_actions() -> dict:
    return {
        "schema_version": "desk_actions_v1",
        "actions": [
            {
                "schema_version": "desk_action_v1",
                "action_id": action["action_id"],
                "group": action["group"],
                "title": action["title"],
                "detail": action["detail"],
                "run_mode": action["run_mode"],
                "display_command": action["display_command"],
                "next_action": action["next_action"],
            }
            for action in DESK_ACTIONS
        ],
    }
def _desk_display_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    normalized = value.strip().replace("\\", "/")
    path = Path(value.strip())
    if not path.is_absolute():
        return normalized if _is_dashboard_openable_artifact_path(normalized) else ""
    try:
        relative = str(path.resolve().relative_to(_project_root().resolve())).replace("\\", "/")
    except ValueError:
        return ""
    return relative if _is_dashboard_openable_artifact_path(relative) else ""

def _desk_payload_from_stdout(stdout: str) -> dict | None:
    text = stdout.strip()
    if not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None

def _desk_artifact_path(action: dict, data: dict) -> str:
    for key in action.get("artifact_keys", ()):
        path = _desk_display_path(data.get(key))
        if path:
            return path
    return ""

def _desk_success_detail(action: dict, payload: dict | None, stdout: str) -> tuple[str, str, str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    status = data.get("status")
    next_step = data.get("next_step")
    artifact_path = _desk_artifact_path(action, data)
    if action.get("action_id") == "schedule_preview":
        return (
            "Automatic AI reviews would run every 15 minutes. Telegram alerts use the saved notification target.",
            "",
            action["next_action"],
        )
    if isinstance(next_step, str) and next_step.strip():
        detail = _desk_safe_result_text(next_step)
    elif isinstance(status, str) and status.strip():
        detail = f"{action['title']} finished with status: {status.strip()}."
    elif stdout.strip() and not stdout.lstrip().startswith("{"):
        detail = _desk_safe_result_text(stdout)
    else:
        detail = _desk_action_success_copy(str(action.get("action_id") or ""), str(action.get("detail") or action["title"]))
    return detail, artifact_path, _desk_safe_result_text(next_step or action["next_action"])

def _desk_action_success_copy(action_id: str, fallback: str) -> str:
    return {
        "init_jobs": "Signal Desk files are ready. Next, check setup before scanning.",
        "doctor_jobs": "Setup check finished. If no problem is shown, run a fresh AI review.",
        "sources_validate": "Source list check finished. If no problem is shown, run a fresh AI review.",
        "sources_import_jobs": "Starter channels were repaired. Next, check setup, then run a fresh AI review.",
        "monitor_jobs_dry_run": "Fresh AI review finished. Open Review for cards or use the Telegram alert buttons.",
    }.get(action_id, f"{fallback} finished.")

def _desk_failure_detail(payload: dict | None, stdout: str, stderr: str) -> tuple[str, str]:
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = _desk_safe_result_text(error.get("message") or "Desk action failed.")
        next_step = _desk_safe_result_text(error.get("next_step") or "Inspect the command output and fix the reported issue.")
        return message, next_step
    text = (stderr or stdout or "Desk action failed.").strip()
    if text.lower().startswith("traceback (most recent call last):"):
        return (
            "This setup check could not finish.",
            "Refresh Signal Desk and rerun the check. If it keeps failing, reconnect Telegram from Start.",
        )
    return _desk_safe_result_text(text), "Inspect the command output and rerun the action when ready."

def _desk_safe_result_text(*parts: object) -> str:
    text = "\n".join(str(part or "") for part in parts).strip()
    if not text:
        return ""
    sanitized = text
    sanitized = SECRET_TOKEN_RE.sub("[redacted-token]", sanitized)
    sanitized = PROVIDER_KEY_RE.sub("[redacted-key]", sanitized)
    sanitized = BEARER_SECRET_RE.sub("Authorization: Bearer [redacted-key]", sanitized)
    sanitized = ENV_SECRET_RE.sub(lambda match: f"{match.group(0).split('=')[0].strip()}=[redacted-secret]", sanitized)
    sanitized = KEY_VALUE_SECRET_RE.sub(lambda match: re.split(r"[:=]", match.group(0), maxsplit=1)[0].strip() + "=[redacted-secret]", sanitized)
    sanitized = ARGV_DUMP_RE.sub("argv=[redacted-argv]", sanitized)
    sanitized = CHAT_ID_FIELD_RE.sub("chat_id [redacted-chat-id]", sanitized)
    project_roots = {str(PROJECT_ROOT), str(_project_root())}
    try:
        project_roots.add(str(_project_root().resolve()))
    except OSError:
        pass
    for raw in project_roots:
        if not raw or raw == ".":
            continue
        # Windows scheduler errors often include a concrete file below the
        # project root. Replace the whole local project path before the generic
        # drive-letter scrubber, otherwise the user sees a vague "local path"
        # and loses the actionable context that the failing file belongs to
        # this project folder.
        for variant in {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}:
            normalized = re.escape(variant).replace(r"\\", r"[\\/]")
            sanitized = re.sub(
                normalized + r"(?:[\\/][^\r\n\"<>|]*)?",
                "project folder",
                sanitized,
                flags=re.IGNORECASE,
            )
    sanitized = UNC_PATH_RE.sub("local path", sanitized)
    sanitized = WINDOWS_PATH_RE.sub("local path", sanitized)
    sanitized = POSIX_PRIVATE_PATH_RE.sub("local path", sanitized)
    replacements = {
        str(Path.home().resolve()): "~",
        str(Path.home().resolve()).replace("\\", "/"): "~",
    }
    for needle, replacement in replacements.items():
        if needle:
            sanitized = sanitized.replace(needle, replacement)
    return sanitized.splitlines()[0][:500]

def _desk_action_result(
    action_id: str,
    *,
    status: str,
    title: str,
    detail: str,
    next_action: str,
    exit_code: int | None = None,
    artifact_path: str = "",
    extra: dict | None = None,
) -> dict:
    action = DESK_ACTION_BY_ID[action_id]
    result = {
        "schema_version": "desk_action_result_v1",
        "action_id": action_id,
        "status": status,
        "title": title,
        "detail": detail,
        "display_command": action["display_command"],
        "exit_code": exit_code,
        "artifact_path": artifact_path,
        "next_action": next_action,
        "finished_at": _utc_now(),
    }
    if extra:
        result.update(extra)
    return result

def _desk_action_lock(action_id: str) -> Lock:
    with _DESK_ACTION_LOCKS_GUARD:
        lock = _DESK_ACTION_LOCKS.get(action_id)
        if lock is None:
            lock = Lock()
            _DESK_ACTION_LOCKS[action_id] = lock
        return lock

def _desk_mark_action_started(action_id: str, *, title: str) -> None:
    now = _utc_now()
    with _DESK_ACTIVE_ACTIONS_GUARD:
        _DESK_ACTIVE_ACTIONS[action_id] = {
            "schema_version": "desk_active_action_v1",
            "action_id": action_id,
            "title": title,
            "status": "running",
            "started_at": now,
            "updated_at": now,
            "detail": f"{title} is running. Keep Signal Desk open.",
        }

def _desk_update_action_progress(action_id: str, **updates: object) -> None:
    with _DESK_ACTIVE_ACTIONS_GUARD:
        current = _DESK_ACTIVE_ACTIONS.get(action_id)
        if not current:
            return
        current.update(updates)
        current["updated_at"] = _utc_now()

def _desk_mark_action_finished(action_id: str) -> None:
    with _DESK_ACTIVE_ACTIONS_GUARD:
        _DESK_ACTIVE_ACTIONS.pop(action_id, None)

def desk_active_actions() -> list[dict]:
    now = datetime.now(UTC)
    with _DESK_ACTIVE_ACTIONS_GUARD:
        active = [dict(item) for item in _DESK_ACTIVE_ACTIONS.values()]
    for item in active:
        started_at = str(item.get("started_at") or "")
        parsed = None
        if started_at.endswith("Z"):
            started_at = f"{started_at[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(started_at) if started_at else None
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            item["elapsed_seconds"] = max(0, int((now - parsed.astimezone(UTC)).total_seconds()))
        else:
            item["elapsed_seconds"] = 0
    return sorted(active, key=lambda value: str(value.get("started_at") or ""))

def run_desk_action(action_id: str, *, body: dict | None = None) -> dict:
    action = DESK_ACTION_BY_ID.get(action_id)
    if not action:
        raise DashboardDeskActionError(f"Unknown Desk action: {action_id}")

    lock = _desk_action_lock(action_id) if action_id in _DESK_LONG_RUNNING_ACTIONS else None
    if lock is not None and not lock.acquire(blocking=False):
        active = next((item for item in desk_active_actions() if item.get("action_id") == action_id), None)
        return _desk_action_result(
            action_id,
            status="blocked",
            title="Action already running",
            detail=str(active.get("detail") if active else "") or f"{action['title']} is still running. Wait for the current run to finish before starting another.",
            next_action="Wait for the current action to finish, then refresh Signal Desk.",
            extra={"active_action": active} if active else None,
        )

    try:
        if lock is not None:
            _desk_mark_action_started(action_id, title=str(action["title"]))
        return _run_desk_action_unlocked(action_id, action=action, body=body)
    finally:
        if lock is not None:
            _desk_mark_action_finished(action_id)
            lock.release()

def _run_desk_action_unlocked(action_id: str, *, action: dict, body: dict | None = None) -> dict:
    if action_id == "sources_probe_access":
        try:
            def progress(checked: int, total: int) -> None:
                _desk_update_action_progress(
                    action_id,
                    checked_count=checked,
                    total_count=total,
                    detail=f"Source access check running; checked {checked}/{total} sources. Keep Signal Desk open.",
                )

            health = _probe_source_access(progress_callback=progress)
        except SourceAccessProbeError as exc:
            return _desk_action_result(
                action_id,
                status=exc.status,
                title=_source_access_blocked_title(exc),
                detail=str(exc),
                next_action=exc.next_action,
            )
        except Exception as exc:
            return _desk_action_result(
                action_id,
                status="failed",
                title="Source access check failed",
                detail=f"Telegram access check could not finish ({exc.__class__.__name__}).",
                next_action="Retry once. If it keeps failing, reconnect Telegram and inspect the launcher window.",
            )
        return _desk_action_result(
            action_id,
            status="success",
            title="Source access checked",
            detail=_source_access_health_detail(health),
            next_action=(
                "Pause inaccessible sources, narrow to recently active sources, or run a fresh AI review."
                if int(health.get("inaccessible_count") or 0)
                else "Quiet sources are readable. Keep them, narrow to recently active sources, or run a fresh AI review."
                if int(health.get("quiet_count") or 0)
                else "Run a fresh AI review."
            ),
            extra={"source_access": _source_access_action_summary(health)},
        )

    if action_id in {"sources_pause_inaccessible", "sources_keep_accessible"}:
        return _apply_source_access_repair(action_id, body=body)

    if action_id in {"schedule_install_dry_run", "schedule_remove_dry_run"}:
        return _run_desk_scheduler_action(action_id, body=body)

    if action_id in {"bot_gateway_install_autostart", "bot_gateway_remove_autostart"}:
        return _run_bot_gateway_autostart_action(action_id, body=body)

    if action["run_mode"] != "execute":
        return {
            "schema_version": "desk_action_result_v1",
            "action_id": action_id,
            "status": "needs_human",
            "title": action["title"],
            "detail": action["detail"],
            "display_command": action["display_command"],
            "exit_code": None,
            "artifact_path": "",
            "next_action": action["next_action"],
            "finished_at": _utc_now(),
        }

    # The browser may send UI state in `body`, but execution never trusts a
    # client-supplied command. Every runnable Desk action maps to this static
    # argv allowlist so Signal Desk cannot become a localhost shell proxy.
    argv = _argv_for_action(action_id, action, body)
    display_command = _display_command_for_argv(action, argv)
    cmd = [sys.executable, str(_project_root() / "scripts" / "tgcs.py"), *argv]
    if action_id == "monitor_jobs_dry_run":
        _desk_update_action_progress(
            action_id,
            detail="AI review running; scanning sources, matching cards, and preparing Telegram alerts. Keep Signal Desk open.",
        )
    try:
        completed = _subprocess_module().run(
            cmd,
            cwd=_project_root(),
            check=False,
            capture_output=True,
            text=True,
            env=_desk_action_env(),
            timeout=int(action.get("timeout", DESK_ACTION_TIMEOUT_SECONDS)),
        )
    except subprocess.TimeoutExpired:
        return {
            "schema_version": "desk_action_result_v1",
            "action_id": action_id,
            "status": "failed",
            "title": action["title"],
            "detail": f"{action['title']} timed out.",
            "display_command": display_command,
            "exit_code": None,
            "artifact_path": "",
            "next_action": "Inspect the terminal or rerun the action with a narrower input.",
            "finished_at": _utc_now(),
        }

    payload = _desk_payload_from_stdout(completed.stdout or "")
    payload_ok = payload.get("ok") is not False if isinstance(payload, dict) else True
    if completed.returncode == 0 and payload_ok:
        detail, artifact_path, next_action = _desk_success_detail(action, payload, completed.stdout or "")
        status = "success"
    else:
        detail, next_action = _desk_failure_detail(payload, completed.stdout or "", completed.stderr or "")
        artifact_path = ""
        status = "failed"

    return {
        "schema_version": "desk_action_result_v1",
        "action_id": action_id,
        "status": status,
        "title": action["title"],
        "detail": detail,
        "display_command": display_command,
        "exit_code": completed.returncode,
        "artifact_path": artifact_path,
        "next_action": next_action,
        "finished_at": _utc_now(),
    }


def _source_access_blocked_title(exc: SourceAccessProbeError) -> str:
    text = f"{exc} {exc.next_action}".casefold()
    if "credential" in text:
        return "Connect Telegram first"
    if "login" in text or "authorized" in text:
        return "Finish Telegram login"
    if "no enabled sources" in text:
        return "Add a channel first"
    if "registry" in text or "syntax" in text or "saved source" in text:
        return "Fix saved channels first"
    return "Source access needs setup"
