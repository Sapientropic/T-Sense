import sqlite3
import unittest

from scripts import monitor_db, monitor_state


class MonitorStateDbTests(unittest.TestCase):
    def test_ensure_column_treats_duplicate_column_race_as_success(self):
        class EmptyCursor:
            def fetchall(self):
                return []

        class RacingConnection:
            def execute(self, sql):
                if str(sql).startswith("PRAGMA table_info"):
                    return EmptyCursor()
                raise sqlite3.OperationalError("duplicate column name: opportunity_status")

        monitor_state._ensure_column(RacingConnection(), "review_cards", "opportunity_status", "TEXT")


    def test_init_db_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        monitor_db.init_db(conn)
        monitor_state.init_db(conn)

        row = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (monitor_db.STATE_SCHEMA_VERSION,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(monitor_state.STATE_SCHEMA_VERSION, monitor_db.STATE_SCHEMA_VERSION)



if __name__ == "__main__":
    unittest.main()
