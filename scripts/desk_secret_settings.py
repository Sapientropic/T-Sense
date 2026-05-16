"""Local notification token and AI provider key settings for Signal Desk."""

from __future__ import annotations

import os
import re
import sys
from datetime import UTC, datetime

from typing import Any

from scripts import delivery, local_credentials


DESK_NOTIFICATION_TOKEN_ALLOWED_FIELDS = {"token", "clear"}
DESK_AI_SETTINGS_ALLOWED_FIELDS = {"provider", "api_key", "clear"}
DESK_AI_PROVIDER_CONFIGS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "env_name": "OPENAI_API_KEY",
        "target": "tgcs.signal-desk.openai-api-key",
        "username": "OpenAI API key",
        "purpose": "matching",
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_name": "DEEPSEEK_API_KEY",
        "target": "tgcs.signal-desk.deepseek-api-key",
        "username": "DeepSeek API key",
        "purpose": "matching",
    },
    "minimax": {
        "label": "MiniMax",
        "env_name": "MINIMAX_TOKEN_PLAN_KEY",
        "target": "tgcs.signal-desk.minimax-token-plan-key",
        "username": "MiniMax token plan key",
        "purpose": "matching",
    },
    "xai": {
        "label": "xAI OCR",
        "env_name": "XAI_API_KEY",
        "target": "tgcs.signal-desk.xai-api-key",
        "username": "xAI API key",
        "purpose": "ocr",
    },
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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
    verification_status = (
        "env_unverified"
        if env_configured
        else "saved_unverified"
        if local_configured
        else "missing"
    )
    if env_configured:
        detail = "Telegram bot token is available from the environment, but Signal Desk has not verified it with Telegram."
    elif local_configured:
        detail = f"Telegram bot token is saved in {local_label}, but Signal Desk has not verified it with Telegram."
    elif local_supported:
        detail = "Telegram bot token is not configured."
    else:
        detail = "Local secure token storage is unavailable on this machine. Set TGCS_TELEGRAM_BOT_TOKEN instead."
    return {
        "schema_version": "desk_notification_token_status_v1",
        "configured": configured,
        "verification_status": verification_status,
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
        purpose = str(config.get("purpose") or "matching")
        if env_configured:
            source = "environment"
            detail = f"{config['label']} is available from {env_name}. Environment wins over local storage, but the key is not verified here."
        elif local_configured:
            source = local_backend
            detail = f"{config['label']} API key is saved in {local_label}, but the provider has not been tested."
        else:
            source = "missing"
            detail = f"{config['label']} API key is not configured."
        if purpose == "ocr":
            detail += " This provider is OCR-only and does not unlock AI matching."
        verification_status = (
            "env_unverified"
            if env_configured
            else "saved_unverified"
            if local_configured
            else "missing"
        )
        providers.append(
            {
                "provider": provider_id,
                "label": config["label"],
                "env_name": env_name,
                "purpose": purpose,
                "configured": configured,
                "verification_status": verification_status,
                "usable_for_matching": purpose == "matching" and configured,
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
    matching_configured_count = sum(
        1 for provider in providers if provider["configured"] and provider.get("purpose") == "matching"
    )
    ocr_configured_count = sum(
        1 for provider in providers if provider["configured"] and provider.get("purpose") == "ocr"
    )
    return {
        "schema_version": "desk_ai_settings_status_v1",
        "configured_count": configured_count,
        "matching_configured_count": matching_configured_count,
        "ocr_configured_count": ocr_configured_count,
        "local_store_supported": local_supported,
        "local_store_backend": local_backend,
        "local_store_label": local_label,
        "platform": sys.platform,
        "detail": (
            f"{matching_configured_count} matching key{'s' if matching_configured_count != 1 else ''} available"
            + (f"; {ocr_configured_count} OCR-only key{'s' if ocr_configured_count != 1 else ''} available." if ocr_configured_count else ".")
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
