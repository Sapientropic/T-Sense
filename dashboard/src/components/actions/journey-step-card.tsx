import { AlertTriangle, Bell, CheckCircle2, CircleDashed, LockKeyhole, Play, ShieldAlert, Wrench } from "lucide-react";

import { CopyableCommand } from "../common";
import type { DeskAction, DeskActionResult, DeskActiveAction } from "../../domain/types";
import { JourneyResults } from "./journey-results";
import type { JourneyState, JourneyStep } from "./journey-model";
import { TelegramLoginPanel } from "./telegram-login-panel";
import type { TelegramControls } from "./types";

export function JourneyStepCard({
  activeActions,
  actionMap,
  anyBusy,
  busyActionId,
  index,
  onRun,
  results,
  step,
  telegram,
}: {
  activeActions: DeskActiveAction[];
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
  const activeAction = step.advancedActionIds
    .map((actionId) => activeActions.find((item) => item.action_id === actionId))
    .find(Boolean);
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
        <p title={step.detailTitle || step.detail}>{step.detail}</p>
        {activeAction && <ActiveActionProgress action={activeAction} />}
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

export function ActiveActionProgress({ action }: { action: DeskActiveAction }) {
  const total = typeof action.total_count === "number" ? action.total_count : 0;
  const checked = typeof action.checked_count === "number" ? action.checked_count : 0;
  const elapsed = typeof action.elapsed_seconds === "number" ? formatElapsed(action.elapsed_seconds) : "";
  const progress = total > 0 ? `Checked ${checked}/${total}.` : "";
  return (
    <div className="journey-progress" role="status">
      <strong>{action.title}</strong>
      <span>{action.detail || "Running locally. Keep Signal Desk open."}</span>
      {(progress || elapsed) && <em>{[progress, elapsed].filter(Boolean).join(" ")}</em>}
    </div>
  );
}

function formatElapsed(seconds: number) {
  if (seconds < 60) {
    return `${seconds}s elapsed`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes}m ${remainder}s elapsed` : `${minutes}m elapsed`;
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
