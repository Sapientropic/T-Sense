"""Run scan.py and report.py as a small daily-report pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    from scripts import agent_cli
    from scripts.profile_schema import parse_profile_config
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import agent_cli
    from scripts.profile_schema import parse_profile_config


def default_report_output_path(
    output_dir: Path,
    scan_date: str | None = None,
    filename_template: str = "job-scan-report-{date}.md",
) -> Path:
    date = scan_date or datetime.now(UTC).date().isoformat()
    return output_dir / filename_template.format(date=date)


def default_scan_output_path(output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"scan_{timestamp}.jsonl"


def parse_agent_stdout(completed) -> dict | None:
    stdout = getattr(completed, "stdout", None)
    if not stdout:
        return None
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Telegram scan and generate a daily report")
    parser.add_argument(
        "channel_list",
        nargs="?",
        type=Path,
        help="Text file with one channel username per line",
    )
    parser.add_argument("--source-registry", type=Path, help="Private source registry JSON.")
    parser.add_argument("--profile", required=True, type=Path, help="Candidate profile MD")
    parser.add_argument("--hours", type=int, default=24, help="Look back this many hours (default: 24)")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--max-messages", type=int)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--scan-concurrency", type=int)
    parser.add_argument("--scan-delay", type=float)
    parser.add_argument("--semantic-batch-size", type=int)
    parser.add_argument("--semantic-concurrency", type=int)
    parser.add_argument(
        "--extractor",
        choices=("auto", "llm", "agent"),
        default="auto",
        help="Semantic extractor passed to report.py.",
    )
    parser.add_argument("--items-json", help="Use agent-produced semantic_items_v1 JSON.")
    parser.add_argument("--html", action="store_true", help="Also output HTML report")
    parser.add_argument("--redact-contact-info", action="store_true")
    parser.add_argument("--next-scan-note")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--allow-partial-failures",
        action="store_true",
        help="Continue report generation when scan.py collected messages from at least one source.",
    )
    parser.add_argument("--state-dir", type=Path, help="Opt-in local item memory directory for report.py.")
    parser.add_argument("--state-read-only", action="store_true", help="Read item memory without writing updates.")
    parser.add_argument(
        "--feedback-jsonl",
        action="append",
        type=Path,
        default=[],
        help="Import exported report feedback JSONL into report.py. Repeat for multiple files.",
    )
    agent_cli.add_format_argument(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    json_mode = agent_cli.is_json_format(args)

    if not args.channel_list and not args.source_registry:
        agent_cli.emit_error(
            args,
            code="source_input_missing",
            message="Missing source input.",
            retryable=False,
            next_step="Pass a channel list or --source-registry .tgcs/sources.json.",
        )
        return agent_cli.EXIT_VALIDATION

    script_dir = Path(__file__).resolve().parent
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Parse profile to get filename template
    profile_config = parse_profile_config(args.profile.read_text(encoding="utf-8"))
    filename_template = profile_config.labels.output_filename

    scan_file = default_scan_output_path(args.output_dir)
    scan_cmd = [
        sys.executable,
        str(script_dir / "scan.py"),
    ]
    if args.source_registry:
        scan_cmd.extend(["--source-registry", str(args.source_registry), "--hours", str(args.hours)])
    else:
        scan_cmd.extend([str(args.channel_list), str(args.hours)])
    scan_cmd.extend(["--output-dir", str(args.output_dir), "--output", str(scan_file)])
    if args.scan_concurrency:
        scan_cmd.extend(["--scan-concurrency", str(args.scan_concurrency)])
    if args.scan_delay is not None:
        scan_cmd.extend(["--delay", str(args.scan_delay)])
    if args.allow_incomplete:
        scan_cmd.append("--allow-incomplete")
    if args.allow_partial_failures:
        scan_cmd.append("--allow-partial-failures")
    if json_mode:
        scan_cmd.extend(["--format", "json"])

    try:
        scan_completed = subprocess.run(
            scan_cmd,
            check=True,
            capture_output=json_mode,
            text=json_mode,
        )
    except subprocess.CalledProcessError as exc:
        if json_mode:
            code = "scan_incomplete" if exc.returncode == agent_cli.EXIT_INCOMPLETE else "scan_failed"
            agent_cli.emit_error(
                args,
                code=code,
                message=f"scan.py failed with exit code {exc.returncode}.",
                retryable=exc.returncode in {agent_cli.EXIT_RUNTIME, agent_cli.EXIT_INCOMPLETE},
                next_step="Inspect the scan JSON envelope or rerun scan.py directly.",
            )
        return exc.returncode or 1
    if not scan_file.exists():
        agent_cli.emit_error(
            args,
            code="scan_output_missing",
            message=f"scan did not create expected output: {scan_file}",
            retryable=True,
            next_step="Rerun scan.py directly and inspect stderr.",
        )
        return agent_cli.EXIT_RUNTIME if json_mode else 1
    report_output = args.report_output or default_report_output_path(args.output_dir, filename_template=filename_template)

    report_cmd = [
        sys.executable,
        str(script_dir / "report.py"),
        "--input",
        str(scan_file),
        "--profile",
        str(args.profile),
        "--output",
        str(report_output),
    ]
    if args.source_registry:
        report_cmd.extend(["--source-registry", str(args.source_registry)])
    if args.base_url:
        report_cmd.extend(["--base-url", args.base_url])
    if args.model:
        report_cmd.extend(["--model", args.model])
    if args.max_messages:
        report_cmd.extend(["--max-messages", str(args.max_messages)])
    if args.max_tokens:
        report_cmd.extend(["--max-tokens", str(args.max_tokens)])
    if args.semantic_batch_size:
        report_cmd.extend(["--semantic-batch-size", str(args.semantic_batch_size)])
    if args.semantic_concurrency:
        report_cmd.extend(["--semantic-concurrency", str(args.semantic_concurrency)])
    if args.extractor:
        report_cmd.extend(["--extractor", args.extractor])
    if args.items_json:
        report_cmd.extend(["--items-json", args.items_json])
    if args.redact_contact_info:
        report_cmd.append("--redact-contact-info")
    if args.next_scan_note:
        report_cmd.extend(["--next-scan-note", args.next_scan_note])
    if args.state_dir:
        report_cmd.extend(["--state-dir", str(args.state_dir)])
    if args.state_read_only:
        report_cmd.append("--state-read-only")
    for feedback_path in args.feedback_jsonl:
        report_cmd.extend(["--feedback-jsonl", str(feedback_path)])
    if args.html:
        html_output = report_output.with_suffix(".html")
        report_cmd.extend(["--html-output", str(html_output)])
    else:
        html_output = None
    report_json_mode = json_mode or args.extractor == "agent"
    if report_json_mode:
        report_cmd.extend(["--format", "json"])

    try:
        report_completed = subprocess.run(
            report_cmd,
            check=True,
            capture_output=report_json_mode,
            text=report_json_mode,
        )
    except subprocess.CalledProcessError as exc:
        if json_mode:
            report_payload = parse_agent_stdout(exc)
            report_error = report_payload.get("error") if isinstance(report_payload, dict) and isinstance(report_payload.get("error"), dict) else {}
            agent_cli.emit_error(
                args,
                code=str(report_error.get("code") or "report_failed"),
                message=str(report_error.get("message") or f"report.py failed with exit code {exc.returncode}."),
                retryable=exc.returncode == agent_cli.EXIT_RUNTIME,
                next_step=str(report_error.get("next_step") or "Inspect report.py JSON envelope or rerun report.py directly."),
                details=report_error.get("details") if isinstance(report_error.get("details"), dict) else None,
            )
        return exc.returncode or 1

    report_payload = parse_agent_stdout(report_completed) if report_json_mode else None
    report_data = report_payload.get("data", {}) if report_payload else {}
    if json_mode:
        scan_payload = parse_agent_stdout(scan_completed)
        scan_data = scan_payload.get("data", {}) if scan_payload else {}
        status = report_data.get("status", "complete")
        agent_cli.print_json(
            agent_cli.envelope_success(
                {
                    "status": status,
                    "scan_path": str(scan_file),
                    "report_path": str(report_output),
                    "html_path": str(html_output) if html_output else None,
                    "source_registry_path": str(args.source_registry)
                    if args.source_registry
                    else None,
                    "source_health": scan_data.get("source_health"),
                    "report_stats": report_data.get("stats"),
                    "source_summary": report_data.get("source_summary"),
                    "state_summary": report_data.get("state_summary"),
                    "llm": report_data.get("llm"),
                    "items": report_data.get("items"),
                    "extraction_request_path": report_data.get("request_path"),
                    "items_output_path": report_data.get("items_output_path"),
                }
            )
        )
    elif report_data.get("status") == "agent_extraction_required":
        print(f"Semantic extraction request saved to {report_data.get('request_path')}")
        print(f"Write items JSON to {report_data.get('items_output_path')}")
    else:
        print(f"Daily report saved to {report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
