"""Local-first Telegram Bot gateway for T-Sense.

The bot is a human interaction surface, not a shell gateway.  Incoming messages
are mapped to a small allowlist of local actions: status, latest results,
profiles, sources, dry-run scans, and Source assistant plans.  Mutating source
plans are previewed first and require an inline button confirmation from the
same chat before they are applied.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts import dashboard_server, delivery, monitor_state, report
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import dashboard_server, delivery, monitor_state, report


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / ".tgcs" / "tgcs.db"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / ".tgcs" / "profiles.toml"
DEFAULT_BOT_STATE_PATH = PROJECT_ROOT / ".tgcs" / "bot-gateway-state.json"
BOT_ALLOWED_CHAT_IDS_ENV = "TGCS_BOT_ALLOWED_CHAT_IDS"
BOT_API_TIMEOUT_SECONDS = 20
BOT_POLL_TIMEOUT_SECONDS = 30
MAX_TELEGRAM_MESSAGE_LENGTH = 3900
PENDING_SOURCE_PLAN_TTL_SECONDS = 15 * 60

BOT_COMMANDS = [
    {"command": "start", "description": "Show the T-Sense bot menu"},
    {"command": "help", "description": "Show commands and safe actions"},
    {"command": "status", "description": "Show setup, source, run, and inbox status"},
    {"command": "latest", "description": "Show the latest actionable results"},
    {"command": "scan", "description": "Run a dry scan for jobs-fast"},
    {"command": "sources", "description": "Show or adjust saved sources"},
    {"command": "profiles", "description": "List enabled profiles"},
    {"command": "settings", "description": "Show local setup guidance"},
]

ALLOWED_INTENT_ACTIONS = {
    "help",
    "status",
    "latest",
    "scan",
    "sources_summary",
    "sources_plan",
    "profiles",
    "settings",
}


@dataclass(frozen=True)
class BotIntent:
    action: str
    profile_id: str = "jobs-fast"
    topic: str = "jobs"
    instruction: str = ""
    needs_confirmation: bool = False
    source: str = "deterministic"


@dataclass
class PendingSourcePlan:
    chat_id: str
    topic: str
    resolved_plan: dict[str, list[str]]
    created_at: float


class BotGatewayError(Exception):
    """Raised when the local bot gateway cannot complete a safe action."""


class TelegramBotApi:
    def __init__(self, token: str, *, timeout_seconds: int = BOT_API_TIMEOUT_SECONDS):
        self.token = token
        self.timeout_seconds = timeout_seconds

    def request(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        data = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BotGatewayError(f"Telegram Bot API request failed: {method}") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            description = result.get("description") if isinstance(result, dict) else ""
            raise BotGatewayError(f"Telegram Bot API rejected {method}: {description or 'unknown error'}")
        return result

    def get_updates(self, *, offset: int | None, timeout_seconds: int = BOT_POLL_TIMEOUT_SECONDS) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout_seconds,
            "limit": 20,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = self.request("getUpdates", payload)
        updates = result.get("result")
        return [item for item in updates if isinstance(item, dict)] if isinstance(updates, list) else []

    def send_message(self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None) -> None:
        chunks = split_telegram_text(text)
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if reply_markup and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            self.request("sendMessage", payload)

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:180]
        self.request("answerCallbackQuery", payload)

    def set_my_commands(self) -> None:
        self.request("setMyCommands", {"commands": BOT_COMMANDS})


def split_telegram_text(text: str) -> list[str]:
    clean = text.strip() or "Done."
    if len(clean) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return [clean]
    chunks: list[str] = []
    remaining = clean
    while len(remaining) > MAX_TELEGRAM_MESSAGE_LENGTH:
        cut = remaining.rfind("\n", 0, MAX_TELEGRAM_MESSAGE_LENGTH)
        if cut < 500:
            cut = MAX_TELEGRAM_MESSAGE_LENGTH
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def load_bot_token() -> str:
    token = delivery.resolve_telegram_bot_token().token
    if not token:
        raise BotGatewayError("Telegram bot token is not configured. Save it in Signal Desk Settings first.")
    return token


def load_state(path: Path = DEFAULT_BOT_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(state: dict[str, Any], path: Path = DEFAULT_BOT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_chat_id(value: object) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"-?\d{5,20}", text) else ""


def allowed_chat_ids_from_env() -> set[str]:
    raw = os.environ.get(BOT_ALLOWED_CHAT_IDS_ENV, "")
    return {chat_id for chat_id in (clean_chat_id(part) for part in re.split(r"[,;\s]+", raw)) if chat_id}


def allowed_chat_ids_from_db(db_path: Path = DEFAULT_DB_PATH) -> set[str]:
    if not db_path.exists():
        return set()
    try:
        conn = monitor_state.connect(db_path)
    except Exception:
        return set()
    try:
        rows = conn.execute(
            "SELECT config_json FROM delivery_targets WHERE enabled = 1 AND target_type = ?",
            ("telegram_bot",),
        ).fetchall()
    finally:
        conn.close()
    allowed: set[str] = set()
    for row in rows:
        payload = monitor_state.parse_json(row["config_json"], {})
        if isinstance(payload, dict):
            config = payload.get("config") if isinstance(payload.get("config"), dict) else payload
            chat_id = clean_chat_id(config.get("chat_id"))
            if chat_id:
                allowed.add(chat_id)
    return allowed


def allowed_chat_ids(db_path: Path = DEFAULT_DB_PATH, extra: list[str] | None = None) -> set[str]:
    allowed = allowed_chat_ids_from_env() | allowed_chat_ids_from_db(db_path)
    for value in extra or []:
        chat_id = clean_chat_id(value)
        if chat_id:
            allowed.add(chat_id)
    return allowed


def chat_is_allowed(chat_id: str, *, allowed: set[str]) -> bool:
    return bool(chat_id and chat_id in allowed)


def main_menu_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Status", "callback_data": "status"},
                {"text": "Latest", "callback_data": "latest"},
            ],
            [
                {"text": "Dry scan", "callback_data": "scan:jobs-fast"},
                {"text": "Sources", "callback_data": "sources"},
            ],
        ]
    }


def help_text() -> str:
    return "\n".join(
        [
            "T-Sense bot",
            "",
            "Commands:",
            "/status - setup, source, run, and inbox status",
            "/latest - latest actionable cards and report",
            "/scan - run jobs-fast in dry-run mode",
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
            f"Latest run: {latest_run.get('status') or 'none'} {latest_run.get('profile_id') or ''}".strip(),
            f"Opportunity summary: {opportunity.get('title') or opportunity.get('status') or 'not ready'}",
        ]
    )


def latest_summary(snapshot: dict[str, Any]) -> str:
    opportunity = snapshot.get("opportunity_summary") if isinstance(snapshot.get("opportunity_summary"), dict) else {}
    title = str(opportunity.get("title") or "Latest results")
    detail = str(opportunity.get("detail") or opportunity.get("status") or "No latest summary yet.")
    lines = [title, detail]
    items = opportunity.get("items")
    if isinstance(items, list):
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("title") or item.get("label") or item.get("card_title") or "Item")
            rating = str(item.get("rating") or item.get("status") or "").strip()
            lines.append(f"- {label}" + (f" ({rating})" if rating else ""))
    runs = [item for item in snapshot.get("runs") or [] if isinstance(item, dict)]
    if runs:
        artifact = runs[0].get("report_artifact") if isinstance(runs[0].get("report_artifact"), dict) else {}
        display_path = str(artifact.get("display_path") or artifact.get("path") or "")
        if display_path:
            lines.append(f"Report: {display_path}")
    return "\n".join(lines)


def run_dry_scan(profile_id: str, *, timeout_seconds: int = 900) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,80}", profile_id):
        raise BotGatewayError("Unsupported profile id.")
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "monitor.py"),
        "run",
        "--profile-id",
        profile_id,
        "--config",
        str(DEFAULT_CONFIG_PATH),
        "--db",
        str(DEFAULT_DB_PATH),
        "--delivery-mode",
        "dry-run",
        "--format",
        "json",
    ]
    try:
        completed = subprocess.run(cmd, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise BotGatewayError("Dry scan timed out. Open Runs in Signal Desk for local diagnostics.") from exc
    if completed.returncode != 0:
        stderr = " ".join((completed.stderr or "").split())[:500]
        raise BotGatewayError(f"Dry scan failed. {stderr or 'Open Runs in Signal Desk for diagnostics.'}")
    snapshot = dashboard_snapshot()
    return "Dry scan finished.\n\n" + latest_summary(snapshot)


def clean_topic(value: str) -> str:
    topic = (value or "jobs").strip().casefold()
    return topic if re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", topic) else "jobs"


def deterministic_intent(text: str) -> BotIntent | None:
    clean = text.strip()
    lowered = clean.casefold()
    if not clean or lowered in {"/start", "start", "menu", "/help", "help", "帮助"}:
        return BotIntent(action="help")
    if lowered.startswith("/status") or lowered in {"status", "状态"}:
        return BotIntent(action="status")
    if lowered.startswith("/latest") or lowered in {"latest", "最近", "最新"}:
        return BotIntent(action="latest")
    if lowered.startswith("/profiles") or lowered in {"profiles", "profile", "配置"}:
        return BotIntent(action="profiles")
    if lowered.startswith("/settings") or lowered in {"settings", "设置"}:
        return BotIntent(action="settings")
    if lowered.startswith("/scan") or "dry scan" in lowered or "跑一次" in lowered or "扫描" in lowered:
        match = re.search(r"(?:/scan|profile)\s+([A-Za-z0-9][A-Za-z0-9_-]{1,80})", clean)
        return BotIntent(action="scan", profile_id=match.group(1) if match else "jobs-fast")
    if lowered.startswith("/sources") and len(clean.split()) <= 1:
        return BotIntent(action="sources_summary")
    source_words = ("source", "sources", "add ", "remove ", "delete ", "pause ", "disable ", "enable ", "resume ", "添加", "删除", "移除", "暂停", "启用")
    has_handle = bool(re.search(r"(?:@|t\.me/)[A-Za-z0-9_]{5,64}|-?\d{5,20}", clean))
    if lowered.startswith("/sources") or (has_handle and any(word in lowered for word in source_words)):
        instruction = re.sub(r"^/sources\s*", "", clean, flags=re.IGNORECASE).strip() or clean
        return BotIntent(action="sources_plan", instruction=instruction, topic="jobs", needs_confirmation=True)
    return None


def llm_intent(text: str) -> BotIntent | None:
    if not report.llm_key_available():
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)
    provider = report.llm_provider(base_url, model)
    api_key = report.api_key_for_provider(provider)
    if not api_key:
        return None
    system_prompt = (
        "Map a Telegram chat message to one T-Sense bot intent. Return JSON only. "
        "Allowed actions: help, status, latest, scan, sources_summary, sources_plan, profiles, settings. "
        "For source changes, put the original user instruction in instruction and set needs_confirmation true. "
        "Never return commands, file paths, shell, argv, tokens, or raw Telegram message data."
    )
    user_prompt = json.dumps(
        {
            "message": text[:2000],
            "schema": {
                "action": "status",
                "profile_id": "jobs-fast",
                "topic": "jobs",
                "instruction": "",
                "needs_confirmation": False,
            },
        },
        ensure_ascii=False,
    )
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": report.llm_temperature(provider),
    }
    if provider in {"deepseek", "openai"}:
        create_kwargs["response_format"] = {"type": "json_object"}
    thinking_extra = report.minimax_thinking_extra(provider) or report.deepseek_thinking_extra(provider, model)
    if thinking_extra:
        create_kwargs["extra_body"] = thinking_extra
    report.add_token_limit(create_kwargs, provider=provider, max_tokens=400)
    try:
        response = OpenAI(api_key=api_key, base_url=base_url).chat.completions.create(**create_kwargs)
        payload = json.loads(report.strip_json_fence(response.choices[0].message.content or "{}"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip()
    if action not in ALLOWED_INTENT_ACTIONS:
        return None
    instruction = str(payload.get("instruction") or "").strip()
    profile_id = str(payload.get("profile_id") or "jobs-fast").strip()
    topic = clean_topic(str(payload.get("topic") or "jobs"))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,80}", profile_id):
        profile_id = "jobs-fast"
    return BotIntent(
        action=action,
        profile_id=profile_id,
        topic=topic,
        instruction=instruction,
        needs_confirmation=bool(payload.get("needs_confirmation")) or action == "sources_plan",
        source="llm",
    )


def route_text_to_intent(text: str, *, use_llm: bool = False) -> BotIntent:
    deterministic = deterministic_intent(text)
    if deterministic:
        return deterministic
    if use_llm:
        routed = llm_intent(text)
        if routed:
            return routed
    return BotIntent(action="help")


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


class BotGateway:
    def __init__(
        self,
        api: TelegramBotApi,
        *,
        db_path: Path = DEFAULT_DB_PATH,
        use_llm: bool = False,
        allowed: set[str] | None = None,
        extra_allowed: list[str] | None = None,
    ):
        self.api = api
        self.db_path = db_path
        self.use_llm = use_llm
        self.extra_allowed = list(extra_allowed or [])
        self.fixed_allowed = allowed is not None
        self.allowed = allowed if allowed is not None else allowed_chat_ids(db_path, self.extra_allowed)
        self.pending_source_plans: dict[str, PendingSourcePlan] = {}

    def refresh_allowed(self) -> None:
        if not self.fixed_allowed:
            self.allowed = allowed_chat_ids(self.db_path, self.extra_allowed)

    def chat_is_allowed(self, chat_id: str) -> bool:
        self.refresh_allowed()
        return chat_is_allowed(chat_id, allowed=self.allowed)

    def prune_pending_source_plans(self) -> None:
        now = time.time()
        expired = [
            plan_id
            for plan_id, plan in self.pending_source_plans.items()
            if now - plan.created_at > PENDING_SOURCE_PLAN_TTL_SECONDS
        ]
        for plan_id in expired:
            self.pending_source_plans.pop(plan_id, None)

    def dispatch_intent(self, chat_id: str, intent: BotIntent) -> None:
        if intent.action == "help":
            self.api.send_message(chat_id, help_text(), reply_markup=main_menu_keyboard())
            return
        if intent.action == "status":
            self.api.send_message(chat_id, status_summary(dashboard_snapshot(self.db_path)))
            return
        if intent.action == "latest":
            self.api.send_message(chat_id, latest_summary(dashboard_snapshot(self.db_path)))
            return
        if intent.action == "profiles":
            self.api.send_message(chat_id, profile_summary(dashboard_snapshot(self.db_path)))
            return
        if intent.action == "settings":
            self.api.send_message(chat_id, settings_text())
            return
        if intent.action == "sources_summary":
            self.api.send_message(chat_id, source_summary())
            return
        if intent.action == "scan":
            self.api.send_message(chat_id, f"Running {intent.profile_id} as dry-run. This can take a minute.")
            self.api.send_message(chat_id, run_dry_scan(intent.profile_id))
            return
        if intent.action == "sources_plan":
            if not intent.instruction:
                self.api.send_message(chat_id, "Send a source instruction such as: add @remote_jobs or remove @old_jobs.")
                return
            preview, result = source_plan_preview(intent.instruction, intent.topic)
            operation_count = sum(int(result.get(key) or 0) for key in ("added_count", "updated_count", "removed_count", "enabled_count", "disabled_count"))
            if operation_count <= 0:
                self.api.send_message(chat_id, preview)
                return
            resolved_plan = result.get("resolved_plan") if isinstance(result.get("resolved_plan"), dict) else {}
            plan_id = secrets.token_urlsafe(8)
            self.prune_pending_source_plans()
            self.pending_source_plans[plan_id] = PendingSourcePlan(
                chat_id=chat_id,
                topic=intent.topic,
                resolved_plan=resolved_plan,
                created_at=time.time(),
            )
            self.api.send_message(
                chat_id,
                preview,
                reply_markup={"inline_keyboard": [[{"text": "Apply source plan", "callback_data": f"sources_apply:{plan_id}"}]]},
            )
            return
        self.api.send_message(chat_id, help_text(), reply_markup=main_menu_keyboard())

    def handle_text(self, chat_id: str, text: str) -> None:
        if not self.chat_is_allowed(chat_id):
            self.api.send_message(chat_id, unauthorized_text(), reply_markup=main_menu_keyboard())
            return
        intent = route_text_to_intent(text, use_llm=self.use_llm)
        self.dispatch_intent(chat_id, intent)

    def handle_callback(self, chat_id: str, callback_query_id: str, data: str) -> None:
        if not self.chat_is_allowed(chat_id):
            self.api.answer_callback_query(callback_query_id, "Open Signal Desk Settings to authorize this chat.")
            self.api.send_message(chat_id, unauthorized_text())
            return
        if data == "status":
            self.api.answer_callback_query(callback_query_id)
            self.dispatch_intent(chat_id, BotIntent(action="status"))
            return
        if data == "latest":
            self.api.answer_callback_query(callback_query_id)
            self.dispatch_intent(chat_id, BotIntent(action="latest"))
            return
        if data == "sources":
            self.api.answer_callback_query(callback_query_id)
            self.dispatch_intent(chat_id, BotIntent(action="sources_summary"))
            return
        if data.startswith("scan:"):
            self.api.answer_callback_query(callback_query_id, "Starting dry scan")
            self.dispatch_intent(chat_id, BotIntent(action="scan", profile_id=data.split(":", 1)[1] or "jobs-fast"))
            return
        if data.startswith("sources_apply:"):
            self.prune_pending_source_plans()
            plan_id = data.split(":", 1)[1]
            plan = self.pending_source_plans.get(plan_id)
            if not plan or plan.chat_id != chat_id:
                self.api.answer_callback_query(callback_query_id, "Source plan expired.")
                return
            self.api.answer_callback_query(callback_query_id, "Applying source plan")
            self.api.send_message(chat_id, apply_source_plan(plan.resolved_plan, plan.topic))
            self.pending_source_plans.pop(plan_id, None)
            return
        self.api.answer_callback_query(callback_query_id, "Unsupported action")

    def handle_update(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
            chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
            chat_id = clean_chat_id(chat.get("id"))
            data = str(callback.get("data") or "")
            callback_id = str(callback.get("id") or "")
            if chat_id and callback_id:
                self.handle_callback(chat_id, callback_id, data)
            return
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        chat_id = clean_chat_id(chat.get("id"))
        text = str(message.get("text") or "").strip()
        if chat_id and text:
            self.handle_text(chat_id, text)


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


def install_menu() -> None:
    TelegramBotApi(load_bot_token()).set_my_commands()


def run_loop(args: argparse.Namespace) -> int:
    token = load_bot_token()
    api = TelegramBotApi(token)
    if not args.skip_menu:
        api.set_my_commands()
    extra_allowed = args.allow_chat_id or []
    gateway = BotGateway(api, db_path=Path(args.db), use_llm=bool(args.llm) and not args.no_llm, extra_allowed=extra_allowed)
    state_path = Path(args.state)
    state = load_state(state_path)
    offset = state.get("offset") if isinstance(state.get("offset"), int) else None
    print("T-Sense bot gateway is running. Press Ctrl+C to stop.", flush=True)
    print(f"Authorized chats: {len(gateway.allowed)}", flush=True)
    while True:
        updates = api.get_updates(offset=offset, timeout_seconds=args.poll_timeout)
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1
                save_state({"offset": offset}, state_path)
            gateway.handle_update(update)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local T-Sense Telegram Bot gateway.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Long-poll Telegram Bot updates and run safe local actions.")
    run.add_argument("--db", default=str(DEFAULT_DB_PATH))
    run.add_argument("--state", default=str(DEFAULT_BOT_STATE_PATH))
    run.add_argument("--allow-chat-id", action="append", default=[], help="Authorize a Telegram chat id for this process.")
    run.add_argument("--poll-timeout", type=int, default=BOT_POLL_TIMEOUT_SECONDS)
    run.add_argument("--install-menu", action="store_true", help="Install the Telegram command menu before polling; this is now the default.")
    run.add_argument("--skip-menu", action="store_true", help="Skip command menu installation before polling.")
    run.add_argument("--llm", action="store_true", help="Opt in to optional LLM routing for free-form messages.")
    run.add_argument("--no-llm", action="store_true", help="Keep free-form routing local-only; this is the default.")
    run.set_defaults(func=run_loop)

    menu = subparsers.add_parser("install-menu", help="Install Telegram Bot command menu.")
    menu.set_defaults(func=lambda _args: install_menu() or 0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except BotGatewayError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
