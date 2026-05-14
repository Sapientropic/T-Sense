"""Localhost dashboard server for the v0.5-alpha review inbox."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import socket
import sys
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
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
        desk_get_routes,
        desk_git,
        desk_http_security,
        desk_operation_routes,
        desk_profiles,
        desk_profile_post_routes,
        desk_profile_routes,
        desk_scheduler,
        desk_server_selection,
        desk_settings_routes,
        desk_source_routes,
        desk_state_payload,
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
        desk_get_routes,
        desk_git,
        desk_http_security,
        desk_operation_routes,
        desk_profiles,
        desk_profile_post_routes,
        desk_profile_routes,
        desk_scheduler,
        desk_server_selection,
        desk_settings_routes,
        desk_source_routes,
        desk_state_payload,
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
DESK_HEALTH_SCHEMA_VERSION = desk_server_selection.DESK_HEALTH_SCHEMA_VERSION
DESK_APP_ID = desk_server_selection.DESK_APP_ID
DESK_VERSION = desk_server_selection.DESK_VERSION
DESK_AUTO_PORT_END = desk_server_selection.DESK_AUTO_PORT_END
GIT_TIMEOUT_SECONDS = 25
DESK_ACTION_TIMEOUT_SECONDS = 180
DESK_SOURCE_ACCESS_HEALTH_SCHEMA_VERSION = "desk_source_access_health_v1"
DESK_SOURCE_ACCESS_PROBE_MAX_SOURCES = _positive_int_env("TGCS_SOURCE_ACCESS_PROBE_MAX_SOURCES", 80)
DESK_SOURCE_ACCESS_HEALTH_MAX_AGE_HOURS = 24
DESK_BOT_GATEWAY_STATE_FILENAME = "bot-gateway-state.json"
DESK_BOT_GATEWAY_STALE_SECONDS = 120
DESK_BOT_SUPPORTED_COMMANDS = ["/status", "/latest", "/sources", "/profiles", "/scan"]
LOOPBACK_DASHBOARD_HOSTS = desk_server_selection.LOOPBACK_DASHBOARD_HOSTS
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
DESK_DELIVERY_TARGET_ID = desk_profiles.DESK_DELIVERY_TARGET_ID
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
PROFILE_CREATE_ALLOWED_FIELDS = desk_profiles.PROFILE_CREATE_ALLOWED_FIELDS
PROFILE_CREATE_MAX_TEXT_LENGTH = desk_profiles.PROFILE_CREATE_MAX_TEXT_LENGTH
PROFILE_CREATE_MAX_BINARY_BYTES = desk_profiles.PROFILE_CREATE_MAX_BINARY_BYTES
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


DashboardServerSelection = desk_server_selection.DashboardServerSelection


def is_dashboard_report_artifact_name(name: str) -> bool:
    return desk_artifacts.is_dashboard_report_artifact_name(name)


def dashboard_host_warning(host: str) -> str | None:
    return desk_server_selection.dashboard_host_warning(host)


def _browser_host(host: str) -> str:
    return desk_server_selection.browser_host(host)


def dashboard_url(host: str, port: int) -> str:
    return desk_server_selection.dashboard_url(host, port)


def desk_health(*, host: str, port: int) -> dict:
    return desk_server_selection.desk_health(host=host, port=port)


def fetch_compatible_desk_health(host: str, port: int, *, timeout_seconds: float = 0.25) -> dict | None:
    return desk_server_selection.fetch_compatible_desk_health(
        host,
        port,
        timeout_seconds=timeout_seconds,
        socket_module=socket,
        urlopen_fn=urlopen,
        dashboard_url_fn=dashboard_url,
        browser_host_fn=_browser_host,
        is_loopback_address_fn=is_loopback_address,
    )


def is_tcp_port_listening(host: str, port: int, *, timeout_seconds: float = 0.15) -> bool:
    return desk_server_selection.is_tcp_port_listening(
        host,
        port,
        timeout_seconds=timeout_seconds,
        socket_module=socket,
        browser_host_fn=_browser_host,
    )


def select_dashboard_server(
    *,
    host: str,
    port: int,
    auto_port: bool,
    handler_cls: type[BaseHTTPRequestHandler] | None = None,
) -> DashboardServerSelection:
    if handler_cls is None:
        handler_cls = DashboardHandler
    return desk_server_selection.select_dashboard_server(
        host=host,
        port=port,
        auto_port=auto_port,
        handler_cls=handler_cls,
        server_cls=ThreadingHTTPServer,
        fetch_health_fn=fetch_compatible_desk_health,
        is_port_listening_fn=is_tcp_port_listening,
    )


def is_loopback_address(value: object) -> bool:
    return desk_server_selection.is_loopback_address(value)


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


create_profile_from_brief = desk_profiles.create_profile_from_brief
_profile_create_input_text = desk_profiles._profile_create_input_text
_profile_text_from_base64_file = desk_profiles._profile_text_from_base64_file
_profile_title_from_text = desk_profiles._profile_title_from_text
_slugify_profile_id = desk_profiles._slugify_profile_id
_unique_profile_id = desk_profiles._unique_profile_id
_profile_keywords_from_text = desk_profiles._profile_keywords_from_text
_profile_markdown_from_brief = desk_profiles._profile_markdown_from_brief
_profile_rule_lines = desk_profiles._profile_rule_lines
_profile_sentence = desk_profiles._profile_sentence
_toml_escape_inline = desk_profiles._toml_escape_inline
_toml_string = desk_profiles._toml_string
_toml_array = desk_profiles._toml_array
_append_profile_config = desk_profiles._append_profile_config


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
    # Keep this wrapper as the compatibility boundary: dashboard_server is the
    # public test/HTTP monkeypatch surface, while desk_state_payload owns the
    # product assembly logic for /api/state.
    return desk_state_payload.dashboard_state_payload(
        conn,
        dashboard_snapshot=monitor_state.dashboard_snapshot,
        active_actions=desk_active_actions,
        source_access_health_loaded=_source_access_health_loaded,
        source_access_health_detail=_source_access_health_detail,
        source_access_health_is_fresh=_source_access_health_is_fresh,
        source_access_action_summary=_source_access_action_summary,
    )


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
        desk_http_security.require_post_request_integrity(
            headers=getattr(self, "headers", None),
            server=getattr(self, "server", None),
            is_loopback_address_fn=is_loopback_address,
        )

    def _is_loopback_same_port_url(self, value: str) -> bool:
        return desk_http_security.is_loopback_same_port_url(
            value,
            request_port=DashboardHandler._request_host_port(self),
            is_loopback_address_fn=is_loopback_address,
        )

    def _request_host_port(self) -> int | None:
        return desk_http_security.request_host_port(
            headers=getattr(self, "headers", None),
            server=getattr(self, "server", None),
        )

    def _connect(self):
        return monitor_state.connect(self.db_path)

    def _require_loopback_access(self, feature: str) -> None:
        desk_http_security.require_loopback_access(
            client_address=getattr(self, "client_address", ("127.0.0.1", 0)),
            feature=feature,
            is_loopback_address_fn=is_loopback_address,
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if desk_get_routes.handle_get_route(
                self,
                parsed.path,
                require_loopback_access=DashboardHandler._require_loopback_access,
                close_after_use=close_after_use,
                desk_health=desk_health,
                desk_actions=desk_actions,
                telegram_status=telegram_status,
                desk_sources=desk_sources,
                desk_scheduler_status=desk_scheduler_status,
                desk_notification_token_status=desk_notification_token_status,
                desk_bot_gateway_status=desk_bot_gateway_status,
                desk_ai_settings_status=desk_ai_settings_status,
                dashboard_state_payload=dashboard_state_payload,
            ):
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
            if desk_settings_routes.handle_settings_post_route(
                self,
                parsed.path,
                body,
                require_loopback_access=DashboardHandler._require_loopback_access,
                close_after_use=close_after_use,
                save_telegram_credentials=save_telegram_credentials,
                telegram_send_code=telegram_send_code,
                telegram_verify_code=telegram_verify_code,
                telegram_cancel_login=telegram_cancel_login,
                update_desk_notification_token=update_desk_notification_token,
                apply_desk_bot_identity=apply_desk_bot_identity,
                update_desk_ai_settings=update_desk_ai_settings,
                save_desk_delivery_target=save_desk_delivery_target,
                test_desk_delivery_target=test_desk_delivery_target,
                detect_desk_delivery_chat_id=detect_desk_delivery_chat_id,
            ):
                return
            if desk_source_routes.handle_source_post_route(
                self,
                parsed.path,
                body,
                require_loopback_access=DashboardHandler._require_loopback_access,
                preview_desk_source_import=preview_desk_source_import,
                import_desk_sources=import_desk_sources,
                import_starter_sources=import_starter_sources,
                run_source_assistant=run_source_assistant,
                set_desk_source_enabled=set_desk_source_enabled,
                set_desk_source_topics=set_desk_source_topics,
                remove_desk_source=remove_desk_source,
            ):
                return
            if desk_operation_routes.handle_operation_post_route(
                self,
                parsed.path,
                body,
                require_loopback_access=DashboardHandler._require_loopback_access,
                close_after_use=close_after_use,
                monitor_state_module=monitor_state,
                run_desk_action=run_desk_action,
                git_update_status=_git_update_status,
                git_pull_latest=_git_pull_latest,
                git_confirmation_error=DashboardGitError,
                write_feedback_export=write_feedback_export,
            ):
                return
            if desk_profile_post_routes.handle_profile_post_route(
                self,
                parsed.path,
                body,
                require_loopback_access=DashboardHandler._require_loopback_access,
                close_after_use=close_after_use,
                monitor_state_module=monitor_state,
                profile_routes_module=desk_profile_routes,
                create_profile_from_brief=create_profile_from_brief,
                profile_enabled_allowed_fields=PROFILE_ENABLED_ALLOWED_FIELDS,
                profile_runtime_settings_allowed_fields=PROFILE_RUNTIME_SETTINGS_ALLOWED_FIELDS,
                profile_draft_note_allowed_fields=PROFILE_DRAFT_NOTE_ALLOWED_FIELDS,
                profile_draft_note_max_length=PROFILE_DRAFT_NOTE_MAX_LENGTH,
                profile_matching_preferences_allowed_fields=PROFILE_MATCHING_PREFERENCES_ALLOWED_FIELDS,
                profile_matching_preferences_max_length=PROFILE_MATCHING_PREFERENCES_MAX_LENGTH,
            ):
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
