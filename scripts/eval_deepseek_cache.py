"""Run a privacy-preserving DeepSeek cache evaluation on local scan history.

The output intentionally keeps aggregate usage and source refs only. Raw
Telegram text and contact handles stay in the local input files and are not
copied into the eval artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts import agent_cli, monitor, report
except ModuleNotFoundError:
    _PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from scripts import agent_cli, monitor, report


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "evals"


def artifact_path(path: Path, *, root: Path = PROJECT_ROOT) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.name


def artifact_paths(paths: list[Path], *, root: Path = PROJECT_ROOT) -> list[str]:
    labels = [artifact_path(path, root=root) for path in paths]
    duplicates = {label for label, count in Counter(labels).items() if count > 1}
    if not duplicates:
        return labels
    root_resolved = root.resolve()
    resolved_labels: list[str] = []
    for path, label in zip(paths, labels, strict=True):
        if label not in duplicates:
            resolved_labels.append(label)
            continue
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(root_resolved)
            resolved_labels.append(label)
        except ValueError:
            suffix = resolved.suffix
            stem = resolved.name.removesuffix(suffix)
            digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
            resolved_labels.append(f"{stem}-{digest}{suffix}")
    return resolved_labels


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def discover_scan_inputs(root: Path = PROJECT_ROOT) -> list[Path]:
    output_dir = root / "output"
    if not output_dir.exists():
        return []
    return sorted(
        (
            path
            for path in output_dir.rglob("*.jsonl")
            if "evals" not in path.parts and "feedback" not in path.name.casefold()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def message_ref(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "channel": message.get("channel"),
        "id": message.get("id"),
        "date": message.get("date"),
    }


def select_prefiltered_messages(
    input_paths: list[Path],
    *,
    keywords: list[str],
    sample_size: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    lowered = [keyword.casefold() for keyword in keywords]
    for path in input_paths:
        for message in report.sort_messages_newest_first(load_jsonl(path)):
            channel = str(message.get("channel") or "")
            msg_id = str(message.get("id") or "")
            marker = (channel, msg_id)
            if marker in seen:
                continue
            haystack = monitor.message_text_for_prefilter(message).casefold()
            if lowered and not any(keyword in haystack for keyword in lowered):
                continue
            selected.append(message)
            seen.add(marker)
            if len(selected) >= sample_size:
                return selected
    return selected


def summarize_items(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for item in items:
        rating = str(item.get("rating") or "unknown").casefold()
        counts[rating if rating in counts else "unknown"] += 1
    return counts


def summarize_sources(messages: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    counts = Counter(str(message.get("channel") or message.get("source") or "unknown") for message in messages)
    return [{"channel": channel, "message_count": count} for channel, count in counts.most_common(limit)]


def run_usage(run: dict[str, Any]) -> dict[str, Any]:
    usage = run.get("usage")
    return usage if isinstance(usage, dict) else {}


def token_cache_rate(*, hit: int, miss: int) -> float:
    total = hit + miss
    return round(hit / total, 4) if total else 0


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    hit = 0
    miss = 0
    cached_hit = 0
    cached_miss = 0
    total_latency = 0
    cached_latency = 0
    completion_tokens = 0
    ok_runs = 0
    cached_ok_runs = 0
    warmup_latency = 0
    for run in runs:
        usage = run_usage(run)
        hit += int(usage.get("prompt_cache_hit_tokens") or 0)
        miss += int(usage.get("prompt_cache_miss_tokens") or 0)
        if run.get("status") != "ok":
            continue
        ok_runs += 1
        latency = int(run.get("latency_ms") or 0)
        total_latency += latency
        completion_tokens += int(usage.get("completion_tokens") or 0)
        if run.get("label") == "warmup":
            warmup_latency = warmup_latency or latency
            continue
        cached_ok_runs += 1
        cached_latency += latency
        cached_hit += int(usage.get("prompt_cache_hit_tokens") or 0)
        cached_miss += int(usage.get("prompt_cache_miss_tokens") or 0)
    return {
        "run_count": len(runs),
        "ok_run_count": ok_runs,
        "prompt_cache_hit_tokens": hit,
        "prompt_cache_miss_tokens": miss,
        "cache_hit_rate": token_cache_rate(hit=hit, miss=miss),
        "cached_cache_hit_rate": token_cache_rate(hit=cached_hit, miss=cached_miss),
        "warmup_latency_ms": warmup_latency,
        "avg_latency_ms": round(total_latency / ok_runs) if ok_runs else 0,
        "avg_cached_latency_ms": round(cached_latency / cached_ok_runs) if cached_ok_runs else 0,
        "avg_completion_tokens": round(completion_tokens / ok_runs) if ok_runs else 0,
    }


def build_eval_payload(
    *,
    input_paths: list[Path],
    selected_messages: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    model: str,
    provider: str,
    base_url: str | None,
    max_tokens: int,
    profile_path: Path,
    prefilter_keywords: list[str],
) -> dict[str, Any]:
    aggregate = summarize_runs(runs)
    aggregate["message_count"] = len(selected_messages)
    return {
        "schema_version": "deepseek_cache_eval_v1",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "max_tokens": max_tokens,
        "profile_path": artifact_path(profile_path),
        "input_paths": artifact_paths(input_paths),
        "prefilter": {
            "keyword_count": len(prefilter_keywords),
            "source_count": len(
                {str(message.get("channel") or message.get("source") or "unknown") for message in selected_messages}
            ),
            "top_sources": summarize_sources(selected_messages),
            "selected_refs": [message_ref(message) for message in selected_messages],
        },
        "aggregate": aggregate,
        "runs": runs,
    }


def build_matrix_payload(
    *,
    input_paths: list[Path],
    entries: list[dict[str, Any]],
    profile_path: Path,
    prefilter_keywords: list[str],
) -> dict[str, Any]:
    ok_entries = 0
    for entry in entries:
        aggregate = entry.get("aggregate") if isinstance(entry.get("aggregate"), dict) else {}
        if aggregate.get("ok_run_count") == aggregate.get("run_count"):
            ok_entries += 1
    matrix = [
        {
            "model": entry.get("model"),
            "provider": entry.get("provider"),
            "base_url": entry.get("base_url"),
            "max_tokens": entry.get("max_tokens"),
            "sample_size": entry.get("aggregate", {}).get("message_count"),
            "aggregate": entry.get("aggregate", {}),
            "prefilter": entry.get("prefilter", {}),
            "runs": entry.get("runs", []),
        }
        for entry in entries
    ]
    return {
        "schema_version": "deepseek_cache_eval_matrix_v1",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "profile_path": artifact_path(profile_path),
        "input_paths": artifact_paths(input_paths),
        "prefilter": {"keyword_count": len(prefilter_keywords)},
        "aggregate": {"entry_count": len(entries), "ok_entry_count": ok_entries},
        "matrix": matrix,
    }


def write_eval_payload(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_csv_strings(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_csv_ints(value: str | None) -> list[int]:
    values: list[int] = []
    for part in parse_csv_strings(value):
        try:
            item = int(part)
        except ValueError as exc:
            raise ValueError(f"sample size must be an integer: {part}") from exc
        if item <= 0:
            raise ValueError(f"sample size must be positive: {part}")
        values.append(item)
    return values


def resolve_eval_context(args: argparse.Namespace) -> tuple[list[Path], Path, str, list[str]] | int:
    input_paths = [Path(path) for path in args.input] if args.input else discover_scan_inputs(PROJECT_ROOT)
    input_paths = [path for path in input_paths if path.exists()]
    if not input_paths:
        agent_cli.emit_error(
            args,
            code="eval_input_missing",
            message="No scan JSONL files found for evaluation.",
            retryable=False,
            next_step="Pass --input output/scan.jsonl or run scan.py first.",
        )
        return agent_cli.EXIT_VALIDATION
    profile_path = Path(args.profile)
    if not profile_path.exists():
        agent_cli.emit_error(
            args,
            code="profile_not_found",
            message=f"Profile file not found: {profile_path}",
            retryable=False,
            next_step="Pass --profile profiles/templates/jobs.md or another existing profile.",
        )
        return agent_cli.EXIT_VALIDATION

    profile_text = profile_path.read_text(encoding="utf-8")
    keywords = monitor.DEFAULT_FAST_JOBS_PREFILTER_KEYWORDS
    return input_paths, profile_path, profile_text, keywords


def collect_eval_entry(
    *,
    input_paths: list[Path],
    profile_path: Path,
    profile_text: str,
    keywords: list[str],
    sample_size: int,
    repeat: int,
    base_url_arg: str | None,
    model_arg: str,
    max_tokens: int,
) -> dict[str, Any] | None:
    selected = select_prefiltered_messages(input_paths, keywords=keywords, sample_size=sample_size)
    if not selected:
        return None

    base_url, model = report.resolve_llm_settings(base_url_arg, model_arg)
    provider = report.llm_provider(base_url, model)
    runs: list[dict[str, Any]] = []
    for index in range(repeat):
        label = "warmup" if index == 0 else f"cached-{index}"
        try:
            extraction = report.extract_jobs_with_metadata(
                messages=selected,
                profile=profile_text,
                meta={
                    "eval": "deepseek_cache",
                    "message_count": len(selected),
                    "input_path_count": len(input_paths),
                },
                base_url=base_url,
                model=model,
                max_messages=sample_size,
                max_tokens=max_tokens,
                profile_config=report.parse_profile_config(profile_text),
            )
        except report.ReportError as exc:
            runs.append({"label": label, "status": "error", "error": str(exc)})
            continue
        rating_counts = summarize_items(extraction.items)
        runs.append(
            {
                "label": label,
                "status": "ok",
                "latency_ms": extraction.llm.get("latency_ms"),
                "provider": extraction.llm.get("provider"),
                "model": extraction.llm.get("model"),
                "thinking": extraction.llm.get("thinking"),
                "usage": extraction.llm.get("usage", {}),
                "cache": extraction.llm.get("cache", {}),
                "prompt_prefix_hash": extraction.llm.get("prompt_prefix_hash"),
                "item_count": len(extraction.items),
                "high_count": rating_counts["high"],
                "rating_counts": rating_counts,
            }
        )
    return build_eval_payload(
        input_paths=input_paths,
        selected_messages=selected,
        runs=runs,
        model=model,
        provider=provider,
        base_url=base_url,
        max_tokens=max_tokens,
        profile_path=profile_path,
        prefilter_keywords=keywords,
    )


def run_matrix_eval(args: argparse.Namespace) -> int:
    context = resolve_eval_context(args)
    if isinstance(context, int):
        return context
    input_paths, profile_path, profile_text, keywords = context
    try:
        sample_sizes = parse_csv_ints(args.sample_sizes) or [args.sample_size]
    except ValueError as exc:
        agent_cli.emit_error(
            args,
            code="eval_invalid_sample_sizes",
            message=str(exc),
            retryable=False,
            next_step="Use a comma-separated list like --sample-sizes 12,20,30.",
        )
        return agent_cli.EXIT_VALIDATION
    models = parse_csv_strings(args.models) or [args.model]

    entries: list[dict[str, Any]] = []
    for model in models:
        for sample_size in sample_sizes:
            entry = collect_eval_entry(
                input_paths=input_paths,
                profile_path=profile_path,
                profile_text=profile_text,
                keywords=keywords,
                sample_size=sample_size,
                repeat=args.repeat,
                base_url_arg=args.base_url,
                model_arg=model,
                max_tokens=args.max_tokens,
            )
            if entry is not None:
                entries.append(entry)
    if not entries:
        agent_cli.emit_error(
            args,
            code="eval_prefilter_no_match",
            message="No messages matched the jobs-fast prefilter in the selected history.",
            retryable=False,
            next_step="Pass a different --input file or tune prefilter keywords.",
        )
        return agent_cli.EXIT_VALIDATION

    output = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / (
        "deepseek-cache-matrix-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    payload = build_matrix_payload(
        input_paths=input_paths,
        entries=entries,
        profile_path=profile_path,
        prefilter_keywords=keywords,
    )
    write_eval_payload(output, payload)
    data = {
        "output_path": str(output),
        "entry_count": payload["aggregate"]["entry_count"],
        "ok_entry_count": payload["aggregate"]["ok_entry_count"],
        "matrix": [
            {
                "model": entry["model"],
                "provider": entry.get("provider"),
                "base_url": entry.get("base_url"),
                "max_tokens": entry.get("max_tokens"),
                "sample_size": entry["sample_size"],
                "ok_run_count": entry["aggregate"].get("ok_run_count"),
                "cache_hit_rate": entry["aggregate"].get("cache_hit_rate"),
                "cached_cache_hit_rate": entry["aggregate"].get("cached_cache_hit_rate"),
                "avg_latency_ms": entry["aggregate"].get("avg_latency_ms"),
                "avg_cached_latency_ms": entry["aggregate"].get("avg_cached_latency_ms"),
            }
            for entry in payload["matrix"]
        ],
    }
    if agent_cli.is_json_format(args):
        agent_cli.print_json(agent_cli.envelope_success(data))
    else:
        print(f"DeepSeek cache eval matrix saved: {output}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return (
        agent_cli.EXIT_SUCCESS
        if payload["aggregate"]["ok_entry_count"] == payload["aggregate"]["entry_count"]
        else agent_cli.EXIT_RUNTIME
    )


def run_eval(args: argparse.Namespace) -> int:
    if args.models or args.sample_sizes:
        return run_matrix_eval(args)
    context = resolve_eval_context(args)
    if isinstance(context, int):
        return context
    input_paths, profile_path, profile_text, keywords = context
    entry = collect_eval_entry(
        input_paths=input_paths,
        profile_path=profile_path,
        profile_text=profile_text,
        keywords=keywords,
        sample_size=args.sample_size,
        repeat=args.repeat,
        base_url_arg=args.base_url,
        model_arg=args.model,
        max_tokens=args.max_tokens,
    )
    if entry is None:
        agent_cli.emit_error(
            args,
            code="eval_prefilter_no_match",
            message="No messages matched the jobs-fast prefilter in the selected history.",
            retryable=False,
            next_step="Pass a different --input file or tune prefilter keywords.",
        )
        return agent_cli.EXIT_VALIDATION

    output = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / (
        "deepseek-cache-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    write_eval_payload(output, entry)
    data = {
        "output_path": str(output),
        "provider": entry["provider"],
        "model": entry["model"],
        "base_url": entry["base_url"],
        "max_tokens": entry["max_tokens"],
        "message_count": entry["aggregate"]["message_count"],
        "run_count": entry["aggregate"]["run_count"],
        "ok_run_count": entry["aggregate"]["ok_run_count"],
        "cache_hit_rate": entry["aggregate"]["cache_hit_rate"],
        "cached_cache_hit_rate": entry["aggregate"]["cached_cache_hit_rate"],
        "avg_latency_ms": entry["aggregate"]["avg_latency_ms"],
        "avg_cached_latency_ms": entry["aggregate"]["avg_cached_latency_ms"],
    }
    if agent_cli.is_json_format(args):
        agent_cli.print_json(agent_cli.envelope_success(data))
    else:
        print(f"DeepSeek cache eval saved: {output}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return agent_cli.EXIT_SUCCESS if entry["aggregate"]["ok_run_count"] == entry["aggregate"]["run_count"] else agent_cli.EXIT_RUNTIME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate DeepSeek prompt-cache behavior on local TGCS history.")
    parser.add_argument("--input", action="append", default=[], help="Scan JSONL path. Repeat to combine history.")
    parser.add_argument("--profile", default="profiles/templates/jobs.md")
    parser.add_argument("--output")
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--model", default=report.DEFAULT_DEEPSEEK_MODEL)
    parser.add_argument("--models", help="Comma-separated model matrix, e.g. deepseek-v4-flash,deepseek-v4-pro.")
    parser.add_argument("--sample-sizes", help="Comma-separated sample-size matrix, e.g. 12,20,30.")
    parser.add_argument("--base-url")
    parser.add_argument("--max-tokens", type=int, default=0)
    agent_cli.add_format_argument(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_eval(args)


if __name__ == "__main__":
    raise SystemExit(main())
