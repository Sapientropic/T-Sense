"""Telegram app credentials and Signal Desk settings compatibility helpers."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from scripts import desk_delivery_settings, desk_secret_settings


def _positive_int_env(name: str, fallback: int) -> int:
    try:
        parsed = int(os.environ.get(name, ""))
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TELEGRAM_CONFIG_DIR = Path(
    os.environ.get("TG_SCANNER_CONFIG_DIR")
    or os.environ.get("TGCLI_CONFIG_DIR")
    or os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".config", "tgcli")
)
TELEGRAM_CONFIG_PATH = TELEGRAM_CONFIG_DIR / "config.toml"
TELEGRAM_SESSION_PATH = TELEGRAM_CONFIG_DIR / "session"
TELEGRAM_LOGIN_CODE_TTL_SECONDS = 300
TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS = desk_delivery_settings.TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS
DESK_DELIVERY_TARGET_ID = desk_delivery_settings.DESK_DELIVERY_TARGET_ID
DESK_DELIVERY_ALLOWED_FIELDS = desk_delivery_settings.DESK_DELIVERY_ALLOWED_FIELDS
DESK_DELIVERY_TEST_ALLOWED_FIELDS = desk_delivery_settings.DESK_DELIVERY_TEST_ALLOWED_FIELDS
DESK_DELIVERY_DETECT_ALLOWED_FIELDS = desk_delivery_settings.DESK_DELIVERY_DETECT_ALLOWED_FIELDS
DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS = desk_secret_settings.DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS
DESK_AI_SETTINGS_ALLOWED_FIELDS = desk_secret_settings.DESK_AI_SETTINGS_ALLOWED_FIELDS
DESK_AI_PROVIDER_CONFIGS = desk_secret_settings.DESK_AI_PROVIDER_CONFIGS
_DESK_TELEGRAM_LOGIN: dict[str, str] = {}
_DESK_TELEGRAM_LOGIN_LOCK = Lock()


def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("scripts.dashboard_server")
    return getattr(facade, name, default) if facade is not None else default


def _project_root() -> Path:
    return Path(_facade_attr("PROJECT_ROOT", PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

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
        send_code_async = _facade_attr("_telegram_send_code_async", _telegram_send_code_async)
        return asyncio.run(send_code_async(clean_phone, config_path=config_path, session_path=session_path))
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
        verify_code_async = _facade_attr("_telegram_verify_code_async", _telegram_verify_code_async)
        return asyncio.run(
            verify_code_async(clean_code, clean_password, config_path=config_path, session_path=session_path)
        )
    except ValueError:
        raise
    except Exception as exc:
        raise _telegram_interactive_error(exc, action="login") from exc


def telegram_cancel_login() -> dict:
    _telegram_login_clear()
    return telegram_status()


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
    _sync_secret_settings_context()
    return desk_secret_settings.desk_action_env()
