import { compactReportName, diagnosticLabel, formatDate, profileDisplayName, titleCaseLabel } from "./format";
import type { DeliveryTarget, FeedbackImpact, GitUpdateStatus, OpportunitySummary, Profile, Run, RunArtifact, SourceStat } from "./types";

export function toneClass(value: string | null | undefined) {
  const normalized = String(value || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
  return normalized || "unknown";
}

function splitDateTime(value?: string) {
  const timestamp = formatDate(value);
  const [date, time] = timestamp.split(" ");
  return time ? { date, time, full: timestamp } : { date: "", time: timestamp, full: timestamp };
}

export function runDisplayTitle(run: Run) {
  const { date } = splitDateTime(run.started_at);
  const title = run.display_name || profileDisplayName(run.profile_id);
  return date ? `${title} · ${date}` : title;
}

export function runDisplayDetail(run: Run) {
  return splitDateTime(run.started_at).time;
}

export function buildProfileReportNames(profiles: Profile[]) {
  return Object.fromEntries(
    profiles.map((profile) => [
      profile.profile_id,
      profile.report_display_name || `${profile.display_name || profileDisplayName(profile.profile_id)} Report`,
    ]),
  );
}

export function reportProfileName(profileId: string, profileReportNames: Record<string, string>) {
  return compactReportName(profileReportNames[profileId] || profileDisplayName(profileId));
}

export function deliveryTargetName(target: DeliveryTarget) {
  if (target.type.toLowerCase() === "telegram_bot") {
    return "Telegram Bot";
  }
  return titleCaseLabel(target.type || target.target_id);
}

export function deliveryTargetDetail(target: DeliveryTarget) {
  if (target.type.toLowerCase() === "telegram_bot") {
    return target.config.chat_id ? "Chat connected" : "Live target not connected";
  }
  return target.enabled ? "Delivery target active" : "Delivery target muted";
}

export function artifactHref(path: string) {
  return `/artifacts/${encodeURIComponent(path)}`;
}

export function artifactFormatFromPath(path: string, explicit?: string) {
  if (explicit) {
    return explicit;
  }
  const lower = path.toLowerCase();
  if (lower.endsWith(".html")) {
    return "HTML";
  }
  if (lower.endsWith(".md")) {
    return "Markdown";
  }
  return "Artifact";
}

export function artifactDisplayName(artifact: RunArtifact, run: Run) {
  return artifact.display_name || `${profileDisplayName(run.profile_id)} Signal Report`;
}

export function artifactShortLabel(artifact: RunArtifact) {
  const lower = artifact.path.toLowerCase();
  if (lower.endsWith(".html") || lower.endsWith(".md")) {
    return "Report";
  }
  return artifact.category ? titleCaseLabel(artifact.category) : "Artifact";
}

export function artifactShortDetail(artifact: RunArtifact, run: Run) {
  return `${artifactFormatFromPath(artifact.path, artifact.format)} · ${formatDate(run.completed_at || run.started_at)}`;
}

export function formatGitRemoteState(status: GitUpdateStatus | null) {
  if (!status) {
    return "unchecked";
  }
  if (status.dirty) {
    return `dirty ${status.dirty_count}`;
  }
  return status.status.replace(/_/g, " ");
}

export function opportunityTone(summary: OpportunitySummary) {
  if ((summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed") {
    return "blocked";
  }
  if ((summary.high_actionable_count ?? 0) > 0) {
    return "hot";
  }
  if (summary.all_clear) {
    return "clear";
  }
  return "quiet";
}

export function opportunityHeadline(summary: OpportunitySummary) {
  if ((summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed") {
    return "Source check needed";
  }
  const count = summary.high_actionable_count ?? 0;
  if (count > 0) {
    return `${count} action signal${count === 1 ? "" : "s"}`;
  }
  if (summary.all_clear) {
    return "All Clear";
  }
  return "Latest run ready";
}

export function opportunityDetail(summary: OpportunitySummary) {
  if ((summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed") {
    return summary.diagnostics?.top_code ? diagnosticLabel(summary.diagnostics.top_code) : "Open Runs";
  }
  const matched = summary.matched_count ?? 0;
  const scanned = summary.scanned_count ?? 0;
  return `${matched}/${scanned} matched`;
}

export function alertMode(profile: Profile) {
  const value = profile.alert_schedule_mode;
  return typeof value === "string" ? value : "work_hours";
}

export function diffStats(diffText: string) {
  return diffText.split(/\r?\n/).reduce(
    (stats, line) => {
      if (line.startsWith("+") && !line.startsWith("+++")) {
        stats.added += 1;
      } else if (line.startsWith("-") && !line.startsWith("---")) {
        stats.removed += 1;
      }
      return stats;
    },
    { added: 0, removed: 0 },
  );
}

export function diagnosticTone(quality?: Run["quality"]) {
  if ((quality?.diagnostic_failure_count ?? 0) > 0) {
    return "diagnostic-pill danger";
  }
  if ((quality?.diagnostic_warning_count ?? 0) > 0) {
    return "diagnostic-pill warn";
  }
  if ((quality?.diagnostic_count ?? 0) > 0) {
    return "diagnostic-pill info";
  }
  return "diagnostic-pill ok";
}

export function percentWidth(value?: number) {
  const safeValue = Number.isFinite(value) ? Math.max(0, Math.min(1, value ?? 0)) : 0;
  return `${Math.round(safeValue * 100)}%`;
}

export function ratio(numerator?: number, denominator?: number) {
  if (!denominator) {
    return 0;
  }
  return Math.max(0, Math.min(1, (numerator ?? 0) / denominator));
}

function finiteSourceValue(value?: number) {
  return Number.isFinite(value) ? Math.max(0, value ?? 0) : 0;
}

// Heat map intensity uses the strongest current signal, not an average, so one hot source
// is still visible when the same channel has low overall card yield or little latest volume.
export function sourceSignalScore(source: SourceStat) {
  const highWeight = Math.min(1, finiteSourceValue(source.high_count) / 5);
  const latestWeight = Math.min(1, finiteSourceValue(source.latest_card_count) / 4);
  const yieldWeight = Math.min(1, finiteSourceValue(source.card_yield_rate));
  return Math.max(highWeight, latestWeight * 0.75, yieldWeight);
}

export function sourceHeatClass(source: SourceStat) {
  if (source.scan_failure) {
    return "risk";
  }
  if (source.scan_incomplete) {
    return "warn";
  }
  if ((source.high_count ?? 0) > 0) {
    return "hot";
  }
  if ((source.card_count ?? 0) > 0 || (source.latest_card_count ?? 0) > 0) {
    return "warm";
  }
  return "quiet";
}

export function metricShortLabel(label: string) {
  if (label.toLowerCase().includes("yield")) {
    return "yield";
  }
  if (label.toLowerCase().includes("high")) {
    return "high";
  }
  return "kept";
}

export function formatActionLabel(action: string) {
  return action.replace(/_/g, " ");
}

export function feedbackImpactKey(impact: FeedbackImpact, index: number) {
  return [
    impact.created_at,
    impact.patch_id,
    impact.profile_id,
    impact.action,
    impact.item_title,
    index,
  ]
    .filter((part) => part !== undefined && part !== "")
    .join("-");
}
