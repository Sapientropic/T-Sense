import { useState } from "react";
import { UserRoundCog } from "lucide-react";

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
import type { SettingsShortcutTarget, TelegramControls } from "./actions/types";
import type { DashboardState, DeliveryTarget, DeskAction, DeskActionResult, DeskActiveAction, DeskSchedulerStatus } from "../domain/types";

export { buildJourneySteps, buildStartSummary, notificationReadiness } from "./actions/journey-model";

const SETUP_STAGE_LABELS: Record<string, string> = {
  needs_ai_key: "AI setup",
  needs_profiles: "Workspace setup",
  needs_enabled_profile: "Profile needs enabling",
  needs_first_run: "Ready for AI review",
  needs_source_access: "Source access needs attention",
  needs_delivery_target: "Delivery optional",
  ready: "Review inbox ready",
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
  const currentStep = activeStep ?? steps.find((step) => step.state === "ready") ?? steps.find((step) => step.state === "manual") ?? steps[0];
  const stage = setupStatus?.stage ?? "";
  const stageLabel = SETUP_STAGE_LABELS[stage] ?? "Local setup";
  const startSummary = buildStartSummary(steps, setupStatus, telegram.status, scheduler, targets, reviewCount);
  const heroTitle = activeStep ? currentStep?.title : "Signal Desk is ready";
  const heroDetail = activeStep
    ? currentStep?.detail
    : reviewCount
      ? ""
      : "Run a fresh AI review first. Automation and notifications can wait.";
  const compactReadyMode = !activeStep && (stage === "ready" || stage === "needs_delivery_target");
  const showCompactMoreControls = false;
  const firstRunStep = steps.find((step) => step.key === "first-run");
  const secondaryReadyStepOrder = ["feedback", "automation"];
  const secondaryReadyStepKeys = new Set(["first-run", ...secondaryReadyStepOrder]);
  const visibleSteps = compactReadyMode ? [] : steps;
  const secondaryReadySteps = compactReadyMode
    ? secondaryReadyStepOrder.map((key) => steps.find((step) => step.key === key)).filter(Boolean) as JourneyStep[]
    : [];
  const parkedSteps = compactReadyMode ? steps.filter((step) => !secondaryReadyStepKeys.has(step.key)) : [];
  const visibleJourneySteps = prioritizeCurrentStep(visibleSteps, activeStep?.key);
  const stepIndexes = new Map(steps.map((step, index) => [step.key, index + 1]));
  const primaryReadyAction = compactReadyMode
    ? buildPrimaryReadyAction(firstRunStep, reviewCount, Boolean(onOpenReview))
    : null;
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
          activeActions={activeActions}
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

      {!compactReadyMode && (
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
