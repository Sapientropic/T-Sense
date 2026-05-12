import type {
  DashboardState,
  DashboardNextAction,
  DeskSourcesResult,
  DeskSource,
  DeskNotificationTokenStatus,
  DeskAction,
  DeskActionResult,
  DeskSchedulerStatus,
  DeskTelegramStatus,
  DeliveryTestResult,
  DeliveryTarget,
  FeedbackImpact,
  FeedbackExportResult,
  GitUpdateStatus,
  OpportunitySummary,
  Profile,
  ProfilePatch,
  ReviewCard,
  Run,
  RunArtifact,
  SetupCheck,
  SourceInsight,
  SourceImportResult,
  SourceRef,
  SourceStat,
  ValidationSummary,
} from "../types";

export const emptyDashboardState: DashboardState = {
  profiles: [],
  inbox: [],
  runs: [],
  delivery_targets: [],
  profile_patch_suggestions: [],
  source_stats: [],
  source_insights: [],
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
    feedback_summary: sanitizeFeedbackSummary(payload.feedback_summary),
    opportunity_summary: sanitizeOpportunitySummary(payload.opportunity_summary),
    validation_summary: sanitizeValidationSummary(payload.validation_summary),
    setup_status: sanitizeSetupStatus(payload.setup_status),
  };
}

export function sanitizeGitUpdateStatus(value: unknown): GitUpdateStatus | null {
  if (!isRecord(value)) {
    return null;
  }
  const status = optionalString(value.status);
  const branch = optionalString(value.branch);
  if (!status || !branch) {
    return null;
  }
  return {
    schema_version: "git_update_status_v1",
    status,
    message: typeof value.message === "string" ? value.message.trim() : "",
    branch,
    upstream: optionalStringOrNull(value.upstream),
    repo_url: optionalStringOrNull(value.repo_url),
    head: optionalStringOrNull(value.head),
    remote_head: optionalStringOrNull(value.remote_head),
    ahead: nonNegativeIntegerOrDefault(value.ahead, 0),
    behind: nonNegativeIntegerOrDefault(value.behind, 0),
    dirty: typeof value.dirty === "boolean" ? value.dirty : false,
    dirty_count: nonNegativeIntegerOrDefault(value.dirty_count, 0),
    pull_allowed: typeof value.pull_allowed === "boolean" ? value.pull_allowed : false,
    checked_at: optionalString(value.checked_at) ?? "",
  };
}

export function sanitizeFeedbackExportResult(value: unknown): FeedbackExportResult | null {
  if (!isRecord(value) || typeof value.output_path !== "string" || !value.output_path.trim()) {
    return null;
  }
  const outputPath = value.output_path.trim();
  const feedbackCount = value.feedback_count;
  if (typeof feedbackCount !== "number" || !Number.isInteger(feedbackCount) || feedbackCount < 0) {
    return null;
  }
  const result: FeedbackExportResult = {
    schema_version: "feedback_export_result_v1",
    feedback_count: feedbackCount,
    output_path: outputPath,
  };
  if (typeof value.changed_since_last_export === "boolean") {
    result.changed_since_last_export = value.changed_since_last_export;
  }
  const exportedAt = optionalString(value.exported_at);
  if (exportedAt) {
    result.exported_at = exportedAt;
  }
  return result;
}

export function sanitizeDeskActions(value: unknown): DeskAction[] {
  const payload = isRecord(value) ? value : {};
  return sanitizeObjectArray(payload.actions, "desk_actions.actions").flatMap((record, index) => {
    const actionId = optionalString(record.action_id);
    const group = optionalString(record.group);
    const title = optionalString(record.title);
    const detail = optionalString(record.detail);
    const runMode = optionalString(record.run_mode);
    const displayCommand = optionalString(record.display_command);
    const nextAction = optionalString(record.next_action);
    if (!actionId || !group || !title || !detail || !runMode || !displayCommand || !nextAction) {
      console.warn(`[tgcs dashboard schema] desk_actions.actions[${index}] missing required display field`, record);
      return [];
    }
    return [
      {
        schema_version: "desk_action_v1",
        action_id: actionId,
        group,
        title,
        detail,
        run_mode: runMode,
        display_command: displayCommand,
        next_action: nextAction,
      },
    ];
  });
}

export function sanitizeDeskActionResult(value: unknown): DeskActionResult | null {
  if (!isRecord(value)) {
    return null;
  }
  const actionId = optionalString(value.action_id);
  const status = optionalString(value.status);
  const title = optionalString(value.title);
  const displayCommand = optionalString(value.display_command);
  if (!actionId || !status || !title || !displayCommand) {
    return null;
  }
  const exitCode = typeof value.exit_code === "number" && Number.isInteger(value.exit_code) ? value.exit_code : null;
  return {
    schema_version: "desk_action_result_v1",
    action_id: actionId,
    status,
    title,
    detail: optionalString(value.detail) ?? "",
    display_command: displayCommand,
    exit_code: exitCode,
    artifact_path: optionalString(value.artifact_path) ?? "",
    next_action: optionalString(value.next_action) ?? "",
    finished_at: optionalString(value.finished_at) ?? "",
  };
}

export function sanitizeDeskSchedulerStatus(value: unknown): DeskSchedulerStatus | null {
  if (!isRecord(value)) {
    return null;
  }
  const status = optionalString(value.status);
  const taskLabel = optionalString(value.task_label);
  const detail = optionalString(value.detail);
  const nextAction = optionalString(value.next_action);
  const checkedAt = optionalString(value.checked_at);
  const intervalMinutes = typeof value.interval_minutes === "number" && Number.isInteger(value.interval_minutes)
    ? Math.max(0, value.interval_minutes)
    : 0;
  if (!status || !taskLabel || !detail || !nextAction || !checkedAt) {
    return null;
  }
  const sanitized: DeskSchedulerStatus = {
    schema_version: "desk_scheduler_status_v1",
    available: value.available === true,
    installed: value.installed === true,
    status,
    task_label: taskLabel,
    interval_minutes: intervalMinutes,
    detail,
    next_action: nextAction,
    checked_at: checkedAt,
  };
  const platform = optionalString(value.platform);
  const backend = optionalString(value.backend);
  if (platform) {
    sanitized.platform = platform;
  }
  if (backend) {
    sanitized.backend = backend;
  }
  if ("can_install" in value) {
    sanitized.can_install = value.can_install === true;
  }
  if ("can_remove" in value) {
    sanitized.can_remove = value.can_remove === true;
  }
  return sanitized;
}

export function sanitizeDeskTelegramStatus(value: unknown): DeskTelegramStatus | null {
  if (!isRecord(value)) {
    return null;
  }
  const loginState = optionalString(value.login_state);
  if (!loginState) {
    return null;
  }
  return {
    schema_version: "desk_telegram_status_v1",
    credentials_ready: value.credentials_ready === true,
    session_ready: value.session_ready === true,
    login_state: loginState,
    detail: optionalString(value.detail) ?? "",
    next_step: optionalString(value.next_step) ?? "",
    config_path: optionalString(value.config_path) ?? "",
    session_path: optionalString(value.session_path) ?? "",
  };
}

export function sanitizeDeskNotificationTokenStatus(value: unknown): DeskNotificationTokenStatus | null {
  if (!isRecord(value)) {
    return null;
  }
  const source = optionalString(value.source);
  if (!source) {
    return null;
  }
  const sanitized: DeskNotificationTokenStatus = {
    schema_version: "desk_notification_token_status_v1",
    configured: value.configured === true,
    source,
    updated_at: optionalStringOrNull(value.updated_at),
    env_configured: value.env_configured === true,
    local_store_supported: value.local_store_supported === true,
    local_store_configured: value.local_store_configured === true,
    can_save: value.can_save === true,
    can_clear: value.can_clear === true,
    platform: optionalString(value.platform) ?? "",
    detail: optionalString(value.detail) ?? "",
  };
  const localStoreBackend = optionalString(value.local_store_backend);
  const localStoreLabel = optionalString(value.local_store_label);
  if (localStoreBackend) {
    sanitized.local_store_backend = localStoreBackend;
  }
  if (localStoreLabel) {
    sanitized.local_store_label = localStoreLabel;
  }
  return sanitized;
}

function sanitizeProfiles(value: unknown): Profile[] {
  return sanitizeObjectArray(value, "profiles").flatMap((record, index) => {
    const profileId = requiredString(index, "profile_id", record.profile_id, "profiles");
    if (!profileId) {
      return [];
    }
    const profile: Profile = {
      profile_id: profileId,
      enabled: typeof record.enabled === "boolean" ? record.enabled : false,
      updated_at: stringOrDefault(record.updated_at, ""),
    };
    assignOptionalStrings(profile, record, ["display_name", "report_display_name", "display_path", "alert_schedule_mode"]);
    const sourceTopics = stringArray(record.source_topics);
    if (sourceTopics.length) {
      profile.source_topics = sourceTopics;
    }
    assignOptionalNumbers(profile, record, ["scan_window_hours", "semantic_max_messages", "delivery_target_count"]);
    const matchingProfile = sanitizeProfileMatchingProfile(record.matching_profile);
    if (matchingProfile) {
      profile.matching_profile = matchingProfile;
    }
    return [profile];
  });
}

function sanitizeProfileMatchingProfile(value: unknown): Profile["matching_profile"] | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const sections = sanitizeObjectArray(value.sections, "profile matching sections")
    .map((section) => ({
      key: stringOrDefault(section.key, ""),
      label: stringOrDefault(section.label, ""),
      items: stringArray(section.items).slice(0, 12),
    }))
    .filter((section) => section.key && section.label && section.items.length);
  return {
    schema_version: value.schema_version === "profile_matching_profile_v1" ? "profile_matching_profile_v1" : undefined,
    summary: optionalString(value.summary),
    sections,
    learned_preferences: stringArray(value.learned_preferences).slice(0, 24),
    editable_text: optionalString(value.editable_text),
  };
}

function sanitizeRuns(value: unknown): Run[] {
  return sanitizeObjectArray(value, "runs").flatMap((record, index) => {
    const runId = requiredString(index, "run_id", record.run_id, "runs");
    const profileId = requiredString(index, "profile_id", record.profile_id, "runs");
    const status = requiredString(index, "status", record.status, "runs");
    const startedAt = requiredString(index, "started_at", record.started_at, "runs");
    if (!runId || !profileId || !status || !startedAt) {
      return [];
    }
    const run: Run = { run_id: runId, profile_id: profileId, status, started_at: startedAt };
    assignOptionalStrings(run, record, ["display_name", "completed_at"]);
    assignOptionalNumbers(run, record, ["alert_count", "review_card_count"]);
    const artifact = sanitizeRunArtifact(record.report_artifact);
    if (artifact || record.report_artifact === null) {
      run.report_artifact = artifact;
    }
    const quality = sanitizeRunQuality(record.quality);
    if (quality) {
      run.quality = quality;
    }
    return [run];
  });
}

function sanitizeDeliveryTargets(value: unknown): DeliveryTarget[] {
  return sanitizeObjectArray(value, "delivery_targets").flatMap((record, index) => {
    const targetId = requiredString(index, "target_id", record.target_id, "delivery_targets");
    const type = requiredString(index, "type", record.type, "delivery_targets");
    if (!targetId || !type) {
      return [];
    }
    const target: DeliveryTarget = {
      target_id: targetId,
      type,
      enabled: typeof record.enabled === "boolean" ? record.enabled : false,
      config: sanitizeDeliveryTargetConfig(record.config),
      updated_at: stringOrDefault(record.updated_at, ""),
    };
    assignOptionalStrings(target, record, ["display_name", "status_label", "detail"]);
    return [target];
  });
}

function sanitizeDeliveryTargetConfig(value: unknown): Record<string, unknown> {
  const record = isRecord(value) ? value : {};
  const chatId = optionalString(record.chat_id);
  return chatId ? { chat_id: chatId } : {};
}

export function sanitizeDeliveryTestResult(value: unknown): DeliveryTestResult | null {
  if (!isRecord(value)) {
    return null;
  }
  const targetId = optionalString(value.target_id);
  const targetType = optionalString(value.target_type);
  const status = optionalString(value.status);
  if (!targetId || !targetType || !status) {
    return null;
  }
  const result: DeliveryTestResult = {
    schema_version: value.schema_version === "desk_delivery_test_result_v1" ? value.schema_version : undefined,
    target_id: targetId,
    target_type: targetType,
    mode: "dry-run",
    ok: value.ok === true,
    status,
  };
  assignOptionalStrings(result, value, ["title", "detail", "error", "finished_at"]);
  return result;
}

export function sanitizeSourceImportResult(value: unknown): SourceImportResult | null {
  if (!isRecord(value)) {
    return null;
  }
  const topic = optionalString(value.topic);
  const registryPath = optionalString(value.registry_path);
  if (!topic || !registryPath) {
    return null;
  }
  const result: SourceImportResult = {
    schema_version: value.schema_version === "desk_source_import_result_v1" ? value.schema_version : undefined,
    dry_run: value.dry_run === true,
    written: value.written === true,
    topic,
    added_count: nonNegativeIntegerOrDefault(value.added_count, 0),
    updated_count: nonNegativeIntegerOrDefault(value.updated_count, 0),
    unchanged_count: nonNegativeIntegerOrDefault(value.unchanged_count, 0),
    source_count: nonNegativeIntegerOrDefault(value.source_count, 0),
    registry_path: registryPath,
    preview_sources: sanitizeSourceImportPreviewSources(value.preview_sources),
    resolved_plan: sanitizeResolvedSourcePlan(value.resolved_plan),
    preview_truncated_count: nonNegativeIntegerOrDefault(value.preview_truncated_count, 0),
  };
  assignOptionalStrings(result, value, ["title", "detail", "next_action", "finished_at"]);
  return result;
}

function sanitizeResolvedSourcePlan(value: unknown): SourceImportResult["resolved_plan"] {
  if (!isRecord(value)) {
    return undefined;
  }
  return {
    add: stringArray(value.add),
    remove: stringArray(value.remove),
    disable: stringArray(value.disable),
    enable: stringArray(value.enable),
  };
}

export function sanitizeDeskSourcesResult(value: unknown): DeskSourcesResult | null {
  if (!isRecord(value)) {
    return null;
  }
  const registryPath = optionalString(value.registry_path);
  if (!registryPath) {
    return null;
  }
  return {
    schema_version: value.schema_version === "desk_sources_v1" ? value.schema_version : undefined,
    source_count: nonNegativeIntegerOrDefault(value.source_count, 0),
    enabled_count: nonNegativeIntegerOrDefault(value.enabled_count, 0),
    topics: stringArray(value.topics),
    registry_path: registryPath,
    sources: sanitizeDeskSources(value.sources),
  };
}

function sanitizeDeskSources(value: unknown): DeskSource[] {
  return sanitizeObjectArray(value, "desk_sources.sources").flatMap((record, index) => {
    const sourceId = optionalString(record.source_id);
    const label = optionalString(record.label);
    const channel = optionalString(record.channel);
    if (!sourceId || !label || !channel) {
      console.warn(`[tgcs dashboard schema] desk_sources.sources[${index}] missing required display field`, record);
      return [];
    }
    return [
      {
        schema_version: record.schema_version === "desk_source_v1" ? record.schema_version : undefined,
        source_id: sourceId,
        label,
        channel,
        enabled: record.enabled !== false,
        topics: stringArray(record.topics),
        priority: optionalString(record.priority) ?? "normal",
        scan_window_hours: nonNegativeIntegerOrDefault(record.scan_window_hours, 24),
      },
    ];
  });
}

function sanitizeSourceImportPreviewSources(value: unknown): SourceImportResult["preview_sources"] {
  return sanitizeObjectArray(value, "source_import.preview_sources").flatMap((record) => {
    const label = optionalString(record.label);
    const sourceId = optionalString(record.source_id);
    if (!label || !sourceId) {
      return [];
    }
    return [{ label, source_id: sourceId }];
  });
}

function sanitizeProfilePatches(value: unknown): ProfilePatch[] {
  return sanitizeObjectArray(value, "profile_patch_suggestions").flatMap((record, index) => {
    const patchId = requiredString(index, "patch_id", record.patch_id, "profile_patch_suggestions");
    const profileId = requiredString(index, "profile_id", record.profile_id, "profile_patch_suggestions");
    if (!patchId || !profileId) {
      return [];
    }
    const patch: ProfilePatch = {
      patch_id: patchId,
      profile_id: profileId,
      note: stringOrDefault(record.note, ""),
      status: stringOrDefault(record.status, "unknown"),
      diff_text: stringOrDefault(record.diff_text, ""),
      created_at: stringOrDefault(record.created_at, ""),
    };
    assignOptionalStrings(patch, record, [
      "profile_display_path",
      "card_id",
      "card_title",
      "base_profile_hash",
      "base_profile_short_hash",
      "applied_at",
    ]);
    const applyReadiness = sanitizeApplyReadiness(record.apply_readiness);
    if (applyReadiness) {
      patch.apply_readiness = applyReadiness;
    }
    return [patch];
  });
}

function sanitizeSourceStats(value: unknown): SourceStat[] {
  return sanitizeObjectArray(value, "source_stats").flatMap((record, index) => {
    const stat = sanitizeSourceStat(record, index, "source_stats");
    return stat ? [stat] : [];
  });
}

function sanitizeSourceInsights(value: unknown): SourceInsight[] {
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

function sanitizeFeedbackSummary(value: unknown): DashboardState["feedback_summary"] {
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
  assignOptionalStrings(summary, value, ["export_scope_note", "last_export_path"]);
  const nextAction = sanitizeDashboardNextAction(value.next_action);
  if (nextAction) {
    summary.next_action = nextAction;
  }
  const recentImpacts = sanitizeFeedbackImpacts(value.recent_impacts);
  if (recentImpacts.length) {
    summary.recent_impacts = recentImpacts;
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

function sanitizeOpportunitySummary(value: unknown): OpportunitySummary | undefined {
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

function sanitizeValidationSummary(value: unknown): ValidationSummary | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const summary: ValidationSummary = {};
  if (value.schema_version === "dashboard_validation_summary_v1") {
    summary.schema_version = value.schema_version;
  }
  assignOptionalStrings(summary, value, ["since"]);
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

function sanitizeSetupStatus(value: unknown): DashboardState["setup_status"] {
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

export function sanitizeInboxCards(value: unknown): ReviewCard[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const cards: ReviewCard[] = [];
  value.forEach((card, index) => {
    if (!isRecord(card)) {
      console.warn(`[tgcs dashboard schema] inbox[${index}] expected object`, card);
      return;
    }
    const sanitized = sanitizeInboxCard(card, index);
    if (sanitized) {
      cards.push(sanitized);
    }
  });
  return cards;
}

function sanitizeInboxCard(record: Record<string, unknown>, index: number): ReviewCard | null {
  const cardId = requiredString(index, "card_id", record.card_id);
  const profileId = requiredString(index, "profile_id", record.profile_id);
  const title = requiredString(index, "title", record.title);
  if (!cardId || !profileId || !title) {
    return null;
  }
  warnUnexpectedInboxField(index, "rating", record.rating);
  warnUnexpectedInboxField(index, "decision_status", record.decision_status);
  const sanitized: ReviewCard = {
    schema_version: "review_card_v1",
    card_id: cardId,
    profile_id: profileId,
    title,
    rating: stringOrDefault(record.rating, "unknown"),
    decision_status: stringOrDefault(record.decision_status, "unknown"),
    source_refs: sanitizeSourceRefs(record.source_refs),
    item: sanitizeReviewItem(record.item),
    status: stringOrDefault(record.status, "pending"),
    updated_at: stringOrDefault(record.updated_at, ""),
  };
  const firstRunId = optionalString(record.first_run_id);
  const lastRunId = optionalString(record.last_run_id);
  const reportPath = optionalString(record.report_path);
  const dashboardUrl = optionalString(record.dashboard_url);
  if (firstRunId) {
    sanitized.first_run_id = firstRunId;
  }
  if (lastRunId) {
    sanitized.last_run_id = lastRunId;
  }
  if (reportPath) {
    sanitized.report_path = reportPath;
  }
  if (dashboardUrl) {
    sanitized.dashboard_url = dashboardUrl;
  }
  return sanitized;
}

function sanitizeObjectArray(value: unknown, scope: string): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item, index) => {
    if (!isRecord(item)) {
      console.warn(`[tgcs dashboard schema] ${scope}[${index}] expected object`, item);
      return [];
    }
    return [item];
  });
}

function sanitizeRunArtifact(value: unknown): RunArtifact | null | undefined {
  if (value === null) {
    return null;
  }
  if (!isRecord(value) || typeof value.path !== "string") {
    return undefined;
  }
  const artifact: RunArtifact = { path: value.path };
  assignOptionalStrings(artifact, value, ["type", "sha256", "category", "format", "display_name", "display_path"]);
  return artifact;
}

function sanitizeRunQuality(value: unknown): Run["quality"] | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const quality: NonNullable<Run["quality"]> = {};
  assignOptionalStrings(quality, value, ["prefilter", "semantic_stage", "llm_provider", "top_diagnostic_code"]);
  assignOptionalNumbersOrNull(quality, value, ["cache_hit_rate", "latency_ms", "completion_tokens"]);
  assignOptionalNumbers(quality, value, [
    "diagnostic_count",
    "diagnostic_failure_count",
    "diagnostic_warning_count",
    "diagnostic_info_count",
  ]);
  return Object.keys(quality).length ? quality : undefined;
}

function sanitizeSourceStat(record: Record<string, unknown>, index: number, scope: string): SourceStat | null {
  const channel = requiredString(index, "channel", record.channel, scope);
  if (!channel) {
    return null;
  }
  const stat: SourceStat = {
    channel,
    card_count: numberOrDefault(record.card_count, 0),
    high_count: numberOrDefault(record.high_count, 0),
    medium_count: numberOrDefault(record.medium_count, 0),
    low_count: numberOrDefault(record.low_count, 0),
    pending_count: numberOrDefault(record.pending_count, 0),
    handled_count: numberOrDefault(record.handled_count, 0),
    false_positive_count: numberOrDefault(record.false_positive_count, 0),
    alert_count: numberOrDefault(record.alert_count, 0),
    high_rate: numberOrDefault(record.high_rate, 0),
  };
  assignOptionalStrings(stat, record, ["display_name", "latest_run_id", "scan_failure_reason"]);
  assignOptionalNumbers(stat, record, [
    "latest_card_count",
    "latest_high_count",
    "raw_count",
    "kept_count",
    "scan_keep_rate",
    "card_yield_rate",
  ]);
  assignOptionalBooleans(stat, record, ["scan_failure", "scan_incomplete"]);
  return stat;
}

function emptySourceStat(channel: string): SourceStat {
  return {
    channel,
    card_count: 0,
    high_count: 0,
    medium_count: 0,
    low_count: 0,
    pending_count: 0,
    handled_count: 0,
    false_positive_count: 0,
    alert_count: 0,
    high_rate: 0,
  };
}

function requiredString(index: number, field: string, value: unknown, scope = "inbox") {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  console.warn(`[tgcs dashboard schema] ${scope}[${index}].${field} expected non-empty string`, value);
  return "";
}

function stringOrDefault(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback;
}

function optionalString(value: unknown) {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function optionalStringOrNull(value: unknown) {
  if (value === null) {
    return null;
  }
  return optionalString(value);
}

function optionalHttpUrl(value: unknown) {
  const text = optionalString(value);
  if (!text) {
    return undefined;
  }
  try {
    const parsed = new URL(text);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}

function numberOrDefault(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nonNegativeIntegerOrDefault(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : fallback;
}

function stringArray(value: unknown) {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        if (typeof item !== "string") {
          return [];
        }
        const trimmed = item.trim();
        return trimmed ? [trimmed] : [];
      })
    : [];
}

function assignOptionalStrings<T extends object>(target: T, record: Record<string, unknown>, fields: string[]) {
  const writable = target as Record<string, unknown>;
  fields.forEach((field) => {
    const value = optionalString(record[field]);
    if (value) {
      writable[field] = value;
    }
  });
}

function assignOptionalNumbers<T extends object>(target: T, record: Record<string, unknown>, fields: string[]) {
  const writable = target as Record<string, unknown>;
  fields.forEach((field) => {
    const value = record[field];
    if (typeof value === "number" && Number.isFinite(value)) {
      writable[field] = value;
    }
  });
}

function assignOptionalNumbersOrNull<T extends object>(target: T, record: Record<string, unknown>, fields: string[]) {
  const writable = target as Record<string, unknown>;
  fields.forEach((field) => {
    const value = record[field];
    if (value === null || (typeof value === "number" && Number.isFinite(value))) {
      writable[field] = value;
    }
  });
}

function assignOptionalBooleans<T extends object>(target: T, record: Record<string, unknown>, fields: string[]) {
  const writable = target as Record<string, unknown>;
  fields.forEach((field) => {
    const value = record[field];
    if (typeof value === "boolean") {
      writable[field] = value;
    }
  });
}

function sanitizeSourceRefs(value: unknown): SourceRef[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((ref) => {
    if (!isRecord(ref) || typeof ref.channel !== "string" || (typeof ref.id !== "string" && typeof ref.id !== "number")) {
      return [];
    }
    const cleanRef: SourceRef = { channel: ref.channel, id: ref.id };
    const url = optionalHttpUrl(ref.url);
    if (url) {
      cleanRef.url = url;
    }
    return [cleanRef];
  });
}

function sanitizeReviewItem(value: unknown): ReviewCard["item"] {
  if (!isRecord(value)) {
    return {};
  }
  const item: ReviewCard["item"] = {};
  const why = optionalString(value.why);
  const decisionState = sanitizeDecisionState(value.decision_state);
  if (why) {
    item.why = why;
  }
  if (decisionState) {
    item.decision_state = decisionState;
  }
  return item;
}

function sanitizeDashboardNextAction(value: unknown): DashboardNextAction | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const action: DashboardNextAction = {};
  assignOptionalStrings(action, value, ["label", "detail", "command", "target", "target_tab", "action_id", "artifact_path"]);
  return Object.keys(action).length ? action : undefined;
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
    return [check];
  });
}

function sanitizeNumberRecord(value: unknown): Record<string, number> | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const clean = Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1])),
  );
  return Object.keys(clean).length ? clean : undefined;
}

function sanitizeApplyReadiness(value: unknown): ProfilePatch["apply_readiness"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const readiness: NonNullable<ProfilePatch["apply_readiness"]> = {};
  assignOptionalStrings(readiness, value, ["status", "label", "detail"]);
  return Object.keys(readiness).length ? readiness : undefined;
}

function sanitizeSourceInsightNextAction(value: unknown): SourceInsight["next_action"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const action: NonNullable<SourceInsight["next_action"]> = {};
  assignOptionalStrings(action, value, ["label", "detail", "command"]);
  return Object.keys(action).length ? action : undefined;
}

function sanitizeDecisionState(value: unknown): ReviewCard["item"]["decision_state"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const decisionState: NonNullable<ReviewCard["item"]["decision_state"]> = {};
  assignOptionalStrings(decisionState, value, ["status"]);
  const signals = stringArray(value.signals);
  if (signals.length) {
    decisionState.signals = signals;
  }
  const explanations = sanitizeStringRecord(value.explanations);
  if (explanations) {
    decisionState.explanations = explanations;
  }
  return Object.keys(decisionState).length ? decisionState : undefined;
}

function sanitizeStringRecord(value: unknown): Record<string, string> | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const clean = Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === "string" && entry[1].trim() !== ""),
  );
  return Object.keys(clean).length ? clean : undefined;
}

function warnUnexpectedInboxField(index: number, field: string, value: unknown) {
  if (value === null || value === undefined || typeof value === "string") {
    return;
  }
  console.warn(`[tgcs dashboard schema] inbox[${index}].${field} expected string/null/undefined`, value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
