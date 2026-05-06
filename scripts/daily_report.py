"""Run scan.py and report.py as a small daily-report pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def default_report_output_path(output_dir: Path, scan_date: str | None = None) -> Path:
    date = scan_date or datetime.now(UTC).date().isoformat()
    return output_dir / f"job-scan-report-{date}.md"


def find_latest_scan(output_dir: Path) -> Path:
    scans = sorted(output_dir.glob("scan_*.jsonl"), key=lambda path: path.stat().st_mtime)
    if not scans:
        raise FileNotFoundError(f"No scan_*.jsonl files found in {output_dir}")
    return scans[-1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Telegram scan and generate a daily job report")
    parser.add_argument("channel_list", type=Path, help="Text file with one channel username per line")
    parser.add_argument("--profile", required=True, type=Path, help="Candidate profile MD")
    parser.add_argument("--hours", type=int, default=24, help="Look back this many hours (default: 24)")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--max-messages", type=int)
    parser.add_argument("--html", action="store_true", help="Also output HTML report")
    parser.add_argument("--redact-contact-info", action="store_true")
    parser.add_argument("--next-scan-note")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parent
    args.output_dir.mkdir(parents=True, exist_ok=True)

    scan_cmd = [
        sys.executable,
        str(script_dir / "scan.py"),
        str(args.channel_list),
        str(args.hours),
        "--output-dir",
        str(args.output_dir),
    ]
    if args.allow_incomplete:
        scan_cmd.append("--allow-incomplete")

    subprocess.run(scan_cmd, check=True)
    scan_file = find_latest_scan(args.output_dir)
    report_output = args.report_output or default_report_output_path(args.output_dir)

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
    if args.base_url:
        report_cmd.extend(["--base-url", args.base_url])
    if args.model:
        report_cmd.extend(["--model", args.model])
    if args.max_messages:
        report_cmd.extend(["--max-messages", str(args.max_messages)])
    if args.redact_contact_info:
        report_cmd.append("--redact-contact-info")
    if args.next_scan_note:
        report_cmd.extend(["--next-scan-note", args.next_scan_note])

    subprocess.run(report_cmd, check=True)

    if args.html:
        html_output = report_output.with_suffix(".html")
        html_cmd = [
            sys.executable,
            str(script_dir / "report.py"),
            "--input", str(scan_file),
            "--profile", str(args.profile),
            "--html",
            "--output", str(html_output),
        ]
        if args.base_url:
            html_cmd.extend(["--base-url", args.base_url])
        if args.model:
            html_cmd.extend(["--model", args.model])
        if args.max_messages:
            html_cmd.extend(["--max-messages", str(args.max_messages)])
        subprocess.run(html_cmd, check=True)

    print(f"Daily report saved to {report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
