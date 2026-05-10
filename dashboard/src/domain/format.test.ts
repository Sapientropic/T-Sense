import { describe, expect, it } from "vitest";

import {
  channelDisplayName,
  compactReportName,
  decisionStatusLabel,
  formatDate,
  formatPercent,
  formatScanWindow,
  formatSemanticCap,
  formatTargetCount,
  profileDisplayName,
  sourceRefLabel,
  titleCaseLabel,
} from "./format";

describe("format domain helpers", () => {
  it("formats compact dashboard dates and preserves invalid values", () => {
    expect(formatDate("2026-05-09T03:04:00Z")).toMatch(/^\d{2}-\d{2} \d{2}:\d{2}$/);
    expect(formatDate("not-a-date")).toBe("not-a-date");
    expect(formatDate()).toBe("unknown");
    expect(formatDate("")).toBe("unknown");
  });

  it("formats scan, semantic, target, and percent readouts", () => {
    expect(formatScanWindow(2)).toBe("2h scan");
    expect(formatScanWindow(0)).toBe("Default scan");
    expect(formatSemanticCap(20)).toBe("20 semantic");
    expect(formatSemanticCap()).toBe("Default semantic");
    expect(formatTargetCount(1)).toBe("1 target");
    expect(formatTargetCount(0)).toBe("0 targets");
    expect(formatPercent(0.664)).toBe("66%");
  });

  it("formats percent edge cases without throwing", () => {
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(-0.5)).toBe("-50%");
    expect(formatPercent(Number.NaN)).toBe("0%");
    expect(formatPercent(Infinity)).toBe("0%");
  });

  it("keeps product-specific acronyms readable", () => {
    expect(titleCaseLabel("developer_api_leads")).toBe("Developer API Leads");
    expect(titleCaseLabel("jobs-fast-react")).toBe("Jobs Fast React");
    expect(channelDisplayName("@webdevelopment_jobs")).toBe("Web Development Jobs");
    expect(profileDisplayName("jobs-fast")).toBe("Jobs Fast");
    expect(sourceRefLabel({ channel: "@golang_remote" })).toBe("Go Remote");
  });

  it("normalizes decision labels defensively", () => {
    expect(decisionStatusLabel("new")).toBe("New");
    expect(decisionStatusLabel("changed")).toBe("Changed");
    expect(decisionStatusLabel("seen")).toBe("Seen");
    expect(decisionStatusLabel("recurring")).toBe("Recurring");
  });

  it("falls back cleanly for unknown or missing decisions", () => {
    expect(decisionStatusLabel("false_positive")).toBe("False Positive");
    expect(decisionStatusLabel("")).toBe("Unknown");
    expect(decisionStatusLabel(undefined)).toBe("Unknown");
    expect(decisionStatusLabel(null)).toBe("Unknown");
  });

  it("compacts report names without losing custom titles", () => {
    expect(compactReportName("Developer Opportunity Signal Report")).toBe("Developer Opportunity");
    expect(compactReportName("Weekly Leads")).toBe("Weekly Leads");
  });
});
