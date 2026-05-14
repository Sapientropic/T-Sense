import { percentWidth } from "../../domain/display";
import { formatPercent } from "../../domain/format";
import { runBucketSignalScore, runDayWindowBuckets } from "../../domain/projections";
import type { Run } from "../../domain/types";
import { buildRunHealthDecision, type RunHealthDecision } from "./model";

export function RunHealthChart({
  runs,
  onRunDeskAction,
  onOpenReview,
  onOpenProfiles,
}: {
  runs: Run[];
  onRunDeskAction?: (actionId: string) => void;
  onOpenReview?: () => void;
  onOpenProfiles?: () => void;
}) {
  const recentRuns = runs.slice(0, 80);
  const buckets = runDayWindowBuckets(recentRuns, 7);
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
      <div className="run-health-week" aria-label="Past 7 days scan health">
        {buckets.map((bucket) => (
          <div
            className={`run-health-day ${bucket.failed ? "is-warn" : bucket.runs ? "is-ok" : "is-quiet"}`}
            key={bucket.key}
            title={`${bucket.label} · ${bucket.complete} complete · ${bucket.failed} failed · ${bucket.cards} cards · ${bucket.alerts} alerts`}
          >
            <span>{bucket.label}</span>
            <strong>{bucket.failed > 0 ? `Fix ${bucket.failed}` : bucket.runs ? "OK" : "No scan"}</strong>
            <small>{bucket.runs ? `${bucket.cards} cards · ${bucket.alerts} alerts` : "No run"}</small>
            <div className="run-health-day-meter" aria-hidden="true">
              <i style={{ width: percentWidth(bucket.failed > 0 ? 1 : runBucketSignalScore(bucket)) }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RunHealthDecisionActions({
  decision,
  onRunDeskAction,
  onOpenReview,
  onOpenProfiles,
}: {
  decision: RunHealthDecision;
  onRunDeskAction?: (actionId: string) => void;
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
    return "Open Review to triage signals.";
  }
  if (decision.headline === "Fix failed scans") {
    return "Fix channels, check setup, then scan again.";
  }
  if (decision.headline === "Fix semantic extraction") {
    return "Tune profile, check setup, then scan again.";
  }
  return decision.detail;
}
