"""Shared path helpers and command launchers for the tgcs facade."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent.parent



def _running_from_source_checkout() -> bool:
    return (PACKAGE_ROOT / "pyproject.toml").exists() and (PACKAGE_ROOT / "scripts" / "tgcs.py").exists()



def _default_project_root() -> Path:
    # A source checkout is both the code root and the workspace.  A wheel/pipx/uvx
    # install keeps read-only fixtures in site-packages, so mutable state and
    # outputs must follow the caller's cwd instead of the package directory.
    if _running_from_source_checkout():
        return PACKAGE_ROOT
    return Path.cwd()



PROJECT_ROOT = _default_project_root()



LOCAL_DIR = ".tgcs"



CONFIG_NAME = "config.toml"



PROFILES_CONFIG_NAME = "profiles.toml"



DEFAULT_PROFILE = "market-news"



DEFAULT_FEEDBACK_EXPORT_PATH = "output/feedback/review-feedback.jsonl"



DEFAULT_TGCLI_CONFIG_PATH = Path.home() / ".config" / "tgcli" / "config.toml"



DEFAULT_SESSION_PATH = Path.home() / ".config" / "tgcli" / "session"



PROFILE_ALIASES = {
    "jobs": "profiles/templates/jobs.md",
    "airdrops": "profiles/templates/airdrops.md",
    "market-news": "profiles/templates/market-news.md",
    "research-leads": "profiles/templates/research-leads.md",
    "competitor-monitoring": "profiles/templates/competitor-monitoring.md",
}



def _python() -> str:
    return sys.executable



def _root_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path



def _asset_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    local_path = PROJECT_ROOT / path
    if local_path.exists():
        return local_path
    packaged_path = PACKAGE_ROOT / path
    if packaged_path.exists():
        return packaged_path
    return local_path



def _script(name: str) -> Path:
    if _running_from_source_checkout():
        local_script = PROJECT_ROOT / "scripts" / name
        if local_script.exists():
            return local_script
    return PACKAGE_ROOT / "scripts" / name



def _local_path(*parts: str) -> Path:
    return PROJECT_ROOT / LOCAL_DIR / Path(*parts)



def _read_config() -> dict[str, Any]:
    path = _local_path(CONFIG_NAME)
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        payload = tomllib.load(fh)
    return payload if isinstance(payload, dict) else {}



def _configured_path(config: dict[str, Any], key: str, default: str) -> Path:
    value = str(config.get(key) or default)
    return _root_path(value)



def _profile_path(value: str | None, config: dict[str, Any]) -> Path:
    profile = value or str(config.get("profile") or DEFAULT_PROFILE)
    if profile in PROFILE_ALIASES:
        return _asset_path(PROFILE_ALIASES[profile])
    if profile.endswith(".md") or "/" in profile or "\\" in profile:
        return _asset_path(profile)
    return _asset_path(f"profiles/templates/{profile}.md")



def _default_source_registry(config: dict[str, Any]) -> Path:
    return _configured_path(config, "source_registry", f"{LOCAL_DIR}/sources.json")



def _default_channel_list(config: dict[str, Any]) -> Path:
    value = str(config.get("channel_list") or "channel_lists/example.txt")
    return _asset_path(value)



def _default_output_dir(config: dict[str, Any]) -> Path:
    return _configured_path(config, "output_dir", "output")



def _default_state_dir(config: dict[str, Any]) -> Path:
    return _configured_path(config, "state_dir", f"{LOCAL_DIR}/state")



def _source_args(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    if getattr(args, "source_registry", None):
        return ["--source-registry", str(_root_path(args.source_registry))]
    registry = _default_source_registry(config)
    if registry.exists():
        return ["--source-registry", str(registry)]
    channel_list = _root_path(getattr(args, "channel_list", None) or _default_channel_list(config))
    return [str(channel_list)]



def _doctor_source_args(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    if getattr(args, "source_registry", None):
        return ["--source-registry", str(_root_path(args.source_registry))]
    registry = _default_source_registry(config)
    if registry.exists():
        return ["--source-registry", str(registry)]
    channel_list = _root_path(getattr(args, "channel_list", None) or _default_channel_list(config))
    return ["--channel-list", str(channel_list)]



def _run(cmd: list[str | Path], *, cwd: Path | None = None) -> int:
    parts = [str(part) for part in cmd]
    if cwd is None:
        completed = subprocess.run(parts, check=False)
    else:
        completed = subprocess.run(parts, check=False, cwd=cwd)
    return completed.returncode



def _parse_node_version(raw: str) -> tuple[int, int, int] | None:
    text = raw.strip().removeprefix("v")
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)



def _node_version_satisfies_dashboard_contract(version: tuple[int, int, int]) -> bool:
    major, minor, patch = version
    if major == 20:
        return (minor, patch) >= (19, 0)
    if major == 22:
        return (minor, patch) >= (12, 0)
    return major > 22



def _dashboard_build_prerequisite_error() -> str:
    retry = "reopen Signal Desk.bat on Windows or ./signal-desk on macOS/Linux"
    if not shutil.which("npm"):
        return f"npm was not found. Install Node.js 20.19+ or 22.12+ with npm, then {retry}."
    if not shutil.which("node"):
        return f"node was not found. Install Node.js 20.19+ or 22.12+ with npm, then {retry}."
    try:
        completed = subprocess.run(["node", "--version"], check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return f"Node.js version could not be checked. Install Node.js 20.19+ or 22.12+, then {retry}."
    stdout = completed.stdout or ""
    version = _parse_node_version(stdout)
    if version is None or not _node_version_satisfies_dashboard_contract(version):
        found = stdout.strip() or "unknown"
        return (
            f"Node.js {found} does not satisfy the dashboard build requirement. "
            f"Install Node.js 20.19+ or 22.12+, then {retry}."
        )
    return ""



def run_demo(args: argparse.Namespace) -> int:
    output = _root_path(args.output or "output/demo-report.html")
    output.parent.mkdir(parents=True, exist_ok=True)
    code = _run(
        [
            _python(),
            _script("report.py"),
            "--input",
            _asset_path("templates/demo/fixtures/demo-scan.jsonl"),
            "--profile",
            _asset_path("templates/demo/fixtures/demo-profile.md"),
            "--html-only",
            _asset_path("templates/demo/fixtures/demo-report.md"),
            "--output",
            output,
        ]
    )
    if code == 0:
        html_output = output.with_suffix(".html")
        print(f"Demo report ready: {html_output}")
        print("Next: open the HTML report, then run tgcs init when you are ready to scan real Telegram sources.")
    return code



def run_login(args: argparse.Namespace) -> int:
    cmd: list[str | Path] = [_python(), _script("scan.py"), "--login-only"]
    if args.format == "json":
        cmd.extend(["--format", "json"])
    return _run(cmd)



def run_doctor(args: argparse.Namespace) -> int:
    config = _read_config()
    cmd: list[str | Path] = [
        _python(),
        _script("doctor.py"),
        *_doctor_source_args(args, config),
        "--profile",
        _profile_path(args.profile, config),
        "--output-dir",
        _root_path(args.output_dir or _default_output_dir(config)),
    ]
    if args.online_telegram:
        cmd.append("--online-telegram")
    if args.format == "json":
        cmd.extend(["--format", "json"])
    return _run(cmd)



def run_daily(args: argparse.Namespace) -> int:
    config = _read_config()
    cmd: list[str | Path] = [
        _python(),
        _script("daily_report.py"),
        *_source_args(args, config),
        "--profile",
        _profile_path(args.profile, config),
        "--hours",
        str(args.hours),
        "--output-dir",
        _root_path(args.output_dir or _default_output_dir(config)),
    ]
    if not args.no_html:
        cmd.append("--html")
    if not args.no_state:
        cmd.extend(["--state-dir", str(_root_path(args.state_dir or _default_state_dir(config)))])
    if args.state_read_only:
        cmd.append("--state-read-only")
    for feedback_path in args.feedback_jsonl:
        cmd.extend(["--feedback-jsonl", str(_root_path(feedback_path))])
    if args.items_json:
        cmd.extend(["--items-json", args.items_json])
    if args.extractor:
        cmd.extend(["--extractor", args.extractor])
    if args.allow_incomplete:
        cmd.append("--allow-incomplete")
    if args.format == "json":
        cmd.extend(["--format", "json"])
    return _run(cmd)



def run_sources(args: argparse.Namespace) -> int:
    registry = _root_path(args.source_registry or f"{LOCAL_DIR}/sources.json")
    cmd: list[str | Path] = [_python(), _script("source_registry.py")]
    if args.sources_command == "import":
        cmd.extend(["import-list", _root_path(args.channel_list), "--source-registry", registry])
        if args.dry_run:
            cmd.append("--dry-run")
        for topic in args.topic or []:
            cmd.extend(["--topic", topic])
    elif args.sources_command == "list":
        cmd.extend(["list", "--source-registry", registry])
        for topic in args.topic or []:
            cmd.extend(["--topic", topic])
    elif args.sources_command == "validate":
        cmd.extend(["validate", "--source-registry", registry])
    elif args.sources_command == "export":
        cmd.extend(["export-list", "--source-registry", registry, "--output", _root_path(args.output)])
        for topic in args.topic or []:
            cmd.extend(["--topic", topic])
    else:
        raise AssertionError(f"Unsupported sources command: {args.sources_command}")
    if args.format == "json":
        cmd.extend(["--format", "json"])
    return _run(cmd)



def run_monitor(args: argparse.Namespace) -> int:
    cmd: list[str | Path] = [_python(), _script("monitor.py")]
    if args.monitor_command == "run":
        cmd.extend(
            [
                "run",
                "--profile-id",
                args.profile_id,
                "--config",
                _root_path(args.config or f"{LOCAL_DIR}/{PROFILES_CONFIG_NAME}"),
                "--delivery-mode",
                args.delivery_mode,
            ]
        )
        if args.hours is not None:
            cmd.extend(["--hours", str(args.hours)])
        if args.scan_input:
            cmd.extend(["--scan-input", _root_path(args.scan_input)])
        if args.items_json:
            cmd.extend(["--items-json", args.items_json])
        if args.output_dir:
            cmd.extend(["--output-dir", _root_path(args.output_dir)])
        if args.db:
            cmd.extend(["--db", _root_path(args.db)])
        if args.format == "json":
            cmd.extend(["--format", "json"])
    elif args.monitor_command == "init-config":
        cmd.extend(["init-config", "--config", _root_path(args.config or f"{LOCAL_DIR}/{PROFILES_CONFIG_NAME}")])
        if args.force:
            cmd.append("--force")
        if args.format == "json":
            cmd.extend(["--format", "json"])
    else:
        raise AssertionError(f"Unsupported monitor command: {args.monitor_command}")
    return _run(cmd)



def run_dashboard(args: argparse.Namespace) -> int:
    static_dir = _root_path(args.static_dir or "dashboard/dist")
    if not args.no_build and not static_dir.exists() and not args.static_dir:
        prereq_error = _dashboard_build_prerequisite_error()
        if prereq_error:
            print(f"Error: {prereq_error}", file=sys.stderr)
            print("Next: install Node.js, or run with a checkout that already includes dashboard/dist.", file=sys.stderr)
            return 3
        dashboard_dir = PROJECT_ROOT / "dashboard"
        code = _run(["npm", "ci"], cwd=dashboard_dir)
        if code != 0:
            return code
        code = _run(["npm", "run", "build"], cwd=dashboard_dir)
        if code != 0:
            return code
    cmd: list[str | Path] = [
        _python(),
        _script("dashboard_server.py"),
        "--host",
        args.host,
        "--port",
        str(args.port or 8765),
        "--db",
        _root_path(args.db or f"{LOCAL_DIR}/tgcs.db"),
    ]
    if args.port is None:
        cmd.append("--auto-port")
    if args.static_dir:
        cmd.extend(["--static-dir", _root_path(args.static_dir)])
    if args.open:
        cmd.append("--open")
    return _run(cmd)



def run_feedback(args: argparse.Namespace) -> int:
    if args.feedback_command != "export":
        raise AssertionError(f"Unsupported feedback command: {args.feedback_command}")
    cmd: list[str | Path] = [
        _python(),
        _script("monitor.py"),
        "feedback-export",
        "--db",
        _root_path(args.db or f"{LOCAL_DIR}/tgcs.db"),
        "--output",
        _root_path(args.output or DEFAULT_FEEDBACK_EXPORT_PATH),
    ]
    if args.format == "json":
        cmd.extend(["--format", "json"])
    return _run(cmd)



def run_delivery(args: argparse.Namespace) -> int:
    if args.delivery_command != "test" or args.adapter != "telegram-bot":
        raise AssertionError("Unsupported delivery command")
    cmd: list[str | Path] = [
        _python(),
        _script("monitor.py"),
        "delivery-test",
        "telegram-bot",
        "--delivery-mode",
        args.delivery_mode,
    ]
    if args.chat_id:
        cmd.extend(["--chat-id", args.chat_id])
    if args.format == "json":
        cmd.extend(["--format", "json"])
    return _run(cmd)



def run_bot(args: argparse.Namespace) -> int:
    cmd: list[str | Path] = [_python(), _script("bot_gateway.py"), args.bot_command]
    if args.bot_command == "run":
        if args.db:
            cmd.extend(["--db", _root_path(args.db)])
        if args.state:
            cmd.extend(["--state", _root_path(args.state)])
        for chat_id in args.allow_chat_id or []:
            cmd.extend(["--allow-chat-id", chat_id])
        if args.poll_timeout:
            cmd.extend(["--poll-timeout", str(args.poll_timeout)])
        if args.install_menu:
            cmd.append("--install-menu")
        if args.skip_menu:
            cmd.append("--skip-menu")
        if args.llm:
            cmd.append("--llm")
        if args.no_llm:
            cmd.append("--no-llm")
    return _run(cmd)
