"""CLI facade for the local T-Sense Telegram Bot gateway.

The gateway is split into Bot API, state/authorization, reply rendering, and
runtime modules.  This facade preserves the historical `scripts.bot_gateway`
API and keeps tests that monkeypatch facade-level helpers working.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    from scripts import bot_actions, bot_intents, dashboard_server, delivery, monitor_state
    from scripts import bot_api as _bot_api
    from scripts import bot_replies as _bot_replies
    from scripts import bot_runtime as _bot_runtime
    from scripts import bot_state as _bot_state
except ModuleNotFoundError:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts import bot_actions, bot_intents, dashboard_server, delivery, monitor_state
    from scripts import bot_api as _bot_api
    from scripts import bot_replies as _bot_replies
    from scripts import bot_runtime as _bot_runtime
    from scripts import bot_state as _bot_state

PROJECT_ROOT = _bot_api.PROJECT_ROOT
DEFAULT_DB_PATH = _bot_state.DEFAULT_DB_PATH
DEFAULT_BOT_STATE_PATH = _bot_state.DEFAULT_BOT_STATE_PATH
DEFAULT_BOT_LOCK_PATH = _bot_state.DEFAULT_BOT_LOCK_PATH
BOT_ALLOWED_CHAT_IDS_ENV = _bot_state.BOT_ALLOWED_CHAT_IDS_ENV
BOT_API_BASE_URL_ENV = _bot_api.BOT_API_BASE_URL_ENV
BOT_API_TIMEOUT_SECONDS = _bot_api.BOT_API_TIMEOUT_SECONDS
BOT_POLL_TIMEOUT_SECONDS = _bot_api.BOT_POLL_TIMEOUT_SECONDS
MAX_TELEGRAM_MESSAGE_LENGTH = _bot_api.MAX_TELEGRAM_MESSAGE_LENGTH
PENDING_SOURCE_PLAN_TTL_SECONDS = _bot_runtime.PENDING_SOURCE_PLAN_TTL_SECONDS
BOT_COMMANDS = _bot_api.BOT_COMMANDS
BOT_DISPLAY_NAME = _bot_api.BOT_DISPLAY_NAME
BOT_DESCRIPTION = _bot_api.BOT_DESCRIPTION
BOT_SHORT_DESCRIPTION = _bot_api.BOT_SHORT_DESCRIPTION
BOT_AVATAR_PATH = _bot_api.BOT_AVATAR_PATH
ALLOWED_INTENT_ACTIONS = _bot_replies.ALLOWED_INTENT_ACTIONS
BotIntent = _bot_replies.BotIntent

PendingSourcePlan = _bot_state.PendingSourcePlan
BotGatewayError = _bot_api.BotGatewayError
BotGatewayLock = _bot_state.BotGatewayLock
TelegramBotApi = _bot_api.TelegramBotApi

split_telegram_text = _bot_api.split_telegram_text
load_bot_token = _bot_api.load_bot_token

_lock_pid_alive = _bot_state._lock_pid_alive
_read_lock_pid = _bot_state._read_lock_pid
load_state = _bot_state.load_state
save_state = _bot_state.save_state
write_gateway_state = _bot_state.write_gateway_state
clean_chat_id = _bot_state.clean_chat_id
allowed_chat_ids_from_env = _bot_state.allowed_chat_ids_from_env
allowed_chat_ids_from_db = _bot_state.allowed_chat_ids_from_db
allowed_chat_ids = _bot_state.allowed_chat_ids
chat_is_allowed = _bot_state.chat_is_allowed

main_menu_keyboard = _bot_replies.main_menu_keyboard
help_text = _bot_replies.help_text
source_summary = _bot_replies.source_summary
profile_summary = _bot_replies.profile_summary
status_summary = _bot_replies.status_summary
latest_summary = _bot_replies.latest_summary
latest_actionable_card = _bot_replies.latest_actionable_card
lifecycle_keyboard = _bot_replies.lifecycle_keyboard
lifecycle_status_label = _bot_replies.lifecycle_status_label
card_action_summary = _bot_replies.card_action_summary
run_dry_scan = _bot_replies.run_dry_scan
clean_topic = _bot_replies.clean_topic
deterministic_intent = _bot_replies.deterministic_intent
llm_intent = _bot_replies.llm_intent
route_text_to_intent = _bot_replies.route_text_to_intent
source_plan_preview = _bot_replies.source_plan_preview
apply_source_plan = _bot_replies.apply_source_plan
unauthorized_text = _bot_replies.unauthorized_text
settings_text = _bot_replies.settings_text

_dashboard_snapshot_impl = _bot_replies.dashboard_snapshot
_apply_bot_identity_impl = _bot_api.apply_bot_identity
_BotGatewayImpl = _bot_runtime.BotGateway
_EXPORTED_MODULES = (bot_actions, bot_intents, dashboard_server, delivery, monitor_state, time)


def dashboard_snapshot(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    _sync_modules()
    return _dashboard_snapshot_impl(db_path)


def apply_bot_identity(api: TelegramBotApi | None = None) -> dict[str, Any]:
    _sync_modules()
    return _apply_bot_identity_impl(api)


_DASHBOARD_SNAPSHOT_WRAPPER = dashboard_snapshot


def _patched_or_impl(name: str, wrapper, impl):
    value = globals()[name]
    return impl if value is wrapper else value


def _sync_modules() -> None:
    _bot_api.PROJECT_ROOT = PROJECT_ROOT
    _bot_api.BOT_AVATAR_PATH = BOT_AVATAR_PATH
    _bot_state.PROJECT_ROOT = PROJECT_ROOT
    _bot_state.DEFAULT_DB_PATH = DEFAULT_DB_PATH
    _bot_state.DEFAULT_BOT_STATE_PATH = DEFAULT_BOT_STATE_PATH
    _bot_state.DEFAULT_BOT_LOCK_PATH = DEFAULT_BOT_LOCK_PATH
    _bot_replies.DEFAULT_DB_PATH = DEFAULT_DB_PATH
    _bot_runtime.DEFAULT_DB_PATH = DEFAULT_DB_PATH
    _bot_runtime.DEFAULT_BOT_STATE_PATH = DEFAULT_BOT_STATE_PATH
    _bot_runtime.DEFAULT_BOT_LOCK_PATH = DEFAULT_BOT_LOCK_PATH
    _bot_runtime.PENDING_SOURCE_PLAN_TTL_SECONDS = PENDING_SOURCE_PLAN_TTL_SECONDS
    _bot_runtime.dashboard_snapshot = _patched_or_impl(
        "dashboard_snapshot",
        _DASHBOARD_SNAPSHOT_WRAPPER,
        _dashboard_snapshot_impl,
    )
    _bot_runtime.source_summary = source_summary
    _bot_runtime.profile_summary = profile_summary
    _bot_runtime.status_summary = status_summary
    _bot_runtime.latest_summary = latest_summary
    _bot_runtime.latest_actionable_card = latest_actionable_card
    _bot_runtime.lifecycle_keyboard = lifecycle_keyboard
    _bot_runtime.lifecycle_status_label = lifecycle_status_label
    _bot_runtime.card_action_summary = card_action_summary
    _bot_runtime.route_text_to_intent = route_text_to_intent
    _bot_runtime.source_plan_preview = source_plan_preview
    _bot_runtime.apply_source_plan = apply_source_plan
    _bot_runtime.unauthorized_text = unauthorized_text
    _bot_runtime.settings_text = settings_text
    _bot_runtime.help_text = help_text
    _bot_runtime.main_menu_keyboard = main_menu_keyboard


class BotGateway(_BotGatewayImpl):
    def refresh_allowed(self) -> None:
        _sync_modules()
        return super().refresh_allowed()

    def chat_is_allowed(self, chat_id: str) -> bool:
        _sync_modules()
        return super().chat_is_allowed(chat_id)

    def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = "Markdown",
    ) -> None:
        _sync_modules()
        return super().send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)

    def prune_pending_source_plans(self) -> None:
        _sync_modules()
        return super().prune_pending_source_plans()

    def dispatch_intent(self, chat_id: str, intent: BotIntent) -> None:
        _sync_modules()
        return super().dispatch_intent(chat_id, intent)

    def handle_text(self, chat_id: str, text: str) -> None:
        _sync_modules()
        return super().handle_text(chat_id, text)

    def handle_callback(self, chat_id: str, callback_query_id: str, data: str) -> None:
        _sync_modules()
        return super().handle_callback(chat_id, callback_query_id, data)

    def handle_update(self, update: dict[str, Any]) -> None:
        _sync_modules()
        return super().handle_update(update)


def install_menu() -> None:
    _sync_modules()
    return _bot_runtime.install_menu()


def run_loop(args: argparse.Namespace) -> int:
    _sync_modules()
    return _bot_runtime.run_loop(args)


def autostart_status() -> dict[str, Any]:
    _sync_modules()
    return _bot_runtime.autostart_status()


def install_autostart() -> dict[str, Any]:
    _sync_modules()
    return _bot_runtime.install_autostart()


def remove_autostart() -> dict[str, Any]:
    _sync_modules()
    return _bot_runtime.remove_autostart()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local T-Sense Telegram Bot gateway.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Long-poll Telegram Bot updates and run safe local actions.")
    run.add_argument("--db", default=str(DEFAULT_DB_PATH))
    run.add_argument("--state", default=str(DEFAULT_BOT_STATE_PATH))
    run.add_argument("--lock", default=str(DEFAULT_BOT_LOCK_PATH))
    run.add_argument("--allow-chat-id", action="append", default=[], help="Authorize a Telegram chat id for this process.")
    run.add_argument("--poll-timeout", type=int, default=BOT_POLL_TIMEOUT_SECONDS)
    run.add_argument("--install-menu", action="store_true", help="Install the Telegram command menu before polling; this is now the default.")
    run.add_argument("--skip-menu", action="store_true", help="Skip command menu installation before polling.")
    run.add_argument("--llm", action="store_true", help="Use AI routing and knowledge answers when an AI API key is configured; this is the default.")
    run.add_argument("--no-llm", action="store_true", help="Keep free-form routing and knowledge answers local-only.")
    run.set_defaults(func=run_loop)

    menu = subparsers.add_parser("install-menu", help="Install Telegram Bot command menu.")
    menu.set_defaults(func=lambda _args: install_menu() or 0)
    identity = subparsers.add_parser("apply-identity", help="Apply T-Sense bot name, descriptions, and command menu.")
    identity.set_defaults(func=lambda _args: print(json.dumps(apply_bot_identity(), ensure_ascii=False)) or 0)
    status = subparsers.add_parser("status", help="Show local Bot Gateway and background status.")
    status.set_defaults(func=lambda _args: print(json.dumps(autostart_status(), ensure_ascii=False)) or 0)
    install_bg = subparsers.add_parser("install-autostart", help="Start Bot Gateway automatically at user login.")
    install_bg.set_defaults(func=lambda _args: print(json.dumps(install_autostart(), ensure_ascii=False)) or 0)
    remove_bg = subparsers.add_parser("remove-autostart", help="Remove the Bot Gateway login task.")
    remove_bg.set_defaults(func=lambda _args: print(json.dumps(remove_autostart(), ensure_ascii=False)) or 0)
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
