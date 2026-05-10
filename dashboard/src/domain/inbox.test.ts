import { describe, expect, it } from "vitest";

import {
  countInboxCardsByRating,
  filterInboxCards,
  inboxFilterOptions,
  isActionableInboxCard,
  isMalformedInboxCard,
  setupCheckLabel,
  setupCheckTone,
  setupNeedsAttention,
  telegramMessageUrl,
  type InboxCardLike,
} from "./inbox";

const cards: InboxCardLike[] = [
  { rating: "high", decision_status: "new", last_run_id: "run-2" },
  { rating: "HIGH", decision_status: "changed", last_run_id: "run-1" },
  { rating: "medium", decision_status: "seen", last_run_id: "run-2" },
  { rating: "low", decision_status: "recurring", last_run_id: "run-2" },
  { rating: null, decision_status: undefined, last_run_id: "run-2" },
  { rating: 0, decision_status: false, last_run_id: "run-2" },
  { rating: "", decision_status: "", last_run_id: "run-2" },
];

describe("inbox domain helpers", () => {
  it("treats latest high new or changed cards as actionable", () => {
    expect(isActionableInboxCard(cards[0], "run-2")).toBe(true);
    expect(isActionableInboxCard(cards[1], "run-2")).toBe(false);
    expect(isActionableInboxCard(cards[1])).toBe(true);
    expect(isActionableInboxCard(cards[2], "run-2")).toBe(false);
  });

  it("keeps dirty API values from crashing filters", () => {
    expect(() => filterInboxCards(cards, "actionable", "run-2")).not.toThrow();
    expect(filterInboxCards(cards, "actionable", "run-2")).toEqual([cards[0]]);
    expect(isActionableInboxCard(cards[4], "run-2")).toBe(false);
  });

  it("surfaces malformed cards for UI schema indicators", () => {
    expect(isMalformedInboxCard(cards[4])).toBe(false);
    expect(isMalformedInboxCard(cards[5])).toBe(true);
    expect(isMalformedInboxCard(cards[6])).toBe(false);
    expect(isMalformedInboxCard(cards[0])).toBe(false);
  });

  it("filters by triage bucket without mutating review state", () => {
    expect(filterInboxCards(cards, "all")).toHaveLength(7);
    expect(filterInboxCards(cards, "high")).toEqual([cards[0], cards[1]]);
    expect(filterInboxCards(cards, "new_changed")).toEqual([cards[0], cards[1]]);
    expect(filterInboxCards(cards, "low_medium")).toEqual([cards[2], cards[3]]);
    expect(countInboxCardsByRating(cards, "high")).toBe(2);
    expect(countInboxCardsByRating(cards, "medium")).toBe(1);
    expect(countInboxCardsByRating(cards, "low")).toBe(1);
  });

  it("builds stable filter options for empty latest-action states", () => {
    expect(inboxFilterOptions(cards, "run-2")).toEqual([
      { id: "actionable", label: "Latest action", count: 1 },
      { id: "all", label: "All", count: 7 },
      { id: "high", label: "High", count: 2 },
      { id: "new_changed", label: "New/Changed", count: 2 },
      { id: "low_medium", label: "Low/Medium", count: 2 },
    ]);
    expect(inboxFilterOptions([], "run-2")[0]).toEqual({ id: "actionable", label: "Latest action", count: 0 });
  });

  it("maps setup checklist states for inbox empty states", () => {
    expect(setupNeedsAttention([{ status: "done" }, { status: "todo" }])).toBe(false);
    expect(setupNeedsAttention([{ status: "blocked" }])).toBe(true);
    expect(setupNeedsAttention([{ status: "active" }])).toBe(true);
    expect(setupCheckTone("done")).toBe("done");
    expect(setupCheckTone("blocked")).toBe("blocked");
    expect(setupCheckTone("active")).toBe("active");
    expect(setupCheckTone("later")).toBe("todo");
    expect(setupCheckLabel("done")).toBe("Done");
    expect(setupCheckLabel("blocked")).toBe("Blocked");
    expect(setupCheckLabel("active")).toBe("Next");
    expect(setupCheckLabel("later")).toBe("Later");
  });

  it("builds Telegram message links only for safe public references", () => {
    expect(telegramMessageUrl({ channel: "@valid_jobs", id: 123 })).toBe("https://t.me/valid_jobs/123");
    expect(telegramMessageUrl({ channel: "abc", id: 123 })).toBe("");
    expect(telegramMessageUrl({ channel: "valid_jobs", id: "abc" })).toBe("");
    expect(telegramMessageUrl({ channel: "valid-jobs", id: 123 })).toBe("");
  });
});
