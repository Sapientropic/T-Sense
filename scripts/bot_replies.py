"""Bot reply text, keyboards, and safe action summaries."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from scripts import bot_actions, bot_intents, dashboard_server, monitor_state
    from scripts.bot_api import BotGatewayError
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts import bot_actions, bot_intents, dashboard_server, monitor_state
    from scripts.bot_api import BotGatewayError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / ".tgcs" / "tgcs.db"
ALLOWED_INTENT_ACTIONS = bot_intents.ALLOWED_INTENT_ACTIONS
BotIntent = bot_intents.BotIntent



def main_menu_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Status", "callback_data": "status"},
                {"text": "Latest", "callback_data": "latest"},
            ],
            [
                {"text": "AI review", "callback_data": "scan:jobs-fast"},
                {"text": "Sources", "callback_data": "sources"},
            ],
            [
                {"text": "Profiles", "callback_data": "profiles"},
                {"text": "Settings", "callback_data": "settings"},
            ],
        ]
    }



def help_text() -> str:
    return "\n".join(
        [
            "*T-Sense bot*",
            "",
            "*Commands*",
            "/status - setup, source, run, and inbox status",
            "/latest - latest actionable cards and report",
            "/scan - run a local AI review for jobs-fast",
            "/sources - source count and topics",
            "/sources add @channel - preview a source change",
            "/profiles - enabled profiles",
            "/settings - local setup guidance",
            "",
            "Natural language works for the same safe actions. Source changes are previewed first and require the Apply button.",
        ]
    )



def dashboard_snapshot(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    conn = monitor_state.connect(db_path)
    try:
        return monitor_state.dashboard_snapshot(conn)
    finally:
        conn.close()



def source_summary() -> str:
    sources = dashboard_server.desk_sources()
    topics = ", ".join(sources.get("topics") or []) or "none"
    return "\n".join(
        [
            "Sources",
            f"Total: {sources.get('source_count', 0)}",
            f"Enabled: {sources.get('enabled_count', 0)}",
            f"Topics: {topics}",
            "",
            "Send: add @channel, pause @channel, remove @channel",
        ]
    )



def profile_summary(snapshot: dict[str, Any]) -> str:
    profiles = [item for item in snapshot.get("profiles") or [] if isinstance(item, dict)]
    if not profiles:
        return "No profiles are registered yet. Open Signal Desk Start or run ./tgcs init --starter jobs."
    lines = ["Profiles"]
    for profile in profiles[:12]:
        status = "enabled" if profile.get("enabled") else "muted"
        label = str(profile.get("display_name") or profile.get("profile_id") or "profile")
        lines.append(f"- {label}: {status}")
    if len(profiles) > 12:
        lines.append(f"... {len(profiles) - 12} more")
    return "\n".join(lines)



def status_summary(snapshot: dict[str, Any]) -> str:
    setup = snapshot.get("setup_status") if isinstance(snapshot.get("setup_status"), dict) else {}
    opportunity = snapshot.get("opportunity_summary") if isinstance(snapshot.get("opportunity_summary"), dict) else {}
    runs = [item for item in snapshot.get("runs") or [] if isinstance(item, dict)]
    inbox = [item for item in snapshot.get("inbox") or [] if isinstance(item, dict)]
    latest_run = runs[0] if runs else {}
    return "\n".join(
        [
            "T-Sense status",
            f"Stage: {setup.get('stage') or 'unknown'}",
            f"Next: {setup.get('next_step') or 'Open Signal Desk'}",
            f"Pending review cards: {len(inbox)}",
            f"Bot delivery: {bot_delivery_status_line(snapshot)}",
            f"Proof loop: {proof_loop_status_line(snapshot)}",
            f"Latest run: {latest_run.get('status') or 'none'} {latest_run.get('profile_id') or ''}".strip(),
            f"Opportunity summary: {opportunity.get('title') or opportunity.get('status') or 'not ready'}",
        ]
    )


def bot_delivery_status_line(snapshot: dict[str, Any]) -> str:
    targets = [item for item in snapshot.get("delivery_targets") or [] if isinstance(item, dict)]
    telegram_targets = [item for item in targets if str(item.get("type") or item.get("target_type") or "") == "telegram_bot"]
    enabled_count = sum(1 for item in telegram_targets if bool(item.get("enabled")))
    if enabled_count:
        return "private Telegram bot ready"
    if telegram_targets:
        return "saved but muted"
    return "needs chat in Settings > Alerts"


def proof_loop_status_line(snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("validation_summary") if isinstance(snapshot.get("validation_summary"), dict) else {}
    minutes = summary.get("first_decision_minutes")
    action = str(summary.get("first_decision_action") or "").strip().replace("_", " ")
    if isinstance(minutes, (int, float)):
        timing = "<1 min" if minutes < 1 else f"{round(minutes)} min"
        return f"first decision {timing}" + (f" ({action})" if action else "")
    if safe_int(summary.get("runs_count")) > 0:
        return "waiting for first review decision"
    return "run an AI review to start"


def public_telegram_link(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = (parsed.hostname or "").casefold()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return ""
    return text


def latest_summary(snapshot: dict[str, Any]) -> str:
    opportunity = snapshot.get("opportunity_summary") if isinstance(snapshot.get("opportunity_summary"), dict) else {}
    display_name = str(opportunity.get("display_name") or "").strip()
    title = str(opportunity.get("title") or "").strip()
    if not title:
        title = f"{display_name} latest" if display_name else "Latest results"
    next_action = opportunity.get("next_action") if isinstance(opportunity.get("next_action"), dict) else {}
    detail = str(
        opportunity.get("detail")
        or next_action.get("detail")
        or opportunity.get("status")
        or "No latest summary yet."
    )
    lines = [title, detail]
    count_line = latest_count_line(opportunity)
    if count_line:
        lines.append(count_line)
    # Current dashboard snapshots use `top_items`; older tests and local state
    # may still pass `items`, so keep the fallback until the bot contract is
    # explicitly versioned.
    items = opportunity.get("top_items")
    if not isinstance(items, list):
        items = opportunity.get("items")
    if isinstance(items, list):
        if items:
            lines.append("Top signals:")
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("title") or item.get("label") or item.get("card_title") or "Item")
            proof = latest_item_proof(item)
            lines.append(f"- {label}" + (f" ({proof})" if proof else ""))
    action_label = str(next_action.get("label") or "").strip()
    if action_label:
        lines.append(f"Next: {action_label}")
        command = str(next_action.get("command") or "").strip()
        if command:
            lines.append(f"Command: {command}")
    runs = [item for item in snapshot.get("runs") or [] if isinstance(item, dict)]
    if runs:
        artifact = runs[0].get("report_artifact") if isinstance(runs[0].get("report_artifact"), dict) else {}
        display_path = str(artifact.get("display_path") or artifact.get("path") or "")
        public_report = public_telegram_link(display_path)
        if public_report:
            lines.append(f"Report: {public_report}")
    return "\n".join(lines)



def latest_count_line(opportunity: dict[str, Any]) -> str:
    keys = ("scanned_count", "matched_count", "review_card_count", "high_actionable_count", "alert_count")
    if not any(key in opportunity for key in keys):
        return ""
    return (
        f"Scanned: {safe_int(opportunity.get('scanned_count'))} | "
        f"Matched: {safe_int(opportunity.get('matched_count'))} | "
        f"Cards: {safe_int(opportunity.get('review_card_count'))} | "
        f"High: {safe_int(opportunity.get('high_actionable_count'))} | "
        f"Alerts: {safe_int(opportunity.get('alert_count'))}"
    )


def latest_item_proof(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("rating") or "").strip(),
        str(item.get("decision_status") or item.get("status") or "").strip(),
    ]
    return "/".join(part for part in parts if part)


def safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def latest_actionable_card(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    inbox = snapshot.get("inbox") if isinstance(snapshot.get("inbox"), list) else []
    for card in inbox:
        if not isinstance(card, dict):
            continue
        if str(card.get("opportunity_status") or "open").strip().lower() != "open":
            continue
        if str(card.get("card_id") or "").strip():
            return card
    return None



def lifecycle_keyboard(card: dict[str, Any]) -> dict[str, Any] | None:
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
                {"text": "Contacted", "callback_data": f"card:contacted:{card_id}"},
                {"text": "Dismiss", "callback_data": f"card:dismissed:{card_id}"},
                {"text": "Duplicate", "callback_data": f"card:duplicate:{card_id}"},
            ],
        ]
    }



def lifecycle_status_label(status: object) -> str:
    labels = {
        "open": "Open",
        "saved": "Saved",
        "applied": "Applied",
        "contacted": "Contacted",
        "dismissed": "Dismissed",
        "duplicate": "Duplicate",
    }
    return labels.get(str(status or "open").strip().lower(), "Open")



def card_action_summary(card: dict[str, Any]) -> str:
    label = lifecycle_status_label(card.get("opportunity_status"))
    title = str(card.get("title") or "Review card").strip()
    rating = str(card.get("rating") or "").strip()
    detail = f"{label}: {title}"
    if rating:
        detail += f" ({rating})"
    return detail



def run_dry_scan(profile_id: str, *, timeout_seconds: int = 900) -> str:
    _ = timeout_seconds
    result = bot_actions.BotActionRegistry().execute(
        BotIntent(action="scan_profile_dry_run", args={"profile_id": profile_id})
    )
    if result.error_category:
        raise BotGatewayError(result.text)
    return result.text



def clean_topic(value: str) -> str:
    return bot_intents.clean_topic(value)



def deterministic_intent(text: str) -> BotIntent | None:
    return bot_intents.deterministic_intent(text)



def llm_intent(text: str) -> BotIntent | None:
    return bot_intents.llm_intent(text)



def route_text_to_intent(text: str, *, use_llm: bool = False) -> BotIntent:
    return bot_intents.route_text_to_intent(text, use_llm=use_llm)



def source_plan_preview(instruction: str, topic: str) -> tuple[str, dict[str, Any]]:
    # Telegram chat confirmation only authorizes applying the resolved local
    # plan. It is not a consent boundary for sending the saved source list to
    # an external model, so bot previews stay parser-only until Signal Desk
    # provides a dedicated AI source planning confirmation flow.
    result = dashboard_server.run_source_assistant(
        {
            "instruction": instruction,
            "topic": topic,
            "dry_run": True,
            "confirm_external_ai": False,
        }
    )
    lines = [
        result.get("title") or "Source plan ready",
        result.get("detail") or "Review the source plan before applying it.",
        f"Add {result.get('added_count', 0)} · Pause {result.get('disabled_count', 0)} · Resume {result.get('enabled_count', 0)} · Remove {result.get('removed_count', 0)}",
    ]
    preview_sources = result.get("preview_sources") if isinstance(result.get("preview_sources"), list) else []
    for source in preview_sources[:8]:
        if isinstance(source, dict):
            lines.append(f"- {source.get('label') or source.get('source_id')}")
    return "\n".join(lines), result



def apply_source_plan(resolved_plan: dict[str, list[str]], topic: str) -> str:
    result = dashboard_server.apply_source_assistant_resolved_plan(resolved_plan, topic)
    return "\n".join(
        [
            result.get("title") or "Source plan applied",
            f"Add {result.get('added_count', 0)} · Pause {result.get('disabled_count', 0)} · Resume {result.get('enabled_count', 0)} · Remove {result.get('removed_count', 0)}",
        ]
    )



def unauthorized_text() -> str:
    return "\n".join(
        [
            "This chat is not authorized for T-Sense actions.",
            "Open Signal Desk Settings > Alerts, detect and save this bot chat, then try again.",
            "CLI fallback: TGCS_BOT_ALLOWED_CHAT_IDS=<chat_id> ./tgcs bot run",
        ]
    )



def settings_text() -> str:
    return "\n".join(
        [
            "Settings",
            "- Save the Telegram bot token in Signal Desk Settings > Alerts.",
            "- Detect and save this chat ID before using bot actions.",
            "- Keep Signal Desk or ./tgcs bot run active for local-first bot control.",
            "- Cloud webhook and Mini App support are tracked as a later roadmap phase.",
        ]
    )
