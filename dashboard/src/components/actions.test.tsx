import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { buildJourneySteps, buildStartSummary, notificationReadiness } from "./actions";
import {
  buildJourneySteps as buildJourneyStepsFromModel,
  buildStartSummary as buildStartSummaryFromModel,
  notificationReadiness as notificationReadinessFromModel,
} from "./actions/journey-model";
import { JourneyStepCard } from "./actions/journey-step-card";
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
    detail: installed ? "Automatic AI reviews are on every 15 minutes." : "Automatic AI reviews are off.",
    next_action: installed ? "You can turn them off." : "Turn on auto review.",
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

  it("starts with AI API setup before profile or source work", () => {
    const steps = buildJourneySteps(actions, {}, { stage: "needs_ai_key", has_profiles: false, has_runs: false }, telegramReady);
    const summary = buildStartSummary(steps, { stage: "needs_ai_key", has_profiles: false, has_runs: false }, telegramReady);

    expect(steps[0]).toMatchObject({
      key: "ai",
      title: "Connect AI matching",
      state: "active",
      stateLabel: "Start here",
    });
    expect(steps.find((step) => step.key === "workspace")?.state).toBe("blocked");
    expect(summary.find((item) => item.label === "Next")).toMatchObject({
      value: "Connect AI matching",
      actionId: "settings_ai",
      actionLabel: "Add AI API key",
    });
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
      "ai",
      "telegram",
      "workspace",
      "first-run",
      "automation",
      "feedback",
    ]);
    expect(steps.find((step) => step.key === "feedback")?.buttons[0]).toMatchObject({
      label: "Suggest rules",
    });
    expect(steps.find((step) => step.key === "telegram")?.detail).toContain("Telegram is ready");
    expect(steps.find((step) => step.key === "telegram")?.detail).not.toContain("Connect Telegram first");
    expect(steps.find((step) => step.key === "demo")).toBeUndefined();
    expect(steps.find((step) => step.key === "ai")?.buttons[0]).toMatchObject({
      actionId: "settings_ai",
      label: "AI API settings",
    });
  });

  it("keeps the completed AI step actionable as a Settings shortcut", () => {
    const aiStep = buildJourneySteps(actions, {}, { stage: "ready", has_profiles: true, has_runs: true }, telegramReady).find(
      (step) => step.key === "ai",
    )!;
    const html = renderToStaticMarkup(
      <JourneyStepCard
        activeActions={[]}
        actionMap={new Map(actions.map((item) => [item.action_id, item]))}
        anyBusy={false}
        busyActionId=""
        index={1}
        onRun={async () => undefined}
        results={{}}
        step={aiStep}
        telegram={{
          status: telegramReady,
          busy: "",
          error: "",
          saveCredentials: async () => telegramReady,
          sendCode: async () => telegramReady,
          verifyCode: async () => telegramReady,
          refresh: async () => telegramReady,
          cancelLogin: async () => telegramReady,
        }}
      />,
    );

    expect(html).toContain("AI API settings");
    expect(html).toContain('title="AI API settings"');
  });

  it("requires both app credentials and Telegram login before calling Telegram ready", () => {
    const setup = { stage: "needs_first_run", has_profiles: true, has_runs: false };
    const sessionOnly = {
      ...telegramReady,
      credentials_ready: false,
      session_ready: true,
      login_state: "credentials_missing",
      detail: "Telegram login is saved, but app credentials are missing.",
    };
    const steps = buildJourneySteps(actions, {}, setup, sessionOnly);
    const summary = buildStartSummary(steps, setup, sessionOnly);

    expect(steps.find((step) => step.key === "telegram")).toMatchObject({
      state: "active",
      stateLabel: "Check before scan",
      detail: expect.stringContaining("app credentials are missing"),
    });
    expect(steps.find((step) => step.key === "first-run")).toMatchObject({
      state: "blocked",
      stateLabel: "Connect Telegram first",
    });
    expect(summary.find((item) => item.label === "Telegram")).toMatchObject({
      value: "Missing app details",
    });
  });

  it("does not expose copied commands inside Start journey steps", () => {
    const step = buildJourneySteps(
      actions,
      {
        doctor_jobs: {
          ...result("doctor_jobs", "failed"),
          detail: "Setup check could not finish.",
        },
      },
      { stage: "ready", has_profiles: true, has_runs: true },
      telegramReady,
    ).find((item) => item.key === "telegram")!;
    const html = renderToStaticMarkup(
      <JourneyStepCard
        activeActions={[]}
        actionMap={new Map(actions.map((item) => [item.action_id, item]))}
        anyBusy={false}
        busyActionId=""
        index={2}
        onRun={async () => undefined}
        results={{ doctor_jobs: result("doctor_jobs", "failed") }}
        step={step}
        telegram={{
          status: telegramReady,
          busy: "",
          error: "",
          saveCredentials: async () => telegramReady,
          sendCode: async () => telegramReady,
          verifyCode: async () => telegramReady,
          refresh: async () => telegramReady,
          cancelLogin: async () => telegramReady,
        }}
      />,
    );

    expect(html).not.toContain("Advanced command");
    expect(html).not.toContain("COPY COMMAND");
    expect(html).not.toContain("tgcs doctor");
    expect(html).not.toContain("doctor_jobs detail");
  });

  it("hides stale setup failures after the current journey state has recovered", () => {
    const sourceAccessBlocked = {
      ...result("sources_probe_access", "blocked"),
      title: "Source access check blocked",
      detail: "Telegram API credentials are not configured.",
      next_action: "Connect Telegram from Start, then check source access again.",
    };
    const step = buildJourneySteps(
      actions,
      { sources_probe_access: sourceAccessBlocked },
      {
        stage: "ready",
        has_profiles: true,
        has_runs: true,
        checks: [
          {
            check_id: "source_access",
            label: "Source access",
            status: "done",
            detail: "Access check: 2 recently active, 1 quiet in the last 24h.",
            source_access: {
              schema_version: "desk_source_access_health_v1",
              source_count: 3,
              checked_count: 3,
              accessible_count: 2,
              quiet_count: 1,
              inaccessible_count: 0,
              truncated_count: 0,
              probe_window_hours: 24,
            },
          },
        ],
      },
      telegramReady,
    ).find((item) => item.key === "workspace")!;
    const html = renderToStaticMarkup(
      <JourneyStepCard
        activeActions={[]}
        actionMap={new Map(actions.map((item) => [item.action_id, item]))}
        anyBusy={false}
        busyActionId=""
        index={3}
        onRun={async () => undefined}
        results={{ sources_probe_access: sourceAccessBlocked }}
        step={step}
        telegram={{
          status: telegramReady,
          busy: "",
          error: "",
          saveCredentials: async () => telegramReady,
          sendCode: async () => telegramReady,
          verifyCode: async () => telegramReady,
          refresh: async () => telegramReady,
          cancelLogin: async () => telegramReady,
        }}
      />,
    );

    expect(html).toContain("Some saved channels are quiet");
    expect(html).not.toContain("Source access check blocked");
    expect(html).not.toContain("Telegram API credentials are not configured");
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

    expect(workspace?.detail).toBe("Some saved channels cannot be read. Check access, then pause unreadable ones.");
    expect(workspace?.detailTitle).toContain("2 recently active");
    expect(workspace?.buttons.map((button) => button.label)).toEqual([
      "Refresh files",
      "Fix channels",
      "Check access",
      "Pause unreadable",
      "Active only",
      "File check",
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

    expect(workspace?.detail).toBe("Some saved channels cannot be read. Check access, then pause unreadable ones.");
    expect(workspace?.detailTitle).toContain("2 inaccessible");
    expect(workspace?.buttons.map((button) => button.label)).toContain("Pause unreadable");
    expect(workspace?.buttons.map((button) => button.label)).toContain("Active only");
  });

  it("keeps commands as advanced fallback data instead of primary controls", () => {
    const steps = buildJourneySteps(actions, {}, { stage: "ready", has_profiles: true, has_runs: true }, telegramReady);

    const automation = steps.find((step) => step.key === "automation");

    expect(automation?.buttons.map((button) => button.label)).toEqual([
      "Preview",
      "Turn on",
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
      "Preview",
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
      "Preview",
      "Turn off",
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
      stateLabel: "Auto review on",
      detail: expect.stringContaining("Automatic AI reviews are on"),
    });
    expect(automation?.buttons.map((button) => button.label)).toEqual([
      "Preview",
      "Turn off",
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

  it("turns the active setup step into a direct Next summary action", () => {
    const firstRunSetup = { stage: "needs_first_run", has_profiles: true, has_runs: false };
    const firstRunSteps = buildJourneySteps(actions, {}, firstRunSetup, telegramReady);
    const firstRunSummary = buildStartSummary(firstRunSteps, firstRunSetup, telegramReady);
    const sourceSetup = {
      stage: "needs_source_access",
      has_profiles: true,
      has_runs: true,
    };
    const sourceSteps = buildJourneySteps(actions, {}, sourceSetup, telegramReady);
    const sourceSummary = buildStartSummary(sourceSteps, sourceSetup, telegramReady);

    expect(firstRunSummary.find((item) => item.label === "Next")).toMatchObject({
      value: "Run first AI review",
      actionId: "monitor_jobs_dry_run",
      actionLabel: "Run review",
    });
    expect(sourceSummary.find((item) => item.label === "Next")).toMatchObject({
      value: "Fix saved channels",
      actionId: "sources_import_jobs",
      actionLabel: "Fix channels",
    });
  });

  it("keeps Telegram login as an embedded form instead of a summary command", () => {
    const setup = { stage: "needs_first_run", has_profiles: true, has_runs: false };
    const disconnected = {
      ...telegramReady,
      session_ready: false,
      login_state: "ready_for_code",
    };
    const steps = buildJourneySteps(actions, {}, setup, disconnected);
    const summary = buildStartSummary(steps, setup, disconnected);

    expect(summary.find((item) => item.label === "Next")).toMatchObject({
      value: "Connect Telegram",
    });
    expect(summary.find((item) => item.label === "Next")?.actionId).toBeUndefined();
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
