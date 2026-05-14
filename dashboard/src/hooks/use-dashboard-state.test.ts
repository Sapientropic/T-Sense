import { describe, expect, it } from "vitest";

import { DASHBOARD_STATE_AUTO_REFRESH_MS, shouldPollDashboardState } from "./use-dashboard-state";

describe("useDashboardState polling policy", () => {
  it("polls local state automatically only when the page can use the result", () => {
    expect(DASHBOARD_STATE_AUTO_REFRESH_MS).toBeGreaterThan(0);
    expect(shouldPollDashboardState({ busy: false, visibilityState: "visible" })).toBe(true);
    expect(shouldPollDashboardState({ busy: true, visibilityState: "visible" })).toBe(false);
    expect(shouldPollDashboardState({ busy: false, visibilityState: "hidden" })).toBe(false);
  });
});
