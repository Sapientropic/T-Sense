import { describe, expect, it, vi } from "vitest";

import {
  sanitizeLocalRelativePath,
  sanitizeObjectArray,
  sanitizeSourceAccessSummary,
  sanitizeStringRecord,
} from "./sanitize/shared";

describe("shared sanitizer primitives", () => {
  it("filters object arrays with scoped warnings", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    expect(sanitizeObjectArray([{ id: "ok" }, null, "bad"], "payload.items")).toEqual([{ id: "ok" }]);
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] payload.items[1] expected object", null);
    expect(warn).toHaveBeenCalledWith("[tgcs dashboard schema] payload.items[2] expected object", "bad");
  });

  it("normalizes relative paths while rejecting local absolute and traversal paths", () => {
    expect(sanitizeLocalRelativePath(" output\\runs\\run-1\\report.html ")).toBe("output/runs/run-1/report.html");
    expect(sanitizeLocalRelativePath("C:/Users/Administrator/private/report.html")).toBeNull();
    expect(sanitizeLocalRelativePath("../private/report.html")).toBeNull();
    expect(sanitizeLocalRelativePath("output/runs/../secret.html")).toBeNull();
    expect(sanitizeLocalRelativePath("https://example.com/report.html")).toBeNull();
    expect(sanitizeLocalRelativePath("output/report\n.html")).toBeNull();
  });

  it("keeps only non-empty string values from string records", () => {
    expect(sanitizeStringRecord({ high: " good ", blank: " ", count: 2 })).toEqual({ high: "good" });
    expect(sanitizeStringRecord({ blank: " " })).toBeUndefined();
    expect(sanitizeStringRecord(null)).toBeUndefined();
  });

  it("sanitizes source access summaries consistently for desk and dashboard payloads", () => {
    expect(
      sanitizeSourceAccessSummary({
        schema_version: "desk_source_access_health_v1",
        checked_at: " 2026-05-12T15:00:00Z ",
        source_count: 8,
        checked_count: 6,
        accessible_count: 3,
        quiet_count: 1,
        inaccessible_count: 2,
        truncated_count: 2,
        probe_window_hours: 24,
        probe_window_hours_min: 24,
        probe_window_hours_max: 24,
        reason_counts: { cannot_resolve_entity: 2, bad: "ignored" },
        token: "secret",
      }),
    ).toEqual({
      schema_version: "desk_source_access_health_v1",
      checked_at: "2026-05-12T15:00:00Z",
      source_count: 8,
      checked_count: 6,
      accessible_count: 3,
      quiet_count: 1,
      inaccessible_count: 2,
      truncated_count: 2,
      probe_window_hours: 24,
      probe_window_hours_min: 24,
      probe_window_hours_max: 24,
      reason_counts: { cannot_resolve_entity: 2 },
    });
    expect(sanitizeSourceAccessSummary(null)).toBeUndefined();
  });
});
