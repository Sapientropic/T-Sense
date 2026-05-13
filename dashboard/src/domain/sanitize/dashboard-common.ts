import type { DashboardNextAction, SourceInsight, SourceRef, SourceStat } from "../types";
import { assignOptionalNumbers, isRecord, numberOrDefault, optionalString, sanitizeLocalRelativePath } from "./shared";

export function sanitizeDashboardRelativePath(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  return sanitizeLocalRelativePath(value) ?? undefined;
}

export function sanitizeSourceStat(record: Record<string, unknown>, index: number, scope: string): SourceStat | null {
  const channel = requiredString(index, "channel", record.channel, scope);
  if (!channel) {
    return null;
  }
  const stat: SourceStat = {
    channel,
    card_count: numberOrDefault(record.card_count, 0),
    high_count: numberOrDefault(record.high_count, 0),
    medium_count: numberOrDefault(record.medium_count, 0),
    low_count: numberOrDefault(record.low_count, 0),
    pending_count: numberOrDefault(record.pending_count, 0),
    handled_count: numberOrDefault(record.handled_count, 0),
    false_positive_count: numberOrDefault(record.false_positive_count, 0),
    alert_count: numberOrDefault(record.alert_count, 0),
    high_rate: numberOrDefault(record.high_rate, 0),
  };
  assignOptionalStrings(stat, record, ["display_name", "latest_run_id", "scan_failure_reason"]);
  assignOptionalNumbers(stat, record, [
    "latest_card_count",
    "latest_high_count",
    "raw_count",
    "kept_count",
    "scan_keep_rate",
    "card_yield_rate",
  ]);
  assignOptionalBooleans(stat, record, ["scan_failure", "scan_incomplete"]);
  return stat;
}

export function emptySourceStat(channel: string): SourceStat {
  return {
    channel,
    card_count: 0,
    high_count: 0,
    medium_count: 0,
    low_count: 0,
    pending_count: 0,
    handled_count: 0,
    false_positive_count: 0,
    alert_count: 0,
    high_rate: 0,
  };
}

export function requiredString(index: number, field: string, value: unknown, scope = "inbox") {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  console.warn(`[tgcs dashboard schema] ${scope}[${index}].${field} expected non-empty string`, value);
  return "";
}

export function stringOrDefault(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback;
}

export function optionalHttpUrl(value: unknown) {
  const text = optionalString(value);
  if (!text) {
    return undefined;
  }
  try {
    const parsed = new URL(text);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}

export function assignOptionalStrings<T extends object>(target: T, record: Record<string, unknown>, fields: string[]) {
  const writable = target as Record<string, unknown>;
  fields.forEach((field) => {
    const value = optionalString(record[field]);
    if (value) {
      writable[field] = value;
    }
  });
}

export function assignOptionalNumbersOrNull<T extends object>(target: T, record: Record<string, unknown>, fields: string[]) {
  const writable = target as Record<string, unknown>;
  fields.forEach((field) => {
    const value = record[field];
    if (value === null || (typeof value === "number" && Number.isFinite(value))) {
      writable[field] = value;
    }
  });
}

export function assignOptionalBooleans<T extends object>(target: T, record: Record<string, unknown>, fields: string[]) {
  const writable = target as Record<string, unknown>;
  fields.forEach((field) => {
    const value = record[field];
    if (typeof value === "boolean") {
      writable[field] = value;
    }
  });
}

export function sanitizeSourceRefs(value: unknown): SourceRef[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((ref) => {
    if (!isRecord(ref) || typeof ref.channel !== "string" || (typeof ref.id !== "string" && typeof ref.id !== "number")) {
      return [];
    }
    const cleanRef: SourceRef = { channel: ref.channel, id: ref.id };
    const url = optionalHttpUrl(ref.url);
    if (url) {
      cleanRef.url = url;
    }
    return [cleanRef];
  });
}

export function sanitizeDashboardNextAction(value: unknown): DashboardNextAction | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const action: DashboardNextAction = {};
  assignOptionalStrings(action, value, ["label", "detail", "command", "target", "target_tab", "action_id", "artifact_path"]);
  return Object.keys(action).length ? action : undefined;
}

export function sanitizeSourceInsightNextAction(value: unknown): SourceInsight["next_action"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const action: NonNullable<SourceInsight["next_action"]> = {};
  assignOptionalStrings(action, value, ["label", "detail", "command"]);
  return Object.keys(action).length ? action : undefined;
}
