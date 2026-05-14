import { AlertTriangle, Bell, CheckCircle2, CircleDashed, LockKeyhole, Play, Settings, ShieldAlert, Wrench } from "lucide-react";

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
  const visibleButtons = step.buttons.filter((button) => actionMap.has(button.actionId) || button.actionId.startsWith("settings_"));
  const quickButtons = quickJourneyButtons(step, visibleButtons);
  const quickActionIds = new Set(quickButtons.map((button) => button.actionId));
  const extraButtons = visibleButtons.filter((button) => !quickActionIds.has(button.actionId));
  const resultActionIds = visibleJourneyResultActionIds(step, telegram, results);
  const activeAction = step.advancedActionIds
    .map((actionId) => activeActions.find((item) => item.action_id === actionId))
    .find(Boolean);
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
        <JourneyResults actionIds={resultActionIds} results={results} />
        {step.key === "telegram" && <TelegramLoginPanel telegram={telegram} />}
      </div>
      <aside className="journey-controls">
        <JourneyIcon state={step.state} />
        <div className={extraButtons.length ? "journey-buttons has-extra-actions" : "journey-buttons"}>
          {quickButtons.map((button) => (
            <JourneyActionButton
              actionMap={actionMap}
              anyBusy={anyBusy}
              busyActionId={busyActionId}
              disabled={disabled}
              key={button.actionId}
              onRun={onRun}
              button={button}
            />
          ))}
          {extraButtons.length > 0 && (
            <details className="journey-extra-actions">
              <summary>{step.state === "done" ? "More checks" : "Other actions"}</summary>
              <div>
                {extraButtons.map((button) => (
                  <JourneyActionButton
                    actionMap={actionMap}
                    anyBusy={anyBusy}
                    busyActionId={busyActionId}
                    disabled={disabled}
                    key={button.actionId}
                    onRun={onRun}
                    button={button}
                    compact
                  />
                ))}
              </div>
            </details>
          )}
        </div>
      </aside>
    </article>
  );
}

function visibleJourneyResultActionIds(
  step: JourneyStep,
  telegram: TelegramControls,
  results: Record<string, DeskActionResult>,
) {
  const telegramReady = Boolean(telegram.status?.credentials_ready && telegram.status?.session_ready);
  return step.advancedActionIds.filter((actionId) => {
    const result = results[actionId];
    if (!result) {
      return true;
    }
    if (step.state === "done" && isProblemResult(result)) {
      return false;
    }
    if (step.key === "telegram" && telegramReady && isProblemResult(result)) {
      return false;
    }
    if (step.key === "workspace" && telegramReady && isTelegramPrerequisiteResult(result)) {
      return false;
    }
    return true;
  });
}

function isProblemResult(result: DeskActionResult) {
  const status = String(result.status || "").toLowerCase();
  return status !== "success" && status !== "needs_human";
}

function isTelegramPrerequisiteResult(result: DeskActionResult) {
  const text = `${result.title} ${result.detail} ${result.next_action}`.toLowerCase();
  return (
    text.includes("telegram api credentials") ||
    text.includes("app credentials") ||
    text.includes("telegram login") ||
    text.includes("connect telegram") ||
    text.includes("finish telegram")
  );
}

function quickJourneyButtons(step: JourneyStep, buttons: JourneyStep["buttons"]) {
  if (buttons.length <= 2) {
    return buttons;
  }
  const primaryButtons = buttons.filter((button) => button.variant === "primary");
  if (primaryButtons.length > 0) {
    return primaryButtons.slice(0, 2);
  }
  if (step.key === "workspace") {
    const preferredOrder = ["sources_probe_access", "sources_keep_accessible", "sources_import_jobs", "init_jobs"];
    const preferred = preferredOrder
      .map((actionId) => buttons.find((button) => button.actionId === actionId))
      .filter(Boolean) as JourneyStep["buttons"];
    if (preferred.length > 0) {
      return preferred.slice(0, 2);
    }
  }
  return buttons.slice(0, 2);
}

function JourneyActionButton({
  actionMap,
  anyBusy,
  busyActionId,
  button,
  compact = false,
  disabled,
  onRun,
}: {
  actionMap: Map<string, DeskAction>;
  anyBusy: boolean;
  busyActionId: string;
  button: JourneyStep["buttons"][number];
  compact?: boolean;
  disabled: boolean;
  onRun: (actionId: string) => Promise<void>;
}) {
  const action = actionMap.get(button.actionId);
  const busy = busyActionId === button.actionId;
  const isNotificationShortcut = action?.action_id === "live_delivery_human";
  const isSettingsShortcut = button.actionId.startsWith("settings_");
  const isHuman = action?.run_mode === "needs_human" && !isNotificationShortcut;
  return (
    <button
      className={`journey-button ${button.variant === "secondary" || isHuman ? "secondary" : ""} ${compact ? "compact" : ""}`}
      disabled={disabled || anyBusy}
      onClick={() => void onRun(button.actionId)}
      title={button.label}
      type="button"
    >
      {isHuman ? <ShieldAlert size={15} /> : isNotificationShortcut ? <Bell size={15} /> : isSettingsShortcut ? <Settings size={15} /> : <Play size={15} />}
      <span>{busy ? "Working" : button.label}</span>
    </button>
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
