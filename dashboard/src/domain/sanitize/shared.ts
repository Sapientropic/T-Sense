import type { DeskActionResult } from "../types";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function optionalString(value: unknown) {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

export function optionalStringOrNull(value: unknown) {
  if (value === null) {
    return null;
  }
  return optionalString(value);
}

export function numberOrDefault(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function nonNegativeIntegerOrDefault(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : fallback;
}

export function nonNegativeInteger(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

export function assignOptionalNumbers<T extends object>(target: T, record: Record<string, unknown>, fields: string[]) {
  const writable = target as Record<string, unknown>;
  fields.forEach((field) => {
    const value = record[field];
    if (typeof value === "number" && Number.isFinite(value)) {
      writable[field] = value;
    }
  });
}

export function sanitizeNumberRecord(value: unknown): Record<string, number> | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const clean = Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1])),
  );
  return Object.keys(clean).length ? clean : undefined;
}

export function stringArray(value: unknown) {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        if (typeof item !== "string") {
          return [];
        }
        const trimmed = item.trim();
        return trimmed ? [trimmed] : [];
      })
    : [];
}

export function sanitizeObjectArray(value: unknown, scope: string): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    if (value !== undefined && value !== null) {
      console.warn(`[tgcs dashboard schema] ${scope} expected array`, value);
    }
    return [];
  }
  return value.flatMap((item, index) => {
    if (!isRecord(item)) {
      console.warn(`[tgcs dashboard schema] ${scope}[${index}] expected object`, item);
      return [];
    }
    return [item];
  });
}

export function sanitizeLocalRelativePath(value: string): string | null {
  const cleaned = value.trim().replace(/\\/g, "/");
  if (
    !cleaned ||
    cleaned.startsWith("/") ||
    /^[A-Za-z]:/.test(cleaned) ||
    /^[a-z][a-z0-9+.-]*:\/\//i.test(cleaned) ||
    /[\u0000-\u001F\u007F]/.test(cleaned)
  ) {
    return null;
  }
  const parts = cleaned.split("/").filter(Boolean);
  if (!parts.length || parts.includes("..")) {
    return null;
  }
  return cleaned;
}

export function sanitizeStringRecord(
  value: unknown,
  blockedKeys: ReadonlySet<string> = new Set(),
  blockedSuffixes: readonly string[] = [],
): Record<string, string> | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const clean = Object.fromEntries(
    Object.entries(value).flatMap(([key, rawValue]) => {
      const normalizedKey = key.trim().toLowerCase();
      if (blockedKeys.has(normalizedKey) || blockedSuffixes.some((suffix) => normalizedKey.endsWith(suffix))) {
        return [];
      }
      const item = optionalString(rawValue);
      return item ? [[key, item]] : [];
    }),
  );
  return Object.keys(clean).length ? clean : undefined;
}

export function sanitizeSourceAccessSummary(value: unknown): DeskActionResult["source_access"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const summary: NonNullable<DeskActionResult["source_access"]> = {
    schema_version: value.schema_version === "desk_source_access_health_v1" ? value.schema_version : undefined,
    checked_at: optionalString(value.checked_at) ?? "",
    source_count: nonNegativeIntegerOrDefault(value.source_count, 0),
    checked_count: nonNegativeIntegerOrDefault(value.checked_count, 0),
    accessible_count: nonNegativeIntegerOrDefault(value.accessible_count, 0),
    quiet_count: nonNegativeIntegerOrDefault(value.quiet_count, 0),
    inaccessible_count: nonNegativeIntegerOrDefault(value.inaccessible_count, 0),
    truncated_count: nonNegativeIntegerOrDefault(value.truncated_count, 0),
  };
  assignOptionalNumbers(summary, value, ["probe_window_hours", "probe_window_hours_min", "probe_window_hours_max"]);
  const reasonCounts = sanitizeNumberRecord(value.reason_counts);
  if (reasonCounts) {
    summary.reason_counts = reasonCounts;
  }
  return summary;
}
