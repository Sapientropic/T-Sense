"""Localhost dashboard server for the v0.5-alpha review inbox."""

from __future__ import annotations

import argparse
import asyncio
import html
import ipaddress
import json
import mimetypes
import os
import re
import subprocess
import socket
import sys
import tomllib
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
from threading import Lock
from urllib import error as urllib_error
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

try:
    from scripts import agent_cli, delivery, local_credentials, monitor_state, source_registry
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import agent_cli, delivery, local_credentials, monitor_state, source_registry


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESK_HEALTH_SCHEMA_VERSION = "desk_health_v1"
DESK_APP_ID = "tgcs-signal-desk"
DESK_VERSION = "0.5.0-alpha.1"
DESK_AUTO_PORT_END = 8799
GIT_TIMEOUT_SECONDS = 25
DESK_ACTION_TIMEOUT_SECONDS = 180
LOOPBACK_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
TELEGRAM_CONFIG_DIR = Path(
    os.environ.get("TG_SCANNER_CONFIG_DIR")
    or os.environ.get("TGCLI_CONFIG_DIR")
    or os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".config", "tgcli")
)
TELEGRAM_CONFIG_PATH = TELEGRAM_CONFIG_DIR / "config.toml"
TELEGRAM_SESSION_PATH = TELEGRAM_CONFIG_DIR / "session"
TELEGRAM_LOGIN_CODE_TTL_SECONDS = 300
DESK_DELIVERY_TARGET_ID = "telegram-bot-default"
DESK_DELIVERY_ALLOWED_FIELDS = {"chat_id", "enabled"}
DESK_DELIVERY_TEST_ALLOWED_FIELDS = {"chat_id"}
DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS = {"token", "clear"}
DESK_SOURCE_IMPORT_ALLOWED_FIELDS = {"sources", "topic"}
DESK_SOURCE_UPDATE_ALLOWED_FIELDS = {"enabled"}
DESK_SOURCE_TOPIC_ALLOWED_FIELDS = {"topics"}
PROFILE_ENABLED_ALLOWED_FIELDS = {"enabled"}
PROFILE_RUNTIME_SETTINGS_ALLOWED_FIELDS = set(monitor_state.PROFILE_RUNTIME_SETTING_LIMITS)
DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH = 20000
DESK_SOURCE_IMPORT_MAX_CHANNELS = 500
DESK_SCHEDULER_PROFILE_ID = "jobs-fast"
DESK_SCHEDULER_INTERVAL_MINUTES = 15
DESK_SCHEDULER_TASK_NAME = "TGCS jobs-fast dry-run"
_DESK_TELEGRAM_LOGIN: dict[str, str] = {}
_DESK_TELEGRAM_LOGIN_LOCK = Lock()
REPORT_HTML_MOBILE_PATCH = """<style data-dashboard-report-mobile-patch>
@media (max-width: 520px) {
  .report-title {
    max-width: 100% !important;
    font-size: 2.35rem !important;
    line-height: 1.04 !important;
    overflow-wrap: anywhere !important;
    text-shadow: 3px 3px 0 color-mix(in oklch, var(--c-accent) 15%, transparent) !important;
  }
}
@media (max-width: 360px) {
  .report-title { font-size: 2rem !important; }
}
</style>"""


class DashboardGitError(Exception):
    """Raised when repository update checks or pulls cannot be completed safely."""


class DashboardArtifactError(Exception):
    """Raised when a requested dashboard artifact is missing or outside output/runs."""


class DashboardDeskActionError(Exception):
    """Raised when a Signal Desk action request is not on the local allowlist."""


@dataclass(frozen=True)
class DashboardServerSelection:
    url: str
    port: int
    server: ThreadingHTTPServer | None
    reused_existing: bool = False


DESK_ACTIONS: tuple[dict, ...] = (
    {
        "action_id": "init_jobs",
        "group": "Setup",
        "title": "Initialize jobs starter",
        "detail": "Create local .tgcs defaults and merge the jobs starter sources.",
        "run_mode": "execute",
        "display_command": "tgcs init --starter jobs",
        "argv": ["init", "--starter", "jobs"],
        "next_action": "Run the jobs doctor check.",
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
        "title": "Check jobs prerequisites",
        "detail": "Run first-use checks for the Developer Opportunity profile.",
        "run_mode": "execute",
        "display_command": "tgcs doctor --profile jobs",
        "argv": ["doctor", "--profile", "jobs", "--format", "json"],
        "next_action": "Resolve any blocking checks, then log in if needed.",
    },
    {
        "action_id": "sources_validate",
        "group": "Sources",
        "title": "Validate source registry",
        "detail": "Check the local source registry shape before scanning.",
        "run_mode": "execute",
        "display_command": "tgcs sources validate",
        "argv": ["sources", "validate", "--format", "json"],
        "next_action": "Import or fix sources if validation reports a problem.",
    },
    {
        "action_id": "sources_import_jobs",
        "group": "Sources",
        "title": "Import jobs sources",
        "detail": "Merge channel_lists/jobs.txt into the private source registry with the jobs topic.",
        "run_mode": "execute",
        "display_command": "tgcs sources import channel_lists/jobs.txt --topic jobs",
        "argv": ["sources", "import", "channel_lists/jobs.txt", "--topic", "jobs", "--format", "json"],
        "next_action": "Run the jobs doctor check again.",
    },
    {
        "action_id": "monitor_jobs_dry_run",
        "group": "Run",
        "title": "Run jobs monitor dry-run",
        "detail": "Run jobs-fast without sending alerts; report artifacts stay local.",
        "run_mode": "execute",
        "display_command": "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
        "argv": [
            "monitor",
            "run",
            "--profile-id",
            "jobs-fast",
            "--delivery-mode",
            "dry-run",
            "--format",
            "json",
        ],
        "artifact_keys": ["html_path", "report_path", "manifest_path"],
        "timeout": 300,
        "next_action": "Review the new Inbox cards or open the generated report.",
    },
    {
        "action_id": "feedback_export",
        "group": "Feedback",
        "title": "Export feedback",
        "detail": "Write note-free keep / skip / false-positive feedback JSONL.",
        "run_mode": "execute",
        "display_command": "tgcs feedback export",
        "argv": ["feedback", "export", "--format", "json"],
        "artifact_keys": ["output_path"],
        "next_action": "Reuse the exported file in a later decision-memory run.",
    },
    {
        "action_id": "schedule_preview",
        "group": "Schedule",
        "title": "Preview dry-run schedule",
        "detail": "Preview the automatic dry-run cadence before turning it on.",
        "run_mode": "execute",
        "display_command": "tgcs schedule print --profile-id jobs-fast --interval-minutes 15 --delivery-mode dry-run",
        "argv": [
            "schedule",
            "print",
            "--profile-id",
            "jobs-fast",
            "--interval-minutes",
            "15",
            "--delivery-mode",
            "dry-run",
        ],
        "next_action": "Turn on dry-run automation from Signal Desk when ready.",
    },
    {
        "action_id": "schedule_install_dry_run",
        "group": "Schedule",
        "title": "Turn on dry-run automation",
        "detail": "Create a Windows Task Scheduler task for the jobs monitor. It runs dry-runs only and sends no live alerts.",
        "run_mode": "confirm_execute",
        "display_command": "Windows Task Scheduler: jobs-fast dry-run",
        "next_action": "Signal Desk will run dry-run checks automatically every 15 minutes.",
    },
    {
        "action_id": "schedule_remove_dry_run",
        "group": "Schedule",
        "title": "Turn off dry-run automation",
        "detail": "Remove the Windows Task Scheduler task created by Signal Desk.",
        "run_mode": "confirm_execute",
        "display_command": "Windows Task Scheduler: remove jobs-fast dry-run",
        "next_action": "Automatic dry-run checks are removed. Manual scans still work in Signal Desk.",
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


def is_dashboard_report_artifact_name(name: str) -> bool:
    lower = name.lower()
    if lower in {"report.html", "report.md"}:
        return True
    path = PurePosixPath(lower)
    if path.suffix not in {".html", ".md"}:
        return False
    return "report" in path.stem.split("-")


def dashboard_host_warning(host: str) -> str | None:
    normalized = host.strip().lower()
    if normalized in LOOPBACK_DASHBOARD_HOSTS:
        return None
    return (
        "Dashboard host is not loopback. Dashboard state can include local workflow context "
        "and report artifacts may include raw context; only bind this server to a trusted interface."
    )


def _browser_host(host: str) -> str:
    normalized = str(host or "").strip()
    if normalized in {"", "0.0.0.0"}:
        return "127.0.0.1"
    if normalized == "::":
        return "::1"
    return normalized


def dashboard_url(host: str, port: int) -> str:
    browser_host = _browser_host(host)
    if ":" in browser_host and not browser_host.startswith("["):
        browser_host = f"[{browser_host}]"
    return f"http://{browser_host}:{port}"


def desk_health(*, host: str, port: int) -> dict:
    return {
        "schema_version": DESK_HEALTH_SCHEMA_VERSION,
        "app": DESK_APP_ID,
        "version": DESK_VERSION,
        "ok": True,
        "url": dashboard_url(host, port),
        "capabilities": [
            "desk_actions_v1",
            "desk_telegram_setup_v1",
            "desk_notification_token_v1",
            "desk_sources_v1",
            "desk_scheduler_v1",
            "dashboard_state_v1",
        ],
    }


def fetch_compatible_desk_health(host: str, port: int, *, timeout_seconds: float = 0.25) -> dict | None:
    try:
        with socket.create_connection((_browser_host(host), port), timeout=0.15):
            pass
    except OSError:
        return None
    try:
        with urlopen(f"{dashboard_url(host, port)}/api/desk/health", timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib_error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != DESK_HEALTH_SCHEMA_VERSION:
        return None
    if payload.get("app") != DESK_APP_ID:
        return None
    return payload


def select_dashboard_server(
    *,
    host: str,
    port: int,
    auto_port: bool,
    handler_cls: type[BaseHTTPRequestHandler] | None = None,
) -> DashboardServerSelection:
    if handler_cls is None:
        handler_cls = DashboardHandler
    ports = [port]
    if auto_port:
        ports.extend(range(port + 1, DESK_AUTO_PORT_END + 1))
    last_error: OSError | None = None
    for candidate in ports:
        if auto_port:
            health = fetch_compatible_desk_health(host, candidate)
            if health:
                return DashboardServerSelection(
                    url=str(health.get("url") or dashboard_url(host, candidate)),
                    port=candidate,
                    server=None,
                    reused_existing=True,
                )
        try:
            server = ThreadingHTTPServer((host, candidate), handler_cls)
            return DashboardServerSelection(
                url=dashboard_url(host, candidate),
                port=candidate,
                server=server,
            )
        except OSError as exc:
            last_error = exc
            if not auto_port:
                raise
    raise OSError(f"No available Signal Desk port in {port}-{DESK_AUTO_PORT_END}.") from last_error


def is_loopback_address(value: object) -> bool:
    text = str(value or "").strip().strip("[]")
    if not text:
        return False
    if text.casefold() == "localhost":
        return True
    if text.startswith("::ffff:"):
        text = text.removeprefix("::ffff:")
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


@contextmanager
def close_after_use(conn) -> Iterator:
    try:
        yield conn
    finally:
        conn.close()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_git(args: list[str], *, timeout: int = GIT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        command = " ".join(["git", *args])
        raise DashboardGitError(f"{command} timed out after {timeout} second(s).") from exc
    except OSError as exc:
        raise DashboardGitError(f"Unable to run git: {exc}") from exc


def _git_value(args: list[str]) -> str | None:
    completed = _run_git(args)
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _repo_web_url(remote_url: str | None) -> str | None:
    if not remote_url:
        return None
    if remote_url.startswith("git@github.com:"):
        remote_url = "https://github.com/" + remote_url.removeprefix("git@github.com:")
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    return remote_url


def _git_update_status(*, fetch: bool) -> dict:
    branch = _git_value(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    upstream = _git_value(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    remote_url = _git_value(["config", "--get", "remote.origin.url"])
    dirty_output = _git_value(["status", "--porcelain"]) or ""
    dirty_count = len([line for line in dirty_output.splitlines() if line.strip()])
    fetch_error = ""

    if fetch:
        completed = _run_git(["fetch", "--prune", "origin"], timeout=45)
        if completed.returncode != 0:
            fetch_error = (completed.stderr or completed.stdout or "git fetch failed").strip()

    head = _git_value(["rev-parse", "--short", "HEAD"])
    remote_head = _git_value(["rev-parse", "--short", upstream]) if upstream else None
    ahead = 0
    behind = 0
    status = "no_upstream"
    message = "No upstream branch is configured for this local branch."
    pull_allowed = False

    if fetch_error:
        status = "fetch_failed"
        message = fetch_error
    elif upstream:
        compare = _git_value(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
        if compare:
            parts = compare.split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
        if ahead == 0 and behind == 0:
            status = "up_to_date"
            message = "Local branch is up to date with upstream."
        elif ahead == 0 and behind > 0:
            status = "behind"
            message = f"{behind} upstream commit(s) available."
            pull_allowed = dirty_count == 0
        elif ahead > 0 and behind == 0:
            status = "ahead"
            message = f"Local branch is ahead of upstream by {ahead} commit(s)."
        else:
            status = "diverged"
            message = f"Local branch diverged: {ahead} ahead, {behind} behind."

    if dirty_count:
        pull_allowed = False
        if status == "behind":
            message = f"{message} Commit or stash {dirty_count} local change(s) before pulling."

    return {
        "schema_version": "git_update_status_v1",
        "status": status,
        "message": message,
        "branch": branch,
        "upstream": upstream,
        "repo_url": _repo_web_url(remote_url),
        "remote_url": remote_url,
        "head": head,
        "remote_head": remote_head,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty_count > 0,
        "dirty_count": dirty_count,
        "pull_allowed": pull_allowed,
        "fetched": fetch and not fetch_error,
        "checked_at": _utc_now(),
    }


def _git_pull_latest() -> dict:
    before = _git_update_status(fetch=True)
    if before["dirty"]:
        raise DashboardGitError("Working tree has local changes. Commit or stash them before pulling.")
    if before["status"] != "behind" or not before["pull_allowed"]:
        raise DashboardGitError(before["message"])
    completed = _run_git(["pull", "--ff-only"], timeout=60)
    if completed.returncode != 0:
        raise DashboardGitError((completed.stderr or completed.stdout or "git pull --ff-only failed").strip())
    after = _git_update_status(fetch=False)
    after["pull_output"] = (completed.stdout or "").strip()
    return after


def resolve_run_artifact_path(requested_path: str, *, artifact_root: Path | None = None) -> Path:
    decoded = unquote(requested_path).replace("\\", "/").lstrip("/")
    parts = PurePosixPath(decoded).parts
    if ".." in parts or not parts:
        raise DashboardArtifactError("artifact_path_outside_output_runs")
    if "runs" not in parts:
        raise DashboardArtifactError("artifact_path_must_include_runs")
    run_index = parts.index("runs")
    if run_index >= len(parts) - 2:
        raise DashboardArtifactError("artifact_path_missing")
    if not is_dashboard_report_artifact_name(parts[-1]):
        raise DashboardArtifactError("artifact_type_not_report")

    root = (artifact_root or PROJECT_ROOT.joinpath(*parts[: run_index + 1])).resolve()
    relative = "/".join(parts[run_index + 1 :])
    if not relative:
        raise DashboardArtifactError("artifact_path_missing")

    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DashboardArtifactError("artifact_path_outside_output_runs") from exc
    if not candidate.exists() or not candidate.is_file():
        raise DashboardArtifactError("artifact_not_found")
    return candidate


def dashboard_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def write_feedback_export(conn, *, output_path: Path | None = None) -> dict:
    target = output_path or PROJECT_ROOT / "output" / "feedback" / "review-feedback.jsonl"
    entries = monitor_state.export_feedback_entries(conn)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    target.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    return {
        "schema_version": "feedback_export_result_v1",
        "feedback_count": len(entries),
        "output_path": dashboard_relative_path(target),
    }


def _display_user_path(path: Path) -> str:
    try:
        return "~/" + str(path.resolve().relative_to(Path.home().resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def _load_telegram_credentials(*, config_path: Path = TELEGRAM_CONFIG_PATH) -> tuple[int, str]:
    api_id: int | None = None
    api_hash = ""
    if config_path.exists():
        try:
            with config_path.open("rb") as handle:
                payload = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError("Telegram credentials file is not readable TOML.") from exc
        raw_id = payload.get("api_id") if isinstance(payload, dict) else None
        raw_hash = payload.get("api_hash") if isinstance(payload, dict) else None
        if raw_id is not None:
            try:
                api_id = int(raw_id)
            except (TypeError, ValueError):
                api_id = None
        api_hash = str(raw_hash or "").strip()

    env_id = os.environ.get("TELEGRAM_API_ID")
    if env_id and api_id is None:
        try:
            api_id = int(env_id)
        except ValueError as exc:
            raise ValueError("TELEGRAM_API_ID must be a number.") from exc
    env_hash = os.environ.get("TELEGRAM_API_HASH")
    if env_hash and not api_hash:
        api_hash = env_hash.strip()

    if not api_id or api_id <= 0 or not api_hash:
        raise ValueError("Telegram app credentials are missing.")
    return api_id, api_hash


def _telegram_credentials_ready(*, config_path: Path = TELEGRAM_CONFIG_PATH) -> bool:
    try:
        _load_telegram_credentials(config_path=config_path)
    except ValueError:
        return False
    return True


def _telegram_session_ready(*, session_path: Path = TELEGRAM_SESSION_PATH) -> bool:
    try:
        return bool(session_path.exists() and session_path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _telegram_login_snapshot() -> dict[str, str]:
    with _DESK_TELEGRAM_LOGIN_LOCK:
        return dict(_DESK_TELEGRAM_LOGIN)


def _telegram_login_set(payload: dict[str, str]) -> None:
    with _DESK_TELEGRAM_LOGIN_LOCK:
        _DESK_TELEGRAM_LOGIN.clear()
        _DESK_TELEGRAM_LOGIN.update(payload)


def _telegram_login_clear() -> None:
    with _DESK_TELEGRAM_LOGIN_LOCK:
        _DESK_TELEGRAM_LOGIN.clear()


def _parse_utc_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _telegram_login_expired(login: dict[str, str], *, now: datetime | None = None) -> bool:
    if login.get("state") not in {"code_sent", "needs_password"}:
        return False
    sent_at = _parse_utc_timestamp(login.get("sent_at"))
    if sent_at is None:
        return True
    return (now or datetime.now(UTC)) - sent_at > timedelta(seconds=TELEGRAM_LOGIN_CODE_TTL_SECONDS)


def save_telegram_credentials(
    api_id: object,
    api_hash: object,
    *,
    config_path: Path = TELEGRAM_CONFIG_PATH,
    session_path: Path = TELEGRAM_SESSION_PATH,
) -> dict:
    try:
        clean_api_id = int(str(api_id).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("Telegram app ID must be a positive number.") from exc
    clean_api_hash = str(api_hash or "").strip()
    if clean_api_id <= 0:
        raise ValueError("Telegram app ID must be a positive number.")
    if not re.fullmatch(r"[A-Za-z0-9]{16,128}", clean_api_hash):
        raise ValueError("Telegram app hash must be 16-128 letters or numbers.")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        f"api_id = {clean_api_id}\napi_hash = {json.dumps(clean_api_hash)}\n",
        encoding="utf-8",
    )
    return telegram_status(config_path=config_path, session_path=session_path)


def telegram_status(
    *,
    config_path: Path = TELEGRAM_CONFIG_PATH,
    session_path: Path = TELEGRAM_SESSION_PATH,
) -> dict:
    credentials_ready = _telegram_credentials_ready(config_path=config_path)
    session_ready = _telegram_session_ready(session_path=session_path)
    login = _telegram_login_snapshot()
    expired_login = _telegram_login_expired(login)
    if expired_login:
        _telegram_login_clear()
        login = {}
    if session_ready:
        state = "authorized"
        detail = "Telegram is connected for local scans."
        next_step = "Run the first scan from Signal Desk."
    elif not credentials_ready:
        state = "credentials_missing"
        detail = "Telegram app credentials are not saved yet."
        next_step = "Save API ID and API hash, then send a login code."
    elif login.get("state") == "code_sent":
        state = "code_sent"
        detail = "Telegram sent a verification code."
        next_step = "Enter the code in Signal Desk to finish login."
    elif login.get("state") == "needs_password":
        state = "needs_password"
        detail = "Telegram accepted the code and requires the account two-step verification password."
        next_step = "Enter the two-step verification password to finish login."
    elif expired_login:
        state = "ready_for_code"
        detail = "The previous Telegram code expired. Send a new code from Signal Desk."
        next_step = "Send a new Telegram login code."
    else:
        state = "ready_for_code"
        detail = "Credentials are saved. Send a Telegram login code from Signal Desk."
        next_step = "Enter your phone number and send a login code."
    return {
        "schema_version": "desk_telegram_status_v1",
        "credentials_ready": credentials_ready,
        "session_ready": session_ready,
        "login_state": state,
        "detail": detail,
        "next_step": next_step,
        "config_path": _display_user_path(config_path),
        "session_path": _display_user_path(session_path),
    }


def _telegram_interactive_error(exc: Exception, *, action: str) -> ValueError:
    name = exc.__class__.__name__
    lowered = name.lower()
    if "phonecodeinvalid" in lowered:
        message = "Telegram rejected the verification code. Check the code and try again."
    elif "phonecodenot" in lowered or "phonecodeexpired" in lowered:
        message = "Telegram login code expired. Send a new code."
    elif "phonenumberinvalid" in lowered:
        message = "Telegram rejected the phone number. Include the country code and try again."
    elif "floodwait" in lowered:
        message = "Telegram is rate limiting login attempts. Wait before trying again."
    elif isinstance(exc, OSError):
        message = "Signal Desk could not save or read the Telegram session file."
    else:
        message = f"Telegram {action} failed. Check the details and try again."
    return ValueError(f"{message} ({name})")


async def _telegram_send_code_async(
    phone: str,
    *,
    config_path: Path = TELEGRAM_CONFIG_PATH,
    session_path: Path = TELEGRAM_SESSION_PATH,
) -> dict:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id, api_hash = _load_telegram_credentials(config_path=config_path)
    session_string = session_path.read_text(encoding="utf-8").strip() if session_path.exists() else ""
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            session_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                session_path.write_text(StringSession.save(client.session), encoding="utf-8")
            finally:
                _telegram_login_clear()
            return telegram_status(config_path=config_path, session_path=session_path)
        sent = await client.send_code_request(phone)
        _telegram_login_set(
            {
                "state": "code_sent",
                "phone": phone,
                "phone_code_hash": str(getattr(sent, "phone_code_hash", "") or ""),
                "sent_at": _utc_now(),
            }
        )
        return telegram_status(config_path=config_path, session_path=session_path)
    finally:
        await client.disconnect()


async def _telegram_verify_code_async(
    code: str,
    password: str = "",
    *,
    config_path: Path = TELEGRAM_CONFIG_PATH,
    session_path: Path = TELEGRAM_SESSION_PATH,
) -> dict:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from telethon.sessions import StringSession

    login = _telegram_login_snapshot()
    if _telegram_login_expired(login):
        _telegram_login_clear()
        raise ValueError("Telegram login code expired. Send a new code.")
    phone = login.get("phone", "")
    phone_code_hash = login.get("phone_code_hash", "")
    if not phone or not phone_code_hash:
        raise ValueError("Send a Telegram login code before verifying.")

    api_id, api_hash = _load_telegram_credentials(config_path=config_path)
    session_string = session_path.read_text(encoding="utf-8").strip() if session_path.exists() else ""
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.connect()
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                login["state"] = "needs_password"
                _telegram_login_set(login)
                return telegram_status(config_path=config_path, session_path=session_path)
            await client.sign_in(password=password)
        session_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            session_path.write_text(StringSession.save(client.session), encoding="utf-8")
        finally:
            _telegram_login_clear()
        return telegram_status(config_path=config_path, session_path=session_path)
    finally:
        await client.disconnect()


def telegram_send_code(
    phone: object,
    *,
    config_path: Path = TELEGRAM_CONFIG_PATH,
    session_path: Path = TELEGRAM_SESSION_PATH,
) -> dict:
    clean_phone = str(phone or "").strip()
    if not re.fullmatch(r"\+?[0-9][0-9 ()-]{5,24}", clean_phone):
        raise ValueError("Enter a phone number with country code.")
    try:
        return asyncio.run(_telegram_send_code_async(clean_phone, config_path=config_path, session_path=session_path))
    except ValueError:
        raise
    except Exception as exc:
        raise _telegram_interactive_error(exc, action="code request") from exc


def telegram_verify_code(
    code: object,
    password: object = "",
    *,
    config_path: Path = TELEGRAM_CONFIG_PATH,
    session_path: Path = TELEGRAM_SESSION_PATH,
) -> dict:
    clean_code = str(code or "").strip().replace(" ", "")
    clean_password = str(password or "")
    if not re.fullmatch(r"[0-9A-Za-z-]{3,32}", clean_code):
        raise ValueError("Enter the Telegram verification code.")
    try:
        return asyncio.run(
            _telegram_verify_code_async(clean_code, clean_password, config_path=config_path, session_path=session_path)
        )
    except ValueError:
        raise
    except Exception as exc:
        raise _telegram_interactive_error(exc, action="login") from exc


def telegram_cancel_login() -> dict:
    _telegram_login_clear()
    return telegram_status()


def _delivery_target_projection(conn, target_id: str) -> dict:
    row = conn.execute("SELECT * FROM delivery_targets WHERE target_id = ?", (target_id,)).fetchone()
    if not row:
        raise ValueError("Notification target is not saved yet.")
    return monitor_state.delivery_target_from_row(row)


def _validate_desk_delivery_target_id(target_id: str) -> str:
    clean = str(target_id or "").strip()
    if clean != DESK_DELIVERY_TARGET_ID:
        raise ValueError("Signal Desk can only edit the default Telegram notification target.")
    return clean


def _reject_unexpected_delivery_fields(body: dict, *, allowed: set[str]) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in allowed)
    if unexpected:
        raise ValueError(f"Unsupported notification setting field: {', '.join(unexpected)}")


def _clean_delivery_chat_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 128 or not re.fullmatch(r"@?[A-Za-z0-9_:+.-]+", text):
        raise ValueError("Telegram chat ID must be a short number, @channel, or channel identifier.")
    return text


def save_desk_delivery_target(conn, target_id: str, body: dict) -> dict:
    clean_target_id = _validate_desk_delivery_target_id(target_id)
    _reject_unexpected_delivery_fields(body, allowed=DESK_DELIVERY_ALLOWED_FIELDS)
    chat_id = _clean_delivery_chat_id(body.get("chat_id"))
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("Notification target enabled value must be true or false.")
    if enabled and not chat_id:
        raise ValueError("Enter a Telegram chat ID before enabling notifications.")
    monitor_state.upsert_delivery_target(
        conn,
        {
            "id": clean_target_id,
            "type": "telegram_bot",
            "enabled": enabled,
            "chat_id": chat_id,
        },
    )
    return _delivery_target_projection(conn, clean_target_id)


def test_desk_delivery_target(conn, target_id: str, body: dict) -> dict:
    clean_target_id = _validate_desk_delivery_target_id(target_id)
    _reject_unexpected_delivery_fields(body, allowed=DESK_DELIVERY_TEST_ALLOWED_FIELDS)
    chat_id = _clean_delivery_chat_id(body.get("chat_id"))
    if not chat_id:
        try:
            current = _delivery_target_projection(conn, clean_target_id)
            config = current.get("config") if isinstance(current.get("config"), dict) else {}
            chat_id = _clean_delivery_chat_id(config.get("chat_id"))
        except ValueError:
            chat_id = ""
    attempt = delivery.send_telegram_bot_message(
        target_id=clean_target_id,
        chat_id=chat_id,
        text="Signal Desk notification test. No Telegram message was sent.",
        mode="dry-run",
    ).to_dict()
    detail = (
        "Dry-run passed. Signal Desk can use this chat ID when live notifications are turned on."
        if attempt.get("ok")
        else str(attempt.get("error") or "Dry-run could not validate the notification target.")
    )
    return {
        "schema_version": "desk_delivery_test_result_v1",
        "target_id": clean_target_id,
        "target_type": "telegram_bot",
        "mode": "dry-run",
        "ok": bool(attempt.get("ok")),
        "status": str(attempt.get("status") or "unknown"),
        "title": "Notification test",
        "detail": detail,
        "finished_at": _utc_now(),
    }


def _local_notification_token() -> local_credentials.StoredSecret | None:
    if not local_credentials.is_supported():
        return None
    return local_credentials.read_secret(delivery.TELEGRAM_BOT_TOKEN_CREDENTIAL_TARGET)


def desk_notification_token_status() -> dict:
    env_configured = bool(os.environ.get(delivery.TELEGRAM_BOT_TOKEN_ENV, "").strip())
    local_supported = local_credentials.is_supported()
    local_configured = False
    local_updated_at: str | None = None
    local_error = ""
    if local_supported:
        try:
            stored = _local_notification_token()
        except local_credentials.CredentialStoreError as exc:
            stored = None
            local_error = str(exc)
        local_configured = bool(stored and stored.secret.strip())
        local_updated_at = stored.updated_at if stored else None

    source = "environment" if env_configured else "windows_credential_manager" if local_configured else "missing"
    configured = env_configured or local_configured
    if env_configured:
        detail = "Telegram bot token is configured from the environment. Environment wins over local storage."
    elif local_configured:
        detail = "Telegram bot token is saved in Windows Credential Manager."
    elif local_supported:
        detail = "Telegram bot token is not configured."
    else:
        detail = "[⚠️ 需确认] Local secure token storage currently supports Windows Credential Manager only."
    return {
        "schema_version": "desk_notification_token_status_v1",
        "configured": configured,
        "source": source,
        "updated_at": None if env_configured else local_updated_at,
        "env_configured": env_configured,
        "local_store_supported": local_supported,
        "local_store_configured": local_configured,
        "can_save": local_supported,
        "can_clear": local_supported and local_configured,
        "platform": sys.platform,
        "detail": detail if not local_error else f"{detail} {local_error}",
    }


def _clean_notification_token(value: object) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("Enter a Telegram bot token before saving.")
    if len(token) > 512:
        raise ValueError("Telegram bot token is too long.")
    if any(ord(char) < 32 for char in token) or any(char.isspace() for char in token):
        raise ValueError("Telegram bot token cannot contain spaces or control characters.")
    if not re.fullmatch(r"\d{5,16}:[A-Za-z0-9_-]{24,128}", token):
        raise ValueError("Telegram bot token should look like 123456:ABC_def from BotFather.")
    return token


def update_desk_notification_token(body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported notification token field: {', '.join(unexpected)}")
    if not local_credentials.is_supported():
        raise ValueError("[⚠️ 需确认] Saving bot tokens in Signal Desk currently requires Windows Credential Manager.")
    clear = body.get("clear")
    raw_token = body.get("token")
    if clear is not None and not isinstance(clear, bool):
        raise ValueError("Notification token clear value must be true or false.")
    if clear and raw_token:
        raise ValueError("Save or clear the notification token, not both.")
    if clear:
        local_credentials.delete_secret(delivery.TELEGRAM_BOT_TOKEN_CREDENTIAL_TARGET)
    else:
        token = _clean_notification_token(raw_token)
        local_credentials.write_secret(
            delivery.TELEGRAM_BOT_TOKEN_CREDENTIAL_TARGET,
            token,
            username="Telegram bot token",
        )
    return desk_notification_token_status()


def _reject_unexpected_source_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_IMPORT_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source import field: {', '.join(unexpected)}")


def _clean_source_topic(value: object) -> str:
    topic = str(value or "jobs").strip().casefold()
    if not topic:
        topic = "jobs"
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", topic):
        raise ValueError("Source topic must use letters, numbers, hyphen, or underscore.")
    return topic


def _source_import_payload(result: dict, *, topic: str, written: bool) -> dict:
    def source_label(source: dict) -> str:
        return str(source.get("username") or source.get("channel_id") or source.get("label") or "").strip()

    raw_preview_sources = [
        source
        for collection in (result.get("sources"), result.get("updated_sources"), result.get("unchanged_sources"))
        for source in (collection or [])
        if isinstance(source, dict)
    ]
    preview_sources = [
        {"label": source_label(source), "source_id": str(source.get("source_id") or "")}
        for source in raw_preview_sources[:12]
    ]
    preview_truncated_count = max(0, len(raw_preview_sources) - len(preview_sources))
    return {
        "schema_version": "desk_source_import_result_v1",
        "dry_run": bool(result.get("dry_run")),
        "written": written,
        "topic": topic,
        "added_count": int(result.get("added_count") or 0),
        "updated_count": int(result.get("updated_count") or 0),
        "unchanged_count": int(result.get("unchanged_count") or 0),
        "source_count": int(result.get("source_count") or 0),
        "registry_path": dashboard_relative_path(Path(str(result.get("registry_path") or ".tgcs/sources.json"))),
        "preview_sources": preview_sources,
        "preview_truncated_count": preview_truncated_count,
        "title": "Sources ready" if written else "Source preview ready",
        "detail": (
            "Sources were saved to the local registry."
            if written
            else "Review the preview, then import when it looks right."
        ),
        "next_action": "Run source checks, then run a scan from Start.",
        "finished_at": _utc_now(),
    }


def _desk_source_record(source: dict) -> dict:
    channel = source_registry.channel_value(source)
    label = str(source.get("label") or channel or source.get("source_id") or "").strip()
    return {
        "schema_version": "desk_source_v1",
        "source_id": str(source.get("source_id") or ""),
        "label": label,
        "channel": channel,
        "enabled": bool(source.get("enabled", True)),
        "topics": source_registry.normalize_topics(source.get("topics") or []),
        "priority": str(source.get("priority") or "normal"),
        "scan_window_hours": int(source.get("scan_window_hours") or source_registry.DEFAULT_SCAN_WINDOW_HOURS),
    }


def desk_sources() -> dict:
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    result = source_registry.registry_sources(registry_path)
    return {
        "schema_version": "desk_sources_v1",
        "source_count": int(result.get("source_count") or 0),
        "enabled_count": int(result.get("enabled_count") or 0),
        "topics": [str(topic) for topic in result.get("topics") or []],
        "registry_path": dashboard_relative_path(Path(str(result.get("registry_path") or registry_path))),
        "sources": [_desk_source_record(source) for source in (result.get("sources") or []) if isinstance(source, dict)],
    }


def _validate_desk_source_id(source_id: str) -> str:
    clean = str(source_id or "").strip()
    if not re.fullmatch(r"telegram:(?:[A-Za-z0-9_]{5,64}|-?[0-9]{5,20})", clean):
        raise ValueError("Source id is not supported by Signal Desk.")
    return clean


def set_desk_source_enabled(source_id: str, body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_UPDATE_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source setting field: {', '.join(unexpected)}")
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("Source enabled value must be true or false.")
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    source_registry.update_source_enabled(
        registry_path,
        source_id=_validate_desk_source_id(source_id),
        enabled=enabled,
    )
    return desk_sources()


def _clean_source_topics(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Source topics must be a list.")
    if len(value) > 8:
        raise ValueError("Use fewer topic tags.")
    topics: list[str] = []
    seen: set[str] = set()
    for raw_topic in value:
        if not isinstance(raw_topic, str):
            raise ValueError("Source topic tags must be text.")
        topic = raw_topic.strip().casefold()
        if not topic:
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", topic):
            raise ValueError("Source topic must use letters, numbers, hyphen, or underscore.")
        if topic in seen:
            continue
        seen.add(topic)
        topics.append(topic)
    if not topics:
        raise ValueError("Add at least one source topic.")
    return topics


def set_desk_source_topics(source_id: str, body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_TOPIC_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source topic field: {', '.join(unexpected)}")
    topics = _clean_source_topics(body.get("topics"))
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    source_registry.update_source_topics(
        registry_path,
        source_id=_validate_desk_source_id(source_id),
        topics=topics,
    )
    return desk_sources()


def _desk_sources_from_body(body: dict) -> tuple[list[str], str]:
    _reject_unexpected_source_fields(body)
    text = str(body.get("sources") or "")
    if len(text) > DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH:
        raise ValueError("Paste fewer sources at a time.")
    channels = source_registry.load_channel_text(text)
    if not channels:
        raise ValueError("Paste at least one Telegram channel handle or t.me link.")
    if len(channels) > DESK_SOURCE_IMPORT_MAX_CHANNELS:
        raise ValueError("Paste fewer sources at a time.")
    invalid_channels = [
        channel
        for channel in channels
        if not re.fullmatch(r"(?:[A-Za-z0-9_]{5,64}|-?[0-9]{5,20})", channel)
    ]
    if invalid_channels:
        raise ValueError("Source import only accepts Telegram channel handles or numeric chat IDs.")
    topic = _clean_source_topic(body.get("topic"))
    return channels, topic


def preview_desk_source_import(body: dict) -> dict:
    channels, topic = _desk_sources_from_body(body)
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=True,
        topics=[topic],
        input_path="pasted sources",
    )
    return _source_import_payload(result, topic=topic, written=False)


def import_desk_sources(body: dict) -> dict:
    channels, topic = _desk_sources_from_body(body)
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=False,
        topics=[topic],
        input_path="pasted sources",
    )
    return _source_import_payload(result, topic=topic, written=True)


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
        return normalized
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


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
            "Automatic jobs dry-runs would run every 15 minutes. Live Telegram delivery stays off.",
            "",
            action["next_action"],
        )
    if isinstance(next_step, str) and next_step.strip():
        detail = next_step.strip()
    elif isinstance(status, str) and status.strip():
        detail = f"{action['title']} finished with status: {status.strip()}."
    elif stdout.strip():
        detail = stdout.strip().splitlines()[0][:500]
    else:
        detail = f"{action['title']} finished."
    return detail, artifact_path, str(next_step or action["next_action"])


def _desk_failure_detail(payload: dict | None, stdout: str, stderr: str) -> tuple[str, str]:
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "Desk action failed.")
        next_step = str(error.get("next_step") or "Inspect the command output and fix the reported issue.")
        return message, next_step
    text = (stderr or stdout or "Desk action failed.").strip()
    return text.splitlines()[0][:500], "Inspect the command output and rerun the action when ready."


def _desk_safe_result_text(*parts: object) -> str:
    text = "\n".join(str(part or "") for part in parts).strip()
    if not text:
        return ""
    replacements = {
        str(PROJECT_ROOT.resolve()): "project folder",
        str(PROJECT_ROOT.resolve()).replace("\\", "/"): "project folder",
        str(Path.home().resolve()): "~",
        str(Path.home().resolve()).replace("\\", "/"): "~",
    }
    sanitized = text
    for needle, replacement in replacements.items():
        if needle:
            sanitized = sanitized.replace(needle, replacement)
    sanitized = re.sub(r"(?i)\b[A-Z]:\\[^\r\n\"<>|]+", "local path", sanitized)
    return sanitized.splitlines()[0][:500]


def _scheduler_result(
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


def _run_scheduler_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    # Task Scheduler should return quickly for query/create/delete. Keep this bounded
    # so a Windows permission dialog or scheduler hang cannot freeze Signal Desk.
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def desk_scheduler_status() -> dict:
    base = {
        "schema_version": "desk_scheduler_status_v1",
        "task_label": "jobs-fast dry-run",
        "interval_minutes": DESK_SCHEDULER_INTERVAL_MINUTES,
        "checked_at": _utc_now(),
    }
    if not sys.platform.startswith("win"):
        return {
            **base,
            "available": False,
            "installed": False,
            "status": "unavailable",
            "detail": "Automatic dry-run checks can be installed from Signal Desk only on Windows.",
            "next_action": "Use manual scans from Signal Desk on this machine.",
        }

    try:
        completed = _run_scheduler_command(["schtasks.exe", "/Query", "/TN", DESK_SCHEDULER_TASK_NAME])
    except subprocess.TimeoutExpired:
        return {
            **base,
            "available": True,
            "installed": False,
            "status": "unknown",
            "detail": "Signal Desk could not confirm the automatic dry-run status before the check timed out.",
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
            "detail": "Automatic jobs dry-runs are on every 15 minutes.",
            "next_action": "You can turn them off from Signal Desk when you no longer need background checks.",
        }
    return {
        **base,
        "available": True,
        "installed": False,
        "status": "not_installed",
        "detail": "Automatic jobs dry-runs are off.",
        "next_action": "Turn on dry-runs from Signal Desk when you want background checks.",
    }


def run_desk_scheduler_action(action_id: str, *, body: dict | None = None) -> dict:
    if body is None:
        body = {}
    unexpected_keys = set(body) - {"confirm"}
    if unexpected_keys:
        raise DashboardDeskActionError("Scheduler actions only accept an explicit confirmation flag.")
    if body.get("confirm") is not True:
        raise DashboardDeskActionError("Automation changes require explicit confirmation.")
    if not sys.platform.startswith("win"):
        return _scheduler_result(
            action_id,
            status="blocked",
            title="Dry-run automation needs Windows",
            detail="Signal Desk can install this automatic dry-run task only through Windows Task Scheduler.",
            next_action="Use the schedule preview for this machine, or run scans manually from Signal Desk.",
        )

    tgcs_entry = PROJECT_ROOT / "tgcs.bat"
    if not tgcs_entry.exists():
        return _scheduler_result(
            action_id,
            status="blocked",
            title="Launcher file is missing",
            detail="Signal Desk could not find the local TGCS launcher needed by Task Scheduler.",
            next_action="Repair the repo-local install, then turn on dry-run automation again.",
        )

    # Keep this as a single fixed /TR argument in a list argv call. Do not
    # refactor this path through shell=True: the browser must never be able to
    # turn scheduler setup into a local shell proxy.
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
        success_title = "Dry-run automation is on"
        success_detail = "Windows Task Scheduler will run jobs dry-runs every 15 minutes. Live Telegram delivery is still off."
        success_next = "You can leave Signal Desk and return later to review new Inbox cards."
    elif action_id == "schedule_remove_dry_run":
        args = ["schtasks.exe", "/Delete", "/TN", DESK_SCHEDULER_TASK_NAME, "/F"]
        success_title = "Dry-run automation is off"
        success_detail = "Signal Desk removed the Windows Task Scheduler task for jobs dry-runs."
        success_next = "Manual scans still work from Signal Desk."
    else:
        raise DashboardDeskActionError(f"Unknown scheduler action: {action_id}")

    try:
        completed = _run_scheduler_command(args)
    except subprocess.TimeoutExpired:
        return _scheduler_result(
            action_id,
            status="failed",
            title="Scheduler change timed out",
            detail="Windows Task Scheduler did not finish the requested change in time.",
            next_action="Check Windows Task Scheduler, then retry from Signal Desk.",
        )
    except OSError:
        return _scheduler_result(
            action_id,
            status="blocked",
            title="Task Scheduler is unavailable",
            detail="Signal Desk could not start the Windows Task Scheduler command on this machine.",
            next_action="Use manual scans in Signal Desk, or install the task from Windows Task Scheduler.",
        )

    if completed.returncode == 0:
        return _scheduler_result(
            action_id,
            status="success",
            title=success_title,
            detail=success_detail,
            next_action=success_next,
            exit_code=completed.returncode,
        )

    failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "Windows Task Scheduler rejected the change."
    return _scheduler_result(
        action_id,
        status="failed",
        title="Scheduler change failed",
        detail=failure,
        next_action="Check Windows Task Scheduler permissions, then retry from Signal Desk.",
        exit_code=completed.returncode,
    )


def run_desk_action(action_id: str, *, body: dict | None = None) -> dict:
    action = DESK_ACTION_BY_ID.get(action_id)
    if not action:
        raise DashboardDeskActionError(f"Unknown Desk action: {action_id}")

    if action_id in {"schedule_install_dry_run", "schedule_remove_dry_run"}:
        return run_desk_scheduler_action(action_id, body=body)

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
    _ = body
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "tgcs.py"), *action["argv"]]
    try:
        completed = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=int(action.get("timeout", DESK_ACTION_TIMEOUT_SECONDS)),
        )
    except subprocess.TimeoutExpired:
        return {
            "schema_version": "desk_action_result_v1",
            "action_id": action_id,
            "status": "failed",
            "title": action["title"],
            "detail": f"{action['title']} timed out.",
            "display_command": action["display_command"],
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
        "display_command": action["display_command"],
        "exit_code": completed.returncode,
        "artifact_path": artifact_path,
        "next_action": next_action,
        "finished_at": _utc_now(),
    }


def markdown_inline_html(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<em>\1</em>", escaped)

    def link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = html.unescape(match.group(2)).strip()
        if not re.match(r"^https?://", href, flags=re.IGNORECASE):
            return match.group(0)
        return f'<a href="{html.escape(href, quote=True)}" rel="noreferrer" target="_blank">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, escaped)


def markdown_table_html(lines: list[str]) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if not rows:
        return ""
    has_header = len(rows) > 1 and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in rows[1])
    body_rows = rows[2:] if has_header else rows
    parts = ["<div class=\"table-wrap\"><table>"]
    if has_header:
        parts.append("<thead><tr>")
        parts.extend(f"<th>{markdown_inline_html(cell)}</th>" for cell in rows[0])
        parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in body_rows:
        parts.append("<tr>")
        parts.extend(f"<td>{markdown_inline_html(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def markdown_blocks_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    index = 0
    in_list = False
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            if in_list:
                parts.append("</ul>")
                in_list = False
            index += 1
            continue
        if stripped.startswith("```"):
            if in_list:
                parts.append("</ul>")
                in_list = False
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue
        if stripped.startswith("|"):
            if in_list:
                parts.append("</ul>")
                in_list = False
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            parts.append(markdown_table_html(table_lines))
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            if in_list:
                parts.append("</ul>")
                in_list = False
            level = len(heading.group(1))
            parts.append(f"<h{level}>{markdown_inline_html(heading.group(2))}</h{level}>")
            index += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{markdown_inline_html(bullet.group(1))}</li>")
            index += 1
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        paragraph = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if (
                not next_line
                or next_line.startswith("```")
                or next_line.startswith("|")
                or re.match(r"^(#{1,6})\s+", next_line)
                or re.match(r"^[-*]\s+", next_line)
            ):
                break
            paragraph.append(next_line)
            index += 1
        parts.append(f"<p>{markdown_inline_html(' '.join(paragraph))}</p>")
    if in_list:
        parts.append("</ul>")
    return "\n".join(part for part in parts if part)


def render_markdown_artifact(path: Path) -> bytes:
    markdown = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem.replace("-", " ").title()
    body = markdown_blocks_html(markdown)
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink: #1f2a24; --muted: #5f6d61; --paper: #fff7e8; --line: #d7c7a6; --teal: #1d8f7b; }}
    body {{ margin: 0; background: #f4ecd9; color: var(--ink); font: 16px/1.62 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ width: min(920px, calc(100% - 28px)); margin: 0 auto; padding: 28px 0 56px; }}
    article {{ background: var(--paper); border: 1px solid var(--line); padding: clamp(18px, 4vw, 38px); box-shadow: 8px 8px 0 rgba(31, 42, 36, 0.12); }}
    h1, h2, h3 {{ line-height: 1.16; margin: 1.45em 0 0.55em; }}
    h1 {{ margin-top: 0; font-size: clamp(2rem, 8vw, 3.4rem); letter-spacing: 0; }}
    h2 {{ border-top: 1px solid var(--line); padding-top: 1.1em; font-size: clamp(1.4rem, 5vw, 2rem); }}
    h3 {{ font-size: 1.15rem; }}
    p, ul, pre, .table-wrap {{ margin: 0 0 1.1rem; }}
    ul {{ padding-left: 1.25rem; }}
    a {{ color: var(--teal); font-weight: 700; }}
    code {{ background: rgba(29, 143, 123, 0.1); padding: 0.1em 0.28em; border-radius: 4px; }}
    pre {{ overflow-x: auto; background: #14251d; color: #d9f5e9; padding: 14px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); }}
    table {{ width: 100%; border-collapse: collapse; min-width: 520px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; }}
    th {{ background: rgba(29, 143, 123, 0.12); font-size: 0.78rem; text-transform: uppercase; }}
    @media (max-width: 560px) {{ main {{ width: calc(100% - 18px); padding-top: 9px; }} article {{ padding: 16px; box-shadow: none; }} body {{ font-size: 15px; }} }}
  </style>
</head>
<body>
  <main><article>{body}</article></main>
</body>
</html>
"""
    return document.encode("utf-8")


def render_html_report_artifact(path: Path) -> bytes:
    document = path.read_text(encoding="utf-8")
    if "data-dashboard-report-mobile-patch" not in document and "</head>" in document:
        document = document.replace("</head>", f"{REPORT_HTML_MOBILE_PATCH}\n</head>", 1)
    return document.encode("utf-8")


def resolve_static_path(request_path: str, *, static_dir: Path) -> Path:
    relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
    candidate = (static_dir / relative).resolve()
    static_root = static_dir.resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return static_root / "index.html"
    if not candidate.exists() or candidate.is_dir():
        return static_root / "index.html"
    return candidate


class DashboardHandler(BaseHTTPRequestHandler):
    db_path: Path
    static_dir: Path

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[dashboard] {self.address_string()} - {format % args}", file=sys.stderr)

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _connect(self):
        return monitor_state.connect(self.db_path)

    def _require_loopback_access(self, feature: str) -> None:
        client_host = getattr(self, "client_address", ("127.0.0.1", 0))[0]
        if is_loopback_address(client_host):
            return
        raise ValueError(f"{feature} requires opening Signal Desk from localhost.")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/desk/health":
                DashboardHandler._require_loopback_access(self, "Signal Desk health")
                server_host, server_port = self.server.server_address[:2]
                self._json(HTTPStatus.OK, desk_health(host=str(server_host), port=int(server_port)))
                return
            if parsed.path == "/api/desk/actions":
                self._json(HTTPStatus.OK, desk_actions())
                return
            if parsed.path == "/api/desk/telegram-status":
                DashboardHandler._require_loopback_access(self, "Telegram setup")
                self._json(HTTPStatus.OK, {"ok": True, "telegram": telegram_status()})
                return
            if parsed.path == "/api/desk/sources":
                DashboardHandler._require_loopback_access(self, "Source library")
                self._json(HTTPStatus.OK, {"ok": True, "sources": desk_sources()})
                return
            if parsed.path == "/api/desk/scheduler-status":
                DashboardHandler._require_loopback_access(self, "Scheduler status")
                self._json(HTTPStatus.OK, {"ok": True, "scheduler": desk_scheduler_status()})
                return
            if parsed.path == "/api/desk/notification-token/status":
                DashboardHandler._require_loopback_access(self, "Notification token status")
                self._json(HTTPStatus.OK, {"ok": True, "token": desk_notification_token_status()})
                return
            if parsed.path == "/api/state":
                with close_after_use(self._connect()) as conn:
                    self._json(HTTPStatus.OK, monitor_state.dashboard_snapshot(conn))
                return
            if parsed.path.startswith("/artifacts/"):
                self._serve_artifact(parsed.path.removeprefix("/artifacts/"))
                return
            self._serve_static(parsed.path)
        except (ValueError, json.JSONDecodeError, monitor_state.MonitorStateError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:
            print(f"[dashboard] internal GET error: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "Signal Desk hit an internal error. Check the launcher window for details."},
            )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
            if parsed.path.startswith("/api/desk/actions/") and parsed.path.endswith("/run"):
                DashboardHandler._require_loopback_access(self, "Desk actions")
                action_id = unquote(parsed.path.removeprefix("/api/desk/actions/").removesuffix("/run").strip("/"))
                self._json(HTTPStatus.OK, {"ok": True, "result": run_desk_action(action_id, body=body)})
                return
            if parsed.path == "/api/desk/telegram-credentials":
                DashboardHandler._require_loopback_access(self, "Telegram setup")
                result = save_telegram_credentials(body.get("api_id"), body.get("api_hash"))
                self._json(HTTPStatus.OK, {"ok": True, "telegram": result})
                return
            if parsed.path == "/api/desk/telegram-login/send-code":
                DashboardHandler._require_loopback_access(self, "Telegram setup")
                result = telegram_send_code(body.get("phone"))
                self._json(HTTPStatus.OK, {"ok": True, "telegram": result})
                return
            if parsed.path == "/api/desk/telegram-login/verify-code":
                DashboardHandler._require_loopback_access(self, "Telegram setup")
                result = telegram_verify_code(body.get("code"), body.get("password") or "")
                self._json(HTTPStatus.OK, {"ok": True, "telegram": result})
                return
            if parsed.path == "/api/desk/telegram-login/cancel":
                DashboardHandler._require_loopback_access(self, "Telegram setup")
                self._json(HTTPStatus.OK, {"ok": True, "telegram": telegram_cancel_login()})
                return
            if parsed.path == "/api/desk/notification-token":
                DashboardHandler._require_loopback_access(self, "Notification token settings")
                self._json(HTTPStatus.OK, {"ok": True, "token": update_desk_notification_token(body)})
                return
            if parsed.path.startswith("/api/desk/delivery-targets/"):
                DashboardHandler._require_loopback_access(self, "Notification settings")
                parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
                if len(parts) == 4:
                    with close_after_use(self._connect()) as conn:
                        target = save_desk_delivery_target(conn, parts[3], body)
                    self._json(HTTPStatus.OK, {"ok": True, "target": target})
                    return
                if len(parts) == 5 and parts[4] == "test":
                    with close_after_use(self._connect()) as conn:
                        result = test_desk_delivery_target(conn, parts[3], body)
                    self._json(HTTPStatus.OK, {"ok": True, "result": result})
                    return
                raise ValueError("Unsupported notification settings path.")
            if parsed.path == "/api/desk/sources/preview":
                DashboardHandler._require_loopback_access(self, "Source import")
                self._json(HTTPStatus.OK, {"ok": True, "result": preview_desk_source_import(body)})
                return
            if parsed.path == "/api/desk/sources/import":
                DashboardHandler._require_loopback_access(self, "Source import")
                self._json(HTTPStatus.OK, {"ok": True, "result": import_desk_sources(body)})
                return
            if parsed.path.startswith("/api/desk/sources/") and parsed.path.endswith("/enabled"):
                DashboardHandler._require_loopback_access(self, "Source library")
                source_id = unquote(parsed.path.removeprefix("/api/desk/sources/").removesuffix("/enabled").strip("/"))
                self._json(HTTPStatus.OK, {"ok": True, "sources": set_desk_source_enabled(source_id, body)})
                return
            if parsed.path.startswith("/api/desk/sources/") and parsed.path.endswith("/topics"):
                DashboardHandler._require_loopback_access(self, "Source library")
                source_id = unquote(parsed.path.removeprefix("/api/desk/sources/").removesuffix("/topics").strip("/"))
                self._json(HTTPStatus.OK, {"ok": True, "sources": set_desk_source_topics(source_id, body)})
                return
            if parsed.path == "/api/git/check-updates":
                self._json(HTTPStatus.OK, {"ok": True, "git": _git_update_status(fetch=True)})
                return
            if parsed.path == "/api/git/pull-latest":
                if body.get("confirm") is not True:
                    raise DashboardGitError("Pull latest requires explicit confirmation.")
                self._json(HTTPStatus.OK, {"ok": True, "git": _git_pull_latest()})
                return
            if parsed.path == "/api/feedback/export":
                with close_after_use(self._connect()) as conn:
                    result = write_feedback_export(conn)
                self._json(HTTPStatus.OK, {"ok": True, "export": result})
                return
            if parsed.path.startswith("/api/review-cards/") and parsed.path.endswith("/action"):
                card_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    card = monitor_state.set_card_action(
                        conn,
                        card_id=card_id,
                        action=str(body.get("action") or ""),
                        note=str(body.get("note") or ""),
                    )
                self._json(HTTPStatus.OK, {"ok": True, "card": card})
                return
            if parsed.path.startswith("/api/profiles/") and parsed.path.endswith("/alert-mode"):
                DashboardHandler._require_loopback_access(self, "Profile settings")
                profile_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    profile = monitor_state.update_profile_alert_mode(
                        conn,
                        profile_id=profile_id,
                        mode=str(body.get("mode") or ""),
                    )
                self._json(HTTPStatus.OK, {"ok": True, "profile": profile})
                return
            if parsed.path.startswith("/api/profiles/") and parsed.path.endswith("/enabled"):
                DashboardHandler._require_loopback_access(self, "Profile settings")
                unexpected = sorted(str(key) for key in body.keys() if key not in PROFILE_ENABLED_ALLOWED_FIELDS)
                if unexpected:
                    raise ValueError(f"Unsupported profile setting field: {', '.join(unexpected)}")
                enabled = body.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("Profile enabled value must be true or false.")
                profile_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    profile = monitor_state.update_profile_enabled(conn, profile_id=profile_id, enabled=enabled)
                self._json(HTTPStatus.OK, {"ok": True, "profile": profile})
                return
            if parsed.path.startswith("/api/profiles/") and parsed.path.endswith("/runtime-settings"):
                DashboardHandler._require_loopback_access(self, "Profile settings")
                unexpected = sorted(str(key) for key in body.keys() if key not in PROFILE_RUNTIME_SETTINGS_ALLOWED_FIELDS)
                if unexpected:
                    raise ValueError(f"Unsupported profile setting field: {', '.join(unexpected)}")
                profile_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    profile = monitor_state.update_profile_runtime_settings(
                        conn,
                        profile_id=profile_id,
                        settings=body,
                    )
                self._json(HTTPStatus.OK, {"ok": True, "profile": profile})
                return
            if parsed.path.startswith("/api/profile-patches/") and parsed.path.endswith("/apply"):
                patch_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    result = monitor_state.apply_profile_patch(conn, patch_id=patch_id)
                self._json(HTTPStatus.OK, {"ok": True, "result": result})
                return
            if parsed.path.startswith("/api/profile-patches/") and parsed.path.endswith("/revert"):
                patch_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    result = monitor_state.revert_profile_patch(conn, patch_id=patch_id)
                self._json(HTTPStatus.OK, {"ok": True, "result": result})
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except (
            ValueError,
            json.JSONDecodeError,
            DashboardGitError,
            DashboardDeskActionError,
            monitor_state.MonitorStateError,
        ) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:
            print(f"[dashboard] internal POST error: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "Signal Desk hit an internal error. Check the launcher window for details."},
            )

    def _serve_static(self, request_path: str) -> None:
        if not self.static_dir.exists():
            self._json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": "dashboard_not_built",
                    "next_step": "Run npm install and npm run build in dashboard/.",
                },
            )
            return
        candidate = resolve_static_path(request_path, static_dir=self.static_dir)
        if not candidate.exists():
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "static_file_not_found"})
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_artifact(self, encoded_path: str) -> None:
        try:
            candidate = resolve_run_artifact_path(encoded_path)
        except DashboardArtifactError as exc:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})
            return
        if candidate.suffix.lower() == ".md":
            body = render_markdown_artifact(candidate)
            content_type = "text/html; charset=utf-8"
        elif candidate.suffix.lower() == ".html":
            body = render_html_report_artifact(candidate)
            content_type = "text/html; charset=utf-8"
        else:
            body = candidate.read_bytes()
            content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the local TGCS dashboard.", allow_abbrev=False)
    parser.add_argument("--db", default=".tgcs/tgcs.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--auto-port",
        action="store_true",
        help="Use an existing compatible Signal Desk or try the next free port through 8799.",
    )
    parser.add_argument("--static-dir", default="dashboard/dist")
    parser.add_argument("--open", dest="open_browser", action="store_true", help="Open Signal Desk in the default browser.")
    agent_cli.add_format_argument(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    static_dir = Path(args.static_dir)
    if not static_dir.is_absolute():
        static_dir = PROJECT_ROOT / static_dir
    DashboardHandler.db_path = db_path
    DashboardHandler.static_dir = static_dir
    try:
        selection = select_dashboard_server(host=args.host, port=args.port, auto_port=args.auto_port)
    except OSError as exc:
        message = f"Signal Desk could not use port {args.port}: {exc}"
        agent_cli.emit_error(
            args,
            code="dashboard_port_unavailable",
            message=message,
            retryable=True,
            next_step=(
                f"Close the other service on port {args.port}, pass --port with a free port, "
                "or omit --port so Signal Desk can auto-select one."
            ),
        )
        return agent_cli.EXIT_RUNTIME
    url = selection.url
    warning = dashboard_host_warning(str(args.host))
    if agent_cli.is_json_format(args):
        payload = {
            "url": url,
            "db_path": str(db_path),
            "port": selection.port,
            "reused_existing": selection.reused_existing,
        }
        if warning:
            payload["warning"] = warning
        agent_cli.print_json(
            agent_cli.envelope_success(payload)
        )
    else:
        if warning:
            print(f"Warning: {warning}", file=sys.stderr)
        if selection.reused_existing:
            print(f"Signal Desk is already running on {url}")
        else:
            print(f"TGCS dashboard listening on {url}")
        if args.open_browser:
            if webbrowser.open(url, new=2):
                print("Opened Signal Desk in your browser.")
            else:
                print(f"Open Signal Desk manually: {url}", file=sys.stderr)
    if selection.reused_existing:
        return agent_cli.EXIT_SUCCESS
    server = selection.server
    if server is None:
        raise AssertionError("Signal Desk server selection did not include a server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return agent_cli.EXIT_SUCCESS
    finally:
        server.server_close()
    return agent_cli.EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
