import unittest
from pathlib import Path

from scripts.profile_schema import parse_profile_config


class ProfileTemplateTests(unittest.TestCase):
    def test_builtin_profile_templates_exist_and_parse(self):
        template_dir = Path("profiles/templates")
        expected = {
            "jobs.md",
            "airdrops.md",
            "market-news.md",
            "research-leads.md",
            "competitor-monitoring.md",
        }

        self.assertEqual(expected, {path.name for path in template_dir.glob("*.md")})

        for path in template_dir.glob("*.md"):
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                config = parse_profile_config(text)
                self.assertTrue(config.labels.report_title)
                self.assertTrue(config.labels.output_filename.endswith(".md"))
                self.assertTrue(config.mode.fields)

    def test_jobs_profile_uses_compact_fast_alert_schema(self):
        text = Path("profiles/templates/jobs.md").read_text(encoding="utf-8")
        config = parse_profile_config(text)
        field_names = {field.name for field in config.mode.fields}
        opportunity_type = next(field for field in config.mode.fields if field.name == "opportunity_type")

        self.assertEqual(config.mode.top_level_key, "items")
        self.assertEqual(config.mode.dedup_fields, ["company", "role"])
        self.assertIn("opportunity_type", field_names)
        self.assertIn("role", field_names)
        self.assertIn("apply_url", field_names)
        self.assertIn("urgency_reason", field_names)
        self.assertNotIn("stack", field_names)
        self.assertIn("contract", opportunity_type.values)
        self.assertIn("mini_app_ton_project", opportunity_type.values)
        self.assertIn("developer opportunity", text.casefold())
        self.assertIn("mini apps", text.casefold())
        self.assertIn("ton", text.casefold())
        self.assertIn("freelance", text.casefold())
        self.assertIn("budget", text.casefold())
        self.assertIn("at most 8 items", text.casefold())
        self.assertIn("do not copy full job descriptions", text.casefold())


if __name__ == "__main__":
    unittest.main()
