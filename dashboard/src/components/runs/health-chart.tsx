import { useState } from "react";

import { formatPercent } from "../../domain/format";
import type { Run } from "../../domain/types";
import { buildRunHealthDecision, type RunHealthDecision } from "./model";

const MANUAL_SCAN_WINDOWS = [
  { hours: 2, label: "2 hours", detail: "Fresh check" },
  { hours: 12, label: "12 hours", detail: "Catch-up scan" },
  { hours: 24, label: "24 hours", detail: "Full day" },
] as const;

type RunDeskActionHandler = (actionId: string, body?: Record<string, unknown>) => void;

export function RunHealthChart({
  runs,
  onRunDeskAction,
  onOpenReview,
  onOpenProfiles,
}: {
  runs: Run[];
  onRunDeskAction?: RunDeskActionHandler;
  onOpenReview?: () => void;
  onOpenProfiles?: () => void;
}) {
  const recentRuns = runs.slice(0, 80);
  const completeRuns = recentRuns.filter((run) => run.status.toLowerCase() === "complete").length;
  const failedRuns = recentRuns.filter((run) => run.status.toLowerCase() === "failed").length;
  const runningRuns = recentRuns.filter((run) => ["running", "pending"].includes(run.status.toLowerCase())).length;
  const cards = recentRuns.reduce((sum, run) => sum + (run.review_card_count ?? 0), 0);
  const alerts = recentRuns.reduce((sum, run) => sum + (run.alert_count ?? 0), 0);
  const settledRuns = completeRuns + failedRuns;
  const successRate = settledRuns ? completeRuns / settledRuns : 0;
  const decision = buildRunHealthDecision(recentRuns);
  return (
    <div className="run-health-chart" aria-label="Recent run health by day">
      <div className="run-health-summary" data-tone={decision.tone}>
        <div className="run-health-score">
          <small>Run health</small>
          <strong>{formatPercent(successRate)}</strong>
          <span>
            {completeRuns} ok / {failedRuns} failed
          </span>
          {runningRuns > 0 && <span>{runningRuns} in progress</span>}
          <span>{cards} cards / {alerts} alerts</span>
        </div>
        <div className={`run-health-decision is-${decision.tone}`}>
          <b>{decision.headline}</b>
          <span title={decision.detail}>{runHealthDecisionVisibleDetail(decision)}</span>
          <RunHealthDecisionActions
            decision={decision}
            onOpenProfiles={onOpenProfiles}
            onOpenReview={onOpenReview}
            onRunDeskAction={onRunDeskAction}
          />
        </div>
      </div>
      <ManualScanSettings onRunDeskAction={onRunDeskAction} />
    </div>
  );
}

function ManualScanSettings({ onRunDeskAction }: { onRunDeskAction?: RunDeskActionHandler }) {
  const [hours, setHours] = useState(24);
  return (
    <section className="manual-scan-panel" aria-label="Manual scan settings">
      <div className="manual-scan-heading">
        <small>Manual scan</small>
        <strong>One-off scan window</strong>
      </div>
      <div className="manual-scan-options" role="group" aria-label="Scan window">
        {MANUAL_SCAN_WINDOWS.map((option) => (
          <button
            aria-pressed={hours === option.hours}
            className={`manual-scan-option ${hours === option.hours ? "is-selected" : ""}`}
            key={option.hours}
            onClick={() => setHours(option.hours)}
            type="button"
          >
            <b>{option.label}</b>
            <span>{option.detail}</span>
          </button>
        ))}
      </div>
      <button
        className="manual-scan-run"
        disabled={!onRunDeskAction}
        onClick={() => onRunDeskAction?.("monitor_jobs_dry_run", { scan_window_hours: hours })}
        type="button"
      >
        Run one-off scan
      </button>
    </section>
  );
}

function RunHealthDecisionActions({
  decision,
  onRunDeskAction,
  onOpenReview,
  onOpenProfiles,
}: {
  decision: RunHealthDecision;
  onRunDeskAction?: RunDeskActionHandler;
  onOpenReview?: () => void;
  onOpenProfiles?: () => void;
}) {
  if (decision.tone === "danger") {
    if (decision.repairKind === "profile_scope") {
      return (
        <div className="run-health-actions">
          <button type="button" onClick={onOpenProfiles} disabled={!onOpenProfiles}>
            Tune profile
          </button>
          <button type="button" onClick={() => onRunDeskAction?.("doctor_jobs")} disabled={!onRunDeskAction}>
            Check setup
          </button>
          <button type="button" onClick={() => onRunDeskAction?.("monitor_jobs_dry_run")} disabled={!onRunDeskAction}>
            Run fresh scan
          </button>
        </div>
      );
    }
    return (
      <div className="run-health-actions">
        {decision.repairKind === "source_access" && (
          <button type="button" onClick={() => onRunDeskAction?.("sources_import_jobs")} disabled={!onRunDeskAction}>
            Fix channels
          </button>
        )}
        <button type="button" onClick={() => onRunDeskAction?.("doctor_jobs")} disabled={!onRunDeskAction}>
          Check setup
        </button>
        <button type="button" onClick={() => onRunDeskAction?.("monitor_jobs_dry_run")} disabled={!onRunDeskAction}>
          Run fresh scan
        </button>
      </div>
    );
  }
  if (decision.tone === "warn") {
    return (
      <div className="run-health-actions">
        <button type="button" onClick={() => onRunDeskAction?.("doctor_jobs")} disabled={!onRunDeskAction}>
          Check setup
        </button>
        <button type="button" onClick={() => onRunDeskAction?.("monitor_jobs_dry_run")} disabled={!onRunDeskAction}>
          Run fresh scan
        </button>
      </div>
    );
  }
  if (decision.tone === "info" && /Review/i.test(decision.headline)) {
    return (
      <div className="run-health-actions">
        <button type="button" onClick={onOpenReview} disabled={!onOpenReview}>
          Open Review
        </button>
      </div>
    );
  }
  return null;
}

function runHealthDecisionVisibleDetail(decision: RunHealthDecision) {
  if (decision.headline.startsWith("Review ") && decision.headline.includes("alert candidate")) {
    return "Open Review before live alerts.";
  }
  if (decision.headline.startsWith("Review ")) {
    return "Open Review to handle cards.";
  }
  if (decision.headline === "Fix failed scans") {
    return "Fix channels, check setup, then scan again.";
  }
  if (decision.headline === "Fix AI matching") {
    return "Tune profile, check setup, then scan again.";
  }
  return decision.detail;
}
