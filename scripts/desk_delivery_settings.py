"""Delivery target settings and chat detection helpers for Signal Desk."""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib import error as urllib_error
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from scripts import delivery, desk_profiles, monitor_state


TELEGRAM_BOT_UPDATES_TIMEOUT_SECONDS = 8
DESK_DELIVERY_TARGET_ID = desk_profiles.DESK_DELIVERY_TARGET_ID
DESK_DELIVERY_ALLOWED_FIELDS = {"chat_id", "enabled"}
DESK_DELIVERY_TEST_ALLOWED_FIELDS = {"chat_id"}
DESK_DELIVERY_DETECT_ALLOWED_FIELDS: set[str] = set()


def _facade_attr(name: str, default):
    facade = sys.modules.get("scripts.dashboard_server")
    return getattr(facade, name, default) if facade is not None else default


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _desk_delivery_target_id() -> str:
    return str(_facade_attr("DESK_DELIVERY_TARGET_ID", DESK_DELIVERY_TARGET_ID) or DESK_DELIVERY_TARGET_ID)


def _delivery_target_projection(conn, target_id: str) -> dict:
    row = conn.execute("SELECT * FROM delivery_targets WHERE target_id = ?", (target_id,)).fetchone()
    if not row:
        raise ValueError("Notification target is not saved yet.")
    return monitor_state.delivery_target_from_row(row)


def _validate_desk_delivery_target_id(target_id: str) -> str:
    clean = str(target_id or "").strip()
    if clean != _desk_delivery_target_id():
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


def _telegram_current_user_chat_id_from_credentials(
    *,
    config_path: Path | None = None,
    session_path: Path | None = None,
) -> str | None:
    try:
        from scripts import desk_credentials

        kwargs = {}
        if config_path is not None:
            kwargs["config_path"] = config_path
        if session_path is not None:
            kwargs["session_path"] = session_path
        return desk_credentials._telegram_current_user_chat_id(**kwargs)
    except Exception:
        return None


_telegram_current_user_chat_id = _telegram_current_user_chat_id_from_credentials


def detect_desk_delivery_chat_id(target_id: str, body: dict) -> dict:
    clean_target_id = _validate_desk_delivery_target_id(target_id)
    _reject_unexpected_delivery_fields(body, allowed=DESK_DELIVERY_DETECT_ALLOWED_FIELDS)
    # dashboard_server is the public patch surface for tests and local Desk
    # integrations. Look up these hooks lazily so the split owner does not
    # strand existing monkeypatches on the old desk_credentials module.
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
