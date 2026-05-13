import { describe, expect, it } from "vitest";
import fixture from "../../../tests/fixtures/contracts/desk_source_access_health_v1.summary.json";

import { sanitizeDeskActionResult } from "./sanitize";

type DeskSourceAccessFixture = {
  frontend_action_result: unknown;
  frontend_expected: unknown;
  denied_strings: string[];
};

describe("desk_source_access_health_v1 contract fixture", () => {
  it("keeps source-access action summaries aggregate-only", () => {
    const contract = fixture as DeskSourceAccessFixture;
    const result = sanitizeDeskActionResult(contract.frontend_action_result);
    const surfaced = JSON.stringify(result);

    expect(result).toEqual(contract.frontend_expected);
    for (const denied of contract.denied_strings) {
      expect(surfaced).not.toContain(denied);
    }
  });
});
