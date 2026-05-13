"""Credential, login, delivery target, and AI key helpers for Signal Desk."""

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
from urllib import error as urllib_error
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from scripts import delivery, local_credentials, monitor_state


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
TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS = 8
DESK_DELIVERY_TARGET_ID = "telegram-bot-default"
DESK_DELIVERY_ALLOWED_FIELDS = {"chat_id", "enabled"}
DESK_DELIVERY_TEST_ALLOWED_FIELDS = {"chat_id"}
DESK_DELIVERY_DETECT_ALLOWED_FIELDS: set[str] = set()
DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS = {"token", "clear"}
DESK_AI_SETTINGS_ALLOWED_FIELDS = {"provider", "api_key", "clear"}
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
        opener = _facade_attr("urlopen", urlopen)
        timeout = int(_facade_attr("TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS", TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS))
        with opener(url, timeout=timeout) as response:
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
    detect_from_bot = _facade_attr("_detect_chat_id_from_bot_updates", _detect_chat_id_from_bot_updates)
    candidate = detect_from_bot()
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
    current_user_chat_id = _facade_attr("_telegram_current_user_chat_id", _telegram_current_user_chat_id)
    current_user_id = current_user_chat_id()
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
