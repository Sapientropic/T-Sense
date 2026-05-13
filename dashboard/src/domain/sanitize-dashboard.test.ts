import { describe, expect, it } from "vitest";

import {
  sanitizeDashboardState,
  sanitizeDeskActionResult,
  sanitizeFeedbackExportResult,
  sanitizeInboxCards,
  sanitizeSourceImportResult,
} from "./sanitize/dashboard";
import { sanitizeDashboardState as sanitizeDashboardStateImpl } from "./sanitize/dashboard-state";
import { sanitizeInboxCards as sanitizeInboxCardsImpl } from "./sanitize/dashboard-review";
import {
  sanitizeDeskActionResult as sanitizeDeskActionResultImpl,
  sanitizeFeedbackExportResult as sanitizeFeedbackExportResultImpl,
  sanitizeSourceImportResult as sanitizeSourceImportResultImpl,
} from "./sanitize/desk";

describe("sanitize dashboard facade", () => {
  it("re-exports dashboard-owned state and review helpers", () => {
    expect(sanitizeDashboardState).toBe(sanitizeDashboardStateImpl);
    expect(sanitizeInboxCards).toBe(sanitizeInboxCardsImpl);
  });

  it("re-exports desk-owned helpers without a second implementation", () => {
    expect(sanitizeDeskActionResult).toBe(sanitizeDeskActionResultImpl);
    expect(sanitizeFeedbackExportResult).toBe(sanitizeFeedbackExportResultImpl);
    expect(sanitizeSourceImportResult).toBe(sanitizeSourceImportResultImpl);
  });
});
