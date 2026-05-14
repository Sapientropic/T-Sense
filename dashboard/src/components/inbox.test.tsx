import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { InboxView, nextNonEmptyReviewFilter } from "./inbox";
import { ReviewCardArticle } from "./inbox/review-card";
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

    expect(html).toContain('aria-label="Review filter: Priority now (1)"');
    expect(html).toContain("Priority");
    expect(html).toContain("Frontend Developer");
    expect(html).toContain("Applied");
    expect(html).toContain("Not a fit");
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
    expect(html).toContain("All caught up");
    expect(html).toContain("Show Handled 1");
  });

  it("moves from an empty priority filter to a visible review bucket", () => {
    const filters = inboxFilterOptions(
      [
        card({
          card_id: "old-medium",
          first_run_id: "run-0",
          last_run_id: "run-0",
          rating: "medium",
          decision_status: "seen",
        }),
        card({
          card_id: "old-low",
          first_run_id: "run-0",
          last_run_id: "run-0",
          rating: "low",
          decision_status: "seen",
        }),
      ],
      "run-1",
    );

    expect(filters.find((item) => item.id === "actionable")?.count).toBe(0);
    expect(filters.find((item) => String(item.id) === "high")).toBeUndefined();
    expect(filters.find((item) => item.id === "medium")).toMatchObject({ label: "Middle", count: 1 });
    expect(filters.find((item) => item.id === "low")).toMatchObject({ label: "Low", count: 1 });
    expect(nextNonEmptyReviewFilter(filters, "actionable")).toBe("medium");
  });

  it("keeps open review cards ahead of handled history after priority clears", () => {
    const filters = inboxFilterOptions(
      [
        card({
          card_id: "just-handled",
          opportunity_status: "applied",
          opportunity_updated_at: "2026-05-11T02:00:00Z",
        }),
        card({
          card_id: "old-medium",
          first_run_id: "run-0",
          last_run_id: "run-0",
          rating: "medium",
          decision_status: "seen",
        }),
        card({
          card_id: "old-saved",
          first_run_id: "run-0",
          last_run_id: "run-0",
          opportunity_status: "saved",
        }),
      ],
      "run-1",
    );

    expect(filters.find((item) => item.id === "actionable")?.count).toBe(0);
    expect(filters.find((item) => item.id === "handled")?.count).toBe(1);
    expect(nextNonEmptyReviewFilter(filters, "actionable")).toBe("medium");
  });

  it("turns an empty priority view into a visible bucket jump", () => {
    const html = renderToStaticMarkup(
      <InboxView
        cards={[
          card({
            card_id: "old-medium",
            first_run_id: "run-0",
            last_run_id: "run-0",
            rating: "medium",
            decision_status: "seen",
          }),
        ]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain("No priority cards");
    expect(html).toContain("Show Middle 1");
  });

  it("keeps low-priority cards visible but out of the blocking next action", () => {
    const filters = inboxFilterOptions(
      [
        card({
          card_id: "old-low",
          first_run_id: "run-0",
          last_run_id: "run-0",
          rating: "low",
          decision_status: "seen",
        }),
      ],
      "run-1",
    );

    expect(filters.find((item) => item.id === "low")).toMatchObject({ label: "Low", count: 1 });
    expect(nextNonEmptyReviewFilter(filters, "actionable")).toBeNull();
  });

  it("keeps open opportunity actions visible and moves close reasons into feedback", () => {
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
    expect(html).toContain('data-review-tone="positive"');
    expect(html).toContain('data-review-action="saved"');
    expect(html).toContain('data-review-tone="supportive"');
    expect(html).toContain('data-review-action="tune"');
    expect(html).toContain('data-review-tone="negative"');
    expect(html).toContain("Reasons + signals");
    expect(html).not.toContain('data-review-action="contacted"');
    expect(html).not.toContain('data-review-action="dismissed"');
    expect(html).not.toContain('data-review-action="duplicate"');
    expect(html).not.toContain('data-review-action="reopen"');
    expect(html).not.toContain('data-review-action="follow_up"');
  });

  it("renders only user-actionable card context from existing review-card evidence", () => {
    const html = renderToStaticMarkup(
      <ReviewCardArticle
        card={card({
          status: "false_positive",
          alert_summary: {
            schema_version: "review_card_alert_summary_v1",
            alert_count: 1,
            latest_delivery_mode: "live",
            latest_delivery_ok: true,
            latest_delivery_status: "sent",
            latest_target_type: "telegram_bot",
          },
          item: {
            why: "Matches the target profile.",
            decision_state: {
              status: "changed",
              signals: ["salary_range"],
              material_change_fields: ["compensation"],
            },
          },
        })}
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain('aria-label="Card context"');
    expect(html).not.toContain("More proof");
    expect(html).not.toContain("Evidence");
    expect(html).not.toContain("Run</strong>");
    expect(html).toContain("Updated");
    expect(html).toContain("Since last scan");
    expect(html).toContain("Changed");
    expect(html).toContain("Wrong match");
    expect(html).toContain("Alert");
    expect(html).toContain("Sent");
    expect(html).toContain("Compensation");
    expect(html).toContain("View original");
    expect(html).toContain("Scan details");
  });

  it("labels notification preview proof in ordinary user language", () => {
    const html = renderToStaticMarkup(
      <ReviewCardArticle
        card={card({
          alert_summary: {
            schema_version: "review_card_alert_summary_v1",
            alert_count: 1,
            latest_delivery_mode: "dry-run",
            latest_delivery_ok: true,
            latest_delivery_status: "dry_run",
            latest_target_type: "telegram_bot",
          },
        })}
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain("Checked");
    expect(html).toContain("checked without sending");
    expect(html).not.toContain("Dry run");
  });

  it("shows repeat counts directly in the card context strip", () => {
    const html = renderToStaticMarkup(
      <ReviewCardArticle
        card={card({
          decision_status: "seen",
          item: {
            why: "Same role was posted again.",
            decision_state: {
              status: "seen",
              seen_count: 3,
              first_seen_at: "2026-05-10T09:00:00Z",
              last_seen_at: "2026-05-12T09:00:00Z",
            },
          },
        })}
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain("Seen before");
    expect(html).toContain("3 times");
  });

  it("surfaces card-level undo for saved review decisions", () => {
    const html = renderToStaticMarkup(
      <ReviewCardArticle
        card={card({
          status: "false_positive",
          item: { why: "Looks related, but the role is not a fit." },
        })}
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        act={vi.fn()}
        busy={false}
      />,
    );

    expect(html).toContain("Wrong match");
    expect(html).toContain('data-review-action="undo_decision"');
    expect(html).toContain("Undo decision");
    expect(html).toContain('aria-label="Undo Wrong match review decision"');
  });

  it("renders original source previews as the primary detail path with a capped overflow count", () => {
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

    expect(html).toContain('data-source-preview="javascript_jobs:42:0"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("View original");
    expect(html).toContain("JavaScript Jobs");
    expect(html).toContain("Python Jobs");
    expect(html).toContain("Rust Jobs");
    expect(html).toContain("TS Jobs");
    expect(html).toContain("+1 originals");
    expect(html).not.toContain("Overflow Jobs");
  });

  it("offers profile draft generation when the review queue is clear and learning decisions exist", () => {
    const html = renderToStaticMarkup(
      <InboxView
        cards={[
          card({
            card_id: "handled-role",
            opportunity_status: "dismissed",
            opportunity_updated_at: "2026-05-11T02:00:00Z",
          }),
        ]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        feedbackSummary={{
          exportable_count: 3,
          pending_profile_diff_count: 0,
        }}
        act={vi.fn()}
        busy={false}
        onGenerateProfileSuggestions={vi.fn()}
      />,
    );

    expect(html).toContain("All caught up");
    expect(html).toContain("Use handled decisions to draft profile changes.");
    expect(html).toContain("Generate drafts 3");
  });

  it("routes to existing profile drafts before generating more suggestions", () => {
    const html = renderToStaticMarkup(
      <InboxView
        cards={[
          card({
            card_id: "handled-role",
            opportunity_status: "dismissed",
            opportunity_updated_at: "2026-05-11T02:00:00Z",
          }),
        ]}
        latestRunId="run-1"
        profileReportNames={{ "jobs-fast": "Jobs Report" }}
        feedbackSummary={{
          exportable_count: 3,
          pending_profile_diff_count: 2,
        }}
        act={vi.fn()}
        busy={false}
        onGenerateProfileSuggestions={vi.fn()}
        onOpenProfiles={vi.fn()}
      />,
    );

    expect(html).toContain("Profile drafts are ready to review.");
    expect(html).toContain("Review drafts 2");
    expect(html).not.toContain("Generate drafts 3");
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
    expect(html).toContain("Next: Open Start and run the first AI review.");
    expect(html).toContain("Open Start");
    expect(html).toContain("Workspace");
    expect(html).toContain("Done");
    expect(html).toContain("Source access");
    expect(html).toContain("Next");
    expect(html).toContain("Check recent messages before pruning.");
    expect(html).not.toContain("Advanced command");
    expect(html).not.toContain("COPY COMMAND");
  });
});
