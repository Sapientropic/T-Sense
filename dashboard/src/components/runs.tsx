import { useState, type CSSProperties } from "react";
import { Activity, Clock3, ExternalLink } from "lucide-react";

import { EmptyStateShell, PanelHeader } from "./common";
import {
  artifactDisplayName,
  artifactHref,
  artifactShortDetail,
  artifactShortLabel,
  diagnosticTone,
  percentWidth,
  runDisplayDetail,
  runDisplayTitle,
  toneClass,
} from "../domain/display";
import { formatPercent } from "../domain/format";
import {
  formatRunDiagnosticAction,
  formatRunDiagnostics,
  runBucketSignalScore,
  runDayWindowBuckets,
  runHealthDetail,
} from "../domain/projections";
import type { Run, RunDayBucket } from "../domain/types";

const RECENT_RUN_LIMIT = 8;

type RunHealthDecision = {
  tone: "ok" | "info" | "warn" | "danger";
  headline: string;
  detail: string;
};

type RunTone = "ok" | "info" | "warn" | "danger" | "quiet";

type RunOutcome = {
  tone: RunTone;
  title: string;
  detail: string;
};

type RunEvidenceGroup = {
  key: "attention" | "review" | "clean";
  tone: RunTone;
  title: string;
  detail: string;
  runs: Run[];
  clusters: RunEvidenceCluster[];
};

type RunEvidenceCluster = {
  key: string;
  outcome: RunOutcome;
  sample: Run;
  runs: Run[];
  cards: number;
  alerts: number;
  failed: number;
};

type CompactTimelineItem = {
  key: string;
  tone: RunTone;
  label: string;
  value: string;
  detail: string;
};

export function RunsView({
  runs,
  onRunDeskAction,
  onOpenReview,
}: {
  runs: Run[];
  onRunDeskAction?: (actionId: string) => void;
  onOpenReview?: () => void;
}) {
  if (!runs.length) {
    return (
      <RunsEmptyState
        title="No runs yet"
        detail="Run a local practice scan before judging source quality."
        onRunDeskAction={onRunDeskAction}
      />
    );
  }
  const evidenceGroups = buildRunEvidenceGroups(runs);
  const visibleClusters = evidenceGroups.flatMap((group) => group.clusters);
  const visibleScaleMax = runCountScaleMax(visibleClusters);
  const visibleRunCount = evidenceGroups.reduce((sum, group) => sum + group.runs.length, 0);
  const archivedRuns = runs.slice(RECENT_RUN_LIMIT);
  const archivedClusters = archivedRuns.map((run) => buildSingleRunCluster(run));
  const archivedScaleMax = runCountScaleMax(archivedClusters);
  return (
    <section className="table-section" aria-label="Run history">
      <PanelHeader icon={<Activity size={18} />} title="Runs" />
      <RunHealthChart runs={runs} onOpenReview={onOpenReview} onRunDeskAction={onRunDeskAction} />
      <div className="run-list-head">
        <strong>Recent Evidence</strong>
        <span>
          {visibleRunCount} recent · {runs.length} total
        </span>
      </div>
      <div className="run-evidence-groups">
        {evidenceGroups.map((group) => (
          <RunEvidenceGroupPanel group={group} key={group.key} scaleMax={visibleScaleMax} />
        ))}
      </div>
      {archivedRuns.length > 0 && (
        <details className="run-archive">
          <summary>Scan history for troubleshooting ({archivedRuns.length})</summary>
          <div className="table-list">
            {archivedClusters.map((cluster) => (
              <RunClusterRow key={cluster.key} cluster={cluster} scaleMax={archivedScaleMax} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function RunEvidenceGroupPanel({ group, scaleMax }: { group: RunEvidenceGroup; scaleMax: number }) {
  const [open, setOpen] = useState(() => shouldOpenRunEvidenceByDefault());
  const historyOnly = group.key === "attention" && group.tone !== "danger";
  return (
    <details
      aria-label={group.title}
      className={`run-evidence-group is-${group.tone}`}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary className="run-evidence-head">
        <strong>{group.title}</strong>
        <span>{group.detail}</span>
        <b>{open ? "Collapse" : "View"}</b>
      </summary>
      <div className="run-evidence-body">
        {group.key === "attention" && (
          <p className="run-evidence-next">
            {group.tone === "danger"
              ? "Fix order: Fix channels, Check setup, then Run fresh scan."
              : "Latest scan recovered. These older failures are kept only for troubleshooting history."}
          </p>
        )}
        <div className="table-list">
          {group.clusters.map((cluster) => (
            <RunClusterRow key={cluster.key} cluster={cluster} scaleMax={scaleMax} historyOnly={historyOnly} />
          ))}
        </div>
      </div>
    </details>
  );
}

function shouldOpenRunEvidenceByDefault() {
  if (typeof window === "undefined") {
    return true;
  }
  return window.innerWidth > 680;
}

function RunClusterRow({ cluster, scaleMax, historyOnly = false }: { cluster: RunEvidenceCluster; scaleMax: number; historyOnly?: boolean }) {
  const run = cluster.sample;
  const artifact = run.report_artifact ?? null;
  const outcome = historyOnly ? historicalRunOutcome(cluster.outcome, cluster.failed) : cluster.outcome;
  const runCountLabel = cluster.runs.length === 1 ? runDisplayDetail(run) : `${cluster.runs.length} runs · latest ${runDisplayDetail(run)}`;
  const statusLabel = historyOnly ? "History" : cluster.runs.length === 1 ? run.status : cluster.failed > 0 ? `${cluster.failed} failed` : `${cluster.runs.length} runs`;
  const outcomeDetail = outcome.detail;
  return (
    <div className="table-row run-row" data-run-tone={outcome.tone}>
      <div className="run-primary">
        <strong>{outcome.title}</strong>
        <small>{[runDisplayTitle(run), runCountLabel].filter(Boolean).join(" · ")}</small>
        <span>{outcomeDetail}</span>
      </div>
      <span className={`status ${historyOnly ? "unknown" : toneClass(statusLabel)}`}>{statusLabel}</span>
      <RunCountBars cards={cluster.cards} alerts={cluster.alerts} scaleMax={scaleMax} />
      <div className="run-health" title={runHealthDetail(run.quality)}>
        <span className={diagnosticTone(run.quality)}>{formatRunDiagnostics(run.quality)}</span>
      </div>
      {artifact ? (
        <a
          className="artifact-link"
          href={artifactHref(artifact.path)}
          aria-label={`Open ${artifactDisplayName(artifact, run)}`}
          rel="noreferrer"
          target="_blank"
          title={artifact.display_path || artifactDisplayName(artifact, run)}
        >
          <ExternalLink size={14} />
          <span>{artifactShortLabel(artifact)}</span>
          <small>{cluster.runs.length === 1 ? artifactShortDetail(artifact, run) : `Latest report · 1 of ${cluster.runs.length} runs`}</small>
        </a>
      ) : (
        <span className="run-report-missing">No report</span>
      )}
    </div>
  );
}

function historicalRunOutcome(outcome: RunOutcome, failed: number): RunOutcome {
  if (outcome.tone !== "danger" && outcome.tone !== "warn") {
    return outcome;
  }
  const title = failed > 1 ? `${failed} past failed scans` : "Past failed scan";
  return {
    tone: "quiet",
    title,
    detail: "Recovered by a newer scan. No action needed unless this repeats.",
  };
}

function RunCountBars({ cards, alerts, scaleMax }: { cards: number; alerts: number; scaleMax: number }) {
  const maxValue = Math.max(1, scaleMax, cards, alerts);
  return (
    <div className="run-count-bars" aria-label={`${cards} cards, ${alerts} alerts`}>
      <span style={{ "--bar": percentWidth(cards / maxValue) } as CSSProperties}>
        <i />
        <b>{cards}</b>
        <em>cards</em>
      </span>
      <span style={{ "--bar": percentWidth(alerts / maxValue) } as CSSProperties}>
        <i />
        <b>{alerts}</b>
        <em>alerts</em>
      </span>
    </div>
  );
}

export function runCountScaleMax(clusters: Array<{ cards: number; alerts: number }>) {
  return Math.max(1, ...clusters.map((cluster) => Math.max(cluster.cards, cluster.alerts)));
}

function RunHealthChart({
  runs,
  onRunDeskAction,
  onOpenReview,
}: {
  runs: Run[];
  onRunDeskAction?: (actionId: string) => void;
  onOpenReview?: () => void;
}) {
  const recentRuns = runs.slice(0, 80);
  const buckets = runDayWindowBuckets(recentRuns, 7);
  const totalRuns = recentRuns.length;
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
          <span>{completeRuns} ok / {failedRuns} failed</span>
          {runningRuns > 0 && <span>{runningRuns} in progress</span>}
          <span>{cards} cards / {alerts} alerts</span>
        </div>
        <div className={`run-health-decision is-${decision.tone}`}>
          <b>{decision.headline}</b>
          <span title={decision.detail}>{runHealthDecisionVisibleDetail(decision)}</span>
          <RunHealthDecisionActions
            decision={decision}
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
}: {
  decision: RunHealthDecision;
  onRunDeskAction?: (actionId: string) => void;
  onOpenReview?: () => void;
}) {
  if (decision.tone === "danger") {
    return (
      <div className="run-health-actions">
        <button type="button" onClick={() => onRunDeskAction?.("sources_import_jobs")} disabled={!onRunDeskAction}>
          Fix channels
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

export function buildRunEvidenceGroups(runs: Run[]): RunEvidenceGroup[] {
  const visibleRuns = runs.slice(0, RECENT_RUN_LIMIT);
  const latest = latestRun(runs);
  const latestFailed = latest?.status.toLowerCase() === "failed";
  const groups = [
    {
      key: "attention",
      tone: latestFailed ? "danger" : "quiet",
      title: latestFailed ? "Failed scans to fix" : "Earlier failed scans",
      detail: latestFailed ? "Use the repair buttons above first" : "History only after latest OK",
      runs: visibleRuns.filter((run) => evidenceBucket(run) === "attention"),
    },
    {
      key: "review",
      tone: "info",
      title: "Review work",
      detail: "Cards and alert candidates",
      runs: visibleRuns.filter((run) => evidenceBucket(run) === "review"),
    },
    {
      key: "clean",
      tone: "quiet",
      title: "Clean background scans",
      detail: "No user action needed",
      runs: visibleRuns.filter((run) => evidenceBucket(run) === "clean"),
    },
  ] satisfies Array<Omit<RunEvidenceGroup, "clusters">>;

  return groups
    .filter((group) => group.runs.length > 0)
    .map((group) => {
      const clusters = buildRunEvidenceClusters(group.runs);
      if (group.key === "review") {
        const cards = group.runs.reduce((sum, run) => sum + (run.review_card_count ?? 0), 0);
        const alerts = group.runs.reduce((sum, run) => sum + (run.alert_count ?? 0), 0);
        return {
          ...group,
          clusters,
          detail: `${cards} card${cards === 1 ? "" : "s"} / ${alerts} alert${alerts === 1 ? "" : "s"}`,
        };
      }
      return {
        ...group,
        clusters,
        detail: `${group.runs.length} run${group.runs.length === 1 ? "" : "s"} · ${group.detail}`,
      };
    });
}

export function buildRunEvidenceClusters(runs: Run[]): RunEvidenceCluster[] {
  const clusterMap = new Map<string, Run[]>();
  for (const run of runs) {
    const outcome = buildRunOutcome(run);
    const key = [evidenceBucketFromOutcome(run, outcome), run.profile_id, runDayKey(run), runOutcomeClusterKey(run, outcome)].join("|");
    clusterMap.set(key, [...(clusterMap.get(key) ?? []), run]);
  }
  return Array.from(clusterMap.entries()).map(([key, clusterRuns]) => buildRunCluster(key, clusterRuns));
}

export function buildRunOutcome(run: Run): RunOutcome {
  const status = run.status.toLowerCase();
  const cards = run.review_card_count ?? 0;
  const alerts = run.alert_count ?? 0;
  const diagnosticCount = run.quality?.diagnostic_count ?? 0;
  const diagnosticFailures = run.quality?.diagnostic_failure_count ?? 0;
  const diagnosticWarnings = run.quality?.diagnostic_warning_count ?? 0;
  const optionalOcr = isOptionalOcrDiagnostic(run);

  if (status === "failed") {
    return {
      tone: "danger",
      title: "Failed scan",
      detail: "Use the repair buttons above, then run a fresh practice scan.",
    };
  }
  if (diagnosticFailures > 0 || diagnosticWarnings > 0 || diagnosticCount > 0) {
    return {
      tone: optionalOcr ? "info" : diagnosticFailures > 0 ? "danger" : diagnosticWarnings > 0 ? "warn" : "info",
      title: formatRunDiagnostics(run.quality),
      detail: formatRunDiagnosticAction(run.quality) || "Open report diagnostics.",
    };
  }
  if (alerts > 0) {
    return {
      tone: "info",
      title: `${alerts} alert candidate${alerts === 1 ? "" : "s"}`,
      detail: `${cards} review card${cards === 1 ? "" : "s"} behind this run.`,
    };
  }
  if (cards > 0) {
    return {
      tone: "info",
      title: `${cards} review card${cards === 1 ? "" : "s"}`,
      detail: "Review queue has work; no alert candidate yet.",
    };
  }
  if (status === "running" || status === "pending") {
    return {
      tone: "warn",
      title: "Scan in progress",
      detail: "Wait for completion before judging source quality.",
    };
  }
  return {
    tone: "ok",
    title: "Clean scan",
    detail: "No cards, alerts, or diagnostics.",
  };
}

function buildSingleRunCluster(run: Run): RunEvidenceCluster {
  const outcome = buildRunOutcome(run);
  const key = [run.run_id, run.profile_id, runDayKey(run), outcome.tone, outcome.title].join("|");
  return buildRunCluster(key, [run]);
}

function buildRunCluster(key: string, runs: Run[]): RunEvidenceCluster {
  const sample = runs[0];
  const cards = runs.reduce((sum, run) => sum + (run.review_card_count ?? 0), 0);
  const alerts = runs.reduce((sum, run) => sum + (run.alert_count ?? 0), 0);
  const failed = runs.filter((run) => run.status.toLowerCase() === "failed").length;
  const outcome = buildClusterOutcome(buildRunOutcome(sample), { runs: runs.length, cards, alerts, failed }, sample);
  return {
    key,
    outcome,
    sample,
    runs,
    cards,
    alerts,
    failed,
  };
}

export function buildCompactRunTimeline(buckets: RunDayBucket[]): CompactTimelineItem[] {
  return buckets.map((bucket) => {
    const failed = bucket.failed;
    const runs = bucket.runs;
    const cards = bucket.cards;
    const alerts = bucket.alerts;
    const tone: RunTone = failed > 0 ? "warn" : cards > 0 || alerts > 0 ? "info" : runs > 0 ? "ok" : "quiet";
    return {
      key: bucket.key,
      tone,
      label: bucket.label,
      value: failed > 0 ? `${failed} fail` : runs > 0 ? `${runs} run${runs === 1 ? "" : "s"}` : "",
      detail: runs > 0 ? `${cards} cards · ${alerts} alerts` : "no scans",
    };
  });
}

export function buildRunHealthDecision(runs: Run[]): RunHealthDecision {
  const totalRuns = runs.length;
  const failedRuns = runs.filter((run) => run.status.toLowerCase() === "failed").length;
  const cards = runs.reduce((sum, run) => sum + (run.review_card_count ?? 0), 0);
  const alerts = runs.reduce((sum, run) => sum + (run.alert_count ?? 0), 0);
  const latest = latestRun(runs);
  const latestFailed = latest?.status.toLowerCase() === "failed";
  const latestDiagnosticFailures = latest && !isOptionalOcrDiagnostic(latest) ? (latest.quality?.diagnostic_failure_count ?? 0) : 0;
  const latestDiagnosticWarnings = latest && !isOptionalOcrDiagnostic(latest) ? (latest.quality?.diagnostic_warning_count ?? 0) : 0;
  const latestIssueCode = latest && (latest.quality?.diagnostic_count ?? 0) > 0 && !isOptionalOcrDiagnostic(latest)
    ? latest.quality?.top_diagnostic_code
    : undefined;

  if (latestFailed) {
    return {
      tone: "danger",
      headline: "Fix failed scans",
      detail: "Use Fix channels to restore saved channels, Check setup to verify login/API/profile, then Run fresh scan. No live alert is sent.",
    };
  }
  if (latestDiagnosticFailures > 0 || latestDiagnosticWarnings > 0) {
    return {
      tone: latestDiagnosticFailures > 0 ? "danger" : "warn",
      headline: "Diagnostics need attention",
      detail: latestIssueCode
        ? formatRunDiagnosticAction({ diagnostic_count: 1, top_diagnostic_code: latestIssueCode })
        : "Open the latest report diagnostics before tuning profiles.",
    };
  }
  if (alerts > 0) {
    return {
      tone: "info",
      headline: `Review ${alerts} alert candidate${alerts === 1 ? "" : "s"}`,
      detail: `${cards} review card${cards === 1 ? "" : "s"} appeared in recent runs. ${failedRuns > 0 ? "Latest scan recovered; older failures are history. " : ""}Open Review before enabling live alerts.`,
    };
  }
  if (cards > 0) {
    return {
      tone: "info",
      headline: `Review ${cards} card${cards === 1 ? "" : "s"}`,
      detail: `${failedRuns > 0 ? "Latest scan recovered; older failures are history. " : ""}There are signals to triage, but no alert candidate yet.`,
    };
  }
  if (failedRuns > 0) {
    return {
      tone: "ok",
      headline: "Latest scan recovered",
      detail: "Older failed scans remain in history, but the newest scan no longer needs repair.",
    };
  }
  return {
    tone: totalRuns ? "ok" : "info",
    headline: totalRuns ? "No urgent run issue" : "Run history is empty",
    detail: totalRuns ? "Recent scans completed without cards, alerts, or diagnostics." : "Run a local scan before judging source quality.",
  };
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
  return decision.detail;
}

function isOptionalOcrDiagnostic(run: Run) {
  return run.quality?.top_diagnostic_code === "ocr_disabled_media_present" && (run.quality?.diagnostic_failure_count ?? 0) === 0;
}

function latestRun(runs: Run[]) {
  return runs.reduce<Run | null>((latest, run) => {
    if (!latest) {
      return run;
    }
    return runTime(run) >= runTime(latest) ? run : latest;
  }, null);
}

function runTime(run: Run) {
  const time = new Date(run.started_at).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function evidenceBucket(run: Run): RunEvidenceGroup["key"] {
  const outcome = buildRunOutcome(run);
  return evidenceBucketFromOutcome(run, outcome);
}

function evidenceBucketFromOutcome(run: Run, outcome: RunOutcome): RunEvidenceGroup["key"] {
  if (outcome.tone === "danger" || outcome.tone === "warn") {
    return "attention";
  }
  if ((run.alert_count ?? 0) > 0 || (run.review_card_count ?? 0) > 0) {
    return "review";
  }
  return "clean";
}

function runOutcomeClusterKey(run: Run, outcome: RunOutcome) {
  if (run.status.toLowerCase() === "failed") {
    return "failed";
  }
  if ((run.quality?.diagnostic_count ?? 0) > 0) {
    return `diagnostic:${run.quality?.top_diagnostic_code || outcome.title}`;
  }
  if ((run.alert_count ?? 0) > 0) {
    return "alerts";
  }
  if ((run.review_card_count ?? 0) > 0) {
    return "cards";
  }
  if (run.status.toLowerCase() === "running" || run.status.toLowerCase() === "pending") {
    return run.status.toLowerCase();
  }
  return "clean";
}

function buildClusterOutcome(outcome: RunOutcome, totals: { runs: number; cards: number; alerts: number; failed: number }, sample: Run): RunOutcome {
  if (totals.runs <= 1) {
    return outcome;
  }
  if (totals.failed > 0) {
    return {
      ...outcome,
      title: `${totals.failed} failed scan${totals.failed === 1 ? "" : "s"}`,
    };
  }
  if ((sample.quality?.diagnostic_count ?? 0) > 0) {
    return outcome;
  }
  if (outcome.tone === "warn" || outcome.tone === "danger") {
    return outcome;
  }
  if (totals.alerts > 0) {
    return {
      ...outcome,
      title: `${totals.alerts} alert candidate${totals.alerts === 1 ? "" : "s"}`,
    };
  }
  if (totals.cards > 0) {
    return {
      ...outcome,
      title: `${totals.cards} review card${totals.cards === 1 ? "" : "s"}`,
    };
  }
  return outcome;
}

function runDayKey(run: Run) {
  const date = new Date(run.started_at);
  if (Number.isNaN(date.getTime())) {
    return String(run.started_at || "unknown");
  }
  return date.toISOString().slice(0, 10);
}

function RunsEmptyState({
  title,
  detail,
  onRunDeskAction,
}: {
  title: string;
  detail?: string;
  onRunDeskAction?: (actionId: string) => void;
}) {
  return (
    <EmptyStateShell
      icon={<Clock3 size={24} />}
      title={title}
      detail={detail}
      readout={[
        { label: "DB", value: "online" },
        { label: "Run", value: "needed" },
        { label: "Next", value: "local" },
      ]}
    >
      <div className="empty-actions" aria-label="Run history next actions">
        <button type="button" onClick={() => onRunDeskAction?.("monitor_jobs_dry_run")} disabled={!onRunDeskAction}>
          <Activity size={15} />
        <span>Run first scan</span>
      </button>
      <button type="button" onClick={() => onRunDeskAction?.("doctor_jobs")} disabled={!onRunDeskAction}>
        <Clock3 size={15} />
        <span>Check setup</span>
      </button>
      </div>
    </EmptyStateShell>
  );
}
