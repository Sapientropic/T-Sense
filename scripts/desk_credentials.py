"""Signal Desk credential/settings compatibility facade."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any

from scripts import desk_delivery_settings, desk_secret_settings, desk_telegram_login


PROJECT_ROOT = desk_telegram_login.PROJECT_ROOT
TELEGRAM_CONFIG_DIR = desk_telegram_login.TELEGRAM_CONFIG_DIR
TELEGRAM_CONFIG_PATH = desk_telegram_login.TELEGRAM_CONFIG_PATH
TELEGRAM_SESSION_PATH = desk_telegram_login.TELEGRAM_SESSION_PATH
_DEFAULT_TELEGRAM_CONFIG_DIR = TELEGRAM_CONFIG_DIR
_DEFAULT_TELEGRAM_CONFIG_PATH = TELEGRAM_CONFIG_PATH
_DEFAULT_TELEGRAM_SESSION_PATH = TELEGRAM_SESSION_PATH
TELEGRAM_LOGIN_CODE_TTL_SECONDS = desk_telegram_login.TELEGRAM_LOGIN_CODE_TTL_SECONDS
TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS = desk_delivery_settings.TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS
DESK_DELIVERY_TARGET_ID = desk_delivery_settings.DESK_DELIVERY_TARGET_ID
DESK_DELIVERY_ALLOWED_FIELDS = desk_delivery_settings.DESK_DELIVERY_ALLOWED_FIELDS
DESK_DELIVERY_TEST_ALLOWED_FIELDS = desk_delivery_settings.DESK_DELIVERY_TEST_ALLOWED_FIELDS
DESK_DELIVERY_DETECT_ALLOWED_FIELDS = desk_delivery_settings.DESK_DELIVERY_DETECT_ALLOWED_FIELDS
DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS = desk_secret_settings.DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS
DESK_AI_SETTINGS_ALLOWED_FIELDS = desk_secret_settings.DESK_AI_SETTINGS_ALLOWED_FIELDS
DESK_AI_PROVIDER_CONFIGS = desk_secret_settings.DESK_AI_PROVIDER_CONFIGS


def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("scripts.dashboard_server")
    return getattr(facade, name, default) if facade is not None else default


def _facade_or_current_attr(name: str, original_default: Any) -> Any:
    current = globals().get(name, original_default)
    facade = sys.modules.get("scripts.dashboard_server")
    facade_value = getattr(facade, name, None) if facade is not None else None
    if current is not original_default:
        return current
    if facade_value is not None:
        return facade_value
    return current


def _telegram_path_following_config_dir(
    raw_path: object,
    *,
    config_dir: Path,
    previous_dir: Path,
    previous_path: Path,
    default_dir: Path,
    default_path: Path,
    filename: str,
) -> Path:
    path = Path(raw_path)
    target_path = config_dir / filename
    if path == target_path:
        return path
    # dashboard_server exposes TELEGRAM_CONFIG_DIR plus derived path constants.
    # macOS app-state routing may patch only the dir; in that case the old
    # default config.toml/session path is stale and must continue to follow the
    # active dir. Explicit non-default path patches are left untouched.
    previous_default = previous_dir / filename
    import_default = default_dir / filename
    if (path == previous_path and previous_path == previous_default) or (
        path == default_path and default_path == import_default
    ):
        return target_path
    return path


def _sync_telegram_login_context() -> None:
    # Telegram login helpers are still reached through dashboard_server by the
    # browser routes and tests. Keep the new owner facade-aware so patches for
    # config paths, login-code TTL, and provider async hooks continue to target
    # the public surface after this split.
    global PROJECT_ROOT, TELEGRAM_CONFIG_DIR, TELEGRAM_CONFIG_PATH, TELEGRAM_SESSION_PATH, TELEGRAM_LOGIN_CODE_TTL_SECONDS
    previous_config_dir = TELEGRAM_CONFIG_DIR
    previous_config_path = TELEGRAM_CONFIG_PATH
    previous_session_path = TELEGRAM_SESSION_PATH
    project_root = Path(_facade_attr("PROJECT_ROOT", PROJECT_ROOT))
    config_dir = Path(_facade_attr("TELEGRAM_CONFIG_DIR", TELEGRAM_CONFIG_DIR))
    raw_config_path = _facade_attr("TELEGRAM_CONFIG_PATH", TELEGRAM_CONFIG_PATH)
    raw_session_path = _facade_attr("TELEGRAM_SESSION_PATH", TELEGRAM_SESSION_PATH)
    config_path = _telegram_path_following_config_dir(
        raw_config_path,
        config_dir=config_dir,
        previous_dir=previous_config_dir,
        previous_path=previous_config_path,
        default_dir=_DEFAULT_TELEGRAM_CONFIG_DIR,
        default_path=_DEFAULT_TELEGRAM_CONFIG_PATH,
        filename="config.toml",
    )
    session_path = _telegram_path_following_config_dir(
        raw_session_path,
        config_dir=config_dir,
        previous_dir=previous_config_dir,
        previous_path=previous_session_path,
        default_dir=_DEFAULT_TELEGRAM_CONFIG_DIR,
        default_path=_DEFAULT_TELEGRAM_SESSION_PATH,
        filename="session",
    )
    login_ttl = int(_facade_attr("TELEGRAM_LOGIN_CODE_TTL_SECONDS", TELEGRAM_LOGIN_CODE_TTL_SECONDS))
    PROJECT_ROOT = desk_telegram_login.PROJECT_ROOT = project_root
    TELEGRAM_CONFIG_DIR = desk_telegram_login.TELEGRAM_CONFIG_DIR = config_dir
    TELEGRAM_CONFIG_PATH = desk_telegram_login.TELEGRAM_CONFIG_PATH = config_path
    TELEGRAM_SESSION_PATH = desk_telegram_login.TELEGRAM_SESSION_PATH = session_path
    TELEGRAM_LOGIN_CODE_TTL_SECONDS = desk_telegram_login.TELEGRAM_LOGIN_CODE_TTL_SECONDS = login_ttl


def _telegram_config_path(config_path: Path | None = None) -> Path:
    return Path(config_path) if config_path is not None else desk_telegram_login.TELEGRAM_CONFIG_PATH


def _telegram_session_path(session_path: Path | None = None) -> Path:
    return Path(session_path) if session_path is not None else desk_telegram_login.TELEGRAM_SESSION_PATH


def _project_root() -> Path:
    _sync_telegram_login_context()
    return desk_telegram_login._project_root()


def _utc_now() -> str:
    _sync_telegram_login_context()
    return desk_telegram_login._utc_now()


def _display_user_path(path: Path) -> str:
    _sync_telegram_login_context()
    return desk_telegram_login._display_user_path(path)


def _load_telegram_credentials(*, config_path: Path | None = None) -> tuple[int, str]:
    _sync_telegram_login_context()
    config_path = _telegram_config_path(config_path)
    return desk_telegram_login._load_telegram_credentials(config_path=config_path)


def _telegram_credentials_ready(*, config_path: Path | None = None) -> bool:
    _sync_telegram_login_context()
    config_path = _telegram_config_path(config_path)
    return desk_telegram_login._telegram_credentials_ready(config_path=config_path)


def _telegram_session_ready(*, session_path: Path | None = None) -> bool:
    _sync_telegram_login_context()
    session_path = _telegram_session_path(session_path)
    return desk_telegram_login._telegram_session_ready(session_path=session_path)


def _telegram_login_snapshot() -> dict[str, str]:
    _sync_telegram_login_context()
    return desk_telegram_login._telegram_login_snapshot()


def _telegram_login_set(payload: dict[str, str]) -> None:
    _sync_telegram_login_context()
    desk_telegram_login._telegram_login_set(payload)


def _telegram_login_clear() -> None:
    _sync_telegram_login_context()
    desk_telegram_login._telegram_login_clear()


def _parse_utc_timestamp(value: object):
    _sync_telegram_login_context()
    return desk_telegram_login._parse_utc_timestamp(value)


def _telegram_login_expired(login: dict[str, str], *, now=None) -> bool:
    _sync_telegram_login_context()
    return desk_telegram_login._telegram_login_expired(login, now=now)


def save_telegram_credentials(
    api_id: object,
    api_hash: object,
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> dict:
    _sync_telegram_login_context()
    config_path = _telegram_config_path(config_path)
    session_path = _telegram_session_path(session_path)
    return desk_telegram_login.save_telegram_credentials(
        api_id,
        api_hash,
        config_path=config_path,
        session_path=session_path,
    )


def telegram_status(
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> dict:
    _sync_telegram_login_context()
    config_path = _telegram_config_path(config_path)
    session_path = _telegram_session_path(session_path)
    return desk_telegram_login.telegram_status(config_path=config_path, session_path=session_path)


def _telegram_interactive_error(exc: Exception, *, action: str) -> ValueError:
    _sync_telegram_login_context()
    return desk_telegram_login._telegram_interactive_error(exc, action=action)


async def _telegram_send_code_async(
    phone: str,
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> dict:
    _sync_telegram_login_context()
    config_path = _telegram_config_path(config_path)
    session_path = _telegram_session_path(session_path)
    return await desk_telegram_login._telegram_send_code_async(
        phone,
        config_path=config_path,
        session_path=session_path,
    )


async def _telegram_verify_code_async(
    code: str,
    password: str = "",
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> dict:
    _sync_telegram_login_context()
    config_path = _telegram_config_path(config_path)
    session_path = _telegram_session_path(session_path)
    return await desk_telegram_login._telegram_verify_code_async(
        code,
        password,
        config_path=config_path,
        session_path=session_path,
    )


_ORIGINAL_TELEGRAM_SEND_CODE_ASYNC = _telegram_send_code_async
_ORIGINAL_TELEGRAM_VERIFY_CODE_ASYNC = _telegram_verify_code_async


def telegram_send_code(
    phone: object,
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> dict:
    _sync_telegram_login_context()
    clean_phone = str(phone or "").strip()
    if not re.fullmatch(r"\+?[0-9][0-9 ()-]{5,24}", clean_phone):
        raise ValueError("Enter a phone number with country code.")
    config_path = _telegram_config_path(config_path)
    session_path = _telegram_session_path(session_path)
    try:
        send_code_async = _facade_or_current_attr("_telegram_send_code_async", _ORIGINAL_TELEGRAM_SEND_CODE_ASYNC)
        return asyncio.run(send_code_async(clean_phone, config_path=config_path, session_path=session_path))
    except ValueError:
        raise
    except Exception as exc:
        raise _telegram_interactive_error(exc, action="code request") from exc


def telegram_verify_code(
    code: object,
    password: object = "",
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> dict:
    _sync_telegram_login_context()
    clean_code = str(code or "").strip().replace(" ", "")
    clean_password = str(password or "")
    if not re.fullmatch(r"[0-9A-Za-z-]{3,32}", clean_code):
        raise ValueError("Enter the Telegram verification code.")
    config_path = _telegram_config_path(config_path)
    session_path = _telegram_session_path(session_path)
    try:
        verify_code_async = _facade_or_current_attr("_telegram_verify_code_async", _ORIGINAL_TELEGRAM_VERIFY_CODE_ASYNC)
        return asyncio.run(
            verify_code_async(clean_code, clean_password, config_path=config_path, session_path=session_path)
        )
    except ValueError:
        raise
    except Exception as exc:
        raise _telegram_interactive_error(exc, action="login") from exc


def telegram_cancel_login() -> dict:
    _sync_telegram_login_context()
    desk_telegram_login._telegram_login_clear()
    return desk_telegram_login.telegram_status(
        config_path=_telegram_config_path(),
        session_path=_telegram_session_path(),
    )


async def _telegram_current_user_chat_id_async(
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> str | None:
    _sync_telegram_login_context()
    config_path = _telegram_config_path(config_path)
    session_path = _telegram_session_path(session_path)
    return await desk_telegram_login._telegram_current_user_chat_id_async(
        config_path=config_path,
        session_path=session_path,
    )


def _telegram_current_user_chat_id(
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> str | None:
    _sync_telegram_login_context()
    config_path = _telegram_config_path(config_path)
    session_path = _telegram_session_path(session_path)
    return desk_telegram_login._telegram_current_user_chat_id(config_path=config_path, session_path=session_path)


def _delivery_target_projection(conn, target_id: str) -> dict:
    _sync_delivery_settings_context()
    return desk_delivery_settings._delivery_target_projection(conn, target_id)


def _validate_desk_delivery_target_id(target_id: str) -> str:
    _sync_delivery_settings_context()
    return desk_delivery_settings._validate_desk_delivery_target_id(target_id)


def _reject_unexpected_delivery_fields(body: dict, *, allowed: set[str]) -> None:
    _sync_delivery_settings_context()
    return desk_delivery_settings._reject_unexpected_delivery_fields(body, allowed=allowed)


def _clean_delivery_chat_id(value: object) -> str:
    _sync_delivery_settings_context()
    return desk_delivery_settings._clean_delivery_chat_id(value)


def save_desk_delivery_target(conn, target_id: str, body: dict) -> dict:
    _sync_delivery_settings_context()
    return desk_delivery_settings.save_desk_delivery_target(conn, target_id, body)


def test_desk_delivery_target(conn, target_id: str, body: dict) -> dict:
    _sync_delivery_settings_context()
    return desk_delivery_settings.test_desk_delivery_target(conn, target_id, body)


def _chat_candidate_from_update(update: dict) -> dict[str, str] | None:
    _sync_delivery_settings_context()
    return desk_delivery_settings._chat_candidate_from_update(update)


def _chat_candidate_from_bot_updates(payload: object) -> dict[str, str] | None:
    _sync_delivery_settings_context()
    return desk_delivery_settings._chat_candidate_from_bot_updates(payload)


def _detect_chat_id_from_bot_updates() -> dict[str, str] | None:
    _sync_delivery_settings_context()
    return desk_delivery_settings._detect_chat_id_from_bot_updates()


def detect_desk_delivery_chat_id(target_id: str, body: dict) -> dict:
    _sync_delivery_settings_context()
    return desk_delivery_settings.detect_desk_delivery_chat_id(target_id, body)


def _sync_delivery_settings_context() -> None:
    # Delivery helpers are exposed through dashboard_server for HTTP handlers,
    # tests, and local Desk integrations. Keep the new owner facade-aware so
    # patches for target ids, allowed fields, bot-update network hooks, and
    # Telegram-session fallback continue to land on the public surface.
    desk_delivery_settings.TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS = _facade_attr(
        "TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS",
        TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS,
    )
    desk_delivery_settings.DESK_DELIVERY_TARGET_ID = _facade_attr(
        "DESK_DELIVERY_TARGET_ID",
        DESK_DELIVERY_TARGET_ID,
    )
    desk_delivery_settings.DESK_DELIVERY_ALLOWED_FIELDS = _facade_attr(
        "DESK_DELIVERY_ALLOWED_FIELDS",
        DESK_DELIVERY_ALLOWED_FIELDS,
    )
    desk_delivery_settings.DESK_DELIVERY_TEST_ALLOWED_FIELDS = _facade_attr(
        "DESK_DELIVERY_TEST_ALLOWED_FIELDS",
        DESK_DELIVERY_TEST_ALLOWED_FIELDS,
    )
    desk_delivery_settings.DESK_DELIVERY_DETECT_ALLOWED_FIELDS = _facade_attr(
        "DESK_DELIVERY_DETECT_ALLOWED_FIELDS",
        DESK_DELIVERY_DETECT_ALLOWED_FIELDS,
    )
    desk_delivery_settings._utc_now = _utc_now
    desk_delivery_settings._telegram_current_user_chat_id = _telegram_current_user_chat_id


def _sync_secret_settings_context() -> None:
    # Settings secrets are called through dashboard_server in tests and in
    # local Desk actions. Keep constants facade-aware so future provider or
    # allowed-field patches do not silently target the old module after this
    # split.
    desk_secret_settings.DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS = _facade_attr(
        "DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS",
        DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS,
    )
    desk_secret_settings.DESK_AI_SETTINGS_ALLOWED_FIELDS = _facade_attr(
        "DESK_AI_SETTINGS_ALLOWED_FIELDS",
        DESK_AI_SETTINGS_ALLOWED_FIELDS,
    )
    desk_secret_settings.DESK_AI_PROVIDER_CONFIGS = _facade_attr(
        "DESK_AI_PROVIDER_CONFIGS",
        DESK_AI_PROVIDER_CONFIGS,
    )
    desk_secret_settings._utc_now = _utc_now


def _local_notification_token():
    _sync_secret_settings_context()
    return desk_secret_settings._local_notification_token()


def _local_store_backend(local_supported: bool) -> str:
    _sync_secret_settings_context()
    return desk_secret_settings._local_store_backend(local_supported)


def _local_store_label(local_supported: bool) -> str:
    _sync_secret_settings_context()
    return desk_secret_settings._local_store_label(local_supported)


def desk_notification_token_status() -> dict:
    _sync_secret_settings_context()
    return desk_secret_settings.desk_notification_token_status()


def _clean_notification_token(value: object) -> str:
    _sync_secret_settings_context()
    return desk_secret_settings._clean_notification_token(value)


def update_desk_notification_token(body: dict) -> dict:
    _sync_secret_settings_context()
    return desk_secret_settings.update_desk_notification_token(body)


def _local_ai_secret(provider_id: str):
    _sync_secret_settings_context()
    return desk_secret_settings._local_ai_secret(provider_id)


def desk_ai_settings_status() -> dict:
    _sync_secret_settings_context()
    return desk_secret_settings.desk_ai_settings_status()


def _clean_ai_provider(value: object) -> str:
    _sync_secret_settings_context()
    return desk_secret_settings._clean_ai_provider(value)


def _clean_ai_api_key(value: object) -> str:
    _sync_secret_settings_context()
    return desk_secret_settings._clean_ai_api_key(value)


def update_desk_ai_settings(body: dict) -> dict:
    _sync_secret_settings_context()
    return desk_secret_settings.update_desk_ai_settings(body)


def desk_action_env() -> dict[str, str]:
    _sync_telegram_login_context()
    _sync_secret_settings_context()
    env = desk_secret_settings.desk_action_env()
    telegram_dir = str(desk_telegram_login.TELEGRAM_CONFIG_DIR)
    # Desk actions run doctor/monitor in subprocesses. They must inherit the
    # same Telegram config root as the browser setup flow, especially after the
    # macOS app moves mutable state into its app-owned data directory.
    env["TG_SCANNER_CONFIG_DIR"] = telegram_dir
    env["TGCLI_CONFIG_DIR"] = telegram_dir
    return env
