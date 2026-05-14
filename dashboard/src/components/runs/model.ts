import { formatRunDiagnosticAction, formatRunDiagnostics } from "../../domain/projections";
import type { Run, RunDayBucket } from "../../domain/types";

export const RECENT_RUN_LIMIT = 8;

export type RunHealthDecision = {
  tone: "ok" | "info" | "warn" | "danger";
  headline: string;
  detail: string;
  repairKind?: "source_access" | "profile_scope" | "setup";
};

export type RunTone = "ok" | "info" | "warn" | "danger" | "quiet";

export type RunOutcome = {
  tone: RunTone;
  title: string;
  detail: string;
};

export type RunEvidenceGroup = {
  key: "attention" | "review" | "clean";
  tone: RunTone;
  title: string;
  detail: string;
  repairKind?: RunHealthDecision["repairKind"];
  runs: Run[];
  clusters: RunEvidenceCluster[];
};

export type RunEvidenceCluster = {
  key: string;
  outcome: RunOutcome;
  sample: Run;
  runs: Run[];
  cards: number;
  alerts: number;
  failed: number;
};

export type CompactTimelineItem = {
  key: string;
  tone: RunTone;
  label: string;
  value: string;
  detail: string;
};

export function runCountScaleMax(clusters: Array<{ cards: number; alerts: number }>) {
  return Math.max(1, ...clusters.map((cluster) => Math.max(cluster.cards, cluster.alerts)));
}

export function buildRunEvidenceGroups(runs: Run[]): RunEvidenceGroup[] {
  const visibleRuns = runs.slice(0, RECENT_RUN_LIMIT);
  const latest = latestRun(runs);
  const latestFailed = latest?.status.toLowerCase() === "failed";
  const latestRepairKind = latestFailed ? runFailureRepairKind(latest?.quality?.top_diagnostic_code) : undefined;
  const groups = [
    ...(latestFailed
      ? [
          {
            key: "attention" as const,
            tone: "danger" as const,
            title: "Failed scans to fix",
            detail: "Use the repair buttons above first",
            repairKind: latestRepairKind,
            runs: visibleRuns.filter((run) => evidenceBucket(run) === "attention"),
          },
        ]
      : []),
    {
      key: "review",
      tone: "info",
      title: "Cards to review",
      detail: "Cards and alert candidates",
      runs: visibleRuns.filter((run) => evidenceBucket(run) === "review"),
    },
    {
      key: "clean",
      tone: "quiet",
      title: "Clean scans",
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
    const repairKind = runFailureRepairKind(run.quality?.top_diagnostic_code);
    return {
      tone: "danger",
      title: repairKind === "profile_scope" ? "AI matching needs attention" : "Failed scan",
      detail: failedRunRepairDetail(repairKind, run.quality?.top_diagnostic_code),
    };
  }
  if (diagnosticFailures > 0 || diagnosticWarnings > 0 || diagnosticCount > 0) {
    return {
      tone: optionalOcr ? "info" : diagnosticFailures > 0 ? "danger" : diagnosticWarnings > 0 ? "warn" : "info",
      title: formatRunDiagnostics(run.quality),
      detail: formatRunDiagnosticAction(run.quality) || "Open run details.",
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
    detail: "No cards or alerts.",
  };
}

export function buildSingleRunCluster(run: Run): RunEvidenceCluster {
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
  const latestIssueCode =
    latest && (latest.quality?.diagnostic_count ?? 0) > 0 && !isOptionalOcrDiagnostic(latest)
      ? latest.quality?.top_diagnostic_code
      : undefined;

  if (latestFailed) {
    const repairKind = runFailureRepairKind(latestIssueCode);
    return {
      tone: "danger",
      headline: repairKind === "profile_scope" ? "Fix AI matching" : "Fix failed scans",
      detail: failedRunRepairDetail(repairKind, latestIssueCode),
      repairKind,
    };
  }
  if (latestDiagnosticFailures > 0 || latestDiagnosticWarnings > 0) {
    return {
      tone: latestDiagnosticFailures > 0 ? "danger" : "warn",
      headline: "Scan needs attention",
      detail: latestIssueCode
        ? formatRunDiagnosticAction({ diagnostic_count: 1, top_diagnostic_code: latestIssueCode })
        : "Open the latest run details before tuning profiles.",
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
    detail: totalRuns ? "Recent scans completed without cards or alerts." : "Run a local scan before judging source quality.",
  };
}

function runFailureRepairKind(code?: string): NonNullable<RunHealthDecision["repairKind"]> {
  if (code === "llm_output_truncated" || code === "semantic_json_invalid" || code === "all_filtered_out") {
    return "profile_scope";
  }
  if (code === "channel_failures" || code === "no_messages_fetched" || code === "source_access_failed" || code === "scan_failed") {
    return "source_access";
  }
  return "setup";
}

function failedRunRepairDetail(kind: NonNullable<RunHealthDecision["repairKind"]>, code?: string) {
  if (kind === "profile_scope") {
    if (code === "all_filtered_out") {
      return "Open Profiles to loosen matching rules or prefilter keywords, then run a fresh AI review.";
    }
    return "Open Profiles to reduce scan size or raise the AI output limit, then scan again.";
  }
  if (kind === "source_access") {
    return "Use Fix channels to restore saved channels, Check setup to verify login/API/profile, then Run fresh scan. No live alert is sent.";
  }
  return "Check setup for the failed stage, then run a fresh AI review. No live alert is sent.";
}

export function historicalRunOutcome(outcome: RunOutcome, failed: number): RunOutcome {
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
