import sqlite3
import unittest

from scripts import monitor_state


class MonitorStateProfilesTests(unittest.TestCase):
    def test_profile_alert_mode_update_persists_dashboard_override(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "alert_schedule_mode": "work_hours",
            },
        )

        profile = monitor_state.update_profile_alert_mode(conn, profile_id="jobs-fast", mode="muted")
        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(profile["config"]["alert_schedule_mode"], "muted")
        self.assertEqual(snapshot["profiles"][0]["alert_schedule_mode"], "muted")
        self.assertNotIn("config", snapshot["profiles"][0])


    def test_profile_enabled_update_persists_dashboard_override(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "alert_schedule_mode": "work_hours",
            },
        )

        profile = monitor_state.update_profile_enabled(conn, profile_id="jobs-fast", enabled=False)
        overridden = monitor_state.apply_profile_runtime_overrides(
            conn,
            {"id": "jobs-fast", "path": "profiles/templates/jobs.md", "enabled": True},
        )
        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertFalse(profile["enabled"])
        self.assertFalse(overridden["enabled"])
        self.assertFalse(snapshot["profiles"][0]["enabled"])
        self.assertEqual(profile["config"]["enabled"], False)
        self.assertNotIn("config", snapshot["profiles"][0])


    def test_profile_runtime_settings_update_persists_dashboard_override(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "scan_window_hours": 2,
                "semantic_max_messages": 20,
            },
        )

        profile = monitor_state.update_profile_runtime_settings(
            conn,
            profile_id="jobs-fast",
            settings={"scan_window_hours": 6, "semantic_max_messages": 40},
        )
        overridden = monitor_state.apply_profile_runtime_overrides(
            conn,
            {"id": "jobs-fast", "path": "profiles/templates/jobs.md", "scan_window_hours": 2, "semantic_max_messages": 20},
        )
        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(profile["config"]["scan_window_hours"], 6)
        self.assertEqual(profile["config"]["semantic_max_messages"], 40)
        self.assertEqual(overridden["scan_window_hours"], 6)
        self.assertEqual(overridden["semantic_max_messages"], 40)
        self.assertEqual(snapshot["profiles"][0]["scan_window_hours"], 6)
        self.assertEqual(snapshot["profiles"][0]["semantic_max_messages"], 40)
        self.assertNotIn("config", snapshot["profiles"][0])


    def test_profile_runtime_settings_update_persists_schedule_and_alert_rules(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "enabled": True,
                "timezone": "Asia/Shanghai",
                "work_start": "09:00",
                "work_end": "23:00",
                "work_interval_minutes": 15,
                "off_hours_interval_minutes": 60,
                "alert_rule": "high_new_or_changed",
                "alert_max_age_minutes": 60,
            },
        )

        profile = monitor_state.update_profile_runtime_settings(
            conn,
            profile_id="jobs-fast",
            settings={
                "timezone": "America/New_York",
                "workdays": ["mon", "wed", "fri"],
                "work_start": "08:30",
                "work_end": "18:15",
                "work_interval_minutes": 30,
                "off_hours_interval_minutes": 120,
                "alert_rule": "high_new_only",
                "alert_max_age_minutes": 45,
            },
        )
        overridden = monitor_state.apply_profile_runtime_overrides(
            conn,
            {
                "id": "jobs-fast",
                "path": "profiles/templates/jobs.md",
                "timezone": "Asia/Shanghai",
                "work_start": "09:00",
                "work_end": "23:00",
                "work_interval_minutes": 15,
                "off_hours_interval_minutes": 60,
                "alert_rule": "high_new_or_changed",
                "alert_max_age_minutes": 60,
            },
        )
        snapshot = monitor_state.dashboard_snapshot(conn)

        self.assertEqual(profile["config"]["timezone"], "America/New_York")
        self.assertEqual(profile["config"]["workdays"], ["mon", "wed", "fri"])
        self.assertEqual(profile["config"]["work_start"], "08:30")
        self.assertEqual(profile["config"]["work_end"], "18:15")
        self.assertEqual(profile["config"]["work_interval_minutes"], 30)
        self.assertEqual(profile["config"]["off_hours_interval_minutes"], 120)
        self.assertEqual(profile["config"]["alert_rule"], "high_new_only")
        self.assertEqual(profile["config"]["alert_max_age_minutes"], 45)
        self.assertEqual(overridden["timezone"], "America/New_York")
        self.assertEqual(overridden["workdays"], ["mon", "wed", "fri"])
        self.assertEqual(overridden["work_start"], "08:30")
        self.assertEqual(overridden["work_end"], "18:15")
        self.assertEqual(overridden["work_interval_minutes"], 30)
        self.assertEqual(overridden["off_hours_interval_minutes"], 120)
        self.assertEqual(overridden["alert_rule"], "high_new_only")
        self.assertEqual(overridden["alert_max_age_minutes"], 45)
        self.assertEqual(snapshot["profiles"][0]["alert_rule"], "high_new_only")
        self.assertEqual(snapshot["profiles"][0]["alert_max_age_minutes"], 45)
        self.assertNotIn("config", snapshot["profiles"][0])


    def test_profile_runtime_settings_rejects_invalid_values(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        monitor_state.init_db(conn)
        monitor_state.upsert_profile(
            conn,
            {"id": "jobs-fast", "path": "profiles/templates/jobs.md", "enabled": True},
        )

        invalid_settings = [
            {"scan_window_hours": 0},
            {"scan_window_hours": 169},
            {"semantic_max_messages": 0},
            {"semantic_max_messages": 501},
            {"scan_window_hours": True},
            {"command": "tgcs monitor run"},
            {"timezone": ".."},
            {"workdays": ["mon", "noday"]},
            {"work_start": "25:00"},
            {"work_end": "18"},
            {"work_interval_minutes": 0},
            {"off_hours_interval_minutes": 1441},
            {"alert_rule": "all_items"},
            {"alert_max_age_minutes": 0},
        ]
        for settings in invalid_settings:
            with self.subTest(settings=settings):
                with self.assertRaises(monitor_state.MonitorStateError):
                    monitor_state.update_profile_runtime_settings(conn, profile_id="jobs-fast", settings=settings)



if __name__ == "__main__":
    unittest.main()
