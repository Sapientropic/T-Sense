"""Dashboard profile projection helpers."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from scripts import source_insights as _source_insights
from scripts.monitor_common import PROJECT_ROOT
from scripts.profile_schema import parse_profile_config


def _project_root() -> Path:
    projection = sys.modules.get("scripts.dashboard_projection")
    projection_root = getattr(projection, "PROJECT_ROOT", PROJECT_ROOT) if projection is not None else PROJECT_ROOT
    if Path(projection_root) != Path(PROJECT_ROOT):
        return Path(projection_root)
    facade = sys.modules.get("scripts.monitor_state")
    root = getattr(facade, "PROJECT_ROOT", PROJECT_ROOT) if facade is not None else PROJECT_ROOT
    return Path(root)


def non_negative_int(value: object) -> int:
    return _source_insights.non_negative_int(value)


def title_case_label(value: str) -> str:
    return _source_insights.title_case_label(value)


def dashboard_profile_projection(profile: dict[str, Any], *, report_title: str = "") -> dict[str, Any]:
    config = profile.get("config") if isinstance(profile.get("config"), dict) else {}
    profile_path = str(profile.get("path") or "")
    source_topics = config.get("source_topics")
    if not isinstance(source_topics, list):
        source_topics = []
    delivery_targets = config.get("delivery_targets")
    if not isinstance(delivery_targets, list):
        delivery_targets = []
    alert_schedule_mode = config.get("alert_schedule_mode")
    return {
        "schema_version": "dashboard_profile_v1",
        "profile_id": profile["profile_id"],
        "display_name": profile_display_label(str(profile["profile_id"]), profile_path=profile_path, report_title=report_title),
        "report_display_name": report_title or f"{profile_display_label(str(profile['profile_id']), profile_path=profile_path)} Report",
        "display_path": profile.get("display_path") or display_profile_path(profile_path),
        "enabled": bool(profile.get("enabled")),
        "alert_schedule_mode": alert_schedule_mode if isinstance(alert_schedule_mode, str) else "work_hours",
        "source_topics": [str(topic) for topic in source_topics if str(topic).strip()],
        "scan_window_hours": non_negative_int(config.get("scan_window_hours")),
        "semantic_max_messages": non_negative_int(config.get("semantic_max_messages")),
        "timezone": str(config.get("timezone") or ""),
        "workdays": (
            [str(day) for day in config.get("workdays", []) if str(day).strip()]
            if isinstance(config.get("workdays"), list)
            else []
        ),
        "work_start": str(config.get("work_start") or ""),
        "work_end": str(config.get("work_end") or ""),
        "work_interval_minutes": non_negative_int(config.get("work_interval_minutes")),
        "off_hours_interval_minutes": non_negative_int(config.get("off_hours_interval_minutes")),
        "alert_rule": str(config.get("alert_rule") or "high_new_or_changed"),
        "alert_max_age_minutes": non_negative_int(config.get("alert_max_age_minutes")),
        "delivery_target_count": len(delivery_targets),
        "matching_profile": profile_matching_summary(profile_path),
        "updated_at": profile.get("updated_at"),
    }


def profile_matching_summary(profile_path: str) -> dict[str, Any]:
    """Project profile Markdown into app-readable matching rules.

    The dashboard is the human surface, so it should expose the criteria the
    scanner is actually using without forcing users into raw Markdown or YAML.
    Keep this parser deliberately conservative: unknown sections remain in the
    source file, while the UI shows only short bullets from stable profile
    sections that influence matching.
    """
    path = Path(profile_path)
    if not path.is_absolute():
        path = _project_root() / path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"schema_version": "profile_matching_profile_v1", "sections": [], "learned_preferences": []}
    sections = _markdown_sections(text)
    learned = [
        item
        for item in _clean_markdown_items(sections.get("Follow-up Preferences", []), limit=12)
        if not _is_profile_tuning_instruction(item)
    ]
    basics = _apply_learned_profile_overrides(_clean_markdown_items(sections.get("Basic Info", []), limit=6), learned)
    search_rules = _apply_learned_profile_overrides(_clean_markdown_items(sections.get("Search Rules", []), limit=7), learned)
    report_preferences = _clean_markdown_items(sections.get("Report Preferences", []), limit=5)
    output_sections: list[dict[str, Any]] = []
    for key, label, items in [
        ("basics", "Match profile", basics),
        ("rules", "How cards are judged", search_rules),
        ("learned", "Applied tuning notes", learned),
        ("report", "Report preferences", report_preferences),
    ]:
        if items:
            output_sections.append({"key": key, "label": label, "items": items})
    return {
        "schema_version": "profile_matching_profile_v1",
        "summary": basics[0] if basics else "",
        "sections": output_sections,
        "learned_preferences": learned,
        "editable_text": "\n".join(f"- {item}" for item in learned),
    }


def _markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(line)
    return sections


def _clean_markdown_items(lines: list[str], *, limit: int) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith((
            "mode:",
            "top_level_key:",
            "dedup_fields:",
            "fields:",
            "system_prompt:",
            "report_title:",
            "section_",
            "stats_label:",
            "output_filename:",
            "profile_section_title:",
            "methodology_label:",
        )):
            continue
        line = re.sub(r"^\d+\.\s+", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\+\s*", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = line.replace("`", "").strip()
        if not line or line in {"|", "fields:"}:
            continue
        normalized = " ".join(line.split())
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        items.append(normalized)
        if len(items) >= limit:
            break
    return items


def _is_profile_tuning_instruction(item: str) -> bool:
    normalized = " ".join(str(item or "").split()).casefold()
    return normalized.startswith("desk feedback tuning:") or normalized.startswith("signal desk review learning batch:")


_FULL_STACK_RE = re.compile(r"\bfull[-\s]?stack\b", flags=re.IGNORECASE)
_NEGATIVE_PREFERENCE_RE = re.compile(
    r"\b(?:not|no|never|exclude|avoid|without|don't|do not|doesn't|isn't|reject|skip)\b"
    r"|不要|不想|不是|非全栈|排除|拒绝|避免",
    flags=re.IGNORECASE,
)


def _apply_learned_profile_overrides(items: list[str], learned: list[str]) -> list[str]:
    """Project the effective matching rules after user tuning notes.

    The Markdown file intentionally keeps base rules and learned preferences as
    separate sections. The dashboard, however, is the user's reading surface:
    if learned tuning says "not full stack", continuing to display full-stack
    as a positive match looks like a contradiction even though the matcher can
    read the later Follow-up Preferences section.
    """
    full_stack_excluded = any(_is_full_stack_exclusion(item) for item in learned)
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        resolved = _resolve_profile_override_item(item, full_stack_excluded=full_stack_excluded)
        if not resolved:
            continue
        key = resolved.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(resolved)
    return output


def _resolve_profile_override_item(item: str, *, full_stack_excluded: bool) -> str:
    if not full_stack_excluded or not _FULL_STACK_RE.search(item) or _is_full_stack_exclusion(item):
        return item
    resolved = re.sub(
        r"\s*/\s*full[-\s]?stack(?=\s+(?:developer|engineer|role|roles|opportunities)\b)",
        "",
        item,
        flags=re.IGNORECASE,
    )
    resolved = re.sub(r"\bfull[-\s]?stack\s*/\s*", "", resolved, flags=re.IGNORECASE)
    resolved = re.sub(r"\s*,\s*full[-\s]?stack\b", "", resolved, flags=re.IGNORECASE)
    resolved = re.sub(r"\bfull[-\s]?stack\s*,\s*", "", resolved, flags=re.IGNORECASE)
    resolved = re.sub(r"\s+([,.;:])", r"\1", resolved)
    resolved = re.sub(r"\s{2,}", " ", resolved).strip(" ,;/")
    return "" if _FULL_STACK_RE.search(resolved) else resolved


def _is_full_stack_exclusion(item: str) -> bool:
    normalized = " ".join(str(item or "").split())
    return bool(_FULL_STACK_RE.search(normalized) and _NEGATIVE_PREFERENCE_RE.search(normalized))


def display_profile_path(profile_path: str) -> str:
    """Return a stable UI label without exposing machine-specific absolute paths."""
    parts = [part for part in re.split(r"[\\/]+", profile_path) if part]
    lowered = [part.lower() for part in parts]
    if "profiles" in lowered:
        index = len(lowered) - 1 - lowered[::-1].index("profiles")
        tail = parts[index + 1 :]
        if tail and tail[0].lower() == "templates":
            tail = tail[1:]
        if tail:
            return "Profiles/" + "/".join(tail)
    name = Path(profile_path).name if profile_path else ""
    return f"Profiles/{name}" if name else "Profile path unavailable"


def report_title_from_profile_path(profile_path: str) -> str:
    if not profile_path:
        return ""
    path = Path(profile_path)
    if not path.is_absolute():
        path = _project_root() / path
    try:
        profile_text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not re.search(r"^##\s+Report Labels\b", profile_text, flags=re.MULTILINE):
        return ""
    return parse_profile_config(profile_text).labels.report_title.strip()


def profile_display_label(profile_id: str, *, profile_path: str = "", report_title: str = "") -> str:
    title = report_title or report_title_from_profile_path(profile_path)
    if title:
        return compact_report_title(title)
    return title_case_label(profile_id)


def compact_report_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title).strip()
    for suffix in (
        "Signal Report",
        "Signal Brief",
        "Scan Report",
        "Report",
        "Brief",
    ):
        if text.casefold().endswith(suffix.casefold()):
            text = text[: -len(suffix)].strip()
            break
    return text or title.strip()
