"""Profile creation helpers for Signal Desk."""

from __future__ import annotations

import base64
import io
import json
import re
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import monitor_config, monitor_state, report, source_registry


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESK_DELIVERY_TARGET_ID = "telegram-bot-default"
PROFILE_CREATE_ALLOWED_FIELDS = {
    "brief",
    "source_filename",
    "source_text",
    "source_base64",
    "template_id",
    "answers",
    "confirm_external_ai",
    "preview",
}
PROFILE_CREATE_MAX_TEXT_LENGTH = 30000
PROFILE_CREATE_MAX_BINARY_BYTES = 4 * 1024 * 1024
PROFILE_TEMPLATE_FILES = {
    "jobs": "jobs.md",
    "airdrops": "airdrops.md",
    "market-news": "market-news.md",
    "research-leads": "research-leads.md",
    "competitor-monitoring": "competitor-monitoring.md",
}
PROFILE_TEMPLATE_METADATA = {
    "jobs": {
        "audience": "Developers looking for paid, actionable opportunities",
        "default_topic": "jobs",
        "starter_brief": (
            "Watch for paid senior remote frontend, TypeScript, React, agent, or Telegram Mini Apps "
            "opportunities. Prefer clear budget, contact path, and work format. Avoid unpaid internships, "
            "candidate CVs, generic full-stack roles, and vague promos."
        ),
        "coach_questions": [
            "What must be true before a lead is worth acting on?",
            "Which roles, stacks, locations, or work formats should never match?",
            "Give one recent good match and one wrong match if you have them.",
        ],
    },
    "airdrops": {
        "audience": "Crypto users who need credible, low-risk airdrop opportunities",
        "default_topic": "airdrops",
        "starter_brief": (
            "Watch for credible airdrop, quest, testnet, points, grant, or bounty opportunities. Prefer official "
            "source evidence, clear eligibility, deadlines, and safe next steps. Avoid referral spam, wallet-drain "
            "prompts, guaranteed-profit claims, and seed phrase requests."
        ),
        "coach_questions": [
            "Which chains, ecosystems, or project types are in scope?",
            "What risk signals should always block a match?",
            "What makes an opportunity urgent enough to act today?",
        ],
    },
    "market-news": {
        "audience": "Analysts who need decision-relevant market and product news",
        "default_topic": "market-news",
        "starter_brief": (
            "Watch for market-moving news, policy changes, launches, outages, partnerships, and risk events with "
            "source context. Avoid routine price chatter, memes, reposts, and unverified rumors without evidence."
        ),
        "coach_questions": [
            "Which decisions should this news brief support?",
            "Which event types are noise even when they mention relevant keywords?",
            "What verification bar should separate high from medium priority?",
        ],
    },
    "research-leads": {
        "audience": "Researchers who need evidence-backed leads and follow-up paths",
        "default_topic": "research-leads",
        "starter_brief": (
            "Watch for papers, datasets, tools, funding calls, events, and expert leads with provenance and links. "
            "Avoid generic thought leadership, weak mentions, reposts without source, and unverifiable claims."
        ),
        "coach_questions": [
            "Which domains, methods, or institutions are in scope?",
            "What evidence is required before saving a lead?",
            "Which generic research chatter should be ignored?",
        ],
    },
    "competitor-monitoring": {
        "audience": "Founders, product marketers, and sales leads tracking competitors",
        "default_topic": "competitor-monitoring",
        "starter_brief": (
            "Watch for competitor launches, pricing changes, hiring, partnerships, incidents, customer complaints, "
            "and positioning signals. Avoid generic brand mentions, repeated announcements, and unsubstantiated rumors."
        ),
        "coach_questions": [
            "Which competitors or adjacent products matter most?",
            "What business action should a high-priority signal trigger?",
            "Which generic brand mentions should never match?",
        ],
    },
}
PROFILE_TEMPLATE_SUPPORTED_FIELDS = [
    "basic_info",
    "search_rules",
    "rejection_rules",
    "prefilter_tuning",
    "good_examples",
    "bad_examples",
    "extraction_schema",
    "extraction_prompt",
    "report_preferences",
    "follow_up_preferences",
    "report_labels",
]


def _facade_attr(name: str, default: Any) -> Any:
    facade = sys.modules.get("scripts.dashboard_server")
    return getattr(facade, name, default) if facade is not None else default


def _facade_callable(name: str, default: Any) -> Any:
    helper = _facade_attr(name, default)
    return helper if callable(helper) and helper is not default else default


def _profile_create_allowed_fields() -> set[str]:
    fields = _facade_attr("PROFILE_CREATE_ALLOWED_FIELDS", PROFILE_CREATE_ALLOWED_FIELDS)
    return {str(field) for field in fields} if isinstance(fields, (set, list, tuple)) else PROFILE_CREATE_ALLOWED_FIELDS


def _profile_create_max_text_length() -> int:
    try:
        value = int(_facade_attr("PROFILE_CREATE_MAX_TEXT_LENGTH", PROFILE_CREATE_MAX_TEXT_LENGTH))
    except (TypeError, ValueError):
        return PROFILE_CREATE_MAX_TEXT_LENGTH
    return value if value > 0 else PROFILE_CREATE_MAX_TEXT_LENGTH


def _profile_create_max_binary_bytes() -> int:
    try:
        value = int(_facade_attr("PROFILE_CREATE_MAX_BINARY_BYTES", PROFILE_CREATE_MAX_BINARY_BYTES))
    except (TypeError, ValueError):
        return PROFILE_CREATE_MAX_BINARY_BYTES
    return value if value > 0 else PROFILE_CREATE_MAX_BINARY_BYTES


def _desk_delivery_target_id() -> str:
    return str(_facade_attr("DESK_DELIVERY_TARGET_ID", DESK_DELIVERY_TARGET_ID) or DESK_DELIVERY_TARGET_ID)


def _project_root() -> Path:
    return Path(_facade_attr("PROJECT_ROOT", PROJECT_ROOT))


def _utc_now() -> str:
    now_fn = _facade_attr("_utc_now", None)
    if callable(now_fn) and now_fn is not _utc_now:
        return str(now_fn())
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_profile_from_brief(conn, body: dict) -> dict:
    unexpected = sorted(str(key) for key in body.keys() if key not in _profile_create_allowed_fields())
    if unexpected:
        raise ValueError(f"Unsupported profile creation field: {', '.join(unexpected)}")
    preview = body.get("preview")
    if preview is not None:
        ai_payload = _profile_ai_payload_from_create_preview(preview)
        source_brief = _profile_preview_source_brief(body, preview)
        return _create_profile_from_ai_payload(conn, ai_payload, source_brief=source_brief, detail="Created this profile from a reviewed preview.")
    brief = _facade_callable("_profile_create_input_text", _profile_create_input_text)(body)
    if not report.llm_key_available():
        raise ValueError("Save an AI API key in Settings before creating a profile.")
    ai_payload = _facade_callable("_profile_ai_payload_from_text", _profile_ai_payload_from_text)(brief)
    return _create_profile_from_ai_payload(conn, ai_payload, source_brief=brief, detail="AI generated this matching profile from your brief.")


def _create_profile_from_ai_payload(conn, ai_payload: dict[str, Any], *, source_brief: str, detail: str) -> dict:
    title = _profile_ai_title(ai_payload)
    project_root = _project_root()
    profile_id = _facade_callable("_unique_profile_id", _unique_profile_id)(
        conn,
        _facade_callable("_slugify_profile_id", _slugify_profile_id)(title),
    )
    profile_rel_path = Path("profiles") / "desk" / f"{profile_id}.md"
    profile_path = project_root / profile_rel_path
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(_profile_markdown_from_ai_payload(ai_payload, source_brief=source_brief), encoding="utf-8")
    source_topic = _profile_source_topic(ai_payload, profile_id)

    config = {
        "id": profile_id,
        "path": profile_rel_path.as_posix(),
        "enabled": True,
        "timezone": "Asia/Shanghai",
        "work_interval_minutes": 30,
        "off_hours_interval_minutes": 120,
        "scan_window_hours": 2,
        "source_registry": ".tgcs/sources.json",
        "channel_list": "channel_lists/example.txt",
        "source_topics": [source_topic],
        "alert_rule": "high_new_or_changed",
        "alert_schedule_mode": "work_hours",
        "delivery_targets": [_desk_delivery_target_id()],
        "dashboard_visible": True,
        "prefilter_enabled": True,
        "allow_partial_source_failures": True,
        "scan_concurrency": monitor_config.DEFAULT_FAST_JOBS_SCAN_CONCURRENCY,
        "scan_delay_seconds": monitor_config.DEFAULT_FAST_JOBS_SCAN_DELAY_SECONDS,
        "semantic_max_messages": monitor_config.DEFAULT_FAST_JOBS_SEMANTIC_MAX_MESSAGES,
        "semantic_max_tokens": monitor_config.DEFAULT_FAST_JOBS_SEMANTIC_MAX_TOKENS,
        "semantic_batch_size": monitor_config.DEFAULT_FAST_JOBS_SEMANTIC_BATCH_SIZE,
        "semantic_concurrency": monitor_config.DEFAULT_FAST_JOBS_SEMANTIC_CONCURRENCY,
        "prefilter_keywords": _profile_keywords_from_ai_payload(ai_payload),
    }
    _facade_callable("_append_profile_config", _append_profile_config)(config)
    monitor_state.upsert_profile(conn, {**config, "path": str(profile_path)})
    return {
        "schema_version": "desk_profile_create_result_v1",
        "profile_id": profile_id,
        "display_name": title,
        "profile_path": profile_rel_path.as_posix(),
        "created": True,
        "detail": detail,
        "next_action": "Discover Telegram sources for this profile, then run an AI review from Start.",
        "created_at": _utc_now(),
    }


def profile_template_catalog() -> dict[str, Any]:
    templates: list[dict[str, Any]] = []
    for template_id in PROFILE_TEMPLATE_FILES:
        text = _profile_template_text(template_id)
        metadata = PROFILE_TEMPLATE_METADATA[template_id]
        templates.append(
            {
                "id": template_id,
                "title": _profile_template_title(text),
                "audience": metadata["audience"],
                "default_topic": metadata["default_topic"],
                "starter_brief": metadata["starter_brief"],
                "coach_questions": list(metadata["coach_questions"]),
                "supported_fields": list(PROFILE_TEMPLATE_SUPPORTED_FIELDS),
            }
        )
    return {
        "schema_version": "desk_profile_template_catalog_v1",
        "templates": templates,
    }


def preview_profile_from_brief(body: dict) -> dict[str, Any]:
    unexpected = sorted(str(key) for key in body.keys() if key not in _profile_create_allowed_fields() - {"preview"})
    if unexpected:
        raise ValueError(f"Unsupported profile creation field: {', '.join(unexpected)}")
    template_id = _clean_profile_template_id(body.get("template_id"))
    text = _profile_create_preview_input_text(body)
    answers = _profile_create_answers(body.get("answers"))
    questions = _profile_template_questions(template_id, text=text, answers=answers)
    if questions and _profile_create_preview_needs_input(text, answers):
        return {
            "schema_version": "desk_profile_create_preview_v1",
            "status": "needs_input",
            "template_id": template_id,
            "title": _profile_template_title(_profile_template_text(template_id)),
            "topic": PROFILE_TEMPLATE_METADATA[template_id]["default_topic"],
            "questions": questions,
            "generated_rules": [],
            "search_rules": [],
            "rejection_rules": [],
            "keywords": [],
            "markdown_preview": "",
            "warnings": ["Add one clear goal or one must-include / never-match example before saving this profile."],
            "llm_used": False,
        }

    warnings: list[str] = []
    ai_payload: dict[str, Any] | None = None
    llm_used = False
    if body.get("confirm_external_ai") is True and report.llm_key_available():
        try:
            ai_payload = _facade_callable("_profile_ai_payload_from_text", _profile_ai_payload_from_text)(text)
            llm_used = True
        except ValueError:
            warnings.append("Smart draft was unavailable, so Signal Desk drafted conservative rules from the template.")
    if ai_payload is None:
        ai_payload = _profile_payload_from_template_text(template_id=template_id, text=text, answers=answers)
        if not warnings:
            warnings.append("Drafted from the selected template; review the rules before saving.")
    markdown_preview = _profile_markdown_from_ai_payload(
        ai_payload,
        source_brief=_profile_preview_source_brief(body, ai_payload),
    )
    return {
        "schema_version": "desk_profile_create_preview_v1",
        "status": "ready",
        "template_id": template_id,
        "title": _profile_ai_title(ai_payload),
        "topic": _profile_source_topic(ai_payload, PROFILE_TEMPLATE_METADATA[template_id]["default_topic"]),
        "questions": questions,
        "generated_rules": list(ai_payload["search_rules"]),
        "search_rules": list(ai_payload["search_rules"]),
        "rejection_rules": list(ai_payload["rejection_rules"]),
        "keywords": list(ai_payload["keywords"]),
        "markdown_preview": markdown_preview,
        "warnings": warnings,
        "llm_used": llm_used,
    }


def delete_profile(conn, profile_id: str) -> dict:
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        raise ValueError("Profile id is required.")
    row = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
    if not row:
        raise monitor_state.MonitorStateError(f"Profile is not registered: {profile_id}")
    profile_path = Path(str(row["path"] or ""))
    removed_from_config = _remove_profile_config(profile_id)
    removed_profile_file = _remove_desk_profile_file(profile_path)
    result = monitor_state.delete_profile(conn, profile_id=profile_id)
    return {
        **result,
        "removed_from_config": removed_from_config,
        "removed_profile_file": removed_profile_file,
        "detail": "Profile deleted from Signal Desk.",
    }


def _remove_profile_config(profile_id: str) -> bool:
    path = _project_root() / ".tgcs" / "profiles.toml"
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    blocks: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != "[[profiles]]":
            index += 1
            continue
        start = index
        index += 1
        while index < len(lines) and not lines[index].lstrip().startswith("["):
            index += 1
        blocks.append((start, index))

    if not blocks:
        return False

    remove_ranges: set[tuple[int, int]] = set()
    for start, end in blocks:
        block = "".join(lines[start:end])
        if _profile_block_id(block) == profile_id:
            remove_ranges.add((start, end))

    if not remove_ranges:
        return False

    kept: list[str] = []
    for line_index, line in enumerate(lines):
        if any(start <= line_index < end for start, end in remove_ranges):
            continue
        kept.append(line)
    path.write_text("".join(kept), encoding="utf-8", newline="")
    return True


def _profile_block_id(block: str) -> str:
    for line in block.splitlines():
        match = re.match(r"\s*id\s*=\s*(['\"])(.*?)\1\s*(?:#.*)?$", line)
        if match:
            return match.group(2)
    return ""


def _remove_desk_profile_file(path_value: Path) -> bool:
    project_root = _project_root().resolve()
    profile_path = path_value if path_value.is_absolute() else project_root / path_value
    try:
        resolved = profile_path.resolve()
        resolved.relative_to(project_root / "profiles" / "desk")
    except ValueError:
        return False
    if not resolved.is_file():
        return False
    resolved.unlink()
    return True


def _profile_create_input_text(body: dict) -> str:
    parts: list[str] = []
    brief = str(body.get("brief") or "").strip()
    if brief:
        parts.append(f"Profile goal:\n{brief}")
    filename = str(body.get("source_filename") or "").strip()
    source_text = str(body.get("source_text") or "").strip()
    if source_text:
        parts.append(f"{_profile_attachment_heading(filename)}:\n{source_text}")
    source_base64 = str(body.get("source_base64") or "").strip()
    if source_base64:
        parsed_text = _facade_callable("_profile_text_from_base64_file", _profile_text_from_base64_file)(source_base64, filename)
        parts.append(f"{_profile_attachment_heading(filename)}:\n{parsed_text}")
    text = "\n\n".join(part for part in parts if part.strip()).strip()
    if not text:
        raise ValueError("Describe the profile or attach a .md, .txt, or .pdf profile file.")
    max_text_length = _profile_create_max_text_length()
    if len(text) > max_text_length:
        raise ValueError(f"Profile brief must be {max_text_length} characters or fewer after parsing.")
    return monitor_state.require_profile_text_without_private_fragments("Profile brief", text)


def _profile_create_preview_input_text(body: dict) -> str:
    base_text = _profile_create_input_text(body)
    answers = _profile_create_answers(body.get("answers"))
    if not answers:
        return base_text
    answer_lines = [f"{key}: {value}" for key, value in sorted(answers.items()) if value]
    combined = "\n\n".join([base_text, "Wizard answers:", *answer_lines]).strip()
    if len(combined) > _profile_create_max_text_length():
        raise ValueError(f"Profile brief must be {_profile_create_max_text_length()} characters or fewer after parsing.")
    return monitor_state.require_profile_text_without_private_fragments("Profile brief", combined)


def _profile_create_answers(value: object) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("Profile wizard answers must be an object.")
    answers: dict[str, str] = {}
    for key, raw in value.items():
        cleaned_key = re.sub(r"[^a-z0-9_-]+", "_", str(key or "").strip().lower()).strip("_")
        if not cleaned_key:
            continue
        text = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not text:
            continue
        answers[cleaned_key[:40]] = monitor_state.require_profile_text_without_private_fragments("Profile wizard answer", text[:800])
    return answers


def _profile_create_preview_needs_input(text: str, answers: dict[str, str]) -> bool:
    word_count = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", text))
    has_boundary = any(key in answers and answers[key] for key in ("avoid", "bad_example", "bad_examples", "must_have", "good_example"))
    return word_count < 8 and not has_boundary


def _clean_profile_template_id(value: object) -> str:
    template_id = str(value or "jobs").strip()
    if not template_id:
        template_id = "jobs"
    if template_id not in PROFILE_TEMPLATE_FILES:
        raise ValueError(f"Unknown profile template: {template_id}")
    return template_id


def _profile_templates_dir() -> Path:
    candidate = _project_root() / "profiles" / "templates"
    if candidate.exists():
        return candidate
    return PROJECT_ROOT / "profiles" / "templates"


def _profile_template_text(template_id: str) -> str:
    template_id = _clean_profile_template_id(template_id)
    path = _profile_templates_dir() / PROFILE_TEMPLATE_FILES[template_id]
    if not path.exists():
        raise ValueError(f"Profile template is missing: {template_id}")
    return path.read_text(encoding="utf-8")


def _profile_template_title(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# "):
            return line.removeprefix("#").replace("Profile:", "").strip(" :-") or "Custom Monitor"
    return "Custom Monitor"


def _profile_template_questions(template_id: str, *, text: str, answers: dict[str, str]) -> list[str]:
    questions = list(PROFILE_TEMPLATE_METADATA[template_id]["coach_questions"])
    if "avoid" not in answers and "bad_example" not in answers and "bad_examples" not in answers:
        questions.append("What should this profile explicitly reject even when keywords overlap?")
    if len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", text)) < 20:
        questions.append("Add one concrete positive example or must-have condition.")
    seen: set[str] = set()
    output: list[str] = []
    for question in questions:
        key = question.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(question)
    return output[:5]


def _profile_payload_from_template_text(*, template_id: str, text: str, answers: dict[str, str]) -> dict[str, Any]:
    template_text = _profile_template_text(template_id)
    metadata = PROFILE_TEMPLATE_METADATA[template_id]
    title = _profile_template_title(template_text)
    goal = _profile_sentence(text)
    search_rules = _profile_section_list(template_text, "Search Rules", max_items=5)
    rejection_rules = _profile_section_list(template_text, "Rejection Rules", max_items=5)
    must_have = answers.get("must_have") or answers.get("good_example") or answers.get("good_examples")
    avoid = answers.get("avoid") or answers.get("bad_example") or answers.get("bad_examples")
    if must_have:
        search_rules.insert(0, f"Include only items that satisfy this user must-have: {must_have[:180]}.")
    else:
        search_rules.insert(0, f"Include items that match this goal: {goal}.")
    if avoid:
        rejection_rules.insert(0, f"Reject items matching this user avoid rule: {avoid[:180]}.")
    if not rejection_rules:
        rejection_rules = ["Reject vague, promotional, unsafe, or off-profile items even when keywords overlap."]
    keywords = _profile_keywords_from_text(" ".join([text, metadata["starter_brief"]]))
    return _clean_profile_ai_payload(
        {
            "title": title,
            "goal": goal,
            "search_rules": search_rules[:8],
            "rejection_rules": rejection_rules[:6],
            "keywords": keywords,
            "topic": metadata["default_topic"],
        }
    )


def _profile_section_list(text: str, section: str, *, max_items: int) -> list[str]:
    body = _profile_section_body(text, section)
    items: list[str] = []
    for raw in body.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+\.)\s*", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if len(line) >= 12:
            items.append(line.rstrip("."))
        if len(items) >= max_items:
            break
    return items


def _profile_section_body(text: str, section: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(section)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    next_match = re.search(r"^##\s+", text[match.end():], flags=re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(text)
    return text[match.end():end].strip()


def _profile_ai_payload_from_create_preview(preview: object) -> dict[str, Any]:
    if not isinstance(preview, dict):
        raise ValueError("Confirmed profile preview must be an object.")
    if preview.get("schema_version") != "desk_profile_create_preview_v1":
        raise ValueError("Confirmed profile preview has an invalid schema.")
    if str(preview.get("status") or "").strip() != "ready":
        raise ValueError("Profile preview must be ready before saving.")
    payload = {
        "title": preview.get("title"),
        "goal": _profile_goal_from_preview(preview),
        "search_rules": preview.get("search_rules") or preview.get("generated_rules"),
        "rejection_rules": preview.get("rejection_rules"),
        "keywords": preview.get("keywords"),
        "topic": preview.get("topic"),
    }
    return _clean_profile_ai_payload(payload)


def _profile_goal_from_preview(preview: dict[str, Any]) -> str:
    markdown = str(preview.get("markdown_preview") or "")
    match = re.search(r"^\s*-\s+\*\*Goal\*\*:\s*(.+)$", markdown, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    title = str(preview.get("title") or "Custom Monitor").strip()
    return f"Monitor {title} signals with the reviewed profile rules."


def _profile_preview_source_brief(body: dict, payload: object) -> str:
    if isinstance(payload, dict) and payload.get("schema_version") == "desk_profile_create_preview_v1":
        template_id = _clean_profile_template_id(payload.get("template_id"))
    else:
        template_id = _clean_profile_template_id(body.get("template_id"))
    answers = _profile_create_answers(body.get("answers"))
    answer_hint = "; ".join(f"{key}: {value}" for key, value in sorted(answers.items()))[:500]
    base = PROFILE_TEMPLATE_METADATA[template_id]["starter_brief"]
    if answer_hint:
        return f"Created from the {template_id} template. Wizard answers: {answer_hint}. Starter brief: {base}"
    return f"Created from the {template_id} template. Starter brief: {base}"


def _profile_attachment_heading(filename: str) -> str:
    display_name = Path(str(filename or "")).name.strip()
    if display_name:
        return f"Attached profile file ({display_name})"
    return "Attached profile file"


def _profile_text_from_base64_file(source_base64: str, filename: str) -> str:
    raw_text = source_base64.split(",", 1)[-1]
    try:
        data = base64.b64decode(raw_text, validate=False)
    except ValueError as exc:
        raise ValueError("Could not read the attached profile file.") from exc
    if len(data) > _profile_create_max_binary_bytes():
        raise ValueError("Profile file is too large for local parsing.")
    if Path(filename).suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF parsing is not installed on this machine; use Markdown or text for now.") from exc
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages).strip()
        if not text:
            raise ValueError("The PDF did not contain readable text. Paste the profile brief instead.")
        return text
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="ignore")


def _profile_title_from_text(text: str) -> str:
    for raw in text.splitlines():
        line = re.sub(r"^[#>*\-\s]+", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if line:
            return line[:72].strip(" :-") or "Custom Monitor"
    return "Custom Monitor"


def _clean_profile_ai_list(value: object, *, field: str, max_items: int, max_item_length: int = 220) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"AI profile generation must return a {field} list.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if not text:
            continue
        text = text[:max_item_length].strip()
        marker = text.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(text)
        if len(cleaned) >= max_items:
            break
    if not cleaned:
        raise ValueError(f"AI profile generation returned no usable {field}.")
    return cleaned


def _clean_profile_ai_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("AI profile generation must return a JSON object.")
    title = re.sub(r"\s+", " ", str(payload.get("title") or "")).strip()[:72].strip(" :-")
    goal = re.sub(r"\s+", " ", str(payload.get("goal") or "")).strip()[:320].strip()
    if not title or not goal:
        raise ValueError("AI profile generation must return title and goal.")
    search_rules = _clean_profile_ai_list(payload.get("search_rules"), field="search_rules", max_items=8)
    rejection_rules = _clean_profile_ai_list(payload.get("rejection_rules"), field="rejection_rules", max_items=6)
    keywords = _clean_profile_ai_keywords(payload.get("keywords"))
    topic = _clean_profile_ai_topic(str(payload.get("topic") or title))
    return {
        "title": title,
        "goal": goal,
        "search_rules": search_rules,
        "rejection_rules": rejection_rules,
        "keywords": keywords,
        "topic": topic,
    }


def _profile_ai_payload_from_text(text: str) -> dict[str, Any]:
    if not report.llm_key_available():
        raise ValueError("Save an AI API key in Settings before creating a profile.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("Install optional LLM dependencies before creating AI profiles.") from exc

    base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)
    provider = report.llm_provider(base_url, model)
    api_key = report.api_key_for_provider(provider)
    if not api_key:
        raise ValueError("Save an AI API key in Settings before creating a profile.")
    system_prompt = (
        "You generate Telegram monitoring profiles. Return JSON only. The profile will be used "
        "by an LLM matcher, so write explicit semantic rules, not keyword-only matching. Do not "
        "include secrets, commands, file paths, or long copies of the user's text."
    )
    user_prompt = json.dumps(
        {
            "brief": text,
            "output_schema": {
                "title": "short human title",
                "goal": "one sentence matching goal",
                "search_rules": ["include criteria"],
                "rejection_rules": ["exclude criteria"],
                "keywords": ["short prefilter hints"],
                "topic": "short lowercase topic tag",
            },
        },
        ensure_ascii=False,
    )
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": report.llm_temperature(provider),
    }
    if provider in {"deepseek", "openai"}:
        create_kwargs["response_format"] = {"type": "json_object"}
    thinking_extra = report.minimax_thinking_extra(provider) or report.deepseek_thinking_extra(provider, model)
    if thinking_extra:
        create_kwargs["extra_body"] = thinking_extra
    report.add_token_limit(create_kwargs, provider=provider, max_tokens=1100)
    try:
        response = OpenAI(api_key=api_key, base_url=base_url).chat.completions.create(**create_kwargs)
    except Exception as exc:
        raise ValueError(f"AI profile generation failed: {exc}") from exc
    raw = response.choices[0].message.content or ""
    try:
        payload = json.loads(report.strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("AI profile generation did not return valid JSON.") from exc
    return _clean_profile_ai_payload(payload)


def _clean_profile_ai_keywords(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("AI profile generation must return a keywords list.")
    keywords: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "").strip().lower())
        text = re.sub(r"[^a-z0-9+#._ -]+", "", text).strip(" ._-")
        if len(text) < 2 or text in seen:
            continue
        seen.add(text)
        keywords.append(text[:48])
        if len(keywords) >= 18:
            break
    if not keywords:
        raise ValueError("AI profile generation returned no usable keywords.")
    return keywords


def _clean_profile_ai_topic(value: str) -> str:
    slug = _slugify_profile_id(value)[:40].strip("-")
    try:
        return source_registry.normalize_topics([slug])[0]
    except source_registry.RegistryError as exc:
        raise ValueError("AI profile generation returned an invalid topic tag.") from exc


def _profile_ai_title(payload: dict[str, Any]) -> str:
    return str(payload.get("title") or "").strip() or "Custom Monitor"


def _profile_source_topic(payload: dict[str, Any], profile_id: str) -> str:
    topic = str(payload.get("topic") or "").strip()
    if topic:
        return topic
    return _clean_profile_ai_topic(profile_id)


def _profile_keywords_from_ai_payload(payload: dict[str, Any]) -> list[str]:
    keywords = payload.get("keywords")
    if isinstance(keywords, list) and keywords:
        return [str(item) for item in keywords][:18]
    raise ValueError("AI profile generation returned no usable keywords.")


def _slugify_profile_id(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:48].strip("-") or "custom-monitor"


def _unique_profile_id(conn, base_slug: str) -> str:
    existing = {str(row["profile_id"]) for row in conn.execute("SELECT profile_id FROM profiles").fetchall()}
    config_path = _project_root() / ".tgcs" / "profiles.toml"
    if config_path.exists():
        try:
            with config_path.open("rb") as handle:
                payload = tomllib.load(handle)
            for item in payload.get("profiles") or []:
                if isinstance(item, dict) and item.get("id"):
                    existing.add(str(item["id"]))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    candidate = base_slug
    suffix = 2
    project_root = _project_root()
    while candidate in existing or (project_root / "profiles" / "desk" / f"{candidate}.md").exists():
        candidate = f"{base_slug[:42].strip('-')}-{suffix}"
        suffix += 1
    return candidate


def _profile_keywords_from_text(text: str) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", text.lower()):
        cleaned = word.strip(".-")
        if cleaned in seen or cleaned in {"the", "and", "with", "from", "that", "this", "profile", "monitor"}:
            continue
        seen.add(cleaned)
        keywords.append(cleaned)
        if len(keywords) >= 18:
            break
    return keywords or ["hiring", "opportunity", "role", "project", "apply"]


def _profile_markdown_from_ai_payload(payload: dict[str, Any], *, source_brief: str) -> str:
    title = _profile_ai_title(payload)
    goal = str(payload.get("goal") or "").strip()
    search_rules = _clean_profile_ai_list(payload.get("search_rules"), field="search_rules", max_items=8)
    rejection_rules = _clean_profile_ai_list(payload.get("rejection_rules"), field="rejection_rules", max_items=6)
    toml_escape = _facade_callable("_toml_escape_inline", _toml_escape_inline)
    slugify = _facade_callable("_slugify_profile_id", _slugify_profile_id)
    return "\n".join(
        [
            f"# Profile: {title}",
            "",
            "## Basic Info",
            f"- **Goal**: {goal}",
            "- **Work format**: Use the AI-generated profile rules as the matching contract.",
            "- **Review style**: Prefer actionable items with clear next steps; reject vague promos.",
            "",
            "## Search Rules",
            *[f"{index + 1}. {rule}" for index, rule in enumerate(search_rules)],
            "",
            "## Rejection Rules",
            *[f"{index + 1}. {rule}" for index, rule in enumerate(rejection_rules)],
            "",
            "## Source Brief",
            source_brief[:1200].strip(),
            "",
            "## Extraction Schema",
            "mode: custom",
            "top_level_key: items",
            "dedup_fields: [title, source]",
            "fields:",
            "  - name: source_message_refs",
            "    type: list",
            "  - name: source_message_ids",
            "    type: list",
            "  - name: title",
            "    required: true",
            "  - name: source",
            "  - name: contact",
            "  - name: link",
            "  - name: rating",
            "    values: [high, medium, low]",
            "  - name: why",
            "  - name: action",
            "    values: [Act now, Inspect, Skip unless criteria change]",
            "",
            "## Extraction Prompt",
            "system_prompt: |",
            "  Extract only Telegram items that match this AI-generated monitor profile.",
            "  Apply the Search Rules and Rejection Rules semantically; do not rely on",
            "  keyword overlap alone. Keep each item compact and actionable, explain why",
            "  it matters in one sentence, and preserve source references.",
            "",
            "## Report Preferences",
            "- Put high-priority items first and explain the fastest safe next step.",
            "- For medium matches, state what must be verified before acting.",
            "- For low matches, state which criterion would need to change.",
            "",
            "## Follow-up Preferences",
            "- No extra learned preferences yet.",
            "",
            "## Report Labels",
            f'report_title: "{toml_escape(title)} Signal Report"',
            'section_high: "Act Now"',
            'section_medium: "Inspect First"',
            'section_low: "Boundary Examples"',
            f'stats_label: "{toml_escape(title)} matches"',
            f'output_filename: "{slugify(title)}-signal-report-{{date}}.md"',
            f'profile_section_title: "{toml_escape(title)} Profile"',
            'methodology_label: "AI-assisted Telegram source monitoring"',
            "",
        ]
    )


def _profile_markdown_from_brief(title: str, brief: str) -> str:
    rules = _facade_callable("_profile_rule_lines", _profile_rule_lines)(brief)
    goal = _facade_callable("_profile_sentence", _profile_sentence)(brief)
    toml_escape = _facade_callable("_toml_escape_inline", _toml_escape_inline)
    slugify = _facade_callable("_slugify_profile_id", _slugify_profile_id)
    return "\n".join(
        [
            f"# Profile: {title}",
            "",
            "## Basic Info",
            f"- **Goal**: {goal}",
            "- **Work format**: Use the pasted brief as the user's matching preference.",
            "- **Review style**: Prefer actionable items with clear next steps; reject vague promos.",
            "",
            "## Search Rules",
            *[f"{index + 1}. {rule}" for index, rule in enumerate(rules)],
            f"{len(rules) + 1}. Rate each item as high, medium, or low based on fit, freshness, and actionability.",
            f"{len(rules) + 2}. Keep low-priority items only when they explain a useful boundary.",
            "",
            "## Extraction Schema",
            "mode: custom",
            "top_level_key: items",
            "dedup_fields: [title, source]",
            "fields:",
            "  - name: source_message_refs",
            "    type: list",
            "  - name: source_message_ids",
            "    type: list",
            "  - name: title",
            "    required: true",
            "  - name: source",
            "  - name: contact",
            "  - name: link",
            "  - name: rating",
            "    values: [high, medium, low]",
            "  - name: why",
            "  - name: action",
            "    values: [Act now, Inspect, Skip unless criteria change]",
            "",
            "## Extraction Prompt",
            "system_prompt: |",
            "  Extract only Telegram items that match this monitor profile. Keep each item",
            "  compact and actionable. Do not copy long source text; explain why the item",
            "  matters in one sentence and preserve source references.",
            "",
            "## Report Preferences",
            "- Put high-priority items first and explain the fastest safe next step.",
            "- For medium matches, state what must be verified before acting.",
            "- For low matches, state which criterion would need to change.",
            "",
            "## Follow-up Preferences",
            "- No extra learned preferences yet.",
            "",
            "## Report Labels",
            f'report_title: "{toml_escape(title)} Signal Report"',
            'section_high: "Act Now"',
            'section_medium: "Inspect First"',
            'section_low: "Boundary Examples"',
            f'stats_label: "{toml_escape(title)} matches"',
            f'output_filename: "{slugify(title)}-signal-report-{{date}}.md"',
            f'profile_section_title: "{toml_escape(title)} Profile"',
            'methodology_label: "Telegram source monitoring"',
            "",
        ]
    )


def _profile_rule_lines(text: str) -> list[str]:
    candidates: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"^[#>*\-\d.\s]+", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if 12 <= len(line) <= 180:
            candidates.append(line.rstrip("."))
        if len(candidates) >= 5:
            break
    return candidates or ["Include items that match the user's pasted brief", "Ignore vague, low-confidence, or off-profile items"]


def _profile_sentence(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:220].rstrip(" ,.;") or "Monitor a custom set of Telegram signals"


def _toml_escape_inline(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _append_profile_config(config: dict) -> None:
    path = _project_root() / ".tgcs" / "profiles.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "\n".join(
                [
                    'schema_version = "profile_run_config_v1"',
                    "",
                    "[defaults]",
                    'output_dir = "output"',
                    'state_dir = ".tgcs/state"',
                    'database = ".tgcs/tgcs.db"',
                    'dashboard_url = "http://127.0.0.1:8765"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
    block = [
        "",
        "[[profiles]]",
        f'id = {_toml_string(config["id"])}',
        f'path = {_toml_string(config["path"])}',
        "enabled = true",
        f'timezone = {_toml_string(config["timezone"])}',
        f'work_interval_minutes = {config["work_interval_minutes"]}',
        f'off_hours_interval_minutes = {config["off_hours_interval_minutes"]}',
        f'scan_window_hours = {config["scan_window_hours"]}',
        f'source_registry = {_toml_string(config["source_registry"])}',
        f'channel_list = {_toml_string(config["channel_list"])}',
        f'source_topics = {_toml_array(config["source_topics"])}',
        f'alert_rule = {_toml_string(config["alert_rule"])}',
        f'alert_schedule_mode = {_toml_string(config["alert_schedule_mode"])}',
        f'delivery_targets = {_toml_array(config["delivery_targets"])}',
        "dashboard_visible = true",
        "prefilter_enabled = true",
        "allow_partial_source_failures = true",
        f'scan_concurrency = {config["scan_concurrency"]}',
        f'scan_delay_seconds = {config["scan_delay_seconds"]}',
        f'semantic_max_messages = {config["semantic_max_messages"]}',
        f'semantic_max_tokens = {config["semantic_max_tokens"]}',
        f'semantic_batch_size = {config["semantic_batch_size"]}',
        f'semantic_concurrency = {config["semantic_concurrency"]}',
        f'prefilter_keywords = {_toml_array(config["prefilter_keywords"])}',
        "",
    ]
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(block))
