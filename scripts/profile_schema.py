"""Profile-driven mode configuration for multi-mode Telegram channel monitoring.

Parses optional sections from a profile Markdown file to override the
default job-mode behavior.  If no mode sections are present, all defaults
match the original hardcoded job-scanning behavior exactly.

Sections recognised (all optional, order does not matter):
  ## Extraction Schema   — field definitions, dedup keys, mode name
  ## Extraction Prompt   — system prompt and filter overrides
  ## Report Labels       — UI strings for reports
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class FieldDef:
    name: str
    required: bool = False
    type: str = "string"  # "string" | "list"
    values: list[str] | None = None
    extract_all: bool = False


@dataclass
class ModeConfig:
    mode: str = "job"  # "job" | "custom"
    top_level_key: str = "jobs"
    dedup_fields: list[str] = field(default_factory=lambda: ["company", "role"])
    fields: list[FieldDef] = field(default_factory=list)


@dataclass
class PromptOverrides:
    system_prompt: str | None = None
    location_filter: str | None = None
    contact_rules: str | None = None


@dataclass
class ReportLabels:
    report_title: str = "Job Scan Report"
    section_high: str = "Highly Recommended (apply now)"
    section_medium: str = "Worth Investigating (check details first)"
    section_low: str = "Low Priority (only if criteria change)"
    stats_label: str = "Frontend/React matches"
    output_filename: str = "job-scan-report-{date}.md"
    profile_section_title: str = "Candidate Profile"
    methodology_label: str = "Telegram job channels"


@dataclass
class ActionMapping:
    """Rating → display label mapping."""
    high: str = "Apply"
    medium: str = "Inspect"
    low: str = "Skip unless criteria change"


@dataclass
class ProfileConfig:
    mode: ModeConfig = field(default_factory=ModeConfig)
    prompts: PromptOverrides = field(default_factory=PromptOverrides)
    labels: ReportLabels = field(default_factory=ReportLabels)
    actions: ActionMapping = field(default_factory=ActionMapping)
    raw_profile: str = ""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

# Default field definitions matching the original hardcoded job-mode schema
_DEFAULT_JOB_FIELDS: list[FieldDef] = [
    FieldDef("company", required=True),
    FieldDef("role", required=True),
    FieldDef("location"),
    FieldDef("salary"),
    FieldDef("contact", extract_all=True),
    FieldDef("link"),
    FieldDef("source"),
    FieldDef("rating", values=["high", "medium", "low"]),
    FieldDef("why"),
    FieldDef("stack", type="list"),
    FieldDef("concerns", type="list"),
    FieldDef("action", values=["Apply", "Inspect", "Skip unless criteria change"]),
]


def _split_sections(text: str) -> dict[str, str]:
    """Split a Markdown document into {section_title: section_body} chunks."""
    parts: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts[title] = text[start:end].strip()
    return parts


def _parse_fields_block(text: str) -> list[FieldDef]:
    """Parse a YAML-like ``fields:`` indented block into FieldDef list."""
    fields: list[FieldDef] = []
    in_fields = False
    current: dict | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("fields:") or stripped == "fields":
            in_fields = True
            continue

        if not in_fields:
            continue

        # Stop at next top-level key (no leading whitespace and has a colon)
        if line and not line[0].isspace() and ":" in stripped and not stripped.startswith("-"):
            break

        # New field entry: "- name: ..."
        if stripped.startswith("- name:"):
            if current is not None:
                fields.append(FieldDef(**current))
            val = stripped[len("- name:"):].strip().strip('"\'')
            current = {"name": val}
            continue

        # Continuation of current field
        if current is not None and stripped and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"\'')
            if key == "required":
                current["required"] = val.lower() in ("true", "yes", "1")
            elif key == "type":
                current["type"] = val
            elif key == "extract_all":
                current["extract_all"] = val.lower() in ("true", "yes", "1")
            elif key == "values":
                # Parse [a, b, c] or list syntax
                if val.startswith("["):
                    items = [v.strip().strip('"\'') for v in val.strip("[]").split(",") if v.strip()]
                    current["values"] = items
                else:
                    current["values"] = [val]

    if current is not None and current.get('name'):
        fields.append(FieldDef(**current))

    return fields


def _parse_kv_block(text: str) -> dict[str, str]:
    """Parse simple ``key: value`` lines (no nesting) into a dict."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"\'')
    return result


def _parse_text_block(text: str, key: str) -> str | None:
    """Extract a multiline ``key: |`` block from text."""
    pattern = re.compile(rf"^{re.escape(key)}:\s*\|?\s*\n((?:[ \t]{{2,}}.+\n?)+)", re.MULTILINE)
    m = pattern.search(text)
    if m:
        lines = m.group(1).splitlines()
        return "\n".join(re.sub(r"^[ \t]{2,}", "", l) for l in lines).strip()
    # Single-line value
    pattern2 = re.compile(rf"^{re.escape(key)}:\s*(.+)$", re.MULTILINE)
    m2 = pattern2.search(text)
    if m2:
        return m2.group(1).strip().strip('"\'')
    return None


def parse_profile_config(profile_text: str) -> ProfileConfig:
    """Parse mode configuration from a profile Markdown file.

    Returns a ProfileConfig where every field has sensible defaults matching
    the original hardcoded job-mode behavior when no mode sections exist.
    """
    sections = _split_sections(profile_text)
    config = ProfileConfig(raw_profile=profile_text)

    # --- Extraction Schema ---
    schema_text = sections.get("Extraction Schema")
    if schema_text:
        kv = _parse_kv_block(schema_text)
        config.mode.mode = kv.get("mode", "custom")
        config.mode.top_level_key = kv.get("top_level_key", "items")

        dedup = kv.get("dedup_fields")
        if dedup:
            if dedup.startswith("["):
                config.mode.dedup_fields = [
                    v.strip().strip('"\'') for v in dedup.strip("[]").split(",") if v.strip()
                ]
            else:
                config.mode.dedup_fields = [d.strip() for d in dedup.split() if d.strip()]

        parsed_fields = _parse_fields_block(schema_text)
        if parsed_fields:
            config.mode.fields = parsed_fields
        elif config.mode.mode == "job":
            config.mode.fields = list(_DEFAULT_JOB_FIELDS)
        # custom mode with no fields: keep empty list
    else:
        config.mode.fields = list(_DEFAULT_JOB_FIELDS)

    # --- Extraction Prompt ---
    prompt_text = sections.get("Extraction Prompt")
    if prompt_text:
        config.prompts.system_prompt = _parse_text_block(prompt_text, "system_prompt")
        config.prompts.location_filter = _parse_text_block(prompt_text, "location_filter")
        config.prompts.contact_rules = _parse_text_block(prompt_text, "contact_rules")

    # --- Report Labels ---
    labels_text = sections.get("Report Labels")
    if labels_text:
        kv = _parse_kv_block(labels_text)
        if "report_title" in kv:
            config.labels.report_title = kv["report_title"]
        if "section_high" in kv:
            config.labels.section_high = kv["section_high"]
        if "section_medium" in kv:
            config.labels.section_medium = kv["section_medium"]
        if "section_low" in kv:
            config.labels.section_low = kv["section_low"]
        if "stats_label" in kv:
            config.labels.stats_label = kv["stats_label"]
        if "output_filename" in kv:
            config.labels.output_filename = kv["output_filename"]
        if "profile_section_title" in kv:
            config.labels.profile_section_title = kv["profile_section_title"]
        if "methodology_label" in kv:
            config.labels.methodology_label = kv["methodology_label"]

    # Derive ActionMapping from action field values by keyword matching
    action_field = next(
        (f for f in config.mode.fields if f.name == "action"), None
    )
    if action_field and action_field.values:
        for v in action_field.values:
            vl = v.lower()
            if re.search(r"\b(apply|participate|act|join|high)\b", vl):
                config.actions.high = v
            elif re.search(r"\b(skip|ignore|pass|dismiss)\b", vl):
                config.actions.low = v
            elif re.search(r"\b(inspect|research|review|check|investigate)\b", vl):
                config.actions.medium = v

    return config


# ---------------------------------------------------------------------------
# Schema → prompt builder
# ---------------------------------------------------------------------------

def build_json_schema_prompt(mode_config: ModeConfig) -> str:
    """Build a JSON schema description for the LLM prompt from field definitions.

    Produces the same output as the original hardcoded schema when
    mode_config.fields matches the default job-mode fields.
    """
    lines = ["{"]
    lines.append(f'  "{mode_config.top_level_key}": [')
    lines.append("    {")

    field_descriptions = []
    for f in mode_config.fields:
        if f.name == "source_message_ids":
            field_descriptions.append('      "source_message_ids": [123]')
            continue
        if f.type == "list":
            field_descriptions.append(f'      "{f.name}": ["example"]')
        elif f.values:
            vals = " | ".join(f.values)
            field_descriptions.append(f'      "{f.name}": "{vals}"')
        else:
            field_descriptions.append(f'      "{f.name}": "..."')

    lines.append(",\n".join(field_descriptions))
    lines.append("    }")
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines)
