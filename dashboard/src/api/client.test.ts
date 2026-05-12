import { afterEach, describe, expect, it, vi } from "vitest";

import { errorMessage, loadDashboardState, loadDeskActions, normalizeDashboardError } from "./client";

function mockJsonResponse(payload: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("dashboard API errors", () => {
  it("turns generic server failures into local recovery guidance", () => {
    expect(normalizeDashboardError("Internal Server Error")).toBe(
      "Local dashboard API hit an internal error. Refresh once; if it repeats, restart Signal Desk.",
    );
    expect(normalizeDashboardError("HTTP 500")).toContain("restart Signal Desk");
  });

  it("turns network failures into a reachable next step", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toBe(
      "Local dashboard API is unreachable. Start or restart Signal Desk, then refresh.",
    );
  });

  it("keeps specific validation errors readable", () => {
    expect(errorMessage(new Error("Use 1 to 8 topic tags."))).toBe("Use 1 to 8 topic tags.");
    expect(errorMessage(new Error("Invalid source library response"))).toBe(
      "Local dashboard API returned data this screen cannot read. Refresh once; if it repeats, restart Signal Desk.",
    );
  });
});

describe("dashboard API contract validation", () => {
  it("throws on malformed dashboard state payloads instead of sanitizing to empty state", async () => {
    mockJsonResponse({
      schema_version: "dashboard_state_v1",
      profiles: "bad",
      inbox: [],
      runs: [],
      delivery_targets: [],
      profile_patch_suggestions: [],
      source_stats: [],
      source_insights: [],
    });

    await expect(loadDashboardState()).rejects.toThrow("Invalid dashboard state response");
  });

  it("throws on malformed Desk actions payloads instead of returning no controls", async () => {
    mockJsonResponse({ schema_version: "desk_actions_v1", actions: "bad" });

    await expect(loadDeskActions()).rejects.toThrow("Invalid Desk actions response");
  });
});
