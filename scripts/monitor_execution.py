"""Scan/report command execution for profile monitor runs."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.monitor_artifacts import report_output_paths, report_title_for_profile
    from scripts.monitor_config import PROJECT_ROOT, relative_to_root, root_path, source_input_args
    from scripts.monitor_prefilter import (
        keyword_prefilter_matches,
        prefilter_keywords,
        scan_concurrency,
        scan_delay_seconds,
        semantic_batch_size,
        semantic_concurrency,
        semantic_max_messages,
        semantic_max_tokens,
        write_prefiltered_scan,
    )
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.monitor_artifacts import report_output_paths, report_title_for_profile
    from scripts.monitor_config import PROJECT_ROOT, relative_to_root, root_path, source_input_args
    from scripts.monitor_prefilter import (
        keyword_prefilter_matches,
        prefilter_keywords,
        scan_concurrency,
        scan_delay_seconds,
        semantic_batch_size,
        semantic_concurrency,
        semantic_max_messages,
        semantic_max_tokens,
        write_prefiltered_scan,
    )

RunJsonCommand = Callable[[list[str | Path]], tuple[int, dict[str, Any] | None, str]]


@dataclass
class MonitorCommandResult:
    command: list[str | Path]
    commands_executed: list[list[str | Path]]
    exit_code: int
    payload: dict[str, Any] | None
    stderr: str
    report_data: dict[str, Any]
    status: str
    prefilter_context: dict[str, Any]
    scan_path: Path | None
    raw_scan_path: Path | None
    semantic_limit: int | None
    token_limit: int | None
    source_scan_concurrency: int | None
    source_scan_delay_seconds: float | None
    batch_limit: int | None
    semantic_concurrency_limit: int | None


def report_command_for_scan_input(
    *,
    scan_input: Path,
    profile_file: Path,
    run_dir: Path,
    state_dir: Path,
    source_registry: Path | None,
    items_json: str | None,
    profile_id: str,
    run_id: str,
    max_messages: int | None = None,
    max_tokens: int | None = None,
    batch_size: int | None = None,
    semantic_concurrency_value: int | None = None,
) -> list[str | Path]:
    report_title = report_title_for_profile(profile_file, profile_id)
    report_output, html_output = report_output_paths(
        run_dir,
        profile_id=profile_id,
        run_id_value=run_id,
        report_title=report_title,
    )
    cmd: list[str | Path] = [
        sys.executable,
        PROJECT_ROOT / "scripts" / "report.py",
        "--input",
        scan_input,
        "--profile",
        profile_file,
        "--output",
        report_output,
        "--html-output",
        html_output,
        "--state-dir",
        state_dir,
        "--format",
        "json",
    ]
    if source_registry and source_registry.exists():
        cmd.extend(["--source-registry", source_registry])
    if items_json:
        cmd.extend(["--items-json", items_json])
    if max_messages:
        cmd.extend(["--max-messages", str(max_messages)])
    if max_tokens:
        cmd.extend(["--max-tokens", str(max_tokens)])
    if batch_size:
        cmd.extend(["--semantic-batch-size", str(batch_size)])
    if semantic_concurrency_value:
        cmd.extend(["--semantic-concurrency", str(semantic_concurrency_value)])
    return cmd


def scan_command(
    *,
    run_dir: Path,
    source_args: list[str],
    hours: int,
    allow_incomplete: bool,
    concurrency: int | None = None,
    delay_seconds: float | None = None,
) -> list[str | Path]:
    scan_output = run_dir / "scan.jsonl"
    cmd: list[str | Path] = [
        sys.executable,
        PROJECT_ROOT / "scripts" / "scan.py",
        *source_args,
        "--hours",
        str(hours),
        "--output-dir",
        run_dir,
        "--output",
        scan_output,
        "--format",
        "json",
    ]
    if allow_incomplete:
        cmd.append("--allow-incomplete")
    if concurrency:
        cmd.extend(["--scan-concurrency", str(concurrency)])
    if delay_seconds is not None:
        cmd.extend(["--delay", str(delay_seconds)])
    return cmd


def daily_report_command(
    *,
    profile: dict[str, Any],
    profile_file: Path,
    run_dir: Path,
    state_dir: Path,
    source_args: list[str],
    hours: int,
    items_json: str | None,
    allow_incomplete: bool,
    profile_id: str,
    run_id: str,
    max_messages: int | None = None,
    max_tokens: int | None = None,
    scan_concurrency_value: int | None = None,
    scan_delay_seconds_value: float | None = None,
    batch_size: int | None = None,
    semantic_concurrency_value: int | None = None,
) -> list[str | Path]:
    report_title = report_title_for_profile(profile_file, profile_id)
    report_output, _ = report_output_paths(
        run_dir,
        profile_id=profile_id,
        run_id_value=run_id,
        report_title=report_title,
    )
    cmd: list[str | Path] = [
        sys.executable,
        PROJECT_ROOT / "scripts" / "daily_report.py",
        *source_args,
        "--profile",
        profile_file,
        "--hours",
        str(hours),
        "--output-dir",
        run_dir,
        "--report-output",
        report_output,
        "--html",
        "--state-dir",
        state_dir,
        "--format",
        "json",
    ]
    if profile.get("next_scan_note"):
        cmd.extend(["--next-scan-note", str(profile["next_scan_note"])])
    if items_json:
        cmd.extend(["--items-json", items_json])
    if allow_incomplete:
        cmd.append("--allow-incomplete")
    if max_messages:
        cmd.extend(["--max-messages", str(max_messages)])
    if max_tokens:
        cmd.extend(["--max-tokens", str(max_tokens)])
    if scan_concurrency_value:
        cmd.extend(["--scan-concurrency", str(scan_concurrency_value)])
    if scan_delay_seconds_value is not None:
        cmd.extend(["--scan-delay", str(scan_delay_seconds_value)])
    if batch_size:
        cmd.extend(["--semantic-batch-size", str(batch_size)])
    if semantic_concurrency_value:
        cmd.extend(["--semantic-concurrency", str(semantic_concurrency_value)])
    return cmd


def source_registry_from_args(source_args: list[str]) -> Path | None:
    try:
        index = source_args.index("--source-registry")
    except ValueError:
        return None
    if index + 1 >= len(source_args):
        return None
    return Path(source_args[index + 1])


def write_latest_pointer(output_dir: Path, manifest_path: Path) -> None:
    latest = output_dir / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    pointer = latest / "run-manifest.path"
    pointer.write_text(str(manifest_path), encoding="utf-8")


def execute_monitor_commands(
    *,
    args: argparse.Namespace,
    profile: dict[str, Any],
    profile_file: Path,
    run_dir: Path,
    state_dir: Path,
    source_registry: Path,
    scan_window_hours: int,
    run_id_value: str,
    source_args: list[str] | None,
    run_json: RunJsonCommand,
) -> MonitorCommandResult:
    keywords = prefilter_keywords(profile)
    profile_prefilter_enabled = bool(profile.get("prefilter_enabled")) and bool(keywords)
    prefilter_context: dict[str, Any] = {
        "enabled": profile_prefilter_enabled and not args.scan_input,
        "keyword_count": len(keywords),
        "matched_count": None,
        "semantic_stage": "disabled",
    }
    if args.scan_input:
        # scan-input is a deliberate replay/debug lane. Keep the manifest
        # explicit so fast-lane evals do not mistake this path for a cheap
        # keyword-gated monitor run.
        prefilter_context["semantic_stage"] = "bypassed_scan_input" if profile_prefilter_enabled else "not_applicable"
        if profile_prefilter_enabled:
            prefilter_context["bypass_reason"] = "scan_input"
    commands_executed: list[list[str | Path]] = []
    cmd: list[str | Path] = []
    exit_code = 0
    payload: dict[str, Any] | None = None
    stderr = ""
    report_data: dict[str, Any] = {}
    status = "complete"
    scan_path: Path | None = None
    raw_scan_path: Path | None = None
    semantic_limit = semantic_max_messages(profile)
    token_limit = semantic_max_tokens(profile)
    source_scan_concurrency = scan_concurrency(profile)
    source_scan_delay_seconds = scan_delay_seconds(profile)
    batch_limit = semantic_batch_size(profile)
    semantic_concurrency_limit = semantic_concurrency(profile)

    if args.scan_input:
        cmd = report_command_for_scan_input(
            scan_input=root_path(args.scan_input),
            profile_file=profile_file,
            run_dir=run_dir,
            state_dir=state_dir,
            source_registry=source_registry,
            items_json=args.items_json,
            profile_id=args.profile_id,
            run_id=run_id_value,
            max_messages=semantic_limit,
            max_tokens=token_limit,
            batch_size=batch_limit,
            semantic_concurrency_value=semantic_concurrency_limit,
        )
        commands_executed.append(cmd)
        exit_code, payload, stderr = run_json(cmd)
    else:
        source_args = source_args or source_input_args(profile, run_dir)
        if profile.get("prefilter_enabled") and keywords and not args.items_json:
            prefilter_context["semantic_stage"] = "scan_pending"
            cmd = scan_command(
                run_dir=run_dir,
                source_args=source_args,
                hours=scan_window_hours,
                allow_incomplete=args.allow_incomplete,
                concurrency=source_scan_concurrency,
                delay_seconds=source_scan_delay_seconds,
            )
            raw_scan_path = run_dir / "scan.jsonl"
            scan_path = raw_scan_path
            commands_executed.append(cmd)
            exit_code, payload, stderr = run_json(cmd)
            scan_data = payload.get("data", {}) if payload and payload.get("ok") else {}
            if scan_data.get("output_path"):
                raw_scan_path = root_path(scan_data.get("output_path"), PROJECT_ROOT)
            scan_path = raw_scan_path
            prefilter_context["raw_scan_path"] = relative_to_root(raw_scan_path) if raw_scan_path else None
            if exit_code == 0 and raw_scan_path and raw_scan_path.exists():
                matches, keyword_counts = keyword_prefilter_matches(raw_scan_path, keywords)
                prefilter_context.update(
                    {
                        "matched_count": len(matches),
                        "matched_keywords": keyword_counts,
                        "raw_message_count": scan_data.get("message_count"),
                    }
                )
                if not matches:
                    status = "prefilter_no_match"
                    prefilter_context["semantic_stage"] = "skipped_no_keyword_match"
                    report_data = {"status": status, "source_health": scan_data.get("source_health")}
                else:
                    filtered_scan_path = write_prefiltered_scan(
                        source_scan_path=raw_scan_path,
                        run_dir=run_dir,
                        matches=matches,
                        keywords=keywords,
                        keyword_counts=keyword_counts,
                    )
                    scan_path = filtered_scan_path
                    prefilter_context["filtered_scan_path"] = relative_to_root(filtered_scan_path)
                    prefilter_context["semantic_stage"] = "report_pending"
                    effective_registry = source_registry_from_args(source_args) or source_registry
                    cmd = report_command_for_scan_input(
                        scan_input=filtered_scan_path,
                        profile_file=profile_file,
                        run_dir=run_dir,
                        state_dir=state_dir,
                        source_registry=effective_registry,
                        items_json=args.items_json,
                        profile_id=args.profile_id,
                        run_id=run_id_value,
                        max_messages=semantic_limit,
                        max_tokens=token_limit,
                        batch_size=batch_limit,
                        semantic_concurrency_value=semantic_concurrency_limit,
                    )
                    commands_executed.append(cmd)
                    exit_code, payload, stderr = run_json(cmd)
            else:
                status = "failed"
                prefilter_context["semantic_stage"] = "scan_failed"
        else:
            if profile.get("prefilter_enabled") and keywords and args.items_json:
                prefilter_context["semantic_stage"] = "bypassed_items_json"
            cmd = daily_report_command(
                profile=profile,
                profile_file=profile_file,
                run_dir=run_dir,
                state_dir=state_dir,
                source_args=source_args,
                hours=scan_window_hours,
                items_json=args.items_json,
                allow_incomplete=args.allow_incomplete,
                profile_id=args.profile_id,
                run_id=run_id_value,
                max_messages=semantic_limit,
                max_tokens=token_limit,
                scan_concurrency_value=source_scan_concurrency,
                scan_delay_seconds_value=source_scan_delay_seconds,
                batch_size=batch_limit,
                semantic_concurrency_value=semantic_concurrency_limit,
            )
            commands_executed.append(cmd)
            exit_code, payload, stderr = run_json(cmd)

    if payload and payload.get("ok"):
        report_data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
    if status != "prefilter_no_match":
        status = report_data.get("status") or ("complete" if exit_code == 0 else "failed")
    if prefilter_context.get("semantic_stage") == "report_pending":
        prefilter_context["semantic_stage"] = (
            "agent_extraction_required"
            if status == "agent_extraction_required"
            else "report_ran"
            if exit_code == 0
            else "report_failed"
        )
    return MonitorCommandResult(
        command=cmd,
        commands_executed=commands_executed,
        exit_code=exit_code,
        payload=payload,
        stderr=stderr,
        report_data=report_data,
        status=status,
        prefilter_context=prefilter_context,
        scan_path=scan_path,
        raw_scan_path=raw_scan_path,
        semantic_limit=semantic_limit,
        token_limit=token_limit,
        source_scan_concurrency=source_scan_concurrency,
        source_scan_delay_seconds=source_scan_delay_seconds,
        batch_limit=batch_limit,
        semantic_concurrency_limit=semantic_concurrency_limit,
    )
