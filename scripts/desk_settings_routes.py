"""POST route dispatch for local Signal Desk settings mutations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote


def handle_settings_post_route(
    handler: Any,
    path: str,
    body: Mapping[str, Any],
    *,
    require_loopback_access: Callable[[Any, str], None],
    close_after_use: Callable[[Any], Any],
    save_telegram_credentials: Callable[[Any, Any], dict],
    telegram_send_code: Callable[[Any], dict],
    telegram_verify_code: Callable[[Any, Any], dict],
    telegram_cancel_login: Callable[[], dict],
    update_desk_notification_token: Callable[[Mapping[str, Any]], dict],
    apply_desk_bot_identity: Callable[[], dict],
    update_desk_ai_settings: Callable[[Mapping[str, Any]], dict],
    save_desk_delivery_target: Callable[[Any, str, Mapping[str, Any]], dict],
    test_desk_delivery_target: Callable[[Any, str, Mapping[str, Any]], dict],
    detect_desk_delivery_chat_id: Callable[[str, Mapping[str, Any]], dict],
) -> bool:
    if path == "/api/desk/telegram-credentials":
        require_loopback_access(handler, "Telegram setup")
        result = save_telegram_credentials(body.get("api_id"), body.get("api_hash"))
        handler._json(HTTPStatus.OK, {"ok": True, "telegram": result})
        return True
    if path == "/api/desk/telegram-login/send-code":
        require_loopback_access(handler, "Telegram setup")
        result = telegram_send_code(body.get("phone"))
        handler._json(HTTPStatus.OK, {"ok": True, "telegram": result})
        return True
    if path == "/api/desk/telegram-login/verify-code":
        require_loopback_access(handler, "Telegram setup")
        result = telegram_verify_code(body.get("code"), body.get("password") or "")
        handler._json(HTTPStatus.OK, {"ok": True, "telegram": result})
        return True
    if path == "/api/desk/telegram-login/cancel":
        require_loopback_access(handler, "Telegram setup")
        handler._json(HTTPStatus.OK, {"ok": True, "telegram": telegram_cancel_login()})
        return True
    if path == "/api/desk/notification-token":
        require_loopback_access(handler, "Notification token settings")
        handler._json(HTTPStatus.OK, {"ok": True, "token": update_desk_notification_token(body)})
        return True
    if path == "/api/desk/bot-identity/apply":
        require_loopback_access(handler, "Bot identity settings")
        handler._json(HTTPStatus.OK, {"ok": True, "identity": apply_desk_bot_identity()})
        return True
    if path == "/api/desk/ai-settings":
        require_loopback_access(handler, "AI API settings")
        handler._json(HTTPStatus.OK, {"ok": True, "ai": update_desk_ai_settings(body)})
        return True
    if path.startswith("/api/desk/delivery-targets/"):
        require_loopback_access(handler, "Notification settings")
        parts = [unquote(part) for part in path.strip("/").split("/")]
        if len(parts) == 4:
            with close_after_use(handler._connect()) as conn:
                target = save_desk_delivery_target(conn, parts[3], body)
            handler._json(HTTPStatus.OK, {"ok": True, "target": target})
            return True
        if len(parts) == 5 and parts[4] == "test":
            with close_after_use(handler._connect()) as conn:
                result = test_desk_delivery_target(conn, parts[3], body)
            handler._json(HTTPStatus.OK, {"ok": True, "result": result})
            return True
        if len(parts) == 5 and parts[4] == "detect-chat-id":
            result = detect_desk_delivery_chat_id(parts[3], body)
            handler._json(HTTPStatus.OK, {"ok": True, "result": result})
            return True
        raise ValueError("Unsupported notification settings path.")
    return False
