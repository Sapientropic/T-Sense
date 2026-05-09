"""First-run environment diagnostics for TG Channel Scanner."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

try:
    from scripts import agent_cli, report, source_registry
    from scripts.profile_schema import parse_profile_config
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import agent_cli, report, source_registry
    from scripts.profile_schema import parse_profile_config


DEFAULT_CONFIG_DIR = Path(
    os.environ.get("TG_SCANNER_CONFIG_DIR")
    or os.environ.get("TGCLI_CONFIG_DIR")
    or Path.home() / ".config" / "tgcli"
)
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_SESSION_PATH = DEFAULT_CONFIG_DIR / "session"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    next_step: str = ""
    details: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        payload = {
            "status": self.status,
            "message": self.message,
        }
        if self.next_step:
            payload["next_step"] = self.next_step
        if self.details:
            payload["details"] = self.details
        return payload


def _pass(name: str, message: str, *, details: dict | None = None) -> CheckResult:
    return CheckResult(name, "pass", message, details=details or {})


def _warn(name: str, message: str, next_step: str = "", *, details: dict | None = None) -> CheckResult:
    return CheckResult(name, "warn", message, next_step, details or {})


def _fail(name: str, message: str, next_step: str = "", *, details: dict | None = None) -> CheckResult:
    return CheckResult(name, "fail", message, next_step, details or {})


def _read_channel_list(path: Path) -> list[str]:
    channels = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            channels.append(line)
    return channels


def _is_invite_link_reference(value: str) -> bool:
    lowered = value.strip().casefold()
    return (
        "t.me/+" in lowered
        or "telegram.me/+" in lowered
        or "t.me/joinchat/" in lowered
        or "telegram.me/joinchat/" in lowered
    )


def _channel_list_review(channels: list[str]) -> dict:
    seen: set[str] = set()
    duplicate_refs: list[str] = []
    invite_refs: list[str] = []
    for channel in channels:
        if _is_invite_link_reference(channel):
            invite_refs.append(channel)
        normalized = source_registry.normalize_channel_name(channel).casefold()
        if normalized in seen:
            duplicate_refs.append(channel)
        else:
            seen.add(normalized)
    return {
        "duplicate_refs": duplicate_refs,
        "invite_refs": invite_refs,
    }


def _placeholder_source_count(sources: list[dict]) -> int:
    count = 0
    for source in sources:
        username = str(source.get("username") or "").strip().casefold()
        label = str(source.get("label") or "").strip().casefold()
        if username.startswith("example_") or label.startswith("example_"):
            count += 1
    return count


def _placeholder_import_next_step(sources: list[dict]) -> str:
    labels = " ".join(
        str(source.get("username") or source.get("label") or "").casefold()
        for source in sources
        if isinstance(source, dict)
    )
    topic = "jobs" if any(token in labels for token in ("job", "career", "hiring", "remote")) else ""
    list_name = "jobs.txt" if topic == "jobs" else "channels.txt"
    command = f"tgcs sources import channel_lists/{list_name}"
    if topic:
        command = f"{command} --topic {topic}"
    if topic == "jobs":
        return (
            "Run `tgcs init --starter jobs --force` to replace placeholder sources, "
            f"or import real Telegram channels with `{command}`, then rerun tgcs doctor."
        )
    return f"Import real Telegram channels with `{command}`, then rerun tgcs doctor."


def check_python_runtime() -> CheckResult:
    version = sys.version_info
    if version < (3, 12):
        return _fail(
            "python_runtime",
            f"Python {version.major}.{version.minor} is too old.",
            "Install Python 3.12+ or use uv to provision a supported interpreter.",
        )
    return _pass(
        "python_runtime",
        f"Python {version.major}.{version.minor}.{version.micro} is supported.",
    )


def check_import(name: str, module: str, required: bool, install_hint: str) -> CheckResult:
    if importlib.util.find_spec(module):
        return _pass(name, f"{module} is importable.")
    if required:
        return _fail(name, f"{module} is not importable.", install_hint)
    return _warn(name, f"{module} is not importable.", install_hint)


def _config_credentials(config_path: Path) -> tuple[int | None, str | None, str]:
    api_id = None
    api_hash = None
    source = ""
    if config_path.exists():
        with config_path.open("rb") as handle:
            cfg = tomllib.load(handle)
        api_id = cfg.get("api_id")
        api_hash = cfg.get("api_hash")
        source = "config"

    env_id = os.environ.get("TELEGRAM_API_ID")
    env_hash = os.environ.get("TELEGRAM_API_HASH")
    if env_id:
        try:
            api_id = int(env_id)
        except ValueError:
            api_id = None
        source = "environment"
    if env_hash:
        api_hash = env_hash
        source = "environment"
    return api_id, api_hash, source


def check_credentials(config_path: Path) -> CheckResult:
    try:
        api_id, api_hash, source = _config_credentials(config_path)
    except Exception as exc:
        return _fail(
            "telegram_credentials",
            f"Could not read Telegram config: {exc}",
            "Fix config.toml or use TELEGRAM_API_ID / TELEGRAM_API_HASH.",
        )
    if not api_id or not api_hash or api_hash == "your_api_hash_here":
        return _fail(
            "telegram_credentials",
            "Telegram API credentials were not found.",
            "Edit config.toml or set TELEGRAM_API_ID and TELEGRAM_API_HASH.",
            details={"config_path": str(config_path)},
        )
    return _pass(
        "telegram_credentials",
        f"Telegram API credentials found via {source}.",
        details={"source": source, "config_path": str(config_path)},
    )


def check_session(session_path: Path) -> CheckResult:
    if session_path.exists() and session_path.read_text(encoding="utf-8").strip():
        return _pass(
            "telegram_session",
            "Telegram session file exists.",
            details={"session_path": str(session_path)},
        )
    return _warn(
        "telegram_session",
        "Telegram session file is missing; the first real scan will prompt for login.",
        "Run scripts/scan.py once after credentials are configured.",
        details={"session_path": str(session_path)},
    )


def check_channel_list(path: Path) -> CheckResult:
    if not path.exists():
        return _fail("channel_list", f"Channel list not found: {path}", "Create a .txt file with one Telegram username per line.")
    try:
        channels = _read_channel_list(path)
    except OSError as exc:
        return _fail("channel_list", f"Channel list cannot be read: {exc}", "Check file permissions.")
    if not channels:
        return _fail("channel_list", f"Channel list is empty: {path}", "Add at least one Telegram username or channel id.")
    review = _channel_list_review(channels)
    duplicate_count = len(review["duplicate_refs"])
    invite_count = len(review["invite_refs"])
    details = {
        "count": len(channels),
        "duplicate_count": duplicate_count,
        "unsupported_invite_count": invite_count,
    }
    if duplicate_count or invite_count:
        issue_parts = []
        if duplicate_count:
            issue_parts.append(f"{duplicate_count} duplicate")
        if invite_count:
            issue_parts.append(f"{invite_count} invite link")
        return _warn(
            "channel_list",
            f"Channel list has {len(channels)} sources, but {' and '.join(issue_parts)} needs review.",
            "Remove duplicates. For invite links, join the channel first and use a username, numeric channel id, or Telegram folder import.",
            details=details,
        )
    return _pass("channel_list", f"Channel list has {len(channels)} sources.", details=details)


def check_source_registry(path: Path) -> CheckResult:
    if not path.exists():
        return _fail(
            "source_registry",
            f"Source registry not found: {path}",
            "Import a channel list or create .tgcs/sources.json.",
        )
    try:
        payload = source_registry.load_registry(path)
        issues = source_registry.validate_registry(payload)
    except Exception as exc:
        return _fail(
            "source_registry",
            f"Source registry cannot be read: {exc}",
            "Run scripts/source_registry.py validate and fix the registry.",
        )
    if issues:
        return _fail(
            "source_registry",
            source_registry.validation_message(issues),
            "Run scripts/source_registry.py validate and fix the registry.",
            details={"issues": issues, "path": str(path)},
        )
    enabled_count = len(source_registry.enabled_sources(payload))
    sources = [source for source in payload.get("sources", []) if isinstance(source, dict)]
    placeholder_count = _placeholder_source_count(sources)
    details = {
        "path": str(path),
        "source_count": len(payload.get("sources", [])),
        "enabled_count": enabled_count,
        "placeholder_count": placeholder_count,
    }
    if enabled_count and placeholder_count == enabled_count:
        return _warn(
            "source_registry",
            f"Source registry has {enabled_count} enabled placeholder sources.",
            _placeholder_import_next_step(sources),
            details=details,
        )
    return _pass(
        "source_registry",
        f"Source registry has {enabled_count} enabled sources.",
        details=details,
    )


def check_source_input(channel_list: Path | None, registry_path: Path | None) -> CheckResult:
    if channel_list or registry_path:
        return _pass("source_input", "Source input is configured.")
    return _fail(
        "source_input",
        "No source input was provided.",
        "Pass --source-registry .tgcs/sources.json or --channel-list channel_lists/example.txt.",
    )


def check_profile(path: Path) -> CheckResult:
    if not path.exists():
        return _fail("profile", f"Profile not found: {path}", "Copy one of profiles/templates/*.md and customize it.")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return _fail("profile", f"Profile is empty: {path}", "Add profile rules or copy a built-in template.")
    try:
        config = parse_profile_config(text)
    except Exception as exc:
        return _fail("profile", f"Profile could not be parsed: {exc}", "Fix the Markdown profile sections.")
    if config.mode.mode != "job" and not config.mode.fields:
        return _fail(
            "profile",
            "Custom profile has no extraction fields.",
            "Add fields under ## Extraction Schema or use a built-in template.",
        )
    return _pass(
        "profile",
        f"Profile parses as {config.mode.mode} mode.",
        details={"mode": config.mode.mode, "output_filename": config.labels.output_filename},
    )


def check_llm_provider() -> CheckResult:
    providers = []
    if os.environ.get("OPENAI_API_KEY"):
        providers.append("openai")
    if os.environ.get("DEEPSEEK_API_KEY"):
        providers.append("deepseek")
    if os.environ.get("MINIMAX_TOKEN_PLAN_KEY") or os.environ.get("MINIMAX_API_KEY"):
        providers.append("minimax")
    if providers:
        details = {"providers": providers}
        if "minimax" in providers:
            details["minimax_key_type"] = "token_plan" if os.environ.get("MINIMAX_TOKEN_PLAN_KEY") else "platform"
            details["minimax_base_url"] = os.environ.get("MINIMAX_BASE_URL") or report.default_minimax_base_url()
        return _pass(
            "llm_provider",
            f"LLM API key is configured for {', '.join(providers)}.",
            details=details,
        )
    return _warn(
        "llm_provider",
        "No LLM API key found.",
        "Set OPENAI_API_KEY, DEEPSEEK_API_KEY, MINIMAX_TOKEN_PLAN_KEY, or MINIMAX_API_KEY before running report generation.",
    )


def check_output_directory(path: Path) -> CheckResult:
    if path.exists() and not path.is_dir():
        return _fail("output_directory", f"Output path is not a directory: {path}", "Choose a directory path for --output-dir.")
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".doctor-", dir=path, delete=True):
            pass
    except OSError as exc:
        return _fail("output_directory", f"Output directory is not writable: {exc}", "Fix permissions or choose another output directory.")
    return _pass("output_directory", f"Output directory is writable: {path}")


def check_media_dependencies() -> CheckResult:
    if shutil.which("ffmpeg"):
        return _pass("media_dependencies", "ffmpeg is available for full-video OCR/STT paths.")
    return _warn(
        "media_dependencies",
        "ffmpeg was not found; thumbnail-only OCR can still work.",
        "Install ffmpeg before using --ocr-full-video or full-video reprocessing.",
    )


def check_dashboard_assets() -> CheckResult:
    dashboard_dir = PROJECT_ROOT / "dashboard"
    static_dir = dashboard_dir / "dist"
    index_path = static_dir / "index.html"
    if index_path.exists():
        return _pass(
            "dashboard_assets",
            "Dashboard static assets are built.",
            details={"static_dir": str(static_dir)},
        )
    if not (dashboard_dir / "package.json").exists():
        return _warn(
            "dashboard_assets",
            "Dashboard source directory was not found.",
            "Clone the full repository if you want to use the optional local dashboard.",
            details={"static_dir": str(static_dir)},
        )
    if shutil.which("npm"):
        return _warn(
            "dashboard_assets",
            "Dashboard static assets are not built yet.",
            "Run tgcs dashboard; it will auto-build dashboard/dist with npm ci and npm run build.",
            details={"static_dir": str(static_dir), "auto_build": True},
        )
    return _warn(
        "dashboard_assets",
        "Dashboard static assets are not built and npm was not found.",
        "Install Node.js/npm before first dashboard launch, or build dashboard/dist on another machine.",
        details={"static_dir": str(static_dir), "auto_build": False},
    )


async def _online_telegram_check(config_path: Path, session_path: Path) -> CheckResult:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        return _fail("telegram_online", "Telethon is not installed.", "Install requirements.txt first.")

    api_id, api_hash, _ = _config_credentials(config_path)
    if not api_id or not api_hash:
        return _fail("telegram_online", "Telegram credentials are missing.", "Configure credentials before online checks.")

    session_string = ""
    if session_path.exists():
        session_string = session_path.read_text(encoding="utf-8").strip()
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    try:
        await client.connect()
        authorized = await client.is_user_authorized()
    except Exception as exc:
        return _warn("telegram_online", f"Telegram authorization check failed: {exc}", "Run a normal scan interactively after fixing credentials/session.")
    finally:
        await client.disconnect()
    if authorized:
        return _pass("telegram_online", "Telegram session is authorized.")
    return _warn(
        "telegram_online",
        "Telegram session exists but is not authorized, or no session was provided.",
        "Run a normal scan to complete interactive login; doctor never prompts for login.",
    )


def check_online_telegram(config_path: Path, session_path: Path) -> CheckResult:
    return asyncio.run(_online_telegram_check(config_path, session_path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check first-run TG Channel Scanner prerequisites.")
    parser.add_argument("--channel-list", type=Path)
    parser.add_argument("--source-registry", type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--session-path", type=Path, default=DEFAULT_SESSION_PATH)
    parser.add_argument("--online-telegram", action="store_true", help="Check Telegram authorization without prompting for login.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    agent_cli.add_format_argument(parser)
    return parser


def run_checks(args) -> list[CheckResult]:
    checks = [
        check_python_runtime(),
        check_import("telethon_dependency", "telethon", True, "Install requirements.txt."),
        check_import("openai_dependency", "openai", False, "Install requirements-llm.txt before LLM report generation."),
        check_credentials(args.config_path),
        check_session(args.session_path),
        check_source_input(args.channel_list, args.source_registry),
        check_profile(args.profile),
        check_llm_provider(),
        check_media_dependencies(),
        check_dashboard_assets(),
        check_output_directory(args.output_dir),
    ]
    if args.channel_list:
        checks.append(check_channel_list(args.channel_list))
    if args.source_registry:
        checks.append(check_source_registry(args.source_registry))
    if args.online_telegram:
        checks.append(check_online_telegram(args.config_path, args.session_path))
    return checks


def payload_for_checks(checks: list[CheckResult]) -> dict:
    summary = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        summary[check.status] += 1
    return {
        "ok": summary["fail"] == 0,
        "summary": summary,
        "checks": {check.name: check.to_json() for check in checks},
    }


def print_text(payload: dict) -> None:
    print("TG Channel Scanner doctor")
    print(f"Status: {'OK' if payload['ok'] else 'FAILED'}")
    for name, check in payload["checks"].items():
        print(f"- {check['status'].upper()} {name}: {check['message']}")
        if check.get("next_step"):
            print(f"  Next: {check['next_step']}")


def agent_failure_code(payload: dict) -> tuple[str, int]:
    checks = payload.get("checks", {})
    auth_failures = {
        "telegram_credentials",
        "telegram_session",
        "telegram_online",
    }
    for name in auth_failures:
        if checks.get(name, {}).get("status") == "fail":
            return "doctor_auth_failed", agent_cli.EXIT_AUTH
    return "doctor_failed", agent_cli.EXIT_VALIDATION


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = payload_for_checks(run_checks(args))
    if agent_cli.is_json_format(args):
        if payload["ok"]:
            agent_cli.print_json(agent_cli.envelope_success(payload))
            return agent_cli.EXIT_SUCCESS
        error_code, exit_code = agent_failure_code(payload)
        agent_cli.print_json(
            agent_cli.envelope_error(
                code=error_code,
                message="One or more first-run checks failed.",
                retryable=False,
                next_step="Fix failed checks, then rerun doctor.",
                details=payload,
            )
        )
        return exit_code
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
