import { type CSSProperties } from "react";
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

export function RunsView({ runs }: { runs: Run[] }) {
  if (!runs.length) {
    return <RunsEmptyState title="No runs yet" detail="Run history is empty in this database." />;
  }
  const evidenceGroups = buildRunEvidenceGroups(runs);
  const visibleRunCount = evidenceGroups.reduce((sum, group) => sum + group.runs.length, 0);
  const archivedRuns = runs.slice(RECENT_RUN_LIMIT);
  return (
    <section className="table-section" aria-label="Run history">
      <PanelHeader icon={<Activity size={18} />} title="Runs" count={runs.length} />
      <RunHealthChart runs={runs} />
      <div className="run-list-head">
        <strong>Recent Evidence</strong>
        <span>
          {visibleRunCount} recent · {runs.length} total
        </span>
      </div>
      <div className="run-evidence-groups">
        {evidenceGroups.map((group) => (
          <section className={`run-evidence-group is-${group.tone}`} key={group.key} aria-label={group.title}>
            <div className="run-evidence-head">
              <strong>{group.title}</strong>
              <span>{group.detail}</span>
            </div>
            <div className="table-list">
              {group.clusters.map((cluster) => (
                <RunClusterRow key={cluster.key} cluster={cluster} />
              ))}
            </div>
          </section>
        ))}
      </div>
      {archivedRuns.length > 0 && (
        <details className="run-archive">
          <summary>Older runs ({archivedRuns.length})</summary>
          <div className="table-list">
            {archivedRuns.map((run) => (
              <RunClusterRow key={run.run_id} cluster={buildSingleRunCluster(run)} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function RunClusterRow({ cluster }: { cluster: RunEvidenceCluster }) {
  const run = cluster.sample;
  const artifact = run.report_artifact ?? null;
  const outcome = cluster.outcome;
  const runCountLabel = cluster.runs.length === 1 ? runDisplayDetail(run) : `${cluster.runs.length} runs · latest ${runDisplayDetail(run)}`;
  const statusLabel = cluster.runs.length === 1 ? run.status : cluster.failed > 0 ? `${cluster.failed} failed` : `${cluster.runs.length} runs`;
  const outcomeDetail =
    cluster.runs.length === 1
      ? outcome.detail
      : `${outcome.detail} ${cluster.cards} cards / ${cluster.alerts} alerts total.`;
  return (
    <div className="table-row run-row" data-run-tone={outcome.tone}>
      <div className="run-primary">
        <strong>{outcome.title}</strong>
        <small>{[runDisplayTitle(run), runCountLabel].filter(Boolean).join(" · ")}</small>
        <span>{outcomeDetail}</span>
      </div>
      <span className={`status ${toneClass(statusLabel)}`}>{statusLabel}</span>
      <RunCountBars cards={cluster.cards} alerts={cluster.alerts} />
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

function RunCountBars({ cards, alerts }: { cards: number; alerts: number }) {
  const maxValue = Math.max(1, cards, alerts);
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

function RunHealthChart({ runs }: { runs: Run[] }) {
  const recentRuns = runs.slice(0, 80);
  const buckets = runDayWindowBuckets(recentRuns, 7);
  const compactTimeline = buildCompactRunTimeline(buckets);
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
      <div className="run-health-summary">
        <small>Run Health</small>
        <strong>{formatPercent(successRate)}</strong>
        <span>complete</span>
        <small>
          {completeRuns} ok / {failedRuns} failed
        </small>
        {runningRuns > 0 && <small>{runningRuns} in progress</small>}
        <small>
          {cards} cards / {alerts} alerts
        </small>
        <div className={`run-health-decision is-${decision.tone}`}>
          <b>{decision.headline}</b>
          <span>{decision.detail}</span>
        </div>
      </div>
      <div className="run-compact-timeline" aria-label="Compact run timeline">
        {compactTimeline.map((item) => (
          <div className={`run-compact-tile is-${item.tone}`} key={item.key}>
            <small>{item.label}</small>
            <strong>{item.value}</strong>
            <span>{item.detail}</span>
          </div>
        ))}
      </div>
      <div className="run-day-bars">
        {buckets.map((bucket) => (
          <div
            className={`run-day-bucket ${bucket.failed ? "has-failure" : ""}`}
            key={bucket.key}
            title={`${bucket.label} · ${bucket.complete} complete · ${bucket.failed} failed · ${bucket.cards} cards · ${bucket.alerts} alerts`}
          >
            <div className="run-day-bar" aria-hidden="true">
              {bucket.failed > 0 && <span className="failed" style={{ height: percentWidth(bucket.failed / bucket.runs) }} />}
              {bucket.complete > 0 && <span className="complete" style={{ height: percentWidth(bucket.complete / bucket.runs) }} />}
              {!bucket.runs && <em />}
              <i style={{ width: percentWidth(runBucketSignalScore(bucket)) }} />
            </div>
            <small>{bucket.label}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

export function buildRunEvidenceGroups(runs: Run[]): RunEvidenceGroup[] {
  const visibleRuns = runs.slice(0, RECENT_RUN_LIMIT);
  const groups = [
    {
      key: "attention",
      tone: "danger",
      title: "Needs attention",
      detail: "Fix before trusting automation",
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

  if (status === "failed") {
    return {
      tone: "danger",
      title: "Failed scan",
      detail: "Open the report before trusting later counts.",
    };
  }
  if (diagnosticFailures > 0 || diagnosticWarnings > 0 || diagnosticCount > 0) {
    return {
      tone: diagnosticFailures > 0 ? "danger" : diagnosticWarnings > 0 ? "warn" : "info",
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
  const outcome = buildClusterOutcome(buildRunOutcome(sample), { runs: runs.length, cards, alerts, failed });
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
    const tone: RunTone = failed > 0 ? "danger" : cards > 0 || alerts > 0 ? "info" : runs > 0 ? "ok" : "quiet";
    return {
      key: bucket.key,
      tone,
      label: bucket.label,
      value: failed > 0 ? `${failed} fail` : runs > 0 ? `${runs} run${runs === 1 ? "" : "s"}` : "none",
      detail: runs > 0 ? `${cards} cards · ${alerts} alerts` : "no scans",
    };
  });
}

export function buildRunHealthDecision(runs: Run[]): RunHealthDecision {
  const totalRuns = runs.length;
  const failedRuns = runs.filter((run) => run.status.toLowerCase() === "failed").length;
  const cards = runs.reduce((sum, run) => sum + (run.review_card_count ?? 0), 0);
  const alerts = runs.reduce((sum, run) => sum + (run.alert_count ?? 0), 0);
  const diagnosticFailures = runs.reduce((sum, run) => sum + (run.quality?.diagnostic_failure_count ?? 0), 0);
  const diagnosticWarnings = runs.reduce((sum, run) => sum + (run.quality?.diagnostic_warning_count ?? 0), 0);
  const latestIssueCode = runs.find((run) => (run.quality?.diagnostic_count ?? 0) > 0)?.quality?.top_diagnostic_code;

  if (failedRuns > 0) {
    return {
      tone: "danger",
      headline: "Fix failed scans",
      detail: "Use the failed evidence row before trusting automation.",
    };
  }
  if (diagnosticFailures > 0 || diagnosticWarnings > 0) {
    return {
      tone: diagnosticFailures > 0 ? "danger" : "warn",
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
      detail: `${cards} review card${cards === 1 ? "" : "s"} appeared in recent runs. Clear Review before enabling live alerts.`,
    };
  }
  if (cards > 0) {
    return {
      tone: "info",
      headline: `Review ${cards} card${cards === 1 ? "" : "s"}`,
      detail: "There are signals to triage, but no alert candidate yet.",
    };
  }
  return {
    tone: totalRuns ? "ok" : "info",
    headline: totalRuns ? "No urgent run issue" : "Run history is empty",
    detail: totalRuns ? "Recent scans completed without cards, alerts, or diagnostics." : "Run a local scan before judging source quality.",
  };
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

function buildClusterOutcome(outcome: RunOutcome, totals: { runs: number; cards: number; alerts: number; failed: number }): RunOutcome {
  if (totals.runs <= 1) {
    return outcome;
  }
  if (totals.failed > 0) {
    return {
      ...outcome,
      title: `${totals.failed} failed scan${totals.failed === 1 ? "" : "s"}`,
    };
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
}: {
  title: string;
  detail?: string;
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
    />
  );
}
