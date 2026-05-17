"""Profile patch suggestion lifecycle for monitor state."""

from __future__ import annotations

import difflib
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from scripts.item_display import display_item_title
from scripts.monitor_common import (
    MonitorStateError,
    PROFILE_PATCH_SCHEMA_VERSION,
    PROJECT_ROOT,
    parse_json,
    require_profile_text_without_private_fragments,
    sha256_text,
    utc_now,
)


REVIEW_LEARNING_PATCH_NOTE = "Signal Desk Review learning batch: combine Review decisions into future matching rules."


def _patch_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema_version": PROFILE_PATCH_SCHEMA_VERSION,
        "patch_id": row["patch_id"],
        "profile_id": row["profile_id"],
        "card_id": row["card_id"],
        "note": row["note"],
        "status": row["status"],
        "diff_text": row["diff_text"],
        "proposed_profile_text": row["proposed_profile_text"],
        "base_profile_hash": row["base_profile_hash"],
        "created_at": row["created_at"],
        "applied_at": row["applied_at"],
    }


def _project_root() -> Path:
    facade = sys.modules.get("scripts.monitor_state")
    root = getattr(facade, "PROJECT_ROOT", PROJECT_ROOT) if facade is not None else PROJECT_ROOT
    return Path(root)


def _append_follow_up_rule(profile_text: str, note: str) -> str:
    lines = _profile_patch_preference_lines(profile_text=profile_text, note=note)
    return _append_follow_up_rules(profile_text, lines)


def _append_follow_up_rules(profile_text: str, preferences: list[str]) -> str:
    lines_to_add = _normalize_preference_lines("\n".join(preferences))
    if not lines_to_add:
        lines_to_add = ["Exclude future matches that do not clearly satisfy this profile's stated requirements."]
    heading = "## Follow-up Preferences"
    if heading not in profile_text:
        suffix = "\n\n" if profile_text.endswith("\n") else "\n\n"
        return f"{profile_text}{suffix}{heading}\n" + "\n".join(f"- {line}" for line in lines_to_add) + "\n"
    lines = profile_text.splitlines()
    output: list[str] = []
    inserted = False
    in_section = False
    existing_keys: set[str] = set()
    for raw in lines:
        line = re.sub(r"^\s*[-*]\s+", "", raw).strip()
        if line and not line.startswith("## "):
            existing_keys.add(" ".join(line.split()).casefold())
    insert_lines = [f"- {line}" for line in lines_to_add if line.casefold() not in existing_keys]
    if not insert_lines:
        return profile_text.rstrip() + "\n"
    for raw in lines:
        if raw.strip() == heading:
            in_section = True
            output.append(raw)
            continue
        if in_section and raw.startswith("## "):
            output.extend(insert_lines)
            inserted = True
            in_section = False
        output.append(raw)
    if in_section and not inserted:
        output.extend(insert_lines)
    return "\n".join(output).rstrip() + "\n"


def _profile_patch_preference_lines(
    *,
    profile_text: str,
    note: str,
    feedback_context: list[dict[str, Any]] | None = None,
) -> list[str]:
    lines = _llm_profile_patch_preference_lines(
        profile_text=profile_text,
        note=note,
        feedback_context=feedback_context or [],
    )
    if lines:
        return lines
    return _fallback_profile_patch_preference_lines(note=note, feedback_context=feedback_context or [])


def _llm_profile_patch_preference_lines(
    *,
    profile_text: str,
    note: str,
    feedback_context: list[dict[str, Any]],
) -> list[str]:
    if os.environ.get("TGCS_PROFILE_PATCH_DISABLE_LLM") == "1":
        return []
    try:
        from openai import OpenAI
        from scripts.report_extraction import (
            DEFAULT_MODEL,
            add_token_limit,
            api_key_for_provider,
            deepseek_thinking_extra,
            llm_provider,
            llm_temperature,
            minimax_thinking_extra,
            resolve_llm_settings,
        )
    except ImportError:
        return []

    base_url, model = resolve_llm_settings(None, DEFAULT_MODEL)
    provider = llm_provider(base_url, model)
    api_key = api_key_for_provider(provider)
    if not api_key:
        return []
    context = [
        {
            "action": str(item.get("action") or ""),
            "title": str(item.get("title") or "")[:160],
            "note": str(item.get("note") or "")[:240],
            "card": item.get("card") if isinstance(item.get("card"), dict) else {},
        }
        for item in feedback_context[:12]
        if isinstance(item, dict)
    ]
    system_prompt = """You rewrite Signal Desk review learning signals into durable matching-profile rules.

Return JSON only:
{"preferences":["..."]}

Rules:
- Review cards are evidence; the note is a future-matching learning signal, not a per-card annotation.
- Read every card together with its note before deciding the direction of the rule.
- Write broad reusable matching rules, not one-off card titles.
- Do not quote the user's raw note verbatim.
- Do not include secrets, local paths, command lines, or provider names.
- Keep each preference under 180 characters.
- Prefer concrete exclusions/priorities a future scan can apply.
- Infer rule direction from the current profile plus repeated feedback.
"""
    user_prompt = json.dumps(
        {
            "current_profile": profile_text[:8000],
            "draft_source": note,
            "review_learning_signals": context,
            "task": "Suggest 1-4 durable Follow-up Preferences that improve future matching for this profile.",
        },
        ensure_ascii=False,
    )
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": llm_temperature(provider),
    }
    if provider in {"deepseek", "openai"}:
        create_kwargs["response_format"] = {"type": "json_object"}
    thinking_extra = minimax_thinking_extra(provider) or deepseek_thinking_extra(provider, model)
    if thinking_extra:
        create_kwargs["extra_body"] = thinking_extra
    add_token_limit(create_kwargs, provider=provider, max_tokens=650)
    try:
        response = OpenAI(api_key=api_key, base_url=base_url).chat.completions.create(**create_kwargs)
    except Exception as exc:
        raise MonitorStateError(f"AI profile draft failed: {exc}") from exc
    raw_response = response.choices[0].message.content or ""
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise MonitorStateError("AI profile draft returned invalid JSON; try again.") from exc
    preferences = payload.get("preferences")
    if not isinstance(preferences, list):
        raise MonitorStateError("AI profile draft did not return preferences; try again.")
    cleaned: list[str] = []
    raw_note_keys = {
        " ".join(str(value or "").split()).casefold()
        for value in [note, *(item.get("note") for item in context if isinstance(item, dict))]
        if str(value or "").strip()
    }
    for item in preferences:
        line = " ".join(str(item or "").split())
        if not line:
            continue
        line = require_profile_text_without_private_fragments("AI profile preference", line)
        line_key = line.casefold()
        if any(raw_note_key and (line_key == raw_note_key or raw_note_key in line_key) for raw_note_key in raw_note_keys):
            continue
        cleaned.append(line)
    return _normalize_preference_lines("\n".join(cleaned))


def _fallback_profile_patch_preference_lines(*, note: str, feedback_context: list[dict[str, Any]]) -> list[str]:
    combined_notes = " ".join(
        [
            str(note or ""),
            *[str(item.get("note") or "") for item in feedback_context if isinstance(item, dict)],
        ]
    )
    normalized = " ".join(combined_notes.split()).casefold()
    context_actions = {str(item.get("action") or "").casefold() for item in feedback_context if isinstance(item, dict)}
    if "full stack" in normalized and any(token in normalized for token in ("not", "不是", "非")):
        return ["Exclude full-stack roles; prefer opportunities with a focused frontend, backend, or specialist scope."]
    if any(token in normalized for token in ("not a fit", "wrong match", "false positive", "不合适", "不匹配")):
        return ["Exclude matches that do not clearly satisfy the profile's role, stack, seniority, and work-mode requirements."]
    if note.startswith("Desk feedback tuning") or context_actions.intersection({"skip", "false_positive"}):
        return ["Down-rank recurring wrong-match patterns unless the item clearly satisfies the profile's core requirements."]
    return ["Require future matches to clearly satisfy the profile's stated role, stack, seniority, location, and work-mode requirements."]


def _normalize_preference_lines(text: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = re.sub(r"^\s*[-*]\s+", "", raw).strip()
        line = re.sub(r"^\d+\.\s+", "", line)
        line = " ".join(line.split())
        if not line:
            continue
        line = _canonical_preference_line(line)
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines[:24]


def _canonical_preference_line(line: str) -> str:
    normalized = " ".join(line.split()).casefold()
    if _looks_like_durable_preference_rule(normalized):
        return line
    if _mentions_full_stack(normalized) and _mentions_negative_preference(normalized):
        return "Exclude full-stack roles; prefer opportunities with a focused frontend, backend, or specialist scope."
    if _mentions_lead_role(normalized) and _mentions_negative_preference(normalized):
        return "Exclude lead-only roles unless the profile explicitly asks for leadership scope."
    return line


def _looks_like_durable_preference_rule(normalized: str) -> bool:
    return normalized.startswith(("exclude ", "avoid ", "reject ", "skip ", "down-rank ", "downrank "))


def _mentions_full_stack(normalized: str) -> bool:
    return bool(re.search(r"\bfull[-\s]?stack\b", normalized))


def _mentions_lead_role(normalized: str) -> bool:
    return bool(re.search(r"\b(?:lead|leader|manager|management)\b", normalized))


def _mentions_negative_preference(normalized: str) -> bool:
    return bool(
        re.search(r"\b(?:not|no|never|exclude|avoid|without|don't|do not|doesn't|isn't|reject|skip)\b", normalized)
        or re.search(r"不要|不想|不是|非|排除|拒绝|避免", normalized)
    )


def _replace_follow_up_preferences(profile_text: str, preferences_text: str) -> str:
    lines_to_write = [f"- {line}" for line in _normalize_preference_lines(preferences_text)]
    if not lines_to_write:
        lines_to_write = ["- No extra learned preferences yet."]
    heading = "## Follow-up Preferences"
    replacement = [heading, *lines_to_write]
    lines = profile_text.splitlines()
    output: list[str] = []
    index = 0
    replaced = False
    while index < len(lines):
        raw = lines[index]
        if raw.strip() == heading:
            output.extend(replacement)
            replaced = True
            index += 1
            while index < len(lines) and not lines[index].startswith("## "):
                index += 1
            continue
        output.append(raw)
        index += 1
    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.extend(replacement)
    return "\n".join(output).rstrip() + "\n"


def dashboard_profile_file_path(profile_path: object) -> Path:
    raw = str(profile_path or "").strip()
    if not raw:
        raise MonitorStateError("Profile path is missing.")
    path = Path(raw)
    project_root = _project_root()
    if not path.is_absolute():
        path = project_root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise MonitorStateError("Profile file path must stay inside the project workspace.") from exc
    return resolved


def profile_patch_feedback_context(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    note: str | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    note_filter = "" if note == REVIEW_LEARNING_PATCH_NOTE else str(note or "")
    where_note = "AND f.note = ?" if note_filter else ""
    params: list[Any] = [profile_id]
    if note_filter:
        params.append(note_filter)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT f.action, f.note, c.title, c.item_json
        FROM feedback_events f
        LEFT JOIN review_cards c ON c.card_id = f.card_id
        WHERE f.profile_id = ?
          AND f.action = 'follow_up'
          {where_note}
        ORDER BY f.created_at DESC, f.event_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    context: list[dict[str, Any]] = []
    for row in rows:
        item = parse_json(row["item_json"], {})
        card = _compact_feedback_card(item if isinstance(item, dict) else {})
        context.append(
            {
                "action": row["action"] or "",
                "note": row["note"] or "",
                "title": display_item_title(item if isinstance(item, dict) else {}, fallback=row["title"] or "", max_len=160),
                "card": card,
            }
        )
    return context


def profile_coach_preview(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    confirm_external_ai: bool = False,
) -> dict[str, Any]:
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        raise MonitorStateError("Profile id is required.")
    row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    if not row:
        raise MonitorStateError(f"Profile is not registered: {profile_id}")
    profile_path = dashboard_profile_file_path(row["path"])
    if not profile_path.exists():
        raise MonitorStateError(f"Profile file not found: {profile_path}")
    profile_text = profile_path.read_text(encoding="utf-8")
    require_profile_text_without_private_fragments("Current profile", profile_text)
    counts = _profile_coach_evidence_counts(conn, profile_id)
    context = profile_patch_feedback_context(conn, profile_id=profile_id, note=REVIEW_LEARNING_PATCH_NOTE, limit=24)
    warnings: list[str] = []
    suggested_rules: list[str] = []
    llm_used = False
    if context:
        if confirm_external_ai:
            try:
                suggested_rules = _llm_profile_patch_preference_lines(
                    profile_text=profile_text,
                    note=REVIEW_LEARNING_PATCH_NOTE,
                    feedback_context=context,
                )
                llm_used = bool(suggested_rules)
            except MonitorStateError:
                warnings.append("Smart suggestions were unavailable, so Signal Desk drafted conservative rules from Review choices.")
            if not suggested_rules:
                suggested_rules = _fallback_profile_patch_preference_lines(
                    note=REVIEW_LEARNING_PATCH_NOTE,
                    feedback_context=context,
                )
        else:
            suggested_rules = _fallback_profile_patch_preference_lines(
                note=REVIEW_LEARNING_PATCH_NOTE,
                feedback_context=context,
            )
    elif counts.get("false_positive", 0):
        suggested_rules = ["Down-rank recurring wrong-match patterns unless the item clearly satisfies the profile's core requirements."]

    suggested_rules = _normalize_preference_lines("\n".join(suggested_rules))
    status = "ready" if suggested_rules or sum(counts.values()) > 0 else "needs_evidence"
    diagnosis = _profile_coach_diagnosis(counts, has_context=bool(context), has_rules=bool(suggested_rules))
    source_suggestions = _profile_coach_source_suggestions(counts)
    return {
        "schema_version": "profile_coach_preview_v1",
        "status": status,
        "profile_id": profile_id,
        "stage": "coach_diagnosis" if status == "ready" else "review_evidence",
        "evidence_counts": counts,
        "diagnosis": diagnosis,
        "suspected_false_positive_patterns": _profile_coach_false_positive_patterns(counts, suggested_rules),
        "suggested_preference_rules": suggested_rules,
        "source_suggestions": source_suggestions,
        "confidence": _profile_coach_confidence(counts, suggested_rules),
        "warnings": warnings,
        "llm_used": llm_used,
    }


def _profile_coach_evidence_counts(conn: sqlite3.Connection, profile_id: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT action, COUNT(*) AS count
        FROM feedback_events
        WHERE profile_id = ?
          AND action IN ('keep', 'skip', 'false_positive', 'follow_up')
        GROUP BY action
        """,
        (profile_id,),
    ).fetchall()
    counts = {"keep": 0, "skip": 0, "false_positive": 0, "follow_up": 0}
    for row in rows:
        action = str(row["action"] or "")
        if action in counts:
            counts[action] = int(row["count"] or 0)
    return counts


def _profile_coach_diagnosis(counts: dict[str, int], *, has_context: bool, has_rules: bool) -> list[dict[str, str]]:
    total = sum(counts.values())
    if total <= 0:
        return [
            {
                "label": "Review evidence",
                "detail": "No saved Review choices yet. Mark a few cards as keep, skip, wrong match, or add notes first.",
            }
        ]
    diagnosis: list[dict[str, str]] = []
    if counts.get("false_positive", 0):
        diagnosis.append(
            {
                "label": "Too many wrong matches",
                "detail": "Recent Review choices suggest this profile needs clearer ignore rules.",
            }
        )
    if counts.get("follow_up", 0) and has_context:
        diagnosis.append(
            {
                "label": "Notes can become rules",
                "detail": "Saved notes can be turned into reusable matching rules after you review them.",
            }
        )
    if counts.get("keep", 0) and counts.get("skip", 0):
        diagnosis.append(
            {
                "label": "Clearer boundaries",
                "detail": "Keep and skip choices give Signal Desk examples of what should and should not match.",
            }
        )
    if not diagnosis:
        diagnosis.append(
            {
                "label": "Needs more examples",
                "detail": "There is feedback, but not enough repeated pattern evidence for a confident rule.",
            }
        )
    if has_rules:
        diagnosis.append(
            {
                "label": "Ready to review",
                "detail": "Suggested rules are ready for a draft. The profile will not change until you approve it.",
            }
        )
    return diagnosis[:4]


def _profile_coach_false_positive_patterns(counts: dict[str, int], suggested_rules: list[str]) -> list[str]:
    patterns: list[str] = []
    combined = " ".join(suggested_rules).casefold()
    if "full-stack" in combined or "full stack" in combined:
        patterns.append("Full-stack generalist items without clear profile fit")
    if counts.get("false_positive", 0):
        patterns.append("Recurring wrong-match items that satisfy keywords but not core criteria")
    return patterns[:4]


def _profile_coach_source_suggestions(counts: dict[str, int]) -> list[dict[str, str]]:
    if counts.get("false_positive", 0) <= 0 and counts.get("skip", 0) <= 1:
        return []
    return [
        {
            "kind": "review_sources",
            "label": "Review noisy sources",
            "detail": "If wrong matches come from the same channel, review that source before changing the profile.",
        }
    ]


def _profile_coach_confidence(counts: dict[str, int], suggested_rules: list[str]) -> str:
    evidence = sum(counts.values())
    if len(suggested_rules) >= 2 and evidence >= 4:
        return "high"
    if suggested_rules and evidence >= 1:
        return "medium"
    return "low"


def _compact_feedback_card(item: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = [
        "topic",
        "title",
        "company",
        "role",
        "summary",
        "description",
        "location",
        "work_mode",
        "employment_type",
        "stack",
        "tags",
        "rating",
        "why",
    ]
    compact: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in item:
            continue
        value = _safe_card_context_value(item.get(key))
        if not _is_empty_card_context_value(value):
            compact[key] = value
    decision_state = item.get("decision_state")
    if isinstance(decision_state, dict):
        signals = _safe_card_context_value(decision_state.get("signals"))
        if signals:
            compact["signals"] = signals
        status = _safe_card_context_value(decision_state.get("status"))
        if status:
            compact["decision_status"] = status
    return compact


def profile_patch_card_context(item: dict[str, Any]) -> dict[str, Any]:
    return _compact_feedback_card(item)


def _safe_card_context_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        text = " ".join(value.split())[:500]
        if not text:
            return ""
        try:
            require_profile_text_without_private_fragments("Review card context", text)
        except MonitorStateError:
            return ""
        return text
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        output = [_safe_card_context_value(item) for item in value[:8]]
        return [item for item in output if not _is_empty_card_context_value(item)]
    return ""


def _is_empty_card_context_value(value: Any) -> bool:
    # Review card metadata may contain lists; emptiness checks here must not
    # require values to be hashable or Learning suggestions can crash.
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    if isinstance(value, list):
        return len(value) == 0
    return False


def create_profile_patch_suggestion(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    card_id: str | None,
    note: str,
    profile_path: Path | None,
    feedback_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    note = require_profile_text_without_private_fragments("Profile note", note)
    existing = conn.execute(
        """
        SELECT *
        FROM profile_patch_suggestions
        WHERE profile_id = ?
          AND note = ?
          AND status = 'pending'
        ORDER BY created_at DESC, patch_id DESC
        LIMIT 1
        """,
        (profile_id, note),
    ).fetchone()
    if profile_path is None:
        row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
        if not row:
            raise MonitorStateError(f"Profile is not registered: {profile_id}")
        profile_path = dashboard_profile_file_path(row["path"])
    if not profile_path.exists():
        raise MonitorStateError(f"Profile file not found: {profile_path}")
    current = profile_path.read_text(encoding="utf-8")
    require_profile_text_without_private_fragments("Current profile", current)
    base_profile_hash = sha256_text(current)
    context = feedback_context if feedback_context is not None else profile_patch_feedback_context(conn, profile_id=profile_id, note=note)
    preference_lines = _profile_patch_preference_lines(profile_text=current, note=note, feedback_context=context)
    proposed = _append_follow_up_rules(current, preference_lines)
    require_profile_text_without_private_fragments("Proposed profile", proposed)
    diff = "\n".join(
        difflib.unified_diff(
            current.splitlines(),
            proposed.splitlines(),
            fromfile="current-profile",
            tofile="proposed-profile",
            lineterm="",
        )
    )
    now = utc_now()
    if existing:
        # One Review-learning draft can represent many cards with different
        # notes. Keep one live profile-level draft so applying it cannot make
        # sibling drafts stale, but let the representative card follow the
        # current feedback set after undo/reclassify operations.
        existing_card_id = str(existing["card_id"] or "")
        next_card_id = card_id if note == REVIEW_LEARNING_PATCH_NOTE else (existing_card_id or card_id)
        conn.execute(
            """
            UPDATE profile_patch_suggestions
            SET card_id = ?,
                diff_text = ?,
                proposed_profile_text = ?,
                base_profile_hash = ?,
                created_at = ?
            WHERE patch_id = ?
            """,
            (
                next_card_id,
                diff,
                proposed,
                base_profile_hash,
                now,
                existing["patch_id"],
            ),
        )
        refreshed = conn.execute(
            "SELECT * FROM profile_patch_suggestions WHERE patch_id = ?",
            (existing["patch_id"],),
        ).fetchone()
        return _patch_from_row(refreshed)
    patch = {
        "schema_version": PROFILE_PATCH_SCHEMA_VERSION,
        "patch_id": "patch_" + uuid.uuid4().hex,
        "profile_id": profile_id,
        "card_id": card_id,
        "note": note,
        "status": "pending",
        "diff_text": diff,
        "proposed_profile_text": proposed,
        "base_profile_hash": base_profile_hash,
        "created_at": now,
        "applied_at": None,
    }
    conn.execute(
        """
        INSERT INTO profile_patch_suggestions(
            patch_id, profile_id, card_id, note, status, diff_text,
            proposed_profile_text, base_profile_hash, created_at, applied_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patch["patch_id"],
            profile_id,
            card_id,
            note,
            "pending",
            diff,
            proposed,
            base_profile_hash,
            now,
            None,
        ),
    )
    return patch


def sync_review_learning_profile_patch_suggestion(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    profile_path: Path | None = None,
) -> dict[str, Any] | None:
    context = profile_patch_feedback_context(conn, profile_id=profile_id, note=REVIEW_LEARNING_PATCH_NOTE)
    if not context:
        conn.execute(
            """
            DELETE FROM profile_patch_suggestions
            WHERE profile_id = ?
              AND note = ?
              AND status = 'pending'
            """,
            (profile_id, REVIEW_LEARNING_PATCH_NOTE),
        )
        return None
    card_row = conn.execute(
        """
        SELECT card_id
        FROM feedback_events
        WHERE profile_id = ?
          AND action = 'follow_up'
          AND card_id IS NOT NULL
        ORDER BY created_at DESC, event_id DESC
        LIMIT 1
        """,
        (profile_id,),
    ).fetchone()
    patch = create_profile_patch_suggestion(
        conn,
        profile_id=profile_id,
        card_id=str(card_row["card_id"] or "") if card_row else None,
        note=REVIEW_LEARNING_PATCH_NOTE,
        profile_path=profile_path,
        feedback_context=context,
    )
    # Older versions created one pending patch per Review card/note. Once the
    # profile-level learning batch exists, those siblings are stale UX debt:
    # applying one would mutate the profile hash and strand the rest as blocked.
    conn.execute(
        """
        DELETE FROM profile_patch_suggestions
        WHERE profile_id = ?
          AND status = 'pending'
          AND patch_id != ?
          AND card_id IN (
              SELECT card_id
              FROM feedback_events
              WHERE profile_id = ?
                AND action = 'follow_up'
          )
        """,
        (profile_id, patch["patch_id"], profile_id),
    )
    return patch


def create_profile_preferences_patch_suggestion(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    preferences_text: str,
) -> dict[str, Any]:
    preferences_text = require_profile_text_without_private_fragments("Profile matching preferences", preferences_text)
    clean_lines = _normalize_preference_lines(preferences_text)
    if not clean_lines:
        raise MonitorStateError("At least one matching preference is required.")
    row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    if not row:
        raise MonitorStateError(f"Profile is not registered: {profile_id}")
    profile_path = dashboard_profile_file_path(row["path"])
    if not profile_path.exists():
        raise MonitorStateError(f"Profile file not found: {profile_path}")
    current = profile_path.read_text(encoding="utf-8")
    require_profile_text_without_private_fragments("Current profile", current)
    base_profile_hash = sha256_text(current)
    proposed = _replace_follow_up_preferences(current, "\n".join(clean_lines))
    require_profile_text_without_private_fragments("Proposed profile", proposed)
    diff = "\n".join(
        difflib.unified_diff(
            current.splitlines(),
            proposed.splitlines(),
            fromfile="current-profile",
            tofile="proposed-profile",
            lineterm="",
        )
    )
    now = utc_now()
    note = "User edited matching preferences in Signal Desk."
    patch = {
        "schema_version": PROFILE_PATCH_SCHEMA_VERSION,
        "patch_id": "patch_" + uuid.uuid4().hex,
        "profile_id": profile_id,
        "card_id": None,
        "note": note,
        "status": "pending",
        "diff_text": diff,
        "proposed_profile_text": proposed,
        "base_profile_hash": base_profile_hash,
        "created_at": now,
        "applied_at": None,
    }
    conn.execute(
        """
        INSERT INTO profile_patch_suggestions(
            patch_id, profile_id, card_id, note, status, diff_text,
            proposed_profile_text, base_profile_hash, created_at, applied_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patch["patch_id"],
            profile_id,
            None,
            note,
            "pending",
            diff,
            proposed,
            base_profile_hash,
            now,
            None,
        ),
    )
    return patch


def apply_profile_patch(conn: sqlite3.Connection, *, patch_id: str, profile_path: Path | None = None) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM profile_patch_suggestions WHERE patch_id = ?",
        (patch_id,),
    ).fetchone()
    if not row:
        raise MonitorStateError(f"Profile patch not found: {patch_id}")
    if row["status"] != "pending":
        raise MonitorStateError(f"Profile patch is not pending: {patch_id}")
    if profile_path is None:
        profile_row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (row["profile_id"],)).fetchone()
        if not profile_row:
            raise MonitorStateError(f"Profile is not registered: {row['profile_id']}")
        profile_path = dashboard_profile_file_path(profile_row["path"])
    current = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    # Profile suggestions are now an editable Desk workflow, not a locked
    # patch-apply ceremony. A stale base hash should not strand ordinary users:
    # snapshot the current file first, then write the reviewed proposal so
    # Revert can restore the latest visible profile if needed.
    snapshot_id = "snapshot_" + uuid.uuid4().hex
    now = utc_now()
    conn.execute(
        """
        INSERT INTO profile_snapshots(snapshot_id, profile_id, profile_path, profile_hash,
                                      profile_text, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (snapshot_id, row["profile_id"], str(profile_path), sha256_text(current), current, f"before {patch_id}", now),
    )
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(row["proposed_profile_text"], encoding="utf-8")
    conn.execute(
        "UPDATE profile_patch_suggestions SET status = ?, applied_at = ? WHERE patch_id = ?",
        ("applied", now, patch_id),
    )
    duplicate_rows = conn.execute(
        """
        SELECT patch_id
        FROM profile_patch_suggestions
        WHERE profile_id = ?
          AND status = 'pending'
          AND patch_id != ?
          AND (
              note = ?
              OR card_id IN (
                  SELECT card_id
                  FROM feedback_events
                  WHERE profile_id = ?
                    AND action = 'follow_up'
              )
          )
        """,
        (row["profile_id"], patch_id, row["note"], row["profile_id"]),
    ).fetchall()
    if duplicate_rows:
        conn.execute(
            """
            DELETE FROM profile_patch_suggestions
            WHERE profile_id = ?
              AND status = 'pending'
              AND patch_id != ?
              AND (
                  note = ?
                  OR card_id IN (
                      SELECT card_id
                      FROM feedback_events
                      WHERE profile_id = ?
                        AND action = 'follow_up'
                  )
              )
            """,
            (row["profile_id"], patch_id, row["note"], row["profile_id"]),
        )
    conn.commit()
    return {
        "patch_id": patch_id,
        "profile_id": row["profile_id"],
        "status": "applied",
        "snapshot_id": snapshot_id,
        "profile_path": str(profile_path),
        "applied_at": now,
        "duplicate_draft_count": len(duplicate_rows),
    }


def revert_profile_patch(conn: sqlite3.Connection, *, patch_id: str, profile_path: Path | None = None) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM profile_patch_suggestions WHERE patch_id = ?",
        (patch_id,),
    ).fetchone()
    if not row:
        raise MonitorStateError(f"Profile patch not found: {patch_id}")
    if row["status"] == "pending":
        now = utc_now()
        conn.execute(
            "UPDATE profile_patch_suggestions SET status = ? WHERE patch_id = ?",
            ("reverted", patch_id),
        )
        conn.commit()
        return {
            "patch_id": patch_id,
            "profile_id": row["profile_id"],
            "status": "reverted",
            "profile_path": str(profile_path) if profile_path else "",
            "reverted_at": now,
        }
    if row["status"] != "applied":
        raise MonitorStateError(f"Profile patch is not applied: {patch_id}")
    snapshot = conn.execute(
        """
        SELECT * FROM profile_snapshots
        WHERE profile_id = ? AND reason = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (row["profile_id"], f"before {patch_id}"),
    ).fetchone()
    if not snapshot:
        raise MonitorStateError(f"Profile snapshot not found for patch: {patch_id}")
    if profile_path is None:
        profile_row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (row["profile_id"],)).fetchone()
        profile_path = dashboard_profile_file_path(profile_row["path"] if profile_row else snapshot["profile_path"])
    current = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    # Do not silently erase manual profile edits made after an applied diff.
    # Revert is only automatic while the file still equals the patch proposal.
    if current != row["proposed_profile_text"]:
        raise MonitorStateError("Profile changed after patch was applied; manual revert required.")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(snapshot["profile_text"], encoding="utf-8")
    now = utc_now()
    conn.execute(
        "UPDATE profile_patch_suggestions SET status = ? WHERE patch_id = ?",
        ("reverted", patch_id),
    )
    conn.commit()
    return {
        "patch_id": patch_id,
        "profile_id": row["profile_id"],
        "status": "reverted",
        "snapshot_id": snapshot["snapshot_id"],
        "profile_path": str(profile_path),
        "reverted_at": now,
    }


def replay_profile_patch(conn: sqlite3.Connection, *, patch_id: str, profile_path: Path | None = None) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM profile_patch_suggestions WHERE patch_id = ?",
        (patch_id,),
    ).fetchone()
    if not row:
        raise MonitorStateError(f"Profile patch not found: {patch_id}")
    if row["status"] != "reverted":
        raise MonitorStateError(f"Profile patch is not reverted: {patch_id}")
    snapshot = conn.execute(
        """
        SELECT * FROM profile_snapshots
        WHERE profile_id = ? AND reason = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (row["profile_id"], f"before {patch_id}"),
    ).fetchone()
    if not snapshot:
        raise MonitorStateError(f"Profile snapshot not found for patch: {patch_id}")
    if profile_path is None:
        profile_row = conn.execute("SELECT path FROM profiles WHERE profile_id = ?", (row["profile_id"],)).fetchone()
        profile_path = dashboard_profile_file_path(profile_row["path"] if profile_row else snapshot["profile_path"])
    current = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    # Replay is intentionally stricter than "apply old patch again": it creates
    # a fresh pending diff only while the profile still matches the revert
    # snapshot, so manual edits after rollback cannot be overwritten by a click.
    if current != snapshot["profile_text"]:
        raise MonitorStateError("Profile changed after patch was reverted; regenerate the profile diff.")
    now = utc_now()
    new_patch_id = "patch_" + uuid.uuid4().hex
    base_profile_hash = sha256_text(current)
    conn.execute(
        """
        INSERT INTO profile_patch_suggestions(
            patch_id, profile_id, card_id, note, status, diff_text,
            proposed_profile_text, base_profile_hash, created_at, applied_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_patch_id,
            row["profile_id"],
            row["card_id"],
            row["note"],
            "pending",
            row["diff_text"],
            row["proposed_profile_text"],
            base_profile_hash,
            now,
            None,
        ),
    )
    conn.commit()
    return {
        "schema_version": PROFILE_PATCH_SCHEMA_VERSION,
        "patch_id": new_patch_id,
        "profile_id": row["profile_id"],
        "card_id": row["card_id"],
        "note": row["note"],
        "status": "pending",
        "diff_text": row["diff_text"],
        "proposed_profile_text": row["proposed_profile_text"],
        "base_profile_hash": base_profile_hash,
        "created_at": now,
        "applied_at": None,
        "replayed_from_patch_id": patch_id,
    }
