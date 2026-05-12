import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CheckCircle2,
  CircleDashed,
  ExternalLink,
  KeyRound,
  LockKeyhole,
  Play,
  ShieldAlert,
  UserRoundCog,
  Wrench,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { CopyableCommand, InlineEmpty } from "./common";
import type { DashboardState, DeliveryTarget, DeskAction, DeskActionResult, DeskSchedulerStatus, DeskTelegramStatus } from "../domain/types";

type JourneyState = "done" | "active" | "ready" | "blocked" | "manual";

type JourneyButton = {
  actionId: string;
  label: string;
  variant?: "primary" | "secondary";
};

type JourneyStep = {
  key: string;
  title: string;
  detail: string;
  state: JourneyState;
  stateLabel: string;
  buttons: JourneyButton[];
  advancedActionIds: string[];
};

type StartSummaryItem = {
  label: string;
  value: string;
  actionId?: string;
  actionLabel?: string;
};

type NotificationReadiness = {
  value: "Enabled" | "Muted" | "Needs chat ID";
  detail: string;
};

type SettingsShortcutTarget = "sources" | "ai" | "notifications" | "learning" | "evidence";

type TelegramControls = {
  status: DeskTelegramStatus | null;
  busy: string;
  error: string;
  saveCredentials: (apiId: string, apiHash: string) => Promise<DeskTelegramStatus>;
  sendCode: (phone: string) => Promise<DeskTelegramStatus>;
  verifyCode: (code: string, password?: string) => Promise<DeskTelegramStatus>;
  refresh: () => Promise<DeskTelegramStatus>;
  cancelLogin: () => Promise<DeskTelegramStatus>;
};

const SETUP_STAGE_LABELS: Record<string, string> = {
  needs_profiles: "Workspace setup",
  needs_enabled_profile: "Profile needs enabling",
  needs_first_run: "Ready for first scan",
  needs_source_access: "Source access needs attention",
  needs_delivery_target: "Delivery optional",
  ready: "Review inbox ready",
};

export function ActionsView({
  actions,
  results,
  busyActionId,
  loadError,
  setupStatus,
  scheduler,
  telegram,
  targets = [],
  reviewCount = 0,
  onOpenReview,
  onOpenProfiles,
  onOpenRuns,
  onOpenSettings,
  onRun,
}: {
  actions: DeskAction[];
  results: Record<string, DeskActionResult>;
  busyActionId: string;
  loadError: string;
  setupStatus?: DashboardState["setup_status"];
  scheduler?: DeskSchedulerStatus | null;
  telegram: TelegramControls;
  targets?: DeliveryTarget[];
  reviewCount?: number;
  onOpenReview?: () => void;
  onOpenProfiles?: () => void;
  onOpenRuns?: () => void;
  onOpenSettings?: (target?: SettingsShortcutTarget) => void;
  onRun: (actionId: string) => Promise<void>;
}) {
  const actionMap = new Map(actions.map((action) => [action.action_id, action]));
  const [showSetupSteps, setShowSetupSteps] = useState(false);
  const steps = buildJourneySteps(actions, results, setupStatus, telegram.status, scheduler, targets);
  const activeStep = steps.find((step) => step.state === "active");
  const currentStep = activeStep ?? steps.find((step) => step.state === "ready") ?? steps.find((step) => step.state === "manual") ?? steps[0];
  const stage = setupStatus?.stage ?? "";
  const stageLabel = SETUP_STAGE_LABELS[stage] ?? "Local setup";
  const startSummary = buildStartSummary(steps, setupStatus, telegram.status, scheduler, targets, reviewCount);
  const heroTitle = activeStep ? currentStep?.title : "Signal Desk is ready";
  const heroDetail = activeStep
    ? currentStep?.detail
    : reviewCount
      ? ""
      : "Run a fresh practice scan first. Automation and notifications can wait.";
  const compactReadyMode = !activeStep && (stage === "ready" || stage === "needs_delivery_target");
  const showCompactMoreControls = false;
  const firstRunStep = steps.find((step) => step.key === "first-run");
  const secondaryReadyStepOrder = ["feedback", "automation"];
  const secondaryReadyStepKeys = new Set(["first-run", ...secondaryReadyStepOrder]);
  const visibleSteps = compactReadyMode
    ? []
    : steps;
  const secondaryReadySteps = compactReadyMode
    ? secondaryReadyStepOrder.map((key) => steps.find((step) => step.key === key)).filter(Boolean) as JourneyStep[]
    : [];
  const parkedSteps = compactReadyMode ? steps.filter((step) => !secondaryReadyStepKeys.has(step.key)) : [];
  const primaryReadyAction = compactReadyMode
    ? buildPrimaryReadyAction(firstRunStep, reviewCount, Boolean(onOpenReview))
    : null;
  const summaryBlock = (
    <div className="start-summary" aria-label="Setup summary">
      {startSummary.map((item) => {
        const actionId = item.actionId;
        const showAction = Boolean(actionId && actionMap.has(actionId));
        return (
          <div className={showAction ? "is-actionable" : ""} key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            {showAction && actionId && (
              <button
                aria-label={`${item.label}: ${item.actionLabel}`}
                className="start-summary-action"
                disabled={Boolean(busyActionId)}
                onClick={() => void onRun(actionId)}
                title={item.actionLabel}
                type="button"
              >
                {item.actionLabel === "Open settings" ? <Wrench size={14} /> : <Bell size={14} />}
                <span>{item.actionLabel}</span>
              </button>
            )}
          </div>
        );
      })}
    </div>
  );

  return (
    <section className="actions-view start-view">
      <section className="start-hero" aria-label="Signal Desk start">
        <span className="panel-kicker">Signal Desk Start</span>
        <div className="start-hero-main">
          <div>
            <h2>{heroTitle || "Open Signal Desk"}</h2>
            {heroDetail && <p>{heroDetail}</p>}
          </div>
          <div className="start-stage" aria-label="Current setup stage">
            <span>{stageLabel}</span>
            <strong>{activeStep ? currentStep?.stateLabel || "Ready" : "Ready"}</strong>
          </div>
        </div>
      </section>

      {!compactReadyMode && summaryBlock}

      {loadError && <InlineEmpty title={loadError} tone="error" />}
      {!actions.length && !loadError && (
        <InlineEmpty title="Signal Desk controls are not exposed by the local server." tone="warning" />
      )}

      {primaryReadyAction && (
        <StartPrimaryActionCard
          action={primaryReadyAction}
          anyBusy={Boolean(busyActionId)}
          busyActionId={busyActionId}
          onOpenReview={onOpenReview}
          onRun={onRun}
        />
      )}

      {compactReadyMode && (
        <StartManagementStrip
          anyBusy={Boolean(busyActionId)}
          automationStep={steps.find((step) => step.key === "automation")}
          onOpenProfiles={onOpenProfiles}
          onOpenRuns={onOpenRuns}
          onOpenSettings={onOpenSettings}
          onRun={onRun}
          scheduler={scheduler}
          setupOpen={showSetupSteps}
          onToggleSetup={() => setShowSetupSteps((value) => !value)}
        />
      )}

      {compactReadyMode && showSetupSteps && (
        <section className="start-setup-drawer" aria-label="Setup and credentials">
          <div className="start-setup-drawer-head">
            <div>
              <span className="panel-kicker">Setup controls</span>
              <strong>Edit login, sources, checks, and first-run setup</strong>
            </div>
            <button className="journey-button secondary" type="button" onClick={() => setShowSetupSteps(false)}>
              Close
            </button>
          </div>
          <div className="journey-list">
            {steps.map((step, index) => (
              <JourneyStepCard
                actionMap={actionMap}
                anyBusy={Boolean(busyActionId)}
                busyActionId={busyActionId}
                index={index + 1}
                key={step.key}
                onRun={onRun}
                results={results}
                step={step}
                telegram={telegram}
              />
            ))}
          </div>
        </section>
      )}

      {!compactReadyMode && (
        <div className="journey-list">
          {visibleSteps.map((step, index) => (
            <JourneyStepCard
              actionMap={actionMap}
              anyBusy={Boolean(busyActionId)}
              busyActionId={busyActionId}
              index={index + 1}
              key={step.key}
              onRun={onRun}
              results={results}
              step={step}
              telegram={telegram}
            />
          ))}
        </div>
      )}
      {showCompactMoreControls && (
        <details className="journey-secondary start-more-controls">
          <summary>More controls</summary>
          <div className="start-more-body">
            <section className="start-more-section" aria-label="Status snapshot">
              <span className="panel-kicker">Status snapshot</span>
              {summaryBlock}
            </section>
            {secondaryReadySteps.length > 0 && (
              <section className="start-more-section" aria-label="Other controls">
                <span className="panel-kicker">Other controls</span>
                <div className="journey-list secondary">
                  {secondaryReadySteps.map((step, index) => (
                    <JourneyStepCard
                      actionMap={actionMap}
                      anyBusy={Boolean(busyActionId)}
                      busyActionId={busyActionId}
                      index={index + 1}
                      key={step.key}
                      onRun={onRun}
                      results={results}
                      step={step}
                      telegram={telegram}
                    />
                  ))}
                </div>
              </section>
            )}
            {parkedSteps.length > 0 && (
              <section className="start-more-section" aria-label="Setup checks">
                <span className="panel-kicker">Setup checks</span>
                <div className="journey-list secondary">
                  {parkedSteps.map((step, index) => (
                    <JourneyStepCard
                      actionMap={actionMap}
                      anyBusy={Boolean(busyActionId)}
                      busyActionId={busyActionId}
                      index={index + 1}
                      key={step.key}
                      onRun={onRun}
                      results={results}
                      step={step}
                      telegram={telegram}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        </details>
      )}
      {!compactReadyMode && (
        <>
          {secondaryReadySteps.length > 0 && (
            <details className="journey-secondary">
              <summary>Other controls</summary>
              <div className="journey-list secondary">
                {secondaryReadySteps.map((step, index) => (
                  <JourneyStepCard
                    actionMap={actionMap}
                    anyBusy={Boolean(busyActionId)}
                    busyActionId={busyActionId}
                    index={index + 1}
                    key={step.key}
                    onRun={onRun}
                    results={results}
                    step={step}
                    telegram={telegram}
                  />
                ))}
              </div>
            </details>
          )}
          {parkedSteps.length > 0 && (
            <details className="journey-secondary">
              <summary>Setup checks</summary>
              <div className="journey-list secondary">
                {parkedSteps.map((step, index) => (
                  <JourneyStepCard
                    actionMap={actionMap}
                    anyBusy={Boolean(busyActionId)}
                    busyActionId={busyActionId}
                    index={index + 1}
                    key={step.key}
                    onRun={onRun}
                    results={results}
                    step={step}
                    telegram={telegram}
                  />
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}

type StartManagementControl = {
  key: string;
  label: string;
  detail: string;
  icon: ReactNode;
  disabled?: boolean;
  onClick: () => void;
};

function StartManagementStrip({
  anyBusy,
  automationStep,
  onOpenProfiles,
  onOpenRuns,
  onOpenSettings,
  onRun,
  scheduler,
  setupOpen,
  onToggleSetup,
}: {
  anyBusy: boolean;
  automationStep?: JourneyStep;
  onOpenProfiles?: () => void;
  onOpenRuns?: () => void;
  onOpenSettings?: (target?: SettingsShortcutTarget) => void;
  onRun: (actionId: string) => Promise<void>;
  scheduler?: DeskSchedulerStatus | null;
  setupOpen: boolean;
  onToggleSetup: () => void;
}) {
  const automationButton =
    automationStep?.buttons.find((button) => button.actionId === "schedule_install_dry_run" || button.actionId === "schedule_remove_dry_run") ??
    automationStep?.buttons.find((button) => button.actionId === "schedule_preview");
  const controls: StartManagementControl[] = [
    ...(automationButton
      ? [
          {
            key: "automation",
            label: scheduler?.installed ? "Auto scan on" : "Automation",
            detail: scheduler?.installed ? "Every 15 min" : "Set schedule",
            icon: <Bell size={15} />,
            disabled: anyBusy,
            onClick: () => void onRun(automationButton.actionId),
          } satisfies StartManagementControl,
        ]
      : []),
    {
      key: "setup",
      label: "Setup",
      detail: setupOpen ? "Hide setup" : "Edit / login",
      icon: <Wrench size={15} />,
      onClick: onToggleSetup,
    },
    {
      key: "ai",
      label: "AI API",
      detail: "LLM / OCR keys",
      icon: <KeyRound size={15} />,
      disabled: !onOpenSettings,
      onClick: () => onOpenSettings?.("ai"),
    },
    {
      key: "profiles",
      label: "Profiles",
      detail: "Create / edit",
      icon: <UserRoundCog size={15} />,
      disabled: !onOpenProfiles,
      onClick: () => onOpenProfiles?.(),
    },
    {
      key: "sources",
      label: "Sources",
      detail: "Channels",
      icon: <Wrench size={15} />,
      disabled: !onOpenSettings,
      onClick: () => onOpenSettings?.("sources"),
    },
    {
      key: "runs",
      label: "Runs",
      detail: "Open evidence",
      icon: <CircleDashed size={15} />,
      disabled: !onOpenRuns,
      onClick: () => onOpenRuns?.(),
    },
  ];
  return (
    <nav className="start-management-strip" aria-label="Desk management shortcuts">
      {controls.map((control) => (
        <button data-control-key={control.key} disabled={control.disabled} key={control.key} onClick={control.onClick} type="button">
          {control.icon}
          <span>{control.label}</span>
          <small>{control.detail}</small>
        </button>
      ))}
    </nav>
  );
}

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
  const firstRunReady = stage === "needs_first_run";
  const ready = stage === "ready";
  const sourceAccessDetail = setupCheckDetail(setupStatus, "source_access");

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
      detail: "Connect Telegram first so Signal Desk can read your saved channels inside this local app.",
      state: telegramState(stage, telegramReady),
      stateLabel: telegramStateLabel(stage, telegramReady),
      buttons: availableButtons([
        { actionId: "doctor_jobs", label: "Check setup", variant: stage === "needs_first_run" || ready ? "secondary" : "primary" },
      ]),
      advancedActionIds: availableAdvanced(["doctor_jobs", "login_human"]),
    },
    {
      key: "workspace",
      title: sourceAttention ? "Repair source list" : "Prepare Signal Desk files",
      detail: sourceAttention
        ? sourceAccessDetail || "Check real Telegram source access, then pause sources that cannot be read."
        : sourceAccessDetail
          ? sourceAccessDetail
          : "Create the private settings and saved-channel files Signal Desk needs after Telegram is connected.",
      state: workspaceState(stage, workspaceDone, sourceAttention),
      stateLabel: workspaceStateLabel(stage, workspaceDone, sourceAttention),
      buttons: availableButtons([
        { actionId: "init_jobs", label: workspaceDone ? "Refresh files" : "Prepare files", variant: workspaceDone ? "secondary" : "primary" },
        { actionId: "sources_import_jobs", label: "Repair source list", variant: sourceAttention ? "primary" : "secondary" },
        { actionId: "sources_probe_access", label: "Check source access", variant: sourceAttention ? "primary" : "secondary" },
        ...(sourceAttention
          ? [
              { actionId: "sources_pause_inaccessible", label: "Pause inaccessible", variant: "secondary" as const },
              { actionId: "sources_keep_accessible", label: "Keep accessible only", variant: "secondary" as const },
            ]
          : []),
        { actionId: "sources_validate", label: "Check syntax", variant: "secondary" },
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

type PrimaryReadyAction = {
  kind: "review" | "scan";
  title: string;
  detail: string;
  label: string;
  actionId?: string;
};

function buildPrimaryReadyAction(step: JourneyStep | undefined, reviewCount: number, canOpenReview: boolean): PrimaryReadyAction | null {
  if (reviewCount > 0 && canOpenReview) {
    return {
      kind: "review",
      title: "Review cards first",
      detail: "Handle the current cards before changing automation.",
      label: `Review ${reviewCount} card${reviewCount === 1 ? "" : "s"}`,
    };
  }
  const button = step?.buttons.find((item) => item.variant === "primary") ?? step?.buttons[0];
  if (!button) {
    return null;
  }
  return {
    kind: "scan",
    title: step?.title || "Run another scan",
    detail: "Create fresh review cards. Nothing sends to Telegram unless live delivery is enabled.",
    label: button.label,
    actionId: button.actionId,
  };
}

function StartPrimaryActionCard({
  action,
  anyBusy,
  busyActionId,
  onOpenReview,
  onRun,
}: {
  action: PrimaryReadyAction;
  anyBusy: boolean;
  busyActionId: string;
  onOpenReview?: () => void;
  onRun: (actionId: string) => Promise<void>;
}) {
  const busy = Boolean(action.actionId && busyActionId === action.actionId);
  return (
    <article className={`start-next-card is-${action.kind}`} aria-label="Recommended next action">
      <div>
        <span className="status new">Next</span>
        <h3>{action.title}</h3>
        <p>{action.detail}</p>
      </div>
      <button
        className="journey-button"
        disabled={anyBusy}
        onClick={() => {
          if (action.kind === "review") {
            onOpenReview?.();
            return;
          }
          if (action.actionId) {
            void onRun(action.actionId);
          }
        }}
        type="button"
      >
        {action.kind === "review" ? <ArrowRight size={16} /> : <Play size={16} />}
        <span>{busy ? "Working" : action.label}</span>
      </button>
    </article>
  );
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

function setupCheckDetail(setupStatus: DashboardState["setup_status"] | undefined, checkId: string) {
  const check = setupStatus?.checks?.find((item) => item.check_id === checkId);
  return check?.detail || "";
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
    return "Repair source list first";
  }
  if (stage === "needs_first_run") {
    return "Next";
  }
  return "Finish setup first";
}

function firstRunBlocked(stage: string, workspaceDone: boolean, sourceAttention: boolean, telegramReady: boolean) {
  return sourceAttention || !workspaceDone || !telegramReady || stage === "needs_profiles" || stage === "needs_enabled_profile";
}

function JourneyStepCard({
  actionMap,
  anyBusy,
  busyActionId,
  index,
  onRun,
  results,
  step,
  telegram,
}: {
  actionMap: Map<string, DeskAction>;
  anyBusy: boolean;
  busyActionId: string;
  index: number;
  onRun: (actionId: string) => Promise<void>;
  results: Record<string, DeskActionResult>;
  step: JourneyStep;
  telegram: TelegramControls;
}) {
  const disabled = step.state === "blocked";
  const visibleButtons = step.buttons.filter((button) => actionMap.has(button.actionId));
  const visibleAdvanced = step.advancedActionIds.map((actionId) => actionMap.get(actionId)).filter(Boolean) as DeskAction[];
  const hasProblemResult = step.advancedActionIds.some((actionId) => {
    const status = results[actionId]?.status;
    return status === "failed" || status === "blocked";
  });
  const showAdvancedReference = visibleAdvanced.length > 0 && (step.state === "manual" || hasProblemResult);
  return (
    <article className={`journey-step is-${step.state}`} aria-label={`${index}. ${step.title}`}>
      <div className="journey-marker" aria-hidden="true">
        {index}
      </div>
      <div className="journey-main">
        <div className="journey-title-row">
          <span className={`status ${statusClassFor(step.state)}`}>{step.stateLabel}</span>
          <h3>{step.title}</h3>
        </div>
        <p>{step.detail}</p>
        <JourneyResults actionIds={step.advancedActionIds} results={results} />
        {step.key === "telegram" && <TelegramLoginPanel telegram={telegram} />}
        {showAdvancedReference && (
          <details className="advanced-command">
            <summary>Advanced / CLI reference</summary>
            <div>
              {visibleAdvanced.map((action) => (
                <CopyableCommand command={action.display_command} label={action.title} key={action.action_id} compact />
              ))}
            </div>
          </details>
        )}
      </div>
      <aside className="journey-controls">
        <JourneyIcon state={step.state} />
        <div className="journey-buttons">
          {visibleButtons.map((button) => {
            const action = actionMap.get(button.actionId);
            const busy = busyActionId === button.actionId;
            const isNotificationShortcut = action?.action_id === "live_delivery_human";
            const isHuman = action?.run_mode === "needs_human" && !isNotificationShortcut;
            return (
              <button
                className={`journey-button ${button.variant === "secondary" || isHuman ? "secondary" : ""}`}
                disabled={disabled || anyBusy}
                key={button.actionId}
                onClick={() => void onRun(button.actionId)}
                title={button.label}
                type="button"
              >
                {isHuman ? <ShieldAlert size={15} /> : isNotificationShortcut ? <Bell size={15} /> : <Play size={15} />}
                <span>{busy ? "Working" : button.label}</span>
              </button>
            );
          })}
        </div>
      </aside>
    </article>
  );
}

function TelegramLoginPanel({ telegram }: { telegram: TelegramControls }) {
  const [apiId, setApiId] = useState("");
  const [apiHash, setApiHash] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const status = telegram.status;
  const busy = Boolean(telegram.busy);
  const needsCode = status?.login_state === "code_sent" || status?.login_state === "needs_password";
  const needsPassword = status?.login_state === "needs_password";
  const connected = Boolean(status?.session_ready);

  return (
    <div className="telegram-panel" aria-label="Telegram login controls">
      <div className="telegram-status-grid">
        <span className={status?.credentials_ready ? "ready" : ""}>
          <strong>{status?.credentials_ready ? "Saved" : "Needed"}</strong>
          App credentials
        </span>
        <span className={connected ? "ready" : ""}>
          <strong>{connected ? "Connected" : "Not connected"}</strong>
          Telegram session
        </span>
      </div>
      {status?.detail && <p className="telegram-status-note">{status.detail}</p>}
      {telegram.error && <p className="telegram-error">{telegram.error}</p>}

      {!connected && (
        <div className="telegram-forms">
          <form
            className="telegram-form credentials"
            onSubmit={(event) => {
              event.preventDefault();
              void telegram.saveCredentials(apiId, apiHash).then(() => {
                setApiHash("");
              }).catch(() => undefined);
            }}
          >
            <div className="telegram-form-intro">
              <strong>Step 1: Save app details</strong>
              <span>
                Get your Telegram app ID and app hash from{" "}
                <a href="https://my.telegram.org/apps" target="_blank" rel="noreferrer">
                  my.telegram.org
                </a>
                . They look like a number and a long letter code.
              </span>
            </div>
            <label>
              <span>Telegram app ID</span>
              <input
                autoComplete="off"
                inputMode="numeric"
                onChange={(event) => setApiId(event.target.value)}
                placeholder="123456"
                type="text"
                value={apiId}
              />
            </label>
            <label>
              <span>Telegram app hash</span>
              <input
                autoComplete="off"
                onChange={(event) => setApiHash(event.target.value)}
                placeholder="32-character app hash"
                type="password"
                value={apiHash}
              />
            </label>
            <button className="journey-button secondary" disabled={busy || !apiId.trim() || !apiHash.trim()} type="submit">
              <LockKeyhole size={15} />
              <span>{telegram.busy === "credentials" ? "Saving" : "Save credentials"}</span>
            </button>
          </form>

          <form
            className="telegram-form login"
            onSubmit={(event) => {
              event.preventDefault();
              if (needsCode) {
                void telegram.verifyCode(code, password).then((next) => {
                  if (next.session_ready) {
                    setCode("");
                    setPassword("");
                  }
                }).catch(() => undefined);
                return;
              }
              void telegram.sendCode(phone).catch(() => undefined);
            }}
          >
            <div className="telegram-form-intro">
              <strong>Step 2: Log in</strong>
              <span>Use the phone number for your Telegram account. Signal Desk stores the session only on this computer.</span>
            </div>
            <label>
              <span>Phone number</span>
              <input
                autoComplete="tel"
                disabled={needsCode}
                onChange={(event) => setPhone(event.target.value)}
                pattern="\+?[0-9][0-9 ()-]{5,24}"
                placeholder="+1..."
                type="tel"
                value={phone}
              />
            </label>
            {needsCode && (
              <label>
                <span>Verification code</span>
                <input
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  onChange={(event) => setCode(event.target.value)}
                  placeholder="Code from Telegram"
                  type="text"
                  value={code}
                />
              </label>
            )}
            {needsPassword && (
              <label>
                <span>Two-step verification password</span>
                <input
                  autoComplete="current-password"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Telegram password"
                  type="password"
                  value={password}
                />
              </label>
            )}
            <div className="telegram-form-actions">
              <button
                className="journey-button"
                disabled={busy || !status?.credentials_ready || (needsCode ? !code.trim() : !phone.trim())}
                type="submit"
              >
                <Play size={15} />
                <span>{telegram.busy === "send-code" ? "Sending" : telegram.busy === "verify-code" ? "Verifying" : needsCode ? "Finish login" : "Send code"}</span>
              </button>
              <button className="journey-button secondary" disabled={busy} onClick={() => void telegram.refresh().catch(() => undefined)} type="button">
                <CircleDashed size={15} />
                <span>Check Telegram</span>
              </button>
              {needsCode && (
                <button className="journey-button secondary" disabled={busy} onClick={() => void telegram.cancelLogin().catch(() => undefined)} type="button">
                  <AlertTriangle size={15} />
                  <span>Cancel</span>
                </button>
              )}
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function JourneyResults({ actionIds, results }: { actionIds: string[]; results: Record<string, DeskActionResult> }) {
  const visibleResults = actionIds.map((actionId) => results[actionId]).filter(Boolean);
  if (!visibleResults.length) {
    return null;
  }
  return (
    <div className="journey-results" aria-label="Recent Desk results">
      {visibleResults.map((result) => (
        <div className={`journey-result is-${result.status}`} key={result.action_id}>
          <strong>{result.title}</strong>
          {result.detail && <span>{result.detail}</span>}
          {result.artifact_path && (
            <a href={artifactHref(result.artifact_path)} target="_blank" rel="noreferrer">
              <ExternalLink size={14} />
              <span>Open result</span>
            </a>
          )}
          {result.next_action && <em>{result.next_action}</em>}
        </div>
      ))}
    </div>
  );
}

function artifactHref(path: string) {
  const clean = path.replace(/^\/+/, "");
  return `/artifacts/${clean.split("/").map(encodeURIComponent).join("/")}`;
}

function statusClassFor(state: JourneyState) {
  if (state === "done") {
    return "handled";
  }
  if (state === "blocked") {
    return "false-positive";
  }
  if (state === "manual") {
    return "pending";
  }
  return "new";
}

function JourneyIcon({ state }: { state: JourneyState }) {
  if (state === "done") {
    return <CheckCircle2 className="journey-state-icon success" size={20} />;
  }
  if (state === "blocked") {
    return <LockKeyhole className="journey-state-icon locked" size={20} />;
  }
  if (state === "manual") {
    return <ShieldAlert className="journey-state-icon human" size={20} />;
  }
  if (state === "active") {
    return <Wrench className="journey-state-icon active" size={20} />;
  }
  if (state === "ready") {
    return <CircleDashed className="journey-state-icon" size={20} />;
  }
  return <AlertTriangle className="journey-state-icon locked" size={20} />;
}
