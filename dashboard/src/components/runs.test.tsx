import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import {
  RunsView,
  buildCompactRunTimeline,
  buildRunEvidenceClusters,
  buildRunEvidenceGroups,
  buildRunHealthDecision,
  buildRunOutcome,
  runCountScaleMax,
} from "./runs";
import type { Run } from "../domain/types";

function run(overrides: Partial<Run>): Run {
  return {
    run_id: "run-1",
    profile_id: "jobs-fast",
    status: "complete",
    started_at: "2026-05-10T00:00:00Z",
    ...overrides,
  };
}

describe("run health decision", () => {
  it("prioritizes failed runs over card volume", () => {
    expect(buildRunHealthDecision([
      run({ run_id: "run-1", review_card_count: 8, alert_count: 3, started_at: "2026-05-10T08:00:00Z" }),
      run({ run_id: "run-2", status: "failed", review_card_count: 4, alert_count: 2, started_at: "2026-05-10T12:00:00Z" }),
    ])).toMatchObject({
      tone: "danger",
      headline: "Fix failed scans",
    });
  });

  it("does not keep the main health card red after a newer successful scan", () => {
    expect(buildRunHealthDecision([
      run({ run_id: "run-1", status: "failed", review_card_count: 0, alert_count: 0, started_at: "2026-05-09T08:00:00Z" }),
      run({ run_id: "run-2", status: "complete", review_card_count: 5, alert_count: 1, started_at: "2026-05-11T12:00:00Z" }),
    ])).toMatchObject({
      tone: "info",
      headline: "Review 1 alert candidate",
    });
  });

  it("turns diagnostics into a concrete next action", () => {
    expect(buildRunHealthDecision([
      run({
        quality: {
          diagnostic_count: 1,
          diagnostic_warning_count: 1,
          top_diagnostic_code: "llm_unavailable",
        },
      }),
    ])).toMatchObject({
      tone: "warn",
      headline: "Diagnostics need attention",
      detail: "Next: check LLM key",
    });
  });

  it("promotes Review when alert candidates exist", () => {
    expect(buildRunHealthDecision([
      run({ review_card_count: 5, alert_count: 2 }),
    ])).toMatchObject({
      tone: "info",
      headline: "Review 2 alert candidates",
    });
  });

  it("does not turn default-off OCR into a red or yellow run-health warning", () => {
    expect(buildRunHealthDecision([
      run({
        review_card_count: 4,
        alert_count: 1,
        quality: { diagnostic_count: 1, diagnostic_warning_count: 1, top_diagnostic_code: "ocr_disabled_media_present" },
      }),
    ])).toMatchObject({
      tone: "info",
      headline: "Review 1 alert candidate",
    });
  });

  it("labels rows by outcome instead of repeating profile and date", () => {
    expect(buildRunOutcome(run({ review_card_count: 4, alert_count: 0 }))).toMatchObject({
      tone: "info",
      title: "4 review cards",
    });
    expect(buildRunOutcome(run({ status: "failed", review_card_count: 4 }))).toMatchObject({
      tone: "danger",
      title: "Failed scan",
    });
  });

  it("groups recent evidence into attention, review, and clean bands", () => {
    const groups = buildRunEvidenceGroups([
      run({ run_id: "run-1", status: "failed" }),
      run({ run_id: "run-2", review_card_count: 2 }),
      run({ run_id: "run-3", review_card_count: 0, alert_count: 0 }),
    ]);
    expect(groups.map((group) => group.key)).toEqual(["attention", "review", "clean"]);
    expect(groups[0].title).toBe("Earlier failed scans");
    expect(groups[1].detail).toBe("2 cards / 0 alerts");
  });

  it("clusters repeated same-day run outcomes into one evidence row", () => {
    const clusters = buildRunEvidenceClusters([
      run({ run_id: "run-1", review_card_count: 3, started_at: "2026-05-10T12:00:00Z" }),
      run({ run_id: "run-2", review_card_count: 5, started_at: "2026-05-10T08:00:00Z" }),
      run({ run_id: "run-3", status: "failed", started_at: "2026-05-10T07:00:00Z" }),
    ]);
    expect(clusters).toHaveLength(2);
    expect(clusters[0]).toMatchObject({ cards: 8, alerts: 0 });
    expect(clusters[0].runs.map((item) => item.run_id)).toEqual(["run-1", "run-2"]);
  });

  it("keeps diagnostic titles ahead of aggregate alert volume", () => {
    const clusters = buildRunEvidenceClusters([
      run({
        run_id: "run-1",
        review_card_count: 3,
        alert_count: 1,
        quality: { diagnostic_count: 1, diagnostic_warning_count: 1, top_diagnostic_code: "ocr_disabled_media_present" },
      }),
      run({
        run_id: "run-2",
        review_card_count: 5,
        alert_count: 3,
        quality: { diagnostic_count: 1, diagnostic_warning_count: 1, top_diagnostic_code: "ocr_disabled_media_present" },
      }),
    ]);
    expect(clusters).toHaveLength(1);
    expect(clusters[0].outcome.title).toBe("OCR optional");
    expect(clusters[0].outcome.tone).toBe("info");
  });

  it("does not escalate info-only diagnostics into the attention group", () => {
    const groups = buildRunEvidenceGroups([
      run({
        run_id: "run-1",
        quality: { diagnostic_count: 1, diagnostic_info_count: 1, top_diagnostic_code: "missing_scan_metadata" },
      }),
    ]);
    expect(buildRunOutcome(groups[0].runs[0])).toMatchObject({ tone: "info" });
    expect(groups.map((group) => group.key)).toEqual(["clean"]);
  });

  it("keeps the mobile timeline daily while compacting each day", () => {
    const timeline = buildCompactRunTimeline([
      { key: "2026-05-04", label: "05-04", runs: 0, complete: 0, failed: 0, cards: 0, alerts: 0 },
      { key: "2026-05-05", label: "05-05", runs: 1, complete: 1, failed: 0, cards: 0, alerts: 0 },
      { key: "2026-05-06", label: "05-06", runs: 1, complete: 1, failed: 0, cards: 3, alerts: 1 },
      { key: "2026-05-07", label: "05-07", runs: 0, complete: 0, failed: 0, cards: 0, alerts: 0 },
      { key: "2026-05-08", label: "05-08", runs: 1, complete: 0, failed: 1, cards: 0, alerts: 0 },
      { key: "2026-05-09", label: "05-09", runs: 1, complete: 1, failed: 0, cards: 0, alerts: 0 },
      { key: "2026-05-10", label: "05-10", runs: 0, complete: 0, failed: 0, cards: 0, alerts: 0 },
    ]);
    expect(timeline).toHaveLength(7);
    expect(timeline.map((item) => item.label)).toEqual(["05-04", "05-05", "05-06", "05-07", "05-08", "05-09", "05-10"]);
    expect(timeline[0]).toMatchObject({ value: "", detail: "no scans" });
    expect(timeline[4]).toMatchObject({ tone: "warn", value: "1 fail" });
  });

  it("uses one count scale across visible run clusters", () => {
    expect(runCountScaleMax([
      { cards: 2, alerts: 1 },
      { cards: 20, alerts: 10 },
    ])).toBe(20);
    expect(runCountScaleMax([])).toBe(1);
  });

  it("gives empty run history direct app actions", () => {
    const html = renderToStaticMarkup(<RunsView runs={[]} onRunDeskAction={() => undefined} />);

    expect(html).toContain("Run first scan");
    expect(html).toContain("Check setup");
    expect(html).not.toContain("Run history is empty in this database.");
  });
});
