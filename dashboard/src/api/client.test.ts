import { afterEach, describe, expect, it, vi } from "vitest";

import {
  checkGitUpdates,
  clearFeedbackDecisions,
  createProfileFromBrief,
  errorMessage,
  detectDeskDeliveryChatId,
  exportFeedback,
  generateFeedbackProfileSuggestions,
  clearDeskNotificationToken,
  loadDashboardState,
  loadDeskActions,
  loadDeskAiSettingsStatus,
  loadDeskNotificationTokenStatus,
  loadDeskSources,
  loadDeskSchedulerStatus,
  loadDeskTelegramStatus,
  normalizeDashboardError,
  previewSourceAssistant,
  pullLatestGit,
  runDeskAction,
  saveDeskNotificationToken,
  saveDeskTelegramCredentials,
  saveDeskDeliveryTarget,
  testDeskDeliveryTarget,
} from "./client";

function mockJsonResponse(payload: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("dashboard API errors", () => {
  it("turns generic server failures into local recovery guidance", () => {
    expect(normalizeDashboardError("Internal Server Error")).toBe(
      "Local dashboard API hit an internal error. Refresh once; if it repeats, restart Signal Desk.",
    );
    expect(normalizeDashboardError("HTTP 500")).toContain("restart Signal Desk");
  });

  it("turns network failures into a reachable next step", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toBe(
      "Local dashboard API is unreachable. Start or restart Signal Desk, then refresh.",
    );
  });

  it("keeps specific validation errors readable", () => {
    expect(errorMessage(new Error("Use 1 to 8 topic tags."))).toBe("Use 1 to 8 topic tags.");
    expect(errorMessage(new Error("Invalid source library response"))).toBe(
      "Local dashboard API returned data this screen cannot read. Refresh once; if it repeats, restart Signal Desk.",
    );
  });
});

describe("dashboard API contract validation", () => {
  it("throws on malformed dashboard state payloads instead of sanitizing to empty state", async () => {
    mockJsonResponse({
      schema_version: "dashboard_state_v1",
      profiles: "bad",
      inbox: [],
      runs: [],
      delivery_targets: [],
      profile_patch_suggestions: [],
      source_stats: [],
      source_insights: [],
    });

    await expect(loadDashboardState()).rejects.toThrow("Invalid dashboard state response");
  });

  it("throws on malformed Desk actions payloads instead of returning no controls", async () => {
    mockJsonResponse({ schema_version: "desk_actions_v1", actions: "bad" });

    await expect(loadDeskActions()).rejects.toThrow("Invalid Desk actions response");
  });

  it("throws on schema-less source library payloads instead of accepting sanitizer fallback", async () => {
    mockJsonResponse({
      sources: {
        registry_path: ".tgcs/sources.json",
        source_count: 0,
        enabled_count: 0,
        topics: [],
        sources: [],
      },
    });

    await expect(loadDeskSources()).rejects.toThrow("Invalid source library response");
  });

  it("throws on schema-less source assistant payloads instead of accepting sanitizer fallback", async () => {
    mockJsonResponse({
      result: {
        dry_run: true,
        written: false,
        topic: "jobs",
        registry_path: ".tgcs/sources.json",
        preview_sources: [],
        resolved_plan: { add: [], remove: [], disable: [], enable: [] },
      },
    });

    await expect(previewSourceAssistant("add @remote_jobs", "jobs")).rejects.toThrow("Invalid source assistant response");
  });

  it("throws on schema-less delivery target payloads instead of accepting sanitizer fallback", async () => {
    mockJsonResponse({
      target: {
        target_id: "telegram-bot-default",
        type: "telegram_bot",
        enabled: true,
        config: { chat_id: "123456" },
        updated_at: "2026-05-10T00:00:00Z",
      },
    });

    await expect(saveDeskDeliveryTarget("telegram-bot-default", "123456", true)).rejects.toThrow(
      "Invalid notification target response",
    );
  });

  it("throws on empty AI settings payloads instead of rendering an unconfigured state", async () => {
    mockJsonResponse({ ai: {} });

    await expect(loadDeskAiSettingsStatus()).rejects.toThrow("Invalid AI API settings response");
  });

  it("throws on incomplete AI settings payloads with only a schema version", async () => {
    mockJsonResponse({ ai: { schema_version: "desk_ai_settings_status_v1" } });

    await expect(loadDeskAiSettingsStatus()).rejects.toThrow("Invalid AI API settings response");
  });

  it("throws on schema-less status payloads instead of rendering fallback scheduler, token, or Telegram state", async () => {
    mockJsonResponse({
      scheduler: {
        available: true,
        installed: false,
        status: "not_installed",
        task_label: "jobs-fast dry-run",
        interval_minutes: 15,
        detail: "Background scan is off.",
        next_action: "Install scheduler.",
        checked_at: "2026-05-13T00:00:00Z",
      },
    });

    await expect(loadDeskSchedulerStatus()).rejects.toThrow("Invalid scheduler status response");

    mockJsonResponse({
      token: {
        configured: false,
        source: "missing",
        env_configured: false,
        local_store_supported: true,
        local_store_configured: false,
        can_save: true,
        can_clear: false,
        platform: "win32",
        detail: "Telegram bot token is not configured.",
      },
    });

    await expect(loadDeskNotificationTokenStatus()).rejects.toThrow("Invalid notification token response");

    mockJsonResponse({
      telegram: {
        credentials_ready: true,
        session_ready: false,
        login_state: "ready_for_code",
        detail: "Credentials are saved.",
        next_step: "Send a code.",
        config_path: "~/.config/tgcli/config.toml",
        session_path: "~/.config/tgcli/session",
      },
    });

    await expect(loadDeskTelegramStatus()).rejects.toThrow("Invalid Telegram status response");
  });

  it("throws on schema-less notification token and Telegram mutation responses", async () => {
    mockJsonResponse({
      token: {
        configured: true,
        source: "local_keyring",
        env_configured: false,
        local_store_supported: true,
        local_store_configured: true,
        can_save: true,
        can_clear: true,
        platform: "win32",
        detail: "Telegram bot token is saved locally.",
      },
    });

    await expect(saveDeskNotificationToken("bot-token")).rejects.toThrow("Invalid notification token response");

    mockJsonResponse({
      token: {
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
      },
    });

    await expect(clearDeskNotificationToken()).rejects.toThrow("Invalid notification token response");

    mockJsonResponse({
      telegram: {
        credentials_ready: true,
        session_ready: false,
        login_state: "code_sent",
        detail: "Telegram sent a verification code.",
        next_step: "Enter the code.",
        config_path: "~/.config/tgcli/config.toml",
        session_path: "~/.config/tgcli/session",
      },
    });

    await expect(saveDeskTelegramCredentials("123", "hash")).rejects.toThrow("Invalid Telegram credentials response");
  });

  it("throws on schema-less Desk action results instead of accepting sanitizer fallback", async () => {
    mockJsonResponse({
      result: {
        action_id: "monitor_jobs_dry_run",
        status: "success",
        title: "Practice scan finished",
        display_command: "tgcs monitor run --profile-id jobs-fast --delivery-mode dry-run",
      },
    });

    await expect(runDeskAction("monitor_jobs_dry_run")).rejects.toThrow("Invalid Desk action response");
  });

  it("throws when a Desk action result belongs to another action", async () => {
    mockJsonResponse({
      result: {
        schema_version: "desk_action_result_v1",
        action_id: "feedback_export",
        status: "success",
        title: "Exported feedback",
        display_command: "tgcs feedback export",
      },
    });

    await expect(runDeskAction("monitor_jobs_dry_run")).rejects.toThrow("Invalid Desk action response");
  });

  it("throws on schema-less delivery test results", async () => {
    mockJsonResponse({
      result: {
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        ok: true,
        status: "dry_run",
      },
    });

    await expect(testDeskDeliveryTarget("telegram-bot-default", "123456")).rejects.toThrow(
      "Invalid notification test response",
    );
  });

  it("throws when a delivery test result belongs to another target", async () => {
    mockJsonResponse({
      result: {
        schema_version: "desk_delivery_test_result_v1",
        target_id: "other-target",
        target_type: "telegram_bot",
        ok: true,
        status: "dry_run",
      },
    });

    await expect(testDeskDeliveryTarget("telegram-bot-default", "123456")).rejects.toThrow(
      "Invalid notification test response",
    );
  });

  it("throws on schema-less chat detection results", async () => {
    mockJsonResponse({
      result: {
        target_id: "telegram-bot-default",
        target_type: "telegram_bot",
        ok: true,
        status: "detected",
        source: "updates",
      },
    });

    await expect(detectDeskDeliveryChatId("telegram-bot-default")).rejects.toThrow(
      "Invalid notification chat detection response",
    );
  });

  it("throws when a chat detection result belongs to another target", async () => {
    mockJsonResponse({
      result: {
        schema_version: "desk_delivery_chat_detection_v1",
        target_id: "other-target",
        target_type: "telegram_bot",
        ok: true,
        status: "detected",
        source: "updates",
      },
    });

    await expect(detectDeskDeliveryChatId("telegram-bot-default")).rejects.toThrow(
      "Invalid notification chat detection response",
    );
  });

  it("throws on schema-less Git mutation results instead of accepting status-shaped payloads", async () => {
    mockJsonResponse({
      git: {
        status: "behind",
        message: "1 upstream commit available.",
        branch: "main",
        ahead: 0,
        behind: 1,
        dirty: false,
        dirty_count: 0,
        pull_allowed: true,
        checked_at: "2026-05-13T00:00:00Z",
      },
    });

    await expect(checkGitUpdates()).rejects.toThrow("Invalid git status response");

    mockJsonResponse({
      git: {
        schema_version: "git_update_status_v0",
        status: "up_to_date",
        message: "Local branch is up to date.",
        branch: "main",
        ahead: 0,
        behind: 0,
        dirty: false,
        dirty_count: 0,
        pull_allowed: false,
        checked_at: "2026-05-13T00:00:00Z",
      },
    });

    await expect(pullLatestGit()).rejects.toThrow("Invalid git status response");
  });

  it("throws on schema-less feedback mutation results instead of accepting plausible counters", async () => {
    mockJsonResponse({
      export: {
        feedback_count: 1,
        output_path: "output/feedback/review-feedback.jsonl",
      },
    });

    await expect(exportFeedback()).rejects.toThrow("Invalid feedback export response");

    mockJsonResponse({
      suggestions: {
        created_count: 1,
        existing_count: 0,
        skipped_count: 0,
      },
    });

    await expect(generateFeedbackProfileSuggestions()).rejects.toThrow(
      "Invalid feedback profile suggestions response",
    );

    mockJsonResponse({
      feedback: {
        schema_version: "feedback_clear_result_v1",
        cleared_count: -1,
      },
    });

    await expect(clearFeedbackDecisions()).rejects.toThrow("Invalid feedback clear response");
  });

  it("throws on schema-less profile creation results instead of trusting profile-shaped payloads", async () => {
    mockJsonResponse({
      profile: {
        profile_id: "jobs-fast",
        display_name: "Jobs Fast",
        profile_path: "profiles/jobs-fast.md",
        created: true,
        detail: "Created profile.",
        next_action: "Review the draft.",
      },
    });

    await expect(createProfileFromBrief({ brief: "Track remote TypeScript roles." })).rejects.toThrow(
      "Invalid profile creation response",
    );
  });
});
