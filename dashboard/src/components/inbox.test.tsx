import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { InboxView, nextNonEmptyReviewFilter } from "./inbox";
import { inboxFilterOptions } from "../domain/inbox";
import type { DashboardState, ReviewCard } from "../domain/types";

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

  it("keeps open opportunity actions and profile tuning entry visible", () => {
    const html = renderToStaticMarkup(
      <InboxView
        cards={[card()]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain('data-review-action="applied"');
    expect(html).toContain('data-review-action="saved"');
    expect(html).toContain('data-review-action="contacted"');
    expect(html).toContain('data-review-action="dismissed"');
    expect(html).toContain('data-review-action="duplicate"');
    expect(html).toContain('data-review-action="tune"');
    expect(html).not.toContain('data-review-action="reopen"');
    expect(html).not.toContain('data-review-action="follow_up"');
  });

  it("renders an action proof strip from existing review-card evidence", () => {
    const html = renderToStaticMarkup(
      <InboxView
        cards={[
          card({
            status: "false_positive",
            item: {
              why: "Matches the target profile.",
              decision_state: {
                status: "changed",
                signals: ["salary_range"],
                material_change_fields: ["compensation"],
              },
            },
          }),
        ]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain('aria-label="Action proof"');
    expect(html).toContain("Profile");
    expect(html).toContain("Jobs Report");
    expect(html).toContain("Decision");
    expect(html).toContain("Changed");
    expect(html).toContain("Review");
    expect(html).toContain("Wrong match");
    expect(html).toContain("Evidence");
    expect(html).toContain("1 source ref");
    expect(html).toContain("Run");
    expect(html).toContain("Latest + report");
    expect(html).toContain("Salary Range");
    expect(html).toContain("Compensation");
  });

  it("renders source references as safe links with a capped overflow count", () => {
    const html = renderToStaticMarkup(
      <InboxView
        cards={[
          card({
            source_refs: [
              { channel: "javascript_jobs", id: 42 },
              { channel: "python_jobs", id: 7 },
              { channel: "rust_jobs", id: 9 },
              { channel: "ts_jobs", id: 11 },
              { channel: "overflow_jobs", id: 12 },
            ],
          }),
        ]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain('href="https://t.me/javascript_jobs/42"');
    expect(html).toContain("JavaScript Jobs");
    expect(html).toContain("Python Jobs");
    expect(html).toContain("Rust Jobs");
    expect(html).toContain("TS Jobs");
    expect(html).toContain("+1");
    expect(html).not.toContain("Overflow Jobs");
  });

  it("shows setup recovery details in the empty inbox state", () => {
    const setupStatus: DashboardState["setup_status"] = {
      stage: "needs_scan",
      next_step: "monitor run --dry-run",
      has_runs: false,
      checks: [
        { check_id: "workspace", label: "Workspace", status: "done", detail: "Local state exists." },
        { check_id: "source_access", label: "Source access", status: "active", detail: "Check recent messages before pruning." },
        { check_id: "delivery", label: "Delivery", status: "todo", command: "tgcs delivery test --dry-run" },
      ],
    };

    const html = renderToStaticMarkup(
      <InboxView
        cards={[]}
        latestRunId="run-1"
        setupStatus={setupStatus}
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
        onOpenStart={vi.fn()}
      />,
    );

    expect(html).toContain("Inbox clear");
    expect(html).toContain("Next: Open Start and run the first practice scan.");
    expect(html).toContain("Run first scan");
    expect(html).toContain("Workspace");
    expect(html).toContain("Done");
    expect(html).toContain("Source access");
    expect(html).toContain("Next");
    expect(html).toContain("Check recent messages before pruning.");
    expect(html).toContain("Troubleshooting command");
  });
});
