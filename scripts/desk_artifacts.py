"""Artifact path and feedback export helpers for the local dashboard."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote


class DashboardArtifactError(Exception):
    """Raised when a requested dashboard artifact is missing or outside output/runs."""


def is_dashboard_report_artifact_name(name: str) -> bool:
    lower = name.lower()
    if lower in {"report.html", "report.md"}:
        return True
    path = PurePosixPath(lower)
    if path.suffix not in {".html", ".md"}:
        return False
    return any(token in path.stem.split("-") for token in {"report", "brief"})


def resolve_run_artifact_path(
    requested_path: str,
    *,
    project_root: Path,
    artifact_root: Path | None = None,
) -> Path:
    decoded = unquote(requested_path).replace("\\", "/").lstrip("/")
    parts = PurePosixPath(decoded).parts
    if ".." in parts or not parts:
        raise DashboardArtifactError("artifact_path_outside_output_runs")
    if "runs" not in parts:
        raise DashboardArtifactError("artifact_path_must_include_runs")
    run_index = parts.index("runs")
    if run_index >= len(parts) - 2:
        raise DashboardArtifactError("artifact_path_missing")
    if not is_dashboard_report_artifact_name(parts[-1]):
        raise DashboardArtifactError("artifact_type_not_report")

    root = (artifact_root or project_root.joinpath(*parts[: run_index + 1])).resolve()
    relative = "/".join(parts[run_index + 1 :])
    if not relative:
        raise DashboardArtifactError("artifact_path_missing")

    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DashboardArtifactError("artifact_path_outside_output_runs") from exc
    if not candidate.exists() or not candidate.is_file():
        raise DashboardArtifactError("artifact_not_found")
    return candidate


def is_dashboard_openable_artifact_path(path: str) -> bool:
    cleaned = str(path or "").strip().replace("\\", "/")
    if (
        not cleaned
        or cleaned.startswith("/")
        or re.match(r"^[A-Za-z]:", cleaned)
        or re.match(r"^[a-z][a-z0-9+.-]*://", cleaned, flags=re.IGNORECASE)
        or re.search(r"[\x00-\x1f\x7f]", cleaned)
    ):
        return False
    parts = PurePosixPath(cleaned).parts
    if not parts or ".." in parts or not is_dashboard_report_artifact_name(parts[-1]):
        return False
    if "runs" in parts:
        run_index = parts.index("runs")
        return run_index < len(parts) - 2
    return parts[0] == "output" and len(parts) >= 2


def resolve_dashboard_artifact_path(
    requested_path: str,
    *,
    project_root: Path,
    artifact_root: Path | None = None,
) -> Path:
    decoded = unquote(requested_path).replace("\\", "/").lstrip("/")
    parts = PurePosixPath(decoded).parts
    if not is_dashboard_openable_artifact_path(decoded):
        raise DashboardArtifactError("artifact_type_not_report")
    if "runs" in parts:
        return resolve_run_artifact_path(decoded, project_root=project_root, artifact_root=artifact_root)

    root = (artifact_root or project_root.joinpath(parts[0])).resolve()
    relative = "/".join(parts[1:])
    if not relative:
        raise DashboardArtifactError("artifact_path_missing")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DashboardArtifactError("artifact_path_outside_output") from exc
    if not candidate.exists() or not candidate.is_file():
        raise DashboardArtifactError("artifact_not_found")
    return candidate


def dashboard_relative_path(path: Path, *, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def dashboard_feedback_export_target(output_path: Path | None = None, *, project_root: Path) -> Path:
    target = output_path or project_root / "output" / "feedback" / "review-feedback.jsonl"
    if not target.is_absolute():
        target = project_root / target
    resolved = target.resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ValueError("feedback_export_path_outside_project") from exc
    return resolved


def write_feedback_export(
    conn,
    *,
    project_root: Path,
    monitor_state_module,
    output_path: Path | None = None,
) -> dict:
    target = dashboard_feedback_export_target(output_path, project_root=project_root)
    entries = monitor_state_module.export_feedback_entries(conn)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    target.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    exported_at = monitor_state_module.utc_now()
    relative_path = dashboard_relative_path(target, project_root=project_root)
    monitor_state_module.record_feedback_export(
        conn,
        output_path=relative_path,
        feedback_count=len(entries),
        exported_at=exported_at,
    )
    return {
        "schema_version": "feedback_export_result_v1",
        "feedback_count": len(entries),
        "output_path": relative_path,
        "changed_since_last_export": False,
        "exported_at": exported_at,
    }
