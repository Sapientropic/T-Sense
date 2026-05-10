import { describe, expect, it } from "vitest";

import {
  alertMode,
  artifactDisplayName,
  artifactFormatFromPath,
  artifactHref,
  artifactShortDetail,
  artifactShortLabel,
  buildProfileReportNames,
  deliveryTargetDetail,
  deliveryTargetName,
  diagnosticTone,
  diffStats,
  feedbackImpactKey,
  formatActionLabel,
  formatGitRemoteState,
  metricShortLabel,
  opportunityDetail,
  opportunityHeadline,
  opportunityTone,
  percentWidth,
  ratio,
  reportProfileName,
  runDisplayDetail,
  runDisplayTitle,
  sourceHeatClass,
  sourceSignalScore,
  toneClass,
} from "./display";
import type { SourceStat } from "./types";

function source(overrides: Partial<SourceStat> = {}): SourceStat {
  return {
    channel: "jobs",
    card_count: 0,
    high_count: 0,
    medium_count: 0,
    low_count: 0,
    pending_count: 0,
    handled_count: 0,
    false_positive_count: 0,
    alert_count: 0,
    high_rate: 0,
    ...overrides,
  };
}

describe("dashboard display helpers", () => {
  it("formats CSS-safe tone classes and report names", () => {
    expect(toneClass("Needs Review!")).toBe("needs-review-");
    const names = buildProfileReportNames([
      { profile_id: "jobs-fast", display_name: "Jobs Fast", enabled: true, updated_at: "2026-05-09T00:00:00Z" },
    ]);
    expect(reportProfileName("jobs-fast", names)).toBe("Jobs Fast");
  });

  it("formats delivery targets without view dependencies", () => {
    expect(
      deliveryTargetName({
        target_id: "tg",
        type: "telegram_bot",
        enabled: true,
        config: { chat_id: "123" },
        updated_at: "2026-05-09T00:00:00Z",
      }),
    ).toBe("Telegram Bot");
    expect(
      deliveryTargetDetail({
        target_id: "tg",
        type: "telegram_bot",
        enabled: true,
        config: {},
        updated_at: "2026-05-09T00:00:00Z",
      }),
    ).toBe("Live target not connected");
  });

  it("formats run artifact links and labels", () => {
    const run = { run_id: "run-1", profile_id: "jobs-fast", status: "complete", started_at: "2026-05-09T08:00:00+08:00" };
    const artifact = { path: "reports/jobs fast.html", category: "daily_report" };
    expect(runDisplayTitle(run)).toBe("Jobs Fast · 05-09");
    expect(runDisplayTitle({ ...run, display_name: "Evening sweep" })).toBe("Evening sweep · 05-09");
    expect(runDisplayDetail(run)).toBe("08:00");
    expect(artifactHref(artifact.path)).toBe("/artifacts/reports%2Fjobs%20fast.html");
    expect(artifactFormatFromPath(artifact.path)).toBe("HTML");
    expect(artifactDisplayName(artifact, run)).toBe("Jobs Fast Signal Report");
    expect(artifactShortLabel(artifact)).toBe("Report");
    expect(artifactShortDetail(artifact, run)).toBe("HTML · 05-09 08:00");
  });

  it("formats git remote state", () => {
    const gitStatus = {
      schema_version: "git_update_status_v1" as const,
      status: "up_to_date",
      message: "",
      branch: "main",
      ahead: 0,
      behind: 0,
      dirty: false,
      dirty_count: 0,
      pull_allowed: true,
      checked_at: "2026-05-09T08:00:00+08:00",
    };
    expect(formatGitRemoteState(null)).toBe("unchecked");
    expect(formatGitRemoteState(gitStatus)).toBe("up to date");
    expect(
      formatGitRemoteState({
        ...gitStatus,
        schema_version: "git_update_status_v1",
        dirty: true,
        dirty_count: 2,
      }),
    ).toBe("dirty 2");
  });

  it("formats opportunity and run diagnostic display state", () => {
    expect(opportunityTone({ status: "failed" })).toBe("blocked");
    expect(opportunityHeadline({ diagnostics: { failure_count: 1, top_code: "scan_failed" } })).toBe("Source check needed");
    expect(opportunityDetail({ diagnostics: { failure_count: 1, top_code: "scan_failed" } })).toBe("Scan failed");
    expect(opportunityHeadline({ high_actionable_count: 2 })).toBe("2 action signals");
    expect(opportunityHeadline({ all_clear: true })).toBe("All Clear");
    expect(opportunityDetail({ matched_count: 3, scanned_count: 9 })).toBe("3/9 matched");
    expect(diagnosticTone({ diagnostic_failure_count: 1 })).toBe("diagnostic-pill danger");
    expect(diagnosticTone({ diagnostic_warning_count: 1 })).toBe("diagnostic-pill warn");
    expect(diagnosticTone({ diagnostic_count: 1 })).toBe("diagnostic-pill info");
    expect(diagnosticTone()).toBe("diagnostic-pill ok");
  });

  it("formats profile alert mode and diff stats", () => {
    expect(alertMode({ profile_id: "jobs", enabled: true, updated_at: "2026-05-09", alert_schedule_mode: "muted" })).toBe("muted");
    expect(alertMode({ profile_id: "jobs", enabled: true, updated_at: "2026-05-09" })).toBe("work_hours");
    expect(diffStats(" a\n+new\n+++ file\n-old\n--- file")).toEqual({ added: 1, removed: 1 });
  });

  it("formats shared meter and source display helpers", () => {
    expect(percentWidth(0.664)).toBe("66%");
    expect(percentWidth(2)).toBe("100%");
    expect(percentWidth(Number.NaN)).toBe("0%");
    expect(ratio(2, 4)).toBe(0.5);
    expect(ratio(2, 0)).toBe(0);
    expect(metricShortLabel("Card yield")).toBe("yield");
    expect(metricShortLabel("High-rate")).toBe("high");
    expect(formatActionLabel("false_positive")).toBe("false positive");
    expect(sourceHeatClass(source({ card_count: 1 }))).toBe("warm");
    expect(sourceSignalScore(source({ card_count: 1, high_count: 5, high_rate: 1 }))).toBe(1);
  });

  it("scores source heat by the strongest visible signal", () => {
    expect(sourceSignalScore(source())).toBe(0);
    expect(sourceSignalScore(source({ card_yield_rate: 0.42 }))).toBe(0.42);
    expect(sourceSignalScore(source({ latest_card_count: 2 }))).toBe(0.375);
    expect(sourceSignalScore(source({ high_count: 2, latest_card_count: 1, card_yield_rate: 0.15 }))).toBe(0.4);
    expect(sourceSignalScore(source({ high_count: 99, latest_card_count: 99, card_yield_rate: 99 }))).toBe(1);
    expect(sourceSignalScore(source({ high_count: Number.NaN, latest_card_count: Number.NaN, card_yield_rate: Number.NaN }))).toBe(0);
    expect(sourceSignalScore(source({ high_count: Infinity, latest_card_count: Infinity, card_yield_rate: Infinity }))).toBe(0);
  });

  it("builds stable feedback impact keys with an index fallback", () => {
    expect(feedbackImpactKey({ created_at: "2026-05-09", action: "keep", item_title: "Role" }, 2)).toBe("2026-05-09-keep-Role-2");
    expect(feedbackImpactKey({}, 3)).toBe("3");
  });
});
