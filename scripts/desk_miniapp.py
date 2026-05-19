"""Telegram Mini App review surface helpers.

The Mini App is a companion review UI. It reads already-generated local review
cards and writes only the same allowlisted review actions as Signal Desk.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

try:
    from scripts import delivery, desk_artifacts, desk_http_security, desk_source_registry, monitor_state, source_registry
    from scripts.bot_state import allowed_chat_ids, clean_chat_id
except ModuleNotFoundError:
    import sys

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts import delivery, desk_artifacts, desk_http_security, desk_source_registry, monitor_state, source_registry
    from scripts.bot_state import allowed_chat_ids, clean_chat_id


MINIAPP_AUTH_SCHEMA_VERSION = "telegram_miniapp_auth_v1"
MINIAPP_REVIEW_STATE_SCHEMA_VERSION = "miniapp_review_state_v1"
MINIAPP_LEARNING_SUMMARY_SCHEMA_VERSION = "miniapp_learning_summary_v1"
MINIAPP_SOURCE_RECOMMENDATION_SCHEMA_VERSION = "miniapp_source_recommendation_v1"
MINIAPP_INIT_DATA_HEADER = "X-Telegram-Init-Data"
MINIAPP_AUTH_MAX_AGE_SECONDS = 24 * 60 * 60
MINIAPP_AUTH_FUTURE_SKEW_SECONDS = 60
MINIAPP_INIT_DATA_MAX_LENGTH = 8192
MINIAPP_SOURCE_EXCERPT_MAX_LENGTH = 600
_MINIAPP_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_MINIAPP_SOURCE_PREFIX_RE = re.compile(
    r"^(?:(?:original|source)\s+(?:post|text|message)|post)\s*[:：-]\s*",
    re.IGNORECASE,
)


def telegram_init_data_from_headers(headers: Any) -> str:
    value = str(headers.get(MINIAPP_INIT_DATA_HEADER) or "").strip() if headers is not None else ""
    if not value and headers is not None:
        authorization = str(headers.get("Authorization") or "").strip()
        lower = authorization.lower()
        if lower.startswith("tma "):
            value = authorization[4:].strip()
    if len(value) > MINIAPP_INIT_DATA_MAX_LENGTH:
        raise ValueError("Telegram Mini App init data is too large.")
    return value


def validate_telegram_init_data(
    init_data: str,
    *,
    bot_token: str,
    now: int | None = None,
    max_age_seconds: int = MINIAPP_AUTH_MAX_AGE_SECONDS,
) -> dict[str, str]:
    if not bot_token:
        raise ValueError("Telegram bot token is not configured.")
    pairs = parse_qsl(str(init_data or ""), keep_blank_values=True, strict_parsing=True)
    if not pairs:
        raise ValueError("Telegram Mini App init data is required.")
    values: dict[str, str] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("Telegram Mini App init data contains duplicate fields.")
        values[key] = value
    received_hash = values.pop("hash", "")
    if len(received_hash) != 64:
        raise ValueError("Telegram Mini App init data signature is missing.")
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Telegram Mini App init data signature is invalid.")
    auth_date = _parse_auth_date(values.get("auth_date"))
    current = int(now if now is not None else time.time())
    if auth_date > current + MINIAPP_AUTH_FUTURE_SKEW_SECONDS:
        raise ValueError("Telegram Mini App init data auth date is in the future.")
    if current - auth_date > max_age_seconds:
        raise ValueError("Telegram Mini App init data is expired.")
    user = _parse_init_data_user(values.get("user"))
    chat = _parse_init_data_user(values.get("chat"))
    user_id = clean_chat_id(user.get("id"))
    chat_id = clean_chat_id(chat.get("id"))
    if not user_id and not chat_id:
        raise ValueError("Telegram Mini App init data does not identify a user.")
    return {
        "schema_version": MINIAPP_AUTH_SCHEMA_VERSION,
        "source": "telegram",
        "user_id": user_id,
        "chat_id": chat_id,
        "auth_date": str(auth_date),
        "query_id": values.get("query_id", ""),
    }


def authorize_miniapp_request(
    handler: Any,
    *,
    is_loopback_address_fn,
    token_loader=None,
    allowed_chat_ids_fn=None,
    allow_loopback_preview: bool = True,
) -> dict[str, str]:
    init_data = telegram_init_data_from_headers(getattr(handler, "headers", None))
    client_host = _client_host(handler)
    if not init_data:
        if allow_loopback_preview and is_loopback_address_fn(client_host) and not desk_http_security.has_forwarded_remote_client(
            getattr(handler, "headers", None),
            is_loopback_address_fn,
        ):
            return {"schema_version": MINIAPP_AUTH_SCHEMA_VERSION, "source": "loopback_preview"}
        raise ValueError("Telegram Mini App init data is required.")
    loader = token_loader or _load_bot_token
    auth = validate_telegram_init_data(init_data, bot_token=loader())
    allowed_loader = allowed_chat_ids_fn or allowed_chat_ids
    allowed = allowed_loader(handler.db_path)
    identities = {value for value in (auth.get("user_id"), auth.get("chat_id")) if value}
    if not allowed:
        raise ValueError("Telegram Mini App user is not authorized. Save the bot chat in Signal Desk Settings first.")
    if not identities.intersection(allowed):
        raise ValueError("Telegram Mini App user is not authorized.")
    return auth


def miniapp_state(conn, *, auth: dict[str, str] | None = None) -> dict[str, Any]:
    snapshot = monitor_state.dashboard_snapshot(conn)
    include_report_path = bool(auth and auth.get("source") == "loopback_preview" and not auth.get("miniapp_only"))
    cards = [
        miniapp_card(card, include_report_path=include_report_path)
        for card in snapshot.get("inbox") or []
        if isinstance(card, dict)
    ]
    return {
        "schema_version": MINIAPP_REVIEW_STATE_SCHEMA_VERSION,
        "auth": _safe_auth(auth),
        "generated_at": monitor_state.utc_now(),
        "cards": cards,
        "setup_status": _miniapp_setup_status(snapshot.get("setup_status")),
        "learning_summary": _miniapp_learning_summary(snapshot.get("feedback_summary")),
        "source_recommendations": miniapp_source_recommendations(),
    }


def miniapp_card(card: dict[str, Any], *, include_report_path: bool = False) -> dict[str, Any]:
    item = card.get("item") if isinstance(card.get("item"), dict) else {}
    return {
        "schema_version": "review_card_v1",
        "card_id": str(card.get("card_id") or ""),
        "profile_id": str(card.get("profile_id") or ""),
        "title": str(card.get("title") or "Review card"),
        "rating": str(card.get("rating") or ""),
        "decision_status": str(card.get("decision_status") or ""),
        "source_refs": [_miniapp_source_ref(ref) for ref in card.get("source_refs") or [] if isinstance(ref, dict)],
        "item": _miniapp_item(item),
        "status": str(card.get("status") or "pending"),
        "opportunity_status": str(card.get("opportunity_status") or "open"),
        "opportunity_updated_at": str(card.get("opportunity_updated_at") or ""),
        "alert_summary": _miniapp_alert_summary(card.get("alert_summary")),
        "report_path": _safe_relative_report_path(card.get("report_path")) if include_report_path else "",
        "updated_at": str(card.get("updated_at") or ""),
    }


def _parse_auth_date(value: object) -> int:
    try:
        auth_date = int(str(value or ""))
    except ValueError as exc:
        raise ValueError("Telegram Mini App init data auth date is invalid.") from exc
    if auth_date <= 0:
        raise ValueError("Telegram Mini App init data auth date is invalid.")
    return auth_date


def _parse_init_data_user(value: object) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Telegram Mini App init data user payload is invalid.") from exc
    return payload if isinstance(payload, dict) else {}


def _load_bot_token() -> str:
    return delivery.resolve_telegram_bot_token().token


def _client_host(handler: Any) -> object:
    client_address = getattr(handler, "client_address", ("127.0.0.1", 0))
    return client_address[0] if isinstance(client_address, tuple) and client_address else "127.0.0.1"


def _safe_auth(auth: dict[str, str] | None) -> dict[str, str]:
    if not auth:
        return {"schema_version": MINIAPP_AUTH_SCHEMA_VERSION, "source": "unknown"}
    result = {
        "schema_version": MINIAPP_AUTH_SCHEMA_VERSION,
        "source": str(auth.get("source") or "unknown"),
    }
    if auth.get("user_id"):
        result["user_id"] = str(auth["user_id"])
    return result


def _miniapp_source_ref(ref: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "channel": str(ref.get("channel") or ""),
        "id": ref.get("id") if isinstance(ref.get("id"), (int, str)) else "",
    }
    url = _safe_public_telegram_url(ref.get("url"))
    if url:
        result["url"] = url
    return result


def _safe_public_telegram_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    if parsed.scheme != "https":
        return ""
    if (parsed.hostname or "").casefold() != "t.me":
        return ""
    return text


def _safe_relative_report_path(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if desk_artifacts.is_dashboard_openable_artifact_path(text):
        return text
    return ""


def _miniapp_item(item: dict[str, Any]) -> dict[str, Any]:
    result = {"why": str(item.get("why") or "")}
    source_excerpt = _miniapp_source_excerpt(item)
    if source_excerpt:
        result["source_excerpt"] = source_excerpt
    decision_state = _miniapp_decision_state(item.get("decision_state"))
    if decision_state:
        result["decision_state"] = decision_state
    return result


def _miniapp_learning_summary(summary: object) -> dict[str, Any]:
    source = summary if isinstance(summary, dict) else {}
    result: dict[str, Any] = {
        "schema_version": MINIAPP_LEARNING_SUMMARY_SCHEMA_VERSION,
        "current_decision_count": _non_negative_int(source.get("current_decision_count")),
        "exportable_count": _non_negative_int(source.get("exportable_count")),
        "non_exportable_follow_up_count": _non_negative_int(source.get("non_exportable_follow_up_count")),
        "pending_profile_diff_count": _non_negative_int(source.get("pending_profile_diff_count")),
        "applied_profile_diff_count": _non_negative_int(source.get("applied_profile_diff_count")),
        "changed_since_last_export": bool(source.get("changed_since_last_export")),
    }
    next_action = _miniapp_next_action(source.get("next_action"))
    if next_action:
        result["next_action"] = next_action
    calibration = source.get("calibration") if isinstance(source.get("calibration"), dict) else {}
    calibration_next_action = _miniapp_next_action(calibration.get("next_action"))
    if calibration_next_action:
        result["calibration_next_action"] = calibration_next_action
    return result


def _non_negative_int(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _miniapp_next_action(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    label = _clean_recommendation_text(value.get("label"), fallback="")
    detail = _clean_recommendation_text(value.get("detail"), fallback="")
    result: dict[str, str] = {}
    if label:
        result["label"] = label[:80]
    if detail:
        result["detail"] = detail[:220]
    return result


def miniapp_source_recommendations(*, limit: int = 6) -> list[dict[str, Any]]:
    payload = _miniapp_public_source_candidate_payload()
    topic = _clean_recommendation_text(payload.get("topic"), fallback="jobs") if payload else "jobs"
    installed_source_ids = _miniapp_installed_source_ids()
    recommendations: list[dict[str, Any]] = []
    candidates = payload.get("candidates") if isinstance(payload, dict) else []
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            recommendation = _miniapp_source_recommendation(candidate, topic=topic, installed_source_ids=installed_source_ids)
            if recommendation:
                recommendations.append(recommendation)
            if len(recommendations) >= limit:
                break
    return recommendations


def _miniapp_source_excerpt(item: dict[str, Any]) -> str:
    for key in ("source_excerpt", "original_excerpt", "source_summary", "summary", "description"):
        text = str(item.get(key) or "").strip()
        if not text:
            continue
        text = _MINIAPP_URL_RE.sub("[link]", " ".join(text.split()))
        text = _MINIAPP_SOURCE_PREFIX_RE.sub("", text).strip()
        if len(text) > MINIAPP_SOURCE_EXCERPT_MAX_LENGTH:
            text = text[: MINIAPP_SOURCE_EXCERPT_MAX_LENGTH - 3].rstrip() + "..."
        return text
    return ""


def _miniapp_public_source_candidate_payload() -> dict[str, Any]:
    paths = desk_source_registry._starter_source_candidate_paths("jobs")
    candidates_path = next((path for path in paths if path.suffix.casefold() == ".json" and path.exists()), None)
    if not candidates_path:
        return {"topic": "jobs", "candidates": []}
    try:
        payload = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"topic": "jobs", "candidates": []}
    return payload if isinstance(payload, dict) else {"topic": "jobs", "candidates": []}


def _miniapp_installed_source_ids() -> set[str]:
    registry_path = desk_source_registry._project_root() / ".tgcs" / "sources.json"
    try:
        registry = source_registry.load_registry(registry_path, missing_ok=True)
    except source_registry.RegistryError:
        return set()
    installed: set[str] = set()
    for source in registry.get("sources") or []:
        if isinstance(source, dict) and source.get("source_id"):
            installed.add(str(source["source_id"]))
    return installed


def _miniapp_source_recommendation(
    candidate: dict[str, Any],
    *,
    topic: str,
    installed_source_ids: set[str],
) -> dict[str, Any] | None:
    channel = source_registry.normalize_channel_name(candidate.get("handle") or candidate.get("username") or candidate.get("channel"))
    if not channel:
        return None
    try:
        source_id = source_registry.source_id_for(channel, None)
    except source_registry.RegistryError:
        return None
    label = _clean_recommendation_text(candidate.get("title"), fallback=channel.replace("_", " ").title())
    reason = _miniapp_source_recommendation_reason(candidate)
    return {
        "schema_version": MINIAPP_SOURCE_RECOMMENDATION_SCHEMA_VERSION,
        "source_id": source_id,
        "channel": channel,
        "label": label[:120],
        "topic": _clean_recommendation_text(topic, fallback="jobs")[:60],
        "reason": reason[:220],
        "installed": source_id in installed_source_ids,
    }


def _miniapp_source_recommendation_reason(candidate: dict[str, Any]) -> str:
    quality_hints = candidate.get("quality_hints") if isinstance(candidate.get("quality_hints"), dict) else {}
    scope = _clean_recommendation_text(quality_hints.get("scope"), fallback="")
    noise = _clean_recommendation_text(quality_hints.get("expected_noise"), fallback="")
    parts: list[str] = []
    if scope:
        parts.append(scope)
    if noise:
        parts.append(f"{noise} expected noise")
    return ". ".join(parts) or "Public starter source for the next local run."


def _clean_recommendation_text(value: object, *, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    return text or fallback


def _miniapp_decision_state(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key in ("status", "first_seen_at", "last_seen_at"):
        text = str(value.get(key) or "").strip()
        if text:
            result[key] = text[:120]
    try:
        seen_count = int(value.get("seen_count") or 0)
    except (TypeError, ValueError):
        seen_count = 0
    if seen_count > 0:
        result["seen_count"] = seen_count
    signals = _miniapp_string_list(value.get("signals"))
    if signals:
        result["signals"] = signals
    material_change_fields = _miniapp_string_list(value.get("material_change_fields"))
    if material_change_fields:
        result["material_change_fields"] = material_change_fields
    return result


def _miniapp_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text[:80])
    return result[:8]


def _miniapp_alert_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    try:
        alert_count = max(0, int(value.get("alert_count") or 0))
    except (TypeError, ValueError):
        alert_count = 0
    if alert_count <= 0:
        return None
    result: dict[str, Any] = {
        "schema_version": "review_card_alert_summary_v1"
        if value.get("schema_version") == "review_card_alert_summary_v1"
        else "",
        "alert_count": alert_count,
    }
    for key in (
        "latest_status",
        "latest_delivery_mode",
        "latest_delivery_status",
        "latest_alerted_at",
    ):
        text = str(value.get(key) or "").strip()
        if text:
            result[key] = text[:120]
    if isinstance(value.get("latest_delivery_ok"), bool):
        result["latest_delivery_ok"] = bool(value["latest_delivery_ok"])
    return result


def _miniapp_setup_status(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "stage": str(value.get("stage") or ""),
        "next_step": str(value.get("next_step") or ""),
        "has_runs": bool(value.get("has_runs")),
        "has_profiles": bool(value.get("has_profiles")),
        "has_user_goal": bool(value.get("has_user_goal")),
    }
