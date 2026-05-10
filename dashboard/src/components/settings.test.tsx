import { describe, expect, it } from "vitest";

import {
  SOURCE_LIBRARY_PAGE_SIZE,
  filterDeskSourcesByQuery,
  paginatedDeskSources,
  sourceLibraryActivityLabel,
  sourceLibraryCountLabel,
  sourceTopicsEditState,
} from "./settings";
import type { DeskSource, SourceStat } from "../domain/types";

function source(overrides: Partial<DeskSource>): DeskSource {
  return {
    source_id: "telegram:remote_jobs",
    label: "remote_jobs",
    channel: "remote_jobs",
    enabled: true,
    topics: ["jobs"],
    priority: "normal",
    scan_window_hours: 24,
    ...overrides,
  };
}

function sourceStat(overrides: Partial<SourceStat>): SourceStat {
  return {
    channel: "remote_jobs",
    card_count: 0,
    high_count: 0,
    medium_count: 0,
    low_count: 0,
    pending_count: 0,
    handled_count: 0,
    false_positive_count: 0,
    alert_count: 0,
    high_rate: 0,
    ...overrides,
  };
}

describe("Settings source topic editor", () => {
  it("normalizes and validates source topic edits", () => {
    expect(sourceTopicsEditState(["jobs"], "jobs")).toMatchObject({ canSave: false, topics: ["jobs"] });
    expect(sourceTopicsEditState(["jobs"], " Remote-Work, jobs, remote-work ")).toMatchObject({
      canSave: true,
      topics: ["remote-work", "jobs"],
    });
    expect(sourceTopicsEditState(["jobs"], "jobs\nremote-work")).toMatchObject({
      canSave: true,
      topics: ["jobs", "remote-work"],
    });
    expect(sourceTopicsEditState(["jobs"], " ")).toMatchObject({ canSave: false, topics: [] });
    expect(sourceTopicsEditState(["jobs"], "../private")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "x")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "-jobs")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "_jobs")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "工作")).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], `a${"b".repeat(41)}`)).toMatchObject({ canSave: false });
    expect(sourceTopicsEditState(["jobs"], "jobs, 123")).toMatchObject({ canSave: true, topics: ["jobs", "123"] });
  });

  it("limits topic count", () => {
    const text = Array.from({ length: 9 }, (_, index) => `topic${index}`).join(", ");

    expect(sourceTopicsEditState(["jobs"], text)).toMatchObject({ canSave: false });
  });

  it("filters saved sources by topic chips or search text", () => {
    const sources = [
      source({ source_id: "telegram:remote_jobs", label: "Remote Jobs", topics: ["jobs", "remote-work"] }),
      source({ source_id: "telegram:market_news", label: "Market News", channel: "market_news", topics: ["jobs", "market-news"] }),
    ];

    expect(filterDeskSourcesByQuery(sources, "", "remote-work").map((item) => item.source_id)).toEqual([
      "telegram:remote_jobs",
    ]);
    expect(filterDeskSourcesByQuery(sources, "market").map((item) => item.source_id)).toEqual([
      "telegram:market_news",
    ]);
    expect(filterDeskSourcesByQuery(sources, "news", "jobs").map((item) => item.source_id)).toEqual([
      "telegram:market_news",
    ]);
    expect(filterDeskSourcesByQuery(sources, "rem", "jobs").map((item) => item.source_id)).toEqual([
      "telegram:remote_jobs",
    ]);
    expect(filterDeskSourcesByQuery(sources, " ", " ").map((item) => item.source_id)).toEqual([
      "telegram:remote_jobs",
      "telegram:market_news",
    ]);
  });

  it("defaults saved source rendering to the first page", () => {
    const sources = Array.from({ length: SOURCE_LIBRARY_PAGE_SIZE + 3 }, (_, index) =>
      source({ source_id: `telegram:source_${index}`, label: `Source ${index}`, channel: `source_${index}` }),
    );

    expect(paginatedDeskSources(sources).map((item) => item.source_id)).toHaveLength(SOURCE_LIBRARY_PAGE_SIZE);
    expect(paginatedDeskSources(sources, SOURCE_LIBRARY_PAGE_SIZE + 24)).toHaveLength(SOURCE_LIBRARY_PAGE_SIZE + 3);
  });

  it("labels source counts as pagination or matching state", () => {
    expect(sourceLibraryCountLabel(8, 82, false)).toBe("Showing first 8 of 82");
    expect(sourceLibraryCountLabel(12, 12, false)).toBe("Showing all 12");
    expect(sourceLibraryCountLabel(4, 4, true)).toBe("4 matching shown");
    expect(sourceLibraryCountLabel(8, 82, true)).toBe("8 of 82 matching shown");
    expect(sourceLibraryCountLabel(0, 0, true)).toBe("No matching sources");
  });

  it("summarizes saved source yield from existing stats only", () => {
    expect(sourceLibraryActivityLabel([
      sourceStat({ latest_card_count: 2, alert_count: 1 }),
      sourceStat({ channel: "quiet" }),
      sourceStat({ channel: "risk", scan_incomplete: true }),
    ])).toBe("2 latest cards · 1 alert · 3 tracked · 1 risk");
    expect(sourceLibraryActivityLabel([])).toBe("");
  });
});
