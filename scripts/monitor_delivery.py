"""Delivery target and alert dispatch helpers for monitor runs."""

from __future__ import annotations

from typing import Any

from scripts import delivery, monitor_state
from scripts.monitor_config import MonitorConfig


def delivery_targets_for_profile(config: MonitorConfig, profile: dict[str, Any]) -> list[dict[str, Any]]:
    target_ids = profile.get("delivery_targets") or profile.get("delivery_target") or []
    if isinstance(target_ids, str):
        target_ids = [target_ids]
    targets = [config.delivery_targets[item] for item in target_ids if item in config.delivery_targets]
    if targets:
        return targets
    return [target for target in config.delivery_targets.values() if target.get("type") == "telegram_bot"]


def apply_delivery_runtime_overrides(conn, config: MonitorConfig) -> MonitorConfig:
    """Merge local Desk notification edits into the loaded monitor config.

    `.tgcs/profiles.toml` remains the portable profile contract, but Signal Desk
    edits are stored in SQLite so a non-CLI user can set or mute notifications
    without hand-editing TOML. Apply these overrides before writing targets
    back to SQLite; otherwise the next monitor run would overwrite the user's
    Desk edits with the file defaults.
    """

    rows = conn.execute("SELECT * FROM delivery_targets ORDER BY target_id").fetchall()
    if not rows:
        return config
    targets = {target_id: dict(target) for target_id, target in config.delivery_targets.items()}
    for row in rows:
        target_id = str(row["target_id"] or "").strip()
        if not target_id:
            continue
        target_type = str(row["target_type"] or targets.get(target_id, {}).get("type") or "telegram_bot")
        if target_type != "telegram_bot":
            continue
        persisted = monitor_state.parse_json(row["config_json"], {})
        if not isinstance(persisted, dict):
            persisted = {}
        merged = {**targets.get(target_id, {}), **persisted}
        merged["id"] = target_id
        merged["type"] = target_type
        merged["enabled"] = bool(row["enabled"])
        merged.pop("token", None)
        merged.pop("bot_token", None)
        targets[target_id] = merged
    return MonitorConfig(path=config.path, profiles=config.profiles, delivery_targets=targets, defaults=config.defaults)


def alert_card_keyboard(card: dict[str, Any]) -> dict[str, Any] | None:
    card_id = str(card.get("card_id") or "").strip()
    if not card_id:
        return None
    return {
        "inline_keyboard": [
            [
                {"text": "Applied", "callback_data": f"card:applied:{card_id}"},
                {"text": "Save", "callback_data": f"card:saved:{card_id}"},
            ],
            [
                {"text": "Dismiss", "callback_data": f"card:dismissed:{card_id}"},
                {"text": "Duplicate", "callback_data": f"card:duplicate:{card_id}"},
            ],
        ]
    }


def run_delivery(
    *,
    conn,
    run_id_value: str,
    profile_id: str,
    cards: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    mode: str,
    alert_rule: dict[str, Any],
    delivery_enabled: bool,
    report_path: str | None,
    dashboard_url: str,
) -> tuple[int, list[dict[str, Any]]]:
    suppressed_alert_keys = (
        monitor_state.sent_alert_suppression_keys(conn, profile_id=profile_id) if conn is not None else set()
    )
    candidates = monitor_state.alert_candidates(
        cards,
        alert_rule=alert_rule,
        suppressed_alert_keys=suppressed_alert_keys,
    )
    events: list[dict[str, Any]] = []
    if mode == "off" or not delivery_enabled:
        return len(candidates), events
    for card in candidates:
        item = card.get("item") if isinstance(card.get("item"), dict) else {}
        for target in targets:
            if target.get("type") != "telegram_bot" or not target.get("enabled", False):
                continue
            text = delivery.build_telegram_alert_text(
                item=item,
                card=card,
                report_url=report_path,
                dashboard_url=dashboard_url,
            )
            attempt = delivery.send_telegram_bot_message(
                target_id=target["id"],
                chat_id=str(target.get("chat_id") or ""),
                text=text,
                mode=mode,
                reply_markup=alert_card_keyboard(card),
            )
            event = monitor_state.record_alert_event(
                conn,
                run_id=run_id_value,
                card_id=card["card_id"],
                profile_id=profile_id,
                target_id=target["id"],
                status=attempt.status,
                payload={
                    "text": text,
                    "decision_status": card.get("decision_status"),
                    "item_key": card.get("item_key"),
                },
                delivery_attempt=attempt.to_dict(),
            )
            events.append(event)
    return len(candidates), events
