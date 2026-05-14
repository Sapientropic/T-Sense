import unittest
from types import SimpleNamespace

from scripts import report_html, report_html_links

from .helpers import load_report_module, sample_extracted_jobs, sample_messages


class ReportHtmlTests(unittest.TestCase):
    def test_report_html_link_helpers_stay_available_from_report_html_facade(self):
        self.assertIs(report_html.safe_href, report_html_links.safe_href)
        self.assertIs(report_html.telegram_handle_to_url, report_html_links.telegram_handle_to_url)
        self.assertIs(report_html._contact_html, report_html_links._contact_html)
        self.assertIs(report_html._source_links, report_html_links._source_links)
        self.assertIs(report_html._tg_md_to_html, report_html_links._tg_md_to_html)
        self.assertIs(report_html._url_field_html, report_html_links._url_field_html)
        self.assertEqual(report_html.safe_href("https://example.com/jobs"), "https://example.com/jobs")
        self.assertIsNone(report_html.safe_href("javascript:alert(1)"))
        self.assertIn('href="https://t.me/remote_jobs"', report_html._source_links(["remote_jobs"]))
        self.assertIn('href="https://safe.example/path"', report_html._tg_md_to_html("[safe](https://safe.example/path)"))


    def test_html_diagnostics_collapses_info_only_items(self):
        report = load_report_module(self)

        html = report.report_diagnostics.render_html(
            [
                {
                    "code": "ocr_disabled_media_present",
                    "severity": "info",
                    "message": "Media text skipped.",
                    "next_step": "Enable OCR only if media matters.",
                }
            ]
        )

        self.assertIn("<details", html)
        self.assertIn("diagnostics-panel compact", html)
        self.assertIn("Info 1", html)


    def test_html_diagnostics_keeps_warning_items_expanded(self):
        report = load_report_module(self)

        html = report.report_diagnostics.render_html(
            [
                {
                    "code": "scan_incomplete",
                    "severity": "warning",
                    "message": "A source may be incomplete.",
                    "next_step": "Rerun with a narrower window.",
                }
            ]
        )

        self.assertIn("<section", html)
        self.assertIn("diagnostic-item warning", html)
        self.assertNotIn("<details", html)


    def test_html_report_does_not_link_unsafe_untrusted_urls(self):
        report = load_report_module(self)
        job = sample_extracted_jobs()[0] | {
            "contact": 'https://safe.example/" onclick="alert(1)',
            "source": 'jobs" onclick="alert(2)',
            "origin_url": "javascript:alert(3)",
        }
        messages = {
            1: {
                "id": 1,
                "channel": 'source" onclick="alert(4)',
                "text": '[bad](javascript:alert(5)) https://safe.example/path?x=1',
            }
        }

        html = report._render_job_card(job, 1, messages)

        self.assertNotIn('onclick="', html.lower())
        self.assertNotIn("href=\"javascript", html.lower())
        self.assertNotIn("javascript:", html.lower())
        self.assertIn("https://safe.example/path?x=1", html)
        self.assertIn('rel="noopener noreferrer"', html)


    def test_html_detail_lists_do_not_use_slash_separators(self):
        report = load_report_module(self)
        job = sample_extracted_jobs()[0] | {
            "contact": "Not specified / @rocket_hr_ai_bot",
            "source": "jobs_in_it_remote / hot_itjobs",
        }

        html = report._render_job_card(job, 1, {})

        self.assertIn("inline-ref-list", html)
        self.assertNotIn("Not specified / @rocket_hr_ai_bot", html)
        self.assertNotIn("jobs_in_it_remote / hot_itjobs", html)


    def test_custom_html_render_uses_profile_action_mapping(self):
        report = load_report_module(self)
        profile = """# Custom watchlist

## Basic Info
- **Focus**: Airdrop signals

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [project, event]
fields:
  - name: project
    required: true
  - name: event
  - name: rating
    values: [high, medium, low]
  - name: action
    values: ["Join now", "Review source", "Skip"]
  - name: why

## Extraction Prompt
system_prompt: |
  Extract useful watchlist items.

## Report Labels
report_title: "Airdrop Signal Brief"
profile_section_title: "Watchlist Profile"
methodology_label: "Telegram channels"
section_high: "Act Now"
section_medium: "Investigate"
section_low: "Archive"
"""
        profile_config = report.parse_profile_config(profile)
        result = report.ReportResult(
            markdown="",
            stats={"matches": 1, "high": 1, "medium": 0, "low": 0, "duplicates_removed": 0},
            warnings=[],
            jobs=[
                {
                    "project": "Example Protocol",
                    "event": "Quest opens",
                    "rating": "high",
                    "why": "Fresh campaign with explicit source.",
                }
            ],
        )

        html = report.render_html(
            result,
            profile,
            {"scan_date": "2026-05-07", "scan_window": "Last 24 hours",
             "channel_count": 3, "total_messages_collected": 42},
            SimpleNamespace(next_scan_note=""),
            [],
            profile_config,
        )

        self.assertIn("Airdrop Signal Brief", html)
        self.assertIn("Join now", html)
        self.assertIn("item-card high", html)
        self.assertIn("data-theme-toggle", html)
        self.assertNotIn("{shared_css}", html)


    def test_generic_html_card_uses_role_when_company_is_placeholder(self):
        report = load_report_module(self)
        profile = """# Developer Opportunities

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [company, role]
fields:
  - name: company
  - name: role
    required: true
  - name: rating
    values: [high, medium, low]
  - name: why
"""
        profile_config = report.parse_profile_config(profile)

        html = report._render_generic_card(
            {
                "company": "Unknown",
                "role": "AI Engineer",
                "rating": "high",
                "why": "Strong fit.",
            },
            1,
            {},
            profile_config,
        )

        self.assertIn('<span class="item-name">AI Engineer</span>', html)
        title_row = html.split("item-title-row", 1)[1].split("</div>", 1)[0]
        self.assertNotIn("Unknown", title_row)


    def test_generic_html_card_avoids_duplicate_why_detail_and_links_apply_url(self):
        report = load_report_module(self)
        profile = """# Developer Opportunities

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [company, role]
fields:
  - name: company
  - name: role
  - name: apply_url
  - name: why
  - name: rating
    values: [high, medium, low]
"""
        profile_config = report.parse_profile_config(profile)

        html = report._render_generic_card(
            {
                "company": "Example Co",
                "role": "AI Engineer",
                "apply_url": "https://example.com/apply",
                "why": "Strong fit.",
                "rating": "high",
            },
            1,
            {},
            profile_config,
        )

        self.assertEqual(html.count("Strong fit."), 1)
        self.assertIn('href="https://example.com/apply"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn(">example.com/apply</a>", html)
        self.assertNotIn(">https://example.com/apply</a>", html)
        self.assertIn("Apply URL", html)
        self.assertNotIn("Apply_Url", html)


    def test_generic_html_card_names_missing_apply_url_and_links_contact_handle(self):
        report = load_report_module(self)
        profile = """# Developer Opportunities

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [company, role]
fields:
  - name: company
  - name: role
  - name: apply_url
  - name: contact
  - name: why
  - name: rating
    values: [high, medium, low]
"""
        profile_config = report.parse_profile_config(profile)

        html = report._render_generic_card(
            {
                "company": "Example Co",
                "role": "AI Engineer",
                "apply_url": "Not specified",
                "contact": "@eupaslavska",
                "why": "Strong fit.",
                "rating": "high",
            },
            1,
            {},
            profile_config,
        )

        self.assertIn("No apply link found", html)
        apply_detail = html.split("Apply URL", 1)[1].split("</div>", 1)[0]
        self.assertNotIn(">Apply<", apply_detail)
        self.assertIn('href="https://t.me/eupaslavska"', html)
        self.assertIn(">@eupaslavska</a>", html)


    def test_html_report_includes_feedback_controls_and_jsonl_export(self):
        report = load_report_module(self)
        raw_jobs = [
            {
                "source_message_refs": [{"channel": "React Job", "id": 1}],
                "company": "Signal Co",
                "role": "Senior React Developer",
                "location": "Remote",
                "source": "React Job",
                "rating": "high",
                "why": "Matches profile",
            }
        ]
        result = report.build_report(
            messages=sample_messages()[:1],
            profile="Senior Frontend Developer",
            raw_jobs=raw_jobs,
            meta={"scan_date": "2026-05-06", "scan_window": "Last 24 hours"},
        )

        html = report.render_html(
            result,
            "Senior Frontend Developer",
            {"scan_date": "2026-05-06", "scan_window": "Last 24 hours"},
            SimpleNamespace(next_scan_note=""),
            sample_messages()[:1],
            report.parse_profile_config("Senior Frontend Developer"),
        )

        self.assertIn("data-report-id=", html)
        self.assertIn("data-feedback-card", html)
        self.assertIn('data-feedback-value="keep"', html)
        self.assertIn('data-feedback-value="skip"', html)
        self.assertIn('data-feedback-value="false_positive"', html)
        self.assertIn("false_negative", html)
        self.assertIn("tgcs-feedback-v1", html)
        self.assertIn("application/x-ndjson", html)
        self.assertIn("&quot;source_message_refs&quot;", html)
        self.assertIn('data-feedback-undo', html)
        self.assertIn('data-feedback-clear', html)
        self.assertIn('"schema_version":"tgcs-report-feedback-state-v2"', html)
        self.assertIn("feedbackByCard", html)



if __name__ == "__main__":
    unittest.main()
