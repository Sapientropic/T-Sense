import type {
  DashboardState,
  DeliveryTarget,
  DeskAction,
  DeskActionResult,
  DeskSchedulerStatus,
  DeskTelegramStatus,
} from "../../domain/types";

export type JourneyState = "done" | "active" | "ready" | "blocked" | "manual";

export type JourneyButton = {
  actionId: string;
  label: string;
  variant?: "primary" | "secondary";
};

export type JourneyStep = {
  key: string;
  title: string;
  detail: string;
  detailTitle?: string;
  state: JourneyState;
  stateLabel: string;
  buttons: JourneyButton[];
  advancedActionIds: string[];
};

export type StartSummaryItem = {
  label: string;
  value: string;
  actionId?: string;
  actionLabel?: string;
};

export type NotificationReadiness = {
  value: "Enabled" | "Muted" | "Needs chat ID";
  detail: string;
};

export function buildJourneySteps(
  actions: DeskAction[],
  results: Record<string, DeskActionResult>,
  setupStatus?: DashboardState["setup_status"],
  telegramStatus?: DeskTelegramStatus | null,
  scheduler?: DeskSchedulerStatus | null,
  targets: DeliveryTarget[] = [],
): JourneyStep[] {
  const actionIds = new Set(actions.map((action) => action.action_id));
  const stage = setupStatus?.stage ?? "";
  const hasRuns = Boolean(setupStatus?.has_runs);
  const telegramReady = Boolean(telegramStatus?.session_ready);
  const workspaceDone = Boolean(setupStatus?.has_profiles && stage !== "needs_profiles" && stage !== "needs_enabled_profile");
  const sourceAttention = stage === "needs_source_access";
  const ready = stage === "ready";
  const sourceAccessCheck = setupCheckById(setupStatus, "source_access");
  const sourceAccessDetail = sourceAccessCheck?.detail || "";
  const sourceAccessResult = results.sources_probe_access?.source_access || sourceAccessCheck?.source_access;
  const sourceAccessHasInaccessible = Boolean(sourceAccessResult && sourceAccessResult.inaccessible_count > 0);
  const sourceAccessHasQuiet = Boolean(sourceAccessResult && sourceAccessResult.quiet_count > 0);
  const sourceStepDetail = results.sources_probe_access?.detail || sourceAccessDetail;
  const sourceNeedsCleanup = sourceAttention || sourceAccessHasInaccessible || sourceAccessHasQuiet;

  const hasSuccess = (actionId: string) => results[actionId]?.status === "success";
  const dryRunScheduleOn = scheduler?.installed || (hasSuccess("schedule_install_dry_run") && results.schedule_remove_dry_run?.status !== "success");
  const notifications = notificationReadiness(targets);
  const schedulerCanInstall = scheduler ? (scheduler.can_install ?? scheduler.available !== false) : true;
  const schedulerCanRemove = scheduler ? (scheduler.can_remove ?? schedulerCanInstall) : true;
  const automationDetail = scheduler?.installed
    ? "Automatic practice scans are on every 15 minutes."
    : schedulerCanInstall
      ? "Automatic practice scans can run every 15 minutes from Signal Desk."
      : "Automatic practice scans need the manual schedule preview on this machine.";
  const automationStateLabel = scheduler?.installed ? "Auto scan on" : schedulerCanInstall ? "Off" : "Manual";
  const automationState =
    ready || stage === "needs_delivery_target"
      ? schedulerCanInstall || scheduler?.installed
        ? "ready"
        : "manual"
      : "blocked";
  const availableButtons = (buttons: JourneyButton[]) => buttons.filter((button) => actionIds.has(button.actionId));
  const availableAdvanced = (ids: string[]) => ids.filter((actionId) => actionIds.has(actionId));

  return [
    {
      key: "demo",
      title: "Try Signal Desk without Telegram",
      detail: "Open a sample report first, so a new user can see the product before connecting accounts.",
      state: hasSuccess("demo_render") ? "done" : "ready",
      stateLabel: hasSuccess("demo_render") ? "Demo ready" : "Optional",
      buttons: availableButtons([{ actionId: "demo_render", label: "Create demo report", variant: "secondary" }]),
      advancedActionIds: availableAdvanced(["demo_render"]),
    },
    {
      key: "telegram",
      title: "Connect Telegram",
      detail: telegramReady
        ? "Telegram is connected for local scans. Check setup only if login changes."
        : "Connect Telegram so Signal Desk can read your saved channels inside this local app.",
      state: telegramState(stage, telegramReady),
      stateLabel: telegramStateLabel(stage, telegramReady),
      buttons: availableButtons([
        { actionId: "doctor_jobs", label: "Check setup", variant: stage === "needs_first_run" || ready ? "secondary" : "primary" },
      ]),
      advancedActionIds: availableAdvanced(["doctor_jobs", "login_human"]),
    },
    {
      key: "workspace",
      title: sourceNeedsCleanup ? "Fix saved channels" : "Set up local files",
      detail: sourceSetupDetail({
        workspaceDone,
        sourceAttention,
        sourceAccessHasInaccessible,
        sourceAccessHasQuiet,
      }),
      detailTitle: sourceStepDetail || undefined,
      state: workspaceState(stage, workspaceDone, sourceAttention),
      stateLabel: workspaceStateLabel(stage, workspaceDone, sourceAttention),
      buttons: availableButtons([
        { actionId: "init_jobs", label: workspaceDone ? "Refresh files" : "Prepare files", variant: workspaceDone ? "secondary" : "primary" },
        { actionId: "sources_import_jobs", label: "Fix channels", variant: sourceAttention ? "primary" : "secondary" },
        { actionId: "sources_probe_access", label: "Check channels", variant: sourceAttention ? "primary" : "secondary" },
        ...(sourceAccessHasInaccessible
          ? [{ actionId: "sources_pause_inaccessible", label: "Pause unreadable", variant: "secondary" as const }]
          : []),
        ...(sourceAccessHasQuiet
          ? [{ actionId: "sources_keep_accessible", label: "Keep active only", variant: "secondary" as const }]
          : []),
        { actionId: "sources_validate", label: "Check file format", variant: "secondary" },
      ]),
      advancedActionIds: availableAdvanced([
        "init_jobs",
        "sources_import_jobs",
        "sources_probe_access",
        "sources_pause_inaccessible",
        "sources_keep_accessible",
        "sources_validate",
      ]),
    },
    {
      key: "first-run",
      title: hasRuns ? "Run another scan" : "Run the first scan",
      detail: "Fetch the latest saved-channel messages and create Review cards locally. Nothing sends to Telegram.",
      state: firstRunState(stage, hasRuns, workspaceDone, sourceAttention, telegramReady),
      stateLabel: firstRunStateLabel(stage, hasRuns, sourceAttention, telegramReady),
      buttons: availableButtons([{ actionId: "monitor_jobs_dry_run", label: hasRuns ? "Run fresh scan" : "Run first scan", variant: "primary" }]),
      advancedActionIds: availableAdvanced(["monitor_jobs_dry_run"]),
    },
    {
      key: "automation",
      title: "Automation",
      detail: `${automationDetail} Notifications: ${notifications.value}. ${notifications.detail}`,
      state: automationState,
      stateLabel: ready || stage === "needs_delivery_target" ? automationStateLabel : "Finish setup first",
      buttons: availableButtons([
        { actionId: "schedule_preview", label: "Preview schedule", variant: "secondary" },
        ...(!dryRunScheduleOn && schedulerCanInstall ? [{ actionId: "schedule_install_dry_run", label: "Turn on auto scan", variant: "primary" as const }] : []),
        ...(dryRunScheduleOn && schedulerCanRemove ? [{ actionId: "schedule_remove_dry_run", label: "Turn off auto scan", variant: "secondary" as const }] : []),
        { actionId: "live_delivery_human", label: "Notifications", variant: "secondary" },
      ]),
      advancedActionIds: availableAdvanced([
        "schedule_preview",
        "schedule_install_dry_run",
        "schedule_remove_dry_run",
        "schedule_install_human",
      ]),
    },
    {
      key: "feedback",
      title: "Tune results",
      detail: "Teach Signal Desk which results matter by reviewing cards and adjusting your preferences.",
      state: hasRuns || ready ? "ready" : "blocked",
      stateLabel: hasRuns || ready ? "Available after review" : "Needs a scan first",
      buttons: availableButtons([{ actionId: "feedback_export", label: "Generate profile suggestions", variant: "secondary" }]),
      advancedActionIds: availableAdvanced(["feedback_export"]),
    },
  ];
}

export function buildStartSummary(
  steps: JourneyStep[],
  setupStatus?: DashboardState["setup_status"],
  telegramStatus?: DeskTelegramStatus | null,
  scheduler?: DeskSchedulerStatus | null,
  targets: DeliveryTarget[] = [],
  reviewCount = 0,
): StartSummaryItem[] {
  const stage = setupStatus?.stage ?? "";
  const workspaceReady = Boolean(setupStatus?.has_profiles && stage !== "needs_profiles" && stage !== "needs_enabled_profile");
  const telegramValue = telegramStatus?.session_ready
    ? "Connected"
    : telegramStatus?.credentials_ready
      ? "Needs login"
      : "Needs app details";
  const activeStep = steps.find((step) => step.state === "active");
  const nextValue = activeStep?.title
    ?? (reviewCount > 0 ? `Review ${reviewCount} card${reviewCount === 1 ? "" : "s"}` : !setupStatus?.has_runs ? "Run first scan" : "Run another scan");
  const automationValue = scheduler?.installed ? "On" : scheduler?.available === false ? "Manual" : "Off";
  const notifications = notificationReadiness(targets);
  const notificationAction =
    notifications.value === "Needs chat ID"
      ? { actionId: "live_delivery_human", actionLabel: "Add chat ID" }
      : notifications.value === "Muted"
        ? { actionId: "live_delivery_human", actionLabel: "Open settings" }
        : {};
  return [
    { label: "Workspace", value: workspaceReady ? "Ready" : "Set up" },
    { label: "Telegram", value: telegramValue },
    { label: "Notifications", value: notifications.value, ...notificationAction },
    { label: "Automation", value: automationValue },
    { label: "Next", value: nextValue },
  ];
}

export function notificationReadiness(targets: DeliveryTarget[]): NotificationReadiness {
  const target = targets.find((item) => item.type.toLowerCase() === "telegram_bot") ?? targets[0];
  const chatId = typeof target?.config.chat_id === "string" ? target.config.chat_id.trim() : "";
  if (!target || !chatId) {
    return {
      value: "Needs chat ID",
      detail: "Add a Telegram chat ID before live alerts can send.",
    };
  }
  if (target.enabled) {
    return {
      value: "Enabled",
      detail: "Saved Telegram notifications can send when a qualifying run fires.",
    };
  }
  return {
    value: "Muted",
    detail: "A Telegram target is saved, but live notifications are muted.",
  };
}

function sourceSetupDetail({
  workspaceDone,
  sourceAttention,
  sourceAccessHasInaccessible,
  sourceAccessHasQuiet,
}: {
  workspaceDone: boolean;
  sourceAttention: boolean;
  sourceAccessHasInaccessible: boolean;
  sourceAccessHasQuiet: boolean;
}) {
  if (sourceAccessHasInaccessible) {
    return "Some saved channels cannot be read. Check channels, then pause unreadable ones.";
  }
  if (sourceAccessHasQuiet) {
    return "Some saved channels are quiet. Keep active channels only if you want a cleaner list.";
  }
  if (sourceAttention) {
    return "Check saved-channel access before the next scan.";
  }
  if (workspaceDone) {
    return "Local files are ready. Refresh only if your saved channels changed.";
  }
  return "Create the local files Signal Desk needs after Telegram is connected.";
}

function setupCheckById(setupStatus: DashboardState["setup_status"] | undefined, checkId: string) {
  return setupStatus?.checks?.find((item) => item.check_id === checkId);
}

function workspaceState(stage: string, workspaceDone: boolean, sourceAttention: boolean): JourneyState {
  if (sourceAttention || stage === "needs_profiles" || stage === "needs_enabled_profile") {
    return "active";
  }
  return workspaceDone ? "done" : "ready";
}

function workspaceStateLabel(stage: string, workspaceDone: boolean, sourceAttention: boolean) {
  if (sourceAttention) {
    return "Needs source fix";
  }
  if (stage === "needs_enabled_profile") {
    return "Enable profile";
  }
  if (stage === "needs_profiles") {
    return "Start here";
  }
  return workspaceDone ? "Ready" : "Create first";
}

function telegramState(stage: string, telegramReady: boolean): JourneyState {
  if (telegramReady) {
    return "done";
  }
  if (stage === "ready" || stage === "needs_delivery_target") {
    return "ready";
  }
  return "active";
}

function telegramStateLabel(stage: string, telegramReady: boolean) {
  if (telegramReady) {
    return "Connected";
  }
  if (stage === "ready" || stage === "needs_delivery_target") {
    return "Optional";
  }
  return "Check before scan";
}

function firstRunState(
  stage: string,
  hasRuns: boolean,
  workspaceDone: boolean,
  sourceAttention: boolean,
  telegramReady: boolean,
): JourneyState {
  if (hasRuns || stage === "ready" || stage === "needs_delivery_target") {
    return "done";
  }
  if (firstRunBlocked(stage, workspaceDone, sourceAttention, telegramReady)) {
    return "blocked";
  }
  return "active";
}

function firstRunStateLabel(stage: string, hasRuns: boolean, sourceAttention: boolean, telegramReady: boolean) {
  if (hasRuns || stage === "ready" || stage === "needs_delivery_target") {
    return "Run history exists";
  }
  if (!telegramReady) {
    return "Connect Telegram first";
  }
  if (sourceAttention) {
    return "Fix channels first";
  }
  if (stage === "needs_first_run") {
    return "Next";
  }
  return "Finish setup first";
}

function firstRunBlocked(stage: string, workspaceDone: boolean, sourceAttention: boolean, telegramReady: boolean) {
  return sourceAttention || !workspaceDone || !telegramReady || stage === "needs_profiles" || stage === "needs_enabled_profile";
}
