import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def load_report_module(testcase):
    try:
        from scripts import report
    except ImportError as exc:
        testcase.fail(f"scripts.report should exist: {exc}")
    return report


def sample_messages():
    return [
        {
            "id": 1,
            "channel": "React Job",
            "date": "2026-05-06T08:00:00+00:00",
            "text": "Senior React Developer at ООО Исходный код remote hr@codesrc.ru",
        },
        {
            "id": 2,
            "channel": "JavaScript Job",
            "date": "2026-05-06T08:05:00+00:00",
            "text": "Senior React Developer - Source Code LLC remote hr@codesrc.ru",
        },
        {
            "id": 3,
            "channel": "TypeScript Job Offers",
            "date": "2026-05-06T08:10:00+00:00",
            "text": "Positive Technologies frontend TypeScript React",
        },
        {
            "id": 4,
            "channel": "IT Jobs",
            "date": "2026-05-06T08:15:00+00:00",
            "text": "Sber frontend Moscow hybrid",
        },
        {
            "id": 5,
            "channel": "Backend Jobs",
            "date": "2026-05-06T08:20:00+00:00",
            "text": "Python backend role",
        },
    ]


def sample_extracted_jobs():
    return [
        {
            "source_message_ids": [1],
            "company": "ООО Исходный код",
            "role": "Senior React Developer",
            "location": "Remote",
            "salary": "Not specified",
            "contact": "hr@codesrc.ru",
            "source": "React Job",
            "rating": "high",
            "why": "React, Redux, TypeScript and Next.js match the profile.",
            "stack": ["React", "Redux", "TypeScript", "Next.js"],
            "concerns": ["Docker experience should be addressed"],
            "action": "Apply",
        },
        {
            "source_message_ids": [2],
            "company": "ООО Исходный код",
            "role": "Senior React Developer",
            "location": "Remote",
            "salary": "Not specified",
            "contact": "hr@codesrc.ru",
            "source": "JavaScript Job",
            "rating": "high",
            "why": "Duplicate posting of the same role.",
            "stack": ["React", "TypeScript"],
            "concerns": [],
            "action": "Apply",
        },
        {
            "source_message_ids": [3],
            "company": "Positive Technologies",
            "role": "Frontend Developer (TypeScript/React)",
            "location": "Unknown",
            "salary": "Not specified",
            "contact": "",
            "source": "TypeScript Job Offers",
            "rating": "medium",
            "why": "Title matches but details are missing.",
            "stack": ["TypeScript", "React"],
            "concerns": ["Search full JD before applying"],
            "action": "Inspect",
        },
        {
            "source_message_ids": [4],
            "company": "Сбер",
            "role": "Frontend Developer",
            "location": "Moscow hybrid",
            "salary": "Not specified",
            "contact": "https://rabota.sber.ru/search/frontend-developer-4524726/",
            "source": "IT Jobs",
            "rating": "low",
            "why": "Frontend match, but location is not remote-first.",
            "stack": ["Frontend"],
            "concerns": ["Russia office/hybrid conflicts with profile"],
            "action": "Skip unless location criteria change",
        },
    ]


class ReportTests(unittest.TestCase):
    def test_build_report_renders_fixed_sections_and_program_stats(self):
        report = load_report_module(self)
        meta = {
            "scan_date": "2026-05-06",
            "scan_window": "Last 24 hours",
            "channel_count": 17,
            "channels": ["React Job", "JavaScript Job", "TypeScript Job Offers"],
            "total_messages_collected": 5,
        }

        result = report.build_report(
            messages=sample_messages(),
            profile="Aleksei Vlasov\nSenior Frontend Developer\nReact TypeScript remote",
            raw_jobs=sample_extracted_jobs(),
            meta=meta,
            next_scan_note="Next scan scheduled for tomorrow.",
        )

        self.assertEqual(result.stats["matches"], 3)
        self.assertEqual(result.stats["duplicates_removed"], 1)
        self.assertEqual(result.stats["non_relevant_filtered_out"], 1)
        self.assertEqual(result.stats["high"], 1)
        self.assertEqual(result.stats["medium"], 1)
        self.assertEqual(result.stats["low"], 1)
        self.assertIn("# Job Scan Report", result.markdown)
        self.assertIn("**Channels scanned**: 17", result.markdown)
        self.assertIn("## Highly Recommended", result.markdown)
        self.assertIn("## Worth Investigating", result.markdown)
        self.assertIn("## Low Priority", result.markdown)
        self.assertIn("ООО Исходный код", result.markdown)
        self.assertIn("React Job / JavaScript Job", result.markdown)
        self.assertIn("| Duplicates removed | 1 |", result.markdown)
        self.assertIn("*Generated automatically. Next scan scheduled for tomorrow.*", result.markdown)

    def test_source_refs_keep_raw_messages_scoped_by_channel(self):
        report = load_report_module(self)
        messages = [
            {
                "id": 1,
                "channel": "channel_a",
                "date": "2026-05-06T08:00:00+00:00",
                "text": "Correct original text",
            },
            {
                "id": 1,
                "channel": "channel_b",
                "date": "2026-05-06T08:01:00+00:00",
                "text": "Wrong same-id text",
            },
        ]
        raw_jobs = [
            {
                "source_message_ids": [1],
                "source_message_refs": [{"channel": "channel_a", "id": 1}],
                "company": "Signal Co",
                "role": "Frontend Developer",
                "source": "channel_a",
                "rating": "high",
                "why": "Matches profile",
            }
        ]

        jobs, _ = report.deduplicate_jobs(raw_jobs, messages)
        html = report._render_job_card(jobs[0], 1, report.build_message_lookup(messages))

        self.assertEqual(jobs[0]["sources"], ["channel_a"])
        self.assertEqual(
            jobs[0]["source_message_refs"],
            [{"channel": "channel_a", "id": 1}],
        )
        self.assertIn("Correct original text", html)
        self.assertNotIn("Wrong same-id text", html)

    def test_custom_schema_prompt_keeps_source_refs_contract(self):
        report = load_report_module(self)
        profile = """# Custom watchlist

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [project]
fields:
  - name: project
    required: true
  - name: rating
    values: [high, medium, low]

## Extraction Prompt
system_prompt: |
  Extract useful watchlist items.
"""
        profile_config = report.parse_profile_config(profile)

        system_prompt, _ = report.build_extraction_prompts(
            sample_messages(),
            profile,
            meta=None,
            max_messages=10,
            profile_config=profile_config,
        )

        self.assertIn('"source_message_refs": [{"channel": "channel name", "id": 123}]', system_prompt)
        self.assertIn('"source_message_ids": [123]', system_prompt)
        self.assertIn("source_message_refs with both channel and id", system_prompt)

    def test_missing_meta_keeps_running_and_marks_report_as_needing_confirmation(self):
        report = load_report_module(self)

        result = report.build_report(
            messages=sample_messages()[:1],
            profile="Senior Frontend Developer",
            raw_jobs=sample_extracted_jobs()[:1],
            meta=None,
        )

        self.assertIn("[⚠️ 需确认]", result.markdown)
        self.assertIn("## Diagnostics", result.markdown)
        self.assertEqual(result.stats["total_messages_scanned"], 1)

    def test_markdown_report_includes_feedback_jsonl_schema(self):
        report = load_report_module(self)

        result = report.build_report(
            messages=sample_messages()[:1],
            profile="Senior Frontend Developer",
            raw_jobs=sample_extracted_jobs()[:1],
            meta={"scan_date": "2026-05-06", "scan_window": "Last 24 hours"},
        )

        self.assertIn("## Feedback", result.markdown)
        self.assertIn("schema_version", result.markdown)
        self.assertIn("false_negative", result.markdown)

    def test_parse_extraction_response_rejects_invalid_json_with_raw_response(self):
        report = load_report_module(self)

        with self.assertRaises(report.ReportError) as ctx:
            report.parse_extraction_response("not json")

        self.assertIn("valid JSON", str(ctx.exception))
        self.assertEqual(ctx.exception.raw_response, "not json")

    def test_dry_run_prompt_redacts_contacts_and_does_not_call_llm(self):
        report = load_report_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "scan_20260506_080000.jsonl"
            profile_path = root / "profile.md"
            prompt_path = root / "prompt.md"
            input_path.write_text(
                json.dumps(sample_messages()[0], ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            profile_path.write_text(
                "Contact me at candidate@example.com for React roles.",
                encoding="utf-8",
            )

            with patch.object(report, "extract_jobs") as extract_jobs:
                exit_code = report.main(
                    [
                        "--input",
                        str(input_path),
                        "--profile",
                        str(profile_path),
                        "--dry-run-prompt",
                        str(prompt_path),
                        "--redact-contact-info",
                    ]
                )
            text = prompt_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        extract_jobs.assert_not_called()
        self.assertIn("[redacted-email]", text)
        self.assertNotIn("candidate@example.com", text)
        self.assertNotIn("hr@codesrc.ru", text)

    def test_invalid_llm_json_writes_debug_response_and_exits_nonzero(self):
        report = load_report_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "scan_20260506_080000.jsonl"
            profile_path = root / "profile.md"
            output_path = root / "job-scan-report.md"
            input_path.write_text(
                json.dumps(sample_messages()[0], ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            profile_path.write_text("Senior Frontend Developer", encoding="utf-8")
            stderr = io.StringIO()

            with patch.object(
                report,
                "extract_jobs",
                side_effect=report.ReportError("LLM response was not valid JSON", "bad"),
            ):
                with patch("sys.stderr", stderr):
                    exit_code = report.main(
                        [
                            "--input",
                            str(input_path),
                            "--profile",
                            str(profile_path),
                            "--output",
                            str(output_path),
                        ]
                    )
            debug_path = output_path.with_suffix(".llm-response.txt")
            debug_exists = debug_path.exists()
            debug_text = debug_path.read_text(encoding="utf-8") if debug_exists else ""

        self.assertEqual(exit_code, 1)
        self.assertIn("not valid JSON", stderr.getvalue())
        self.assertTrue(debug_exists)
        self.assertEqual(debug_text, "bad")

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

    def test_custom_markdown_render_uses_profile_action_mapping(self):
        report = load_report_module(self)
        profile = """# Custom watchlist

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
"""
        profile_config = report.parse_profile_config(profile)

        rendered = report.render_job(
            {
                "project": "Example Protocol",
                "event": "Quest opens",
                "rating": "high",
                "why": "Fresh campaign with explicit source.",
            },
            1,
            profile_config,
        )

        self.assertIn("**Action**: **Join now**", rendered)

    def test_deepseek_key_gets_matching_default_endpoint_and_model(self):
        report = load_report_module(self)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)

        self.assertEqual(base_url, report.DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(model, report.DEFAULT_DEEPSEEK_MODEL)

    def test_openai_key_keeps_openai_defaults_when_both_keys_exist(self):
        report = load_report_module(self)

        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "sk-openai", "DEEPSEEK_API_KEY": "sk-deepseek"},
            clear=True,
        ):
            base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)

        self.assertIsNone(base_url)
        self.assertEqual(model, report.DEFAULT_MODEL)

    def test_html_output_writes_markdown_and_html_from_one_extraction(self):
        report = load_report_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "scan_20260506_080000.jsonl"
            profile_path = root / "profile.md"
            output_path = root / "job-scan-report.md"
            html_output_path = root / "job-scan-report.html"
            input_path.write_text(
                json.dumps(sample_messages()[0], ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            profile_path.write_text("Senior Frontend Developer", encoding="utf-8")

            with patch.object(report, "extract_jobs", return_value=sample_extracted_jobs()[:1]) as extract_jobs:
                exit_code = report.main(
                    [
                        "--input",
                        str(input_path),
                        "--profile",
                        str(profile_path),
                        "--output",
                        str(output_path),
                        "--html-output",
                        str(html_output_path),
                    ]
                )

            markdown = output_path.read_text(encoding="utf-8")
            html = html_output_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        extract_jobs.assert_called_once()
        self.assertIn("# Job Scan Report", markdown)
        self.assertIn("<!doctype html>", html.lower())

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

    def test_demo_fixture_html_only_runs_without_llm_or_telegram(self):
        report = load_report_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "demo-report.md"

            with patch.object(report, "extract_jobs") as extract_jobs:
                exit_code = report.main(
                    [
                        "--input",
                        "docs/demo/fixtures/demo-scan.jsonl",
                        "--profile",
                        "docs/demo/fixtures/demo-profile.md",
                        "--html-only",
                        "docs/demo/fixtures/demo-report.md",
                        "--output",
                        str(output_path),
                    ]
                )

            html_path = output_path.with_suffix(".html")
            self.assertEqual(exit_code, 0)
            extract_jobs.assert_not_called()
            self.assertTrue(html_path.exists())


if __name__ == "__main__":
    unittest.main()
