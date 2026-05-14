"""Telegram channel discovery for Signal Desk source setup."""

from __future__ import annotations

import asyncio
from typing import Any

from telethon import TelegramClient
from telethon.sessions import StringSession

from scripts import export_folder, source_registry
from scripts.scan_config import ScanError, load_config


def _dialog_is_channel(entity: object) -> bool:
    return (
        bool(getattr(entity, "broadcast", False))
        or bool(getattr(entity, "megagroup", False))
        or entity.__class__.__name__.casefold().endswith("channel")
    )


def _channel_record(channel: str, *, title: str = "", folder: str = "") -> dict[str, str]:
    normalized = source_registry.normalize_channel_name(channel)
    if not normalized:
        return {}
    return {
        "channel": normalized,
        "label": title.strip() or normalized,
        "title": title.strip() or normalized,
        "folder": folder.strip(),
    }


async def _discover_all_channels(client: TelegramClient) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    async for dialog in client.iter_dialogs():
        entity = getattr(dialog, "entity", None)
        if entity is None or not _dialog_is_channel(entity):
            continue
        username = getattr(entity, "username", None)
        entity_id = getattr(entity, "id", None)
        channel = str(username or entity_id or "").strip()
        record = _channel_record(channel, title=str(getattr(dialog, "name", "") or getattr(entity, "title", "")))
        if record:
            records.append(record)
    return _dedupe_records(records)


async def _discover_folder_channels(client: TelegramClient, *, folder_name: str = "", folder_id: int | None = None) -> list[dict[str, str]]:
    resolved_folder_id = folder_id
    resolved_folder_title = str(folder_name or "").strip()
    if resolved_folder_id is None:
        folders = await export_folder.list_folders(client)
        exact = [folder for folder in folders if str(folder.get("title") or "").casefold() == resolved_folder_title.casefold()]
        fuzzy = [
            folder
            for folder in folders
            if resolved_folder_title and resolved_folder_title.casefold() in str(folder.get("title") or "").casefold()
        ]
        matches = exact or fuzzy
        if len(matches) != 1:
            if not matches:
                raise ScanError(f"Telegram folder not found: {resolved_folder_title}")
            names = ", ".join(str(item.get("title") or item.get("id")) for item in matches[:5])
            raise ScanError(f"Telegram folder name is ambiguous: {resolved_folder_title}. Matches: {names}")
        resolved_folder_id = int(matches[0]["id"])
        resolved_folder_title = str(matches[0]["title"])
    channels = await export_folder.export_folder(client, resolved_folder_id)
    return _dedupe_records([_channel_record(channel, folder=resolved_folder_title) for channel in channels])


def _dedupe_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        channel = source_registry.normalize_channel_name(record.get("channel"))
        if not channel:
            continue
        marker = channel.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append({**record, "channel": channel})
    return deduped


async def _discover_source_channels_async(*, folder_name: str = "", folder_id: int | None = None) -> list[dict[str, str]]:
    config = load_config()
    client = TelegramClient(StringSession(config.session_string), config.api_id, config.api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise ScanError("Telegram session is not authorized. Connect Telegram before source discovery.")
        if folder_name.strip() or folder_id is not None:
            return await _discover_folder_channels(client, folder_name=folder_name, folder_id=folder_id)
        return await _discover_all_channels(client)
    finally:
        await client.disconnect()


def discover_source_channels(*, folder_name: str = "", folder_id: int | None = None) -> list[dict[str, Any]]:
    return list(asyncio.run(_discover_source_channels_async(folder_name=folder_name, folder_id=folder_id)))
