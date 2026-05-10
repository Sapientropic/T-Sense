"""User-facing diagnostics for scan reports.

This module keeps "why was my report empty?" logic out of report.py so the
renderer can stay focused on formatting. The diagnostics are intentionally
plain data first; Markdown and HTML rendering are thin projections.
"""

from __future__ import annotations

import html
from typing import Iterable


def _count_meta_list(meta: dict | None, key: str, count_key: str) -> tuple[int, list[str]]:
    if not meta:
        return 0, []
    values = meta.get(key)
    if isinstance(values, list):
        return len(values), [str(value) for value in values]
    count = meta.get(count_key)
    if isinstance(count, int):
        return count, []
    return 0, []


def _has_media_without_ocr(messages: Iterable[dict]) -> bool:
    for message in messages:
        if message.get("ocr_text"):
            continue
        if message.get("media_group") or message.get("has_photo") or message.get("media_type"):
            return True
    return False


def build_diagnostics(
    *,
    messages: list[dict],
    raw_items: list[dict],
    meta: dict | None,
    ocr_enabled: bool,
    llm_available: bool = True,
) -> list[dict]:
    diagnostics: list[dict] = []
    total_messages = len(messages)
    if meta and isinstance(meta.get("total_messages_collected"), int):
        total_messages = int(meta["total_messages_collected"])

    if meta is None:
        diagnostics.append(
            {
                "code": "missing_scan_metadata",
                "severity": "warning",
                "message": "Scan metadata sidecar was not found, so report stats are inferred from JSONL.",
                "next_step": "Keep the .meta.json file next to the scan JSONL when sharing or archiving reports.",
            }
        )

    failure_count, failed_channels = _count_meta_list(meta, "failed_channels", "failure_count")
    if failure_count:
        channel_hint = ", ".join(failed_channels[:5]) if failed_channels else f"{failure_count} channels"
        diagnostics.append(
            {
                "code": "channel_failures",
                "severity": "warning",
                "message": f"{failure_count} channels failed during scan: {channel_hint}.",
                "next_step": "Open the scan .errors.log file and fix access, username, or FloodWait issues.",
            }
        )

    incomplete_count, incomplete_channels = _count_meta_list(
        meta, "incomplete_channels", "incomplete_count"
    )
    if incomplete_count:
        channel_hint = ", ".join(incomplete_channels[:5]) if incomplete_channels else f"{incomplete_count} channels"
        diagnostics.append(
            {
                "code": "scan_incomplete",
                "severity": "warning",
                "message": f"{incomplete_count} channels may be incomplete: {channel_hint}.",
                "next_step": "Raise SCAN_MAX_LIMIT, narrow the time window, or rerun with --allow-incomplete only when acceptable.",
            }
        )

    if total_messages == 0:
        diagnostics.append(
            {
                "code": "no_messages_fetched",
                "severity": "failure",
                "message": "No Telegram messages were fetched for this report.",
                "next_step": "Check the channel list, login session, scan window, and output .errors.log before tuning the profile.",
            }
        )
    elif not raw_items and llm_available:
        diagnostics.append(
            {
                "code": "all_filtered_out",
                "severity": "info",
                "message": "The scan had messages, but the LLM/profile returned no useful items.",
                "next_step": "Preview the prompt with --dry-run-prompt, loosen the profile, or inspect raw messages for missed signal.",
            }
        )

    effective_ocr_enabled = bool(meta.get("ocr_enabled")) if meta else ocr_enabled
    if not effective_ocr_enabled and _has_media_without_ocr(messages):
        diagnostics.append(
            {
                "code": "ocr_disabled_media_present",
                "severity": "info",
                "message": "Some scanned messages contain media, but OCR/STT was disabled.",
                "next_step": "Rerun with --ocr only if media text is important and the provider privacy/cost tradeoff is acceptable.",
            }
        )

    if not llm_available:
        diagnostics.append(
            {
                "code": "llm_unavailable",
                "severity": "failure",
                "message": "The LLM provider is unavailable, so semantic extraction cannot run.",
                "next_step": "Install requirements-llm.txt and set OPENAI_API_KEY or DEEPSEEK_API_KEY, or use --dry-run-prompt for inspection.",
            }
        )

    return diagnostics


def render_markdown(diagnostics: list[dict]) -> str:
    if not diagnostics:
        return ""
    lines = ["## Diagnostics", ""]
    for item in diagnostics:
        severity = str(item.get("severity", "info")).upper()
        lines.append(f"- **{severity} / {item['code']}**: {item['message']}")
        lines.append(f"  Next: {item['next_step']}")
    return "\n".join(lines) + "\n"


def render_html(diagnostics: list[dict]) -> str:
    if not diagnostics:
        return ""
    has_blocker = any(str(item.get("severity", "info")) in {"failure", "warning"} for item in diagnostics)
    rows = []
    for item in diagnostics:
        severity = html.escape(str(item.get("severity", "info")), quote=True)
        code = html.escape(str(item.get("code", "")), quote=True)
        message = html.escape(str(item.get("message", "")), quote=True)
        next_step = html.escape(str(item.get("next_step", "")), quote=True)
        rows.append(
            f'<li class="diagnostic-item {severity}">'
            f'<span class="diagnostic-code">{severity} / {code}</span>'
            f'<span class="diagnostic-message">{message}</span>'
            f'<span class="diagnostic-next">Next: {next_step}</span>'
            "</li>"
        )
    body = '<ul class="diagnostic-list">' + "".join(rows) + "</ul>"
    if has_blocker:
        return (
            '<section class="diagnostics-panel" aria-label="Report diagnostics">'
            '<h2 class="diagnostics-title">Diagnostics</h2>'
            + body
            + "</section>"
        )
    return (
        '<details class="diagnostics-panel compact" aria-label="Report diagnostics">'
        '<summary><span class="diagnostics-title">Diagnostics</span>'
        f'<span class="diagnostics-count">Info {len(diagnostics)}</span></summary>'
        + body
        + "</details>"
    )
