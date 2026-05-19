import { useState } from "react";
import { ShieldCheck, UserRoundCog } from "lucide-react";

import { InlineEmpty } from "./common";
import { JourneyStepCard } from "./actions/journey-step-card";
import {
  buildJourneySteps,
  buildStartSummary,
  notificationReadiness,
  type JourneyStep,
} from "./actions/journey-model";
import { buildPrimaryReadyAction, StartPrimaryActionCard } from "./actions/primary-action-card";
import { StartManagementStrip } from "./actions/start-management-strip";
import { StartSummary } from "./actions/start-summary";
import { JourneyResults } from "./actions/journey-results";
import type { SettingsShortcutTarget, TelegramControls } from "./actions/types";
import type { DashboardState, DeliveryTarget, DeskAction, DeskActionResult, DeskActiveAction, DeskSchedulerStatus } from "../domain/types";

export { buildJourneySteps, buildStartSummary, notificationReadiness } from "./actions/journey-model";

const SETUP_STAGE_LABELS: Record<string, string> = {
  needs_ai_key: "Report setup",
  needs_profiles: "Preview ready",
  needs_enabled_profile: "Goal paused",
  needs_first_run: "Ready for report",
  needs_source_access: "Sources need help",
  needs_delivery_target: "Alerts optional",
  ready: "Inbox ready",
};

export function ActionsView({
  actions,
  activeActions = [],
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
  activeActions?: DeskActiveAction[];
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
  const stage = setupStatus?.stage ?? "";
  const stageLabel = SETUP_STAGE_LABELS[stage] ?? "Local setup";
  const startSummary = buildStartSummary(steps, setupStatus, telegram.status, scheduler, targets, reviewCount);
  const heroTitle = reviewCount > 0 ? "Review the latest signals" : setupStatus?.has_runs ? "Generate another report" : "Generate your first report";
  const heroDetail = reviewCount > 0
    ? "Handle the cards already waiting before changing setup."
    : setupStatus?.has_runs
      ? "Run a fresh local review when you want new cards."
      : "Start with a local sample report. Telegram, AI, and advanced settings can wait.";
  const compactReadyMode = !activeStep && (stage === "ready" || stage === "needs_delivery_target");
  const showCompactMoreControls = false;
  const firstRunStep = steps.find((step) => step.key === "first-run");
  const hasUserGoal = setupHasUserGoal(setupStatus);
  const showProfileGuide = !compactReadyMode && hasUserGoal === false;
  const showPrivacyBoundary = !compactReadyMode && setupStatus?.has_runs !== true;
  const showPostReviewControls = Boolean(setupStatus?.has_runs || reviewCount > 0 || stage === "ready" || stage === "needs_delivery_target");
  const secondaryReadyStepOrder = ["feedback", "automation"];
  const secondaryReadyStepKeys = new Set(["first-run", ...secondaryReadyStepOrder]);
  const visibleSteps = compactReadyMode
    ? []
    : steps.filter((step) => {
        if (!showPostReviewControls && ["automation", "feedback"].includes(step.key)) {
          return false;
        }
        return !(hasUserGoal === false && step.key === "telegram");
      });
  const secondaryReadySteps = compactReadyMode
    ? secondaryReadyStepOrder.map((key) => steps.find((step) => step.key === key)).filter(Boolean) as JourneyStep[]
    : [];
  const parkedSteps = compactReadyMode ? steps.filter((step) => !secondaryReadyStepKeys.has(step.key)) : [];
  const visibleJourneySteps = prioritizeCurrentStep(visibleSteps, activeStep?.key);
  const stepIndexes = new Map(steps.map((step, index) => [step.key, index + 1]));
  const primaryReadyAction = compactReadyMode
    ? buildPrimaryReadyAction(firstRunStep, reviewCount, Boolean(onOpenReview))
    : null;
  const primaryStartAction = buildPrimaryStartAction({
    steps,
    results,
    reviewCount,
    canOpenReview: Boolean(onOpenReview),
    canOpenProfiles: Boolean(onOpenProfiles),
    setupStatus,
  }) ?? primaryReadyAction;
  const demoResultReady = results.demo_render?.status === "success" && !setupStatus?.has_runs;
  const primaryStartResultActionIds = primaryStartAction?.actionId
    ? [primaryStartAction.actionId]
    : demoResultReady
      ? ["demo_render"]
      : [];
  const summaryBlock = (
    <StartSummary
      actionMap={actionMap}
      busyActionId={busyActionId}
      items={startSummary}
      onRun={onRun}
    />
  );
  const journeyCardProps = {
    actionMap,
    anyBusy: Boolean(busyActionId),
    activeActions,
    busyActionId,
    onRun,
    results,
    telegram,
  };

  return (
    <section className="actions-view start-view">
      <section className="start-hero" aria-label="Signal Desk start">
        <span className="panel-kicker">Start</span>
        <div className="start-hero-main">
          <div>
            <h2>{heroTitle || "Open Signal Desk"}</h2>
            {heroDetail && <p>{heroDetail}</p>}
          </div>
          <div className="start-stage" aria-label="Current setup stage">
            <span>{stageLabel}</span>
            <strong>{activeStep ? activeStep.stateLabel || "Ready" : "Ready"}</strong>
          </div>
        </div>
      </section>

      {loadError && <InlineEmpty title={loadError} tone="error" />}
      {!actions.length && !loadError && (
        <InlineEmpty title="Signal Desk controls are not exposed by the local server." tone="warning" />
      )}

      {primaryStartAction && (
        <StartPrimaryActionCard
          action={primaryStartAction}
          anyBusy={Boolean(busyActionId)}
          activeActions={activeActions}
          busyActionId={busyActionId}
          onOpenProfiles={onOpenProfiles}
          onOpenReview={onOpenReview}
          onRun={onRun}
        />
      )}

      {primaryStartResultActionIds.length > 0 && (
        <div className="start-primary-results">
          <JourneyResults actionIds={primaryStartResultActionIds} results={results} />
        </div>
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
              <strong>Fix only the setup area that needs attention</strong>
            </div>
            <button className="journey-button secondary" type="button" onClick={() => setShowSetupSteps(false)}>
              Close
            </button>
          </div>
          <div className="start-setup-guide">
            <strong>Current repair path first.</strong>
            <span>Completed steps stay available for recovery without crowding the main action.</span>
          </div>
          <StartProfileGuide onOpenProfiles={onOpenProfiles} />
          <div className="journey-list">
            {steps.map((step, index) => (
              <JourneyStepCard
                {...journeyCardProps}
                index={index + 1}
                key={step.key}
                step={step}
              />
            ))}
          </div>
        </section>
      )}

      {!compactReadyMode && actions.length > 0 && (
        <details className="start-setup-drawer start-real-setup" aria-label="Set up your first scan">
          <summary>
            <span>Set up your first scan</span>
            <small>Goal, Telegram, sources, and AI checks</small>
          </summary>
          {summaryBlock}
          {showProfileGuide && <StartProfileGuide onOpenProfiles={onOpenProfiles} />}
          {showPrivacyBoundary && <StartPrivacyBoundary onOpenSupport={() => onOpenSettings?.("support")} />}
          <div className="journey-list">
            {visibleJourneySteps.map((step, index) => (
              <JourneyStepCard
                {...journeyCardProps}
                index={stepIndexes.get(step.key) ?? index + 1}
                key={step.key}
                step={step}
              />
            ))}
          </div>
        </details>
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
                      {...journeyCardProps}
                      index={index + 1}
                      key={step.key}
                      step={step}
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
                      {...journeyCardProps}
                      index={index + 1}
                      key={step.key}
                      step={step}
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
                    {...journeyCardProps}
                    index={index + 1}
                    key={step.key}
                    step={step}
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
                    {...journeyCardProps}
                    index={index + 1}
                    key={step.key}
                    step={step}
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

function StartProfileGuide({ onOpenProfiles }: { onOpenProfiles?: () => void }) {
  return (
    <section className="start-profile-guide" aria-label="Create profile guidance">
      <div>
        <span className="panel-kicker">Profile builder</span>
        <strong>Create a monitor in plain language</strong>
        <p>Tell Signal Desk what to watch for, or start from built-in goals like developer jobs, crypto opportunities, or competitor signals.</p>
      </div>
      <button className="journey-button" disabled={!onOpenProfiles} onClick={() => onOpenProfiles?.()} type="button">
        <UserRoundCog size={15} />
        <span>Create profile</span>
      </button>
    </section>
  );
}

function StartPrivacyBoundary({ onOpenSupport }: { onOpenSupport?: () => void }) {
  return (
    <section className="start-boundary-note" aria-label="Local privacy and Telegram boundary">
      <div>
        <span className="panel-kicker">Local boundary</span>
        <strong>Telegram access stays explicit</strong>
        <p>
          T-Sense runs as a third-party Telegram API client. Only scan sources you can access, and review them before running an AI scan.
          Sessions, reports, and review state stay on this Mac by default.
        </p>
      </div>
      <button className="journey-button secondary" disabled={!onOpenSupport} onClick={() => onOpenSupport?.()} type="button">
        <ShieldCheck size={15} />
        <span>Data boundaries</span>
      </button>
    </section>
  );
}

function buildPrimaryStartAction({
  canOpenProfiles,
  canOpenReview,
  results,
  reviewCount,
  setupStatus,
  steps,
}: {
  canOpenProfiles: boolean;
  canOpenReview: boolean;
  results: Record<string, DeskActionResult>;
  reviewCount: number;
  setupStatus?: DashboardState["setup_status"];
  steps: JourneyStep[];
}) {
  if (reviewCount > 0 && canOpenReview) {
    return buildPrimaryReadyAction(undefined, reviewCount, canOpenReview);
  }

  const firstRunStep = steps.find((step) => step.key === "first-run");
  const firstRunButton = firstRunStep?.buttons.find((button) => button.actionId === "monitor_jobs_dry_run");
  const canRunRealReport = Boolean(firstRunButton && (firstRunStep?.state === "active" || firstRunStep?.state === "ready"));
  if (canRunRealReport && firstRunButton) {
    return {
      kind: "scan" as const,
      title: setupStatus?.has_runs ? "Generate another report" : "Generate first real report",
      detail: "Scan the saved Telegram sources and create review cards locally.",
      label: setupStatus?.has_runs ? "Generate report" : "Generate first report",
      actionId: firstRunButton.actionId,
    };
  }

  const demoStep = steps.find((step) => step.key === "demo");
  const demoButton = demoStep?.buttons.find((button) => button.actionId === "demo_render");
  const demoReady = results.demo_render?.status === "success";
  if (demoButton && !demoReady) {
    return {
      kind: "scan" as const,
      title: "Generate a sample report",
      detail: "See what T-Sense produces before connecting Telegram or AI.",
      label: "Generate demo report",
      actionId: demoButton.actionId,
    };
  }

  if (setupHasUserGoal(setupStatus) === false) {
    return {
      kind: "profile" as const,
      title: "Create your monitor",
      detail: "Describe what T-Sense should watch before connecting Telegram sources.",
      label: "Create profile",
    };
  }

  const activeStep = steps.find((step) => step.state === "active");
  const activeButton = activeStep?.buttons.find((button) => button.variant === "primary") ?? activeStep?.buttons[0];
  if (activeStep && activeButton) {
    return {
      kind: "scan" as const,
      title: activeStep.title,
      detail: activeStep.detail,
      label: activeButton.label,
      actionId: activeButton.actionId,
    };
  }

  if (demoButton) {
    return {
      kind: "scan" as const,
      title: "Sample report is ready",
      detail: "Refresh the local sample report any time from setup controls.",
      label: "Refresh sample report",
      actionId: demoButton.actionId,
    };
  }

  return null;
}

function setupHasUserGoal(setupStatus: DashboardState["setup_status"] | undefined) {
  if (!setupStatus) {
    return undefined;
  }
  return setupStatus.has_user_goal ?? setupStatus.has_profiles;
}

function prioritizeCurrentStep(steps: JourneyStep[], activeKey?: string) {
  if (!activeKey) {
    return steps;
  }
  const current = steps.find((step) => step.key === activeKey);
  if (!current) {
    return steps;
  }
  return [current, ...steps.filter((step) => step.key !== activeKey)];
}
