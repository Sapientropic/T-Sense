import type { Run, RunArtifact } from "../types";
import { assignOptionalNumbers, isRecord, sanitizeObjectArray } from "./shared";
import { assignOptionalNumbersOrNull, assignOptionalStrings, requiredString } from "./dashboard-common";

export function sanitizeRuns(value: unknown): Run[] {
  return sanitizeObjectArray(value, "runs").flatMap((record, index) => {
    const runId = requiredString(index, "run_id", record.run_id, "runs");
    const profileId = requiredString(index, "profile_id", record.profile_id, "runs");
    const status = requiredString(index, "status", record.status, "runs");
    const startedAt = requiredString(index, "started_at", record.started_at, "runs");
    if (!runId || !profileId || !status || !startedAt) {
      return [];
    }
    const run: Run = { run_id: runId, profile_id: profileId, status, started_at: startedAt };
    assignOptionalStrings(run, record, ["display_name", "completed_at"]);
    assignOptionalNumbers(run, record, ["alert_count", "review_card_count"]);
    const artifact = sanitizeRunArtifact(record.report_artifact);
    if (artifact || record.report_artifact === null) {
      run.report_artifact = artifact;
    }
    const quality = sanitizeRunQuality(record.quality);
    if (quality) {
      run.quality = quality;
    }
    return [run];
  });
}


function sanitizeRunArtifact(value: unknown): RunArtifact | null | undefined {
  if (value === null) {
    return null;
  }
  if (!isRecord(value) || typeof value.path !== "string" || !isSafeRunReportArtifactPath(value.path)) {
    return undefined;
  }
  const artifact: RunArtifact = { path: value.path };
  assignOptionalStrings(artifact, value, ["type", "sha256", "category", "format", "display_name", "display_path"]);
  return artifact;
}

function isSafeRunReportArtifactPath(value: string): boolean {
  const cleaned = value.trim().replace(/\\/g, "/");
  if (!cleaned || cleaned.startsWith("/") || /^[A-Za-z]:/.test(cleaned)) {
    return false;
  }
  const parts = cleaned.split("/").filter(Boolean);
  if (!parts.length || parts.includes("..")) {
    return false;
  }
  const runIndex = parts.indexOf("runs");
  if (runIndex < 0 || runIndex >= parts.length - 2) {
    return false;
  }
  return isDashboardReportArtifactName(parts[parts.length - 1] ?? "");
}

function isDashboardReportArtifactName(value: string): boolean {
  const lower = value.trim().toLowerCase();
  if (lower === "report.html" || lower === "report.md") {
    return true;
  }
  const dotIndex = lower.lastIndexOf(".");
  if (dotIndex < 0) {
    return false;
  }
  const stem = lower.slice(0, dotIndex);
  const suffix = lower.slice(dotIndex);
  return (suffix === ".html" || suffix === ".md") && stem.split("-").some((token) => token === "report" || token === "brief");
}

function sanitizeRunQuality(value: unknown): Run["quality"] | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const quality: NonNullable<Run["quality"]> = {};
  assignOptionalStrings(quality, value, ["prefilter", "semantic_stage", "llm_provider", "top_diagnostic_code"]);
  assignOptionalNumbersOrNull(quality, value, ["cache_hit_rate", "latency_ms", "completion_tokens"]);
  assignOptionalNumbers(quality, value, [
    "diagnostic_count",
    "diagnostic_failure_count",
    "diagnostic_warning_count",
    "diagnostic_info_count",
  ]);
  return Object.keys(quality).length ? quality : undefined;
}
