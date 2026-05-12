import { afterEach, describe, expect, it, vi } from "vitest";

import {
  emptyDashboardState,
  sanitizeDeskActions,
  sanitizeDeskActionResult,
  sanitizeDeskAiSettingsStatus,
  sanitizeDeskNotificationTokenStatus,
  sanitizeDeskSchedulerStatus,
  sanitizeDeskSourcesResult,
  sanitizeDeskTelegramStatus,
  sanitizeDeliveryChatDetectionResult,
  sanitizeDeliveryTestResult,
  sanitizeDashboardState,
  sanitizeFeedbackClearResult,
  sanitizeFeedbackExportResult,
  sanitizeFeedbackProfileSuggestionsResult,
  sanitizeGitUpdateStatus,
  sanitizeInboxCards,
  sanitizeProfileCreateResult,
  sanitizeSourceImportResult,
} from "./sanitize";
import {
  sanitizeDeskActionResult as sanitizeDashboardModuleDeskActionResult,
  sanitizeFeedbackExportResult as sanitizeDashboardModuleFeedbackExportResult,
  sanitizeSourceImportResult as sanitizeDashboardModuleSourceImportResult,
} from "./sanitize/dashboard";
import {
  sanitizeDeskActionResult as sanitizeDeskModuleDeskActionResult,
  sanitizeFeedbackExportResult as sanitizeDeskModuleFeedbackExportResult,
  sanitizeSourceImportResult as sanitizeDeskModuleSourceImportResult,
} from "./sanitize/desk";
import sourceImportFixture from "../../../tests/fixtures/contracts/desk_source_import_result_v1.json";

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
      source_stats: [{ channel: "jobs", high_count: 2, scan_failure_reason: " permission_or_private " }],
      source_insights: [{ channel: "jobs", label: "Watch", reason: "Thin source", stats: { channel: "jobs" } }],
    });
    expect(state.profiles).toEqual([{ profile_id: "jobs-fast", enabled: true, updated_at: "2026-05-09T00:00:00Z" }]);
    expect(state.runs).toEqual([{ run_id: "run-2", profile_id: "jobs-fast", status: "complete", started_at: "2026-05-09T00:00:00Z" }]);
    expect(state.source_stats[0]).toMatchObject({ channel: "jobs", card_count: 0, high_count: 2, high_rate: 0, scan_failure_reason: "permission_or_private" });
    expect(state.source_insights[0].stats).toMatchObject({ channel: "jobs", card_count: 0 });
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] profiles[0] expected object", null);
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] runs[0].status expected non-empty string", undefined);
  });

  it("sanitizes active Desk action progress from dashboard state", () => {
    const state = sanitizeDashboardState({
      active_actions: [
        {
          schema_version: "desk_active_action_v1",
          action_id: "sources_probe_access",
          title: "Check source access",
          status: "running",
          started_at: "2026-05-12T15:00:00Z",
          updated_at: "2026-05-12T15:01:00Z",
          elapsed_seconds: 61,
          checked_count: 17,
          total_count: 68,
          detail: "Source access check running; checked 17/68 sources.",
        },
        { action_id: "", title: "bad", status: "running", started_at: "" },
      ],
    });

    expect(state.active_actions).toEqual([
      {
        schema_version: "desk_active_action_v1",
        action_id: "sources_probe_access",
        title: "Check source access",
        status: "running",
        started_at: "2026-05-12T15:00:00Z",
        updated_at: "2026-05-12T15:01:00Z",
        elapsed_seconds: 61,
        checked_count: 17,
        total_count: 68,
        detail: "Source access check running; checked 17/68 sources.",
      },
    ]);
  });

  it("keeps structured source access summaries on setup checks", () => {
    const state = sanitizeDashboardState({
      setup_status: {
        stage: "needs_source_access",
        checks: [
          {
            check_id: "source_access",
            label: "Source access",
            status: "blocked",
            detail: "Access check: 2 recently active.",
            source_access: {
              schema_version: "desk_source_access_health_v1",
              source_count: 8,
              checked_count: 8,
              accessible_count: 2,
              quiet_count: 1,
              inaccessible_count: 5,
              truncated_count: 0,
              probe_window_hours: 24,
            },
          },
        ],
      },
    });

    expect(state.setup_status?.checks?.[0].source_access).toMatchObject({
      accessible_count: 2,
      quiet_count: 1,
      inaccessible_count: 5,
      probe_window_hours: 24,
    });
  });

  it("keeps safe source ref urls and drops unsafe ones", () => {
    expect(
      sanitizeInboxCards([
        {
          ...validCard,
          source_refs: [
            { channel: "jobs", id: 1, url: "https://t.me/jobs/1" },
            { channel: "bad", id: 2, url: "javascript:alert(1)" },
          ],
        },
      ])[0].source_refs,
    ).toEqual([
      { channel: "jobs", id: 1, url: "https://t.me/jobs/1" },
      { channel: "bad", id: 2 },
    ]);
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

  it("sanitizes AI API provider status without exposing secrets", () => {
    expect(
      sanitizeDeskAiSettingsStatus({
        schema_version: "desk_ai_settings_status_v1",
        configured_count: 1,
        local_store_supported: true,
        platform: "win32",
        detail: "1 AI provider key configured.",
        checked_at: "2026-05-11T00:00:00Z",
        providers: [
          {
            provider: "deepseek",
            label: "DeepSeek",
            env_name: "DEEPSEEK_API_KEY",
            configured: true,
            source: "windows_credential_manager",
            env_configured: false,
            local_store_configured: true,
            can_save: true,
            can_clear: true,
            updated_at: "2026-05-10T00:00:00Z",
            detail: "DeepSeek API key is saved.",
            api_key: "secret",
          },
          { provider: "", label: "Bad", env_name: "BAD", source: "missing" },
        ],
      }),
    ).toEqual({
      schema_version: "desk_ai_settings_status_v1",
      configured_count: 1,
      local_store_supported: true,
      platform: "win32",
      detail: "1 AI provider key configured.",
      checked_at: "2026-05-11T00:00:00Z",
      providers: [
        {
          provider: "deepseek",
          label: "DeepSeek",
          env_name: "DEEPSEEK_API_KEY",
          configured: true,
          source: "windows_credential_manager",
          env_configured: false,
          local_store_configured: true,
          can_save: true,
          can_clear: true,
          updated_at: "2026-05-10T00:00:00Z",
          detail: "DeepSeek API key is saved.",
        },
      ],
    });
    expect(sanitizeDeskAiSettingsStatus({})).toBeNull();
    expect(sanitizeDeskAiSettingsStatus({ schema_version: "desk_ai_settings_status_v1" })).toBeNull();
    expect(
      sanitizeDeskAiSettingsStatus({
        schema_version: "desk_ai_settings_status_v1",
        configured_count: Number.NaN,
        local_store_supported: true,
        platform: "win32",
        detail: "Bad count.",
        providers: [],
      }),
    ).toBeNull();
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
        {
          run_id: "run-absolute",
          profile_id: "jobs-fast",
          status: "complete",
          started_at: "2026-05-09T00:00:00Z",
          report_artifact: { path: "C:/Users/Administrator/private/report.html" },
        },
        {
          run_id: "run-traversal",
          profile_id: "jobs-fast",
          status: "complete",
          started_at: "2026-05-09T00:00:00Z",
          report_artifact: { path: "output/runs/run-1/../secret-report.html" },
        },
        {
          run_id: "run-non-report",
          profile_id: "jobs-fast",
          status: "complete",
          started_at: "2026-05-09T00:00:00Z",
          report_artifact: { path: "output/runs/run-1/scan.jsonl" },
        },
        {
          run_id: "run-report",
          profile_id: "jobs-fast",
          status: "complete",
          started_at: "2026-05-09T00:00:00Z",
          report_artifact: { path: "output/runs/run-1/jobs-fast-signal-report-2026-05-09-1225.html" },
        },
      ],
    });
    expect(state.runs[0]).toHaveProperty("report_artifact", null);
    expect(state.runs[1]).not.toHaveProperty("report_artifact");
    expect(state.runs[2]).not.toHaveProperty("report_artifact");
    expect(state.runs[3]).not.toHaveProperty("report_artifact");
    expect(state.runs[4]).not.toHaveProperty("report_artifact");
    expect(state.runs[5]).not.toHaveProperty("report_artifact");
    expect(state.runs[6].report_artifact?.path).toBe("output/runs/run-1/jobs-fast-signal-report-2026-05-09-1225.html");
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
      delivery_targets: [
        {
          target_id: "legacy-target",
          type: "telegram_bot",
          enabled: true,
          config: { chat_id: "999999", bot_token: "secret" },
          updated_at: "2026-05-10T00:00:00Z",
        },
        {
          schema_version: "delivery_target_v1",
          target_id: "telegram-bot-default",
          type: "telegram_bot",
          enabled: true,
          config: {
            chat_id: "123456",
            bot_token: "secret",
            token: "secret",
            mode: "live",
          },
          updated_at: "2026-05-10T00:00:00Z",
        },
      ],
      opportunity_summary: {
        status: "failed",
        diagnostics: "bad",
        decision_counts: { new: 2, bad: "x", infinite: Number.POSITIVE_INFINITY },
        next_action: { label: "Fix sources", command: 12, target: "inbox" },
        top_items: [{ card_id: "card-1", title: "Role", rating: "high", decision_status: "new", status: "pending", source_refs: ["bad"] }],
      },
      validation_summary: { by_action: { keep: 1, skip: "bad", bad_nan: Number.NaN }, next_action: { detail: "Review outcomes" } },
      feedback_summary: {
        recent_impacts: ["bad", {}, { item_title: "Kept role", impact_status: 3 }],
        by_rating: { high: 1, low: null },
        last_export_path: "C:/Users/Administrator/private/review-feedback.jsonl",
      },
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
    expect(
      sanitizeDashboardState({ feedback_summary: { last_export_path: " output\\feedback\\review-feedback.jsonl " } }).feedback_summary
        ?.last_export_path,
    ).toBe("output/feedback/review-feedback.jsonl");
    expect(state.setup_status).toEqual({ checks: [{ check_id: "profiles", label: "Profiles", status: "active" }] });
    expect(state.delivery_targets).toHaveLength(1);
    expect(state.delivery_targets[0].config).toEqual({ chat_id: "123456" });
    expect(JSON.stringify(state.delivery_targets)).not.toContain("secret");
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

  it("sanitizes notification dry-run result envelopes", () => {
    expect(
      sanitizeDeliveryTestResult({
        schema_version: "desk_delivery_test_result_v1",
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        mode: "live",
        ok: true,
        status: "dry_run",
        title: "Notification test",
        detail: "Checked",
      }),
    ).toEqual({
      schema_version: "desk_delivery_test_result_v1",
      target_id: "telegram-bot-default",
      target_type: "telegram_bot",
      mode: "dry-run",
      ok: true,
      status: "dry_run",
      title: "Notification test",
      detail: "Checked",
    });
    expect(sanitizeDeliveryTestResult({ target_id: "telegram-bot-default", target_type: "telegram_bot" })).toBeNull();
    expect(
      sanitizeDeliveryTestResult({
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        ok: true,
        status: "dry_run",
      }),
    ).toBeNull();
    expect(
      sanitizeDeliveryChatDetectionResult({
        schema_version: "desk_delivery_chat_detection_v1",
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        ok: true,
        status: "detected",
        source: "updates",
        chat_id: "123456",
        chat_type: "private",
        title: "Detected chat",
      }),
    ).toEqual({
      schema_version: "desk_delivery_chat_detection_v1",
      target_id: "telegram-bot-default",
      target_type: "telegram_bot",
      ok: true,
      status: "detected",
      source: "updates",
      chat_id: "123456",
      chat_type: "private",
      title: "Detected chat",
    });
    expect(
      sanitizeDeliveryChatDetectionResult({
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        ok: true,
        status: "detected",
        source: "updates",
      }),
    ).toBeNull();
  });

  it("sanitizes source import result envelopes without trusting backend-only fields", () => {
    expect(
      sanitizeSourceImportResult({
        schema_version: "desk_source_import_result_v1",
        dry_run: true,
        written: false,
        topic: " jobs ",
        added_count: 2,
        updated_count: 1,
        unchanged_count: -4,
        source_count: 3,
        registry_path: " .tgcs/sources.json ",
        preview_truncated_count: 8,
        preview_sources: [
          { label: " remote_jobs ", source_id: " telegram:remote_jobs ", token: "secret" },
          { label: "", source_id: "bad" },
        ],
        resolved_plan: {
          add: [" remote_jobs ", 12],
          remove: [" telegram:old_jobs "],
          disable: [" telegram:spam_jobs "],
          enable: [" telegram:paused_jobs "],
        },
        title: " Source preview ready ",
        detail: " Review first. ",
        command: "tgcs sources import private.txt",
      }),
    ).toEqual({
      schema_version: "desk_source_import_result_v1",
      dry_run: true,
      written: false,
      topic: "jobs",
      added_count: 2,
      updated_count: 1,
      unchanged_count: 0,
      removed_count: 0,
      enabled_count: 0,
      disabled_count: 0,
      source_count: 3,
      registry_path: ".tgcs/sources.json",
      preview_sources: [{ label: "remote_jobs", source_id: "telegram:remote_jobs" }],
      resolved_plan: {
        add: ["remote_jobs"],
        remove: ["telegram:old_jobs"],
        disable: ["telegram:spam_jobs"],
        enable: ["telegram:paused_jobs"],
      },
      preview_truncated_count: 8,
      action: undefined,
      llm_used: false,
      title: "Source preview ready",
      detail: "Review first.",
      next_action: undefined,
      finished_at: undefined,
    });
    expect(sanitizeSourceImportResult({ topic: "jobs" })).toBeNull();
  });

  it("keeps source import result semantics aligned across public and legacy sanitizer entrypoints", () => {
    const expected = {
      schema_version: "desk_source_import_result_v1",
      dry_run: true,
      written: false,
      topic: "jobs",
      added_count: 2,
      updated_count: 1,
      unchanged_count: 0,
      removed_count: 3,
      enabled_count: 4,
      disabled_count: 5,
      source_count: 14,
      registry_path: ".tgcs/sources.json",
      preview_sources: [{ label: "remote_jobs", source_id: "telegram:remote_jobs" }],
      resolved_plan: {
        add: ["remote_jobs"],
        remove: ["telegram:old_jobs"],
        disable: ["telegram:spam_jobs"],
        enable: ["telegram:paused_jobs"],
      },
      preview_truncated_count: 1,
      action: "assistant_apply",
      llm_used: true,
      title: "Source plan ready",
      detail: "Review first.",
      next_action: "Apply reviewed changes.",
      finished_at: "2026-05-13T00:00:00Z",
    };

    expect(sanitizeSourceImportResult(sourceImportFixture)).toEqual(expected);
    expect(sanitizeDeskModuleSourceImportResult(sourceImportFixture)).toEqual(expected);
    expect(sanitizeDashboardModuleSourceImportResult(sourceImportFixture)).toEqual(expected);
    expect(JSON.stringify(sanitizeSourceImportResult(sourceImportFixture))).not.toContain("SECRET_SHOULD_NOT_RENDER");
  });

  it("sanitizes saved source library envelopes without leaking backend-only fields", () => {
    expect(
      sanitizeDeskSourcesResult({
        schema_version: "desk_sources_v1",
        source_count: 2,
        enabled_count: 1,
        topics: [" jobs ", 7, "ai"],
        registry_path: " .tgcs/sources.json ",
        sources: [
          {
            schema_version: "desk_source_v1",
            source_id: " telegram:remote_jobs ",
            label: " Remote Jobs ",
            channel: " remote_jobs ",
            enabled: true,
            topics: ["jobs", "", 42],
            priority: " high ",
            scan_window_hours: 48,
            token: "secret",
            command: "tgcs sources import private.txt",
          },
          {
            source_id: "telegram:quiet_jobs",
            label: "Quiet Jobs",
            channel: "quiet_jobs",
            enabled: false,
            topics: "jobs",
            priority: 2,
            scan_window_hours: -1,
          },
          { source_id: "bad", label: "", channel: "broken" },
        ],
      }),
    ).toEqual({
      schema_version: "desk_sources_v1",
      source_count: 2,
      enabled_count: 1,
      topics: ["jobs", "ai"],
      registry_path: ".tgcs/sources.json",
      sources: [
        {
          schema_version: "desk_source_v1",
          source_id: "telegram:remote_jobs",
          label: "Remote Jobs",
          channel: "remote_jobs",
          enabled: true,
          topics: ["jobs"],
          priority: "high",
          scan_window_hours: 48,
        },
        {
          schema_version: undefined,
          source_id: "telegram:quiet_jobs",
          label: "Quiet Jobs",
          channel: "quiet_jobs",
          enabled: false,
          topics: [],
          priority: "normal",
          scan_window_hours: 24,
        },
      ],
    });
    expect(JSON.stringify(sanitizeDeskSourcesResult({ registry_path: ".tgcs/sources.json", sources: [] }))).not.toContain("secret");
    expect(sanitizeDeskSourcesResult({ sources: [] })).toBeNull();
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
        schema_version: "git_update_status_v1",
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
    expect(
      sanitizeGitUpdateStatus({
        status: "behind",
        message: "missing schema",
        branch: "main",
        ahead: 0,
        behind: 1,
        dirty: false,
        dirty_count: 0,
        pull_allowed: true,
        checked_at: "2026-05-10T09:00:00+08:00",
      }),
    ).toBeNull();
    expect(sanitizeGitUpdateStatus({ message: "missing status", branch: "main" })).toBeNull();
    expect(sanitizeGitUpdateStatus({ status: " ", branch: "main" })).toBeNull();
    expect(sanitizeGitUpdateStatus({ status: "behind", branch: " " })).toBeNull();
    expect(
      sanitizeGitUpdateStatus({
        schema_version: "git_update_status_v1",
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
    expect(
      sanitizeFeedbackExportResult({
        schema_version: "feedback_export_result_v1",
        feedback_count: 2,
        output_path: " output/feedback/review-feedback.jsonl ",
        changed_since_last_export: true,
        exported_at: " 2026-05-10T00:00:00Z ",
      }),
    ).toEqual({
      schema_version: "feedback_export_result_v1",
      feedback_count: 2,
      output_path: "output/feedback/review-feedback.jsonl",
      changed_since_last_export: true,
      exported_at: "2026-05-10T00:00:00Z",
    });
    expect(
      sanitizeFeedbackExportResult({ schema_version: "feedback_export_result_v1", feedback_count: 0, output_path: "out.jsonl" }),
    ).toEqual({
      schema_version: "feedback_export_result_v1",
      feedback_count: 0,
      output_path: "out.jsonl",
    });
    expect(sanitizeFeedbackExportResult({ feedback_count: 1, output_path: "output/feedback/review-feedback.jsonl" })).toBeNull();
    expect(sanitizeFeedbackExportResult({ schema_version: "feedback_export_result_v1", feedback_count: 1, output_path: 42 })).toBeNull();
    expect(
      sanitizeFeedbackExportResult({
        schema_version: "feedback_export_result_v1",
        feedback_count: Number.NaN,
        output_path: "output/feedback/review-feedback.jsonl",
      }),
    ).toBeNull();
    expect(
      sanitizeFeedbackExportResult({
        schema_version: "feedback_export_result_v1",
        feedback_count: -1,
        output_path: "output/feedback/review-feedback.jsonl",
      }),
    ).toBeNull();
    expect(
      sanitizeFeedbackExportResult({
        schema_version: "feedback_export_result_v1",
        feedback_count: 1.5,
        output_path: "output/feedback/review-feedback.jsonl",
      }),
    ).toBeNull();
    expect(
      sanitizeFeedbackExportResult({ schema_version: "feedback_export_result_v1", feedback_count: 1, output_path: "   " }),
    ).toBeNull();
    for (const output_path of [
      "C:/Users/Administrator/private/review-feedback.jsonl",
      "C:\\Users\\Administrator\\private\\review-feedback.jsonl",
      "../private/review-feedback.jsonl",
      "output/feedback/../private.jsonl",
      "file:///tmp/review-feedback.jsonl",
      "output/feedback/review\nfeedback.jsonl",
    ]) {
      expect(sanitizeFeedbackExportResult({ schema_version: "feedback_export_result_v1", feedback_count: 1, output_path })).toBeNull();
      expect(
        sanitizeDeskModuleFeedbackExportResult({ schema_version: "feedback_export_result_v1", feedback_count: 1, output_path }),
      ).toBeNull();
      expect(
        sanitizeDashboardModuleFeedbackExportResult({ schema_version: "feedback_export_result_v1", feedback_count: 1, output_path }),
      ).toBeNull();
    }
    expect(
      sanitizeDashboardModuleFeedbackExportResult({
        schema_version: "feedback_export_result_v1",
        feedback_count: 2,
        output_path: " output\\feedback\\review-feedback.jsonl ",
      }),
    ).toEqual({
      schema_version: "feedback_export_result_v1",
      feedback_count: 2,
      output_path: "output/feedback/review-feedback.jsonl",
    });
    expect(
      sanitizeFeedbackProfileSuggestionsResult({
        schema_version: "feedback_profile_suggestions_result_v1",
        created_count: 1,
        existing_count: 2,
        skipped_count: 0,
        patch_ids: [" patch-1 ", 42, "patch-2"],
        profile_ids: [" jobs-fast "],
        detail: " Profile drafts ready ",
        generated_at: " 2026-05-10T00:00:00Z ",
      }),
    ).toEqual({
      schema_version: "feedback_profile_suggestions_result_v1",
      created_count: 1,
      existing_count: 2,
      skipped_count: 0,
      patch_ids: ["patch-1", "patch-2"],
      profile_ids: ["jobs-fast"],
      detail: "Profile drafts ready",
      generated_at: "2026-05-10T00:00:00Z",
    });
    expect(sanitizeFeedbackProfileSuggestionsResult({ created_count: 1, existing_count: 0, skipped_count: 0 })).toBeNull();
    expect(
      sanitizeFeedbackProfileSuggestionsResult({
        schema_version: "feedback_profile_suggestions_result_v1",
        created_count: -1,
        existing_count: 0,
        skipped_count: 0,
      }),
    ).toBeNull();
    expect(sanitizeFeedbackClearResult({ schema_version: "feedback_clear_result_v1", cleared_count: 2 })).toEqual({
      schema_version: "feedback_clear_result_v1",
      cleared_count: 2,
    });
    expect(sanitizeFeedbackClearResult({ cleared_count: 2 })).toBeNull();
    expect(sanitizeFeedbackClearResult({ schema_version: "feedback_clear_result_v1", cleared_count: 1.5 })).toBeNull();
    expect(
      sanitizeProfileCreateResult({
        schema_version: "desk_profile_create_result_v1",
        profile_id: " jobs-fast ",
        display_name: " Jobs Fast ",
        profile_path: " profiles/jobs-fast.md ",
        created: true,
        detail: " Created profile ",
        next_action: " Review it ",
      }),
    ).toEqual({
      schema_version: "desk_profile_create_result_v1",
      profile_id: "jobs-fast",
      display_name: "Jobs Fast",
      profile_path: "profiles/jobs-fast.md",
      created: true,
      detail: "Created profile",
      next_action: "Review it",
      created_at: undefined,
    });
    expect(
      sanitizeProfileCreateResult({
        profile_id: "jobs-fast",
        display_name: "Jobs Fast",
        profile_path: "profiles/jobs-fast.md",
      }),
    ).toBeNull();
  });

  it("sanitizes Desk action payloads without trusting backend-only fields", () => {
    const actions = sanitizeDeskActions({
      schema_version: "desk_actions_v1",
      actions: [
        {
          schema_version: "desk_action_v1",
          action_id: " monitor_jobs_dry_run ",
          group: " run ",
          title: " Dry-run monitor ",
          detail: "Preview local report generation.",
          run_mode: "execute",
          display_command: " tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run ",
          next_action: "Open the report.",
          argv: ["monitor", "run"],
        },
        {
          schema_version: "desk_action_v1",
          action_id: "schedule_install_dry_run",
          group: "Schedule",
          title: "Turn on auto scan",
          detail: "Create a local practice scan schedule.",
          run_mode: "confirm_execute",
          display_command: "Windows Task Scheduler: jobs-fast dry-run",
          next_action: "Review future cards in Signal Desk.",
          argv: ["blocked", "frontend", "must", "ignore"],
        },
        { action_id: "broken", title: "Missing required fields" },
        "bad",
      ],
    });

    expect(actions).toEqual([
      {
        schema_version: "desk_action_v1",
        action_id: "monitor_jobs_dry_run",
        group: "run",
        title: "Dry-run monitor",
        detail: "Preview local report generation.",
        run_mode: "execute",
        display_command: "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
        next_action: "Open the report.",
      },
      {
        schema_version: "desk_action_v1",
        action_id: "schedule_install_dry_run",
        group: "Schedule",
        title: "Turn on auto scan",
        detail: "Create a local practice scan schedule.",
        run_mode: "confirm_execute",
        display_command: "Windows Task Scheduler: jobs-fast dry-run",
        next_action: "Review future cards in Signal Desk.",
      },
    ]);
    expect(actions[0]).not.toHaveProperty("argv");
    expect(actions[1]).not.toHaveProperty("argv");
  });

  it("sanitizes Desk action results for rendering", () => {
    expect(
      sanitizeDeskActionResult({
        schema_version: "desk_action_result_v1",
        action_id: "monitor_jobs_dry_run",
        status: " success ",
        title: " Practice scan complete ",
        detail: "Report ready.",
        display_command: " tgcs monitor run ",
        exit_code: 0,
        artifact_path: " output\\runs\\run-1\\report.html ",
        next_action: "Open the report.",
        finished_at: " 2026-05-10T16:30:00+08:00 ",
        source_access: {
          schema_version: "desk_source_access_health_v1",
          source_count: 8,
          checked_count: 6,
          accessible_count: 3,
          quiet_count: 1,
          inaccessible_count: 2,
          truncated_count: 2,
          probe_window_hours: 24,
          probe_window_hours_min: 24,
          probe_window_hours_max: 24,
          reason_counts: { cannot_resolve_entity: 2, bad: "ignored" },
        },
        stdout: "ignored",
      }),
    ).toEqual({
      schema_version: "desk_action_result_v1",
      action_id: "monitor_jobs_dry_run",
      status: "success",
      title: "Practice scan complete",
      detail: "Report ready.",
      display_command: "tgcs monitor run",
      exit_code: 0,
      artifact_path: "output/runs/run-1/report.html",
      next_action: "Open the report.",
      finished_at: "2026-05-10T16:30:00+08:00",
      source_access: {
        schema_version: "desk_source_access_health_v1",
        checked_at: "",
        source_count: 8,
        checked_count: 6,
        accessible_count: 3,
        quiet_count: 1,
        inaccessible_count: 2,
        truncated_count: 2,
        probe_window_hours: 24,
        probe_window_hours_min: 24,
        probe_window_hours_max: 24,
        reason_counts: { cannot_resolve_entity: 2 },
      },
    });

    expect(
      sanitizeDeskActionResult({
        schema_version: "desk_action_result_v1",
        action_id: "login_human",
        status: "needs_human",
        title: "Login requires terminal",
        display_command: "tgcs login",
        exit_code: "not-a-number",
      }),
    ).toMatchObject({
      schema_version: "desk_action_result_v1",
      action_id: "login_human",
      status: "needs_human",
      exit_code: null,
    });
    expect(sanitizeDeskActionResult({ status: "success", title: "Missing id" })).toBeNull();
    expect(
      sanitizeDeskActionResult({
        action_id: "monitor_jobs_dry_run",
        status: "success",
        title: "Missing schema",
        display_command: "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
      }),
    ).toBeNull();
    expect(sanitizeDeskActionResult({ action_id: "feedback_export", status: " ", title: "Bad status" })).toBeNull();
    for (const artifact_path of [
      "output/feedback/review-feedback.jsonl",
      "C:/Users/Administrator/private/report.html",
      "output/runs/run-1/../secret-report.html",
      "https://example.com/report.html",
    ]) {
      const payload = {
        schema_version: "desk_action_result_v1" as const,
        action_id: "monitor_jobs_dry_run",
        status: "success",
        title: "Report ready",
        display_command: "tgcs monitor run",
        artifact_path,
      };
      expect(sanitizeDeskActionResult(payload)?.artifact_path).toBe("");
      expect(sanitizeDeskModuleDeskActionResult(payload)?.artifact_path).toBe("");
      expect(sanitizeDashboardModuleDeskActionResult(payload)?.artifact_path).toBe("");
    }
  });

  it("sanitizes Desk scheduler status without trusting command output", () => {
    expect(
      sanitizeDeskSchedulerStatus({
        schema_version: "desk_scheduler_status_v1",
        available: true,
        installed: true,
        status: " installed ",
        task_label: " jobs-fast dry-run ",
        interval_minutes: 15.8,
        detail: " Checks every 15 minutes. ",
        next_action: " Review Inbox. ",
        checked_at: " 2026-05-10T00:00:00Z ",
        platform: " linux ",
        backend: " linux_systemd_user ",
        can_install: true,
        can_remove: false,
        stdout: "ignored",
        command: "schtasks /Query",
      }),
    ).toEqual({
      schema_version: "desk_scheduler_status_v1",
      available: true,
      installed: true,
      status: "installed",
      task_label: "jobs-fast dry-run",
      interval_minutes: 0,
      detail: "Checks every 15 minutes.",
      next_action: "Review Inbox.",
      checked_at: "2026-05-10T00:00:00Z",
      platform: "linux",
      backend: "linux_systemd_user",
      can_install: true,
      can_remove: false,
    });

    expect(sanitizeDeskSchedulerStatus({ available: true, installed: false })).toBeNull();
    expect(
      sanitizeDeskSchedulerStatus({
        available: true,
        installed: false,
        status: "not_installed",
        task_label: "jobs-fast dry-run",
        interval_minutes: 15,
        detail: "Background scan is off.",
        next_action: "Install scheduler.",
        checked_at: "2026-05-10T00:00:00Z",
      }),
    ).toBeNull();
  });

  it("sanitizes notification token status only when the local secret contract is explicit", () => {
    expect(
      sanitizeDeskNotificationTokenStatus({
        schema_version: "desk_notification_token_status_v1",
        configured: true,
        source: " local_keyring ",
        updated_at: " 2026-05-10T00:00:00Z ",
        env_configured: false,
        local_store_supported: true,
        local_store_configured: true,
        local_store_backend: " windows_credential_manager ",
        local_store_label: " Windows Credential Manager ",
        can_save: true,
        can_clear: true,
        platform: " win32 ",
        detail: " Telegram bot token is saved locally. ",
        token: "secret",
      }),
    ).toEqual({
      schema_version: "desk_notification_token_status_v1",
      configured: true,
      source: "local_keyring",
      updated_at: "2026-05-10T00:00:00Z",
      env_configured: false,
      local_store_supported: true,
      local_store_configured: true,
      local_store_backend: "windows_credential_manager",
      local_store_label: "Windows Credential Manager",
      can_save: true,
      can_clear: true,
      platform: "win32",
      detail: "Telegram bot token is saved locally.",
    });
    expect(
      sanitizeDeskNotificationTokenStatus({
        configured: false,
        source: "missing",
        env_configured: false,
        local_store_supported: true,
        local_store_configured: false,
        can_save: true,
        can_clear: false,
        platform: "win32",
        detail: "Telegram bot token is not configured.",
      }),
    ).toBeNull();
    expect(
      sanitizeDeskNotificationTokenStatus({
        schema_version: "desk_notification_token_status_v1",
        configured: false,
        source: "missing",
        env_configured: false,
        local_store_supported: true,
        local_store_configured: false,
        can_save: true,
        can_clear: false,
        platform: "",
        detail: "Telegram bot token is not configured.",
      }),
    ).toBeNull();
  });

  it("sanitizes Desk Telegram status without trusting secret backend fields", () => {
    expect(
      sanitizeDeskTelegramStatus({
        schema_version: "desk_telegram_status_v1",
        credentials_ready: true,
        session_ready: false,
        login_state: " code_sent ",
        detail: "Code sent.",
        next_step: "Enter code.",
        config_path: " ~/.config/tgcli/config.toml ",
        session_path: " ~/.config/tgcli/session ",
        api_hash: "secret",
      }),
    ).toEqual({
      schema_version: "desk_telegram_status_v1",
      credentials_ready: true,
      session_ready: false,
      login_state: "code_sent",
      detail: "Code sent.",
      next_step: "Enter code.",
      config_path: "~/.config/tgcli/config.toml",
      session_path: "~/.config/tgcli/session",
    });
    expect(sanitizeDeskTelegramStatus({ credentials_ready: true })).toBeNull();
    expect(
      sanitizeDeskTelegramStatus({
        schema_version: "desk_telegram_status_v1",
        credentials_ready: true,
        session_ready: false,
        login_state: "ready_for_code",
        detail: "",
        next_step: "Send a code.",
        config_path: "~/.config/tgcli/config.toml",
        session_path: "~/.config/tgcli/session",
      }),
    ).toBeNull();
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
