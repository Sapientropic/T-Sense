"""Localhost dashboard server for the v0.5-alpha review inbox."""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import io
import ipaddress
import json
import mimetypes
import os
import plistlib
import re
import shutil
import subprocess
import socket
import sys
import tomllib
import webbrowser
from collections import Counter
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
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import urlopen

def _positive_int_env(name: str, fallback: int) -> int:
    try:
        parsed = int(os.environ.get(name, ""))
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


try:
    from scripts import agent_cli, delivery, local_credentials, monitor_state, report, source_registry
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import agent_cli, delivery, local_credentials, monitor_state, report, source_registry


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESK_HEALTH_SCHEMA_VERSION = "desk_health_v1"
DESK_APP_ID = "tgcs-signal-desk"
DESK_VERSION = "0.5.0-alpha.1"
DESK_AUTO_PORT_END = 8799
GIT_TIMEOUT_SECONDS = 25
DESK_ACTION_TIMEOUT_SECONDS = 180
DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION = "desk_source_access_health_v1"
DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES = _positive_int_env("TGCS_SOURCE_ACCESS_PROBE_MAX_SOURCES", 80)
DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS = 24
DESK_BOT_GATEWAY_STATE_FILENAME = "bot-gateway-state.json"
DESK_BOT_GATEWAY_STALE_SECONDS = 120
DESK_BOT_SUPPORTED_COMMANDS = ["/status", "/latest", "/sources", "/profiles", "/scan"]
LOOPBACK_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
SECRET_TOKEN_RE = re.compile(r"\b\d{5,12}:[A-Za-z0-9_-]{10,}\b")
PROVIDER_KEY_RE = re.compile(r"\b(?:sk|sk-proj|sk-ant|ak)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE)
BEARER_SECRET_RE = re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]{8,}")
ENV_SECRET_RE = re.compile(r"(?i)\b[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)\b\s*=\s*[^\s`'\"]+")
KEY_VALUE_SECRET_RE = re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*[^\s`'\"]+")
ARGV_DUMP_RE = re.compile(r"(?i)\bargv\s*[:=]\s*(?:\[[^\]]*\]|[^\r\n]+)")
CHAT_ID_FIELD_RE = re.compile(r"\bchat[_ -]?id\b\s*[:=]?\s*-?\d{5,20}\b", re.IGNORECASE)
TELEGRAM_CONFIG_DIR = Path(
    os.environ.get("TG_SCANNER_CONFIG_DIR")
    or os.environ.get("TGCLI_CONFIG_DIR")
    or os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".config", "tgcli")
)
TELEGRAM_CONFIG_PATH = TELEGRAM_CONFIG_DIR / "config.toml"
TELEGRAM_SESSION_PATH = TELEGRAM_CONFIG_DIR / "session"
TELEGRAM_LOGIN_CODE_TTL_SECONDS = 300
TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS = 8
DESK_DELIVERY_TARGET_ID = "telegram-bot-default"
DESK_DELIVERY_ALLOWED_FIELDS = {"chat_id", "enabled"}
DESK_DELIVERY_TEST_ALLOWED_FIELDS = {"chat_id"}
DESK_DELIVERY_DETECT_ALLOWED_FIELDS: set[str] = set()
DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS = {"token", "clear"}
DESK_AI_SETTINGS_ALLOWED_FIELDS = {"provider", "api_key", "clear"}
DESK_SOURCE_IMPORT_ALLOWED_FIELDS = {"sources", "topic"}
DESK_SOURCE_STARTER_ALLOWED_FIELDS = {"topic"}
DESK_SOURCE_ASSISTANT_ALLOWED_FIELDS = {"instruction", "topic", "dry_run", "confirm_external_ai", "resolved_plan"}
DESK_SOURCE_UPDATE_ALLOWED_FIELDS = {"enabled"}
DESK_SOURCE_TOPIC_ALLOWED_FIELDS = {"topics"}
PROFILE_ENABLED_ALLOWED_FIELDS = {"enabled"}
PROFILE_RUNTIME_SETTINGS_ALLOWED_FIELDS = set(monitor_state.PROFILE_RUNTIME_SETTING_LIMITS)
PROFILE_DRAFT_NOTE_ALLOWED_FIELDS = {"note"}
PROFILE_DRAFT_NOTE_MAX_LENGTH = 2000
PROFILE_MATCHING_PREFERENCES_ALLOWED_FIELDS = {"preferences"}
PROFILE_MATCHING_PREFERENCES_MAX_LENGTH = 4000
PROFILE_CREATE_ALLOWED_FIELDS = {"brief", "source_filename", "source_text", "source_base64"}
PROFILE_CREATE_MAX_TEXT_LENGTH = 30000
PROFILE_CREATE_MAX_BINARY_BYTES = 4 * 1024 * 1024
DESK_SOURCE_IMPORT_MAX_TEXT_LENGTH = 20000
DESK_SOURCE_IMPORT_MAX_CHANNELS = 500
DESK_SCHEDULER_PROFILE_ID = "jobs-fast"
DESK_SCHEDULER_INTERVAL_MINUTES = 15
DESK_SCHEDULER_TASK_NAME = "TGCS jobs-fast dry-run"
DESK_SCHEDULER_LAUNCHD_LABEL = "com.sapientropic.tgcs.jobs-fast.dry-run"
DESK_SCHEDULER_SYSTEMD_NAME = "tgcs-jobs-fast-dry-run"
DESK_BOT_GATEWAY_TASK_NAME = "T-Sense Bot Gateway"
DESK_BOT_GATEWAY_LAUNCHD_LABEL = "com.sapientropic.tsense.bot-gateway"
DESK_BOT_GATEWAY_SYSTEMD_NAME = "tsense-bot-gateway"
DESK_BOT_GATEWAY_POLL_TIMEOUT_SECONDS = 8
DESK_AI_PROVIDER_CONFIGS: dict[str, dict[str, str]] = {
    "openai": {
        "label": "OpenAI",
        "env_name": "OPENAI_API_KEY",
        "target": "tgcs.signal-desk.openai-api-key",
        "username": "OpenAI API key",
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_name": "DEEPSEEK_API_KEY",
        "target": "tgcs.signal-desk.deepseek-api-key",
        "username": "DeepSeek API key",
    },
    "minimax": {
        "label": "MiniMax",
        "env_name": "MINIMAX_TOKEN_PLAN_KEY",
        "target": "tgcs.signal-desk.minimax-token-plan-key",
        "username": "MiniMax token plan key",
    },
    "xai": {
        "label": "xAI OCR",
        "env_name": "XAI_API_KEY",
        "target": "tgcs.signal-desk.xai-api-key",
        "username": "xAI API key",
    },
}
_DESK_TELEGRAM_LOGIN: dict[str, str] = {}
_DESK_TELEGRAM_LOGIN_LOCK = Lock()
_DESK_ACTION_LOCKS: dict[str, Lock] = {}
_DESK_ACTION_LOCKS_GUARD = Lock()
_DESK_LONG_RUNNING_ACTIONS = {"monitor_jobs_dry_run", "sources_probe_access"}
_DESK_ACTIVE_ACTIONS: dict[str, dict] = {}
_DESK_ACTIVE_ACTIONS_GUARD = Lock()
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


class SourceAccessProbeError(Exception):
    """Raised when a source access probe cannot start safely."""

    def __init__(self, message: str, *, next_action: str, status: str = "blocked") -> None:
        super().__init__(message)
        self.next_action = next_action
        self.status = status


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
        "next_action": "Fix anything marked blocked, then run a practice scan.",
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
        "next_action": "Pause inaccessible sources or run a practice scan after access looks healthy.",
    },
    {
        "action_id": "sources_pause_inaccessible",
        "group": "Sources",
        "title": "Pause inaccessible sources",
        "detail": "Disable sources from the latest access check that Telegram could not resolve or read.",
        "run_mode": "confirm_execute",
        "display_command": "Signal Desk: pause inaccessible sources",
        "next_action": "Run a fresh practice scan after pausing inaccessible sources.",
    },
    {
        "action_id": "sources_keep_accessible",
        "group": "Sources",
        "title": "Keep only recently active sources",
        "detail": "Disable inaccessible and quiet sources from the latest access check. Quiet sources are readable, but had no recent messages in the probe window.",
        "run_mode": "confirm_execute",
        "display_command": "Signal Desk: keep recently active sources",
        "next_action": "Run a fresh practice scan after narrowing the source list.",
    },
    {
        "action_id": "sources_import_jobs",
        "group": "Sources",
        "title": "Repair starter sources",
        "detail": "Restore or refresh the starter Telegram channels for the jobs monitor.",
        "run_mode": "execute",
        "display_command": "tgcs sources import channel_lists/jobs.txt --topic jobs",
        "argv": ["sources", "import", "channel_lists/jobs.txt", "--topic", "jobs", "--format", "json"],
        "next_action": "Check setup again, then run a practice scan.",
    },
    {
        "action_id": "monitor_jobs_dry_run",
        "group": "Run",
        "title": "Run fresh practice scan",
        "detail": "Fetch latest source messages and create local Review cards without sending Telegram alerts.",
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
        "next_action": "Review the new cards or open the generated report.",
    },
    {
        "action_id": "feedback_export",
        "group": "Feedback",
        "title": "Export feedback JSONL",
        "detail": "Troubleshooting fallback for agents or CLI imports; Desk can generate profile drafts directly.",
        "run_mode": "execute",
        "display_command": "tgcs feedback export",
        "argv": ["feedback", "export", "--format", "json"],
        "artifact_keys": ["output_path"],
        "next_action": "Use Desk Learning to generate profile drafts, or import JSONL through the CLI.",
    },
    {
        "action_id": "schedule_preview",
        "group": "Schedule",
        "title": "Preview auto scan",
        "detail": "Preview the automatic practice-scan cadence before turning it on.",
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
        "next_action": "Turn on automatic practice scans from Signal Desk when ready.",
    },
    {
        "action_id": "schedule_install_dry_run",
        "group": "Schedule",
        "title": "Turn on auto scan",
        "detail": "Create a Windows Task Scheduler task for local practice scans. It sends no live alerts.",
        "run_mode": "confirm_execute",
        "display_command": "Windows Task Scheduler: jobs-fast dry-run",
        "next_action": "Signal Desk will run local practice scans automatically every 15 minutes.",
    },
    {
        "action_id": "schedule_remove_dry_run",
        "group": "Schedule",
        "title": "Turn off auto scan",
        "detail": "Remove the automatic practice scan task created by Signal Desk.",
        "run_mode": "confirm_execute",
        "display_command": "Windows Task Scheduler: remove jobs-fast dry-run",
        "next_action": "Automatic practice scans are removed. Manual scans still work in Signal Desk.",
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


def is_dashboard_report_artifact_name(name: str) -> bool:
    lower = name.lower()
    if lower in {"report.html", "report.md"}:
        return True
    path = PurePosixPath(lower)
    if path.suffix not in {".html", ".md"}:
        return False
    return any(token in path.stem.split("-") for token in {"report", "brief"})


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
            "desk_ai_settings_v1",
            "desk_sources_v1",
            "desk_source_assistant_v1",
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
    health_url = str(payload.get("url") or "").strip()
    if health_url:
        parsed = urlparse(health_url)
        if parsed.scheme != "http" or not parsed.hostname or not is_loopback_address(parsed.hostname) or parsed.port != port:
            return None
    return payload


def is_tcp_port_listening(host: str, port: int, *, timeout_seconds: float = 0.15) -> bool:
    try:
        with socket.create_connection((_browser_host(host), port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


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
                    url=dashboard_url(host, candidate),
                    port=candidate,
                    server=None,
                    reused_existing=True,
                )
            if is_tcp_port_listening(host, candidate):
                # Windows can allow a second bind when an older local tool did
                # not claim the port exclusively. Skip that URL so the browser
                # cannot land on an unrelated directory listing or test server.
                last_error = OSError(f"Port {candidate} is already used by another local service.")
                continue
        elif is_tcp_port_listening(host, candidate):
            raise OSError(f"Port {candidate} is already used by another local service.")
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
    remote_url = remote_url.strip()
    if remote_url.startswith("git@github.com:"):
        remote_url = "https://github.com/" + remote_url.removeprefix("git@github.com:")
    parsed = urlparse(remote_url)
    if parsed.hostname and parsed.scheme in {"http", "https", "ssh"}:
        path = parsed.path or ""
        if path.endswith(".git"):
            path = path[:-4]
        scheme = "https" if parsed.scheme == "ssh" else parsed.scheme
        return f"{scheme}://{parsed.hostname}{path}"
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    return remote_url if "@" not in remote_url and ":" not in remote_url else None


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
            fetch_error = _desk_safe_result_text(completed.stderr, completed.stdout) or "git fetch failed"

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


def is_dashboard_openable_artifact_path(path: str) -> bool:
    cleaned = str(path or "").strip().replace("\\", "/")
    if (
        not cleaned
        or cleaned.startswith("/")
        or re.match(r"^[A-Za-z]:", cleaned)
        or re.match(r"^[a-z][a-z0-9+.-]*://", cleaned, flags=re.IGNORECASE)
        or re.search(r"[\x00-\x1f\x7f]", cleaned)
    ):
        return False
    parts = PurePosixPath(cleaned).parts
    if not parts or ".." in parts or not is_dashboard_report_artifact_name(parts[-1]):
        return False
    if "runs" in parts:
        run_index = parts.index("runs")
        return run_index < len(parts) - 2
    return parts[0] == "output" and len(parts) >= 2


def resolve_dashboard_artifact_path(requested_path: str, *, artifact_root: Path | None = None) -> Path:
    decoded = unquote(requested_path).replace("\\", "/").lstrip("/")
    parts = PurePosixPath(decoded).parts
    if not is_dashboard_openable_artifact_path(decoded):
        raise DashboardArtifactError("artifact_type_not_report")
    if "runs" in parts:
        return resolve_run_artifact_path(decoded, artifact_root=artifact_root)

    root = (artifact_root or PROJECT_ROOT.joinpath(parts[0])).resolve()
    relative = "/".join(parts[1:])
    if not relative:
        raise DashboardArtifactError("artifact_path_missing")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DashboardArtifactError("artifact_path_outside_output") from exc
    if not candidate.exists() or not candidate.is_file():
        raise DashboardArtifactError("artifact_not_found")
    return candidate


def dashboard_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def dashboard_feedback_export_target(output_path: Path | None = None) -> Path:
    target = output_path or PROJECT_ROOT / "output" / "feedback" / "review-feedback.jsonl"
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    resolved = target.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("feedback_export_path_outside_project") from exc
    return resolved


def write_feedback_export(conn, *, output_path: Path | None = None) -> dict:
    target = dashboard_feedback_export_target(output_path)
    entries = monitor_state.export_feedback_entries(conn)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    target.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    exported_at = monitor_state.utc_now()
    relative_path = dashboard_relative_path(target)
    monitor_state.record_feedback_export(
        conn,
        output_path=relative_path,
        feedback_count=len(entries),
        exported_at=exported_at,
    )
    return {
        "schema_version": "feedback_export_result_v1",
        "feedback_count": len(entries),
        "output_path": relative_path,
        "changed_since_last_export": False,
        "exported_at": exported_at,
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
        "Test passed. Signal Desk can use this chat ID when live notifications are turned on."
        if attempt.get("ok")
        else str(attempt.get("error") or "The test could not validate the notification target.")
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


def _chat_candidate_from_update(update: dict) -> dict[str, str] | None:
    chat: object = None
    for key in ("message", "edited_message", "channel_post", "my_chat_member"):
        event = update.get(key)
        if not isinstance(event, dict):
            continue
        if key == "my_chat_member":
            chat = event.get("chat")
        else:
            chat = event.get("chat")
        if isinstance(chat, dict):
            break
    if not isinstance(chat, dict):
        return None
    raw_chat_id = chat.get("id")
    if raw_chat_id is None:
        return None
    chat_id = _clean_delivery_chat_id(str(raw_chat_id))
    if not chat_id:
        return None
    chat_type = str(chat.get("type") or "chat").strip() or "chat"
    return {
        "chat_id": chat_id,
        "chat_type": chat_type,
    }


def _chat_candidate_from_bot_updates(payload: object) -> dict[str, str] | None:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return None
    updates = payload.get("result")
    if not isinstance(updates, list):
        return None
    fallback: dict[str, str] | None = None
    for update in reversed(updates):
        if not isinstance(update, dict):
            continue
        candidate = _chat_candidate_from_update(update)
        if not candidate:
            continue
        if candidate.get("chat_type") == "private":
            return candidate
        fallback = fallback or candidate
    return fallback


def _detect_chat_id_from_bot_updates() -> dict[str, str] | None:
    token = delivery.resolve_telegram_bot_token()
    if not token.token:
        return None
    query = urlencode({"limit": "20", "timeout": "0"})
    url = f"https://api.telegram.org/bot{quote(token.token, safe=':')}/getUpdates?{query}"
    try:
        with urlopen(url, timeout=TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib_error.URLError, json.JSONDecodeError, ValueError):
        return None
    candidate = _chat_candidate_from_bot_updates(payload)
    if not candidate:
        return None
    return {
        **candidate,
        "source": "telegram_bot_updates",
    }


async def _telegram_current_user_chat_id_async(
    *,
    config_path: Path = TELEGRAM_CONFIG_PATH,
    session_path: Path = TELEGRAM_SESSION_PATH,
) -> str | None:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id, api_hash = _load_telegram_credentials(config_path=config_path)
    session_string = session_path.read_text(encoding="utf-8").strip() if session_path.exists() else ""
    if not session_string:
        return None
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return None
        me = await client.get_me()
        user_id = getattr(me, "id", None)
        return _clean_delivery_chat_id(str(user_id)) if user_id is not None else None
    finally:
        await client.disconnect()


def _telegram_current_user_chat_id(
    *,
    config_path: Path = TELEGRAM_CONFIG_PATH,
    session_path: Path = TELEGRAM_SESSION_PATH,
) -> str | None:
    try:
        return asyncio.run(_telegram_current_user_chat_id_async(config_path=config_path, session_path=session_path))
    except Exception:
        return None


def detect_desk_delivery_chat_id(target_id: str, body: dict) -> dict:
    clean_target_id = _validate_desk_delivery_target_id(target_id)
    _reject_unexpected_delivery_fields(body, allowed=DESK_DELIVERY_DETECT_ALLOWED_FIELDS)
    candidate = _detect_chat_id_from_bot_updates()
    if candidate:
        chat_type = candidate.get("chat_type") or "chat"
        return {
            "schema_version": "desk_delivery_chat_detection_v1",
            "target_id": clean_target_id,
            "target_type": "telegram_bot",
            "ok": True,
            "status": "detected_from_bot_updates",
            "source": "telegram_bot_updates",
            "chat_id": candidate["chat_id"],
            "chat_type": chat_type,
            "title": "Chat ID detected",
            "detail": f"Detected the latest {chat_type} that messaged this bot. Review it, then save notifications.",
            "finished_at": _utc_now(),
        }
    current_user_id = _telegram_current_user_chat_id()
    if current_user_id:
        return {
            "schema_version": "desk_delivery_chat_detection_v1",
            "target_id": clean_target_id,
            "target_type": "telegram_bot",
            "ok": True,
            "status": "detected_from_telegram_session",
            "source": "telegram_session",
            "chat_id": current_user_id,
            "chat_type": "private",
            "title": "Private chat ID detected",
            "detail": "Detected your Telegram user ID from the local login. Send a message to the bot before live alerts, then save notifications.",
            "finished_at": _utc_now(),
        }
    token = delivery.resolve_telegram_bot_token()
    if token.token:
        detail = "Send any message to the bot, then retry detection. Telegram has not returned a chat for this bot yet."
    else:
        detail = "Save a Telegram bot token, send the bot a message, then retry detection. If you use Telegram login, finish Start login first."
    return {
        "schema_version": "desk_delivery_chat_detection_v1",
        "target_id": clean_target_id,
        "target_type": "telegram_bot",
        "ok": False,
        "status": "needs_bot_message",
        "source": "none",
        "chat_id": "",
        "chat_type": "",
        "title": "Chat ID not found",
        "detail": detail,
        "finished_at": _utc_now(),
    }


def _local_notification_token() -> local_credentials.StoredSecret | None:
    if not local_credentials.is_supported():
        return None
    return local_credentials.read_secret(delivery.TELEGRAM_BOT_TOKEN_CREDENTIAL_TARGET)


def _local_store_backend(local_supported: bool) -> str:
    try:
        selected = local_credentials.backend()
    except Exception:
        selected = local_credentials.BACKEND_UNSUPPORTED
    if selected != local_credentials.BACKEND_UNSUPPORTED:
        return selected
    # Some tests patch is_supported/read/write directly to exercise dashboard
    # behavior without invoking the OS store. Keep that compatibility while
    # production still derives support from local_credentials.backend().
    return local_credentials.BACKEND_WINDOWS if local_supported else local_credentials.BACKEND_UNSUPPORTED


def _local_store_label(local_supported: bool) -> str:
    try:
        label = local_credentials.store_label()
    except Exception:
        label = "environment variables only"
    if local_supported and label == "environment variables only":
        return "Windows Credential Manager"
    return label


def desk_notification_token_status() -> dict:
    env_configured = bool(os.environ.get(delivery.TELEGRAM_BOT_TOKEN_ENV, "").strip())
    local_supported = local_credentials.is_supported()
    local_backend = _local_store_backend(local_supported)
    local_label = _local_store_label(local_supported)
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

    source = "environment" if env_configured else local_backend if local_configured else "missing"
    configured = env_configured or local_configured
    if env_configured:
        detail = "Telegram bot token is configured from the environment. Environment wins over local storage."
    elif local_configured:
        detail = f"Telegram bot token is saved in {local_label}."
    elif local_supported:
        detail = "Telegram bot token is not configured."
    else:
        detail = "Local secure token storage is unavailable on this machine. Set TGCS_TELEGRAM_BOT_TOKEN instead."
    return {
        "schema_version": "desk_notification_token_status_v1",
        "configured": configured,
        "source": source,
        "updated_at": None if env_configured else local_updated_at,
        "env_configured": env_configured,
        "local_store_supported": local_supported,
        "local_store_configured": local_configured,
        "local_store_backend": local_backend,
        "local_store_label": local_label,
        "can_save": local_supported,
        "can_clear": local_supported and local_configured,
        "platform": sys.platform,
        "detail": detail if not local_error else f"{detail} {local_error}",
    }


def _enabled_telegram_bot_target_count(conn) -> int:
    try:
        rows = conn.execute(
            "SELECT config_json FROM delivery_targets WHERE enabled = 1 AND target_type = ?",
            ("telegram_bot",),
        ).fetchall()
    except Exception:
        return 0
    count = 0
    for row in rows:
        payload = monitor_state.parse_json(row["config_json"], {})
        config = payload.get("config") if isinstance(payload, dict) and isinstance(payload.get("config"), dict) else payload
        if isinstance(config, dict) and str(config.get("chat_id") or "").strip():
            count += 1
    return count


def _load_bot_gateway_state() -> dict[str, object]:
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
    state = _load_bot_gateway_state()
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
        "background": background,
        "started_at": str(state.get("started_at") or "") if state else "",
        "last_poll_at": str(state.get("last_poll_at") or "") if state else "",
    }


def apply_desk_bot_identity() -> dict:
    try:
        from scripts import bot_gateway
    except ModuleNotFoundError:
        _PROJECT_ROOT = str(PROJECT_ROOT)
        if _PROJECT_ROOT not in sys.path:
            sys.path.insert(0, _PROJECT_ROOT)
        from scripts import bot_gateway

    try:
        return bot_gateway.apply_bot_identity()
    except bot_gateway.BotGatewayError as exc:
        raise ValueError(str(exc)) from exc


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
        raise ValueError("Local secure token storage is unavailable. Set TGCS_TELEGRAM_BOT_TOKEN in the environment instead.")
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


def _local_ai_secret(provider_id: str) -> local_credentials.StoredSecret | None:
    config = DESK_AI_PROVIDER_CONFIGS[provider_id]
    try:
        return local_credentials.read_secret(config["target"])
    except local_credentials.CredentialStoreError:
        return None


def desk_ai_settings_status() -> dict:
    providers = []
    local_supported = local_credentials.is_supported()
    local_backend = _local_store_backend(local_supported)
    local_label = _local_store_label(local_supported)
    for provider_id, config in DESK_AI_PROVIDER_CONFIGS.items():
        env_name = config["env_name"]
        env_configured = bool(os.environ.get(env_name, "").strip())
        stored = _local_ai_secret(provider_id) if local_supported else None
        local_configured = bool(stored and stored.secret.strip())
        configured = env_configured or local_configured
        if env_configured:
            source = "environment"
            detail = f"{config['label']} is configured from {env_name}. Environment wins over local storage."
        elif local_configured:
            source = local_backend
            detail = f"{config['label']} API key is saved in {local_label}."
        else:
            source = "missing"
            detail = f"{config['label']} API key is not configured."
        providers.append(
            {
                "provider": provider_id,
                "label": config["label"],
                "env_name": env_name,
                "configured": configured,
                "source": source,
                "env_configured": env_configured,
                "local_store_configured": local_configured,
                "local_store_backend": local_backend,
                "local_store_label": local_label,
                "can_save": local_supported,
                "can_clear": local_configured,
                "updated_at": None if env_configured else stored.updated_at if stored else None,
                "detail": detail,
            }
        )
    configured_count = sum(1 for provider in providers if provider["configured"])
    return {
        "schema_version": "desk_ai_settings_status_v1",
        "configured_count": configured_count,
        "local_store_supported": local_supported,
        "local_store_backend": local_backend,
        "local_store_label": local_label,
        "platform": sys.platform,
        "detail": (
            f"{configured_count} AI provider key{'s' if configured_count != 1 else ''} configured."
            if configured_count
            else "No AI provider keys configured yet."
        ),
        "providers": providers,
        "checked_at": _utc_now(),
    }


def _clean_ai_provider(value: object) -> str:
    provider = str(value or "").strip().casefold()
    if provider not in DESK_AI_PROVIDER_CONFIGS:
        raise ValueError("Choose a supported AI provider.")
    return provider


def _clean_ai_api_key(value: object) -> str:
    key = str(value or "").strip()
    if not key:
        raise ValueError("Enter an API key before saving.")
    if len(key) < 8:
        raise ValueError("API key is too short.")
    if len(key) > 1024:
        raise ValueError("API key is too long for local secure storage.")
    if any(ord(char) < 32 for char in key) or any(char.isspace() for char in key):
        raise ValueError("API key cannot contain spaces or control characters.")
    return key


def update_desk_ai_settings(body: dict) -> dict:
    unexpected = set(body) - DESK_AI_SETTINGS_ALLOWED_FIELDS
    if unexpected:
        raise ValueError(f"Unsupported AI settings field: {', '.join(sorted(unexpected))}")
    if not local_credentials.is_supported():
        raise ValueError("Local secure API key storage is unavailable. Set the provider API key in the environment instead.")
    provider_id = _clean_ai_provider(body.get("provider"))
    config = DESK_AI_PROVIDER_CONFIGS[provider_id]
    clear = body.get("clear") is True
    raw_key = body.get("api_key")
    if body.get("clear") not in (None, True, False):
        raise ValueError("AI key clear value must be true or false.")
    if clear and raw_key:
        raise ValueError("Save or clear the AI API key, not both.")
    if clear:
        local_credentials.delete_secret(config["target"])
    elif raw_key is not None:
        local_credentials.write_secret(
            config["target"],
            _clean_ai_api_key(raw_key),
            username=config["username"],
        )
    else:
        raise ValueError("Save or clear an AI API key.")
    return desk_ai_settings_status()


def desk_action_env() -> dict[str, str]:
    env = os.environ.copy()
    for provider_id, config in DESK_AI_PROVIDER_CONFIGS.items():
        env_name = config["env_name"]
        if env.get(env_name):
            continue
        stored = _local_ai_secret(provider_id)
        if stored and stored.secret.strip():
            env[env_name] = stored.secret.strip()
    return env


def _reject_unexpected_source_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_IMPORT_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source import field: {', '.join(unexpected)}")


def _reject_unexpected_source_starter_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_STARTER_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported starter source field: {', '.join(unexpected)}")


def _reject_unexpected_source_assistant_fields(body: dict) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in DESK_SOURCE_ASSISTANT_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported source assistant field: {', '.join(unexpected)}")


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


def _source_operation_payload(
    *,
    action: str,
    topic: str,
    dry_run: bool,
    added_count: int = 0,
    updated_count: int = 0,
    unchanged_count: int = 0,
    removed_count: int = 0,
    enabled_count: int = 0,
    disabled_count: int = 0,
    preview_sources: list[dict] | None = None,
    resolved_plan: dict[str, list[str]] | None = None,
    title: str,
    detail: str,
    llm_used: bool = False,
) -> dict:
    return {
        "schema_version": "desk_source_import_result_v1",
        "dry_run": dry_run,
        "written": not dry_run,
        "action": action,
        "topic": topic,
        "added_count": added_count,
        "updated_count": updated_count,
        "unchanged_count": unchanged_count,
        "removed_count": removed_count,
        "enabled_count": enabled_count,
        "disabled_count": disabled_count,
        "source_count": desk_sources()["source_count"],
        "registry_path": ".tgcs/sources.json",
        "preview_sources": preview_sources or [],
        "preview_truncated_count": 0,
        "resolved_plan": resolved_plan or {"add": [], "remove": [], "disable": [], "enable": []},
        "llm_used": llm_used,
        "title": title,
        "detail": detail,
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


def remove_desk_source(source_id: str, body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in {"confirm"})
    if unexpected:
        raise ValueError(f"Unsupported source remove field: {', '.join(unexpected)}")
    if body.get("confirm") is not True:
        raise ValueError("Source removal requires confirmation.")
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    source_registry.remove_sources(registry_path, source_ids=[_validate_desk_source_id(source_id)])
    return desk_sources()


def source_access_health_path() -> Path:
    return PROJECT_ROOT / ".tgcs" / "source-access-health.json"


def _source_access_health_loaded() -> dict | None:
    path = source_access_health_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION:
        return None
    return payload


def _write_source_access_health(payload: dict) -> None:
    path = source_access_health_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _source_access_checked_at(payload: dict) -> datetime | None:
    text = str(payload.get("checked_at") or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _source_access_health_is_fresh(payload: dict, *, max_age_hours: int = DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS) -> bool:
    checked_at = _source_access_checked_at(payload)
    if checked_at is None:
        return False
    return checked_at >= datetime.now(UTC) - timedelta(hours=max_age_hours)


def _source_access_reason_label(reason: str) -> str:
    return {
        "cannot_resolve_entity": "cannot resolve",
        "permission_or_private": "private or permission",
        "rate_limited": "rate limited",
        "empty_recent_window": "quiet",
        "source_missing_identifier": "missing identifier",
        "timeout": "timeout",
        "access_error": "access error",
    }.get(reason, reason.replace("_", " "))


def _source_access_health_detail(payload: dict) -> str:
    accessible = int(payload.get("accessible_count") or 0)
    quiet = int(payload.get("quiet_count") or 0)
    inaccessible = int(payload.get("inaccessible_count") or 0)
    checked = int(payload.get("checked_count") or 0)
    truncated = int(payload.get("truncated_count") or 0)
    window_min = int(payload.get("probe_window_hours_min") or payload.get("probe_window_hours") or 0)
    window_max = int(payload.get("probe_window_hours_max") or payload.get("probe_window_hours") or 0)
    window_text = ""
    if window_min and window_max and window_min == window_max:
        window_text = f" in the last {window_max}h"
    elif window_min and window_max:
        window_text = f" in each source window ({window_min}-{window_max}h)"
    reason_counts = payload.get("reason_counts") if isinstance(payload.get("reason_counts"), dict) else {}
    issue_parts = [
        f"{_source_access_reason_label(str(reason))} {int(count)}"
        for reason, count in sorted(reason_counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[:3]
        if int(count or 0) > 0
    ]
    detail = (
        f"Access check: {accessible} recently active, {quiet} quiet{window_text}, "
        f"{inaccessible} inaccessible across {checked} checked sources."
    )
    if issue_parts:
        detail += f" Notes: {', '.join(issue_parts)}."
    if truncated:
        detail += f" {truncated} additional enabled sources were not checked by the bounded probe."
    return detail


def _source_access_action_summary(payload: dict) -> dict:
    reason_counts = payload.get("reason_counts") if isinstance(payload.get("reason_counts"), dict) else {}
    window_min = int(payload.get("probe_window_hours_min") or payload.get("probe_window_hours") or 0)
    window_max = int(payload.get("probe_window_hours_max") or payload.get("probe_window_hours") or 0)
    summary = {
        "schema_version": DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION,
        "checked_at": str(payload.get("checked_at") or ""),
        "source_count": int(payload.get("source_count") or 0),
        "checked_count": int(payload.get("checked_count") or 0),
        "accessible_count": int(payload.get("accessible_count") or 0),
        "quiet_count": int(payload.get("quiet_count") or 0),
        "inaccessible_count": int(payload.get("inaccessible_count") or 0),
        "truncated_count": int(payload.get("truncated_count") or 0),
        "reason_counts": {
            str(reason): int(count or 0)
            for reason, count in reason_counts.items()
            if int(count or 0) > 0
        },
    }
    if window_min and window_max:
        summary["probe_window_hours_min"] = window_min
        summary["probe_window_hours_max"] = window_max
        if window_min == window_max:
            summary["probe_window_hours"] = window_max
    return summary


def _source_access_record_base(source: dict) -> dict:
    channel = source_registry.channel_value(source)
    label = str(source.get("label") or channel or source.get("source_id") or "Unknown source").strip()
    return {
        "source_id": str(source.get("source_id") or ""),
        "label": label,
        "channel": channel,
        "topics": source_registry.normalize_topics(source.get("topics") or []),
        "scan_window_hours": int(source.get("scan_window_hours") or source_registry.DEFAULT_SCAN_WINDOW_HOURS),
    }


def _source_access_error_reason(exc: Exception) -> str:
    name = exc.__class__.__name__.casefold()
    text = str(exc).casefold()
    if "floodwait" in name or "flood wait" in text or "too many requests" in text:
        return "rate_limited"
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return "timeout"
    if any(marker in text for marker in ("cannot resolve", "could not find the input entity", "no user has")):
        return "cannot_resolve_entity"
    if any(marker in text for marker in ("private", "forbidden", "not a participant", "invite", "permission")):
        return "permission_or_private"
    return "access_error"


def _source_access_failure_record(source: dict, exc: Exception) -> dict:
    reason = _source_access_error_reason(exc)
    return {
        **_source_access_record_base(source),
        "status": "inaccessible",
        "reason": reason,
        "detail": f"Telegram returned {exc.__class__.__name__}.",
        "latest_message_at": "",
    }


async def _resolve_probe_entity(client, channel: str):
    clean = channel.strip()
    if clean.lstrip("-").isdigit():
        entity_id = int(clean)
        try:
            return await client.get_entity(entity_id)
        except Exception as first_error:
            async for dialog in client.iter_dialogs():
                if getattr(dialog.entity, "id", None) == entity_id:
                    return dialog.entity
            raise ValueError(f"Cannot resolve entity: {clean}") from first_error
    try:
        return await client.get_entity(clean)
    except Exception as first_error:
        clean_lower = clean.casefold()
        async for dialog in client.iter_dialogs():
            name = str(getattr(dialog, "name", "") or "").casefold()
            if name == clean_lower:
                return dialog.entity
        raise ValueError(f"Cannot resolve entity: {clean}") from first_error


def _message_datetime(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


async def _probe_one_source_access(client, source: dict, *, now: datetime) -> dict:
    base = _source_access_record_base(source)
    channel = base["channel"]
    if not channel:
        return {
            **base,
            "status": "inaccessible",
            "reason": "source_missing_identifier",
            "detail": "Source has no Telegram handle or numeric chat id.",
            "latest_message_at": "",
        }
    try:
        entity = await _resolve_probe_entity(client, channel)
        messages = await client.get_messages(entity, limit=1)
    except Exception as exc:
        return _source_access_failure_record(source, exc)

    latest = messages[0] if messages else None
    latest_at = _message_datetime(getattr(latest, "date", None)) if latest is not None else None
    window_hours = int(base.get("scan_window_hours") or source_registry.DEFAULT_SCAN_WINDOW_HOURS)
    if latest_at is None:
        return {
            **base,
            "status": "quiet",
            "reason": "empty_recent_window",
            "detail": "Telegram access works, but no recent message timestamp was found.",
            "latest_message_at": "",
        }
    if latest_at < now - timedelta(hours=window_hours):
        return {
            **base,
            "status": "quiet",
            "reason": "empty_recent_window",
            "detail": f"Telegram access works, but no messages were found in the last {window_hours} hours.",
            "latest_message_at": latest_at.isoformat().replace("+00:00", "Z"),
        }
    return {
        **base,
        "status": "accessible",
        "reason": "recent_message_found",
        "detail": "Telegram access works for the current scan window.",
        "latest_message_at": latest_at.isoformat().replace("+00:00", "Z"),
    }


def _source_access_summary(records: list[dict], *, total_source_count: int, truncated_count: int, checked_at: str) -> dict:
    status_counts = Counter(str(record.get("status") or "unknown") for record in records)
    reason_counts = Counter(
        str(record.get("reason") or "unknown")
        for record in records
        if str(record.get("status") or "") in {"inaccessible", "quiet"}
    )
    window_values = [
        int(record.get("scan_window_hours") or 0)
        for record in records
        if int(record.get("scan_window_hours") or 0) > 0
    ]
    summary = {
        "schema_version": DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION,
        "checked_at": checked_at,
        "source_count": total_source_count,
        "checked_count": len(records),
        "truncated_count": truncated_count,
        "accessible_count": int(status_counts.get("accessible", 0)),
        "quiet_count": int(status_counts.get("quiet", 0)),
        "inaccessible_count": int(status_counts.get("inaccessible", 0)),
        "reason_counts": dict(sorted(reason_counts.items())),
        "sources": records,
    }
    if window_values:
        summary["probe_window_hours_min"] = min(window_values)
        summary["probe_window_hours_max"] = max(window_values)
        if min(window_values) == max(window_values):
            summary["probe_window_hours"] = max(window_values)
    return summary


async def _probe_source_access_async(progress_callback=None) -> dict:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    try:
        registry = source_registry.load_registry(registry_path)
        issues = source_registry.validate_registry(registry)
    except (OSError, source_registry.RegistryError) as exc:
        raise SourceAccessProbeError(
            str(exc),
            next_action="Prepare Signal Desk files or repair the source registry, then check source access again.",
        ) from exc
    if issues:
        raise SourceAccessProbeError(
            source_registry.validation_message(issues),
            next_action="Run Check source syntax or repair starter sources before access probing.",
        )
    sources = [
        source
        for source in source_registry.enabled_sources(registry)
        if isinstance(source, dict)
    ]
    if not sources:
        raise SourceAccessProbeError(
            "No enabled sources are saved.",
            next_action="Add or enable at least one source, then check source access again.",
        )

    try:
        api_id, api_hash = _load_telegram_credentials()
    except ValueError as exc:
        raise SourceAccessProbeError(
            "Telegram API credentials are not configured.",
            next_action="Connect Telegram from Start, then check source access again.",
        ) from exc
    session_string = TELEGRAM_SESSION_PATH.read_text(encoding="utf-8").strip() if TELEGRAM_SESSION_PATH.exists() else ""
    if not session_string:
        raise SourceAccessProbeError(
            "Telegram login is not complete.",
            next_action="Finish Telegram login from Start, then check source access again.",
        )

    checked_sources = sources[:DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES]
    now = datetime.now(UTC)
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SourceAccessProbeError(
                "Telegram login is not authorized.",
                next_action="Reconnect Telegram from Start, then check source access again.",
            )
        records = []
        for index, source in enumerate(checked_sources, start=1):
            records.append(await _probe_one_source_access(client, source, now=now))
            if progress_callback:
                progress_callback(index, len(checked_sources))
    finally:
        await client.disconnect()

    summary = _source_access_summary(
        records,
        total_source_count=len(sources),
        truncated_count=max(0, len(sources) - len(checked_sources)),
        checked_at=now.isoformat().replace("+00:00", "Z"),
    )
    _write_source_access_health(summary)
    return summary


def probe_source_access(progress_callback=None) -> dict:
    return asyncio.run(_probe_source_access_async(progress_callback=progress_callback))


def _require_confirm_only(body: dict | None, *, action_label: str) -> None:
    body = body or {}
    unexpected = sorted(str(key) for key in body.keys() if key not in {"confirm"})
    if unexpected:
        raise DashboardDeskActionError(f"{action_label} only accepts an explicit confirmation flag.")
    if body.get("confirm") is not True:
        raise DashboardDeskActionError(f"{action_label} requires explicit confirmation.")


def _source_access_target_ids(payload: dict, *, keep_only_accessible: bool) -> list[str]:
    wanted_statuses = {"inaccessible", "quiet"} if keep_only_accessible else {"inaccessible"}
    ids: list[str] = []
    seen: set[str] = set()
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    for record in sources:
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "") not in wanted_statuses:
            continue
        source_id = str(record.get("source_id") or "").strip()
        if not source_id or source_id in seen:
            continue
        try:
            ids.append(_validate_desk_source_id(source_id))
        except ValueError:
            continue
        seen.add(source_id)
    return ids


def _disable_sources_from_access_health(source_ids: list[str]) -> int:
    if not source_ids:
        return 0
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    try:
        payload = source_registry.load_registry(registry_path)
    except (OSError, source_registry.RegistryError) as exc:
        raise DashboardDeskActionError(str(exc)) from exc
    issues = source_registry.validate_registry(payload)
    if issues:
        raise DashboardDeskActionError(source_registry.validation_message(issues))
    target_ids = set(source_ids)
    changed = 0
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        if source.get("source_id") in target_ids and source.get("enabled", True):
            source["enabled"] = False
            changed += 1
    if changed:
        source_registry.save_registry(registry_path, payload)
    return changed


def apply_source_access_repair(action_id: str, *, body: dict | None = None) -> dict:
    action_label = "Source access repair"
    _require_confirm_only(body, action_label=action_label)
    health = _source_access_health_loaded()
    if not health:
        return _desk_action_result(
            action_id,
            status="blocked",
            title="Check source access first",
            detail="Signal Desk needs a recent source access check before it can safely disable sources.",
            next_action="Run Check source access, then retry this repair action.",
        )
    if not _source_access_health_is_fresh(health):
        return _desk_action_result(
            action_id,
            status="blocked",
            title="Source access check is stale",
            detail="Run a fresh access check before changing the saved source list.",
            next_action="Run Check source access, then retry this repair action.",
        )
    keep_only_accessible = action_id == "sources_keep_accessible"
    target_ids = _source_access_target_ids(health, keep_only_accessible=keep_only_accessible)
    changed_count = _disable_sources_from_access_health(target_ids)
    if keep_only_accessible:
        title = "Recently active sources kept"
        detail = (
            f"Signal Desk disabled {changed_count} inaccessible or quiet sources from the latest access check. "
            "Quiet sources were readable, but had no recent messages in the probe window."
        )
    else:
        title = "Inaccessible sources paused"
        detail = f"Signal Desk disabled {changed_count} inaccessible sources from the latest access check."
    return _desk_action_result(
        action_id,
        status="success",
        title=title,
        detail=detail,
        next_action="Run a fresh practice scan to verify the narrowed source list.",
    )


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


def import_starter_sources(body: dict) -> dict:
    _reject_unexpected_source_starter_fields(body)
    topic = _clean_source_topic(body.get("topic"))
    starter_path = PROJECT_ROOT / "channel_lists" / "jobs.txt"
    if not starter_path.exists():
        starter_path = PROJECT_ROOT / "channel_lists" / "example.txt"
    if not starter_path.exists():
        raise ValueError("Starter source list is missing from this checkout.")
    channels = source_registry.load_channel_list(starter_path)
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    result = source_registry.import_channels(
        channels,
        registry_path,
        dry_run=False,
        topics=[topic],
        input_path="packaged starter sources",
    )
    payload = _source_import_payload(result, topic=topic, written=True)
    payload["title"] = "Starter sources installed"
    payload["detail"] = "Signal Desk added the packaged starter source set. Replace or prune it from Settings as you learn what works."
    return payload


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


def _extract_source_channels_from_text(text: str) -> list[str]:
    channels: list[str] = []
    for match in re.finditer(r"(?:https?://)?t\.me/(?:s/)?([A-Za-z0-9_]{5,64}|-?[0-9]{5,20})", text, re.IGNORECASE):
        channels.append(match.group(1))
    for match in re.finditer(r"@([A-Za-z0-9_]{5,64})", text):
        channels.append(match.group(1))
    for line in text.splitlines():
        clean = source_registry.normalize_channel_name(line)
        if re.fullmatch(r"(?:[A-Za-z0-9_]{5,64}|-?[0-9]{5,20})", clean):
            channels.append(clean)
    deduped: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        key = channel.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(channel)
    return deduped


def _source_id_from_channel(channel: str) -> str:
    source = source_registry.source_from_channel(channel)
    return str(source["source_id"])


def _source_assistant_action(text: str) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ("delete", "remove", "prune", "drop", "删", "删除", "移除", "清掉", "去掉")):
        return "remove"
    if any(word in lowered for word in ("pause", "disable", "mute", "stop", "暂停", "停用", "禁用")):
        return "disable"
    if any(word in lowered for word in ("enable", "resume", "use", "restore", "启用", "恢复", "使用")):
        return "enable"
    return "add"


def _source_assistant_plan(instruction: str) -> dict[str, list[str]]:
    plan = {"add": [], "remove": [], "disable": [], "enable": []}
    segments = [segment.strip() for segment in re.split(r"[\n;；。]+", instruction) if segment.strip()]
    for segment in segments or [instruction]:
        action = _source_assistant_action(segment)
        channels = _extract_source_channels_from_text(segment)
        if not channels:
            continue
        plan[action].extend(channels)
    for key, values in plan.items():
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = source_registry.normalize_channel_name(value)
            marker = normalized.casefold()
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(normalized)
        plan[key] = deduped
    return plan


def _source_assistant_has_plan(plan: dict[str, list[str]]) -> bool:
    return any(bool(values) for values in plan.values())


def _source_assistant_requested_existing_actions(instruction: str) -> set[str]:
    requested: set[str] = set()
    segments = [segment.strip() for segment in re.split(r"[\n;；。]+", instruction) if segment.strip()]
    for segment in segments or [instruction]:
        action = _source_assistant_action(segment)
        if action in {"remove", "disable", "enable"}:
            requested.add(action)
    return requested


def _source_assistant_should_use_llm_plan(instruction: str, plan: dict[str, list[str]]) -> bool:
    if not _source_assistant_has_plan(plan):
        return True
    requested_existing_actions = _source_assistant_requested_existing_actions(instruction)
    return any(not plan[action] for action in requested_existing_actions)


def _dedupe_source_ids(source_ids: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        clean = _validate_desk_source_id(source_id)
        marker = clean.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(clean)
    return deduped


def _dedupe_source_channels(channels: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        clean = source_registry.normalize_channel_name(channel)
        if not clean:
            continue
        marker = clean.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(clean)
    return deduped


def _clean_resolved_source_plan(plan: dict) -> dict[str, list[str]]:
    if not isinstance(plan, dict):
        raise ValueError("Source plan must be an object.")
    return {
        "add": _dedupe_source_channels([str(value) for value in plan.get("add") or []]),
        "remove": _dedupe_source_ids([str(value) for value in plan.get("remove") or []]),
        "disable": _dedupe_source_ids([str(value) for value in plan.get("disable") or []]),
        "enable": _dedupe_source_ids([str(value) for value in plan.get("enable") or []]),
    }


def _source_assistant_llm_plan(instruction: str, topic: str, existing: dict[str, dict]) -> dict[str, list[str]]:
    if not report.llm_key_available():
        raise ValueError("Save an AI API key in Settings before using AI source planning.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("Install optional LLM dependencies before using AI source planning.") from exc

    base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)
    provider = report.llm_provider(base_url, model)
    api_key = report.api_key_for_provider(provider)
    if not api_key:
        raise ValueError("Save an AI API key in Settings before using AI source planning.")

    sources = [
        {
            "source_id": source_id,
            "label": str(source.get("label") or ""),
            "channel": source_registry.channel_value(source),
            "topics": source_registry.normalize_topics(source.get("topics") or []),
            "enabled": bool(source.get("enabled", True)),
        }
        for source_id, source in sorted(existing.items())
    ][:300]
    system_prompt = (
        "You plan local Telegram source registry changes. Return JSON only with keys "
        "remove, disable, enable. Each value must be a list of source_id strings copied "
        "from the provided sources. Do not invent source ids, commands, paths, argv, tokens, "
        "or new Telegram channels. If the instruction asks to add unknown sources, return empty lists."
    )
    user_prompt = json.dumps(
        {
            "instruction": instruction,
            "topic": topic,
            "sources": sources,
            "output_schema": {"remove": ["telegram:..."], "disable": ["telegram:..."], "enable": ["telegram:..."]},
        },
        ensure_ascii=False,
    )
    create_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": report.llm_temperature(provider),
    }
    if provider in {"deepseek", "openai"}:
        create_kwargs["response_format"] = {"type": "json_object"}
    thinking_extra = report.minimax_thinking_extra(provider) or report.deepseek_thinking_extra(provider, model)
    if thinking_extra:
        create_kwargs["extra_body"] = thinking_extra
    report.add_token_limit(create_kwargs, provider=provider, max_tokens=700)

    try:
        response = OpenAI(api_key=api_key, base_url=base_url).chat.completions.create(**create_kwargs)
    except Exception as exc:
        raise ValueError(f"AI source planning failed: {exc}") from exc
    raw = response.choices[0].message.content or ""
    try:
        payload = json.loads(report.strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("AI source planning did not return valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("AI source planning must return a JSON object.")

    existing_ids = set(existing)
    plan: dict[str, list[str]] = {"remove": [], "disable": [], "enable": []}
    for action in plan:
        values = payload.get(action) or []
        if not isinstance(values, list):
            raise ValueError("AI source planning returned an invalid action list.")
        for value in values:
            source_id = _validate_desk_source_id(str(value))
            if source_id in existing_ids:
                plan[action].append(source_id)
    return {action: _dedupe_source_ids(values) for action, values in plan.items()}


def run_source_assistant(body: dict) -> dict:
    _reject_unexpected_source_assistant_fields(body)
    instruction = str(body.get("instruction") or "").strip()
    if len(instruction) > 4000:
        raise ValueError("Source instruction is too long.")
    if not instruction:
        raise ValueError("Describe what to add, pause, or remove.")
    topic = _clean_source_topic(body.get("topic"))
    dry_run = body.get("dry_run") is not False
    confirm_external_ai = body.get("confirm_external_ai", False)
    if not isinstance(confirm_external_ai, bool):
        raise ValueError("AI source planning confirmation must be true or false.")
    resolved_plan = body.get("resolved_plan")
    if resolved_plan is not None and not isinstance(resolved_plan, dict):
        raise ValueError("Resolved source plan must be an object.")
    if not dry_run and resolved_plan is not None:
        return apply_source_assistant_resolved_plan(resolved_plan, topic)
    plan = _source_assistant_plan(instruction)
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    preview_sources: list[dict] = []
    added_count = updated_count = unchanged_count = removed_count = enabled_count = disabled_count = 0
    llm_used = False
    resolved_plan = {"add": list(plan["add"]), "remove": [], "disable": [], "enable": []}

    if plan["add"]:
        result = source_registry.import_channels(
            plan["add"],
            registry_path,
            dry_run=dry_run,
            topics=[topic],
            input_path="source assistant",
        )
        added_count += int(result.get("added_count") or 0)
        updated_count += int(result.get("updated_count") or 0)
        unchanged_count += int(result.get("unchanged_count") or 0)
        for source in (result.get("sources") or []) + (result.get("updated_sources") or []) + (result.get("unchanged_sources") or []):
            if isinstance(source, dict):
                preview_sources.append(_desk_source_record(source))

    payload = source_registry.load_registry(registry_path, missing_ok=True)
    existing = {str(source.get("source_id")): source for source in payload.get("sources", []) if isinstance(source, dict)}
    llm_plan = {"remove": [], "disable": [], "enable": []}
    if confirm_external_ai and _source_assistant_should_use_llm_plan(instruction, plan):
        # Explicit confirmation is required because this sends the existing local
        # source list to the configured model. We only do it when local parsing
        # missed an existing-source operation, including mixed "add + pause" text.
        llm_plan = _source_assistant_llm_plan(instruction, topic, existing)
        llm_used = True

    def source_ids(values: list[str]) -> list[str]:
        return [_source_id_from_channel(value) for value in values]

    disable_ids = _dedupe_source_ids(source_ids(plan["disable"]) + llm_plan["disable"])
    resolved_plan["disable"] = list(disable_ids)
    for source_id in disable_ids:
        source = existing.get(source_id)
        if not source:
            continue
        disabled_count += 1
        preview_sources.append(_desk_source_record({**source, "enabled": False}))
        if not dry_run:
            source_registry.update_source_enabled(registry_path, source_id=source_id, enabled=False)
    enable_ids = _dedupe_source_ids(source_ids(plan["enable"]) + llm_plan["enable"])
    resolved_plan["enable"] = list(enable_ids)
    for source_id in enable_ids:
        source = existing.get(source_id)
        if not source:
            continue
        enabled_count += 1
        preview_sources.append(_desk_source_record({**source, "enabled": True}))
        if not dry_run:
            source_registry.update_source_enabled(registry_path, source_id=source_id, enabled=True)
    remove_ids = [source_id for source_id in _dedupe_source_ids(source_ids(plan["remove"]) + llm_plan["remove"]) if source_id in existing]
    resolved_plan["remove"] = list(remove_ids)
    removed_count += len(remove_ids)
    for source_id in remove_ids:
        preview_sources.append(_desk_source_record(existing[source_id]))
    if remove_ids and not dry_run:
        source_registry.remove_sources(registry_path, source_ids=remove_ids)

    operation_count = added_count + updated_count + unchanged_count + removed_count + enabled_count + disabled_count
    if operation_count == 0:
        ai_hint = (
            " AI keys are configured, but Signal Desk will not send private source lists to an external model without a dedicated confirmation flow."
            if report.llm_key_available()
            else ""
        )
        return _source_operation_payload(
            action="assistant",
            topic=topic,
            dry_run=True,
            title="No source changes found",
            detail=f"Include Telegram handles, t.me links, numeric chat IDs, or enable AI source planning. For example: add @remote_jobs; remove @old_jobs.{ai_hint}",
            llm_used=llm_used,
            resolved_plan=resolved_plan,
        )
    return _source_operation_payload(
        action="assistant",
        topic=topic,
        dry_run=dry_run,
        added_count=added_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        removed_count=removed_count,
        enabled_count=enabled_count,
        disabled_count=disabled_count,
        preview_sources=preview_sources[:12],
        resolved_plan=resolved_plan,
        title="Source plan ready" if dry_run else "Source plan applied",
        detail="Review the plan, then apply it." if dry_run else "Signal Desk updated the local source registry.",
        llm_used=llm_used,
    )


def apply_source_assistant_resolved_plan(plan: dict, topic: str) -> dict:
    clean_plan = _clean_resolved_source_plan(plan)
    clean_topic = _clean_source_topic(topic)
    registry_path = PROJECT_ROOT / ".tgcs" / "sources.json"
    preview_sources: list[dict] = []
    added_count = updated_count = unchanged_count = removed_count = enabled_count = disabled_count = 0

    if clean_plan["add"]:
        result = source_registry.import_channels(
            clean_plan["add"],
            registry_path,
            dry_run=False,
            topics=[clean_topic],
            input_path="source assistant confirmation",
        )
        added_count += int(result.get("added_count") or 0)
        updated_count += int(result.get("updated_count") or 0)
        unchanged_count += int(result.get("unchanged_count") or 0)
        for source in (result.get("sources") or []) + (result.get("updated_sources") or []) + (result.get("unchanged_sources") or []):
            if isinstance(source, dict):
                preview_sources.append(_desk_source_record(source))

    payload = source_registry.load_registry(registry_path, missing_ok=True)
    existing = {str(source.get("source_id")): source for source in payload.get("sources", []) if isinstance(source, dict)}

    for source_id in clean_plan["disable"]:
        source = existing.get(source_id)
        if not source:
            continue
        disabled_count += 1
        updated = source_registry.update_source_enabled(registry_path, source_id=source_id, enabled=False)
        preview_sources.append(_desk_source_record(updated))

    for source_id in clean_plan["enable"]:
        source = existing.get(source_id)
        if not source:
            continue
        enabled_count += 1
        updated = source_registry.update_source_enabled(registry_path, source_id=source_id, enabled=True)
        preview_sources.append(_desk_source_record(updated))

    removable_ids = [source_id for source_id in clean_plan["remove"] if source_id in existing]
    removed_count += len(removable_ids)
    for source_id in removable_ids:
        preview_sources.append(_desk_source_record(existing[source_id]))
    if removable_ids:
        source_registry.remove_sources(registry_path, source_ids=removable_ids)

    return _source_operation_payload(
        action="assistant",
        topic=clean_topic,
        dry_run=False,
        added_count=added_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        removed_count=removed_count,
        enabled_count=enabled_count,
        disabled_count=disabled_count,
        preview_sources=preview_sources[:12],
        resolved_plan=clean_plan,
        title="Source plan applied",
        detail="Signal Desk updated the local source registry from the confirmed plan.",
    )


def create_profile_from_brief(conn, body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in PROFILE_CREATE_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f"Unsupported profile creation field: {', '.join(unexpected)}")
    brief = _profile_create_input_text(body)
    title = _profile_title_from_text(brief)
    profile_id = _unique_profile_id(conn, _slugify_profile_id(title))
    profile_rel_path = Path("profiles") / "desk" / f"{profile_id}.md"
    profile_path = PROJECT_ROOT / profile_rel_path
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(_profile_markdown_from_brief(title, brief), encoding="utf-8")

    config = {
        "id": profile_id,
        "path": profile_rel_path.as_posix(),
        "enabled": True,
        "timezone": "Asia/Shanghai",
        "work_interval_minutes": 30,
        "off_hours_interval_minutes": 120,
        "scan_window_hours": 2,
        "source_registry": ".tgcs/sources.json",
        "channel_list": "channel_lists/example.txt",
        "source_topics": ["jobs"],
        "alert_rule": "high_new_or_changed",
        "alert_schedule_mode": "work_hours",
        "delivery_targets": [DESK_DELIVERY_TARGET_ID],
        "dashboard_visible": True,
        "prefilter_enabled": True,
        "semantic_max_messages": 20,
        "semantic_max_tokens": 6000,
        "prefilter_keywords": _profile_keywords_from_text(brief),
    }
    _append_profile_config(config)
    monitor_state.upsert_profile(conn, {**config, "path": str(profile_path)})
    return {
        "schema_version": "desk_profile_create_result_v1",
        "profile_id": profile_id,
        "display_name": title,
        "profile_path": profile_rel_path.as_posix(),
        "created": True,
        "detail": "Profile created from your brief. Review its matching rules, then run a practice scan.",
        "next_action": "Open the new profile, adjust matching rules if needed, then run a practice scan from Start.",
        "created_at": _utc_now(),
    }


def _profile_create_input_text(body: dict) -> str:
    parts: list[str] = []
    brief = str(body.get("brief") or "").strip()
    if brief:
        parts.append(brief)
    source_text = str(body.get("source_text") or "").strip()
    if source_text:
        parts.append(source_text)
    source_base64 = str(body.get("source_base64") or "").strip()
    if source_base64:
        filename = str(body.get("source_filename") or "").strip()
        parts.append(_profile_text_from_base64_file(source_base64, filename))
    text = "\n\n".join(part for part in parts if part.strip()).strip()
    if not text:
        raise ValueError("Describe the profile or attach a Markdown, text, or PDF file.")
    if len(text) > PROFILE_CREATE_MAX_TEXT_LENGTH:
        raise ValueError(f"Profile brief must be {PROFILE_CREATE_MAX_TEXT_LENGTH} characters or fewer after parsing.")
    return monitor_state.require_profile_text_without_private_fragments("Profile brief", text)


def _profile_text_from_base64_file(source_base64: str, filename: str) -> str:
    raw_text = source_base64.split(",", 1)[-1]
    try:
        data = base64.b64decode(raw_text, validate=False)
    except ValueError as exc:
        raise ValueError("Could not read the attached profile file.") from exc
    if len(data) > PROFILE_CREATE_MAX_BINARY_BYTES:
        raise ValueError("Profile file is too large for local parsing.")
    if Path(filename).suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF parsing is not installed on this machine; use Markdown or text for now.") from exc
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages).strip()
        if not text:
            raise ValueError("The PDF did not contain readable text. Paste the profile brief instead.")
        return text
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="ignore")


def _profile_title_from_text(text: str) -> str:
    for raw in text.splitlines():
        line = re.sub(r"^[#>*\-\s]+", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if line:
            return line[:72].strip(" :-") or "Custom Monitor"
    return "Custom Monitor"


def _slugify_profile_id(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:48].strip("-") or "custom-monitor"


def _unique_profile_id(conn, base_slug: str) -> str:
    existing = {str(row["profile_id"]) for row in conn.execute("SELECT profile_id FROM profiles").fetchall()}
    config_path = PROJECT_ROOT / ".tgcs" / "profiles.toml"
    if config_path.exists():
        try:
            with config_path.open("rb") as handle:
                payload = tomllib.load(handle)
            for item in payload.get("profiles") or []:
                if isinstance(item, dict) and item.get("id"):
                    existing.add(str(item["id"]))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    candidate = base_slug
    suffix = 2
    while candidate in existing or (PROJECT_ROOT / "profiles" / "desk" / f"{candidate}.md").exists():
        candidate = f"{base_slug[:42].strip('-')}-{suffix}"
        suffix += 1
    return candidate


def _profile_keywords_from_text(text: str) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", text.lower()):
        cleaned = word.strip(".-")
        if cleaned in seen or cleaned in {"the", "and", "with", "from", "that", "this", "profile", "monitor"}:
            continue
        seen.add(cleaned)
        keywords.append(cleaned)
        if len(keywords) >= 18:
            break
    return keywords or ["hiring", "opportunity", "role", "project", "apply"]


def _profile_markdown_from_brief(title: str, brief: str) -> str:
    rules = _profile_rule_lines(brief)
    goal = _profile_sentence(brief)
    return "\n".join(
        [
            f"# Profile: {title}",
            "",
            "## Basic Info",
            f"- **Goal**: {goal}",
            "- **Work format**: Use the pasted brief as the user's matching preference.",
            "- **Review style**: Prefer actionable items with clear next steps; reject vague promos.",
            "",
            "## Search Rules",
            *[f"{index + 1}. {rule}" for index, rule in enumerate(rules)],
            f"{len(rules) + 1}. Rate each item as high, medium, or low based on fit, freshness, and actionability.",
            f"{len(rules) + 2}. Keep low-priority items only when they explain a useful boundary.",
            "",
            "## Extraction Schema",
            "mode: custom",
            "top_level_key: items",
            "dedup_fields: [title, source]",
            "fields:",
            "  - name: source_message_refs",
            "    type: list",
            "  - name: source_message_ids",
            "    type: list",
            "  - name: title",
            "    required: true",
            "  - name: source",
            "  - name: contact",
            "  - name: link",
            "  - name: rating",
            "    values: [high, medium, low]",
            "  - name: why",
            "  - name: action",
            "    values: [Act now, Inspect, Skip unless criteria change]",
            "",
            "## Extraction Prompt",
            "system_prompt: |",
            "  Extract only Telegram items that match this monitor profile. Keep each item",
            "  compact and actionable. Do not copy long source text; explain why the item",
            "  matters in one sentence and preserve source references.",
            "",
            "## Report Preferences",
            "- Put high-priority items first and explain the fastest safe next step.",
            "- For medium matches, state what must be verified before acting.",
            "- For low matches, state which criterion would need to change.",
            "",
            "## Follow-up Preferences",
            "- No extra learned preferences yet.",
            "",
            "## Report Labels",
            f'report_title: "{_toml_escape_inline(title)} Signal Report"',
            'section_high: "Act Now"',
            'section_medium: "Inspect First"',
            'section_low: "Boundary Examples"',
            f'stats_label: "{_toml_escape_inline(title)} matches"',
            f'output_filename: "{_slugify_profile_id(title)}-signal-report-{{date}}.md"',
            f'profile_section_title: "{_toml_escape_inline(title)} Profile"',
            'methodology_label: "Telegram source monitoring"',
            "",
        ]
    )


def _profile_rule_lines(text: str) -> list[str]:
    candidates: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"^[#>*\-\d.\s]+", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if 12 <= len(line) <= 180:
            candidates.append(line.rstrip("."))
        if len(candidates) >= 5:
            break
    return candidates or ["Include items that match the user's pasted brief", "Ignore vague, low-confidence, or off-profile items"]


def _profile_sentence(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:220].rstrip(" ,.;") or "Monitor a custom set of Telegram signals"


def _toml_escape_inline(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _append_profile_config(config: dict) -> None:
    path = PROJECT_ROOT / ".tgcs" / "profiles.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
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
                ]
            ),
            encoding="utf-8",
        )
    block = [
        "",
        "[[profiles]]",
        f'id = {_toml_string(config["id"])}',
        f'path = {_toml_string(config["path"])}',
        "enabled = true",
        f'timezone = {_toml_string(config["timezone"])}',
        f'work_interval_minutes = {config["work_interval_minutes"]}',
        f'off_hours_interval_minutes = {config["off_hours_interval_minutes"]}',
        f'scan_window_hours = {config["scan_window_hours"]}',
        f'source_registry = {_toml_string(config["source_registry"])}',
        f'channel_list = {_toml_string(config["channel_list"])}',
        f'source_topics = {_toml_array(config["source_topics"])}',
        f'alert_rule = {_toml_string(config["alert_rule"])}',
        f'alert_schedule_mode = {_toml_string(config["alert_schedule_mode"])}',
        f'delivery_targets = {_toml_array(config["delivery_targets"])}',
        "dashboard_visible = true",
        "prefilter_enabled = true",
        f'semantic_max_messages = {config["semantic_max_messages"]}',
        f'semantic_max_tokens = {config["semantic_max_tokens"]}',
        f'prefilter_keywords = {_toml_array(config["prefilter_keywords"])}',
        "",
    ]
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(block))


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
        return normalized if is_dashboard_openable_artifact_path(normalized) else ""
    try:
        relative = str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return ""
    return relative if is_dashboard_openable_artifact_path(relative) else ""


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
            "Automatic practice scans would run every 15 minutes. Live Telegram delivery stays off.",
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
        "doctor_jobs": "Setup check finished. If no problem is shown, run a fresh practice scan.",
        "sources_validate": "Source list check finished. If no problem is shown, run a fresh practice scan.",
        "sources_import_jobs": "Starter channels were repaired. Next, check setup, then run a fresh practice scan.",
        "monitor_jobs_dry_run": "Fresh practice scan finished. Open Review for cards or Runs for scan evidence.",
    }.get(action_id, f"{fallback} finished.")


def _desk_failure_detail(payload: dict | None, stdout: str, stderr: str) -> tuple[str, str]:
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = _desk_safe_result_text(error.get("message") or "Desk action failed.")
        next_step = _desk_safe_result_text(error.get("next_step") or "Inspect the command output and fix the reported issue.")
        return message, next_step
    text = (stderr or stdout or "Desk action failed.").strip()
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
    for root in {PROJECT_ROOT, PROJECT_ROOT.resolve()}:
        raw = str(root)
        if not raw:
            continue
        # Windows scheduler errors often include a concrete file below the
        # project root. Replace the whole local project path before the generic
        # drive-letter scrubber, otherwise the user sees a vague "local path"
        # and loses the actionable context that the failing file belongs to
        # this project folder.
        normalized = re.escape(raw).replace(r"\\", r"[\\/]")
        sanitized = re.sub(
            normalized + r"(?:[\\/][^\r\n\"<>|]*)?",
            "project folder",
            sanitized,
            flags=re.IGNORECASE,
        )
    replacements = {
        str(Path.home().resolve()): "~",
        str(Path.home().resolve()).replace("\\", "/"): "~",
    }
    for needle, replacement in replacements.items():
        if needle:
            sanitized = sanitized.replace(needle, replacement)
    sanitized = re.sub(r"(?i)\b[A-Z]:\\[^\r\n\"<>|]+", "local path", sanitized)
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


def _scheduler_backend() -> str:
    if sys.platform.startswith("win"):
        return "windows_schtasks"
    if sys.platform == "darwin":
        return "macos_launchd"
    if sys.platform.startswith("linux") and shutil.which("systemctl") and os.environ.get("XDG_RUNTIME_DIR"):
        return "linux_systemd_user"
    return "manual_cron_preview"


def _scheduler_base(backend: str) -> dict:
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


def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{DESK_SCHEDULER_LAUNCHD_LABEL}.plist"


def _systemd_user_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _systemd_service_path() -> Path:
    return _systemd_user_dir() / f"{DESK_SCHEDULER_SYSTEMD_NAME}.service"


def _systemd_timer_path() -> Path:
    return _systemd_user_dir() / f"{DESK_SCHEDULER_SYSTEMD_NAME}.timer"


def _posix_tgcs_entry() -> Path:
    return PROJECT_ROOT / "tgcs"


def _bot_gateway_script_path() -> Path:
    return PROJECT_ROOT / "scripts" / "bot_gateway.py"


def _pythonw_entry() -> Path:
    executable = Path(sys.executable)
    if sys.platform.startswith("win") and executable.name.lower() == "python.exe":
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            return candidate
    return executable


def _fixed_monitor_argv(entry: Path) -> list[str]:
    return [
        str(entry),
        "monitor",
        "run",
        "--profile-id",
        DESK_SCHEDULER_PROFILE_ID,
        "--delivery-mode",
        "dry-run",
    ]


def _systemd_exec_path(path: Path) -> str:
    text = str(path)
    if any(char.isspace() for char in text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def _fixed_bot_gateway_argv(python_entry: Path | None = None) -> list[str]:
    return [
        str(python_entry or _pythonw_entry()),
        str(_bot_gateway_script_path()),
        "run",
        "--poll-timeout",
        str(DESK_BOT_GATEWAY_POLL_TIMEOUT_SECONDS),
    ]


def _bot_gateway_launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{DESK_BOT_GATEWAY_LAUNCHD_LABEL}.plist"


def _bot_gateway_systemd_service_path() -> Path:
    return _systemd_user_dir() / f"{DESK_BOT_GATEWAY_SYSTEMD_NAME}.service"


def _bot_gateway_background_base(backend: str) -> dict:
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
    backend = _scheduler_backend()
    base = _bot_gateway_background_base(backend)
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
        installed = _bot_gateway_launchd_plist_path().exists()
        return {
            **base,
            "installed": installed,
            "status": "installed" if installed else "not_installed",
            "can_remove": installed,
            "detail": "Bot Gateway starts at login." if installed else base["detail"],
            "next_action": "You can turn it off from Settings." if installed else base["next_action"],
        }
    if backend == "linux_systemd_user":
        installed = _bot_gateway_systemd_service_path().exists()
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
    backend = _scheduler_backend()
    base = _scheduler_base(backend)
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
        installed = _launchd_plist_path().exists()
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
        installed = _systemd_timer_path().exists()
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


def _write_launchd_plist(path: Path, entry: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": DESK_SCHEDULER_LAUNCHD_LABEL,
        "ProgramArguments": _fixed_monitor_argv(entry),
        "RunAtLoad": True,
        "StartInterval": DESK_SCHEDULER_INTERVAL_MINUTES * 60,
        "WorkingDirectory": str(PROJECT_ROOT),
        "StandardOutPath": str(PROJECT_ROOT / "output" / f"tgcs-{DESK_SCHEDULER_PROFILE_ID}.log"),
        "StandardErrorPath": str(PROJECT_ROOT / "output" / f"tgcs-{DESK_SCHEDULER_PROFILE_ID}.err.log"),
    }
    PROJECT_ROOT.joinpath("output").mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(payload, handle)


def _write_systemd_units(service_path: Path, timer_path: Path, entry: Path) -> None:
    service_path.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_ROOT.joinpath("output").mkdir(parents=True, exist_ok=True)
    exec_start = " ".join(
        [
            _systemd_exec_path(entry),
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
    backend = _scheduler_backend()
    if backend == "manual_cron_preview":
        return _scheduler_result(
            action_id,
            status="blocked",
            title="Auto scan needs a supported scheduler",
            detail="Signal Desk will not edit crontab directly. This machine can use the schedule preview or manual scans.",
            next_action="Run tgcs schedule print --platform cron for a no-side-effect crontab preview.",
        )

    tgcs_entry = PROJECT_ROOT / "tgcs.bat" if backend == "windows_schtasks" else _posix_tgcs_entry()
    if not tgcs_entry.exists():
        return _scheduler_result(
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
            return _scheduler_result(
                action_id,
                status="failed",
                title="Scheduler change timed out",
                detail="The local scheduler did not finish the requested change in time.",
                next_action="Check the local scheduler, then retry from Signal Desk.",
            )
        except OSError:
            return _scheduler_result(
                action_id,
                status="blocked",
                title="Scheduler is unavailable",
                detail="Signal Desk could not start the local scheduler command on this machine.",
                next_action="Use manual scans in Signal Desk, or install the task from the local scheduler.",
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

        failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
        return _scheduler_result(
            action_id,
            status="failed",
            title="Scheduler change failed",
            detail=failure,
            next_action="Check scheduler permissions, then retry from Signal Desk.",
            exit_code=completed.returncode,
        )

    if backend == "macos_launchd":
        plist_path = _launchd_plist_path()
        if action_id == "schedule_install_dry_run":
            _write_launchd_plist(plist_path, tgcs_entry)
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
        service_path = _systemd_service_path()
        timer_path = _systemd_timer_path()
        if action_id == "schedule_install_dry_run":
            _write_systemd_units(service_path, timer_path, tgcs_entry)
            try:
                reload_result = _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
            except (OSError, subprocess.TimeoutExpired):
                reload_result = subprocess.CompletedProcess(["systemctl"], 1, stdout="", stderr="systemctl --user daemon-reload failed")
            if reload_result.returncode != 0:
                failure = _desk_safe_result_text(reload_result.stderr, reload_result.stdout) or "systemd user daemon reload failed."
                return _scheduler_result(
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
        return _scheduler_result(
            action_id,
            status="failed",
            title="Scheduler change timed out",
            detail="The local scheduler did not finish the requested change in time.",
            next_action="Check the local scheduler, then retry from Signal Desk.",
        )
    except OSError:
        return _scheduler_result(
            action_id,
            status="blocked",
            title="Scheduler is unavailable",
            detail="Signal Desk could not start the local scheduler command on this machine.",
            next_action="Use manual scans in Signal Desk, or install the task from the local scheduler.",
        )

    if backend == "macos_launchd" and action_id == "schedule_remove_dry_run":
        _launchd_plist_path().unlink(missing_ok=True)
    if backend == "linux_systemd_user" and action_id == "schedule_remove_dry_run":
        _systemd_service_path().unlink(missing_ok=True)
        _systemd_timer_path().unlink(missing_ok=True)
        try:
            _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
        except (OSError, subprocess.TimeoutExpired):
            pass

    if completed.returncode == 0:
        return _scheduler_result(
            action_id,
            status="success",
            title=success_title,
            detail=success_detail,
            next_action=success_next,
            exit_code=completed.returncode,
        )

    failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
    return _scheduler_result(
        action_id,
        status="failed",
        title="Scheduler change failed",
        detail=failure,
        next_action="Check scheduler permissions, then retry from Signal Desk.",
        exit_code=completed.returncode,
    )


def _bot_gateway_action_result(
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


def _write_bot_gateway_launchd_plist(path: Path, python_entry: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": DESK_BOT_GATEWAY_LAUNCHD_LABEL,
        "ProgramArguments": _fixed_bot_gateway_argv(python_entry),
        "RunAtLoad": True,
        "KeepAlive": {"Crashed": True},
        "WorkingDirectory": str(PROJECT_ROOT),
        "StandardOutPath": str(output_dir / "tsense-bot-gateway.log"),
        "StandardErrorPath": str(output_dir / "tsense-bot-gateway.err.log"),
    }
    with path.open("wb") as handle:
        plistlib.dump(payload, handle)


def _write_bot_gateway_systemd_service(path: Path, python_entry: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    argv = _fixed_bot_gateway_argv(python_entry)
    exec_start = " ".join(_systemd_exec_path(Path(part)) if index < 2 else part for index, part in enumerate(argv))
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
        return _bot_gateway_action_result(
            action_id,
            status="blocked",
            title="Bot token is missing",
            detail="Save a Telegram bot token before turning on background mode.",
            next_action="Save the bot token in Settings, then turn on bot background mode.",
        )

    backend = _scheduler_backend()
    if backend == "manual_cron_preview":
        return _bot_gateway_action_result(
            action_id,
            status="blocked",
            title="Bot background mode needs a local scheduler",
            detail="Signal Desk cannot install a Bot Gateway login task on this platform.",
            next_action="Keep Signal Desk open for now, or run tgcs bot run manually.",
        )

    bot_script = _bot_gateway_script_path()
    python_entry = _pythonw_entry()
    if not bot_script.exists() or not python_entry.exists():
        return _bot_gateway_action_result(
            action_id,
            status="blocked",
            title="Bot Gateway launcher is missing",
            detail="Signal Desk could not find the local Bot Gateway runtime needed for background mode.",
            next_action="Repair the local install, then turn on bot background mode again.",
        )

    if backend == "windows_schtasks":
        if action_id == "bot_gateway_install_autostart":
            task_action = " ".join(f'"{part}"' if " " in part or "\\" in part else part for part in _fixed_bot_gateway_argv(python_entry))
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
            return _bot_gateway_action_result(
                action_id,
                status="failed",
                title="Bot background change timed out",
                detail="The local scheduler did not finish the requested change in time.",
                next_action="Check Windows Task Scheduler, then retry from Settings.",
            )
        except OSError:
            return _bot_gateway_action_result(
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
                    return _bot_gateway_action_result(
                        action_id,
                        status="failed",
                        title="Bot background mode installed but not started",
                        detail=failure,
                        next_action="Log out and back in, or open Windows Task Scheduler and start the T-Sense Bot Gateway task.",
                        exit_code=start_result.returncode,
                    )
            return _bot_gateway_action_result(
                action_id,
                status="success",
                title=success_title,
                detail=success_detail,
                next_action=success_next,
                exit_code=completed.returncode,
            )
        failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
        return _bot_gateway_action_result(
            action_id,
            status="failed",
            title="Bot background change failed",
            detail=failure,
            next_action="Check scheduler permissions, then retry from Settings.",
            exit_code=completed.returncode,
        )

    if backend == "macos_launchd":
        plist_path = _bot_gateway_launchd_plist_path()
        if action_id == "bot_gateway_install_autostart":
            _write_bot_gateway_launchd_plist(plist_path, python_entry)
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
        service_path = _bot_gateway_systemd_service_path()
        if action_id == "bot_gateway_install_autostart":
            _write_bot_gateway_systemd_service(service_path, python_entry)
            try:
                reload_result = _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
            except (OSError, subprocess.TimeoutExpired):
                reload_result = subprocess.CompletedProcess(["systemctl"], 1, stdout="", stderr="systemctl --user daemon-reload failed")
            if reload_result.returncode != 0:
                failure = _desk_safe_result_text(reload_result.stderr, reload_result.stdout) or "systemd user daemon reload failed."
                return _bot_gateway_action_result(
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
        return _bot_gateway_action_result(
            action_id,
            status="failed",
            title="Bot background change timed out",
            detail="The local scheduler did not finish the requested change in time.",
            next_action="Check the local scheduler, then retry from Settings.",
        )
    except OSError:
        return _bot_gateway_action_result(
            action_id,
            status="blocked",
            title="Local scheduler is unavailable",
            detail="Signal Desk could not start the local scheduler command on this machine.",
            next_action="Use manual bot runs until the scheduler is available.",
        )

    if backend == "macos_launchd" and action_id == "bot_gateway_remove_autostart":
        _bot_gateway_launchd_plist_path().unlink(missing_ok=True)
    if backend == "linux_systemd_user" and action_id == "bot_gateway_remove_autostart":
        _bot_gateway_systemd_service_path().unlink(missing_ok=True)
        try:
            _run_scheduler_command(["systemctl", "--user", "daemon-reload"])
        except (OSError, subprocess.TimeoutExpired):
            pass

    if completed.returncode == 0:
        return _bot_gateway_action_result(
            action_id,
            status="success",
            title=success_title,
            detail=success_detail,
            next_action=success_next,
            exit_code=completed.returncode,
        )
    failure = _desk_safe_result_text(completed.stderr, completed.stdout) or "The local scheduler rejected the change."
    return _bot_gateway_action_result(
        action_id,
        status="failed",
        title="Bot background change failed",
        detail=failure,
        next_action="Check scheduler permissions, then retry from Settings.",
        exit_code=completed.returncode,
    )


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

            health = probe_source_access(progress_callback=progress)
        except SourceAccessProbeError as exc:
            return _desk_action_result(
                action_id,
                status=exc.status,
                title="Source access check blocked",
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
                "Pause inaccessible sources, narrow to recently active sources, or run a fresh practice scan."
                if int(health.get("inaccessible_count") or 0)
                else "Quiet sources are readable. Keep them, narrow to recently active sources, or run a fresh practice scan."
                if int(health.get("quiet_count") or 0)
                else "Run a fresh practice scan."
            ),
            extra={"source_access": _source_access_action_summary(health)},
        )

    if action_id in {"sources_pause_inaccessible", "sources_keep_accessible"}:
        return apply_source_access_repair(action_id, body=body)

    if action_id in {"schedule_install_dry_run", "schedule_remove_dry_run"}:
        return run_desk_scheduler_action(action_id, body=body)

    if action_id in {"bot_gateway_install_autostart", "bot_gateway_remove_autostart"}:
        return run_bot_gateway_autostart_action(action_id, body=body)

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
    if action_id == "monitor_jobs_dry_run":
        _desk_update_action_progress(
            action_id,
            detail="Practice scan running; scanning sources, prefiltering, and generating the local report. Keep Signal Desk open.",
        )
    try:
        completed = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=desk_action_env(),
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


def dashboard_state_payload(conn) -> dict:
    snapshot = monitor_state.dashboard_snapshot(conn)
    snapshot["active_actions"] = desk_active_actions()
    health = _source_access_health_loaded()
    if not health:
        return snapshot
    setup = snapshot.get("setup_status") if isinstance(snapshot.get("setup_status"), dict) else {}
    checks = setup.get("checks") if isinstance(setup.get("checks"), list) else []
    if not checks:
        return snapshot
    detail = _source_access_health_detail(health)
    if not _source_access_health_is_fresh(health):
        detail = f"Last source access check is stale. {detail}"
    updated_checks: list[dict] = []
    for check in checks:
        if isinstance(check, dict) and check.get("check_id") == "source_access":
            updated_checks.append({**check, "detail": detail, "source_access": _source_access_action_summary(health)})
        else:
            updated_checks.append(check)
    snapshot["setup_status"] = {**setup, "checks": updated_checks}
    return snapshot


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
        try:
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            print("[dashboard] client disconnected before response completed", file=sys.stderr)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _require_post_request_integrity(self) -> None:
        if not hasattr(self, "headers"):
            return
        content_type = str(self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Signal Desk POST requests require application/json.")
        for header_name in ("Origin", "Referer"):
            header_value = str(self.headers.get(header_name) or "").strip()
            if header_value and not DashboardHandler._is_loopback_same_port_url(self, header_value):
                raise ValueError("Signal Desk POST requests must originate from the local dashboard.")

    def _is_loopback_same_port_url(self, value: str) -> bool:
        try:
            parsed = urlparse(value)
            source_port = parsed.port or (80 if parsed.scheme == "http" else 443 if parsed.scheme == "https" else None)
        except ValueError:
            return False
        if parsed.scheme != "http" or not parsed.hostname or not is_loopback_address(parsed.hostname):
            return False
        request_port = DashboardHandler._request_host_port(self)
        return request_port is None or source_port == request_port

    def _request_host_port(self) -> int | None:
        host = str(self.headers.get("Host") or "").strip() if hasattr(self, "headers") else ""
        if host:
            try:
                parsed = urlparse(f"//{host}")
                if parsed.port is not None:
                    return parsed.port
            except ValueError:
                return None
        server = getattr(self, "server", None)
        address = getattr(server, "server_address", None)
        if isinstance(address, tuple) and len(address) >= 2:
            try:
                return int(address[1])
            except (TypeError, ValueError):
                return None
        return None

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
            if parsed.path == "/api/desk/bot-gateway-status":
                DashboardHandler._require_loopback_access(self, "Bot gateway status")
                with close_after_use(self._connect()) as conn:
                    self._json(HTTPStatus.OK, {"ok": True, "bot_gateway": desk_bot_gateway_status(conn)})
                return
            if parsed.path == "/api/desk/ai-settings/status":
                DashboardHandler._require_loopback_access(self, "AI API settings status")
                self._json(HTTPStatus.OK, {"ok": True, "ai": desk_ai_settings_status()})
                return
            if parsed.path == "/api/state":
                DashboardHandler._require_loopback_access(self, "Dashboard state")
                with close_after_use(self._connect()) as conn:
                    self._json(HTTPStatus.OK, dashboard_state_payload(conn))
                return
            if parsed.path.startswith("/artifacts/"):
                DashboardHandler._require_loopback_access(self, "Report artifacts")
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
            DashboardHandler._require_post_request_integrity(self)
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
            if parsed.path == "/api/desk/bot-identity/apply":
                DashboardHandler._require_loopback_access(self, "Bot identity settings")
                self._json(HTTPStatus.OK, {"ok": True, "identity": apply_desk_bot_identity()})
                return
            if parsed.path == "/api/desk/ai-settings":
                DashboardHandler._require_loopback_access(self, "AI API settings")
                self._json(HTTPStatus.OK, {"ok": True, "ai": update_desk_ai_settings(body)})
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
                if len(parts) == 5 and parts[4] == "detect-chat-id":
                    result = detect_desk_delivery_chat_id(parts[3], body)
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
            if parsed.path == "/api/desk/sources/starter":
                DashboardHandler._require_loopback_access(self, "Starter source import")
                self._json(HTTPStatus.OK, {"ok": True, "result": import_starter_sources(body)})
                return
            if parsed.path == "/api/desk/sources/assistant":
                DashboardHandler._require_loopback_access(self, "Source assistant")
                self._json(HTTPStatus.OK, {"ok": True, "result": run_source_assistant(body)})
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
            if parsed.path.startswith("/api/desk/sources/") and parsed.path.endswith("/remove"):
                DashboardHandler._require_loopback_access(self, "Source library")
                source_id = unquote(parsed.path.removeprefix("/api/desk/sources/").removesuffix("/remove").strip("/"))
                self._json(HTTPStatus.OK, {"ok": True, "sources": remove_desk_source(source_id, body)})
                return
            if parsed.path == "/api/git/check-updates":
                DashboardHandler._require_loopback_access(self, "Git update")
                self._json(HTTPStatus.OK, {"ok": True, "git": _git_update_status(fetch=True)})
                return
            if parsed.path == "/api/git/pull-latest":
                DashboardHandler._require_loopback_access(self, "Git update")
                if body.get("confirm") is not True:
                    raise DashboardGitError("Pull latest requires explicit confirmation.")
                self._json(HTTPStatus.OK, {"ok": True, "git": _git_pull_latest()})
                return
            if parsed.path == "/api/feedback/export":
                DashboardHandler._require_loopback_access(self, "Feedback export")
                with close_after_use(self._connect()) as conn:
                    result = write_feedback_export(conn)
                self._json(HTTPStatus.OK, {"ok": True, "export": result})
                return
            if parsed.path == "/api/feedback/clear":
                DashboardHandler._require_loopback_access(self, "Feedback clear")
                with close_after_use(self._connect()) as conn:
                    result = monitor_state.clear_feedback_decisions(conn)
                self._json(HTTPStatus.OK, {"ok": True, "feedback": result})
                return
            if parsed.path == "/api/feedback/profile-suggestions":
                DashboardHandler._require_loopback_access(self, "Feedback profile suggestions")
                with close_after_use(self._connect()) as conn:
                    result = monitor_state.create_feedback_profile_patch_suggestions(conn)
                self._json(HTTPStatus.OK, {"ok": True, "suggestions": result})
                return
            if parsed.path == "/api/profiles/create":
                DashboardHandler._require_loopback_access(self, "Profile creation")
                with close_after_use(self._connect()) as conn:
                    result = create_profile_from_brief(conn, body)
                self._json(HTTPStatus.OK, {"ok": True, "profile": result})
                return
            if parsed.path.startswith("/api/review-cards/") and parsed.path.endswith("/undo"):
                DashboardHandler._require_loopback_access(self, "Review card actions")
                card_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    card = monitor_state.undo_card_action(conn, card_id=card_id)
                self._json(HTTPStatus.OK, {"ok": True, "card": card})
                return
            if parsed.path.startswith("/api/review-cards/") and parsed.path.endswith("/action"):
                DashboardHandler._require_loopback_access(self, "Review card actions")
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
            if parsed.path.startswith("/api/profiles/") and parsed.path.endswith("/draft-note"):
                DashboardHandler._require_loopback_access(self, "Profile draft note")
                unexpected = sorted(str(key) for key in body.keys() if key not in PROFILE_DRAFT_NOTE_ALLOWED_FIELDS)
                if unexpected:
                    raise ValueError(f"Unsupported profile draft field: {', '.join(unexpected)}")
                note = " ".join(str(body.get("note") or "").split())
                if not note:
                    raise ValueError("Profile note is required.")
                if len(note) > PROFILE_DRAFT_NOTE_MAX_LENGTH:
                    raise ValueError(f"Profile note must be {PROFILE_DRAFT_NOTE_MAX_LENGTH} characters or fewer.")
                note = monitor_state.require_profile_text_without_private_fragments("Profile note", note)
                profile_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    patch = monitor_state.create_profile_patch_suggestion(
                        conn,
                        profile_id=profile_id,
                        card_id=None,
                        note=note,
                        profile_path=None,
                    )
                    conn.commit()
                self._json(HTTPStatus.OK, {"ok": True, "patch": patch})
                return
            if parsed.path.startswith("/api/profiles/") and parsed.path.endswith("/matching-preferences"):
                DashboardHandler._require_loopback_access(self, "Profile matching preferences")
                unexpected = sorted(str(key) for key in body.keys() if key not in PROFILE_MATCHING_PREFERENCES_ALLOWED_FIELDS)
                if unexpected:
                    raise ValueError(f"Unsupported profile matching field: {', '.join(unexpected)}")
                preferences = str(body.get("preferences") or "").strip()
                if not preferences:
                    raise ValueError("Profile matching preferences are required.")
                if len(preferences) > PROFILE_MATCHING_PREFERENCES_MAX_LENGTH:
                    raise ValueError(f"Profile matching preferences must be {PROFILE_MATCHING_PREFERENCES_MAX_LENGTH} characters or fewer.")
                preferences = monitor_state.require_profile_text_without_private_fragments(
                    "Profile matching preferences",
                    preferences,
                )
                profile_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    patch = monitor_state.create_profile_preferences_patch_suggestion(
                        conn,
                        profile_id=profile_id,
                        preferences_text=preferences,
                    )
                    conn.commit()
                self._json(HTTPStatus.OK, {"ok": True, "patch": patch})
                return
            if parsed.path.startswith("/api/profile-patches/") and parsed.path.endswith("/apply"):
                DashboardHandler._require_loopback_access(self, "Profile patch actions")
                patch_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    result = monitor_state.apply_profile_patch(conn, patch_id=patch_id)
                self._json(HTTPStatus.OK, {"ok": True, "result": result})
                return
            if parsed.path.startswith("/api/profile-patches/") and parsed.path.endswith("/revert"):
                DashboardHandler._require_loopback_access(self, "Profile patch actions")
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
            candidate = resolve_dashboard_artifact_path(encoded_path)
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
    parser = argparse.ArgumentParser(description="Serve the local T-Sense dashboard.", allow_abbrev=False)
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
            print(f"T-Sense dashboard listening on {url}")
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
