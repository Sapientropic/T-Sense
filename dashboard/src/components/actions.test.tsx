import { describe, expect, it } from "vitest";

import { buildJourneySteps, buildStartSummary, notificationReadiness } from "./actions";
import {
  buildJourneySteps as buildJourneyStepsFromModel,
  buildStartSummary as buildStartSummaryFromModel,
  notificationReadiness as notificationReadinessFromModel,
} from "./actions/journey-model";
import type { DeliveryTarget, DeskAction, DeskActionResult, DeskSchedulerStatus } from "../domain/types";

function action(actionId: string, runMode = "execute"): DeskAction {
  return {
    schema_version: "desk_action_v1",
    action_id: actionId,
    group: "Setup",
    title: actionId,
    detail: `${actionId} detail`,
    run_mode: runMode,
    display_command: `tgcs ${actionId}`,
    next_action: `${actionId} next`,
  };
}

function result(actionId: string, status = "success"): DeskActionResult {
  return {
    schema_version: "desk_action_result_v1",
    action_id: actionId,
    status,
    title: actionId,
    detail: `${actionId} detail`,
    display_command: `tgcs ${actionId}`,
    exit_code: 0,
    artifact_path: "",
    next_action: `${actionId} next`,
    finished_at: "2026-05-10T00:00:00Z",
  };
}

function schedulerStatus(installed: boolean): DeskSchedulerStatus {
  return {
    schema_version: "desk_scheduler_status_v1",
    available: true,
    installed,
    status: installed ? "installed" : "not_installed",
    task_label: "jobs-fast dry-run",
    interval_minutes: 15,
    detail: installed ? "Automatic practice scans are on every 15 minutes." : "Automatic practice scans are off.",
    next_action: installed ? "You can turn them off." : "Turn on auto scan.",
    checked_at: "2026-05-10T00:00:00Z",
  };
}

function deliveryTarget(overrides: Partial<DeliveryTarget>): DeliveryTarget {
  return {
    schema_version: "delivery_target_v1",
    target_id: "telegram-bot-default",
    type: "telegram_bot",
    enabled: false,
    config: { chat_id: "@desk_signal" },
    updated_at: "2026-05-10T00:00:00Z",
    ...overrides,
  };
}

const actions = [
  action("init_jobs"),
  action("demo_render"),
  action("doctor_jobs"),
  action("sources_validate"),
  action("sources_probe_access"),
  action("sources_pause_inaccessible", "confirm_execute"),
  action("sources_keep_accessible", "confirm_execute"),
  action("sources_import_jobs"),
  action("monitor_jobs_dry_run"),
  action("feedback_export"),
  action("schedule_preview"),
  action("schedule_install_dry_run", "confirm_execute"),
  action("schedule_remove_dry_run", "confirm_execute"),
  action("login_human", "needs_human"),
  action("live_delivery_human", "needs_human"),
  action("schedule_install_human", "needs_human"),
];

const telegramReady = {
  schema_version: "desk_telegram_status_v1" as const,
  credentials_ready: true,
  session_ready: true,
  login_state: "authorized",
  detail: "Connected.",
  next_step: "Run scan.",
  config_path: "~/.config/tgcli/config.toml",
  session_path: "~/.config/tgcli/session",
};

describe("Signal Desk journey", () => {
  it("keeps the split journey model helpers on the public actions API", () => {
    expect(buildJourneyStepsFromModel).toBe(buildJourneySteps);
    expect(buildStartSummaryFromModel).toBe(buildStartSummary);
    expect(notificationReadinessFromModel).toBe(notificationReadiness);
  });

  it("summarizes notification readiness without exposing the chat id", () => {
    expect(notificationReadiness([])).toMatchObject({ value: "Needs chat ID" });
    expect(notificationReadiness([deliveryTarget({ config: {} })])).toMatchObject({ value: "Needs chat ID" });
    expect(notificationReadiness([deliveryTarget({ enabled: true, config: { chat_id: "   " } })])).toMatchObject({
      value: "Needs chat ID",
    });
    expect(notificationReadiness([deliveryTarget({ enabled: true, config: { chat_id: 123456 } })])).toMatchObject({
      value: "Needs chat ID",
    });
    expect(notificationReadiness([deliveryTarget({ enabled: false })])).toMatchObject({ value: "Muted" });
    expect(notificationReadiness([deliveryTarget({ enabled: true })])).toMatchObject({ value: "Enabled" });
    expect(notificationReadiness([deliveryTarget({ enabled: true })]).detail).not.toContain("@desk_signal");
    expect(notificationReadiness([deliveryTarget({ type: "webhook", enabled: true })])).toMatchObject({ value: "Enabled" });
  });

  it("starts with workspace setup when profiles are missing", () => {
    const steps = buildJourneySteps(actions, {}, { stage: "needs_profiles", has_profiles: false, has_runs: false }, null);

    const workspace = steps.find((step) => step.key === "workspace");
    const firstRun = steps.find((step) => step.key === "first-run");

    expect(workspace?.state).toBe("active");
    expect(workspace?.buttons[0]).toMatchObject({ actionId: "init_jobs", label: "Prepare files" });
    expect(firstRun?.state).toBe("blocked");
  });

  it("promotes first scan after workspace exists", () => {
    const steps = buildJourneySteps(actions, {}, { stage: "needs_first_run", has_profiles: true, has_runs: false }, telegramReady);

    expect(steps.find((step) => step.key === "workspace")?.state).toBe("done");
    expect(steps.find((step) => step.key === "first-run")).toMatchObject({
      state: "active",
      stateLabel: "Next",
    });
  });

  it("puts Telegram before source files and avoids export jargon", () => {
    const steps = buildJourneySteps(actions, {}, { stage: "ready", has_profiles: true, has_runs: true }, telegramReady);

    expect(steps.map((step) => step.key)).toEqual([
      "demo",
      "telegram",
      "workspace",
      "first-run",
      "automation",
      "feedback",
    ]);
    expect(steps.find((step) => step.key === "feedback")?.buttons[0]).toMatchObject({
      label: "Generate profile suggestions",
    });
  });

  it("separates source syntax checks from real Telegram access checks", () => {
    const steps = buildJourneySteps(
      actions,
      {},
      {
        stage: "needs_source_access",
        has_profiles: true,
        has_runs: true,
        checks: [
          {
            check_id: "source_access",
            label: "Source access",
            status: "blocked",
            detail: "Access check: 2 recently active, 1 quiet in the last 24h, 5 inaccessible across 8 checked sources.",
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
      telegramReady,
    );

    const workspace = steps.find((step) => step.key === "workspace");

    expect(workspace?.detail).toBe("Some saved channels cannot be read. Check channels, then pause unreadable ones.");
    expect(workspace?.detailTitle).toContain("2 recently active");
    expect(workspace?.buttons.map((button) => button.label)).toEqual([
      "Refresh files",
      "Fix channels",
      "Check channels",
      "Pause unreadable",
      "Keep active only",
      "Check file format",
    ]);
  });

  it("offers source repair immediately after a source access check finds problems", () => {
    const steps = buildJourneySteps(
      actions,
      {
        sources_probe_access: {
          ...result("sources_probe_access"),
          detail: "Access check: 3 accessible, 1 quiet, 2 inaccessible across 6 checked sources.",
          source_access: {
            schema_version: "desk_source_access_health_v1",
            source_count: 6,
            checked_count: 6,
            accessible_count: 3,
            quiet_count: 1,
            inaccessible_count: 2,
            truncated_count: 0,
          },
        },
      },
      { stage: "needs_first_run", has_profiles: true, has_runs: false },
      telegramReady,
    );

    const workspace = steps.find((step) => step.key === "workspace");

    expect(workspace?.detail).toBe("Some saved channels cannot be read. Check channels, then pause unreadable ones.");
    expect(workspace?.detailTitle).toContain("2 inaccessible");
    expect(workspace?.buttons.map((button) => button.label)).toContain("Pause unreadable");
    expect(workspace?.buttons.map((button) => button.label)).toContain("Keep active only");
  });

  it("keeps commands as advanced fallback data instead of primary controls", () => {
    const steps = buildJourneySteps(actions, {}, { stage: "ready", has_profiles: true, has_runs: true }, telegramReady);

    const automation = steps.find((step) => step.key === "automation");

    expect(automation?.buttons.map((button) => button.label)).toEqual([
      "Preview schedule",
      "Turn on auto scan",
      "Notifications",
    ]);
    expect(automation?.buttons.map((button) => button.label)).not.toContain("Turn off");
    expect(automation?.stateLabel).toBe("Off");
    expect(automation?.advancedActionIds).toContain("schedule_preview");
    expect(automation?.advancedActionIds).not.toContain("live_delivery_human");
  });

  it("keeps unsupported scheduler installs on the manual preview path", () => {
    const unsupportedScheduler: DeskSchedulerStatus = {
      ...schedulerStatus(false),
      available: false,
      status: "manual",
      backend: "manual_cron_preview",
      can_install: false,
      can_remove: false,
    };
    const steps = buildJourneySteps(
      actions,
      {},
      { stage: "ready", has_profiles: true, has_runs: true },
      telegramReady,
      unsupportedScheduler,
    );

    const automation = steps.find((step) => step.key === "automation");

    expect(automation?.state).toBe("manual");
    expect(automation?.stateLabel).toBe("Manual");
    expect(automation?.detail).toContain("manual schedule preview");
    expect(automation?.buttons.map((button) => button.label)).toEqual([
      "Preview schedule",
      "Notifications",
    ]);
  });

  it("replaces the automation turn-on control after a successful Desk install", () => {
    const steps = buildJourneySteps(
      actions,
      { schedule_install_dry_run: result("schedule_install_dry_run") },
      { stage: "ready", has_profiles: true, has_runs: true },
      telegramReady,
    );

    const automation = steps.find((step) => step.key === "automation");

    expect(automation?.buttons.map((button) => button.label)).toEqual([
      "Preview schedule",
      "Turn off auto scan",
      "Notifications",
    ]);
  });

  it("uses scheduler status as the automation source of truth", () => {
    const steps = buildJourneySteps(
      actions,
      {},
      { stage: "ready", has_profiles: true, has_runs: true },
      telegramReady,
      schedulerStatus(true),
    );

    const automation = steps.find((step) => step.key === "automation");

    expect(automation).toMatchObject({
      title: "Automation",
      stateLabel: "Auto scan on",
      detail: expect.stringContaining("Automatic practice scans are on"),
    });
    expect(automation?.buttons.map((button) => button.label)).toEqual([
      "Preview schedule",
      "Turn off auto scan",
      "Notifications",
    ]);
  });

  it("shows notification readiness in the automation guidance", () => {
    const liveSteps = buildJourneySteps(
      actions,
      {},
      { stage: "ready", has_profiles: true, has_runs: true },
      telegramReady,
      schedulerStatus(false),
      [deliveryTarget({ enabled: true })],
    );
    const mutedSteps = buildJourneySteps(
      actions,
      {},
      { stage: "ready", has_profiles: true, has_runs: true },
      telegramReady,
      schedulerStatus(false),
      [deliveryTarget({ enabled: false })],
    );
    const missingSteps = buildJourneySteps(
      actions,
      {},
      { stage: "ready", has_profiles: true, has_runs: true },
      telegramReady,
      schedulerStatus(false),
      [deliveryTarget({ config: {} })],
    );

    expect(liveSteps.find((step) => step.key === "automation")?.detail).toContain("Notifications: Enabled");
    expect(mutedSteps.find((step) => step.key === "automation")?.detail).toContain("Notifications: Muted");
    expect(missingSteps.find((step) => step.key === "automation")?.detail).toContain("Notifications: Needs chat ID");
  });

  it("turns missing or muted notification status into a Settings shortcut", () => {
    const baseSetup = { stage: "ready", has_profiles: true, has_runs: true };
    const steps = buildJourneySteps(actions, {}, baseSetup, telegramReady, schedulerStatus(false));
    const missingSummary = buildStartSummary(steps, baseSetup, telegramReady, schedulerStatus(false), [
      deliveryTarget({ config: {} }),
    ]);
    const mutedSummary = buildStartSummary(steps, baseSetup, telegramReady, schedulerStatus(false), [
      deliveryTarget({ enabled: false }),
    ]);
    const enabledSummary = buildStartSummary(steps, baseSetup, telegramReady, schedulerStatus(false), [
      deliveryTarget({ enabled: true }),
    ]);

    expect(missingSummary.find((item) => item.label === "Notifications")).toMatchObject({
      value: "Needs chat ID",
      actionId: "live_delivery_human",
      actionLabel: "Add chat ID",
    });
    expect(mutedSummary.find((item) => item.label === "Notifications")).toMatchObject({
      value: "Muted",
      actionId: "live_delivery_human",
      actionLabel: "Open settings",
    });
    const enabledNotification = enabledSummary.find((item) => item.label === "Notifications");
    expect(enabledNotification).toMatchObject({ value: "Enabled" });
    expect(enabledNotification?.actionId).toBeUndefined();
  });

  it("keeps Review ahead of automation when cards are pending", () => {
    const baseSetup = { stage: "needs_delivery_target", has_profiles: true, has_runs: true };
    const steps = buildJourneySteps(actions, {}, baseSetup, telegramReady, schedulerStatus(false), [
      deliveryTarget({ config: {} }),
    ]);
    const summary = buildStartSummary(steps, baseSetup, telegramReady, schedulerStatus(false), [], 3);

    expect(summary.find((item) => item.label === "Next")).toMatchObject({
      value: "Review 3 cards",
    });
  });

  it("does not let optional Telegram setup seize the ready-state path", () => {
    const readyButDisconnected = { ...telegramReady, session_ready: false, credentials_ready: false };
    const baseSetup = { stage: "ready", has_profiles: true, has_runs: true };
    const steps = buildJourneySteps(actions, {}, baseSetup, readyButDisconnected, schedulerStatus(false));
    const summary = buildStartSummary(steps, baseSetup, readyButDisconnected, schedulerStatus(false), [], 2);

    expect(steps.find((step) => step.key === "telegram")).toMatchObject({
      state: "ready",
      stateLabel: "Optional",
    });
    expect(summary.find((item) => item.label === "Next")).toMatchObject({
      value: "Review 2 cards",
    });
  });

  it("blocks first scan until Telegram is connected", () => {
    const steps = buildJourneySteps(actions, {}, { stage: "needs_first_run", has_profiles: true, has_runs: false }, {
      ...telegramReady,
      session_ready: false,
      login_state: "ready_for_code",
    });

    expect(steps.find((step) => step.key === "telegram")).toMatchObject({ state: "active" });
    expect(steps.find((step) => step.key === "first-run")).toMatchObject({
      state: "blocked",
      stateLabel: "Connect Telegram first",
    });
  });

  it("keeps Telegram active while a two-step password is required", () => {
    const steps = buildJourneySteps(actions, {}, { stage: "needs_first_run", has_profiles: true, has_runs: false }, {
      ...telegramReady,
      session_ready: false,
      login_state: "needs_password",
    });

    expect(steps.find((step) => step.key === "telegram")).toMatchObject({
      state: "active",
      stateLabel: "Check before scan",
    });
    expect(steps.find((step) => step.key === "first-run")?.state).toBe("blocked");
  });
});
