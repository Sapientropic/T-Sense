"""Profile monitor command orchestration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from scripts import agent_cli, delivery, monitor_execution, monitor_state
    from scripts.monitor_artifacts import (
        annotate_items_with_source_freshness,
        artifact,
        diagnostics_from_scan_meta,
        file_hash,
        load_scan_meta,
        report_title_for_profile,
        scan_sidecar_paths,
    )
    from scripts.monitor_config import (
        DEFAULT_DASHBOARD_URL,
        PROJECT_ROOT,
        PROFILE_RUN_CONFIG_SCHEMA_VERSION,
        RUN_MANIFEST_SCHEMA_VERSION,
        alert_rule_for_profile,
        delivery_enabled_for_profile,
        effective_scan_hours,
        load_config,
        profile_path,
        relative_to_root,
        root_path,
        run_id,
        source_input_args,
        utc_now,
    )
    from scripts.monitor_delivery import (
        apply_delivery_runtime_overrides,
        delivery_targets_for_profile,
        run_delivery,
    )
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts import agent_cli, delivery, monitor_execution, monitor_state
    from scripts.monitor_artifacts import (
        annotate_items_with_source_freshness,
        artifact,
        diagnostics_from_scan_meta,
        file_hash,
        load_scan_meta,
        report_title_for_profile,
        scan_sidecar_paths,
    )
    from scripts.monitor_config import (
        DEFAULT_DASHBOARD_URL,
        PROJECT_ROOT,
        PROFILE_RUN_CONFIG_SCHEMA_VERSION,
        RUN_MANIFEST_SCHEMA_VERSION,
        alert_rule_for_profile,
        delivery_enabled_for_profile,
        effective_scan_hours,
        load_config,
        profile_path,
        relative_to_root,
        root_path,
        run_id,
        source_input_args,
        utc_now,
    )
    from scripts.monitor_delivery import (
        apply_delivery_runtime_overrides,
        delivery_targets_for_profile,
        run_delivery,
    )



def parse_agent_stdout(completed: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    if not completed.stdout:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None



def run_json_command(cmd: list[str | Path]) -> tuple[int, dict[str, Any] | None, str]:
    completed = subprocess.run(
        [str(part) for part in cmd],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, parse_agent_stdout(completed), completed.stderr or ""



def diagnostics_from_agent_error(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    diagnostics = details.get("diagnostics") if isinstance(details.get("diagnostics"), list) else []
    return [item for item in diagnostics if isinstance(item, dict)]



def llm_from_agent_error(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    llm = details.get("llm") if isinstance(details.get("llm"), dict) else None
    return llm



def monitor_failure_next_step(diagnostics: list[dict[str, Any]]) -> str:
    top_code = monitor_state.top_diagnostic_code(diagnostics)
    if top_code in {"llm_output_truncated", "semantic_json_invalid"}:
        return (
            "Open Signal Desk Profiles and raise semantic_max_tokens, lower semantic_max_messages, "
            "or narrow the source/prefilter before rerunning the practice scan."
        )
    if top_code in {"channel_failures", "no_messages_fetched", "source_access_failed"}:
        return "Open Start > Check source access, then pause inaccessible sources or inspect scan.errors.log."
    if top_code:
        return f"Open Runs for diagnostic {top_code}, then rerun after fixing that stage."
    return "Inspect the run manifest and rerun the failing scan/report command if needed."



MonitorCommandResult = monitor_execution.MonitorCommandResult


def _sync_monitor_execution_project_root() -> None:
    monitor_execution.PROJECT_ROOT = PROJECT_ROOT


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
    _sync_monitor_execution_project_root()
    return monitor_execution.report_command_for_scan_input(
        scan_input=scan_input,
        profile_file=profile_file,
        run_dir=run_dir,
        state_dir=state_dir,
        source_registry=source_registry,
        items_json=items_json,
        profile_id=profile_id,
        run_id=run_id,
        max_messages=max_messages,
        max_tokens=max_tokens,
        batch_size=batch_size,
        semantic_concurrency_value=semantic_concurrency_value,
    )


def scan_command(
    *,
    run_dir: Path,
    source_args: list[str],
    hours: int,
    allow_incomplete: bool,
    concurrency: int | None = None,
    delay_seconds: float | None = None,
) -> list[str | Path]:
    _sync_monitor_execution_project_root()
    return monitor_execution.scan_command(
        run_dir=run_dir,
        source_args=source_args,
        hours=hours,
        allow_incomplete=allow_incomplete,
        concurrency=concurrency,
        delay_seconds=delay_seconds,
    )


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
    _sync_monitor_execution_project_root()
    return monitor_execution.daily_report_command(
        profile=profile,
        profile_file=profile_file,
        run_dir=run_dir,
        state_dir=state_dir,
        source_args=source_args,
        hours=hours,
        items_json=items_json,
        allow_incomplete=allow_incomplete,
        profile_id=profile_id,
        run_id=run_id,
        max_messages=max_messages,
        max_tokens=max_tokens,
        scan_concurrency_value=scan_concurrency_value,
        scan_delay_seconds_value=scan_delay_seconds_value,
        batch_size=batch_size,
        semantic_concurrency_value=semantic_concurrency_value,
    )


def source_registry_from_args(source_args: list[str]) -> Path | None:
    return monitor_execution.source_registry_from_args(source_args)


def write_latest_pointer(output_dir: Path, manifest_path: Path) -> None:
    monitor_execution.write_latest_pointer(output_dir, manifest_path)


def execute_monitor_commands(**kwargs: Any) -> MonitorCommandResult:
    _sync_monitor_execution_project_root()
    return monitor_execution.execute_monitor_commands(**kwargs)



def run_profile(args: argparse.Namespace) -> int:
    config_path = root_path(args.config)
    try:
        config = load_config(config_path)
    except ValueError as exc:
        agent_cli.emit_error(
            args,
            code="profile_run_config_invalid",
            message=str(exc),
            retryable=False,
            next_step="Fix .tgcs/profiles.toml or pass --config with a valid profile_run_config_v1 file.",
        )
        return agent_cli.EXIT_VALIDATION
    profile = config.profiles.get(args.profile_id)
    if not profile:
        agent_cli.emit_error(
            args,
            code="profile_not_found",
            message=f"Profile id not found: {args.profile_id}",
            retryable=False,
            next_step="Add the profile to .tgcs/profiles.toml or choose an existing profile id.",
        )
        return agent_cli.EXIT_VALIDATION
    db_path = root_path(args.db or config.defaults.get("database", ".tgcs/tgcs.db"))
    conn = monitor_state.connect(db_path)
    config = apply_delivery_runtime_overrides(conn, config)
    profile = monitor_state.apply_profile_runtime_overrides(conn, profile)
    if not profile.get("enabled", True):
        conn.close()
        agent_cli.emit_error(
            args,
            code="profile_disabled",
            message=f"Profile is disabled: {args.profile_id}",
            retryable=True,
            next_step="Enable the profile in Signal Desk Profiles before running it.",
        )
        return agent_cli.EXIT_VALIDATION

    started_at = utc_now()
    current_run_id = args.run_id or run_id()
    output_dir = root_path(args.output_dir or config.defaults.get("output_dir", "output"))
    run_dir = output_dir / "runs" / current_run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        conn.close()
        agent_cli.emit_error(
            args,
            code="run_id_exists",
            message=f"Run output already exists: {run_dir}",
            retryable=False,
            next_step="Choose a different --run-id or let monitor.py generate one.",
        )
        return agent_cli.EXIT_VALIDATION
    state_dir = root_path(args.state_dir or config.defaults.get("state_dir", ".tgcs/state"))
    dashboard_url = args.dashboard_url or str(config.defaults.get("dashboard_url") or DEFAULT_DASHBOARD_URL)
    profile_file = profile_path(profile)
    if not profile_file.exists():
        conn.close()
        agent_cli.emit_error(
            args,
            code="profile_file_not_found",
            message=f"Profile file not found: {profile_file}",
            retryable=False,
            next_step="Create the local profile copy or fix the profile path.",
        )
        return agent_cli.EXIT_VALIDATION

    source_registry = root_path(profile.get("source_registry") or ".tgcs/sources.json")
    scan_window_hours = effective_scan_hours(args, profile)
    source_args: list[str] | None = None
    if not args.scan_input:
        source_args = source_input_args(profile, run_dir)
        if not source_args:
            conn.close()
            agent_cli.emit_error(
                args,
                code="source_input_missing",
                message="Missing source input for monitor run.",
                retryable=False,
                next_step="Create .tgcs/sources.json, configure source_registry, or provide a channel list.",
            )
            return agent_cli.EXIT_VALIDATION
    execution = execute_monitor_commands(
        args=args,
        profile=profile,
        profile_file=profile_file,
        run_dir=run_dir,
        state_dir=state_dir,
        source_registry=source_registry,
        scan_window_hours=scan_window_hours,
        run_id_value=current_run_id,
        source_args=source_args,
        run_json=run_json_command,
    )
    commands_executed = execution.commands_executed
    cmd = execution.command
    exit_code = execution.exit_code
    payload = execution.payload
    stderr = execution.stderr
    report_data = execution.report_data
    status = execution.status
    prefilter_context = execution.prefilter_context
    scan_path = execution.scan_path
    raw_scan_path = execution.raw_scan_path
    semantic_limit = execution.semantic_limit
    token_limit = execution.token_limit
    source_scan_concurrency = execution.source_scan_concurrency
    source_scan_delay_seconds = execution.source_scan_delay_seconds
    batch_limit = execution.batch_limit
    semantic_concurrency_limit = execution.semantic_concurrency_limit
    report_path: Path | None = None
    html_path: Path | None = None
    items: list[dict[str, Any]] = []
    report_path = root_path(report_data.get("report_path"), PROJECT_ROOT) if report_data.get("report_path") else None
    html_path = root_path(report_data.get("html_path"), PROJECT_ROOT) if report_data.get("html_path") else None
    if report_data.get("scan_path"):
        scan_path = root_path(report_data.get("scan_path"), PROJECT_ROOT)
    elif args.scan_input:
        scan_path = root_path(args.scan_input)
    items = report_data.get("items") if isinstance(report_data.get("items"), list) else []
    items = annotate_items_with_source_freshness(items, scan_path)

    # Keep this after apply_profile_runtime_overrides() and before run writeback:
    # upsert_profile() replaces config_json, so the profile dict must already
    # include Desk runtime settings such as enabled and alert_schedule_mode.
    monitor_state.upsert_profile(conn, {**profile, "path": str(profile_file)})
    for target in config.delivery_targets.values():
        monitor_state.upsert_delivery_target(conn, target)
    monitor_state.record_run(
        conn,
        {
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "run_id": current_run_id,
            "profile_id": args.profile_id,
            "status": "running",
            "started_at": started_at,
            "completed_at": None,
            "artifacts": [],
        },
    )

    cards: list[dict[str, Any]] = []
    alert_count = 0
    alert_events: list[dict[str, Any]] = []
    dashboard_report_path = html_path or report_path
    if exit_code == 0 and status != "agent_extraction_required":
        cards = monitor_state.upsert_review_cards(
            conn,
            profile_id=args.profile_id,
            run_id=current_run_id,
            items=items,
            report_path=relative_to_root(dashboard_report_path) if dashboard_report_path else None,
            dashboard_url=dashboard_url,
        )
        delivery_enabled, delivery_suppressed_reason = delivery_enabled_for_profile(profile)
        alert_count, alert_events = run_delivery(
            conn=conn,
            run_id_value=current_run_id,
            profile_id=args.profile_id,
            cards=cards,
            targets=delivery_targets_for_profile(config, profile),
            mode=args.delivery_mode,
            alert_rule=alert_rule_for_profile(profile),
            delivery_enabled=delivery_enabled,
            report_path=relative_to_root(dashboard_report_path) if dashboard_report_path else None,
            dashboard_url=dashboard_url,
        )
    else:
        delivery_enabled, delivery_suppressed_reason = delivery_enabled_for_profile(profile)

    completed_at = utc_now()
    manifest_diagnostics = report_data.get("diagnostics") if isinstance(report_data.get("diagnostics"), list) else []
    command_error_diagnostics = diagnostics_from_agent_error(payload) if exit_code != 0 else []
    if not manifest_diagnostics:
        manifest_diagnostics = command_error_diagnostics or diagnostics_from_scan_meta(
            load_scan_meta(raw_scan_path or scan_path, run_dir)
        )
    artifacts = []
    report_title = report_title_for_profile(profile_file, args.profile_id)
    if raw_scan_path and raw_scan_path.exists() and raw_scan_path != scan_path:
        artifacts.append(artifact(raw_scan_path, "raw_scan", profile_id=args.profile_id, run_id=current_run_id))
    for path, kind in ((scan_path, "scan"), (report_path, "report_markdown"), (html_path, "report_html")):
        if path and path.exists():
            artifacts.append(
                artifact(
                    path,
                    kind,
                    profile_id=args.profile_id,
                    run_id=current_run_id,
                    report_title=report_title,
                )
            )
    meta_path, errors_path = scan_sidecar_paths(raw_scan_path or scan_path, run_dir)
    if meta_path.exists():
        artifacts.append(artifact(meta_path, "scan_meta", profile_id=args.profile_id, run_id=current_run_id))
    if errors_path.exists():
        artifacts.append(artifact(errors_path, "scan_errors", profile_id=args.profile_id, run_id=current_run_id))
    llm_payload = report_data.get("llm") or llm_from_agent_error(payload)
    semantic_manifest = {
        "max_messages": semantic_limit,
        "max_tokens": token_limit,
        "batch_size": batch_limit,
        "concurrency": semantic_concurrency_limit or 1,
    }
    scan_manifest = {"concurrency": source_scan_concurrency or 1}
    if source_scan_delay_seconds is not None:
        scan_manifest["delay_seconds"] = source_scan_delay_seconds
    manifest = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": current_run_id,
        "profile_id": args.profile_id,
        "profile_path": relative_to_root(profile_file),
        "profile_hash": file_hash(profile_file),
        "source_registry_path": relative_to_root(source_registry) if source_registry.exists() else None,
        "source_registry_hash": file_hash(source_registry) if source_registry.exists() else None,
        "scan_window": {"hours": scan_window_hours},
        "scan": scan_manifest,
        "source_filters": {
            "topics": profile.get("source_topics") or profile.get("topics") or [],
            "source_ids": profile.get("source_ids") or [],
        },
        "alert_rule": alert_rule_for_profile(profile),
        "semantic": semantic_manifest,
        "alert_schedule": {
            "mode": profile.get("alert_schedule_mode") or "work_hours",
            "delivery_enabled": delivery_enabled,
            "suppressed_reason": "" if delivery_enabled else delivery_suppressed_reason,
        },
        "prefilter": prefilter_context,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "artifacts": artifacts,
        "report_status": status,
        "alert_count": alert_count,
        "review_card_count": len(cards),
        "diagnostics": manifest_diagnostics,
        "error_summary": None if exit_code == 0 else {"exit_code": exit_code, "stderr": stderr[-2000:]},
        "llm": llm_payload,
        "delivery_attempts": [event["delivery_attempt"] for event in alert_events],
        "command": [str(part) for part in cmd],
        "commands": [[str(part) for part in command] for command in commands_executed],
    }
    manifest_path = run_dir / "run-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_latest_pointer(output_dir, manifest_path)
    monitor_state.record_run(conn, manifest)
    conn.close()

    data = {
        "schema_version": "monitor_run_result_v1",
        "status": status,
        "run_id": current_run_id,
        "manifest_path": relative_to_root(manifest_path),
        "db_path": relative_to_root(db_path),
        "report_path": relative_to_root(report_path) if report_path else None,
        "html_path": relative_to_root(html_path) if html_path else None,
        "review_card_count": len(cards),
        "alert_count": alert_count,
        "prefilter": prefilter_context,
        "semantic": semantic_manifest,
        "diagnostics": manifest_diagnostics,
        "llm": llm_payload,
        "delivery_attempts": [event["delivery_attempt"] for event in alert_events],
        "extraction_request_path": report_data.get("extraction_request_path") or report_data.get("request_path"),
        "items_output_path": report_data.get("items_output_path"),
    }
    if agent_cli.is_json_format(args):
        if exit_code == 0:
            agent_cli.print_json(agent_cli.envelope_success(data))
        else:
            agent_cli.print_json(
                agent_cli.envelope_error(
                    code="monitor_run_failed",
                    message=f"Monitor run failed with exit code {exit_code}.",
                    retryable=exit_code in {agent_cli.EXIT_RUNTIME, agent_cli.EXIT_INCOMPLETE},
                    next_step=monitor_failure_next_step(manifest_diagnostics),
                    details=data,
                )
            )
    else:
        print(f"Monitor run saved: {manifest_path}")
    return exit_code



def test_telegram_bot(args: argparse.Namespace) -> int:
    chat_id = args.chat_id or ""
    if not chat_id:
        agent_cli.emit_error(
            args,
            code="telegram_bot_chat_id_missing",
            message="Telegram bot chat_id is required for delivery test.",
            retryable=False,
            next_step="Pass --chat-id or add a chat_id to .tgcs/profiles.toml.",
        )
        return agent_cli.EXIT_VALIDATION
    attempt = delivery.send_telegram_bot_message(
        target_id=args.target_id,
        chat_id=chat_id,
        text="T-Sense delivery test.",
        mode=args.delivery_mode,
    )
    if agent_cli.is_json_format(args):
        agent_cli.print_json(agent_cli.envelope_success({"attempt": attempt.to_dict()}))
    else:
        print(f"Telegram bot delivery test: {attempt.status}")
    return agent_cli.EXIT_SUCCESS if attempt.ok else agent_cli.EXIT_RUNTIME



def write_default_config(args: argparse.Namespace) -> int:
    config_path = root_path(args.config)
    if config_path.exists() and not args.force:
        if not agent_cli.is_json_format(args):
            print(f"Profile run config already exists: {config_path}")
        return agent_cli.EXIT_SUCCESS
    config_path.parent.mkdir(parents=True, exist_ok=True)
    text = """schema_version = "profile_run_config_v1"

[defaults]
output_dir = "output"
state_dir = ".tgcs/state"
database = ".tgcs/tgcs.db"
dashboard_url = "http://127.0.0.1:8765"

[[profiles]]
id = "market-news"
path = "profiles/templates/market-news.md"
enabled = true
timezone = "Asia/Shanghai"
work_interval_minutes = 120
off_hours_interval_minutes = 360
scan_window_hours = 24
source_registry = ".tgcs/sources.json"
channel_list = "channel_lists/example.txt"
source_topics = ["market-news"]
alert_rule = "high_new_or_changed"
alert_schedule_mode = "work_hours"
delivery_targets = ["telegram-bot-default"]
dashboard_visible = true

[[profiles]]
id = "jobs-fast"
path = "profiles/templates/jobs.md"
enabled = true
timezone = "Asia/Shanghai"
work_start = "09:00"
work_end = "23:00"
work_interval_minutes = 15
off_hours_interval_minutes = 60
scan_window_hours = 2
source_registry = ".tgcs/sources.json"
channel_list = "channel_lists/example.txt"
source_topics = ["jobs"]
alert_rule = "high_new_or_changed"
alert_max_age_minutes = 60
alert_schedule_mode = "work_hours"
delivery_targets = ["telegram-bot-default"]
dashboard_visible = true
prefilter_enabled = true
# Keep high-frequency alert batches bounded; use a separate backfill/audit lane
# if you need exhaustive semantic extraction over a larger catch-up window.
scan_concurrency = 3
scan_delay_seconds = 0.2
semantic_max_messages = 40
semantic_max_tokens = 6000
semantic_batch_size = 20
semantic_concurrency = 2
prefilter_keywords = [
  "hiring",
  "we're hiring",
  "is hiring",
  "job opening",
  "open role",
  "remote",
  "apply",
  "frontend",
  "backend",
  "fullstack",
  "react",
  "typescript",
  "engineer",
  "developer",
  "freelance",
  "contract",
  "contractor",
  "gig",
  "bounty",
  "paid project",
  "mini app",
  "mini apps",
  "telegram mini app",
  "ton",
  "usdt",
  "budget",
  "招聘",
  "招人",
  "岗位",
  "职位",
  "远程",
  "简历",
  "外包",
  "接活",
  "兼职",
  "私活",
  "项目",
  "预算",
]

[[delivery]]
id = "telegram-bot-default"
type = "telegram_bot"
enabled = false
chat_id = ""
"""
    config_path.write_text(text, encoding="utf-8")
    data = {"schema_version": PROFILE_RUN_CONFIG_SCHEMA_VERSION, "config_path": relative_to_root(config_path)}
    if agent_cli.is_json_format(args):
        agent_cli.print_json(agent_cli.envelope_success(data))
    else:
        print(f"Profile run config written: {config_path}")
    return agent_cli.EXIT_SUCCESS



def export_feedback(args: argparse.Namespace) -> int:
    db_path = root_path(args.db)
    output_path = root_path(args.output)
    conn = monitor_state.connect(db_path)
    try:
        entries = monitor_state.export_feedback_entries(conn)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
        output_path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
        exported_at = monitor_state.utc_now()
        monitor_state.record_feedback_export(
            conn,
            output_path=relative_to_root(output_path),
            feedback_count=len(entries),
            exported_at=exported_at,
        )
    finally:
        conn.close()

    data = {
        "schema_version": "feedback_export_result_v1",
        "feedback_count": len(entries),
        "output_path": relative_to_root(output_path),
        "changed_since_last_export": False,
        "exported_at": exported_at,
    }
    if agent_cli.is_json_format(args):
        agent_cli.print_json(agent_cli.envelope_success(data))
    else:
        print(f"Feedback exported: {output_path} ({len(entries)} rows)")
    return agent_cli.EXIT_SUCCESS
