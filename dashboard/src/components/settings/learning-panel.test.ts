import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { LearningPanel, feedbackExportStatusLine, feedbackSuggestionStatusLine, learningActionLabel } from "./learning-panel";

describe("Learning panel copy", () => {
  it("turns a feedback export result into an app-native status line", () => {
    expect(
      feedbackExportStatusLine({
        schema_version: "feedback_export_result_v1",
        feedback_count: 3,
        output_path: "output/feedback/review-feedback.jsonl",
        changed_since_last_export: false,
        exported_at: "2026-05-10T00:00:00Z",
      }),
    ).toBe("3 decisions exported for CLI fallback · output/feedback/review-feedback.jsonl");
  });

  it("summarizes generated profile drafts without making JSONL the happy path", () => {
    expect(
      feedbackSuggestionStatusLine({
        schema_version: "feedback_profile_suggestions_result_v1",
        created_count: 1,
        existing_count: 2,
        skipped_count: 0,
        patch_ids: ["patch-1", "patch-2"],
        profile_ids: ["jobs-fast"],
      }),
    ).toBe("1 draft created · 2 already waiting");
  });

  it("uses app-first wording for the primary learning action", () => {
    expect(learningActionLabel(0)).toBe("Collect review decisions");
    expect(learningActionLabel(2)).toBe("Generate drafts");
    expect(learningActionLabel(2, 1)).toBe("Apply profile drafts");
  });

  it("keeps clear action clickable even when there are no current decisions", () => {
    const html = renderToStaticMarkup(
      createElement(LearningPanel, {
        busy: false,
        clearFeedback: () => undefined,
        applyPendingProfileDrafts: () => undefined,
        exportFeedback: () => undefined,
        exportResult: null,
        generateProfileSuggestions: () => undefined,
        openProfileDrafts: () => undefined,
        runAgainWithLearning: () => undefined,
        summary: { current_decision_count: 0, exportable_count: 0 },
        suggestionResult: null,
        undoFeedbackDecision: () => undefined,
      }),
    );

    expect(html).toContain("Clear learning decisions");
    expect(html).not.toMatch(/<button class="text-button secondary"[^>]*disabled[^>]*>[\s\S]*?Clear learning decisions/);
  });

  it("renders calibration evidence for profile tuning decisions", () => {
    const html = renderToStaticMarkup(
      createElement(LearningPanel, {
        busy: false,
        clearFeedback: () => undefined,
        applyPendingProfileDrafts: () => undefined,
        exportFeedback: () => undefined,
        exportResult: null,
        generateProfileSuggestions: () => undefined,
        openProfileDrafts: () => undefined,
        runAgainWithLearning: () => undefined,
        summary: {
          current_decision_count: 5,
          exportable_count: 3,
          pending_profile_diff_count: 1,
          applied_profile_diff_count: 2,
          reverted_profile_diff_count: 1,
          by_action: { keep: 1, skip: 1, false_positive: 1 },
          by_rating: { high: 2 },
          by_decision_status: { changed: 1 },
        },
        suggestionResult: null,
        undoFeedbackDecision: () => undefined,
      }),
    );

    expect(html).toContain('aria-label="Feedback calibration evidence"');
    expect(html).toContain("Preferred 1");
    expect(html).toContain("Wrong match 1");
    expect(html).toContain("High signal 2");
    expect(html).toContain("Applied diffs 2");
    expect(html).toContain("Reverted diffs 1");
    expect(html).toContain("reverted");
  });
});
