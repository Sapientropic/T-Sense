"""CLI facade for T-Sense profile monitors.

The monitor implementation is split by product boundary:
configuration/scheduling, artifacts, keyword prefiltering, and run orchestration.
This module stays as the stable public import and argparse entrypoint for old
tests, scripts, and source-checkout launchers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    from scripts import agent_cli
    from scripts import monitor_artifacts as _monitor_artifacts
    from scripts import monitor_config as _monitor_config
    from scripts import monitor_delivery as _monitor_delivery
    from scripts import monitor_execution as _monitor_execution
    from scripts import monitor_prefilter as _monitor_prefilter
    from scripts import monitor_runner as _monitor_runner
except ModuleNotFoundError:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts import agent_cli
    from scripts import monitor_artifacts as _monitor_artifacts
    from scripts import monitor_config as _monitor_config
    from scripts import monitor_delivery as _monitor_delivery
    from scripts import monitor_execution as _monitor_execution
    from scripts import monitor_prefilter as _monitor_prefilter
    from scripts import monitor_runner as _monitor_runner

MonitorConfig = _monitor_config.MonitorConfig

PROJECT_ROOT = _monitor_config.PROJECT_ROOT
PROFILE_RUN_CONFIG_SCHEMA_VERSION = _monitor_config.PROFILE_RUN_CONFIG_SCHEMA_VERSION
RUN_MANIFEST_SCHEMA_VERSION = _monitor_config.RUN_MANIFEST_SCHEMA_VERSION
DEFAULT_PROFILE_ID = _monitor_config.DEFAULT_PROFILE_ID
DEFAULT_DASHBOARD_URL = _monitor_config.DEFAULT_DASHBOARD_URL
DEFAULT_FEEDBACK_EXPORT_PATH = _monitor_config.DEFAULT_FEEDBACK_EXPORT_PATH
DEFAULT_FAST_JOBS_PROFILE_ID = _monitor_config.DEFAULT_FAST_JOBS_PROFILE_ID
DEFAULT_FAST_JOBS_SCAN_WINDOW_HOURS = _monitor_config.DEFAULT_FAST_JOBS_SCAN_WINDOW_HOURS
DEFAULT_FAST_JOBS_INTERVAL_MINUTES = _monitor_config.DEFAULT_FAST_JOBS_INTERVAL_MINUTES
DEFAULT_FAST_JOBS_ALERT_MAX_AGE_MINUTES = _monitor_config.DEFAULT_FAST_JOBS_ALERT_MAX_AGE_MINUTES
DEFAULT_FAST_JOBS_SEMANTIC_MAX_MESSAGES = _monitor_config.DEFAULT_FAST_JOBS_SEMANTIC_MAX_MESSAGES
DEFAULT_FAST_JOBS_SEMANTIC_MAX_TOKENS = _monitor_config.DEFAULT_FAST_JOBS_SEMANTIC_MAX_TOKENS
DEFAULT_FAST_JOBS_SCAN_CONCURRENCY = _monitor_config.DEFAULT_FAST_JOBS_SCAN_CONCURRENCY
DEFAULT_FAST_JOBS_SCAN_DELAY_SECONDS = _monitor_config.DEFAULT_FAST_JOBS_SCAN_DELAY_SECONDS
DEFAULT_FAST_JOBS_SEMANTIC_BATCH_SIZE = _monitor_config.DEFAULT_FAST_JOBS_SEMANTIC_BATCH_SIZE
DEFAULT_FAST_JOBS_SEMANTIC_CONCURRENCY = _monitor_config.DEFAULT_FAST_JOBS_SEMANTIC_CONCURRENCY
DEFAULT_FAST_JOBS_PREFILTER_KEYWORDS = _monitor_config.DEFAULT_FAST_JOBS_PREFILTER_KEYWORDS
PREFILTER_TEXT_FIELDS = _monitor_prefilter.PREFILTER_TEXT_FIELDS
ALERT_SCHEDULE_MODES = _monitor_config.ALERT_SCHEDULE_MODES

utc_now = _monitor_config.utc_now
run_id = _monitor_config.run_id
default_config = _monitor_config.default_config
filter_source_registry = _monitor_config.filter_source_registry
effective_scan_hours = _monitor_config.effective_scan_hours
alert_rule_for_profile = _monitor_config.alert_rule_for_profile
parse_hhmm = _monitor_config.parse_hhmm
local_now_for_profile = _monitor_config.local_now_for_profile
is_work_time = _monitor_config.is_work_time
delivery_enabled_for_profile = _monitor_config.delivery_enabled_for_profile

file_hash = _monitor_artifacts.file_hash
safe_slug = _monitor_artifacts.safe_slug
profile_display_name = _monitor_artifacts.profile_display_name
report_stamp_from_run_id = _monitor_artifacts.report_stamp_from_run_id
report_title_for_profile = _monitor_artifacts.report_title_for_profile
report_file_stem = _monitor_artifacts.report_file_stem
report_output_paths = _monitor_artifacts.report_output_paths
artifact_display_metadata = _monitor_artifacts.artifact_display_metadata
scan_sidecar_paths = _monitor_artifacts.scan_sidecar_paths
load_scan_meta = _monitor_artifacts.load_scan_meta
diagnostics_from_scan_meta = _monitor_artifacts.diagnostics_from_scan_meta
parse_message_date = _monitor_artifacts.parse_message_date
source_ref_dates = _monitor_artifacts.source_ref_dates
annotate_items_with_source_freshness = _monitor_artifacts.annotate_items_with_source_freshness

prefilter_keywords = _monitor_prefilter.prefilter_keywords
semantic_max_messages = _monitor_prefilter.semantic_max_messages
semantic_max_tokens = _monitor_prefilter.semantic_max_tokens
scan_concurrency = _monitor_prefilter.scan_concurrency
scan_delay_seconds = _monitor_prefilter.scan_delay_seconds
semantic_batch_size = _monitor_prefilter.semantic_batch_size
semantic_concurrency = _monitor_prefilter.semantic_concurrency
message_text_for_prefilter = _monitor_prefilter.message_text_for_prefilter
load_jsonl = _monitor_prefilter.load_jsonl
keyword_prefilter_matches = _monitor_prefilter.keyword_prefilter_matches
write_prefiltered_scan = _monitor_prefilter.write_prefiltered_scan

parse_agent_stdout = _monitor_runner.parse_agent_stdout
run_json_command = _monitor_runner.run_json_command
diagnostics_from_agent_error = _monitor_runner.diagnostics_from_agent_error
llm_from_agent_error = _monitor_runner.llm_from_agent_error
monitor_failure_next_step = _monitor_runner.monitor_failure_next_step
source_registry_from_args = _monitor_runner.source_registry_from_args
delivery_targets_for_profile = _monitor_delivery.delivery_targets_for_profile
apply_delivery_runtime_overrides = _monitor_delivery.apply_delivery_runtime_overrides
run_delivery = _monitor_delivery.run_delivery
write_latest_pointer = _monitor_runner.write_latest_pointer


def _sync_modules() -> None:
    """Propagate facade monkeypatches into split modules before delegated calls."""

    _monitor_config.PROJECT_ROOT = PROJECT_ROOT
    _monitor_artifacts.PROJECT_ROOT = PROJECT_ROOT
    _monitor_execution.PROJECT_ROOT = PROJECT_ROOT
    _monitor_runner.PROJECT_ROOT = PROJECT_ROOT
    _monitor_runner.run_json_command = run_json_command


def root_path(value: str | Path, root: Path | None = None) -> Path:
    _sync_modules()
    return _monitor_config.root_path(value, root)


def relative_to_root(path: str | Path | None, root: Path | None = None) -> str | None:
    _sync_modules()
    return _monitor_config.relative_to_root(path, root)


def load_config(config_path: Path, root: Path | None = None) -> MonitorConfig:
    _sync_modules()
    return _monitor_config.load_config(config_path, root=root)


def profile_path(profile: dict[str, Any], root: Path | None = None) -> Path:
    _sync_modules()
    return _monitor_config.profile_path(profile, root=root)


def source_input_args(profile: dict[str, Any], run_dir: Path, root: Path | None = None) -> list[str]:
    _sync_modules()
    return _monitor_config.source_input_args(profile, run_dir, root=root)


def artifact(
    path: Path,
    artifact_type: str,
    *,
    profile_id: str | None = None,
    run_id: str | None = None,
    report_title: str | None = None,
) -> dict[str, Any]:
    _sync_modules()
    return _monitor_artifacts.artifact(
        path,
        artifact_type,
        profile_id=profile_id,
        run_id=run_id,
        report_title=report_title,
    )


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
    _sync_modules()
    return _monitor_runner.report_command_for_scan_input(
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
    allow_partial_failures: bool = False,
    concurrency: int | None = None,
    delay_seconds: float | None = None,
) -> list[str | Path]:
    _sync_modules()
    return _monitor_runner.scan_command(
        run_dir=run_dir,
        source_args=source_args,
        hours=hours,
        allow_incomplete=allow_incomplete,
        allow_partial_failures=allow_partial_failures,
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
    allow_partial_failures: bool = False,
    max_messages: int | None = None,
    max_tokens: int | None = None,
    scan_concurrency_value: int | None = None,
    scan_delay_seconds_value: float | None = None,
    batch_size: int | None = None,
    semantic_concurrency_value: int | None = None,
) -> list[str | Path]:
    _sync_modules()
    return _monitor_runner.daily_report_command(
        profile=profile,
        profile_file=profile_file,
        run_dir=run_dir,
        state_dir=state_dir,
        source_args=source_args,
        hours=hours,
        items_json=items_json,
        allow_incomplete=allow_incomplete,
        allow_partial_failures=allow_partial_failures,
        profile_id=profile_id,
        run_id=run_id,
        max_messages=max_messages,
        max_tokens=max_tokens,
        scan_concurrency_value=scan_concurrency_value,
        scan_delay_seconds_value=scan_delay_seconds_value,
        batch_size=batch_size,
        semantic_concurrency_value=semantic_concurrency_value,
    )


def run_profile(args: argparse.Namespace) -> int:
    _sync_modules()
    return _monitor_runner.run_profile(args)


def test_telegram_bot(args: argparse.Namespace) -> int:
    _sync_modules()
    return _monitor_runner.test_telegram_bot(args)


def write_default_config(args: argparse.Namespace) -> int:
    _sync_modules()
    return _monitor_runner.write_default_config(args)


def export_feedback(args: argparse.Namespace) -> int:
    _sync_modules()
    return _monitor_runner.export_feedback(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run T-Sense profile monitors.", allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-config", help="Write a starter .tgcs/profiles.toml.")
    init.add_argument("--config", default=".tgcs/profiles.toml")
    init.add_argument("--force", action="store_true")
    agent_cli.add_format_argument(init)
    init.set_defaults(func=write_default_config)

    run = subparsers.add_parser("run", help="Run one profile monitor.")
    run.add_argument("--profile-id", default=DEFAULT_PROFILE_ID)
    run.add_argument("--config", default=".tgcs/profiles.toml")
    run.add_argument("--db")
    run.add_argument("--output-dir")
    run.add_argument("--state-dir")
    run.add_argument("--run-id")
    run.add_argument("--hours", type=int)
    run.add_argument("--scan-input", type=Path, help="Use an existing JSONL scan file instead of scanning Telegram.")
    run.add_argument("--items-json", help="Use semantic_items_v1 JSON for report generation.")
    run.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD_URL)
    run.add_argument("--delivery-mode", choices=("off", "dry-run", "live"), default="dry-run")
    run.add_argument("--allow-incomplete", action="store_true")
    agent_cli.add_format_argument(run)
    run.set_defaults(func=run_profile)

    feedback_export = subparsers.add_parser(
        "feedback-export",
        help="Export dashboard feedback as reusable report feedback JSONL.",
    )
    feedback_export.add_argument("--db", default=".tgcs/tgcs.db")
    feedback_export.add_argument("--output", default=DEFAULT_FEEDBACK_EXPORT_PATH)
    agent_cli.add_format_argument(feedback_export)
    feedback_export.set_defaults(func=export_feedback)

    delivery_parser = subparsers.add_parser("delivery-test", help="Test a delivery adapter.")
    delivery_subparsers = delivery_parser.add_subparsers(dest="delivery_command", required=True)
    bot = delivery_subparsers.add_parser("telegram-bot", help="Send or dry-run a Telegram bot test.")
    bot.add_argument("--target-id", default="telegram-bot-default")
    bot.add_argument("--chat-id")
    bot.add_argument("--delivery-mode", choices=("dry-run", "live"), default="dry-run")
    agent_cli.add_format_argument(bot)
    bot.set_defaults(func=test_telegram_bot)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
