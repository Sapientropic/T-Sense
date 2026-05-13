"""Localhost dashboard server for the v0.5-alpha review inbox."""

from __future__ import annotations

import argparse
import base64
import io
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import subprocess
import socket
import sys
import tomllib
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib import error as urllib_error
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

def _positive_int_env(name: str, fallback: int) -> int:
    try:
        parsed = int(os.environ.get(name, ""))
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


try:
    from scripts import (
        agent_cli,
        desk_actions as _desk_actions_module,
        delivery as delivery,
        desk_artifacts,
        desk_credentials,
        desk_git,
        desk_scheduler,
        desk_sources as _desk_sources_module,
        local_credentials as local_credentials,
        monitor_state,
        report as report,
        source_registry as source_registry,
    )
    from scripts.dashboard_markdown import (  # noqa: F401
        REPORT_HTML_MOBILE_PATCH,
        markdown_blocks_html,
        markdown_inline_html,
        markdown_table_html,
        render_html_report_artifact,
        render_markdown_artifact,
    )
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import (
        agent_cli,
        desk_actions as _desk_actions_module,
        delivery as delivery,
        desk_artifacts,
        desk_credentials,
        desk_git,
        desk_scheduler,
        desk_sources as _desk_sources_module,
        local_credentials as local_credentials,
        monitor_state,
        report as report,
        source_registry as source_registry,
    )
    from scripts.dashboard_markdown import (  # noqa: F401
        REPORT_HTML_MOBILE_PATCH,
        markdown_blocks_html,
        markdown_inline_html,
        markdown_table_html,
        render_html_report_artifact,
        render_markdown_artifact,
    )


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
PROFILE_RUNTIME_SETTINGS_ALLOWED_FIELDS = set(monitor_state.PROFILE_RUNTIME_SETTINGS_ALLOWED)
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

_DESK_ACTION_LOCKS = _desk_actions_module._DESK_ACTION_LOCKS
_DESK_ACTION_LOCKS_GUARD = _desk_actions_module._DESK_ACTION_LOCKS_GUARD
_DESK_LONG_RUNNING_ACTIONS = _desk_actions_module._DESK_LONG_RUNNING_ACTIONS
_DESK_ACTIVE_ACTIONS = _desk_actions_module._DESK_ACTIVE_ACTIONS
_DESK_ACTIVE_ACTIONS_GUARD = _desk_actions_module._DESK_ACTIVE_ACTIONS_GUARD
DESK_ACTIONS = _desk_actions_module.DESK_ACTIONS
DESK_ACTION_BY_ID = _desk_actions_module.DESK_ACTION_BY_ID
desk_actions = _desk_actions_module.desk_actions
_desk_display_path = _desk_actions_module._desk_display_path
_desk_payload_from_stdout = _desk_actions_module._desk_payload_from_stdout
_desk_artifact_path = _desk_actions_module._desk_artifact_path
_desk_success_detail = _desk_actions_module._desk_success_detail
_desk_action_success_copy = _desk_actions_module._desk_action_success_copy
_desk_failure_detail = _desk_actions_module._desk_failure_detail
_desk_safe_result_text = _desk_actions_module._desk_safe_result_text
_desk_action_result = _desk_actions_module._desk_action_result
_desk_action_lock = _desk_actions_module._desk_action_lock
_desk_mark_action_started = _desk_actions_module._desk_mark_action_started
_desk_update_action_progress = _desk_actions_module._desk_update_action_progress
_desk_mark_action_finished = _desk_actions_module._desk_mark_action_finished
desk_active_actions = _desk_actions_module.desk_active_actions
run_desk_action = _desk_actions_module.run_desk_action
_run_desk_action_unlocked = _desk_actions_module._run_desk_action_unlocked
DashboardGitError = desk_git.DashboardGitError
DashboardArtifactError = desk_artifacts.DashboardArtifactError


DashboardDeskActionError = desk_scheduler.DashboardDeskActionError

SourceAccessProbeError = _desk_sources_module.SourceAccessProbeError


@dataclass(frozen=True)
class DashboardServerSelection:
    url: str
    port: int
    server: ThreadingHTTPServer | None
    reused_existing: bool = False




def is_dashboard_report_artifact_name(name: str) -> bool:
    return desk_artifacts.is_dashboard_report_artifact_name(name)


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
    return desk_git.run_git(args, project_root=PROJECT_ROOT, timeout=timeout, subprocess_module=subprocess)


def _git_value(args: list[str]) -> str | None:
    return desk_git.git_value(args, run_git_fn=_run_git)


def _repo_web_url(remote_url: str | None) -> str | None:
    return desk_git.repo_web_url(remote_url)


def _git_update_status(*, fetch: bool) -> dict:
    return desk_git.git_update_status(
        fetch=fetch,
        git_value_fn=_git_value,
        run_git_fn=_run_git,
        safe_result_text_fn=_desk_safe_result_text,
        utc_now_fn=_utc_now,
    )


def _git_pull_latest() -> dict:
    return desk_git.git_pull_latest(git_update_status_fn=_git_update_status, run_git_fn=_run_git)


def resolve_run_artifact_path(requested_path: str, *, artifact_root: Path | None = None) -> Path:
    return desk_artifacts.resolve_run_artifact_path(
        requested_path,
        project_root=PROJECT_ROOT,
        artifact_root=artifact_root,
    )


def is_dashboard_openable_artifact_path(path: str) -> bool:
    return desk_artifacts.is_dashboard_openable_artifact_path(path)


def resolve_dashboard_artifact_path(requested_path: str, *, artifact_root: Path | None = None) -> Path:
    return desk_artifacts.resolve_dashboard_artifact_path(
        requested_path,
        project_root=PROJECT_ROOT,
        artifact_root=artifact_root,
    )


def dashboard_relative_path(path: Path) -> str:
    return desk_artifacts.dashboard_relative_path(path, project_root=PROJECT_ROOT)


def dashboard_feedback_export_target(output_path: Path | None = None) -> Path:
    return desk_artifacts.dashboard_feedback_export_target(output_path, project_root=PROJECT_ROOT)


def write_feedback_export(conn, *, output_path: Path | None = None) -> dict:
    return desk_artifacts.write_feedback_export(
        conn,
        project_root=PROJECT_ROOT,
        monitor_state_module=monitor_state,
        output_path=output_path,
    )



_display_user_path = desk_credentials._display_user_path
_load_telegram_credentials = desk_credentials._load_telegram_credentials
_telegram_credentials_ready = desk_credentials._telegram_credentials_ready
_telegram_session_ready = desk_credentials._telegram_session_ready
_telegram_login_snapshot = desk_credentials._telegram_login_snapshot
_telegram_login_set = desk_credentials._telegram_login_set
_telegram_login_clear = desk_credentials._telegram_login_clear
_parse_utc_timestamp = desk_credentials._parse_utc_timestamp
_telegram_login_expired = desk_credentials._telegram_login_expired
save_telegram_credentials = desk_credentials.save_telegram_credentials
telegram_status = desk_credentials.telegram_status
_telegram_interactive_error = desk_credentials._telegram_interactive_error
_telegram_send_code_async = desk_credentials._telegram_send_code_async
_telegram_verify_code_async = desk_credentials._telegram_verify_code_async
telegram_send_code = desk_credentials.telegram_send_code
telegram_verify_code = desk_credentials.telegram_verify_code
telegram_cancel_login = desk_credentials.telegram_cancel_login
_delivery_target_projection = desk_credentials._delivery_target_projection
_validate_desk_delivery_target_id = desk_credentials._validate_desk_delivery_target_id
_reject_unexpected_delivery_fields = desk_credentials._reject_unexpected_delivery_fields
_clean_delivery_chat_id = desk_credentials._clean_delivery_chat_id
save_desk_delivery_target = desk_credentials.save_desk_delivery_target
test_desk_delivery_target = desk_credentials.test_desk_delivery_target
_chat_candidate_from_update = desk_credentials._chat_candidate_from_update
_chat_candidate_from_bot_updates = desk_credentials._chat_candidate_from_bot_updates
_detect_chat_id_from_bot_updates = desk_credentials._detect_chat_id_from_bot_updates
_telegram_current_user_chat_id_async = desk_credentials._telegram_current_user_chat_id_async
_telegram_current_user_chat_id = desk_credentials._telegram_current_user_chat_id
detect_desk_delivery_chat_id = desk_credentials.detect_desk_delivery_chat_id
_local_notification_token = desk_credentials._local_notification_token
_local_store_backend = desk_credentials._local_store_backend
_local_store_label = desk_credentials._local_store_label
desk_notification_token_status = desk_credentials.desk_notification_token_status
_clean_notification_token = desk_credentials._clean_notification_token
update_desk_notification_token = desk_credentials.update_desk_notification_token
_local_ai_secret = desk_credentials._local_ai_secret
desk_ai_settings_status = desk_credentials.desk_ai_settings_status
_clean_ai_provider = desk_credentials._clean_ai_provider
_clean_ai_api_key = desk_credentials._clean_ai_api_key
update_desk_ai_settings = desk_credentials.update_desk_ai_settings
desk_action_env = desk_credentials.desk_action_env


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


def _sync_desk_scheduler_context() -> None:
    # Scheduler helpers live in a smaller module, but dashboard_server remains
    # the public monkeypatch surface for tests and local callers. Sync the
    # mutable dependencies at wrapper call time so patches to PROJECT_ROOT,
    # shutil, token status, or _run_scheduler_command keep their old effect.
    desk_scheduler.PROJECT_ROOT = PROJECT_ROOT
    desk_scheduler.DESK_BOT_GATEWAY_STATE_FILENAME = DESK_BOT_GATEWAY_STATE_FILENAME
    desk_scheduler.DESK_BOT_GATEWAY_STALE_SECONDS = DESK_BOT_GATEWAY_STALE_SECONDS
    desk_scheduler.DESK_BOT_SUPPORTED_COMMANDS = DESK_BOT_SUPPORTED_COMMANDS
    desk_scheduler.DESK_SCHEDULER_PROFILE_ID = DESK_SCHEDULER_PROFILE_ID
    desk_scheduler.DESK_SCHEDULER_INTERVAL_MINUTES = DESK_SCHEDULER_INTERVAL_MINUTES
    desk_scheduler.DESK_SCHEDULER_TASK_NAME = DESK_SCHEDULER_TASK_NAME
    desk_scheduler.DESK_SCHEDULER_LAUNCHD_LABEL = DESK_SCHEDULER_LAUNCHD_LABEL
    desk_scheduler.DESK_SCHEDULER_SYSTEMD_NAME = DESK_SCHEDULER_SYSTEMD_NAME
    desk_scheduler.DESK_BOT_GATEWAY_TASK_NAME = DESK_BOT_GATEWAY_TASK_NAME
    desk_scheduler.DESK_BOT_GATEWAY_LAUNCHD_LABEL = DESK_BOT_GATEWAY_LAUNCHD_LABEL
    desk_scheduler.DESK_BOT_GATEWAY_SYSTEMD_NAME = DESK_BOT_GATEWAY_SYSTEMD_NAME
    desk_scheduler.DESK_BOT_GATEWAY_POLL_TIMEOUT_SECONDS = DESK_BOT_GATEWAY_POLL_TIMEOUT_SECONDS
    desk_scheduler.DESK_ACTION_BY_ID = DESK_ACTION_BY_ID
    desk_scheduler.shutil = shutil
    desk_scheduler._utc_now = _utc_now
    desk_scheduler._desk_safe_result_text = _desk_safe_result_text
    desk_scheduler._parse_utc_timestamp = _parse_utc_timestamp
    desk_scheduler._enabled_telegram_bot_target_count = _enabled_telegram_bot_target_count
    desk_scheduler.desk_notification_token_status = desk_notification_token_status
    desk_scheduler._run_scheduler_command = _run_scheduler_command
    if globals().get("_ORIGINAL_PYTHONW_ENTRY_WRAPPER") is not None and _pythonw_entry is not _ORIGINAL_PYTHONW_ENTRY_WRAPPER:
        desk_scheduler.pythonw_entry = _pythonw_entry
    else:
        desk_scheduler.pythonw_entry = desk_scheduler._DEFAULT_PYTHONW_ENTRY


def _load_bot_gateway_state() -> dict[str, object]:
    _sync_desk_scheduler_context()
    return desk_scheduler.load_bot_gateway_state()


def desk_bot_gateway_status(conn, *, now: datetime | None = None) -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.desk_bot_gateway_status(conn, now=now)


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





_reject_unexpected_source_fields = _desk_sources_module._reject_unexpected_source_fields
_reject_unexpected_source_starter_fields = _desk_sources_module._reject_unexpected_source_starter_fields
_reject_unexpected_source_assistant_fields = _desk_sources_module._reject_unexpected_source_assistant_fields
_clean_source_topic = _desk_sources_module._clean_source_topic
_source_import_payload = _desk_sources_module._source_import_payload
_source_operation_payload = _desk_sources_module._source_operation_payload
_desk_source_record = _desk_sources_module._desk_source_record
desk_sources = _desk_sources_module.desk_sources
_validate_desk_source_id = _desk_sources_module._validate_desk_source_id
set_desk_source_enabled = _desk_sources_module.set_desk_source_enabled
_clean_source_topics = _desk_sources_module._clean_source_topics
set_desk_source_topics = _desk_sources_module.set_desk_source_topics
remove_desk_source = _desk_sources_module.remove_desk_source
source_access_health_path = _desk_sources_module.source_access_health_path
_source_access_health_loaded = _desk_sources_module._source_access_health_loaded
_write_source_access_health = _desk_sources_module._write_source_access_health
_source_access_checked_at = _desk_sources_module._source_access_checked_at
_source_access_health_is_fresh = _desk_sources_module._source_access_health_is_fresh
_source_access_reason_label = _desk_sources_module._source_access_reason_label
_source_access_health_detail = _desk_sources_module._source_access_health_detail
_source_access_action_summary = _desk_sources_module._source_access_action_summary
_source_access_record_base = _desk_sources_module._source_access_record_base
_source_access_error_reason = _desk_sources_module._source_access_error_reason
_source_access_failure_record = _desk_sources_module._source_access_failure_record
_resolve_probe_entity = _desk_sources_module._resolve_probe_entity
_message_datetime = _desk_sources_module._message_datetime
_probe_one_source_access = _desk_sources_module._probe_one_source_access
_source_access_summary = _desk_sources_module._source_access_summary
_probe_source_access_async = _desk_sources_module._probe_source_access_async
probe_source_access = _desk_sources_module.probe_source_access
_require_confirm_only = _desk_sources_module._require_confirm_only
_source_access_target_ids = _desk_sources_module._source_access_target_ids
_disable_sources_from_access_health = _desk_sources_module._disable_sources_from_access_health
apply_source_access_repair = _desk_sources_module.apply_source_access_repair
_desk_sources_from_body = _desk_sources_module._desk_sources_from_body
import_starter_sources = _desk_sources_module.import_starter_sources
preview_desk_source_import = _desk_sources_module.preview_desk_source_import
import_desk_sources = _desk_sources_module.import_desk_sources
_extract_source_channels_from_text = _desk_sources_module._extract_source_channels_from_text
_source_id_from_channel = _desk_sources_module._source_id_from_channel
_source_assistant_action = _desk_sources_module._source_assistant_action
_source_assistant_plan = _desk_sources_module._source_assistant_plan
_source_assistant_has_plan = _desk_sources_module._source_assistant_has_plan
_source_assistant_requested_existing_actions = _desk_sources_module._source_assistant_requested_existing_actions
_source_assistant_should_use_llm_plan = _desk_sources_module._source_assistant_should_use_llm_plan
_dedupe_source_ids = _desk_sources_module._dedupe_source_ids
_dedupe_source_channels = _desk_sources_module._dedupe_source_channels
_clean_resolved_source_plan = _desk_sources_module._clean_resolved_source_plan
_source_assistant_llm_plan = _desk_sources_module._source_assistant_llm_plan
run_source_assistant = _desk_sources_module.run_source_assistant
apply_source_assistant_resolved_plan = _desk_sources_module.apply_source_assistant_resolved_plan


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




















def _scheduler_result(
    action_id: str,
    *,
    status: str,
    title: str,
    detail: str,
    next_action: str,
    exit_code: int | None = None,
) -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.scheduler_result(
        action_id,
        status=status,
        title=title,
        detail=detail,
        next_action=next_action,
        exit_code=exit_code,
    )


def _run_scheduler_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    _sync_desk_scheduler_context()
    return desk_scheduler.run_scheduler_command(args)


def _scheduler_backend() -> str:
    _sync_desk_scheduler_context()
    return desk_scheduler.scheduler_backend()


def _scheduler_base(backend: str) -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.scheduler_base(backend)


def _launchd_plist_path() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.launchd_plist_path()


def _systemd_user_dir() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.systemd_user_dir()


def _systemd_service_path() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.systemd_service_path()


def _systemd_timer_path() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.systemd_timer_path()


def _posix_tgcs_entry() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.posix_tgcs_entry()


def _bot_gateway_script_path() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.bot_gateway_script_path()


def _pythonw_entry() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.pythonw_entry()


_ORIGINAL_PYTHONW_ENTRY_WRAPPER = _pythonw_entry


def _fixed_monitor_argv(entry: Path) -> list[str]:
    _sync_desk_scheduler_context()
    return desk_scheduler.fixed_monitor_argv(entry)


def _systemd_exec_path(path: Path) -> str:
    _sync_desk_scheduler_context()
    return desk_scheduler.systemd_exec_path(path)


def _fixed_bot_gateway_argv(python_entry: Path | None = None) -> list[str]:
    _sync_desk_scheduler_context()
    return desk_scheduler.fixed_bot_gateway_argv(python_entry)


def _bot_gateway_launchd_plist_path() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.bot_gateway_launchd_plist_path()


def _bot_gateway_systemd_service_path() -> Path:
    _sync_desk_scheduler_context()
    return desk_scheduler.bot_gateway_systemd_service_path()


def _bot_gateway_background_base(backend: str) -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.bot_gateway_background_base(backend)


def desk_bot_gateway_background_status(*, token_configured: bool | None = None) -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.desk_bot_gateway_background_status(token_configured=token_configured)


def desk_scheduler_status() -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.desk_scheduler_status()


def _write_launchd_plist(path: Path, entry: Path) -> None:
    _sync_desk_scheduler_context()
    desk_scheduler.write_launchd_plist(path, entry)


def _write_systemd_units(service_path: Path, timer_path: Path, entry: Path) -> None:
    _sync_desk_scheduler_context()
    desk_scheduler.write_systemd_units(service_path, timer_path, entry)


def run_desk_scheduler_action(action_id: str, *, body: dict | None = None) -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.run_desk_scheduler_action(action_id, body=body)


def _bot_gateway_action_result(
    action_id: str,
    *,
    status: str,
    title: str,
    detail: str,
    next_action: str,
    exit_code: int | None = None,
) -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.bot_gateway_action_result(
        action_id,
        status=status,
        title=title,
        detail=detail,
        next_action=next_action,
        exit_code=exit_code,
    )


def _write_bot_gateway_launchd_plist(path: Path, python_entry: Path) -> None:
    _sync_desk_scheduler_context()
    desk_scheduler.write_bot_gateway_launchd_plist(path, python_entry)


def _write_bot_gateway_systemd_service(path: Path, python_entry: Path) -> None:
    _sync_desk_scheduler_context()
    desk_scheduler.write_bot_gateway_systemd_service(path, python_entry)


def run_bot_gateway_autostart_action(action_id: str, *, body: dict | None = None) -> dict:
    _sync_desk_scheduler_context()
    return desk_scheduler.run_bot_gateway_autostart_action(action_id, body=body)
















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
            if parsed.path.startswith("/api/profile-patches/") and parsed.path.endswith("/replay"):
                DashboardHandler._require_loopback_access(self, "Profile patch actions")
                patch_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    result = monitor_state.replay_profile_patch(conn, patch_id=patch_id)
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
