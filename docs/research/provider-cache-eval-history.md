# Provider And Cache Eval History

**Status**: historical research artifact moved out of the public v0.5 product
contract on 2026-05-10.

Use this file for provider/cache evidence and local smoke history. The current
product boundary remains in `../v0.5-alpha-alert-review-inbox.md`.

## 2026-05-09 Prompt Payload Smoke

Input:

- `output/runs/run_20260509T122524Z_a85fdfaa/prefiltered-scan.jsonl`

After removing the full scan sidecar/debug fields from the LLM prompt, DeepSeek
Flash prompt tokens dropped from 29,107 in the original monitor run to 17,192
in a same-input report rerun. Latency dropped from 27.9s to 13.6s; cache hit
rate rose from 1.76% to 6.7%.

This does not prove warm-cache steady state, but it does prove the production
prompt no longer pays for source-health diagnostics inside the provider
request.

## 2026-05-09 Endpoint Smoke

External endpoint check on 2026-05-09:

- MiniMax official docs list `https://api.minimax.io/v1` for the
  OpenAI-compatible protocol.
- China-region Codex CLI setup uses `https://api.minimaxi.com/v1`.

The local MiniMax Token Plan key failed with `invalid_api_key` on the official
international endpoint but succeeded on the official China endpoint. The code
now defaults `MINIMAX_TOKEN_PLAN_KEY` to `https://api.minimaxi.com/v1`; use
`MINIMAX_BASE_URL` only when an account needs an explicit override.

[⚠️ 需确认] Endpoint behavior and provider pricing/cache behavior may change and
must be rechecked against official docs before shipping provider-specific flags.

## 2026-05-09 Local Eval Snapshot

Artifacts:

- `output/evals/deepseek-cache-matrix-20260508T202844Z.json`
- `output/evals/deepseek-cache-matrix-20260508T204000Z.json`
- `output/evals/deepseek-cache-matrix-20260508T210926Z.json`
- `output/evals/deepseek-cache-matrix-20260508T212706Z.json`
- `output/evals/deepseek-cache-matrix-20260508T212724Z.json`
- `output/evals/deepseek-cache-matrix-20260508T212743Z.json`
- `output/evals/deepseek-cache-matrix-20260508T212926Z.json`
- `output/evals/deepseek-cache-matrix-20260508T213021Z.json`
- `output/evals/deepseek-cache-matrix-20260509T044525Z.json`
- `output/evals/deepseek-cache-matrix-20260509T044552Z.json`
- `output/evals/deepseek-cache-matrix-20260509T055155Z.json`
- `output/evals/deepseek-cache-matrix-20260509T070836Z.json`

| Scenario | Model | Sample | Max tokens | JSON OK | Cached hit | Avg latency | Avg cached | Avg completion | Items |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| optimized prompt | deepseek-v4-flash | 10 | none | 3/3 | 98.77% | 0.72s | 0.65s | 7 | 0 |
| optimized prompt | deepseek-v4-flash | 20 | 2000 | 3/3 | 99.63% | 7.84s | 7.68s | 648 | 3 |
| optimized prompt | deepseek-v4-flash | 30 | 2000 | 3/3 | 99.35% | 18.39s | 18.72s | 1625 | 8 |
| optimized prompt | deepseek-v4-pro | 20 | 2000 | 3/3 | 99.63% | 14.63s | 14.51s | 496 | 2 |
| optimized prompt | deepseek-v4-pro | 30 | 2000 | 3/3 | 99.35% | 19.93s | 20.95s | 728 | 3 |
| output cap too low | deepseek-v4-flash | 30 | 1200 | 0/3 | n/a | n/a | n/a | n/a | n/a |
| provider smoke | deepseek-v4-flash | 5 | 1000 | 1/1 | 96.56% | 0.78s | n/a | [⚠️ 需确认] | [⚠️ 需确认] |
| provider smoke | MiniMax-M2.7, international endpoint | 5 | 1000 | 0/1 | n/a | n/a | n/a | n/a | n/a |
| provider smoke | MiniMax-M2.7, China endpoint | 5 | 1000 | 1/1 | 0% | 6.59-6.94s | n/a | 340 | 0 |
| provider compare | deepseek-v4-flash | 5 | 1000 | 1/1 | 96.56% | 0.70s | n/a | 7 | 0 |
| provider compare | MiniMax-M2.7, China endpoint | 5 | 1000 | 1/1 | 0% | 14.44s | n/a | 729 | 0 |
| provider smoke after Developer Opportunity profile | deepseek-v4-flash | 5 | 1000 | 1/1 | 0% | 1.02s | n/a | 7 | 0 |
| provider smoke after Developer Opportunity profile | MiniMax-M2.7, international endpoint | 5 | 1000 | 0/1 | n/a | n/a | n/a | n/a | n/a |
| provider smoke after Developer Opportunity profile | MiniMax-M2.7, China endpoint | 5 | 1000 | 1/1 | 0% | 11.14s | n/a | 360 | 0 |
| provider smoke after Token Plan default switch | MiniMax-M2.7, China endpoint | 3 | 1000 | 1/1 | 0% | 8.16s | n/a | 183 | 0 |
| provider compare after opportunity-summary polish | deepseek-v4-flash | 10 | 2000 | 1/1 | 0% | 10.80s | n/a | 663 | 3 |
| provider compare after opportunity-summary polish | MiniMax-M2.7, China endpoint | 10 | 2000 | 1/1 | 0% | 7.10s | n/a | 313 | 0 |
| provider compare after source-yield/profile-diff polish | deepseek-v4-flash | 5 | 1000 | 1/1 | 0% | 10.90s | n/a | 592 | 3, including 1 high |
| provider compare after source-yield/profile-diff polish | MiniMax-M2.7, China endpoint via `MINIMAX_TOKEN_PLAN_KEY` | 5 | 1000 | 1/1 | 0% | 19.40s | n/a | 861 | 2, 0 high |

Recommendation from this snapshot:

- Keep Flash as the default high-frequency extractor.
- Keep fast-lane batches around 20 messages.
- Set the output cap to 2000 tokens rather than 1200.
- Reserve Pro for fallback or periodic review; within this local sample it was
  more conservative but not clearly better for interrupt routing, and was
  usually slower.
- Treat cache as useful for input cost, while remembering that output tokens
  still dominate latency when the model emits several structured items.

[⚠️ 需确认] This history did not contain a labeled high-value job lead, so true
recall on urgent opportunities still needs live review.

The 2026-05-09 10-message comparison did not change the default route: MiniMax
M2.7 was faster and used fewer completion tokens on that run, but returned zero
items while DeepSeek Flash returned three. Keep MiniMax available for explicit
comparison/fallback until live labeled opportunity data proves its recall is
sufficient.

The later 2026-05-09 five-message Token Plan comparison also supports the same
default: DeepSeek Flash returned more items, found one high item, used fewer
completion tokens, and was faster than MiniMax M2.7 on that small sample.

[⚠️ 需确认] This remains a provider-routing smoke rather than a stable recall
benchmark because it uses only five local messages and no independently labeled
ground truth.

## Source Metadata Reuse Ideas

Scan metadata is now reused in the Source Yield panel through source-level
`raw_count`, `kept_count`, latest-card counts, and card yield. Further reuse
should focus on:

- dynamic channel cadence: scan valuable channels more often and dormant/noisy
  channels less often;
- channel pruning candidates: surface channels with repeated raw messages but
  no high or medium items;
- keyword evolution: propose added/removed prefilter terms from false positives,
  misses, and matched keyword counts;
- budget allocation: spend semantic extraction only on profiles/channels with
  recent yield;
- freshness monitoring: detect channels whose newest message is lagging or
  whose high-value posts arrive outside the current alert window;
- source-health alerts: distinguish access failures, incomplete scans, OCR
  volume, and empty channels from true low value.
