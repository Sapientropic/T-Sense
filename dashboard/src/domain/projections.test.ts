import { describe, expect, it } from "vitest";

import {
  buildBoardMeta,
  buildMetrics,
  buildTabCounts,
  formatRunDiagnosticAction,
  formatRunDiagnostics,
  formatRunQuality,
  hasBlockingOpportunitySummary,
  runBucketSignalScore,
  runDayBuckets,
  runDayWindowBuckets,
  runHealthDetail,
  settingsActionCount,
} from "./projections";
import { emptyDashboardState } from "./sanitize";
import type { DashboardState, Run } from "./types";

function state(overrides: Partial<DashboardState>): DashboardState {
  return { ...emptyDashboardState, ...overrides };
}

describe("dashboard projections", () => {
  it("builds shell metrics and tab counts from dashboard state", () => {
    const dashboard = state({
      profiles: [{ profile_id: "jobs-fast", enabled: true, updated_at: "2026-05-09T00:00:00Z" }],
      runs: [{ run_id: "run-1", profile_id: "jobs-fast", status: "complete", started_at: "2026-05-09T00:00:00Z", alert_count: 2 }],
      delivery_targets: [
        {
          schema_version: "delivery_target_v1",
          target_id: "tg",
          type: "telegram_bot",
          enabled: true,
          config: {},
          updated_at: "2026-05-09T00:00:00Z",
        },
      ],
      profile_patch_suggestions: [{ patch_id: "p1", profile_id: "jobs-fast", note: "x", status: "pending", diff_text: "+x", created_at: "2026-05-09T00:00:00Z" }],
      source_stats: [{ channel: "jobs", card_count: 4, high_count: 2, medium_count: 1, low_count: 1, pending_count: 1, handled_count: 3, false_positive_count: 0, alert_count: 1, high_rate: 0.5 }],
      source_insights: [{ kind: "promote", channel: "jobs", label: "Promote", reason: "Good", priority: 1, stats: { channel: "jobs", card_count: 4, high_count: 2, medium_count: 1, low_count: 1, pending_count: 1, handled_count: 3, false_positive_count: 0, alert_count: 1, high_rate: 0.5 } }],
      feedback_summary: { exportable_count: 3, pending_profile_diff_count: 1 },
    });
    expect(buildMetrics(dashboard).map((metric) => metric.label)).toEqual(["Runs", "Alerts", "Profiles", "Sources"]);
    expect(buildTabCounts(dashboard, 8)).toEqual({ inbox: 0, actions: 8, profiles: 1, runs: 1, settings: 5 });
    expect(buildBoardMeta("actions", dashboard, 8).title).toBe("Start");
    expect(buildBoardMeta("settings", dashboard).title).toBe("Settings");
    expect(settingsActionCount(dashboard)).toBe(5);
  });

  it("builds a fixed run-day window with empty days preserved", () => {
    const runs: Run[] = [
      { run_id: "run-1", profile_id: "jobs-fast", status: "complete", started_at: "2026-05-07T00:00:00Z", review_card_count: 2, alert_count: 1 },
      { run_id: "run-2", profile_id: "jobs-fast", status: "failed", started_at: "2026-05-09T00:00:00Z", review_card_count: 0, alert_count: 0 },
    ];
    expect(runDayBuckets(runs).map((bucket) => bucket.key)).toEqual(["2026-05-07", "2026-05-09"]);
    const buckets = runDayWindowBuckets(runs, 3);
    expect(buckets.map((bucket) => bucket.key)).toEqual(["2026-05-07", "2026-05-08", "2026-05-09"]);
    expect(buckets.map((bucket) => bucket.runs)).toEqual([1, 0, 1]);
    expect(runBucketSignalScore({ ...buckets[0], cards: 8, alerts: 0 })).toBe(0.5);
    expect(runBucketSignalScore({ ...buckets[1], cards: 0, alerts: 0 })).toBe(0);
  });

  it("formats run quality and diagnostics without UI dependencies", () => {
    expect(formatRunQuality()).toBe("Quality not recorded");
    expect(formatRunQuality({ llm_provider: "deepseek", cache_hit_rate: 0.42, latency_ms: 1200 })).toBe("deepseek / 42% cache / 1200ms");
    expect(formatRunDiagnostics({ diagnostic_count: 1, top_diagnostic_code: "channel_failures" })).toBe("Source access failed");
    expect(formatRunDiagnosticAction({ diagnostic_count: 1, top_diagnostic_code: "llm_unavailable" })).toBe("Next: check LLM key");
    expect(formatRunDiagnosticAction({ diagnostic_count: 1, top_diagnostic_code: "llm_output_truncated" })).toBe("Next: raise semantic limits or narrow scope");
    expect(formatRunDiagnosticAction({ diagnostic_count: 1, top_diagnostic_code: "source_access_failed" })).toBe("Next: fix source access");
    expect(runHealthDetail({ diagnostic_count: 1, top_diagnostic_code: "scan_incomplete" })).toBe("Semantic stage not recorded · Next: inspect incomplete sources");
  });

  it("keeps blocking latest-run summaries visible even when the inbox has action cards", () => {
    expect(hasBlockingOpportunitySummary({ status: "failed" })).toBe(true);
    expect(hasBlockingOpportunitySummary({ diagnostics: { failure_count: 1 } })).toBe(true);
    expect(hasBlockingOpportunitySummary({ status: "ready", diagnostics: { failure_count: 0 } })).toBe(false);
  });
});
