import { afterEach, describe, expect, it, vi } from "vitest";

import {
  emptyDashboardState,
  sanitizeDashboardState,
  sanitizeFeedbackExportResult,
  sanitizeGitUpdateStatus,
  sanitizeInboxCards,
} from "./sanitize";

const validCard = {
  schema_version: "review_card_v1" as const,
  card_id: "card-1",
  profile_id: "jobs-fast",
  title: "Frontend role",
  rating: "high",
  decision_status: "new",
  source_refs: [],
  item: {},
  status: "pending",
  updated_at: "2026-05-09T00:00:00Z",
};

describe("dashboard state sanitizers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("falls back to empty arrays for malformed state sections", () => {
    expect(sanitizeDashboardState({ inbox: "bad" as never, runs: null as never })).toEqual({
      ...emptyDashboardState,
      schema_version: undefined,
    });
  });

  it("drops malformed optional object sections instead of passing null or arrays through", () => {
    expect(
      sanitizeDashboardState({
        schema_version: "bad" as never,
        feedback_summary: null as never,
        opportunity_summary: [] as never,
        validation_summary: "bad" as never,
        setup_status: { stage: "ready" },
      }),
    ).toEqual({
      ...emptyDashboardState,
      setup_status: { stage: "ready" },
      schema_version: undefined,
    });
  });

  it("filters malformed dashboard array elements before they reach view code", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const state = sanitizeDashboardState({
      profiles: [null, { profile_id: "jobs-fast", enabled: true, updated_at: "2026-05-09T00:00:00Z" }],
      runs: [{ run_id: "run-1", profile_id: "jobs-fast" }, { run_id: "run-2", profile_id: "jobs-fast", status: "complete", started_at: "2026-05-09T00:00:00Z" }],
      source_stats: [{ channel: "jobs", high_count: 2 }],
      source_insights: [{ channel: "jobs", label: "Watch", reason: "Thin source", stats: { channel: "jobs" } }],
    });
    expect(state.profiles).toEqual([{ profile_id: "jobs-fast", enabled: true, updated_at: "2026-05-09T00:00:00Z" }]);
    expect(state.runs).toEqual([{ run_id: "run-2", profile_id: "jobs-fast", status: "complete", started_at: "2026-05-09T00:00:00Z" }]);
    expect(state.source_stats[0]).toMatchObject({ channel: "jobs", card_count: 0, high_count: 2, high_rate: 0 });
    expect(state.source_insights[0].stats).toMatchObject({ channel: "jobs", card_count: 0 });
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] profiles[0] expected object", null);
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] runs[0].status expected non-empty string", undefined);
  });

  it("sanitizes nested run quality fields before diagnostic formatting", () => {
    const state = sanitizeDashboardState({
      runs: [
        {
          run_id: "run-1",
          profile_id: "jobs-fast",
          status: "complete",
          started_at: "2026-05-09T00:00:00Z",
          quality: {
            semantic_stage: 12,
            top_diagnostic_code: {},
            cache_hit_rate: null,
            latency_ms: 100,
            completion_tokens: Number.POSITIVE_INFINITY,
            diagnostic_count: 1,
            diagnostic_failure_count: Number.NaN,
            diagnostic_warning_count: Number.NEGATIVE_INFINITY,
          },
        },
      ],
    });
    expect(state.runs[0].quality).toEqual({ cache_hit_rate: null, latency_ms: 100, diagnostic_count: 1 });
  });

  it("preserves explicit null run artifacts but omits malformed artifacts", () => {
    const state = sanitizeDashboardState({
      runs: [
        {
          run_id: "run-null",
          profile_id: "jobs-fast",
          status: "complete",
          started_at: "2026-05-09T00:00:00Z",
          report_artifact: null,
        },
        {
          run_id: "run-missing",
          profile_id: "jobs-fast",
          status: "complete",
          started_at: "2026-05-09T00:00:00Z",
        },
        {
          run_id: "run-bad",
          profile_id: "jobs-fast",
          status: "complete",
          started_at: "2026-05-09T00:00:00Z",
          report_artifact: { path: 42 },
        },
      ],
    });
    expect(state.runs[0]).toHaveProperty("report_artifact", null);
    expect(state.runs[1]).not.toHaveProperty("report_artifact");
    expect(state.runs[2]).not.toHaveProperty("report_artifact");
  });

  it("drops empty optional summary objects", () => {
    expect(
      sanitizeDashboardState({
        feedback_summary: {},
        opportunity_summary: {},
        validation_summary: {},
        setup_status: {},
      }),
    ).toEqual({ ...emptyDashboardState, schema_version: undefined });
  });

  it("sanitizes optional dashboard summary sections instead of trusting objects", () => {
    const state = sanitizeDashboardState({
      opportunity_summary: {
        status: "failed",
        diagnostics: "bad",
        decision_counts: { new: 2, bad: "x", infinite: Number.POSITIVE_INFINITY },
        next_action: { label: "Fix sources", command: 12, target: "inbox" },
        top_items: [{ card_id: "card-1", title: "Role", rating: "high", decision_status: "new", status: "pending", source_refs: ["bad"] }],
      },
      validation_summary: { by_action: { keep: 1, skip: "bad", bad_nan: Number.NaN }, next_action: { detail: "Review outcomes" } },
      feedback_summary: { recent_impacts: ["bad", {}, { item_title: "Kept role", impact_status: 3 }], by_rating: { high: 1, low: null } },
      setup_status: { checks: [{ check_id: "profiles", label: "Profiles", status: "active", command: 42 }, null] },
    });
    expect(state.opportunity_summary).toEqual({
      status: "failed",
      decision_counts: { new: 2 },
      next_action: { label: "Fix sources", target: "inbox" },
      top_items: [{ card_id: "card-1", title: "Role", rating: "high", decision_status: "new", status: "pending", source_refs: [] }],
    });
    expect(state.validation_summary).toEqual({ by_action: { keep: 1 }, next_action: { detail: "Review outcomes" } });
    expect(state.feedback_summary).toEqual({ recent_impacts: [{ item_title: "Kept role" }], by_rating: { high: 1 } });
    expect(state.setup_status).toEqual({ checks: [{ check_id: "profiles", label: "Profiles", status: "active" }] });
  });

  it("sanitizes nested optional objects instead of object-level casting", () => {
    const state = sanitizeDashboardState({
      profile_patch_suggestions: [
        {
          patch_id: "patch-1",
          profile_id: "jobs-fast",
          note: "Retune threshold",
          status: "pending",
          diff_text: "{}",
          created_at: "2026-05-09T00:00:00Z",
          apply_readiness: { status: 1, label: "Ready", detail: null, extra: "ignored" },
        },
      ],
      source_insights: [
        {
          channel: "jobs",
          label: "Watch jobs",
          reason: "Good yield",
          next_action: { label: "Review source", command: 7, target: "ignored" },
        },
      ],
      inbox: [
        {
          ...validCard,
          item: {
            why: "Strong match",
            decision_state: {
              status: "new",
              signals: ["salary", "   ", 2],
              explanations: { salary: "clear", blank: "", whitespace: " ", bad: 3 },
              extra: "ignored",
            },
          },
        },
        {
          ...validCard,
          card_id: "card-empty-decision-state",
          item: { decision_state: { signals: [], explanations: {} } },
        },
      ],
    });
    expect(state.profile_patch_suggestions[0].apply_readiness).toEqual({ label: "Ready" });
    expect(state.source_insights[0].next_action).toEqual({ label: "Review source" });
    expect(state.inbox[0].item).toEqual({
      why: "Strong match",
      decision_state: { status: "new", signals: ["salary"], explanations: { salary: "clear" } },
    });
    expect(state.inbox[1].item).toEqual({});
  });

  it("drops nested optional objects when every known field is invalid", () => {
    const state = sanitizeDashboardState({
      profile_patch_suggestions: [
        {
          patch_id: "patch-1",
          profile_id: "jobs-fast",
          note: "Retune threshold",
          status: "pending",
          diff_text: "{}",
          created_at: "2026-05-09T00:00:00Z",
          apply_readiness: { status: 1, label: "", detail: [] },
        },
      ],
      source_insights: [
        {
          channel: "jobs",
          label: "Watch jobs",
          reason: "Good yield",
          next_action: { label: "", command: 7, detail: null },
        },
      ],
    });
    expect(state.profile_patch_suggestions[0].apply_readiness).toBeUndefined();
    expect(state.source_insights[0].next_action).toBeUndefined();
  });

  it("sanitizes action API response envelopes before view state updates", () => {
    expect(
      sanitizeGitUpdateStatus({
        status: " behind ",
        message: "  needs pull  ",
        branch: " main ",
        upstream: 42,
        ahead: -1,
        behind: 2.5,
        dirty: true,
        dirty_count: -3,
        pull_allowed: false,
        checked_at: " 2026-05-10T09:00:00+08:00 ",
      }),
    ).toEqual({
      schema_version: "git_update_status_v1",
      status: "behind",
      message: "needs pull",
      branch: "main",
      upstream: undefined,
      repo_url: undefined,
      head: undefined,
      remote_head: undefined,
      ahead: 0,
      behind: 0,
      dirty: true,
      dirty_count: 0,
      pull_allowed: false,
      checked_at: "2026-05-10T09:00:00+08:00",
    });
    expect(sanitizeGitUpdateStatus({ message: "missing status", branch: "main" })).toBeNull();
    expect(sanitizeGitUpdateStatus({ status: " ", branch: "main" })).toBeNull();
    expect(sanitizeGitUpdateStatus({ status: "behind", branch: " " })).toBeNull();
    expect(
      sanitizeGitUpdateStatus({
        status: "clean",
        message: 42,
        branch: "main",
        upstream: " ",
        ahead: 0,
        behind: 0,
        dirty: "true",
        dirty_count: 0,
        pull_allowed: "false",
        checked_at: "",
      }),
    ).toMatchObject({
      status: "clean",
      message: "",
      branch: "main",
      upstream: undefined,
      ahead: 0,
      behind: 0,
      dirty: false,
      dirty_count: 0,
      pull_allowed: false,
      checked_at: "",
    });
    expect(sanitizeFeedbackExportResult({ feedback_count: 2, output_path: " output/feedback/review-feedback.jsonl " })).toEqual({
      schema_version: "feedback_export_result_v1",
      feedback_count: 2,
      output_path: "output/feedback/review-feedback.jsonl",
    });
    expect(sanitizeFeedbackExportResult({ feedback_count: 0, output_path: "out.jsonl" })).toEqual({
      schema_version: "feedback_export_result_v1",
      feedback_count: 0,
      output_path: "out.jsonl",
    });
    expect(sanitizeFeedbackExportResult({ feedback_count: 1, output_path: 42 })).toBeNull();
    expect(sanitizeFeedbackExportResult({ feedback_count: Number.NaN, output_path: "output/feedback/review-feedback.jsonl" })).toBeNull();
    expect(sanitizeFeedbackExportResult({ feedback_count: -1, output_path: "output/feedback/review-feedback.jsonl" })).toBeNull();
    expect(sanitizeFeedbackExportResult({ feedback_count: 1.5, output_path: "output/feedback/review-feedback.jsonl" })).toBeNull();
    expect(sanitizeFeedbackExportResult({ feedback_count: 1, output_path: "   " })).toBeNull();
  });

  it("filters non-object inbox entries instead of casting them through", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const cards = sanitizeInboxCards([validCard, null, "bad", {}]);
    expect(cards).toEqual([validCard]);
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] inbox[1] expected object", null);
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] inbox[2] expected object", "bad");
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] inbox[3].card_id expected non-empty string", undefined);
  });

  it("keeps object cards renderable while warning on unexpected field types", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const dirtyCard = { ...validCard, card_id: "card-2", rating: 0, decision_status: false };
    const cards = sanitizeInboxCards([dirtyCard]);
    expect(cards).toEqual([{ ...validCard, card_id: "card-2", rating: "unknown", decision_status: "unknown" }]);
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] inbox[0].rating expected string/null/undefined", 0);
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] inbox[0].decision_status expected string/null/undefined", false);
  });

  it("builds a safe review card shape instead of trusting extra backend fields", () => {
    const card = {
      ...validCard,
      extra: "ignored",
      item: { why: "Strong match", decision_state: { status: "new" } },
      source_refs: [{ channel: "jobs", id: 1 }, { channel: "bad" }, "bad"],
    };
    expect(sanitizeInboxCards([card])).toEqual([
      {
        ...validCard,
        item: { why: "Strong match", decision_state: { status: "new" } },
        source_refs: [{ channel: "jobs", id: 1 }],
      },
    ]);
  });
});
