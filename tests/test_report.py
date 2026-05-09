import io
import json
import sys
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

    def test_build_report_with_state_marks_decision_state_and_negative_evidence(self):
        report = load_report_module(self)
        from scripts import state_store

        profile = """# Market Watch

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [topic, event]
fields:
  - name: source_message_refs
    type: list
  - name: topic
  - name: event
  - name: rating
    values: [high, medium, low]
  - name: why
  - name: negative_evidence
"""
        profile_config = report.parse_profile_config(profile)

        result = report.build_report(
            messages=[
                {
                    "id": 101,
                    "channel": "cointelegraph",
                    "date": "2026-05-08T09:00:00+00:00",
                    "text": "Coinbase outage affects trading.",
                }
            ],
            profile=profile,
            raw_jobs=[
                {
                    "source_message_refs": [{"channel": "cointelegraph", "id": 101}],
                    "topic": "Coinbase",
                    "event": "Exchange outage",
                    "rating": "high",
                    "why": "Decision-relevant operational risk.",
                    "negative_evidence": "No official postmortem yet.",
                }
            ],
            meta={"scan_date": "2026-05-08", "scan_window": "Last 24 hours"},
            profile_config=profile_config,
            state=state_store.default_item_memory(),
            state_observed_at="2026-05-08T09:00:00Z",
        )

        self.assertEqual(result.state_summary["new"], 1)
        self.assertEqual(result.jobs[0]["decision_state"]["status"], "new")
        self.assertIn("Decision state: New", result.markdown)
        self.assertIn("Negative evidence", result.markdown)

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

            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
                with patch.object(
                    report,
                    "extract_jobs_with_metadata",
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

    def test_markdown_title_uses_role_when_company_is_placeholder(self):
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
"""
        profile_config = report.parse_profile_config(profile)

        rendered = report.render_job(
            {
                "company": "Unknown",
                "role": "AI Engineer",
                "rating": "high",
                "why": "Strong fit.",
            },
            1,
            profile_config,
        )

        self.assertIn("### 1. AI Engineer", rendered)
        self.assertNotIn("### 1. Unknown", rendered)

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
        self.assertIn("Apply URL", html)
        self.assertNotIn("Apply_Url", html)

    def test_markdown_field_labels_are_human_readable(self):
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
  - name: urgency_reason
  - name: rating
    values: [high, medium, low]
"""
        profile_config = report.parse_profile_config(profile)

        rendered = report.render_job(
            {
                "company": "Example Co",
                "role": "AI Engineer",
                "apply_url": "https://example.com/apply",
                "urgency_reason": "Fresh post.",
                "rating": "high",
            },
            1,
            profile_config,
        )

        self.assertIn("**Apply URL**", rendered)
        self.assertIn("**Urgency Reason**", rendered)
        self.assertNotIn("Apply_Url", rendered)
        self.assertNotIn("Urgency_Reason", rendered)

    def test_deepseek_key_gets_matching_default_endpoint_and_model(self):
        report = load_report_module(self)

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)

        self.assertEqual(base_url, report.DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(model, "deepseek-v4-flash")

    def test_minimax_token_plan_key_gets_china_endpoint_and_model(self):
        report = load_report_module(self)

        with patch.dict("os.environ", {"MINIMAX_TOKEN_PLAN_KEY": "sk-test"}, clear=True):
            base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)

        self.assertEqual(report.DEFAULT_MINIMAX_TOKEN_PLAN_BASE_URL, "https://api.minimaxi.com/v1")
        self.assertEqual(base_url, report.DEFAULT_MINIMAX_TOKEN_PLAN_BASE_URL)
        self.assertEqual(model, "MiniMax-M2.7")

    def test_minimax_platform_key_keeps_platform_endpoint(self):
        report = load_report_module(self)

        with patch.dict("os.environ", {"MINIMAX_API_KEY": "sk-test"}, clear=True):
            base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)

        self.assertEqual(base_url, report.DEFAULT_MINIMAX_BASE_URL)
        self.assertEqual(model, "MiniMax-M2.7")

    def test_minimax_region_cn_uses_china_endpoint(self):
        report = load_report_module(self)

        with patch.dict("os.environ", {"MINIMAX_API_KEY": "sk-test", "MINIMAX_REGION": "cn"}, clear=True):
            base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)

        self.assertEqual(base_url, report.DEFAULT_MINIMAX_CN_BASE_URL)
        self.assertEqual(model, "MiniMax-M2.7")

    def test_explicit_deepseek_model_gets_deepseek_endpoint_even_when_minimax_key_exists(self):
        report = load_report_module(self)

        with patch.dict(
            "os.environ",
            {"DEEPSEEK_API_KEY": "sk-deepseek", "MINIMAX_TOKEN_PLAN_KEY": "sk-minimax"},
            clear=True,
        ):
            base_url, model = report.resolve_llm_settings(None, "deepseek-v4-flash")

        self.assertEqual(base_url, report.DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(model, "deepseek-v4-flash")

    def test_deepseek_key_wins_default_when_no_openai_key_and_minimax_also_exists(self):
        report = load_report_module(self)

        with patch.dict(
            "os.environ",
            {"DEEPSEEK_API_KEY": "sk-deepseek", "MINIMAX_TOKEN_PLAN_KEY": "sk-minimax"},
            clear=True,
        ):
            base_url, model = report.resolve_llm_settings(None, report.DEFAULT_MODEL)

        self.assertEqual(base_url, report.DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(model, "deepseek-v4-flash")

    def test_extraction_prompt_keeps_profile_in_cacheable_prefix(self):
        report = load_report_module(self)

        system_prompt, user_prompt = report.build_extraction_prompts(
            sample_messages(),
            "# Job Profile\nRemote TypeScript roles only.",
            meta={"scan_started_at": "2026-05-08T08:00:00Z"},
            max_messages=10,
        )

        self.assertIn("=== CANDIDATE PROFILE ===", system_prompt)
        self.assertIn("Remote TypeScript roles only.", system_prompt)
        self.assertNotIn("=== CANDIDATE PROFILE ===", user_prompt)
        self.assertLess(user_prompt.index("=== SCAN METADATA ==="), user_prompt.index("=== UNTRUSTED TELEGRAM MESSAGES"))

    def test_deepseek_v4_extraction_disables_thinking_and_reports_cache_usage(self):
        report = load_report_module(self)
        captured: dict = {}

        class FakeUsage:
            def model_dump(self):
                return {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                    "prompt_cache_hit_tokens": 8,
                    "prompt_cache_miss_tokens": 2,
                }

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"jobs": []}'))],
                    usage=FakeUsage(),
                )

        class FakeOpenAI:
            def __init__(self, *, api_key, base_url):
                captured["api_key"] = api_key
                captured["base_url"] = base_url
                self.chat = SimpleNamespace(completions=FakeCompletions())

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}):
                result = report.extract_jobs_with_metadata(
                    messages=sample_messages()[:1],
                    profile="Senior TypeScript roles",
                    meta=None,
                    base_url=report.DEFAULT_DEEPSEEK_BASE_URL,
                    model="deepseek-v4-flash",
                    max_messages=10,
                )

        self.assertEqual(result.items, [])
        self.assertEqual(captured["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertEqual(captured["temperature"], 0)
        self.assertEqual(result.llm["provider"], "deepseek")
        self.assertEqual(result.llm["model"], "deepseek-v4-flash")
        self.assertEqual(result.llm["usage"]["prompt_cache_hit_tokens"], 8)
        self.assertEqual(result.llm["usage"]["prompt_cache_miss_tokens"], 2)
        self.assertIn("prompt_prefix_hash", result.llm)

    def test_minimax_m27_extraction_uses_minimax_key_and_provider_safe_request_shape(self):
        report = load_report_module(self)
        captured: dict = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"jobs": []}'))],
                    usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                )

        class FakeOpenAI:
            def __init__(self, *, api_key, base_url):
                captured["api_key"] = api_key
                captured["base_url"] = base_url
                self.chat = SimpleNamespace(completions=FakeCompletions())

        with patch.dict(
            "os.environ",
            {
                "DEEPSEEK_API_KEY": "sk-deepseek",
                "MINIMAX_TOKEN_PLAN_KEY": "sk-minimax",
            },
            clear=True,
        ):
            with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeOpenAI)}):
                base_url, model = report.resolve_llm_settings(None, "MiniMax-M2.7")
                result = report.extract_jobs_with_metadata(
                    messages=sample_messages()[:1],
                    profile="Senior TypeScript roles",
                    meta=None,
                    base_url=base_url,
                    model=model,
                    max_messages=10,
                    max_tokens=512,
                )

        self.assertEqual(result.items, [])
        self.assertEqual(captured["api_key"], "sk-minimax")
        self.assertEqual(captured["base_url"], report.DEFAULT_MINIMAX_CN_BASE_URL)
        self.assertEqual(captured["extra_body"], {"reasoning_split": True})
        self.assertGreater(captured["temperature"], 0)
        self.assertEqual(captured["max_completion_tokens"], 512)
        self.assertNotIn("max_tokens", captured)
        self.assertNotIn("response_format", captured)
        self.assertEqual(result.llm["provider"], "minimax")
        self.assertEqual(result.llm["thinking"], "split")

    def test_minimax_token_plan_key_takes_precedence_for_minimax_provider(self):
        report = load_report_module(self)

        with patch.dict(
            "os.environ",
            {
                "MINIMAX_API_KEY": "sk-general",
                "MINIMAX_TOKEN_PLAN_KEY": "sk-token-plan",
            },
            clear=True,
        ):
            key = report.api_key_for_provider("minimax")

        self.assertEqual(key, "sk-token-plan")

    def test_extraction_response_strips_minimax_thinking_block_before_json_parse(self):
        report = load_report_module(self)

        items = report.parse_extraction_response('<think>drafting</think>\n{"jobs": [{"rating": "high"}]}')

        self.assertEqual(items, [{"rating": "high"}])

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

            extraction = report.ExtractionResult(items=sample_extracted_jobs()[:1], llm={"provider": "openai"})
            with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=True):
                with patch.object(report, "extract_jobs_with_metadata", return_value=extraction) as extract_jobs:
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

    def test_json_output_includes_llm_metadata_from_extraction_result(self):
        report = load_report_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "scan_20260506_080000.jsonl"
            profile_path = root / "profile.md"
            input_path.write_text(
                json.dumps(sample_messages()[0], ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            profile_path.write_text("Senior Frontend Developer", encoding="utf-8")
            stdout = io.StringIO()

            def fake_extract_jobs(**kwargs):
                return report.ExtractionResult(
                    items=sample_extracted_jobs()[:1],
                    llm={
                        "provider": "deepseek",
                        "model": "deepseek-v4-flash",
                        "usage": {
                            "prompt_cache_hit_tokens": 80,
                            "prompt_cache_miss_tokens": 20,
                        },
                    },
                )

            with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
                with patch("sys.stdout", stdout):
                    exit_code = report.main(
                        [
                            "--input",
                            str(input_path),
                            "--profile",
                            str(profile_path),
                            "--format",
                            "json",
                        ],
                        extract_jobs_override=fake_extract_jobs,
                    )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["llm"]["provider"], "deepseek")
        self.assertEqual(payload["data"]["llm"]["usage"]["prompt_cache_hit_tokens"], 80)

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

    def test_report_main_state_dir_persists_seen_state_and_json_summary(self):
        report = load_report_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "scan.jsonl"
            profile_path = root / "profile.md"
            items_path = root / "items.json"
            output_path = root / "report.md"
            state_dir = root / ".tgcs" / "state"
            input_path.write_text(
                json.dumps(
                    {
                        "id": 101,
                        "channel": "cointelegraph",
                        "date": "2026-05-08T09:00:00+00:00",
                        "text": "Coinbase outage affects trading.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            input_path.with_suffix(".meta.json").write_text(
                json.dumps({"scan_date": "2026-05-08", "scan_window": "Last 24 hours"}),
                encoding="utf-8",
            )
            profile_path.write_text(
                """# Market Watch

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [topic, event]
fields:
  - name: topic
  - name: event
  - name: rating
    values: [high, medium, low]
  - name: why
""",
                encoding="utf-8",
            )
            items_path.write_text(
                json.dumps(
                    {
                        "schema_version": "semantic_items_v1",
                        "items": [
                            {
                                "source_message_refs": [{"channel": "cointelegraph", "id": 101}],
                                "topic": "Coinbase",
                                "event": "Exchange outage",
                                "rating": "high",
                                "why": "Decision-relevant operational risk.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout_first = io.StringIO()
            stdout_second = io.StringIO()

            with patch("sys.stdout", stdout_first):
                first_exit = report.main(
                    [
                        "--input",
                        str(input_path),
                        "--profile",
                        str(profile_path),
                        "--items-json",
                        str(items_path),
                        "--output",
                        str(output_path),
                        "--state-dir",
                        str(state_dir),
                        "--format",
                        "json",
                    ]
                )
            with patch("sys.stdout", stdout_second):
                second_exit = report.main(
                    [
                        "--input",
                        str(input_path),
                        "--profile",
                        str(profile_path),
                        "--items-json",
                        str(items_path),
                        "--output",
                        str(output_path),
                        "--state-dir",
                        str(state_dir),
                        "--format",
                        "json",
                    ]
                )

            first_payload = json.loads(stdout_first.getvalue())
            second_payload = json.loads(stdout_second.getvalue())
            state_text = (state_dir / "item-memory.json").read_text(encoding="utf-8")

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertEqual(first_payload["data"]["state_summary"]["new"], 1)
        self.assertEqual(first_payload["data"]["items"][0]["decision_state"]["status"], "new")
        self.assertEqual(second_payload["data"]["state_summary"]["seen"], 1)
        self.assertEqual(second_payload["data"]["items"][0]["decision_state"]["status"], "seen")
        self.assertNotIn("Coinbase outage affects trading", state_text)

    def test_report_main_state_read_only_does_not_write_memory_file(self):
        report = load_report_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "scan.jsonl"
            profile_path = root / "profile.md"
            items_path = root / "items.json"
            state_dir = root / ".tgcs" / "state"
            input_path.write_text(
                json.dumps(
                    {
                        "id": 101,
                        "channel": "cointelegraph",
                        "date": "2026-05-08T09:00:00+00:00",
                        "text": "Coinbase outage affects trading.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            profile_path.write_text(
                """# Market Watch

## Extraction Schema
mode: custom
top_level_key: items
dedup_fields: [topic, event]
fields:
  - name: topic
  - name: event
  - name: rating
    values: [high, medium, low]
  - name: why
""",
                encoding="utf-8",
            )
            items_path.write_text(
                json.dumps(
                    {
                        "schema_version": "semantic_items_v1",
                        "items": [
                            {
                                "source_message_refs": [{"channel": "cointelegraph", "id": 101}],
                                "topic": "Coinbase",
                                "event": "Exchange outage",
                                "rating": "high",
                                "why": "Decision-relevant operational risk.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with patch("sys.stdout", stdout):
                exit_code = report.main(
                    [
                        "--input",
                        str(input_path),
                        "--profile",
                        str(profile_path),
                        "--items-json",
                        str(items_path),
                        "--state-dir",
                        str(state_dir),
                        "--state-read-only",
                        "--format",
                        "json",
                    ]
                )
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["data"]["state_summary"]["new"], 1)
        self.assertFalse((state_dir / "item-memory.json").exists())

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
