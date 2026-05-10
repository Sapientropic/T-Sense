"""Delivery adapters for v0.5-alpha monitor alerts.

This module deliberately keeps outbound delivery separate from monitor state.
The monitor can dry-run delivery in tests and CI, while live Telegram Bot API
calls must be explicitly selected by the caller.  Bot tokens are resolved from
the environment first, then from the local OS credential store when available.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from scripts.item_display import display_item_title
from scripts import local_credentials


TELEGRAM_BOT_TOKEN_ENV = "TGCS_TELEGRAM_BOT_TOKEN"
TELEGRAM_BOT_TOKEN_CREDENTIAL_TARGET = "tgcs.signal-desk.telegram-bot-token"


class DeliveryError(Exception):
    """Raised when a delivery adapter cannot complete a requested live send."""


@dataclass(frozen=True)
class DeliveryAttempt:
    target_id: str
    target_type: str
    mode: str
    ok: bool
    status: str
    message_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "mode": self.mode,
            "ok": self.ok,
            "status": self.status,
            "message_id": self.message_id,
            "error": self.error,
        }


@dataclass(frozen=True)
class TelegramBotToken:
    token: str
    source: str
    updated_at: str | None = None


def resolve_telegram_bot_token(
    *,
    token_env: str = TELEGRAM_BOT_TOKEN_ENV,
    credential_target: str = TELEGRAM_BOT_TOKEN_CREDENTIAL_TARGET,
) -> TelegramBotToken:
    env_token = os.environ.get(token_env, "").strip()
    if env_token:
        return TelegramBotToken(token=env_token, source="environment")
    if not local_credentials.is_supported():
        return TelegramBotToken(token="", source="missing")
    try:
        stored = local_credentials.read_secret(credential_target)
    except local_credentials.CredentialStoreError:
        return TelegramBotToken(token="", source="credential_error")
    if stored and stored.secret.strip():
        return TelegramBotToken(
            token=stored.secret.strip(),
            source="windows_credential_manager",
            updated_at=stored.updated_at,
        )
    return TelegramBotToken(token="", source="missing")


def _clean_text(value: object, *, max_len: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "..."


def _item_title(item: dict[str, Any]) -> str:
    return display_item_title(item, fallback="Telegram signal", max_len=120)


def _source_refs(item: dict[str, Any]) -> str:
    refs = item.get("source_message_refs")
    if not isinstance(refs, list):
        return "source refs unavailable"
    rendered = []
    for ref in refs[:5]:
        if not isinstance(ref, dict):
            continue
        channel = _clean_text(ref.get("channel"), max_len=80)
        msg_id = _clean_text(ref.get("id"), max_len=40)
        if channel and msg_id:
            rendered.append(f"{channel}#{msg_id}")
    if len(refs) > 5:
        rendered.append("...")
    return ", ".join(rendered) if rendered else "source refs unavailable"


def build_telegram_alert_text(
    *,
    item: dict[str, Any],
    card: dict[str, Any] | None = None,
    report_url: str | None = None,
    dashboard_url: str | None = None,
) -> str:
    """Build a redacted Telegram alert body.

    The alert intentionally excludes raw Telegram message text.  It carries
    enough provenance to get the user back to the local report/dashboard where
    raw context can be expanded under local control.
    """

    state = item.get("decision_state") if isinstance(item.get("decision_state"), dict) else {}
    status = _clean_text(state.get("status") or "unknown", max_len=40)
    rating = _clean_text(item.get("rating") or "unknown", max_len=40)
    why = _clean_text(item.get("why") or item.get("market_impact") or "", max_len=320)
    card_id = _clean_text((card or {}).get("card_id") or "", max_len=80)

    lines = [
        f"TGCS alert: {_item_title(item)}",
        f"Rating: {rating} / State: {status}",
    ]
    if why:
        lines.append(f"Why: {why}")
    lines.append(f"Sources: {_source_refs(item)}")
    if card_id:
        lines.append(f"Card: {card_id}")
    if report_url:
        lines.append(f"Report: {report_url}")
    if dashboard_url:
        lines.append(f"Dashboard: {dashboard_url}")
    return "\n".join(lines)


def send_telegram_bot_message(
    *,
    target_id: str,
    chat_id: str,
    text: str,
    mode: str = "dry-run",
    token_env: str = TELEGRAM_BOT_TOKEN_ENV,
    timeout_seconds: int = 15,
) -> DeliveryAttempt:
    if mode not in {"dry-run", "live"}:
        raise ValueError("mode must be dry-run or live")
    if not chat_id:
        return DeliveryAttempt(
            target_id=target_id,
            target_type="telegram_bot",
            mode=mode,
            ok=False,
            status="chat_id_missing",
            error="Telegram bot chat_id is missing.",
        )
    if mode == "dry-run":
        return DeliveryAttempt(
            target_id=target_id,
            target_type="telegram_bot",
            mode=mode,
            ok=True,
            status="dry_run",
        )

    token_status = resolve_telegram_bot_token(token_env=token_env)
    if not token_status.token:
        return DeliveryAttempt(
            target_id=target_id,
            target_type="telegram_bot",
            mode=mode,
            ok=False,
            status="token_missing",
            error=f"Telegram bot token is not configured. Save it in Signal Desk Settings or set {token_env}.",
        )

    url = f"https://api.telegram.org/bot{token_status.token}/sendMessage"
    body = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return DeliveryAttempt(
            target_id=target_id,
            target_type="telegram_bot",
            mode=mode,
            ok=False,
            status="request_failed",
            error=str(exc),
        )
    except json.JSONDecodeError as exc:
        return DeliveryAttempt(
            target_id=target_id,
            target_type="telegram_bot",
            mode=mode,
            ok=False,
            status="invalid_response",
            error=str(exc),
        )

    if not payload.get("ok"):
        return DeliveryAttempt(
            target_id=target_id,
            target_type="telegram_bot",
            mode=mode,
            ok=False,
            status="bot_api_error",
            error=_clean_text(payload.get("description") or payload, max_len=500),
        )
    message = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return DeliveryAttempt(
        target_id=target_id,
        target_type="telegram_bot",
        mode=mode,
        ok=True,
        status="sent",
        message_id=str(message.get("message_id")) if message.get("message_id") is not None else None,
    )
