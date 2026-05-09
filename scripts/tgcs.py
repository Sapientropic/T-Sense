"""Human-oriented TG Channel Scanner CLI facade.

The lower-level scripts keep their explicit agent contract.  This facade is
for people who run the same local workflow repeatedly: it chooses stable local
defaults, keeps v0.4 state on by default, and delegates to the existing scripts
without changing their machine-readable interfaces.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DIR = ".tgcs"
CONFIG_NAME = "config.toml"
PROFILES_CONFIG_NAME = "profiles.toml"
DEFAULT_PROFILE = "market-news"
DEFAULT_TGCLI_CONFIG_PATH = Path.home() / ".config" / "tgcli" / "config.toml"
DEFAULT_SESSION_PATH = Path.home() / ".config" / "tgcli" / "session"
PROFILE_ALIASES = {
    "jobs": "profiles/templates/jobs.md",
    "airdrops": "profiles/templates/airdrops.md",
    "market-news": "profiles/templates/market-news.md",
    "research-leads": "profiles/templates/research-leads.md",
    "competitor-monitoring": "profiles/templates/competitor-monitoring.md",
}
INIT_STARTERS = {
    "default": {
        "profile": "market-news",
        "channel_list": "channel_lists/example.txt",
        "topics": [],
    },
    "jobs": {
        "profile": "jobs",
        "channel_list": "channel_lists/jobs.txt",
        "topics": ["jobs"],
    },
}


def _python() -> str:
    return sys.executable


def _root_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _script(name: str) -> Path:
    return PROJECT_ROOT / "scripts" / name


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
        return _root_path(PROFILE_ALIASES[profile])
    if profile.endswith(".md") or "/" in profile or "\\" in profile:
        return _root_path(profile)
    return _root_path(f"profiles/templates/{profile}.md")


def _default_source_registry(config: dict[str, Any]) -> Path:
    return _configured_path(config, "source_registry", f"{LOCAL_DIR}/sources.json")


def _default_channel_list(config: dict[str, Any]) -> Path:
    return _configured_path(config, "channel_list", "channel_lists/example.txt")


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


def _quickstart_check(check_id: str, label: str, status: str, detail: str, command: str = "") -> dict[str, str]:
    payload = {
        "check_id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
    }
    if command:
        payload["command"] = command
    return payload


def _jobs_sources_ready(registry_path: Path) -> bool:
    if not registry_path.exists():
        return False
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        return False
    for source in sources:
        if not isinstance(source, dict) or source.get("enabled") is False:
            continue
        topics = source.get("topics")
        if isinstance(topics, list) and any(str(topic).casefold() == "jobs" for topic in topics):
            return True
    return False


def _telegram_credentials_ready(config_path: Path | None = None) -> bool:
    config_path = config_path or DEFAULT_TGCLI_CONFIG_PATH
    env_id = os.environ.get("TELEGRAM_API_ID")
    env_hash = os.environ.get("TELEGRAM_API_HASH")
    if env_id and env_hash:
        try:
            int(env_id)
            return True
        except ValueError:
            return False
    if not config_path.exists():
        return False
    try:
        with config_path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    api_id = payload.get("api_id") if isinstance(payload, dict) else None
    api_hash = str(payload.get("api_hash") or "") if isinstance(payload, dict) else ""
    return bool(api_id and api_hash and api_hash != "your_api_hash_here")


def _telegram_session_ready(session_path: Path | None = None) -> bool:
    session_path = session_path or DEFAULT_SESSION_PATH
    try:
        return bool(session_path.exists() and session_path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _monitor_has_runs(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False
    return bool(row and int(row[0] or 0) > 0)


def quickstart_jobs_status() -> dict[str, Any]:
    config_path = _local_path(CONFIG_NAME)
    profiles_config_path = _local_path(PROFILES_CONFIG_NAME)
    registry_path = _local_path("sources.json")
    db_path = _local_path("tgcs.db")
    local_defaults = config_path.exists() and profiles_config_path.exists()
    jobs_sources = _jobs_sources_ready(registry_path)
    credentials = _telegram_credentials_ready()
    session = _telegram_session_ready()
    has_runs = _monitor_has_runs(db_path)

    if not local_defaults:
        stage = "init_required"
        next_command = "tgcs init --starter jobs"
        why = "Local .tgcs defaults are missing."
    elif not jobs_sources:
        stage = "source_import_required"
        next_command = "tgcs init --starter jobs"
        why = "The local source registry does not yet have enabled jobs-topic sources."
    elif not credentials:
        stage = "doctor_required"
        next_command = "tgcs doctor --profile jobs"
        why = "Telegram API credentials are not visible to the local scanner."
    elif not session:
        stage = "login_required"
        next_command = "tgcs login"
        why = "Telegram credentials exist, but the local session file is missing."
    elif not has_runs:
        stage = "dry_run_required"
        next_command = "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run"
        why = "Jobs sources and Telegram login are ready; run one safe dry-run before live alerts."
    else:
        stage = "dashboard_ready"
        next_command = "tgcs dashboard"
        why = "A previous monitor run exists; open the review inbox."

    def status_for(check_id: str) -> str:
        order = [
            ("local_defaults", local_defaults),
            ("jobs_sources", jobs_sources),
            ("telegram_credentials", credentials),
            ("telegram_login", session),
            ("first_dry_run", has_runs),
        ]
        for current_id, is_done in order:
            if current_id == check_id:
                return "done" if is_done else "next"
            if not is_done:
                return "todo"
        return "next" if check_id == "dashboard" else "done"

    checks = [
        _quickstart_check(
            "local_defaults",
            "Local defaults",
            status_for("local_defaults"),
            "Create .tgcs config, profiles, and local source registry defaults.",
            "tgcs init --starter jobs",
        ),
        _quickstart_check(
            "jobs_sources",
            "Jobs sources",
            status_for("jobs_sources"),
            "Merge channel_lists/jobs.txt into .tgcs/sources.json with the jobs topic.",
            "tgcs init --starter jobs",
        ),
        _quickstart_check(
            "telegram_credentials",
            "Telegram credentials",
            status_for("telegram_credentials"),
            "Verify TELEGRAM_API_ID / TELEGRAM_API_HASH or ~/.config/tgcli/config.toml.",
            "tgcs doctor --profile jobs",
        ),
        _quickstart_check(
            "telegram_login",
            "Telegram login",
            status_for("telegram_login"),
            "Create the local MTProto session without scanning channels.",
            "tgcs login",
        ),
        _quickstart_check(
            "first_dry_run",
            "First dry-run",
            status_for("first_dry_run"),
            "Run jobs-fast once in dry-run delivery mode before enabling live alerts.",
            "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
        ),
        _quickstart_check(
            "dashboard",
            "Review inbox",
            status_for("dashboard"),
            "Open the local dashboard after at least one monitor run exists.",
            "tgcs dashboard",
        ),
    ]
    return {
        "schema_version": "tgcs_quickstart_v1",
        "vertical": "jobs",
        "label": "Developer Opportunity quickstart",
        "stage": stage,
        "next_command": next_command,
        "why": why,
        "checks": checks,
    }


def run_quickstart(args: argparse.Namespace) -> int:
    if args.vertical != "jobs":
        raise AssertionError(f"Unsupported quickstart vertical: {args.vertical}")
    payload = quickstart_jobs_status()
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(payload["label"])
    print(f"Stage: {payload['stage']}")
    print(f"Next: {payload['next_command']}")
    print(f"Why: {payload['why']}")
    print("Checklist:")
    for check in payload["checks"]:
        print(f"- {check['label']}: {check['status']}")
    return 0


def _print_init_next_steps(starter: str = "default") -> None:
    print("Local project defaults ready.")
    print("- Profiles: market-news, jobs-fast")
    print("- Next: tgcs doctor")
    if starter == "jobs":
        print("- Check jobs setup: tgcs doctor --profile jobs")
        print("- Run jobs monitor: tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run")
    print("- Import real jobs sources: tgcs sources import channel_lists/jobs.txt --topic jobs")
    print("- Login: tgcs login")
    print("- Run report: tgcs run")
    print("- Print scheduler command: tgcs schedule print --profile-id jobs-fast --interval-minutes 15")
    print("- Open inbox: tgcs dashboard")


def _write_default_config(
    path: Path,
    *,
    force: bool = False,
    profile: str = "market-news",
    channel_list: str = "channel_lists/example.txt",
) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'channel_list = "{channel_list}"',
                'source_registry = ".tgcs/sources.json"',
                'output_dir = "output"',
                'state_dir = ".tgcs/state"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_default_profiles_config(path: Path, *, force: bool = False) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                'schema_version = "profile_run_config_v1"',
                "",
                "[defaults]",
                'output_dir = "output"',
                'state_dir = ".tgcs/state"',
                'database = ".tgcs/tgcs.db"',
                'dashboard_url = "http://127.0.0.1:8765"',
                "",
                "[[profiles]]",
                'id = "market-news"',
                'path = "profiles/templates/market-news.md"',
                "enabled = true",
                'timezone = "Asia/Shanghai"',
                "work_interval_minutes = 120",
                "off_hours_interval_minutes = 360",
                "scan_window_hours = 24",
                'source_registry = ".tgcs/sources.json"',
                'channel_list = "channel_lists/example.txt"',
                'source_topics = ["market-news"]',
                'alert_rule = "high_new_or_changed"',
                'alert_schedule_mode = "work_hours"',
                'delivery_targets = ["telegram-bot-default"]',
                "dashboard_visible = true",
                "",
                "[[profiles]]",
                'id = "jobs-fast"',
                'path = "profiles/templates/jobs.md"',
                "enabled = true",
                'timezone = "Asia/Shanghai"',
                'work_start = "09:00"',
                'work_end = "23:00"',
                "work_interval_minutes = 15",
                "off_hours_interval_minutes = 60",
                "scan_window_hours = 2",
                'source_registry = ".tgcs/sources.json"',
                'channel_list = "channel_lists/example.txt"',
                'source_topics = ["jobs"]',
                'alert_rule = "high_new_or_changed"',
                "alert_max_age_minutes = 60",
                'alert_schedule_mode = "work_hours"',
                'delivery_targets = ["telegram-bot-default"]',
                "dashboard_visible = true",
                "prefilter_enabled = true",
                "semantic_max_messages = 20",
                "semantic_max_tokens = 2000",
                "prefilter_keywords = [\"hiring\", \"we're hiring\", \"is hiring\", \"job opening\", \"open role\", \"remote\", \"apply\", \"frontend\", \"backend\", \"fullstack\", \"react\", \"typescript\", \"engineer\", \"developer\", \"招聘\", \"招人\", \"岗位\", \"职位\", \"远程\", \"简历\"]",
                "",
                "[[delivery]]",
                'id = "telegram-bot-default"',
                'type = "telegram_bot"',
                "enabled = false",
                'chat_id = ""',
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_demo(args: argparse.Namespace) -> int:
    output = _root_path(args.output or "output/demo-report.html")
    output.parent.mkdir(parents=True, exist_ok=True)
    code = _run(
        [
            _python(),
            _script("report.py"),
            "--input",
            PROJECT_ROOT / "docs/demo/fixtures/demo-scan.jsonl",
            "--profile",
            PROJECT_ROOT / "docs/demo/fixtures/demo-profile.md",
            "--html-only",
            PROJECT_ROOT / "docs/demo/fixtures/demo-report.md",
            "--output",
            output,
        ]
    )
    if code == 0:
        html_output = output.with_suffix(".html")
        print(f"Demo report ready: {html_output}")
        print("Next: open the HTML report, then run tgcs init when you are ready to scan real Telegram sources.")
    return code


def run_init(args: argparse.Namespace) -> int:
    starter = INIT_STARTERS[args.starter]
    config_path = _local_path(CONFIG_NAME)
    profiles_config_path = _local_path(PROFILES_CONFIG_NAME)
    _local_path().mkdir(parents=True, exist_ok=True)
    _default_output_dir({}).mkdir(parents=True, exist_ok=True)
    _default_state_dir({}).mkdir(parents=True, exist_ok=True)
    _write_default_config(
        config_path,
        force=args.force,
        profile=str(starter["profile"]),
        channel_list=str(starter["channel_list"]),
    )
    _write_default_profiles_config(profiles_config_path, force=args.force)

    registry = _root_path(args.source_registry or f"{LOCAL_DIR}/sources.json")
    channel_list = _root_path(args.channel_list or str(starter["channel_list"]))
    topics = list(args.topic or starter["topics"])
    if registry.exists() and not args.force:
        if args.starter == "jobs":
            print(f"Local config ready: {config_path}")
            if not channel_list.exists():
                print(f"Source registry already exists: {registry}")
                print(f"Channel list not found, skipped source import: {channel_list}", file=sys.stderr)
                _print_init_next_steps(args.starter)
                return 0
            print(f"Source registry already exists, merging starter sources: {registry}")
        else:
            print(f"Local config ready: {config_path}")
            print(f"Source registry already exists: {registry}")
            _print_init_next_steps(args.starter)
            return 0
    if not channel_list.exists():
        print(f"Local config ready: {config_path}")
        print(f"Channel list not found, skipped source import: {channel_list}", file=sys.stderr)
        _print_init_next_steps(args.starter)
        return 0
    cmd: list[str | Path] = [
        _python(),
        _script("source_registry.py"),
        "import-list",
        channel_list,
        "--source-registry",
        registry,
    ]
    for topic in topics:
        cmd.extend(["--topic", str(topic)])
    code = _run(cmd)
    if code == 0:
        _print_init_next_steps(args.starter)
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
        str(args.port),
        "--db",
        _root_path(args.db or f"{LOCAL_DIR}/tgcs.db"),
    ]
    if args.static_dir:
        cmd.extend(["--static-dir", _root_path(args.static_dir)])
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
        _root_path(args.output or "output/dashboard-feedback.jsonl"),
    ]
    if args.format == "json":
        cmd.extend(["--format", "json"])
    return _run(cmd)


def _windows_preview_quote(value: str | Path) -> str:
    text = str(value)
    return f'"{text}"'


def _windows_task_quote(value: str | Path) -> str:
    return f'\\"{value}\\"'


def _cron_prefix(interval_minutes: int) -> str:
    if interval_minutes < 60:
        return f"*/{interval_minutes} * * * *"
    if interval_minutes % 60 == 0:
        return f"0 */{interval_minutes // 60} * * *"
    raise SystemExit("cron intervals above 59 minutes must be whole hours")


def run_schedule(args: argparse.Namespace) -> int:
    if args.schedule_command != "print":
        raise AssertionError(f"Unsupported schedule command: {args.schedule_command}")
    if args.interval_minutes < 1:
        raise SystemExit("--interval-minutes must be at least 1")

    profile_id = args.profile_id
    delivery_mode = args.delivery_mode
    platform = args.platform or ("windows" if sys.platform.startswith("win") else "cron")

    if platform == "windows":
        task_name = args.task_name or f"TGCS {profile_id}"
        tgcs_path = PROJECT_ROOT / "tgcs.bat"
        task_command = (
            f"{_windows_task_quote(tgcs_path)} monitor run --profile-id {profile_id} "
            f"--delivery-mode {delivery_mode}"
        )
        preview_command = (
            f"{_windows_preview_quote(tgcs_path)} monitor run --profile-id {profile_id} "
            f"--delivery-mode {delivery_mode}"
        )
        print("Task Scheduler command:")
        print(
            f'schtasks /Create /TN "{task_name}" /SC MINUTE /MO {args.interval_minutes} '
            f'/TR "{task_command}" /F'
        )
        print("Preview command:")
        print(preview_command)
        return 0

    cron_prefix = _cron_prefix(args.interval_minutes)
    log_path = f"output/tgcs-{profile_id}.log"
    print("Crontab line:")
    print(
        f'{cron_prefix} cd "{PROJECT_ROOT}" && ./tgcs monitor run --profile-id {profile_id} '
        f"--delivery-mode {delivery_mode} >> {log_path} 2>&1"
    )
    return 0


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tgcs",
        description="Human-friendly TG Channel Scanner command facade.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Render the offline demo report.")
    demo.add_argument("--output", help="HTML output path. Defaults to output/demo-report.html.")
    demo.set_defaults(func=run_demo)

    init = subparsers.add_parser("init", help="Create .tgcs defaults and import the example sources.")
    init.add_argument("--starter", choices=tuple(INIT_STARTERS), default="default", help="Choose first-run defaults.")
    init.add_argument("--channel-list", help="Channel list to import into .tgcs/sources.json.")
    init.add_argument("--source-registry", help="Source registry path. Defaults to .tgcs/sources.json.")
    init.add_argument("--topic", action="append", default=[], help="Attach a topic tag to imported sources.")
    init.add_argument("--force", action="store_true", help="Overwrite local config and source registry.")
    init.set_defaults(func=run_init)

    quickstart = subparsers.add_parser("quickstart", help="Show the single next action for a starter workflow.")
    quickstart.add_argument("vertical", choices=("jobs",), help="Starter workflow to inspect.")
    quickstart.add_argument("--format", choices=("human", "json"), default="human")
    quickstart.set_defaults(func=run_quickstart)

    login = subparsers.add_parser("login", help="Complete Telegram login without scanning.")
    login.add_argument("--format", choices=("human", "json"), default="human")
    login.set_defaults(func=run_login)

    doctor = subparsers.add_parser("doctor", help="Run first-run checks with local defaults.")
    doctor.add_argument("--profile", help="Profile alias or path. Defaults to market-news.")
    doctor.add_argument("--source-registry", help="Source registry path.")
    doctor.add_argument("--channel-list", help="Channel list path used when no registry exists.")
    doctor.add_argument("--output-dir", help="Output directory. Defaults to output.")
    doctor.add_argument("--online-telegram", action="store_true")
    doctor.add_argument("--format", choices=("human", "json"), default="human")
    doctor.set_defaults(func=run_doctor)

    run = subparsers.add_parser("run", help="Scan sources and generate today's report.")
    run.add_argument("--profile", help="Profile alias or path. Defaults to market-news.")
    run.add_argument("--hours", type=int, default=24)
    run.add_argument("--source-registry", help="Source registry path.")
    run.add_argument("--channel-list", help="Channel list path used when no registry exists.")
    run.add_argument("--output-dir", help="Output directory. Defaults to output.")
    run.add_argument("--no-html", action="store_true", help="Skip HTML output.")
    run.add_argument("--no-state", action="store_true", help="Disable v0.4 local decision memory.")
    run.add_argument("--state-dir", help="State directory. Defaults to .tgcs/state.")
    run.add_argument("--state-read-only", action="store_true")
    run.add_argument("--feedback-jsonl", action="append", default=[])
    run.add_argument("--items-json")
    run.add_argument("--extractor", choices=("auto", "llm", "agent"))
    run.add_argument("--allow-incomplete", action="store_true")
    run.add_argument("--format", choices=("human", "json"), default="human")
    run.set_defaults(func=run_daily)

    sources = subparsers.add_parser("sources", help="Maintain the local source registry.")
    source_subparsers = sources.add_subparsers(dest="sources_command", required=True)
    source_import = source_subparsers.add_parser("import", help="Import a channel list.")
    source_import.add_argument("channel_list")
    source_import.add_argument("--source-registry")
    source_import.add_argument("--dry-run", action="store_true")
    source_import.add_argument("--topic", action="append", default=[], help="Attach a topic tag to imported sources.")
    source_import.add_argument("--format", choices=("human", "json"), default="human")
    source_import.set_defaults(func=run_sources)
    source_list = source_subparsers.add_parser("list", help="List sources.")
    source_list.add_argument("--source-registry")
    source_list.add_argument("--topic", action="append", default=[], help="Filter sources by topic tag.")
    source_list.add_argument("--format", choices=("human", "json"), default="human")
    source_list.set_defaults(func=run_sources)
    source_validate = source_subparsers.add_parser("validate", help="Validate sources.")
    source_validate.add_argument("--source-registry")
    source_validate.add_argument("--format", choices=("human", "json"), default="human")
    source_validate.set_defaults(func=run_sources)
    source_export = source_subparsers.add_parser("export", help="Export sources as a channel list.")
    source_export.add_argument("--output", required=True)
    source_export.add_argument("--source-registry")
    source_export.add_argument("--topic", action="append", default=[], help="Filter exported sources by topic tag.")
    source_export.add_argument("--format", choices=("human", "json"), default="human")
    source_export.set_defaults(func=run_sources)

    monitor = subparsers.add_parser("monitor", help="Run v0.5-alpha profile monitors.")
    monitor_subparsers = monitor.add_subparsers(dest="monitor_command", required=True)
    monitor_init = monitor_subparsers.add_parser("init-config", help="Write .tgcs/profiles.toml.")
    monitor_init.add_argument("--config")
    monitor_init.add_argument("--force", action="store_true")
    monitor_init.add_argument("--format", choices=("human", "json"), default="human")
    monitor_init.set_defaults(func=run_monitor)
    monitor_run = monitor_subparsers.add_parser("run", help="Run one configured profile monitor.")
    monitor_run.add_argument("--profile-id", default=DEFAULT_PROFILE)
    monitor_run.add_argument("--config")
    monitor_run.add_argument("--hours", type=int)
    monitor_run.add_argument("--scan-input")
    monitor_run.add_argument("--items-json")
    monitor_run.add_argument("--output-dir")
    monitor_run.add_argument("--db")
    monitor_run.add_argument("--delivery-mode", choices=("off", "dry-run", "live"), default="dry-run")
    monitor_run.add_argument("--format", choices=("human", "json"), default="human")
    monitor_run.set_defaults(func=run_monitor)

    dashboard = subparsers.add_parser("dashboard", help="Serve the local review dashboard.")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.add_argument("--db")
    dashboard.add_argument("--static-dir")
    dashboard.add_argument("--no-build", action="store_true", help="Do not auto-build dashboard/dist before serving.")
    dashboard.set_defaults(func=run_dashboard)

    feedback = subparsers.add_parser("feedback", help="Export reusable feedback from the local dashboard.")
    feedback_subparsers = feedback.add_subparsers(dest="feedback_command", required=True)
    feedback_export = feedback_subparsers.add_parser("export", help="Export dashboard feedback as JSONL.")
    feedback_export.add_argument("--db")
    feedback_export.add_argument("--output")
    feedback_export.add_argument("--format", choices=("human", "json"), default="human")
    feedback_export.set_defaults(func=run_feedback)

    schedule = subparsers.add_parser("schedule", help="Print local scheduler commands without installing them.")
    schedule_subparsers = schedule.add_subparsers(dest="schedule_command", required=True)
    schedule_print = schedule_subparsers.add_parser("print", help="Print a Task Scheduler or cron command.")
    schedule_print.add_argument("--platform", choices=("windows", "cron"))
    schedule_print.add_argument("--profile-id", default=DEFAULT_PROFILE)
    schedule_print.add_argument("--interval-minutes", type=int, default=15)
    schedule_print.add_argument("--delivery-mode", choices=("off", "dry-run", "live"), default="dry-run")
    schedule_print.add_argument("--task-name")
    schedule_print.set_defaults(func=run_schedule)

    delivery_parser = subparsers.add_parser("delivery", help="Manage delivery adapters.")
    delivery_subparsers = delivery_parser.add_subparsers(dest="delivery_command", required=True)
    delivery_test = delivery_subparsers.add_parser("test", help="Test one delivery adapter.")
    delivery_test.add_argument("adapter", choices=("telegram-bot",))
    delivery_test.add_argument("--chat-id")
    delivery_test.add_argument("--delivery-mode", choices=("dry-run", "live"), default="dry-run")
    delivery_test.add_argument("--format", choices=("human", "json"), default="human")
    delivery_test.set_defaults(func=run_delivery)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
