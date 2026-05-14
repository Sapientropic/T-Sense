"""POST route dispatch for local Signal Desk operations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote


def handle_operation_post_route(
    handler: Any,
    path: str,
    body: Mapping[str, Any],
    *,
    require_loopback_access: Callable[[Any, str], None],
    close_after_use: Callable[[Any], Any],
    monitor_state_module: Any,
    run_desk_action: Callable[[str], dict],
    git_update_status: Callable[..., dict],
    git_pull_latest: Callable[[], dict],
    git_confirmation_error: Callable[[str], Exception],
    write_feedback_export: Callable[[Any], dict],
) -> bool:
    if path.startswith("/api/desk/actions/") and path.endswith("/run"):
        require_loopback_access(handler, "Desk actions")
        action_id = unquote(path.removeprefix("/api/desk/actions/").removesuffix("/run").strip("/"))
        handler._json(HTTPStatus.OK, {"ok": True, "result": run_desk_action(action_id, body=body)})
        return True
    if path == "/api/git/check-updates":
        require_loopback_access(handler, "Git update")
        handler._json(HTTPStatus.OK, {"ok": True, "git": git_update_status(fetch=True)})
        return True
    if path == "/api/git/pull-latest":
        require_loopback_access(handler, "Git update")
        if body.get("confirm") is not True:
            raise git_confirmation_error("Pull latest requires explicit confirmation.")
        handler._json(HTTPStatus.OK, {"ok": True, "git": git_pull_latest()})
        return True
    if path == "/api/feedback/export":
        require_loopback_access(handler, "Feedback export")
        with close_after_use(handler._connect()) as conn:
            result = write_feedback_export(conn)
        handler._json(HTTPStatus.OK, {"ok": True, "export": result})
        return True
    if path == "/api/feedback/clear":
        require_loopback_access(handler, "Feedback clear")
        with close_after_use(handler._connect()) as conn:
            result = monitor_state_module.clear_feedback_decisions(conn)
        handler._json(HTTPStatus.OK, {"ok": True, "feedback": result})
        return True
    if path == "/api/feedback/profile-suggestions":
        require_loopback_access(handler, "Feedback profile suggestions")
        with close_after_use(handler._connect()) as conn:
            result = monitor_state_module.create_feedback_profile_patch_suggestions(conn)
        handler._json(HTTPStatus.OK, {"ok": True, "suggestions": result})
        return True
    if path.startswith("/api/review-cards/") and path.endswith("/undo"):
        require_loopback_access(handler, "Review card actions")
        card_id = unquote(path.split("/")[3])
        with close_after_use(handler._connect()) as conn:
            card = monitor_state_module.undo_card_action(conn, card_id=card_id)
        handler._json(HTTPStatus.OK, {"ok": True, "card": card})
        return True
    if path.startswith("/api/review-cards/") and path.endswith("/action"):
        require_loopback_access(handler, "Review card actions")
        card_id = unquote(path.split("/")[3])
        with close_after_use(handler._connect()) as conn:
            card = monitor_state_module.set_card_action(
                conn,
                card_id=card_id,
                action=str(body.get("action") or ""),
                note=str(body.get("note") or ""),
            )
        handler._json(HTTPStatus.OK, {"ok": True, "card": card})
        return True
    return False
