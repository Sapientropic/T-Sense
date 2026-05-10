"""Localhost dashboard server for the v0.5-alpha review inbox."""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

try:
    from scripts import agent_cli, monitor_state
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import agent_cli, monitor_state


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GIT_TIMEOUT_SECONDS = 25
LOOPBACK_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
REPORT_HTML_MOBILE_PATCH = """<style data-dashboard-report-mobile-patch>
@media (max-width: 520px) {
  .report-title {
    max-width: 100% !important;
    font-size: 2.35rem !important;
    line-height: 1.04 !important;
    overflow-wrap: anywhere !important;
    text-shadow: 3px 3px 0 color-mix(in oklch, var(--c-accent) 15%, transparent) !important;
  }
}
@media (max-width: 360px) {
  .report-title { font-size: 2rem !important; }
}
</style>"""


class DashboardGitError(Exception):
    """Raised when repository update checks or pulls cannot be completed safely."""


class DashboardArtifactError(Exception):
    """Raised when a requested dashboard artifact is missing or outside output/runs."""


def is_dashboard_report_artifact_name(name: str) -> bool:
    lower = name.lower()
    if lower in {"report.html", "report.md"}:
        return True
    path = PurePosixPath(lower)
    if path.suffix not in {".html", ".md"}:
        return False
    return "report" in path.stem.split("-")


def dashboard_host_warning(host: str) -> str | None:
    normalized = host.strip().lower()
    if normalized in LOOPBACK_DASHBOARD_HOSTS:
        return None
    return (
        "Dashboard host is not loopback. Dashboard state can include local workflow context "
        "and report artifacts may include raw context; only bind this server to a trusted interface."
    )


@contextmanager
def close_after_use(conn) -> Iterator:
    try:
        yield conn
    finally:
        conn.close()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_git(args: list[str], *, timeout: int = GIT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        command = " ".join(["git", *args])
        raise DashboardGitError(f"{command} timed out after {timeout} second(s).") from exc
    except OSError as exc:
        raise DashboardGitError(f"Unable to run git: {exc}") from exc


def _git_value(args: list[str]) -> str | None:
    completed = _run_git(args)
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _repo_web_url(remote_url: str | None) -> str | None:
    if not remote_url:
        return None
    if remote_url.startswith("git@github.com:"):
        remote_url = "https://github.com/" + remote_url.removeprefix("git@github.com:")
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    return remote_url


def _git_update_status(*, fetch: bool) -> dict:
    branch = _git_value(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    upstream = _git_value(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    remote_url = _git_value(["config", "--get", "remote.origin.url"])
    dirty_output = _git_value(["status", "--porcelain"]) or ""
    dirty_count = len([line for line in dirty_output.splitlines() if line.strip()])
    fetch_error = ""

    if fetch:
        completed = _run_git(["fetch", "--prune", "origin"], timeout=45)
        if completed.returncode != 0:
            fetch_error = (completed.stderr or completed.stdout or "git fetch failed").strip()

    head = _git_value(["rev-parse", "--short", "HEAD"])
    remote_head = _git_value(["rev-parse", "--short", upstream]) if upstream else None
    ahead = 0
    behind = 0
    status = "no_upstream"
    message = "No upstream branch is configured for this local branch."
    pull_allowed = False

    if fetch_error:
        status = "fetch_failed"
        message = fetch_error
    elif upstream:
        compare = _git_value(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
        if compare:
            parts = compare.split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
        if ahead == 0 and behind == 0:
            status = "up_to_date"
            message = "Local branch is up to date with upstream."
        elif ahead == 0 and behind > 0:
            status = "behind"
            message = f"{behind} upstream commit(s) available."
            pull_allowed = dirty_count == 0
        elif ahead > 0 and behind == 0:
            status = "ahead"
            message = f"Local branch is ahead of upstream by {ahead} commit(s)."
        else:
            status = "diverged"
            message = f"Local branch diverged: {ahead} ahead, {behind} behind."

    if dirty_count:
        pull_allowed = False
        if status == "behind":
            message = f"{message} Commit or stash {dirty_count} local change(s) before pulling."

    return {
        "schema_version": "git_update_status_v1",
        "status": status,
        "message": message,
        "branch": branch,
        "upstream": upstream,
        "repo_url": _repo_web_url(remote_url),
        "remote_url": remote_url,
        "head": head,
        "remote_head": remote_head,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty_count > 0,
        "dirty_count": dirty_count,
        "pull_allowed": pull_allowed,
        "fetched": fetch and not fetch_error,
        "checked_at": _utc_now(),
    }


def _git_pull_latest() -> dict:
    before = _git_update_status(fetch=True)
    if before["dirty"]:
        raise DashboardGitError("Working tree has local changes. Commit or stash them before pulling.")
    if before["status"] != "behind" or not before["pull_allowed"]:
        raise DashboardGitError(before["message"])
    completed = _run_git(["pull", "--ff-only"], timeout=60)
    if completed.returncode != 0:
        raise DashboardGitError((completed.stderr or completed.stdout or "git pull --ff-only failed").strip())
    after = _git_update_status(fetch=False)
    after["pull_output"] = (completed.stdout or "").strip()
    return after


def resolve_run_artifact_path(requested_path: str, *, artifact_root: Path | None = None) -> Path:
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

    root = (artifact_root or PROJECT_ROOT.joinpath(*parts[: run_index + 1])).resolve()
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


def dashboard_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def write_feedback_export(conn, *, output_path: Path | None = None) -> dict:
    target = output_path or PROJECT_ROOT / "output" / "feedback" / "review-feedback.jsonl"
    entries = monitor_state.export_feedback_entries(conn)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    target.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    return {
        "schema_version": "feedback_export_result_v1",
        "feedback_count": len(entries),
        "output_path": dashboard_relative_path(target),
    }


def markdown_inline_html(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<em>\1</em>", escaped)

    def link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = html.unescape(match.group(2)).strip()
        if not re.match(r"^https?://", href, flags=re.IGNORECASE):
            return match.group(0)
        return f'<a href="{html.escape(href, quote=True)}" rel="noreferrer" target="_blank">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, escaped)


def markdown_table_html(lines: list[str]) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if not rows:
        return ""
    has_header = len(rows) > 1 and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in rows[1])
    body_rows = rows[2:] if has_header else rows
    parts = ["<div class=\"table-wrap\"><table>"]
    if has_header:
        parts.append("<thead><tr>")
        parts.extend(f"<th>{markdown_inline_html(cell)}</th>" for cell in rows[0])
        parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in body_rows:
        parts.append("<tr>")
        parts.extend(f"<td>{markdown_inline_html(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def markdown_blocks_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    index = 0
    in_list = False
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            if in_list:
                parts.append("</ul>")
                in_list = False
            index += 1
            continue
        if stripped.startswith("```"):
            if in_list:
                parts.append("</ul>")
                in_list = False
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue
        if stripped.startswith("|"):
            if in_list:
                parts.append("</ul>")
                in_list = False
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            parts.append(markdown_table_html(table_lines))
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            if in_list:
                parts.append("</ul>")
                in_list = False
            level = len(heading.group(1))
            parts.append(f"<h{level}>{markdown_inline_html(heading.group(2))}</h{level}>")
            index += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{markdown_inline_html(bullet.group(1))}</li>")
            index += 1
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        paragraph = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if (
                not next_line
                or next_line.startswith("```")
                or next_line.startswith("|")
                or re.match(r"^(#{1,6})\s+", next_line)
                or re.match(r"^[-*]\s+", next_line)
            ):
                break
            paragraph.append(next_line)
            index += 1
        parts.append(f"<p>{markdown_inline_html(' '.join(paragraph))}</p>")
    if in_list:
        parts.append("</ul>")
    return "\n".join(part for part in parts if part)


def render_markdown_artifact(path: Path) -> bytes:
    markdown = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem.replace("-", " ").title()
    body = markdown_blocks_html(markdown)
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink: #1f2a24; --muted: #5f6d61; --paper: #fff7e8; --line: #d7c7a6; --teal: #1d8f7b; }}
    body {{ margin: 0; background: #f4ecd9; color: var(--ink); font: 16px/1.62 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ width: min(920px, calc(100% - 28px)); margin: 0 auto; padding: 28px 0 56px; }}
    article {{ background: var(--paper); border: 1px solid var(--line); padding: clamp(18px, 4vw, 38px); box-shadow: 8px 8px 0 rgba(31, 42, 36, 0.12); }}
    h1, h2, h3 {{ line-height: 1.16; margin: 1.45em 0 0.55em; }}
    h1 {{ margin-top: 0; font-size: clamp(2rem, 8vw, 3.4rem); letter-spacing: 0; }}
    h2 {{ border-top: 1px solid var(--line); padding-top: 1.1em; font-size: clamp(1.4rem, 5vw, 2rem); }}
    h3 {{ font-size: 1.15rem; }}
    p, ul, pre, .table-wrap {{ margin: 0 0 1.1rem; }}
    ul {{ padding-left: 1.25rem; }}
    a {{ color: var(--teal); font-weight: 700; }}
    code {{ background: rgba(29, 143, 123, 0.1); padding: 0.1em 0.28em; border-radius: 4px; }}
    pre {{ overflow-x: auto; background: #14251d; color: #d9f5e9; padding: 14px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); }}
    table {{ width: 100%; border-collapse: collapse; min-width: 520px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; }}
    th {{ background: rgba(29, 143, 123, 0.12); font-size: 0.78rem; text-transform: uppercase; }}
    @media (max-width: 560px) {{ main {{ width: calc(100% - 18px); padding-top: 9px; }} article {{ padding: 16px; box-shadow: none; }} body {{ font-size: 15px; }} }}
  </style>
</head>
<body>
  <main><article>{body}</article></main>
</body>
</html>
"""
    return document.encode("utf-8")


def render_html_report_artifact(path: Path) -> bytes:
    document = path.read_text(encoding="utf-8")
    if "data-dashboard-report-mobile-patch" not in document and "</head>" in document:
        document = document.replace("</head>", f"{REPORT_HTML_MOBILE_PATCH}\n</head>", 1)
    return document.encode("utf-8")


def resolve_static_path(request_path: str, *, static_dir: Path) -> Path:
    relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
    candidate = (static_dir / relative).resolve()
    static_root = static_dir.resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return static_root / "index.html"
    if not candidate.exists() or candidate.is_dir():
        return static_root / "index.html"
    return candidate


class DashboardHandler(BaseHTTPRequestHandler):
    db_path: Path
    static_dir: Path

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[dashboard] {self.address_string()} - {format % args}", file=sys.stderr)

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _connect(self):
        return monitor_state.connect(self.db_path)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/state":
                with close_after_use(self._connect()) as conn:
                    self._json(HTTPStatus.OK, monitor_state.dashboard_snapshot(conn))
                return
            if parsed.path.startswith("/artifacts/"):
                self._serve_artifact(parsed.path.removeprefix("/artifacts/"))
                return
            self._serve_static(parsed.path)
        except (ValueError, json.JSONDecodeError, monitor_state.MonitorStateError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
            if parsed.path == "/api/git/check-updates":
                self._json(HTTPStatus.OK, {"ok": True, "git": _git_update_status(fetch=True)})
                return
            if parsed.path == "/api/git/pull-latest":
                if body.get("confirm") is not True:
                    raise DashboardGitError("Pull latest requires explicit confirmation.")
                self._json(HTTPStatus.OK, {"ok": True, "git": _git_pull_latest()})
                return
            if parsed.path == "/api/feedback/export":
                with close_after_use(self._connect()) as conn:
                    result = write_feedback_export(conn)
                self._json(HTTPStatus.OK, {"ok": True, "export": result})
                return
            if parsed.path.startswith("/api/review-cards/") and parsed.path.endswith("/action"):
                card_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    card = monitor_state.set_card_action(
                        conn,
                        card_id=card_id,
                        action=str(body.get("action") or ""),
                        note=str(body.get("note") or ""),
                    )
                self._json(HTTPStatus.OK, {"ok": True, "card": card})
                return
            if parsed.path.startswith("/api/profiles/") and parsed.path.endswith("/alert-mode"):
                profile_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    profile = monitor_state.update_profile_alert_mode(
                        conn,
                        profile_id=profile_id,
                        mode=str(body.get("mode") or ""),
                    )
                self._json(HTTPStatus.OK, {"ok": True, "profile": profile})
                return
            if parsed.path.startswith("/api/profile-patches/") and parsed.path.endswith("/apply"):
                patch_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    result = monitor_state.apply_profile_patch(conn, patch_id=patch_id)
                self._json(HTTPStatus.OK, {"ok": True, "result": result})
                return
            if parsed.path.startswith("/api/profile-patches/") and parsed.path.endswith("/revert"):
                patch_id = unquote(parsed.path.split("/")[3])
                with close_after_use(self._connect()) as conn:
                    result = monitor_state.revert_profile_patch(conn, patch_id=patch_id)
                self._json(HTTPStatus.OK, {"ok": True, "result": result})
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except (ValueError, json.JSONDecodeError, DashboardGitError, monitor_state.MonitorStateError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def _serve_static(self, request_path: str) -> None:
        if not self.static_dir.exists():
            self._json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": "dashboard_not_built",
                    "next_step": "Run npm install and npm run build in dashboard/.",
                },
            )
            return
        candidate = resolve_static_path(request_path, static_dir=self.static_dir)
        if not candidate.exists():
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "static_file_not_found"})
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_artifact(self, encoded_path: str) -> None:
        try:
            candidate = resolve_run_artifact_path(encoded_path)
        except DashboardArtifactError as exc:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})
            return
        if candidate.suffix.lower() == ".md":
            body = render_markdown_artifact(candidate)
            content_type = "text/html; charset=utf-8"
        elif candidate.suffix.lower() == ".html":
            body = render_html_report_artifact(candidate)
            content_type = "text/html; charset=utf-8"
        else:
            body = candidate.read_bytes()
            content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the local TGCS dashboard.", allow_abbrev=False)
    parser.add_argument("--db", default=".tgcs/tgcs.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--static-dir", default="dashboard/dist")
    agent_cli.add_format_argument(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    static_dir = Path(args.static_dir)
    if not static_dir.is_absolute():
        static_dir = PROJECT_ROOT / static_dir
    DashboardHandler.db_path = db_path
    DashboardHandler.static_dir = static_dir
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    warning = dashboard_host_warning(str(args.host))
    if agent_cli.is_json_format(args):
        payload = {"url": f"http://{args.host}:{args.port}", "db_path": str(db_path)}
        if warning:
            payload["warning"] = warning
        agent_cli.print_json(
            agent_cli.envelope_success(payload)
        )
    else:
        if warning:
            print(f"Warning: {warning}", file=sys.stderr)
        print(f"TGCS dashboard listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return agent_cli.EXIT_SUCCESS
    finally:
        server.server_close()
    return agent_cli.EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
