"""SQLite connection and schema ownership for monitor state.

The database is local private state under ``.tgcs/``.  Keep schema setup here so
domain modules can change review/projection behavior without also owning
migration races and connection pragmas.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


DB_FILENAME = "tgcs.db"
STATE_SCHEMA_VERSION = "monitor_state_v1"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profiles (
            profile_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            config_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profile_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            profile_path TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            profile_text TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            manifest_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_artifacts (
            artifact_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS review_cards (
            card_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            item_key TEXT NOT NULL,
            title TEXT NOT NULL,
            rating TEXT NOT NULL,
            decision_status TEXT NOT NULL,
            source_refs_json TEXT NOT NULL,
            item_json TEXT NOT NULL,
            status TEXT NOT NULL,
            opportunity_status TEXT NOT NULL DEFAULT 'open',
            opportunity_updated_at TEXT NOT NULL DEFAULT '',
            duplicate_of_card_id TEXT,
            first_run_id TEXT NOT NULL,
            last_run_id TEXT NOT NULL,
            report_path TEXT,
            dashboard_url TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            handled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback_events (
            event_id TEXT PRIMARY KEY,
            card_id TEXT,
            profile_id TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(card_id) REFERENCES review_cards(card_id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS feedback_exports (
            export_id TEXT PRIMARY KEY,
            output_path TEXT NOT NULL,
            feedback_count INTEGER NOT NULL,
            exported_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profile_patch_suggestions (
            patch_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            card_id TEXT,
            note TEXT NOT NULL,
            status TEXT NOT NULL,
            diff_text TEXT NOT NULL,
            proposed_profile_text TEXT NOT NULL,
            base_profile_hash TEXT,
            created_at TEXT NOT NULL,
            applied_at TEXT,
            FOREIGN KEY(card_id) REFERENCES review_cards(card_id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS alert_events (
            alert_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            card_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            delivery_attempt_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
            FOREIGN KEY(card_id) REFERENCES review_cards(card_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS delivery_targets (
            target_id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    _ensure_column(conn, "profile_patch_suggestions", "base_profile_hash", "TEXT")
    _ensure_column(conn, "review_cards", "opportunity_status", "TEXT NOT NULL DEFAULT 'open'")
    _ensure_column(conn, "review_cards", "opportunity_updated_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "review_cards", "duplicate_of_card_id", "TEXT")
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (STATE_SCHEMA_VERSION, utc_now()),
    )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError as exc:
            # Dashboard startup fires several local API requests in parallel.
            # Each request opens its own SQLite connection and runs init_db; if
            # two connections race through the same ADD COLUMN migration, the
            # loser may see "duplicate column name" after its table_info check.
            # Treat that as success rather than surfacing a transient 500.
            if "duplicate column name" not in str(exc).casefold():
                raise
