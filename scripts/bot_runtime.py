"""Bot Gateway runtime loop and local background integration."""

from __future__ import annotations

import argparse
import secrets
import sys
import time
from pathlib import Path
from typing import Any

try:
    from scripts import bot_actions, dashboard_server, monitor_state
    from scripts.bot_api import BotGatewayError, TelegramBotApi, load_bot_token
    from scripts.bot_replies import (
        BotIntent,
        apply_source_plan,
        card_action_summary,
        dashboard_snapshot,
        help_text,
        latest_actionable_card,
        latest_summary,
        lifecycle_keyboard,
        lifecycle_status_label,
        main_menu_keyboard,
        profile_summary,
        route_text_to_intent,
        settings_text,
        source_plan_preview,
        source_summary,
        status_summary,
        unauthorized_text,
    )
    from scripts.bot_state import (
        DEFAULT_DB_PATH,
        BotGatewayLock,
        PendingSourcePlan,
        allowed_chat_ids,
        chat_is_allowed,
        clean_chat_id,
        load_state,
        write_gateway_state,
    )
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts import bot_actions, dashboard_server, monitor_state
    from scripts.bot_api import BotGatewayError, TelegramBotApi, load_bot_token
    from scripts.bot_replies import (
        BotIntent,
        apply_source_plan,
        card_action_summary,
        dashboard_snapshot,
        help_text,
        latest_actionable_card,
        latest_summary,
        lifecycle_keyboard,
        lifecycle_status_label,
        main_menu_keyboard,
        profile_summary,
        route_text_to_intent,
        settings_text,
        source_plan_preview,
        source_summary,
        status_summary,
        unauthorized_text,
    )
    from scripts.bot_state import (
        DEFAULT_DB_PATH,
        BotGatewayLock,
        PendingSourcePlan,
        allowed_chat_ids,
        chat_is_allowed,
        clean_chat_id,
        load_state,
        write_gateway_state,
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PENDING_SOURCE_PLAN_TTL_SECONDS = 15 * 60


def _runtime_error_text(exc: BaseException) -> str:
    return bot_actions.redact_telegram_reply(str(exc))[:500]


def _poll_error_sleep_seconds(poll_timeout: int) -> int:
    try:
        timeout = int(poll_timeout)
    except (TypeError, ValueError):
        timeout = 1
    return max(1, min(10, timeout or 1))



class BotGateway:
    def __init__(
        self,
        api: TelegramBotApi,
        *,
        db_path: Path = DEFAULT_DB_PATH,
        use_llm: bool = True,
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
        self.action_registry = bot_actions.BotActionRegistry()

    def refresh_allowed(self) -> None:
        if not self.fixed_allowed:
            self.allowed = allowed_chat_ids(self.db_path, self.extra_allowed)

    def chat_is_allowed(self, chat_id: str) -> bool:
        self.refresh_allowed()
        return chat_is_allowed(chat_id, allowed=self.allowed)

    def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = "Markdown",
    ) -> None:
        self.api.send_message(
            chat_id,
            bot_actions.redact_telegram_reply(text),
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

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
            self.send_message(chat_id, help_text(), reply_markup=main_menu_keyboard())
            return
        if intent.action == "status":
            self.send_message(chat_id, status_summary(dashboard_snapshot(self.db_path)))
            return
        if intent.action == "latest":
            snapshot = dashboard_snapshot(self.db_path)
            card = latest_actionable_card(snapshot)
            self.send_message(chat_id, latest_summary(snapshot), reply_markup=lifecycle_keyboard(card or {}))
            return
        if intent.action == "profiles":
            self.send_message(chat_id, profile_summary(dashboard_snapshot(self.db_path)))
            return
        if intent.action == "settings":
            self.send_message(chat_id, settings_text())
            return
        if intent.action == "sources_summary":
            self.send_message(chat_id, source_summary())
            return
        if intent.action == "knowledge_answer":
            result = self.action_registry.execute(intent)
            self.send_message(chat_id, result.text, reply_markup=result.reply_markup)
            return
        if intent.action in {"scan", "scan_profile_dry_run"}:
            if intent.profile_id == "jobs-fast":
                self.send_message(chat_id, f"Running an AI review for {intent.profile_id}. This can take a minute.")
            result = self.action_registry.execute(
                BotIntent(action="scan_profile_dry_run", args={"profile_id": intent.profile_id})
            )
            self.send_message(chat_id, result.text, reply_markup=result.reply_markup)
            return
        if intent.action == "sources_plan":
            if not intent.instruction:
                self.send_message(chat_id, "Send a source instruction such as: add @remote_jobs or remove @old_jobs.")
                return
            preview, result = source_plan_preview(intent.instruction, intent.topic)
            operation_count = sum(int(result.get(key) or 0) for key in ("added_count", "updated_count", "removed_count", "enabled_count", "disabled_count"))
            if operation_count <= 0:
                self.send_message(chat_id, preview)
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
            self.send_message(
                chat_id,
                preview,
                reply_markup={"inline_keyboard": [[{"text": "Apply source plan", "callback_data": f"sources_apply:{plan_id}"}]]},
            )
            return
        self.send_message(chat_id, help_text(), reply_markup=main_menu_keyboard())

    def handle_text(self, chat_id: str, text: str) -> None:
        if not self.chat_is_allowed(chat_id):
            self.send_message(chat_id, unauthorized_text(), reply_markup=main_menu_keyboard())
            return
        intent = route_text_to_intent(text, use_llm=self.use_llm)
        self.dispatch_intent(chat_id, intent)

    def handle_callback(self, chat_id: str, callback_query_id: str, data: str) -> None:
        if not self.chat_is_allowed(chat_id):
            self.api.answer_callback_query(callback_query_id, "Open Signal Desk Settings to authorize this chat.")
            self.send_message(chat_id, unauthorized_text())
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
        if data == "profiles":
            self.api.answer_callback_query(callback_query_id)
            self.dispatch_intent(chat_id, BotIntent(action="profiles"))
            return
        if data == "settings":
            self.api.answer_callback_query(callback_query_id)
            self.dispatch_intent(chat_id, BotIntent(action="settings"))
            return
        if data.startswith("scan:"):
            self.api.answer_callback_query(callback_query_id, "Starting AI review")
            self.dispatch_intent(
                chat_id,
                BotIntent(action="scan_profile_dry_run", args={"profile_id": data.split(":", 1)[1] or "jobs-fast"}),
            )
            return
        if data.startswith("sources_apply:"):
            self.prune_pending_source_plans()
            plan_id = data.split(":", 1)[1]
            plan = self.pending_source_plans.get(plan_id)
            if not plan or plan.chat_id != chat_id:
                self.api.answer_callback_query(callback_query_id, "Source plan expired.")
                return
            self.api.answer_callback_query(callback_query_id, "Applying source plan")
            self.send_message(chat_id, apply_source_plan(plan.resolved_plan, plan.topic))
            self.pending_source_plans.pop(plan_id, None)
            return
        if data.startswith("card:"):
            parts = data.split(":", 2)
            if len(parts) != 3:
                self.api.answer_callback_query(callback_query_id, "Card action expired.")
                return
            _, action, card_id = parts
            if action not in monitor_state.LIFECYCLE_ACTIONS:
                self.api.answer_callback_query(callback_query_id, "Unsupported card action.")
                return
            try:
                conn = monitor_state.connect(self.db_path)
                try:
                    card = monitor_state.set_card_action(conn, card_id=card_id, action=action)
                finally:
                    conn.close()
            except monitor_state.MonitorStateError:
                self.api.answer_callback_query(callback_query_id, "Card is no longer available.")
                return
            label = lifecycle_status_label(card.get("opportunity_status"))
            self.api.answer_callback_query(callback_query_id, f"Marked {label}")
            self.send_message(chat_id, card_action_summary(card), reply_markup=lifecycle_keyboard(card) if card.get("opportunity_status") == "open" else None)
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



def install_menu() -> None:
    TelegramBotApi(load_bot_token()).set_my_commands()



def run_loop(args: argparse.Namespace) -> int:
    with BotGatewayLock(Path(args.lock)):
        token = load_bot_token()
        api = TelegramBotApi(token)
        commands_installed = False
        last_error = ""
        if not args.skip_menu:
            try:
                api.set_my_commands()
            except BotGatewayError as exc:
                # Command menu setup is useful discovery chrome, not the
                # message pump itself. A transient Bot API failure here should
                # not leave the local-first bot silent until the next login.
                last_error = _runtime_error_text(exc)
                print(f"Bot Gateway setup warning: {last_error}", file=sys.stderr, flush=True)
            else:
                commands_installed = True
        extra_allowed = args.allow_chat_id or []
        gateway = BotGateway(api, db_path=Path(args.db), use_llm=not bool(args.no_llm), extra_allowed=extra_allowed)
        state_path = Path(args.state)
        state = load_state(state_path)
        offset = state.get("offset") if isinstance(state.get("offset"), int) else None
        started_at = monitor_state.utc_now()
        write_gateway_state(
            state_path,
            offset=offset,
            started_at=started_at,
            authorized_chat_count=len(gateway.allowed),
            commands_installed=commands_installed,
            last_error=last_error,
        )
        print("T-Sense bot gateway is running. Press Ctrl+C to stop.", flush=True)
        print(f"Authorized chats: {len(gateway.allowed)}", flush=True)
        while True:
            try:
                updates = api.get_updates(offset=offset, timeout_seconds=args.poll_timeout)
            except BotGatewayError as exc:
                last_error = _runtime_error_text(exc)
                write_gateway_state(
                    state_path,
                    offset=offset,
                    started_at=started_at,
                    authorized_chat_count=len(gateway.allowed),
                    commands_installed=commands_installed,
                    last_error=last_error,
                )
                print(f"Bot Gateway polling warning: {last_error}", file=sys.stderr, flush=True)
                time.sleep(_poll_error_sleep_seconds(args.poll_timeout))
                continue
            gateway.refresh_allowed()
            update_errors: list[str] = []
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                try:
                    gateway.handle_update(update)
                except Exception as exc:
                    update_errors.append(_runtime_error_text(exc))
            last_error = update_errors[-1] if update_errors else ""
            if last_error:
                print(f"Bot Gateway update warning: {last_error}", file=sys.stderr, flush=True)
            write_gateway_state(
                state_path,
                offset=offset,
                started_at=started_at,
                authorized_chat_count=len(gateway.allowed),
                commands_installed=commands_installed,
                last_error=last_error,
            )



def autostart_status() -> dict[str, Any]:
    conn = monitor_state.connect(DEFAULT_DB_PATH)
    try:
        return dashboard_server.desk_bot_gateway_status(conn)
    finally:
        conn.close()



def install_autostart() -> dict[str, Any]:
    return dashboard_server.run_desk_action("bot_gateway_install_autostart", body={"confirm": True})



def remove_autostart() -> dict[str, Any]:
    return dashboard_server.run_desk_action("bot_gateway_remove_autostart", body={"confirm": True})
