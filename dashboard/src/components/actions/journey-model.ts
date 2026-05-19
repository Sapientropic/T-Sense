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
  const needsAiKey = stage === "needs_ai_key";
  const hasRuns = Boolean(setupStatus?.has_runs);
  const telegramReady = Boolean(telegramStatus?.credentials_ready && telegramStatus?.session_ready);
  const hasProfiles = Boolean(setupStatus?.has_profiles);
  const hasUserGoal = setupHasUserGoal(setupStatus);
  const workspaceDone = Boolean(hasUserGoal && !["needs_profiles", "needs_enabled_profile"].includes(stage));
  const aiNeededForReview = needsAiKey && workspaceDone && telegramReady;
  const sourceAttention = stage === "needs_source_access";
  const ready = stage === "ready";
  const sourceAccessCheck = setupCheckById(setupStatus, "source_access");
  const sourceAccessDetail = sourceAccessCheck?.detail || "";
  const sourceAccessActionResult = results.sources_probe_access;
  const sourceAccessResult = sourceAccessActionResult?.source_access || sourceAccessCheck?.source_access;
  const sourceAccessHasInaccessible = Boolean(sourceAccessResult && sourceAccessResult.inaccessible_count > 0);
  const sourceAccessHasQuiet = Boolean(sourceAccessResult && sourceAccessResult.quiet_count > 0);
  const sourceStepDetail = sourceAccessActionResult?.source_access ? sourceAccessActionResult.detail : sourceAccessDetail;
  const sourceNeedsCleanup = sourceAttention || (workspaceDone && (sourceAccessHasInaccessible || sourceAccessHasQuiet));
  const workspaceTitle = !hasUserGoal ? "Create your goal" : sourceNeedsCleanup ? "Fix saved channels" : "Add sources";
  const workspaceButtons = !hasUserGoal
    ? []
    : [
        { actionId: "init_jobs", label: workspaceDone ? "Refresh files" : "Prepare files", variant: workspaceDone ? "secondary" as const : "primary" as const },
        { actionId: "sources_import_jobs", label: "Fix channels", variant: sourceAttention ? "primary" as const : "secondary" as const },
        { actionId: "sources_probe_access", label: "Check access", variant: sourceAttention ? "primary" as const : "secondary" as const },
        ...(sourceAccessHasInaccessible
          ? [{ actionId: "sources_pause_inaccessible", label: "Pause unreadable", variant: "secondary" as const }]
          : []),
        ...(sourceAccessHasQuiet
          ? [{ actionId: "sources_keep_accessible", label: "Active only", variant: "secondary" as const }]
          : []),
        { actionId: "sources_validate", label: "File check", variant: "secondary" as const },
      ];

  const hasSuccess = (actionId: string) => results[actionId]?.status === "success";
  const demoRendered = hasSuccess("demo_render");
  const demoShouldLead = !demoRendered && !hasRuns && !hasUserGoal;
  const demoState: JourneyState = demoRendered ? "done" : demoShouldLead ? "active" : "ready";
  const automationNeedsAttention = schedulerNeedsAttention(scheduler);
  const dryRunScheduleOn = Boolean(scheduler?.installed) || (hasSuccess("schedule_install_dry_run") && results.schedule_remove_dry_run?.status !== "success");
  const notifications = notificationReadiness(targets);
  const schedulerCanInstall = scheduler ? (scheduler.can_install ?? scheduler.available !== false) : true;
  const schedulerCanRemove = scheduler ? (scheduler.can_remove ?? schedulerCanInstall) : true;
  const automationDetail = automationNeedsAttention
    ? schedulerAttentionDetail(scheduler)
    : scheduler?.installed
      ? "Automatic AI reviews are on every 15 minutes."
      : schedulerCanInstall
        ? "Automatic AI reviews can run every 15 minutes from Signal Desk."
        : "Automatic AI reviews need the manual schedule preview on this machine.";
  const automationStateLabel = automationNeedsAttention ? "Needs repair" : scheduler?.installed ? "Auto review on" : schedulerCanInstall ? "Off" : "Manual";
  const automationState =
    ready || stage === "needs_delivery_target"
      ? automationNeedsAttention
        ? "active"
        : schedulerCanInstall || scheduler?.installed
          ? "ready"
          : "manual"
      : "blocked";
  const installScheduleButton = automationNeedsAttention
    ? schedulerCanInstall
      ? [{ actionId: "schedule_install_dry_run", label: "Repair", variant: "primary" as const }]
      : []
    : !dryRunScheduleOn && schedulerCanInstall
      ? [{ actionId: "schedule_install_dry_run", label: "Turn on", variant: "primary" as const }]
      : [];
  const availableButtons = (buttons: JourneyButton[]) => buttons.filter((button) => actionIds.has(button.actionId) || button.actionId.startsWith("settings_"));
  const availableAdvanced = (ids: string[]) => ids.filter((actionId) => actionIds.has(actionId));

  return [
    {
      key: "demo",
      title: "Preview demo",
      detail: "Render a local sample brief before connecting Telegram or AI.",
      state: demoState,
      stateLabel: demoRendered ? "Ready" : demoShouldLead ? "Start here" : "Optional",
      buttons: availableButtons([
        { actionId: "demo_render", label: demoRendered ? "Refresh demo" : "Render demo", variant: hasRuns ? "secondary" : "primary" },
      ]),
      advancedActionIds: availableAdvanced(["demo_render"]),
    },
    {
      key: "ai",
      title: "Connect AI matching",
      detail: "Save an AI API key before running AI review or AI source assistance. Demo, local files, profile setup, and Telegram login can continue without it.",
      state: needsAiKey ? (aiNeededForReview ? "active" : "ready") : "done",
      stateLabel: needsAiKey ? "Before review" : "Ready",
      buttons: availableButtons([
        {
          actionId: "settings_ai",
          label: needsAiKey ? "Add AI API key" : "AI API settings",
          variant: needsAiKey ? "primary" : "secondary",
        },
      ]),
      advancedActionIds: [],
    },
    {
      key: "telegram",
      title: "Connect Telegram",
      detail: telegramDetail(telegramStatus, telegramReady),
      state: telegramState(stage, telegramReady, hasUserGoal),
      stateLabel: telegramStateLabel(stage, telegramReady, hasUserGoal),
      buttons: availableButtons([
        { actionId: "doctor_jobs", label: "Check", variant: stage === "needs_first_run" || ready ? "secondary" : "primary" },
      ]),
      advancedActionIds: availableAdvanced(["doctor_jobs", "login_human"]),
    },
    {
      key: "workspace",
      title: workspaceTitle,
      detail: sourceSetupDetail({
        hasUserGoal,
        workspaceDone,
        sourceAttention,
        sourceAccessHasInaccessible,
        sourceAccessHasQuiet,
      }),
      detailTitle: sourceStepDetail || undefined,
      state: workspaceState(stage, workspaceDone, sourceAttention, hasProfiles, hasUserGoal),
      stateLabel: workspaceStateLabel(stage, workspaceDone, sourceAttention, hasProfiles, hasUserGoal),
      buttons: availableButtons(workspaceButtons),
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
      title: hasRuns ? "Run another AI review" : "Run first AI review",
      detail: "Fetch the latest saved-channel messages and let the configured AI model create Review cards locally. Nothing sends to Telegram.",
      state: firstRunState(stage, hasRuns, workspaceDone, sourceAttention, telegramReady),
      stateLabel: firstRunStateLabel(stage, hasRuns, sourceAttention, telegramReady, workspaceDone),
      buttons: availableButtons([{ actionId: "monitor_jobs_dry_run", label: "Run review", variant: "primary" }]),
      advancedActionIds: availableAdvanced(["monitor_jobs_dry_run"]),
    },
    {
      key: "automation",
      title: "Automation",
      detail: `${automationDetail} Notifications: ${notifications.value}. ${notifications.detail}`,
      state: automationState,
      stateLabel: ready || stage === "needs_delivery_target" ? automationStateLabel : "Finish setup first",
      buttons: availableButtons([
        { actionId: "schedule_preview", label: "Preview", variant: "secondary" },
        ...installScheduleButton,
        ...(dryRunScheduleOn && schedulerCanRemove ? [{ actionId: "schedule_remove_dry_run", label: "Turn off", variant: "secondary" as const }] : []),
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
      stateLabel: hasRuns || ready ? "Available after review" : "Needs an AI review first",
      buttons: availableButtons([{ actionId: "feedback_export", label: "Suggest rules", variant: "secondary" }]),
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
  const workspaceReady = Boolean(setupHasUserGoal(setupStatus) && !["needs_profiles", "needs_enabled_profile"].includes(stage));
  const showPostReviewSummary = Boolean(setupStatus?.has_runs || reviewCount > 0 || stage === "ready" || stage === "needs_delivery_target");
  const telegramValue =
    telegramStatus?.credentials_ready && telegramStatus?.session_ready
      ? "Ready"
      : telegramStatus?.session_ready
        ? "Missing app details"
        : telegramStatus?.credentials_ready
          ? "Needs login"
          : "Not connected";
  const activeStep = steps.find((step) => step.state === "active");
  const activeButton = activeStep?.key === "telegram" ? undefined : primaryButtonForStep(activeStep);
  const nextValue = activeStep?.title
    ?? (reviewCount > 0 ? `Review ${reviewCount} card${reviewCount === 1 ? "" : "s"}` : !setupStatus?.has_runs ? "Run first AI review" : "Run another AI review");
  const automationValue = schedulerNeedsAttention(scheduler) ? "Needs repair" : scheduler?.installed ? "On" : scheduler?.available === false ? "Manual" : "Off";
  const notifications = notificationReadiness(targets);
  const notificationAction =
    notifications.value === "Needs chat ID"
      ? { actionId: "live_delivery_human", actionLabel: "Add chat ID" }
      : notifications.value === "Muted"
        ? { actionId: "live_delivery_human", actionLabel: "Open settings" }
        : {};
  const items: StartSummaryItem[] = [
    { label: "Workspace", value: workspaceReady ? "Ready" : "Set up" },
    { label: "Telegram", value: telegramValue },
    { label: "Next", value: nextValue, ...(activeButton ? { actionId: activeButton.actionId, actionLabel: activeButton.label } : {}) },
  ];
  if (showPostReviewSummary) {
    items.splice(
      2,
      0,
      { label: "Notifications", value: notifications.value, ...notificationAction },
      { label: "Automation", value: automationValue },
    );
  }
  return items;
}

function primaryButtonForStep(step: JourneyStep | undefined) {
  return step?.buttons.find((button) => button.variant === "primary") ?? step?.buttons[0];
}

function schedulerNeedsAttention(scheduler: DeskSchedulerStatus | null | undefined) {
  return Boolean(scheduler?.installed && scheduler.status !== "installed");
}

function setupHasUserGoal(setupStatus: DashboardState["setup_status"] | undefined) {
  return Boolean(setupStatus?.has_user_goal ?? setupStatus?.has_profiles);
}

function schedulerAttentionDetail(scheduler: DeskSchedulerStatus | null | undefined) {
  const detail = scheduler?.detail?.trim() || "Automatic AI reviews are installed, but Signal Desk cannot confirm they are running.";
  const nextAction = scheduler?.next_action?.trim();
  return nextAction ? `${detail} ${nextAction}` : detail;
}

function telegramDetail(telegramStatus: DeskTelegramStatus | null | undefined, telegramReady: boolean) {
  if (telegramReady) {
    return "Telegram is ready for local channel scans. Check only if login changes.";
  }
  if (telegramStatus?.session_ready) {
    return "Telegram login is saved, but app credentials are missing. Save the app ID and hash before scanning channels.";
  }
  if (telegramStatus?.credentials_ready) {
    return "App credentials are saved. Finish Telegram login before scanning channels.";
  }
  return "Connect Telegram so Signal Desk can read your saved channels inside this local app.";
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
  hasUserGoal,
  workspaceDone,
  sourceAttention,
  sourceAccessHasInaccessible,
  sourceAccessHasQuiet,
}: {
  hasUserGoal: boolean;
  workspaceDone: boolean;
  sourceAttention: boolean;
  sourceAccessHasInaccessible: boolean;
  sourceAccessHasQuiet: boolean;
}) {
  if (!hasUserGoal) {
    return "Create a monitor goal in plain language so Signal Desk knows what to watch.";
  }
  if (sourceAccessHasInaccessible) {
    return "Some saved channels cannot be read. Check access, then pause unreadable ones.";
  }
  if (sourceAccessHasQuiet) {
    return "Some saved channels are quiet. Keep active channels only if you want a cleaner list.";
  }
  if (sourceAttention) {
    return "Check saved-channel access before the next AI review.";
  }
  if (workspaceDone) {
    return "Local files are ready. Refresh only if your saved channels changed.";
  }
  return "Create the local files Signal Desk needs after Telegram is ready.";
}

function setupCheckById(setupStatus: DashboardState["setup_status"] | undefined, checkId: string) {
  return setupStatus?.checks?.find((item) => item.check_id === checkId);
}

function workspaceState(stage: string, workspaceDone: boolean, sourceAttention: boolean, hasProfiles: boolean, hasUserGoal: boolean): JourneyState {
  if (sourceAttention || stage === "needs_profiles" || stage === "needs_enabled_profile" || !hasUserGoal) {
    return "active";
  }
  return workspaceDone ? "done" : "ready";
}

function workspaceStateLabel(stage: string, workspaceDone: boolean, sourceAttention: boolean, hasProfiles: boolean, hasUserGoal: boolean) {
  if (sourceAttention) {
    return "Needs source fix";
  }
  if (stage === "needs_enabled_profile" && hasProfiles) {
    return "Enable profile";
  }
  if (stage === "needs_profiles" || !hasUserGoal) {
    return "Start here";
  }
  return workspaceDone ? "Ready" : "Create first";
}

function telegramState(stage: string, telegramReady: boolean, hasUserGoal: boolean): JourneyState {
  if (telegramReady) {
    return "done";
  }
  if (!hasUserGoal) {
    return "ready";
  }
  if (stage === "ready" || stage === "needs_delivery_target") {
    return "ready";
  }
  return "active";
}

function telegramStateLabel(stage: string, telegramReady: boolean, hasUserGoal: boolean) {
  if (telegramReady) {
    return "Ready";
  }
  if (!hasUserGoal) {
    return "After goal";
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

function firstRunStateLabel(stage: string, hasRuns: boolean, sourceAttention: boolean, telegramReady: boolean, workspaceDone: boolean) {
  if (hasRuns || stage === "ready" || stage === "needs_delivery_target") {
    return "Run history exists";
  }
  if (!workspaceDone) {
    return "Choose goal first";
  }
  if (!telegramReady) {
    return "Connect Telegram first";
  }
  if (sourceAttention) {
    return "Fix channels first";
  }
  if (stage === "needs_ai_key") {
    return "Add AI key first";
  }
  if (stage === "needs_first_run") {
    return "Next";
  }
  return "Finish setup first";
}

function firstRunBlocked(stage: string, workspaceDone: boolean, sourceAttention: boolean, telegramReady: boolean) {
  return (
    sourceAttention ||
    !workspaceDone ||
    !telegramReady ||
    stage === "needs_ai_key" ||
    stage === "needs_profiles" ||
    stage === "needs_enabled_profile"
  );
}
