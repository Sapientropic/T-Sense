import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { InboxView, nextNonEmptyReviewFilter } from "./inbox";
import { inboxFilterOptions } from "../domain/inbox";
import type { ReviewCard } from "../domain/types";

function card(overrides: Partial<ReviewCard> = {}): ReviewCard {
  return {
    schema_version: "review_card_v1",
    card_id: "card-1",
    profile_id: "jobs-fast",
    title: "Frontend Developer",
    rating: "high",
    decision_status: "new",
    opportunity_status: "open",
    opportunity_updated_at: "",
    source_refs: [{ channel: "javascript_jobs", id: 42 }],
    item: { why: "Remote React role with a clear salary range." },
    status: "pending",
    first_run_id: "run-1",
    last_run_id: "run-1",
    report_path: "reports/jobs.html",
    updated_at: "2026-05-11T01:42:00+08:00",
    ...overrides,
  };
}

describe("InboxView", () => {
  it("keeps the compact mobile filter control accessible", () => {
    const html = renderToStaticMarkup(
      <InboxView
        cards={[card()]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain('aria-label="Review filter: Latest action (1)"');
    expect(html).toContain("Latest");
    expect(html).toContain("Frontend Developer");
    expect(html).toContain("Applied");
    expect(html).toContain("Tune profile");
    expect(html).not.toContain("Prefer similar");
  });

  it("labels handled lifecycle cards without making them latest-action cards", () => {
    const filters = inboxFilterOptions(
      [
        card({
          card_id: "applied-role",
          opportunity_status: "applied",
          opportunity_updated_at: "2026-05-11T02:00:00Z",
        }),
      ],
      "run-1",
    );
    const html = renderToStaticMarkup(
      <InboxView
        cards={[
          card({
            card_id: "applied-role",
            opportunity_status: "applied",
            opportunity_updated_at: "2026-05-11T02:00:00Z",
          }),
        ]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(filters.find((item) => item.id === "actionable")?.count).toBe(0);
    expect(filters.find((item) => item.id === "handled")?.count).toBe(1);
    expect(html).toContain("Applied");
    expect(html).toContain("Show Handled 1");
  });

  it("moves from an empty latest-action filter to a visible backlog bucket", () => {
    const filters = inboxFilterOptions(
      [
        card({
          card_id: "old-high",
          first_run_id: "run-0",
          last_run_id: "run-0",
          rating: "high",
          decision_status: "seen",
        }),
        card({
          card_id: "old-medium",
          first_run_id: "run-0",
          last_run_id: "run-0",
          rating: "medium",
          decision_status: "seen",
        }),
      ],
      "run-1",
    );

    expect(filters.find((item) => item.id === "actionable")?.count).toBe(0);
    expect(nextNonEmptyReviewFilter(filters, "actionable")).toBe("high");
  });

  it("turns an empty latest-action view into a visible backlog jump", () => {
    const html = renderToStaticMarkup(
      <InboxView
        cards={[
          card({
            card_id: "old-high",
            first_run_id: "run-0",
            last_run_id: "run-0",
            rating: "high",
            decision_status: "seen",
          }),
        ]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain("No latest action cards");
    expect(html).toContain("Show High 1");
  });
});
