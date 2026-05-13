"""Git update helpers for the local dashboard."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse


GIT_TIMEOUT_SECONDS = 25


class DashboardGitError(Exception):
    """Raised when repository update checks or pulls cannot be completed safely."""


RunGit = Callable[..., subprocess.CompletedProcess[str]]
GitValue = Callable[[list[str]], str | None]


def run_git(
    args: list[str],
    *,
    project_root: Path,
    timeout: int = GIT_TIMEOUT_SECONDS,
    subprocess_module=subprocess,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess_module.run(
            ["git", *args],
            cwd=project_root,
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


def git_value(args: list[str], *, run_git_fn: RunGit) -> str | None:
    completed = run_git_fn(args)
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def repo_web_url(remote_url: str | None) -> str | None:
    if not remote_url:
        return None
    remote_url = remote_url.strip()
    if remote_url.startswith("git@github.com:"):
        remote_url = "https://github.com/" + remote_url.removeprefix("git@github.com:")
    parsed = urlparse(remote_url)
    if parsed.hostname and parsed.scheme in {"http", "https", "ssh"}:
        path = parsed.path or ""
        if path.endswith(".git"):
            path = path[:-4]
        scheme = "https" if parsed.scheme == "ssh" else parsed.scheme
        return f"{scheme}://{parsed.hostname}{path}"
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    return remote_url if "@" not in remote_url and ":" not in remote_url else None


def git_update_status(
    *,
    fetch: bool,
    git_value_fn: GitValue,
    run_git_fn: RunGit,
    safe_result_text_fn: Callable[..., str],
    utc_now_fn: Callable[[], str],
) -> dict:
    branch = git_value_fn(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    upstream = git_value_fn(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    remote_url = git_value_fn(["config", "--get", "remote.origin.url"])
    dirty_output = git_value_fn(["status", "--porcelain"]) or ""
    dirty_count = len([line for line in dirty_output.splitlines() if line.strip()])
    fetch_error = ""

    if fetch:
        completed = run_git_fn(["fetch", "--prune", "origin"], timeout=45)
        if completed.returncode != 0:
            fetch_error = safe_result_text_fn(completed.stderr, completed.stdout) or "git fetch failed"

    head = git_value_fn(["rev-parse", "--short", "HEAD"])
    remote_head = git_value_fn(["rev-parse", "--short", upstream]) if upstream else None
    ahead = 0
    behind = 0
    status = "no_upstream"
    message = "No upstream branch is configured for this local branch."
    pull_allowed = False

    if fetch_error:
        status = "fetch_failed"
        message = fetch_error
    elif upstream:
        compare = git_value_fn(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
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
        "repo_url": repo_web_url(remote_url),
        "head": head,
        "remote_head": remote_head,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty_count > 0,
        "dirty_count": dirty_count,
        "pull_allowed": pull_allowed,
        "fetched": fetch and not fetch_error,
        "checked_at": utc_now_fn(),
    }


def git_pull_latest(*, git_update_status_fn: Callable[..., dict], run_git_fn: RunGit) -> dict:
    before = git_update_status_fn(fetch=True)
    if before["dirty"]:
        raise DashboardGitError("Working tree has local changes. Commit or stash them before pulling.")
    if before["status"] != "behind" or not before["pull_allowed"]:
        raise DashboardGitError(before["message"])
    completed = run_git_fn(["pull", "--ff-only"], timeout=60)
    if completed.returncode != 0:
        raise DashboardGitError((completed.stderr or completed.stdout or "git pull --ff-only failed").strip())
    after = git_update_status_fn(fetch=False)
    after["pull_output"] = (completed.stdout or "").strip()
    return after
