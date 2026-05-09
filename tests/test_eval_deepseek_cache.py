import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_eval_module(testcase):
    try:
        from scripts import eval_deepseek_cache
    except ImportError as exc:
        testcase.fail(f"scripts.eval_deepseek_cache should exist: {exc}")
    return eval_deepseek_cache


class DeepSeekCacheEvalTests(unittest.TestCase):
    def test_eval_payload_summarizes_usage_without_raw_message_text(self):
        evaluator = load_eval_module(self)

        messages = [
            {
                "id": 1,
                "channel": "jobs",
                "date": "2026-05-08T08:30:00Z",
                "text": "We are hiring a TypeScript engineer. Contact @hr.",
            }
        ]
        runs = [
            {
                "label": "warmup",
                "status": "ok",
                "latency_ms": 1000,
                "item_count": 1,
                "high_count": 1,
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": 100,
                },
            },
            {
                "label": "cached",
                "status": "ok",
                "latency_ms": 600,
                "item_count": 1,
                "high_count": 1,
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_cache_hit_tokens": 80,
                    "prompt_cache_miss_tokens": 20,
                },
            },
        ]

        payload = evaluator.build_eval_payload(
            input_paths=[Path("scan.jsonl")],
            selected_messages=messages,
            runs=runs,
            model="deepseek-v4-flash",
            provider="deepseek",
            base_url="https://api.deepseek.com",
            max_tokens=2000,
            profile_path=Path("profiles/templates/jobs.md"),
            prefilter_keywords=["hiring"],
        )
        text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["aggregate"]["cache_hit_rate"], 0.4)
        self.assertEqual(payload["aggregate"]["cached_cache_hit_rate"], 0.8)
        self.assertEqual(payload["aggregate"]["warmup_latency_ms"], 1000)
        self.assertEqual(payload["aggregate"]["avg_cached_latency_ms"], 600)
        self.assertEqual(payload["aggregate"]["message_count"], 1)
        self.assertEqual(payload["provider"], "deepseek")
        self.assertEqual(payload["base_url"], "https://api.deepseek.com")
        self.assertEqual(payload["max_tokens"], 2000)
        self.assertEqual(payload["prefilter"]["source_count"], 1)
        self.assertEqual(payload["prefilter"]["top_sources"], [{"channel": "jobs", "message_count": 1}])
        self.assertEqual(payload["runs"][1]["usage"]["prompt_cache_hit_tokens"], 80)
        self.assertNotIn("We are hiring", text)
        self.assertNotIn("@hr", text)

    def test_matrix_payload_summarizes_entries_without_raw_message_text(self):
        evaluator = load_eval_module(self)

        entry = evaluator.build_eval_payload(
            input_paths=[Path("scan.jsonl")],
            selected_messages=[
                {
                    "id": 1,
                    "channel": "jobs",
                    "date": "2026-05-08T08:30:00Z",
                    "text": "We are hiring a TypeScript engineer. Contact @hr.",
                }
            ],
            runs=[
                {
                    "label": "warmup",
                    "status": "ok",
                    "latency_ms": 1000,
                    "item_count": 1,
                    "high_count": 1,
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "prompt_cache_hit_tokens": 0,
                        "prompt_cache_miss_tokens": 100,
                    },
                }
            ],
            model="deepseek-v4-flash",
            provider="deepseek",
            base_url="https://api.deepseek.com",
            max_tokens=2000,
            profile_path=Path("profiles/templates/jobs.md"),
            prefilter_keywords=["hiring"],
        )

        payload = evaluator.build_matrix_payload(
            input_paths=[Path("scan.jsonl")],
            entries=[entry],
            profile_path=Path("profiles/templates/jobs.md"),
            prefilter_keywords=["hiring"],
        )
        text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["schema_version"], "deepseek_cache_eval_matrix_v1")
        self.assertEqual(payload["aggregate"]["entry_count"], 1)
        self.assertEqual(payload["matrix"][0]["model"], "deepseek-v4-flash")
        self.assertEqual(payload["matrix"][0]["provider"], "deepseek")
        self.assertEqual(payload["matrix"][0]["base_url"], "https://api.deepseek.com")
        self.assertEqual(payload["matrix"][0]["max_tokens"], 2000)
        self.assertEqual(payload["matrix"][0]["sample_size"], 1)
        self.assertNotIn("We are hiring", text)
        self.assertNotIn("@hr", text)

    def test_collect_eval_entry_resolves_minimax_provider_metadata_without_raw_text(self):
        evaluator = load_eval_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = str(Path(tmp))
            scan = Path(tmp) / "scan.jsonl"
            scan.write_text(
                json.dumps(
                    {
                        "id": 1,
                        "channel": "jobs",
                        "date": "2026-05-08T08:30:00Z",
                        "text": "We are hiring a TypeScript engineer. Contact @hr.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_extract_jobs_with_metadata(**kwargs):
                return evaluator.report.ExtractionResult(
                    items=[{"rating": "high"}],
                    llm={
                        "provider": "minimax",
                        "model": "MiniMax-M2.7",
                        "base_url": evaluator.report.DEFAULT_MINIMAX_TOKEN_PLAN_BASE_URL,
                        "latency_ms": 900,
                        "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
                    },
                )

            with patch.dict("os.environ", {"MINIMAX_TOKEN_PLAN_KEY": "sk-test"}, clear=True):
                with patch.object(
                    evaluator.report,
                    "extract_jobs_with_metadata",
                    side_effect=fake_extract_jobs_with_metadata,
                ):
                    entry = evaluator.collect_eval_entry(
                        input_paths=[scan],
                        profile_path=Path("profiles/templates/jobs.md"),
                        profile_text="# Jobs",
                        keywords=["hiring"],
                        sample_size=1,
                        repeat=1,
                        base_url_arg=None,
                        model_arg="MiniMax-M2.7",
                        max_tokens=2000,
                    )

        text = json.dumps(entry, ensure_ascii=False)

        self.assertIsNotNone(entry)
        self.assertEqual(entry["provider"], "minimax")
        self.assertEqual(entry["base_url"], evaluator.report.DEFAULT_MINIMAX_CN_BASE_URL)
        self.assertEqual(entry["max_tokens"], 2000)
        self.assertEqual(entry["input_paths"], ["scan.jsonl"])
        self.assertNotIn("We are hiring", text)
        self.assertNotIn("@hr", text)
        self.assertNotIn(tmp_root, text)

    def test_matrix_payload_disambiguates_external_input_basenames(self):
        evaluator = load_eval_module(self)

        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            left_scan = Path(left) / "scan.jsonl"
            right_scan = Path(right) / "scan.jsonl"
            payload = evaluator.build_matrix_payload(
                input_paths=[left_scan, right_scan],
                entries=[],
                profile_path=Path("profiles/templates/jobs.md"),
                prefilter_keywords=[],
            )

        self.assertEqual(len(payload["input_paths"]), 2)
        self.assertNotEqual(payload["input_paths"][0], payload["input_paths"][1])
        self.assertTrue(all(path.startswith("scan-") and path.endswith(".jsonl") for path in payload["input_paths"]))
        self.assertNotIn(left, json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(right, json.dumps(payload, ensure_ascii=False))

    def test_write_eval_payload_creates_parent_directory(self):
        evaluator = load_eval_module(self)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "nested" / "eval.json"
            evaluator.write_eval_payload(output, {"ok": True})
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
