import type {
  DashboardState,
  FeedbackCalibrationSummary,
  FeedbackImpact,
  OpportunitySummary,
  SetupCheck,
  SourceInsight,
  SourceStat,
  ValidationSummary,
} from "../types";
import {
  assignOptionalNumbers,
  isRecord,
  numberOrDefault,
  optionalString,
  sanitizeNumberRecord,
  sanitizeObjectArray,
  sanitizeSourceAccessSummary,
} from "./shared";
import {
  assignOptionalBooleans,
  assignOptionalStrings,
  emptySourceStat,
  requiredString,
  sanitizeDashboardNextAction,
  sanitizeDashboardRelativePath,
  sanitizeSourceInsightNextAction,
  sanitizeSourceRefs,
  sanitizeSourceStat,
  stringOrDefault,
} from "./dashboard-common";

export function sanitizeActiveActions(value: unknown): NonNullable<DashboardState["active_actions"]> {
  return sanitizeObjectArray(value, "active_actions").flatMap((record, index) => {
    const actionId = optionalString(record.action_id);
    const title = optionalString(record.title);
    const status = optionalString(record.status);
    const startedAt = optionalString(record.started_at);
    if (!actionId || !title || !status || !startedAt) {
      console.warn(`[tgcs dashboard schema] active_actions[${index}] missing required display field`, record);
      return [];
    }
    const action: NonNullable<DashboardState["active_actions"]>[number] = {
      schema_version: record.schema_version === "desk_active_action_v1" ? "desk_active_action_v1" : undefined,
      action_id: actionId,
      title,
      status,
      started_at: startedAt,
      updated_at: optionalString(record.updated_at) ?? undefined,
      detail: optionalString(record.detail) ?? undefined,
    };
    assignOptionalNumbers(action, record, ["elapsed_seconds", "checked_count", "total_count"]);
    return [action];
  });
}


export function sanitizeSourceStats(value: unknown): SourceStat[] {
  return sanitizeObjectArray(value, "source_stats").flatMap((record, index) => {
    const stat = sanitizeSourceStat(record, index, "source_stats");
    return stat ? [stat] : [];
  });
}

export function sanitizeSourceInsights(value: unknown): SourceInsight[] {
  return sanitizeObjectArray(value, "source_insights").flatMap((record, index) => {
    const channel = requiredString(index, "channel", record.channel, "source_insights");
    const label = requiredString(index, "label", record.label, "source_insights");
    const reason = requiredString(index, "reason", record.reason, "source_insights");
    if (!channel || !label || !reason) {
      return [];
    }
    const stats = isRecord(record.stats)
      ? sanitizeSourceStat(record.stats, index, "source_insights.stats")
      : emptySourceStat(channel);
    const insight: SourceInsight = {
      kind: stringOrDefault(record.kind, "watch"),
      channel,
      label,
      reason,
      priority: numberOrDefault(record.priority, 0),
      stats: stats ?? emptySourceStat(channel),
    };
    assignOptionalStrings(insight, record, ["display_name", "confidence"]);
    const nextAction = sanitizeSourceInsightNextAction(record.next_action);
    if (nextAction) {
      insight.next_action = nextAction;
    }
    return [insight];
  });
}

export function sanitizeFeedbackSummary(value: unknown): DashboardState["feedback_summary"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const summary: NonNullable<DashboardState["feedback_summary"]> = {};
  if (value.schema_version === "dashboard_feedback_summary_v1" || value.schema_version === "dashboard_feedback_summary_v2") {
    summary.schema_version = value.schema_version;
  }
  assignOptionalNumbers(summary, value, [
    "current_decision_count",
    "exportable_count",
    "non_exportable_follow_up_count",
    "profile_diff_count",
    "pending_profile_diff_count",
    "applied_profile_diff_count",
    "reverted_profile_diff_count",
  ]);
  if (typeof value.changed_since_last_export === "boolean") {
    summary.changed_since_last_export = value.changed_since_last_export;
  }
  assignOptionalStrings(summary, value, ["export_scope_note"]);
  const lastExportPath = sanitizeDashboardRelativePath(value.last_export_path);
  if (lastExportPath) {
    summary.last_export_path = lastExportPath;
  }
  const nextAction = sanitizeDashboardNextAction(value.next_action);
  if (nextAction) {
    summary.next_action = nextAction;
  }
  const recentImpacts = sanitizeFeedbackImpacts(value.recent_impacts);
  if (recentImpacts.length) {
    summary.recent_impacts = recentImpacts;
  }
  const calibration = sanitizeFeedbackCalibration(value.calibration);
  if (calibration) {
    summary.calibration = calibration;
  }
  const byAction = sanitizeNumberRecord(value.by_action);
  const byRating = sanitizeNumberRecord(value.by_rating);
  const byDecisionStatus = sanitizeNumberRecord(value.by_decision_status);
  if (byAction) {
    summary.by_action = byAction;
  }
  if (byRating) {
    summary.by_rating = byRating;
  }
  if (byDecisionStatus) {
    summary.by_decision_status = byDecisionStatus;
  }
  return Object.keys(summary).length ? summary : undefined;
}

function sanitizeFeedbackCalibration(value: unknown): FeedbackCalibrationSummary | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const calibration: FeedbackCalibrationSummary = {};
  if (value.schema_version === "feedback_calibration_summary_v1") {
    calibration.schema_version = value.schema_version;
  }
  assignOptionalStrings(calibration, value, ["latest_applied_at"]);
  assignOptionalNumbers(calibration, value, [
    "runs_after_latest_apply",
    "cards_after_latest_apply",
    "high_cards_after_latest_apply",
    "feedback_after_latest_apply",
    "false_positive_after_latest_apply",
    "high_rate_after_latest_apply",
  ]);
  const nextAction = sanitizeDashboardNextAction(value.next_action);
  if (nextAction) {
    calibration.next_action = nextAction;
  }
  return Object.keys(calibration).length ? calibration : undefined;
}

export function sanitizeOpportunitySummary(value: unknown): OpportunitySummary | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const summary: OpportunitySummary = {};
  if (value.schema_version === "dashboard_opportunity_summary_v1") {
    summary.schema_version = value.schema_version;
  }
  assignOptionalStrings(summary, value, ["status", "run_id", "profile_id", "display_name"]);
  assignOptionalNumbers(summary, value, [
    "scanned_count",
    "matched_count",
    "review_card_count",
    "alert_count",
    "high_actionable_count",
  ]);
  if (typeof value.all_clear === "boolean") {
    summary.all_clear = value.all_clear;
  }
  const topItems = sanitizeOpportunityItems(value.top_items);
  if (topItems.length) {
    summary.top_items = topItems;
  }
  const diagnostics = sanitizeOpportunityDiagnostics(value.diagnostics);
  if (diagnostics) {
    summary.diagnostics = diagnostics;
  }
  const decisionCounts = sanitizeNumberRecord(value.decision_counts);
  if (decisionCounts) {
    summary.decision_counts = decisionCounts;
  }
  const nextAction = sanitizeDashboardNextAction(value.next_action);
  if (nextAction) {
    summary.next_action = nextAction;
  }
  return Object.keys(summary).length ? summary : undefined;
}

export function sanitizeValidationSummary(value: unknown): ValidationSummary | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const summary: ValidationSummary = {};
  if (value.schema_version === "dashboard_validation_summary_v1") {
    summary.schema_version = value.schema_version;
  }
  assignOptionalStrings(summary, value, ["since", "first_decision_action"]);
  assignOptionalNumbers(summary, value, [
    "window_days",
    "runs_count",
    "card_count",
    "high_card_count",
    "pending_count",
    "action_count",
    "triage_rate",
    "keep_rate",
    "false_positive_rate",
    "first_decision_minutes",
  ]);
  const byAction = sanitizeNumberRecord(value.by_action);
  if (byAction) {
    summary.by_action = byAction;
  }
  const nextAction = sanitizeDashboardNextAction(value.next_action);
  if (nextAction) {
    summary.next_action = nextAction;
  }
  return Object.keys(summary).length ? summary : undefined;
}

export function sanitizeSetupStatus(value: unknown): DashboardState["setup_status"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const setup: NonNullable<DashboardState["setup_status"]> = {};
  if (value.schema_version === "dashboard_setup_status_v1") {
    setup.schema_version = value.schema_version;
  }
  assignOptionalStrings(setup, value, ["stage", "next_step"]);
  assignOptionalBooleans(setup, value, [
    "has_profiles",
    "has_user_goal",
    "has_runs",
    "has_delivery_targets",
    "has_enabled_delivery_targets",
  ]);
  const checks = sanitizeSetupChecks(value.checks);
  if (checks.length) {
    setup.checks = checks;
  }
  return Object.keys(setup).length ? setup : undefined;
}

function sanitizeFeedbackImpacts(value: unknown): FeedbackImpact[] {
  return sanitizeObjectArray(value, "feedback_summary.recent_impacts").flatMap((record) => {
    const impact: FeedbackImpact = {};
    assignOptionalStrings(impact, record, [
      "created_at",
      "card_id",
      "profile_id",
      "action",
      "item_title",
      "rating",
      "decision_status",
      "impact_type",
      "impact_status",
      "impact_label",
      "impact_detail",
      "patch_id",
    ]);
    return Object.keys(impact).length ? [impact] : [];
  });
}

function sanitizeOpportunityItems(value: unknown): NonNullable<OpportunitySummary["top_items"]> {
  return sanitizeObjectArray(value, "opportunity_summary.top_items").flatMap((record, index) => {
    const cardId = requiredString(index, "card_id", record.card_id, "opportunity_summary.top_items");
    const title = requiredString(index, "title", record.title, "opportunity_summary.top_items");
    const rating = requiredString(index, "rating", record.rating, "opportunity_summary.top_items");
    const decisionStatus = requiredString(index, "decision_status", record.decision_status, "opportunity_summary.top_items");
    const status = requiredString(index, "status", record.status, "opportunity_summary.top_items");
    if (!cardId || !title || !rating || !decisionStatus || !status) {
      return [];
    }
    const item: NonNullable<OpportunitySummary["top_items"]>[number] = {
      card_id: cardId,
      title,
      rating,
      decision_status: decisionStatus,
      status,
      source_refs: sanitizeSourceRefs(record.source_refs),
    };
    const why = optionalString(record.why);
    const updatedAt = optionalString(record.updated_at);
    if (why) {
      item.why = why;
    }
    if (updatedAt) {
      item.updated_at = updatedAt;
    }
    return [item];
  });
}

function sanitizeOpportunityDiagnostics(value: unknown): OpportunitySummary["diagnostics"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const diagnostics: NonNullable<OpportunitySummary["diagnostics"]> = {};
  assignOptionalNumbers(diagnostics, value, ["failure_count", "warning_count"]);
  assignOptionalStrings(diagnostics, value, ["top_code"]);
  return Object.keys(diagnostics).length ? diagnostics : undefined;
}

function sanitizeSetupChecks(value: unknown): SetupCheck[] {
  return sanitizeObjectArray(value, "setup_status.checks").flatMap((record, index) => {
    const checkId = requiredString(index, "check_id", record.check_id, "setup_status.checks");
    const label = requiredString(index, "label", record.label, "setup_status.checks");
    const status = requiredString(index, "status", record.status, "setup_status.checks");
    if (!checkId || !label || !status) {
      return [];
    }
    const check: SetupCheck = { check_id: checkId, label, status };
    assignOptionalStrings(check, record, ["detail", "command"]);
    const sourceAccess = sanitizeSourceAccessSummary(record.source_access);
    if (sourceAccess) {
      check.source_access = sourceAccess;
    }
    return [check];
  });
}
