import { afterEach, describe, expect, it, vi } from "vitest";

import {
  emptyDashboardState,
  sanitizeDeskActions,
  sanitizeDeskActionResult,
  sanitizeDeskAiSettingsStatus,
  sanitizeDeskSchedulerStatus,
  sanitizeDeskSourcesResult,
  sanitizeDeskTelegramStatus,
  sanitizeDeliveryTestResult,
  sanitizeDashboardState,
  sanitizeFeedbackExportResult,
  sanitizeFeedbackProfileSuggestionsResult,
  sanitizeGitUpdateStatus,
  sanitizeInboxCards,
  sanitizeSourceImportResult,
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
      delivery_targets: [
        {
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
    expect(
      sanitizeFeedbackExportResult({
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
    expect(
      sanitizeFeedbackProfileSuggestionsResult({
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
    expect(sanitizeFeedbackProfileSuggestionsResult({ created_count: -1, existing_count: 0, skipped_count: 0 })).toBeNull();
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
        action_id: "feedback_export",
        status: " success ",
        title: " Feedback exported ",
        detail: "2 records ready.",
        display_command: " tgcs feedback export ",
        exit_code: 0,
        artifact_path: " output/feedback/review-feedback.jsonl ",
        next_action: "Share the export.",
        finished_at: " 2026-05-10T16:30:00+08:00 ",
        stdout: "ignored",
      }),
    ).toEqual({
      schema_version: "desk_action_result_v1",
      action_id: "feedback_export",
      status: "success",
      title: "Feedback exported",
      detail: "2 records ready.",
      display_command: "tgcs feedback export",
      exit_code: 0,
      artifact_path: "output/feedback/review-feedback.jsonl",
      next_action: "Share the export.",
      finished_at: "2026-05-10T16:30:00+08:00",
    });

    expect(
      sanitizeDeskActionResult({
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
    expect(sanitizeDeskActionResult({ action_id: "feedback_export", status: " ", title: "Bad status" })).toBeNull();
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
