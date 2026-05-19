"""Dashboard setup-readiness projection."""

from __future__ import annotations

from typing import Any


def dashboard_setup_status(
    *,
    profiles: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    delivery_targets: list[dict[str, Any]],
    ai_configured: bool = False,
) -> dict[str, Any]:
    active_profiles = [profile for profile in profiles if profile.get("enabled")]
    active_targets = [target for target in delivery_targets if target.get("enabled")]
    preferred = preferred_setup_profile(active_profiles)
    has_user_goal = has_selected_user_goal(profiles, active_profiles)
    latest_source_attention = latest_run_needs_source_attention(runs[0]) if runs else False
    if not ai_configured:
        if not profiles and not runs:
            next_step = "Open Start and generate the demo report, then create a monitor goal."
        elif not has_user_goal and not runs:
            next_step = "Open Start and create or choose a monitor goal before connecting sources."
        else:
            next_step = "Open Signal Desk Settings > AI API key before the first AI review."
        stage = "needs_ai_key"
    elif not profiles:
        next_step = "Open Profiles and create an AI-generated matching profile."
        stage = "needs_profiles"
    elif not active_profiles:
        next_step = "Enable a profile in .tgcs/profiles.toml"
        stage = "needs_enabled_profile"
    elif not has_user_goal and not runs:
        next_step = "Open Profiles or Start and create or choose a monitor goal."
        stage = "needs_profiles"
    elif not runs:
        next_step = f"Open Start and run the first AI review for {preferred['profile_id']}."
        stage = "needs_first_run"
    elif latest_source_attention:
        profile = profile_for_run(active_profiles, runs[0])
        next_step = source_attention_next_step(profile)
        stage = "needs_source_access"
    elif not active_targets:
        next_step = "Save and enable a Telegram bot notification target in Settings > Alerts."
        stage = "needs_delivery_target"
    else:
        next_step = "Review inbox"
        stage = "ready"
    return {
        "schema_version": "dashboard_setup_status_v1",
        "stage": stage,
        "next_step": next_step,
        "has_profiles": bool(profiles),
        "has_user_goal": has_user_goal,
        "has_runs": bool(runs),
        "has_delivery_targets": bool(delivery_targets),
        "has_enabled_delivery_targets": bool(active_targets),
        "checks": setup_checklist(
            ai_configured=ai_configured,
            profiles=profiles,
            active_profiles=active_profiles,
            has_user_goal=has_user_goal,
            runs=runs,
            active_targets=active_targets,
            latest_source_attention=latest_source_attention,
        ),
    }


def setup_check(
    check_id: str,
    label: str,
    status: str,
    *,
    detail: str = "",
    command: str = "",
) -> dict[str, str]:
    payload = {"check_id": check_id, "label": label, "status": status}
    if detail:
        payload["detail"] = detail
    if command:
        payload["command"] = command
    return payload


def preferred_setup_profile(active_profiles: list[dict[str, Any]]) -> dict[str, Any]:
    if not active_profiles:
        return {"profile_id": "market-news", "config": {"id": "market-news"}}
    desk_profiles = [
        profile
        for profile in active_profiles
        if str(profile.get("path") or "").replace("\\", "/").startswith("profiles/desk/")
    ]
    if desk_profiles:
        # A profile created in Signal Desk is usually the user's current
        # matching intent. Prefer the newest registered Desk profile for manual
        # first/fresh scans so users do not tune a custom profile while Start
        # keeps pointing them back at the packaged jobs-fast template.
        return sorted(desk_profiles, key=lambda profile: str(profile.get("updated_at") or ""))[-1]
    return next(
        (profile for profile in active_profiles if profile.get("profile_id") == "market-news"),
        active_profiles[0],
    )


def profile_config_path(profile: dict[str, Any]) -> str:
    config = profile.get("config") if isinstance(profile.get("config"), dict) else {}
    return str(profile.get("path") or config.get("path") or "").replace("\\", "/")


def is_packaged_template_profile(profile: dict[str, Any]) -> bool:
    return profile_config_path(profile).startswith("profiles/templates/")


def has_selected_user_goal(profiles: list[dict[str, Any]], active_profiles: list[dict[str, Any]]) -> bool:
    # `tgcs init` installs multiple packaged templates so the scanner can run,
    # but that is not the same as a human choosing what Signal Desk should watch.
    # A custom Desk profile, non-template profile, or one remaining active
    # packaged profile means the user has made a goal choice.
    if any(not is_packaged_template_profile(profile) for profile in active_profiles):
        return True
    active_packaged = [profile for profile in active_profiles if is_packaged_template_profile(profile)]
    if len(active_packaged) == 1:
        return True
    return bool(profiles) and not active_profiles and any(
        not is_packaged_template_profile(profile) for profile in profiles
    )


def profile_for_run(active_profiles: list[dict[str, Any]], run: dict[str, Any]) -> dict[str, Any]:
    if not active_profiles:
        return preferred_setup_profile(active_profiles)
    return next(
        (
            item
            for item in active_profiles
            if item.get("profile_id") == run.get("profile_id")
        ),
        preferred_setup_profile(active_profiles),
    )


def setup_checklist(
    *,
    ai_configured: bool = False,
    profiles: list[dict[str, Any]],
    active_profiles: list[dict[str, Any]],
    has_user_goal: bool,
    runs: list[dict[str, Any]],
    active_targets: list[dict[str, Any]],
    latest_source_attention: bool,
) -> list[dict[str, str]]:
    preferred = preferred_setup_profile(active_profiles)
    first_run_command = f"tgcs monitor run --profile-id {preferred['profile_id']} --delivery-mode live"

    if not ai_configured:
        ai_status = "todo"
        ai_detail = "An AI key is only needed before the first AI review; demo, local goals, Telegram setup, and sources can continue without it."
    else:
        ai_status = "done"
        ai_detail = "AI matching key is configured."

    if not profiles:
        profile_status = "active"
        profile_command = ""
        if ai_configured:
            profile_detail = "Create an AI-generated matching profile from a plain-language goal."
        else:
            profile_detail = "Create a local monitor goal now; AI-generated profile help can wait until a key is saved."
    elif not active_profiles:
        profile_status = "blocked"
        profile_command = "Enable a profile in .tgcs/profiles.toml"
        profile_detail = "At least one profile must be enabled before monitoring."
    elif not has_user_goal:
        profile_status = "active"
        profile_command = ""
        profile_detail = "Create or choose one monitor goal so Signal Desk knows what to watch before Telegram/source setup."
    else:
        profile_status = "done"
        profile_command = ""
        profile_detail = "Enabled profile config is registered."

    if latest_source_attention:
        source_status = "blocked"
        source_detail = "The latest run fetched no usable Telegram messages."
    elif runs:
        source_status = "done"
        source_detail = "The latest run reached the scan/report pipeline."
    elif not has_user_goal:
        source_status = "todo"
        source_detail = "Choose a monitor goal, then add starter or public sources before the first review."
    elif active_profiles and ai_configured:
        source_status = "todo"
        source_detail = "Discover Telegram channels, then let AI select sources for this profile."
    elif active_profiles:
        source_status = "todo"
        source_detail = "Add starter or public sources now; AI source matching can wait until a key is saved."
    else:
        source_status = "todo"
        source_detail = "Create a goal, then add starter or public sources before the first review."

    if latest_source_attention:
        first_run_status = "blocked"
        first_run_detail = "Fix source access, then rerun the monitor."
    elif runs:
        first_run_status = "done"
        first_run_detail = "Run history exists in the local dashboard database."
    elif active_profiles and has_user_goal and ai_configured:
        first_run_status = "active"
        first_run_detail = "Run one AI review pass locally; Telegram alerts send when a notification target is enabled."
    else:
        first_run_status = "todo"
        first_run_detail = "A goal, Telegram access, sources, and an AI key are required before the first AI review."

    delivery_status = "done" if active_targets else "todo"
    if not active_targets:
        delivery_detail = "Save and enable a Telegram bot target for interrupt alerts."
        delivery_command = ""
    else:
        delivery_detail = "At least one delivery target is enabled."
        delivery_command = ""

    return [
        setup_check(
            "ai_api",
            "AI API key",
            ai_status,
            detail=ai_detail,
            command="",
        ),
        setup_check(
            "profiles",
            "Profiles",
            profile_status,
            detail=profile_detail,
            command=profile_command,
        ),
        setup_check(
            "source_access",
            "Source access",
            source_status,
            detail=source_detail,
            command="",
        ),
        setup_check(
            "first_run",
            "First AI review",
            first_run_status,
            detail=first_run_detail,
            command="" if latest_source_attention else first_run_command,
        ),
        setup_check(
            "delivery",
            "Alert delivery",
            delivery_status,
            detail=delivery_detail,
            command=delivery_command,
        ),
    ]


def latest_run_needs_source_attention(run: dict[str, Any]) -> bool:
    if str(run.get("status") or "").lower() not in {"failed", "error"}:
        return False
    quality = run.get("quality") if isinstance(run.get("quality"), dict) else {}
    source_failure_codes = {"channel_failures", "no_messages_fetched"}
    if str(quality.get("semantic_stage") or "") == "scan_failed":
        return True
    return str(quality.get("top_diagnostic_code") or "") in source_failure_codes


def source_attention_next_step(profile: dict[str, Any]) -> str:
    config = profile.get("config") if isinstance(profile.get("config"), dict) else {}
    profile_id = str(profile.get("profile_id") or config.get("id") or "market-news")
    return (
        "Open Signal Desk Settings > Sources, discover Telegram channels with AI, "
        f"then run another AI review for {profile_id}."
    )
