"""Export channels from a Telegram chat folder to a channel list file.

Usage:
    # List all folders
    python scripts/export_folder.py --list

    # Export a specific folder
    python scripts/export_folder.py --folder "Jobs" --output channel_lists/jobs.txt

    # Export by folder ID
    python scripts/export_folder.py --folder-id 3 --output channel_lists/jobs.txt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

# Reuse config loading from scan.py
from scripts.scan import CONFIG_DIR, CONFIG_PATH, SESSION_PATH, ScanError, load_config


async def list_folders(client: TelegramClient) -> list[dict]:
    """List all chat folders with their names and IDs."""
    from telethon.tl.functions.messages import GetDialogFiltersRequest

    filters = await client(GetDialogFiltersRequest())
    folders = []
    for f in filters:
        if hasattr(f, "title") and f.title:
            folders.append(
                {
                    "id": f.id,
                    "title": f.title,
                    "has_pinned": bool(getattr(f, "pinned_peers", None)),
                    "has_included": bool(getattr(f, "include_peers", None)),
                }
            )
    return folders


async def export_folder(client: TelegramClient, folder_id: int) -> list[str]:
    """Export all channel usernames from a specific folder."""
    from telethon.tl.functions.messages import GetDialogFiltersRequest

    filters = await client(GetDialogFiltersRequest())

    target = None
    for f in filters:
        if f.id == folder_id:
            target = f
            break

    if target is None:
        raise ScanError(f"Folder ID {folder_id} not found")

    # Collect all peer entities from the folder
    peers = []
    if hasattr(target, "include_peers") and target.include_peers:
        peers.extend(target.include_peers)
    if hasattr(target, "pinned_peers") and target.pinned_peers:
        peers.extend(target.pinned_peers)

    channels = []
    for peer in peers:
        try:
            entity = await client.get_entity(peer)
            username = getattr(entity, "username", None)
            if username:
                channels.append(username)
            else:
                # Channel without username — use ID
                entity_id = getattr(entity, "id", None)
                if entity_id:
                    channels.append(str(entity_id))
        except Exception as exc:
            print(f"  Warning: could not resolve peer: {exc}", file=sys.stderr)

    return sorted(set(channels))


async def _run(args) -> int:
    config = load_config()
    client = TelegramClient(
        StringSession(config.session_string),
        config.api_id,
        config.api_hash,
    )
    await client.connect()

    if not await client.is_user_authorized():
        print("Error: Not authorized. Run scan.py first to login.", file=sys.stderr)
        await client.disconnect()
        return 1

    if args.list:
        folders = await list_folders(client)
        if not folders:
            print("No chat folders found.")
        else:
            print(f"Found {len(folders)} chat folders:\n")
            for f in folders:
                print(f"  ID {f['id']:2d}: {f['title']}")
        await client.disconnect()
        return 0

    # Determine folder ID
    if args.folder_id is not None:
        folder_id = args.folder_id
    elif args.folder:
        folders = await list_folders(client)
        folder_id = None
        for f in folders:
            if f["title"].lower() == args.folder.lower():
                folder_id = f["id"]
                break
        if folder_id is None:
            # Fuzzy match
            matches = [
                f for f in folders if args.folder.lower() in f["title"].lower()
            ]
            if len(matches) == 1:
                folder_id = matches[0]["id"]
                print(f"Matched folder: {matches[0]['title']}")
            elif len(matches) > 1:
                print(
                    f"Ambiguous folder name '{args.folder}'. Matches:",
                    file=sys.stderr,
                )
                for m in matches:
                    print(f"  ID {m['id']}: {m['title']}", file=sys.stderr)
                await client.disconnect()
                return 1
            else:
                print(f"Folder '{args.folder}' not found.", file=sys.stderr)
                print("Available folders:", file=sys.stderr)
                for f in folders:
                    print(f"  ID {f['id']}: {f['title']}", file=sys.stderr)
                await client.disconnect()
                return 1
    else:
        print("Error: specify --folder or --folder-id", file=sys.stderr)
        await client.disconnect()
        return 1

    print(f"Exporting folder (ID {folder_id})...")
    channels = await export_folder(client, folder_id)
    await client.disconnect()

    if not channels:
        print("No channels found in this folder.")
        return 1

    output = Path(args.output) if args.output else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as f:
            f.write(f"# Auto-exported from Telegram folder\n")
            f.write(f"# {len(channels)} channels\n\n")
            for ch in channels:
                f.write(f"{ch}\n")
        print(f"\nExported {len(channels)} channels to {output}")
    else:
        print(f"\n{len(channels)} channels:")
        for ch in channels:
            print(f"  {ch}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export channels from a Telegram chat folder"
    )
    parser.add_argument("--list", action="store_true", help="List all folders")
    parser.add_argument("--folder", help="Folder name (case-insensitive)")
    parser.add_argument("--folder-id", type=int, help="Folder ID (from --list)")
    parser.add_argument("--output", help="Output file path")
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
