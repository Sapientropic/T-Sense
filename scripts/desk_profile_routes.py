"""Profile mutation helpers for the local Signal Desk HTTP facade."""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import Any
from urllib.parse import unquote


def _profile_id_from_path(path: str) -> str:
    return unquote(path.split("/")[3])


def _patch_id_from_path(path: str) -> str:
    return unquote(path.split("/")[3])


def _reject_unexpected_fields(body: Mapping[str, Any], allowed_fields: Set[str], *, label: str) -> None:
    unexpected = sorted(str(key) for key in body.keys() if key not in allowed_fields)
    if unexpected:
        raise ValueError(f"Unsupported {label} field: {', '.join(unexpected)}")


def validate_profile_enabled_body(body: Mapping[str, Any], *, allowed_fields: Set[str]) -> bool:
    _reject_unexpected_fields(body, allowed_fields, label="profile setting")
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("Profile enabled value must be true or false.")
    return enabled


def validate_profile_runtime_settings_body(body: Mapping[str, Any], *, allowed_fields: Set[str]) -> None:
    _reject_unexpected_fields(body, allowed_fields, label="profile setting")


def validate_profile_draft_note_text(
    body: Mapping[str, Any],
    *,
    monitor_state_module: Any,
    allowed_fields: Set[str],
    max_length: int,
) -> str:
    _reject_unexpected_fields(body, allowed_fields, label="profile draft")
    note = " ".join(str(body.get("note") or "").split())
    if not note:
        raise ValueError("Profile note is required.")
    if len(note) > max_length:
        raise ValueError(f"Profile note must be {max_length} characters or fewer.")
    return monitor_state_module.require_profile_text_without_private_fragments("Profile note", note)


def validate_profile_matching_preferences_text(
    body: Mapping[str, Any],
    *,
    monitor_state_module: Any,
    allowed_fields: Set[str],
    max_length: int,
) -> str:
    _reject_unexpected_fields(body, allowed_fields, label="profile matching")
    preferences = str(body.get("preferences") or "").strip()
    if not preferences:
        raise ValueError("Profile matching preferences are required.")
    if len(preferences) > max_length:
        raise ValueError(f"Profile matching preferences must be {max_length} characters or fewer.")
    return monitor_state_module.require_profile_text_without_private_fragments(
        "Profile matching preferences",
        preferences,
    )


def profile_alert_mode_payload(conn: Any, *, path: str, body: Mapping[str, Any], monitor_state_module: Any) -> dict:
    profile = monitor_state_module.update_profile_alert_mode(
        conn,
        profile_id=_profile_id_from_path(path),
        mode=str(body.get("mode") or ""),
    )
    return {"ok": True, "profile": profile}


def profile_enabled_payload(
    conn: Any,
    *,
    path: str,
    body: Mapping[str, Any],
    monitor_state_module: Any,
    allowed_fields: Set[str],
) -> dict:
    enabled = validate_profile_enabled_body(body, allowed_fields=allowed_fields)
    profile = monitor_state_module.update_profile_enabled(conn, profile_id=_profile_id_from_path(path), enabled=enabled)
    return {"ok": True, "profile": profile}


def profile_runtime_settings_payload(
    conn: Any,
    *,
    path: str,
    body: Mapping[str, Any],
    monitor_state_module: Any,
    allowed_fields: Set[str],
) -> dict:
    validate_profile_runtime_settings_body(body, allowed_fields=allowed_fields)
    profile = monitor_state_module.update_profile_runtime_settings(
        conn,
        profile_id=_profile_id_from_path(path),
        settings=body,
    )
    return {"ok": True, "profile": profile}


def profile_draft_note_payload(
    conn: Any,
    *,
    path: str,
    body: Mapping[str, Any],
    monitor_state_module: Any,
    allowed_fields: Set[str],
    max_length: int,
) -> dict:
    note = validate_profile_draft_note_text(
        body,
        monitor_state_module=monitor_state_module,
        allowed_fields=allowed_fields,
        max_length=max_length,
    )
    patch = monitor_state_module.create_profile_patch_suggestion(
        conn,
        profile_id=_profile_id_from_path(path),
        card_id=None,
        note=note,
        profile_path=None,
    )
    conn.commit()
    return {"ok": True, "patch": patch}


def profile_matching_preferences_payload(
    conn: Any,
    *,
    path: str,
    body: Mapping[str, Any],
    monitor_state_module: Any,
    allowed_fields: Set[str],
    max_length: int,
) -> dict:
    preferences = validate_profile_matching_preferences_text(
        body,
        monitor_state_module=monitor_state_module,
        allowed_fields=allowed_fields,
        max_length=max_length,
    )
    patch = monitor_state_module.create_profile_preferences_patch_suggestion(
        conn,
        profile_id=_profile_id_from_path(path),
        preferences_text=preferences,
    )
    conn.commit()
    return {"ok": True, "patch": patch}


def profile_patch_action_payload(conn: Any, *, path: str, action: str, monitor_state_module: Any) -> dict:
    patch_id = _patch_id_from_path(path)
    if action == "apply":
        result = monitor_state_module.apply_profile_patch(conn, patch_id=patch_id)
    elif action == "revert":
        result = monitor_state_module.revert_profile_patch(conn, patch_id=patch_id)
    elif action == "replay":
        result = monitor_state_module.replay_profile_patch(conn, patch_id=patch_id)
    else:
        raise ValueError(f"Unsupported profile patch action: {action}")
    return {"ok": True, "result": result}
