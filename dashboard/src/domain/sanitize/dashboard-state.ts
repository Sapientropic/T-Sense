import type { DashboardState } from "../types";
import { isRecord } from "./shared";
import { sanitizeDeliveryTargets } from "./dashboard-delivery";
import { sanitizeProfilePatches, sanitizeProfiles } from "./dashboard-profiles";
import { sanitizeInboxCards } from "./dashboard-review";
import { sanitizeRuns } from "./dashboard-runs";
import {
  sanitizeActiveActions,
  sanitizeFeedbackSummary,
  sanitizeOpportunitySummary,
  sanitizeSetupStatus,
  sanitizeSourceInsights,
  sanitizeSourceStats,
  sanitizeValidationSummary,
} from "./dashboard-summary";

export const emptyDashboardState: DashboardState = {
  profiles: [],
  inbox: [],
  runs: [],
  delivery_targets: [],
  profile_patch_suggestions: [],
  source_stats: [],
  source_insights: [],
  active_actions: [],
  feedback_summary: undefined,
  opportunity_summary: undefined,
  validation_summary: undefined,
  setup_status: undefined,
};

export function sanitizeDashboardState(value: unknown): DashboardState {
  const payload = isRecord(value) ? value : {};
  return {
    schema_version: payload.schema_version === "dashboard_state_v1" ? payload.schema_version : undefined,
    profiles: sanitizeProfiles(payload.profiles),
    inbox: sanitizeInboxCards(payload.inbox),
    runs: sanitizeRuns(payload.runs),
    delivery_targets: sanitizeDeliveryTargets(payload.delivery_targets),
    profile_patch_suggestions: sanitizeProfilePatches(payload.profile_patch_suggestions),
    source_stats: sanitizeSourceStats(payload.source_stats),
    source_insights: sanitizeSourceInsights(payload.source_insights),
    active_actions: sanitizeActiveActions(payload.active_actions),
    feedback_summary: sanitizeFeedbackSummary(payload.feedback_summary),
    opportunity_summary: sanitizeOpportunitySummary(payload.opportunity_summary),
    validation_summary: sanitizeValidationSummary(payload.validation_summary),
    setup_status: sanitizeSetupStatus(payload.setup_status),
  };
}
