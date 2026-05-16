"""Telethon login, entity resolution, and scan loop runtime."""

from __future__ import annotations

import asyncio
import getpass
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

try:
    from scripts import agent_cli, source_registry
    from scripts.media_ocr import OcrConfig, process_message
    from scripts.scan_config import (
        LOGIN_QUIT_COMMANDS,
        LOGIN_RESEND_COMMANDS,
        SESSION_PATH,
        ScanError,
        load_config,
    )
    from scripts.scan_media_projection import _make_ocr_config, message_to_dict
    from scripts.scan_metadata import build_scan_metadata, meta_path_for_output, write_scan_metadata
    from scripts.scan_sources import (
        ChannelResult,
        ScanSource,
        _health_from_failure,
        _health_from_result,
        load_scan_sources,
        scan_hours,
        write_jsonl,
    )
    from scripts.scan_config import cutoff_from_args
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts import agent_cli, source_registry
    from scripts.media_ocr import OcrConfig, process_message
    from scripts.scan_config import (
        LOGIN_QUIT_COMMANDS,
        LOGIN_RESEND_COMMANDS,
        SESSION_PATH,
        ScanError,
        load_config,
    )
    from scripts.scan_media_projection import _make_ocr_config, message_to_dict
    from scripts.scan_metadata import build_scan_metadata, meta_path_for_output, write_scan_metadata
    from scripts.scan_sources import (
        ChannelResult,
        ScanSource,
        _health_from_failure,
        _health_from_result,
        load_scan_sources,
        scan_hours,
        write_jsonl,
    )
    from scripts.scan_config import cutoff_from_args



def _read_login_value(prompt: str, *, secret: bool = False) -> str:
    try:
        value = getpass.getpass(prompt) if secret else input(prompt)
    except (EOFError, KeyboardInterrupt) as exc:
        raise ScanError("Login cancelled.") from exc
    value = value.strip()
    if value.casefold() in LOGIN_QUIT_COMMANDS:
        raise ScanError("Login cancelled.")
    return value



async def _prompt_phone_and_send_code(client: TelegramClient, max_attempts: int) -> str:
    for _attempt in range(max_attempts):
        phone = _read_login_value("Enter your phone number with country code (or q to quit): ")
        if not phone:
            print("Phone number cannot be empty. Try again or type q to quit.", file=sys.stderr)
            continue
        try:
            await client.send_code_request(phone)
        except Exception as exc:
            print(f"Telegram rejected that phone number: {exc}", file=sys.stderr)
            continue
        return phone
    raise ScanError("Could not send Telegram login code after multiple attempts.")



async def _prompt_two_factor_password(client: TelegramClient, max_attempts: int) -> None:
    for _attempt in range(max_attempts):
        password = _read_login_value("Enter your Telegram 2FA password (or q to quit): ", secret=True)
        if not password:
            print("Two-factor password cannot be empty. Try again or type q to quit.", file=sys.stderr)
            continue
        try:
            await client.sign_in(password=password)
        except Exception as exc:
            print(f"Telegram rejected that 2FA password: {exc}", file=sys.stderr)
            continue
        return
    raise ScanError("Could not complete Telegram 2FA after multiple attempts.")



async def _prompt_code_and_sign_in(
    client: TelegramClient,
    phone: str,
    max_attempts: int,
) -> None:
    for _attempt in range(max_attempts):
        code = _read_login_value(
            "Enter the Telegram verification code, or type resend to request a new code: "
        )
        if not code:
            print("Verification code cannot be empty. Try again or type resend.", file=sys.stderr)
            continue
        if code.casefold() in LOGIN_RESEND_COMMANDS:
            try:
                await client.send_code_request(phone)
            except Exception as exc:
                print(f"Could not resend Telegram code: {exc}", file=sys.stderr)
            else:
                print("Telegram code resent.", file=sys.stderr)
            continue
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            await _prompt_two_factor_password(client, max_attempts)
            return
        except Exception as exc:
            print(f"Telegram rejected that verification code: {exc}", file=sys.stderr)
            continue
        return
    raise ScanError("Could not complete Telegram login after multiple verification attempts.")



async def interactive_login(client: TelegramClient, *, max_attempts: int = 3) -> None:
    print("No active Telegram session. Starting interactive login...")
    print("Type q at any prompt to cancel.", file=sys.stderr)

    phone = await _prompt_phone_and_send_code(client, max_attempts)
    await _prompt_code_and_sign_in(client, phone, max_attempts)

    session_string = StringSession.save(client.session)
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(session_string, encoding="utf-8")
    print(f"Session saved to {SESSION_PATH}")



async def resolve_entity(client: TelegramClient, name: str):
    name = name.strip()
    if name.lstrip("-").isdigit():
        entity_id = int(name)
        try:
            return await client.get_entity(entity_id)
        except Exception:
            pass
        # Fallback: search dialogs for matching ID
        async for dialog in client.iter_dialogs():
            if dialog.entity.id == entity_id:
                return dialog.entity
        raise ScanError(f"Cannot resolve entity: {name}")
    try:
        return await client.get_entity(name)
    except Exception:
        pass
    name_lower = name.lower()
    async for dialog in client.iter_dialogs():
        if dialog.name.lower() == name_lower:
            return dialog.entity
    raise ScanError(f"Cannot resolve channel: {name}")



async def read_channel(
    client: TelegramClient,
    entity,
    channel_name: str,
    cutoff: datetime,
    max_limit: int,
    ocr: OcrConfig | None = None,
) -> ChannelResult:
    """Stream messages via iter_messages, stop immediately at cutoff.

    Uses iter_messages with early termination: as soon as we encounter a
    message older than cutoff, we break — no exponential doubling, no
    over-fetching. max_limit serves as a safety cap against runaway reads.
    """
    cutoff_utc = cutoff.astimezone(UTC)
    safety_cap = max_limit

    kept_msgs: list = []
    raw_count = 0
    skipped_missing_date = 0
    hit_cutoff = False

    async for msg in client.iter_messages(entity, limit=safety_cap):
        raw_count += 1
        if msg.date is None:
            skipped_missing_date += 1
            continue
        d = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=UTC)
        if d.astimezone(UTC) < cutoff_utc:
            hit_cutoff = True
            break
        kept_msgs.append(msg)

    exhausted_limit = raw_count >= safety_cap

    # OCR media
    ocr_texts: dict[int, str] = {}
    ocr_count = 0
    ocr_errors: list[str] = []
    if ocr:
        for m in kept_msgs:
            if m.media:
                try:
                    text = await process_message(client, m, ocr)
                except Exception as exc:
                    ocr_errors.append(f"OCR failed for message {m.id}: {exc}")
                    continue
                if text:
                    ocr_texts[m.id] = text
                    ocr_count += 1
                    print(f"    OCR [{channel_name}:{m.id}] -> {len(text)} chars", file=sys.stderr)

    dicts = [message_to_dict(m, channel_name) for m in kept_msgs]
    for d in dicts:
        if d["id"] in ocr_texts:
            d["ocr_text"] = ocr_texts[d["id"]]

    return ChannelResult(
        channel=channel_name,
        messages=dicts,
        raw_count=raw_count,
        skipped_missing_date=skipped_missing_date,
        limit=safety_cap,
        incomplete=exhausted_limit and not hit_cutoff,
        ocr_count=ocr_count,
        stderr="\n".join(ocr_errors),
    )



def _print_progress(args, text: str, *, error: bool = False) -> None:
    stream = sys.stderr if error or agent_cli.is_json_format(args) else sys.stdout
    print(text, file=stream)


@dataclass
class SourceScanOutcome:
    index: int
    scan_source: ScanSource
    result: ChannelResult | None = None
    error: Exception | None = None


def _display_name_for_entity(channel_name: str, entity) -> str:
    if not channel_name.lstrip("-").isdigit():
        return channel_name
    title = getattr(entity, "title", None) or getattr(entity, "first_name", None)
    return str(title) if title else channel_name


async def _scan_one_source(
    *,
    args,
    client: TelegramClient,
    scan_source: ScanSource,
    index: int,
    cutoff: datetime,
    ocr: OcrConfig | None,
) -> SourceScanOutcome:
    channel_name = scan_source.channel
    _print_progress(args, f"[{index}] Reading: {channel_name}")
    try:
        entity = await resolve_entity(client, channel_name)
        result = await read_channel(
            client=client,
            entity=entity,
            channel_name=_display_name_for_entity(channel_name, entity),
            cutoff=cutoff,
            max_limit=args.max_limit,
            ocr=ocr,
        )
    except Exception as exc:
        return SourceScanOutcome(index=index, scan_source=scan_source, error=exc)
    return SourceScanOutcome(index=index, scan_source=scan_source, result=result)



async def _run_scan(args) -> int:
    json_mode = agent_cli.is_json_format(args)
    login_only = getattr(args, "login_only", False)

    if login_only:
        sources: list[ScanSource] = []
        registry_payload = None
        channels: list[str] = []
    else:
        try:
            sources, registry_payload = load_scan_sources(args)
        except (OSError, source_registry.RegistryError, ScanError) as exc:
            agent_cli.emit_error(
                args,
                code="source_input_invalid",
                message=str(exc),
                retryable=False,
                next_step="Fix --source-registry or channel list, then rerun scan.",
            )
            return agent_cli.EXIT_VALIDATION
        if not sources:
            message = "No enabled sources to scan."
            agent_cli.emit_error(
                args,
                code="source_input_empty",
                message=message,
                retryable=False,
                next_step="Enable at least one source or add channels to the list.",
            )
            return agent_cli.EXIT_VALIDATION if json_mode else 1

        channels = [source.channel for source in sources]

    try:
        config = load_config()
    except ScanError as exc:
        agent_cli.emit_error(
            args,
            code="telegram_credentials_missing",
            message=str(exc),
            retryable=False,
            next_step="Configure TELEGRAM_API_ID and TELEGRAM_API_HASH.",
        )
        return agent_cli.EXIT_AUTH if json_mode else 1

    client = TelegramClient(
        StringSession(config.session_string),
        config.api_id,
        config.api_hash,
        flood_sleep_threshold=args.max_flood_wait_seconds,
    )
    await client.connect()

    try:
        if not await client.is_user_authorized():
            if login_only and json_mode:
                await client.disconnect()
                agent_cli.emit_error(
                    args,
                    code="telegram_login_interactive_required",
                    message="Telegram login requires an interactive terminal.",
                    retryable=False,
                    next_step="Run tgcs login in a terminal.",
                )
                return agent_cli.EXIT_AUTH
            if json_mode:
                await client.disconnect()
                agent_cli.emit_error(
                    args,
                    code="telegram_session_unauthorized",
                    message="Telegram session is not authorized.",
                    retryable=False,
                    next_step="Run a human-mode scan once to complete Telegram login.",
                )
                return agent_cli.EXIT_AUTH
            if not sys.stdin.isatty():
                await client.disconnect()
                agent_cli.emit_error(
                    args,
                    code="telegram_login_interactive_required",
                    message="Telegram login requires an interactive terminal.",
                    retryable=False,
                    next_step="Run tgcs login in a terminal.",
                )
                return agent_cli.EXIT_AUTH
            await interactive_login(client)
    except ScanError:
        await client.disconnect()
        raise

    if login_only:
        await client.disconnect()
        if json_mode:
            agent_cli.emit_success(args, {"status": "authorized"})
        else:
            print("Telegram session is ready.")
        return agent_cli.EXIT_SUCCESS

    try:
        ocr = _make_ocr_config(args)
    except ScanError as exc:
        await client.disconnect()
        agent_cli.emit_error(
            args,
            code="ocr_config_invalid",
            message=str(exc),
            retryable=False,
            next_step="Disable --ocr or configure the selected OCR provider.",
        )
        return agent_cli.EXIT_VALIDATION if json_mode else 1

    if ocr:
        _print_progress(
            args,
            "OCR enabled: "
            f"{ocr.model} @ {args.ocr_effective_base_url} "
            f"({args.ocr_effective_provider})",
        )
    else:
        _print_progress(args, "OCR disabled: pass --ocr to upload media to an OCR/STT API")

    hours = scan_hours(args)
    cutoff = cutoff_from_args(hours, args.since)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or (args.output_dir / f"scan_{timestamp}.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path = output_path.with_suffix(".errors.log")
    meta_path = meta_path_for_output(output_path)

    _print_progress(args, f"Scan started: {started_at.isoformat(timespec='seconds')}")
    _print_progress(args, f"Precise cutoff: {cutoff.isoformat()}")
    if args.source_registry:
        _print_progress(args, f"Source registry: {args.source_registry}")
    else:
        _print_progress(args, f"Channel list: {args.channel_list}")
    _print_progress(args, f"Output: {output_path}")
    _print_progress(args, "---")

    failures = 0
    incomplete = 0
    total_written = 0
    total_ocr = 0
    failed_channels: list[str] = []
    incomplete_channels: list[str] = []
    source_health: list[dict] = []
    scan_concurrency = max(1, int(getattr(args, "scan_concurrency", 1) or 1))
    start_lock = asyncio.Lock()
    next_start_at = 0.0

    async def wait_for_rate_limit() -> None:
        nonlocal next_start_at
        delay = float(getattr(args, "delay", 0) or 0)
        if delay <= 0:
            return
        loop = asyncio.get_running_loop()
        async with start_lock:
            now = loop.time()
            wait_seconds = max(0.0, next_start_at - now)
            next_start_at = max(now, next_start_at) + delay
        if wait_seconds:
            await asyncio.sleep(wait_seconds)

    semaphore = asyncio.Semaphore(scan_concurrency)

    async def run_bounded_source(index: int, scan_source: ScanSource) -> SourceScanOutcome:
        async with semaphore:
            # Telegram rate limits are account-wide. Even when source reads run
            # concurrently, keep starts paced by --delay so raising concurrency
            # does not silently turn a first-run catch-up into a request burst.
            await wait_for_rate_limit()
            return await _scan_one_source(
                args=args,
                client=client,
                scan_source=scan_source,
                index=index,
                cutoff=cutoff,
                ocr=ocr,
            )

    with errors_path.open("w", encoding="utf-8", newline="\n") as errors:
        pending_outcomes: dict[int, SourceScanOutcome] = {}
        next_outcome_index = 1
        tasks = [
            asyncio.create_task(run_bounded_source(index, scan_source))
            for index, scan_source in enumerate(sources, start=1)
        ]
        for completed in asyncio.as_completed(tasks):
            outcome = await completed
            pending_outcomes[outcome.index] = outcome
            while next_outcome_index in pending_outcomes:
                outcome = pending_outcomes.pop(next_outcome_index)
                next_outcome_index += 1
                scan_source = outcome.scan_source
                channel_name = scan_source.channel
                if outcome.error:
                    failures += 1
                    failed_channels.append(channel_name)
                    errors.write(f"[{channel_name}] ERROR: {outcome.error}\n")
                    source_health.append(_health_from_failure(scan_source, outcome.error))
                    _print_progress(
                        args,
                        f"  Failed: {channel_name}: {outcome.error} (see {errors_path.name})",
                        error=True,
                    )
                    continue

                result = outcome.result
                if result is None:
                    continue
                written = write_jsonl(output_path, result.messages)
                total_written += written
                total_ocr += result.ocr_count
                source_health.append(_health_from_result(scan_source, result, written))
                if result.skipped_missing_date:
                    errors.write(
                        f"[{channel_name}] skipped {result.skipped_missing_date} "
                        "messages without parseable date\n"
                    )
                if result.stderr:
                    for line in result.stderr.splitlines():
                        errors.write(f"[{channel_name}] {line}\n")
                if result.incomplete:
                    incomplete += 1
                    incomplete_channels.append(channel_name)
                    errors.write(
                        f"[{channel_name}] INCOMPLETE: read {result.raw_count} rows at "
                        f"max limit {result.limit}; raise SCAN_MAX_LIMIT or narrow the window.\n"
                    )
                    _print_progress(
                        args,
                        f"  Incomplete at limit {result.limit}; see {errors_path.name}",
                        error=True,
                    )
                ocr_info = f", {result.ocr_count} media OCR'd" if result.ocr_count else ""
                _print_progress(
                    args,
                    f"  {written} messages kept from {result.raw_count} rows "
                    f"(limit {result.limit}){ocr_info}",
                )
    await client.disconnect()
    completed_at = datetime.now(UTC)
    metadata = build_scan_metadata(
        started_at=started_at,
        completed_at=completed_at,
        cutoff=cutoff,
        channel_list_path=args.channel_list or Path(""),
        channels=channels,
        output_path=output_path,
        errors_path=errors_path,
        total_written=total_written,
        failed_channels=failed_channels,
        incomplete_channels=incomplete_channels,
        total_ocr=total_ocr,
        ocr_enabled=ocr is not None,
        hours=hours,
        source_health=source_health,
        source_registry_path=args.source_registry,
    )
    if registry_payload is not None:
        metadata["source_registry_source_count"] = len(registry_payload.get("sources", []))
    metadata["scan_concurrency"] = scan_concurrency
    write_scan_metadata(meta_path, metadata)

    _print_progress(args, "---")
    _print_progress(args, f"Done. {len(channels)} channels scanned, {total_written} messages collected.")
    if total_ocr:
        _print_progress(args, f"{total_ocr} media messages OCR'd.")
    if failures:
        _print_progress(args, f"{failures} channels failed. See: {errors_path}", error=True)
    if incomplete:
        _print_progress(args, f"{incomplete} channels may be incomplete. See: {errors_path}", error=True)
    _print_progress(args, f"Output: {output_path}")
    _print_progress(args, f"Metadata: {meta_path}")
    _print_progress(args, "")
    _print_progress(args, "Next: Summarize with your preferred AI:")
    _print_progress(
        args,
        f"  python scripts/summarize.py "
        f"--input {output_path} --profile profiles/YOUR_PROFILE.md",
    )

    partial_failures_allowed = bool(getattr(args, "allow_partial_failures", False))
    partial_failure_warning = failures and partial_failures_allowed and total_written > 0
    if failures and not partial_failure_warning:
        if json_mode:
            agent_cli.print_json(
                agent_cli.envelope_error(
                    code="scan_failed",
                    message=f"{failures} sources failed.",
                    retryable=True,
                    next_step=f"Inspect {errors_path} and source_health.",
                    details={
                        "output_path": str(output_path),
                        "meta_path": str(meta_path),
                        "errors_path": str(errors_path),
                        "failed_channels": failed_channels,
                        "source_health": source_health,
                    },
                )
            )
        return agent_cli.EXIT_RUNTIME
    if partial_failure_warning:
        _print_progress(
            args,
            "Partial source failures were kept as warnings because other sources produced messages.",
            error=True,
        )
    if incomplete and not args.allow_incomplete:
        if json_mode:
            agent_cli.print_json(
                agent_cli.envelope_error(
                    code="scan_incomplete",
                    message=f"{incomplete} sources may be incomplete.",
                    retryable=True,
                    next_step="Raise --max-limit, narrow --hours, or pass --allow-incomplete.",
                    details={
                        "output_path": str(output_path),
                        "meta_path": str(meta_path),
                        "errors_path": str(errors_path),
                        "incomplete_channels": incomplete_channels,
                        "source_health": source_health,
                    },
                )
            )
        return agent_cli.EXIT_INCOMPLETE
    if json_mode:
        agent_cli.print_json(
            agent_cli.envelope_success(
                {
                    "output_path": str(output_path),
                    "meta_path": str(meta_path),
                    "errors_path": str(errors_path),
                    "message_count": total_written,
                    "channel_count": len(channels),
                    "failure_count": failures,
                    "failed_channels": failed_channels,
                    "status": "complete_with_warnings" if partial_failure_warning else "complete",
                    "source_health": source_health,
                }
            )
        )
    return agent_cli.EXIT_SUCCESS
