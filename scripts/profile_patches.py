"""Profile patch suggestion lifecycle for monitor state."""

from __future__ import annotations

import difflib
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from scripts.monitor_common import (
    MonitorStateError,
    PROFILE_PATCH_SCHEMA_VERSION,
    PROJECT_ROOT,
    require_profile_text_without_private_fragments,
    sha256_text,
    utc_now,
)


def _project_root() -> Path:
    facade = sys.modules.get("scripts.monitor_state")
    root = getattr(facade, "PROJECT_ROOT", PROJECT_ROOT) if facade is not None else PROJECT_ROOT
    return Path(root)


def _append_follow_up_rule(profile_text: str, note: str) -> str:
    clean_note = " ".join(note.split())
    line = f"- {clean_note}" if clean_note else "- Follow up on similar future items."
    heading = "## Follow-up Preferences"
    if heading not in profile_text:
        suffix = "\n\n" if profile_text.endswith("\n") else "\n\n"
        return f"{profile_text}{suffix}{heading}\n{line}\n"
    lines = profile_text.splitlines()
    output: list[str] = []
    inserted = False
    in_section = False
    for raw in lines:
        if raw.strip() == heading:
            in_section = True
            output.append(raw)
            continue
        if in_section and raw.startswith("## "):
            output.append(line)
            inserted = True
            in_section = False
        output.append(raw)
    if in_section and not inserted:
        output.append(line)
    return "\n".join(output).rstrip() + "\n"


def _normalize_preference_lines(text: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = re.sub(r"^\s*[-*]\s+", "", raw).strip()
        line = re.sub(r"^\d+\.\s+", "", line)
        line = " ".join(line.split())
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines[:24]


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


def create_profile_patch_suggestion(
    conn: sqlite3.Connection,
    *,
    profile_id: str,
    card_id: str | None,
    note: str,
    profile_path: Path | None,
) -> dict[str, Any]:
    note = require_profile_text_without_private_fragments("Profile note", note)
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
    proposed = _append_follow_up_rule(current, note)
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
    base_profile_hash = row["base_profile_hash"]
    if not base_profile_hash:
        raise MonitorStateError("Profile patch is missing its base hash; regenerate the profile diff.")
    if sha256_text(current) != base_profile_hash:
        raise MonitorStateError("Profile changed after patch was suggested; regenerate the profile diff.")
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
    conn.commit()
    return {
        "patch_id": patch_id,
        "profile_id": row["profile_id"],
        "status": "applied",
        "snapshot_id": snapshot_id,
        "profile_path": str(profile_path),
        "applied_at": now,
    }


def revert_profile_patch(conn: sqlite3.Connection, *, patch_id: str, profile_path: Path | None = None) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM profile_patch_suggestions WHERE patch_id = ?",
        (patch_id,),
    ).fetchone()
    if not row:
        raise MonitorStateError(f"Profile patch not found: {patch_id}")
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
