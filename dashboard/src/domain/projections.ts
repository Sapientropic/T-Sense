import { channelDisplayName, diagnosticLabel, formatDate, formatPercent } from "./format";
import type { DashboardState, Metric, OpportunitySummary, Run, RunDayBucket, SourceStat, Tab } from "./types";

export function buildMetrics(state: DashboardState): Metric[] {
  const activeProfiles = state.profiles.filter((profile) => profile.enabled).length;
  const totalAlerts = state.runs.reduce((sum, run) => sum + (run.alert_count ?? 0), 0);
  const pendingPatches = state.profile_patch_suggestions.filter((patch) => patch.status === "pending").length;
  const activeTargets = state.delivery_targets.filter((target) => target.enabled).length;
  const topSource = state.source_stats[0];
  const topSourceMeter = topSource?.card_count ? Math.min(1, (topSource.high_count || 0) / topSource.card_count) : 0;

  return [
    { label: "Runs", value: String(state.runs.length), detail: latestRunDetail(state.runs), tone: "teal", meter: Math.min(1, state.runs.length / 7) },
    {
      label: "Alerts",
      value: String(totalAlerts),
      detail: `${activeTargets} live target${activeTargets === 1 ? "" : "s"}`,
      tone: "rust",
      meter: totalAlerts ? Math.min(1, totalAlerts / Math.max(1, state.runs.length)) : 0,
    },
    {
      label: "Profiles",
      value: String(activeProfiles),
      detail: `${pendingPatches} diff${pendingPatches === 1 ? "" : "s"}`,
      tone: "blue",
      meter: state.profiles.length ? activeProfiles / state.profiles.length : 0,
    },
    { label: "Sources", value: String(state.source_stats.length), detail: topSourceDetail(state.source_stats), tone: "amber", meter: topSourceMeter },
  ];
}

export function buildTabCounts(state: DashboardState, actionCount = 0): Record<Tab, number> {
  const feedbackCount = (state.feedback_summary?.exportable_count ?? 0) + (state.feedback_summary?.pending_profile_diff_count ?? 0);
  const deliveryBlockers = state.delivery_targets.filter((target) => !target.enabled).length;
  return {
    inbox: state.inbox.length,
    actions: actionCount,
    profiles: state.profiles.length,
    runs: state.runs.length,
    settings: deliveryBlockers + state.source_insights.length + feedbackCount,
  };
}

export function buildBoardMeta(activeTab: Tab, state: DashboardState, actionCount = 0) {
  const metas: Record<Tab, { title: string; detail: string; value: string; tone: "amber" | "teal" | "rust" | "blue" }> = {
    inbox: {
      title: "Review",
      detail: state.inbox.length ? "Pending cards sorted by latest signal." : "Queue clear.",
      value: `${state.inbox.length}`,
      tone: "amber",
    },
    actions: {
      title: "Start",
      detail: "Guided setup and run controls for people who do not want a CLI.",
      value: `${actionCount}`,
      tone: "teal",
    },
    profiles: {
      title: "Profiles",
      detail: `${state.profiles.filter((profile) => profile.enabled).length} enabled profiles, ${
        state.profile_patch_suggestions.filter((patch) => patch.status === "pending").length
      } pending diffs.`,
      value: `${state.profiles.length}`,
      tone: "blue",
    },
    runs: {
      title: "Runs",
      detail: state.runs.length ? `Day-level health. Latest run ${formatDate(state.runs[0].started_at)}.` : "Run history is empty.",
      value: `${state.runs.length}`,
      tone: "teal",
    },
    settings: {
      title: "Settings",
      value: `${settingsActionCount(state)}`,
      detail: `Saved sources, notification delivery, and learning controls. ${
        state.source_insights.length
      } source decisions pending.`,
      tone: "blue",
    },
  };
  return metas[activeTab];
}

export function settingsActionCount(state: DashboardState) {
  const deliveryBlockers = state.delivery_targets.filter((target) => !target.enabled).length;
  return deliveryBlockers + state.source_insights.length + (state.feedback_summary?.exportable_count ?? 0) + (state.feedback_summary?.pending_profile_diff_count ?? 0);
}

export function hasBlockingOpportunitySummary(summary?: OpportunitySummary) {
  return Boolean(summary && ((summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed"));
}

export function runDayBuckets(runs: Run[]) {
  const buckets = new Map<string, RunDayBucket>();
  for (const run of runs) {
    const date = new Date(run.started_at);
    const key = Number.isNaN(date.getTime()) ? String(run.started_at || "unknown") : date.toISOString().slice(0, 10);
    const label = Number.isNaN(date.getTime()) ? "unknown" : formatDayBucketLabel(key);
    const bucket = buckets.get(key) ?? { key, label, runs: 0, complete: 0, failed: 0, cards: 0, alerts: 0 };
    bucket.runs += 1;
    if (run.status.toLowerCase() === "complete") {
      bucket.complete += 1;
    } else if (run.status.toLowerCase() === "failed") {
      bucket.failed += 1;
    }
    bucket.cards += run.review_card_count ?? 0;
    bucket.alerts += run.alert_count ?? 0;
    buckets.set(key, bucket);
  }
  return Array.from(buckets.values()).sort((a, b) => a.key.localeCompare(b.key));
}

export function runDayWindowBuckets(runs: Run[], dayCount: number) {
  const bucketMap = new Map(runDayBuckets(runs).map((bucket) => [bucket.key, bucket]));
  const datedKeys = Array.from(bucketMap.keys()).filter((key) => /^\d{4}-\d{2}-\d{2}$/.test(key)).sort();
  const endKey = datedKeys.at(-1) ?? new Date().toISOString().slice(0, 10);
  const endDate = new Date(`${endKey}T00:00:00.000Z`);
  if (Number.isNaN(endDate.getTime())) {
    return Array.from(bucketMap.values()).slice(-dayCount);
  }
  return Array.from({ length: dayCount }, (_, index) => {
    const date = new Date(endDate);
    date.setUTCDate(endDate.getUTCDate() - (dayCount - index - 1));
    const key = date.toISOString().slice(0, 10);
    return bucketMap.get(key) ?? { key, label: formatDayBucketLabel(key), runs: 0, complete: 0, failed: 0, cards: 0, alerts: 0 };
  });
}

export function runBucketSignalScore(bucket: RunDayBucket) {
  if (!bucket.runs) {
    return 0;
  }
  return Math.max(0.12, Math.min(1, bucket.cards / 16), Math.min(1, bucket.alerts / 6));
}

export function formatRunQuality(quality?: Run["quality"]) {
  if (!quality) {
    return "Quality not recorded";
  }
  if (!quality.llm_provider) {
    return quality.semantic_stage ? diagnosticLabel(quality.semantic_stage) : "Semantic stage not recorded";
  }
  const provider = quality.llm_provider || (quality.semantic_stage ? diagnosticLabel(quality.semantic_stage) : "Semantic stage not recorded");
  const cache =
    typeof quality.cache_hit_rate === "number" ? `${Math.round(quality.cache_hit_rate * 100)}% cache` : "";
  const latency = typeof quality.latency_ms === "number" ? `${quality.latency_ms}ms` : "";
  return [provider, cache, latency].filter(Boolean).join(" / ");
}

export function formatRunDiagnosticAction(quality?: Run["quality"]) {
  const code = quality?.top_diagnostic_code || "";
  if (!code || (quality?.diagnostic_count ?? 0) === 0) {
    return "";
  }
  if (code === "scan_failed" || code === "channel_failures" || code === "source_access_failed") {
    return "Next: fix source access";
  }
  if (code === "scan_incomplete") {
    return "Next: inspect incomplete sources";
  }
  if (code === "no_messages_fetched") {
    return "Next: widen scan window or check sources";
  }
  if (code === "llm_unavailable") {
    return "Next: check LLM key";
  }
  if (code === "llm_output_truncated" || code === "semantic_json_invalid") {
    return "Next: raise semantic limits or narrow scope";
  }
  if (code === "all_filtered_out") {
    return "Next: loosen profile or prefilter";
  }
  if (code === "ocr_disabled_media_present") {
    return "Optional: enable OCR if media matters";
  }
  if (code === "missing_scan_metadata") {
    return "Next: keep scan metadata sidecar";
  }
  return "Next: open report diagnostics";
}

export function formatRunDiagnostics(quality?: Run["quality"]) {
  const count = quality?.diagnostic_count ?? 0;
  if (!count) {
    return "Clean";
  }
  const code = diagnosticLabel(quality?.top_diagnostic_code || "diagnostic");
  return code;
}

export function runHealthDetail(quality?: Run["quality"]) {
  return [formatRunQuality(quality), formatRunDiagnosticAction(quality)].filter(Boolean).join(" · ");
}

function latestRunDetail(runs: Run[]) {
  if (!runs.length) {
    return "no history";
  }
  return formatDate(runs[0].started_at);
}

function topSourceDetail(sources: SourceStat[]) {
  if (!sources.length) {
    return "no source stats";
  }
  const top = sources[0];
  const sourceName = top.display_name || channelDisplayName(top.channel);
  if (top.scan_failure) {
    return `${sourceName} · access failed`;
  }
  if (top.scan_incomplete) {
    return `${sourceName} · incomplete`;
  }
  const totalValue = `${top.high_count} high · ${top.card_count} cards`;
  const hasLatestScan =
    Boolean(top.latest_run_id) ||
    (top.raw_count ?? 0) > 0 ||
    (top.kept_count ?? 0) > 0 ||
    (top.latest_card_count ?? 0) > 0 ||
    Boolean(top.scan_failure) ||
    Boolean(top.scan_incomplete);
  if (hasLatestScan) {
    return `${sourceName} · ${totalValue} · ${top.kept_count ?? 0}/${top.raw_count ?? 0} kept`;
  }
  if (top.card_count > 0) {
    return `${sourceName} · ${totalValue}`;
  }
  return `${sourceName} · ${formatPercent(top.high_rate)} high`;
}

function formatDayBucketLabel(key: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(key)) {
    return key || "unknown";
  }
  return key.slice(5);
}
