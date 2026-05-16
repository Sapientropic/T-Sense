import type {
  DeskAction,
  DeskActionResult,
  DeskAiProviderStatus,
  DeskAiSettingsStatus,
  DeskBotIdentityResult,
  DeskBotGatewayStatus,
  DeskNotificationTokenStatus,
  DeskSchedulerStatus,
  DeskSource,
  DeskSourcesResult,
  DeskTelegramStatus,
  DeliveryChatDetectionResult,
  DeliveryTestResult,
  FeedbackClearResult,
  FeedbackExportResult,
  FeedbackProfileSuggestionsResult,
  GitUpdateStatus,
  ProfileCoachPreview,
  ProfileCreateResult,
  ProfileCreatePreview,
  ProfileTemplateCatalog,
  SourceImportResult,
} from "../types";
import {
  isRecord,
  nonNegativeInteger,
  nonNegativeIntegerOrDefault,
  numberOrDefault,
  optionalString,
  optionalStringOrNull,
  sanitizeLocalRelativePath,
  sanitizeObjectArray,
  sanitizeSourceAccessSummary,
  stringArray,
} from "./shared";

export function sanitizeGitUpdateStatus(value: unknown): GitUpdateStatus | null {
  if (!isRecord(value) || value.schema_version !== "git_update_status_v1") {
    return null;
  }
  const status = optionalString(value.status);
  const branch = optionalString(value.branch);
  if (!status || !branch) {
    return null;
  }
  const result: GitUpdateStatus = {
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
    dirty_paths: stringArray(value.dirty_paths).flatMap((path) => sanitizeLocalRelativePath(path) ?? []),
    repairable_dirty: value.repairable_dirty === true,
    repairable_dirty_count: nonNegativeIntegerOrDefault(value.repairable_dirty_count, 0),
    dirty_repair_applied: value.dirty_repair_applied === true,
    pull_allowed: typeof value.pull_allowed === "boolean" ? value.pull_allowed : false,
    checked_at: optionalString(value.checked_at) ?? "",
  };
  if (typeof value.fetched === "boolean") {
    result.fetched = value.fetched;
  }
  const pullOutput = optionalString(value.pull_output);
  if (pullOutput) {
    result.pull_output = pullOutput;
  }
  if (value.desk_build_status === "success" || value.desk_build_status === "failed" || value.desk_build_status === "skipped") {
    result.desk_build_status = value.desk_build_status;
  }
  const deskBuildMessage = optionalString(value.desk_build_message);
  if (deskBuildMessage) {
    result.desk_build_message = deskBuildMessage;
  }
  if (typeof value.desk_reload_recommended === "boolean") {
    result.desk_reload_recommended = value.desk_reload_recommended;
  }
  return result;
}

export function sanitizeFeedbackExportResult(value: unknown): FeedbackExportResult | null {
  if (!isRecord(value) || value.schema_version !== "feedback_export_result_v1" || typeof value.output_path !== "string" || !value.output_path.trim()) {
    return null;
  }
  const outputPath = sanitizeLocalRelativePath(value.output_path);
  if (!outputPath) {
    return null;
  }
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

export function sanitizeFeedbackProfileSuggestionsResult(value: unknown): FeedbackProfileSuggestionsResult | null {
  if (!isRecord(value) || value.schema_version !== "feedback_profile_suggestions_result_v1") {
    return null;
  }
  const createdCount = value.created_count;
  const existingCount = value.existing_count;
  const skippedCount = value.skipped_count;
  if (
    typeof createdCount !== "number" ||
    typeof existingCount !== "number" ||
    typeof skippedCount !== "number" ||
    !Number.isInteger(createdCount) ||
    !Number.isInteger(existingCount) ||
    !Number.isInteger(skippedCount) ||
    createdCount < 0 ||
    existingCount < 0 ||
    skippedCount < 0
  ) {
    return null;
  }
  return {
    schema_version: "feedback_profile_suggestions_result_v1",
    created_count: createdCount,
    existing_count: existingCount,
    skipped_count: skippedCount,
    patch_ids: stringArray(value.patch_ids),
    profile_ids: stringArray(value.profile_ids),
    detail: optionalString(value.detail),
    generated_at: optionalString(value.generated_at),
  };
}

export function sanitizeFeedbackClearResult(value: unknown): FeedbackClearResult | null {
  if (!isRecord(value) || value.schema_version !== "feedback_clear_result_v1") {
    return null;
  }
  const clearedCount = nonNegativeInteger(value.cleared_count);
  if (clearedCount === null) {
    return null;
  }
  return {
    schema_version: "feedback_clear_result_v1",
    cleared_count: clearedCount,
  };
}

export function sanitizeProfileCreateResult(value: unknown): ProfileCreateResult | null {
  if (!isRecord(value) || value.schema_version !== "desk_profile_create_result_v1") {
    return null;
  }
  const profileId = optionalString(value.profile_id);
  const displayName = optionalString(value.display_name);
  const profilePath = optionalString(value.profile_path);
  if (!profileId || !displayName || !profilePath) {
    return null;
  }
  return {
    schema_version: "desk_profile_create_result_v1",
    profile_id: profileId,
    display_name: displayName,
    profile_path: profilePath,
    created: value.created === true,
    detail: optionalString(value.detail) ?? "",
    next_action: optionalString(value.next_action) ?? "",
    created_at: optionalString(value.created_at),
  };
}

export function sanitizeProfileTemplateCatalog(value: unknown): ProfileTemplateCatalog | null {
  if (!isRecord(value) || value.schema_version !== "desk_profile_template_catalog_v1") {
    return null;
  }
  const templates = sanitizeObjectArray(value.templates, "profile_templates.templates").flatMap((record) => {
    const id = optionalString(record.id);
    const title = optionalString(record.title);
    const audience = optionalString(record.audience);
    const defaultTopic = optionalString(record.default_topic);
    const starterBrief = optionalString(record.starter_brief);
    if (!id || !title || !audience || !defaultTopic || !starterBrief) {
      return [];
    }
    return [
      {
        id,
        title,
        audience,
        default_topic: defaultTopic,
        starter_brief: starterBrief,
        coach_questions: stringArray(record.coach_questions),
        supported_fields: stringArray(record.supported_fields),
      },
    ];
  });
  return {
    schema_version: "desk_profile_template_catalog_v1",
    templates,
  };
}

export function sanitizeProfileCreatePreview(value: unknown): ProfileCreatePreview | null {
  if (!isRecord(value) || value.schema_version !== "desk_profile_create_preview_v1") {
    return null;
  }
  const status = optionalString(value.status);
  const templateId = optionalString(value.template_id);
  const title = optionalString(value.title);
  const topic = optionalString(value.topic);
  if (!status || !["ready", "needs_input"].includes(status) || !templateId || !title || !topic) {
    return null;
  }
  return {
    schema_version: "desk_profile_create_preview_v1",
    status,
    template_id: templateId,
    title,
    topic,
    questions: stringArray(value.questions),
    generated_rules: stringArray(value.generated_rules),
    search_rules: stringArray(value.search_rules),
    rejection_rules: stringArray(value.rejection_rules),
    keywords: stringArray(value.keywords),
    markdown_preview: optionalString(value.markdown_preview) ?? "",
    warnings: stringArray(value.warnings),
    llm_used: value.llm_used === true,
  };
}

export function sanitizeProfileCoachPreview(value: unknown): ProfileCoachPreview | null {
  if (!isRecord(value) || value.schema_version !== "profile_coach_preview_v1") {
    return null;
  }
  const status = optionalString(value.status);
  const profileId = optionalString(value.profile_id);
  const confidence = optionalString(value.confidence);
  const evidenceCounts = sanitizeEvidenceCounts(value.evidence_counts);
  if (!status || !profileId || !confidence || !evidenceCounts) {
    return null;
  }
  return {
    schema_version: "profile_coach_preview_v1",
    status,
    profile_id: profileId,
    stage: optionalString(value.stage),
    evidence_counts: evidenceCounts,
    diagnosis: sanitizeProfileCoachDiagnosis(value.diagnosis),
    suspected_false_positive_patterns: stringArray(value.suspected_false_positive_patterns),
    suggested_preference_rules: stringArray(value.suggested_preference_rules),
    source_suggestions: sanitizeProfileCoachSourceSuggestions(value.source_suggestions),
    confidence,
    warnings: stringArray(value.warnings),
    llm_used: value.llm_used === true,
  };
}

function sanitizeEvidenceCounts(value: unknown): Record<string, number> | null {
  if (!isRecord(value)) {
    return null;
  }
  const output: Record<string, number> = {};
  for (const key of ["keep", "skip", "false_positive", "follow_up"]) {
    output[key] = nonNegativeIntegerOrDefault(value[key], 0);
  }
  return output;
}

function sanitizeProfileCoachDiagnosis(value: unknown): ProfileCoachPreview["diagnosis"] {
  return sanitizeObjectArray(value, "profile_coach.diagnosis").flatMap((record) => {
    const label = optionalString(record.label);
    const detail = optionalString(record.detail);
    return label && detail ? [{ label, detail }] : [];
  });
}

function sanitizeProfileCoachSourceSuggestions(value: unknown): ProfileCoachPreview["source_suggestions"] {
  return sanitizeObjectArray(value, "profile_coach.source_suggestions").flatMap((record) => {
    const kind = optionalString(record.kind);
    const label = optionalString(record.label);
    const detail = optionalString(record.detail);
    return kind && label && detail ? [{ kind, label, detail }] : [];
  });
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
  if (!isRecord(value) || value.schema_version !== "desk_action_result_v1") {
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
  const result: DeskActionResult = {
    schema_version: "desk_action_result_v1",
    action_id: actionId,
    status,
    title,
    detail: optionalString(value.detail) ?? "",
    display_command: displayCommand,
    exit_code: exitCode,
    artifact_path: sanitizeOpenableArtifactPath(value.artifact_path),
    next_action: optionalString(value.next_action) ?? "",
    finished_at: optionalString(value.finished_at) ?? "",
  };
  const sourceAccess = sanitizeSourceAccessSummary(value.source_access);
  if (sourceAccess) {
    result.source_access = sourceAccess;
  }
  return result;
}

function sanitizeOpenableArtifactPath(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  const cleaned = sanitizeLocalRelativePath(value);
  if (!cleaned) {
    return "";
  }
  const parts = cleaned.split("/").filter(Boolean);
  const fileName = parts[parts.length - 1] ?? "";
  if (!isDashboardReportArtifactName(fileName)) {
    return "";
  }
  const runIndex = parts.indexOf("runs");
  if (runIndex >= 0) {
    return runIndex < parts.length - 2 ? cleaned : "";
  }
  return parts[0] === "output" && parts.length >= 2 ? cleaned : "";
}

function isDashboardReportArtifactName(value: string): boolean {
  const lower = value.trim().toLowerCase();
  if (lower === "report.html" || lower === "report.md") {
    return true;
  }
  const dotIndex = lower.lastIndexOf(".");
  if (dotIndex < 0) {
    return false;
  }
  const stem = lower.slice(0, dotIndex);
  const suffix = lower.slice(dotIndex);
  return (suffix === ".html" || suffix === ".md") && stem.split("-").some((token) => token === "report" || token === "brief");
}

export function sanitizeDeskSchedulerStatus(value: unknown): DeskSchedulerStatus | null {
  if (!isRecord(value) || value.schema_version !== "desk_scheduler_status_v1") {
    return null;
  }
  const status = optionalString(value.status);
  const taskLabel = optionalString(value.task_label);
  const profileId = optionalString(value.profile_id);
  const displayCommand = optionalString(value.display_command);
  const detail = optionalString(value.detail);
  const nextAction = optionalString(value.next_action);
  const checkedAt = optionalString(value.checked_at);
  const intervalMinutes =
    typeof value.interval_minutes === "number" && Number.isInteger(value.interval_minutes)
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
  if (profileId) {
    sanitized.profile_id = profileId;
  }
  if (displayCommand) {
    sanitized.display_command = displayCommand;
  }
  if (typeof value.last_exit_code === "number" && Number.isInteger(value.last_exit_code)) {
    sanitized.last_exit_code = value.last_exit_code;
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
  if (!isRecord(value) || value.schema_version !== "desk_telegram_status_v1") {
    return null;
  }
  const loginState = optionalString(value.login_state);
  const detail = optionalString(value.detail);
  const nextStep = optionalString(value.next_step);
  const configPath = optionalString(value.config_path);
  const sessionPath = optionalString(value.session_path);
  if (!loginState || !detail || !nextStep || !configPath || !sessionPath) {
    return null;
  }
  const sanitized: DeskTelegramStatus = {
    schema_version: "desk_telegram_status_v1",
    credentials_ready: value.credentials_ready === true,
    session_ready: value.session_ready === true,
    login_state: loginState,
    detail,
    next_step: nextStep,
    config_path: configPath,
    session_path: sessionPath,
  };
  const credentialsStatus = optionalString(value.credentials_status);
  if (credentialsStatus) {
    sanitized.credentials_status = credentialsStatus;
  }
  return sanitized;
}

export function sanitizeDeskNotificationTokenStatus(value: unknown): DeskNotificationTokenStatus | null {
  if (!isRecord(value) || value.schema_version !== "desk_notification_token_status_v1") {
    return null;
  }
  const source = optionalString(value.source);
  const platform = optionalString(value.platform);
  const detail = optionalString(value.detail);
  if (
    !source ||
    !platform ||
    !detail ||
    typeof value.configured !== "boolean" ||
    typeof value.env_configured !== "boolean" ||
    typeof value.local_store_supported !== "boolean" ||
    typeof value.local_store_configured !== "boolean" ||
    typeof value.can_save !== "boolean" ||
    typeof value.can_clear !== "boolean"
  ) {
    return null;
  }
  const sanitized: DeskNotificationTokenStatus = {
    schema_version: "desk_notification_token_status_v1",
    configured: value.configured,
    source,
    updated_at: optionalStringOrNull(value.updated_at),
    env_configured: value.env_configured,
    local_store_supported: value.local_store_supported,
    local_store_configured: value.local_store_configured,
    can_save: value.can_save,
    can_clear: value.can_clear,
    platform,
    detail,
  };
  const verificationStatus = optionalString(value.verification_status);
  if (verificationStatus) {
    sanitized.verification_status = verificationStatus;
  }
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

export function sanitizeDeskBotGatewayStatus(value: unknown): DeskBotGatewayStatus | null {
  if (!isRecord(value) || value.schema_version !== "desk_bot_gateway_status_v1") {
    return null;
  }
  const gatewayStatus = optionalString(value.gateway_status);
  const localFirstNote = optionalString(value.local_first_note);
  const startCommand = optionalString(value.start_command);
  const background = sanitizeDeskBotGatewayBackgroundStatus(value.background);
  if (!gatewayStatus || !localFirstNote || !startCommand || !background) {
    return null;
  }
  const sanitized: DeskBotGatewayStatus = {
    schema_version: "desk_bot_gateway_status_v1",
    token_configured: value.token_configured === true,
    authorized_chat_count: nonNegativeIntegerOrDefault(value.authorized_chat_count, 0),
    gateway_status: gatewayStatus,
    commands_installed: value.commands_installed === true,
    supported_commands: stringArray(value.supported_commands),
    local_first_note: localFirstNote,
    start_command: startCommand,
    background,
  };
  const startedAt = optionalString(value.started_at);
  const lastPollAt = optionalString(value.last_poll_at);
  const lastUpdateAt = optionalString(value.last_update_at);
  const lastError = optionalString(value.last_error);
  const safeNextAction = optionalString(value.safe_next_action);
  if (lastUpdateAt) {
    sanitized.last_update_at = lastUpdateAt;
  }
  if (lastError) {
    sanitized.last_error = lastError;
  }
  if (safeNextAction) {
    sanitized.safe_next_action = safeNextAction;
  }
  if (startedAt) {
    sanitized.started_at = startedAt;
  }
  if (lastPollAt) {
    sanitized.last_poll_at = lastPollAt;
  }
  return sanitized;
}

export function sanitizeDeskBotGatewayBackgroundStatus(value: unknown): DeskBotGatewayStatus["background"] | null {
  if (!isRecord(value) || value.schema_version !== "desk_bot_gateway_background_status_v1") {
    return null;
  }
  const backend = optionalString(value.backend);
  const status = optionalString(value.status);
  const detail = optionalString(value.detail);
  const nextAction = optionalString(value.next_action);
  if (!backend || !status || !detail || !nextAction) {
    return null;
  }
  const sanitized: DeskBotGatewayStatus["background"] = {
    schema_version: "desk_bot_gateway_background_status_v1",
    backend,
    available: value.available === true,
    installed: value.installed === true,
    status,
    can_install: value.can_install === true,
    can_remove: value.can_remove === true,
    detail,
    next_action: nextAction,
  };
  const checkedAt = optionalString(value.checked_at);
  if (checkedAt) {
    sanitized.checked_at = checkedAt;
  }
  return sanitized;
}

export function sanitizeDeskBotIdentityResult(value: unknown): DeskBotIdentityResult | null {
  if (!isRecord(value) || value.schema_version !== "bot_identity_apply_result_v1") {
    return null;
  }
  const name = optionalString(value.name);
  if (!name) {
    return null;
  }
  return {
    schema_version: "bot_identity_apply_result_v1",
    name,
    description_updated: value.description_updated === true,
    short_description_updated: value.short_description_updated === true,
    commands_installed: value.commands_installed === true,
    profile_photo_updated: value.profile_photo_updated === true,
  };
}

export function sanitizeDeskAiSettingsStatus(value: unknown): DeskAiSettingsStatus | null {
  if (!isRecord(value) || value.schema_version !== "desk_ai_settings_status_v1") {
    return null;
  }
  const configuredCount = nonNegativeInteger(value.configured_count);
  const platform = optionalString(value.platform);
  const detail = optionalString(value.detail);
  if (configuredCount === null || typeof value.local_store_supported !== "boolean" || !platform || !detail || !Array.isArray(value.providers)) {
    return null;
  }
  const sanitized: DeskAiSettingsStatus = {
    schema_version: "desk_ai_settings_status_v1",
    configured_count: configuredCount,
    local_store_supported: value.local_store_supported === true,
    platform,
    detail,
    providers: sanitizeDeskAiProviders(value.providers),
    checked_at: optionalString(value.checked_at),
  };
  const matchingConfiguredCount = nonNegativeInteger(value.matching_configured_count);
  const ocrConfiguredCount = nonNegativeInteger(value.ocr_configured_count);
  if (matchingConfiguredCount !== null) {
    sanitized.matching_configured_count = matchingConfiguredCount;
  }
  if (ocrConfiguredCount !== null) {
    sanitized.ocr_configured_count = ocrConfiguredCount;
  }
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

function sanitizeDeskAiProviders(value: unknown): DeskAiProviderStatus[] {
  return sanitizeObjectArray(value, "desk_ai_settings.providers").flatMap((record, index) => {
    const provider = optionalString(record.provider);
    const label = optionalString(record.label);
    const envName = optionalString(record.env_name);
    const source = optionalString(record.source);
    if (!provider || !label || !envName || !source) {
      console.warn(`[tgcs dashboard schema] desk_ai_settings.providers[${index}] missing required field`, record);
      return [];
    }
    const providerStatus: DeskAiProviderStatus = {
      provider,
      label,
      env_name: envName,
      configured: record.configured === true,
      source,
      env_configured: record.env_configured === true,
      local_store_configured: record.local_store_configured === true,
      can_save: record.can_save === true,
      can_clear: record.can_clear === true,
      updated_at: optionalStringOrNull(record.updated_at),
      detail: optionalString(record.detail) ?? "",
    };
    const purpose = optionalString(record.purpose);
    const verificationStatus = optionalString(record.verification_status);
    if (purpose) {
      providerStatus.purpose = purpose;
    }
    if (verificationStatus) {
      providerStatus.verification_status = verificationStatus;
    }
    if ("usable_for_matching" in record) {
      providerStatus.usable_for_matching = record.usable_for_matching === true;
    }
    const localStoreBackend = optionalString(record.local_store_backend);
    const localStoreLabel = optionalString(record.local_store_label);
    if (localStoreBackend) {
      providerStatus.local_store_backend = localStoreBackend;
    }
    if (localStoreLabel) {
      providerStatus.local_store_label = localStoreLabel;
    }
    return [providerStatus];
  });
}

export function sanitizeDeliveryTestResult(value: unknown): DeliveryTestResult | null {
  if (!isRecord(value) || value.schema_version !== "desk_delivery_test_result_v1") {
    return null;
  }
  const targetId = optionalString(value.target_id);
  const targetType = optionalString(value.target_type);
  const status = optionalString(value.status);
  if (!targetId || !targetType || !status) {
    return null;
  }
  return {
    schema_version: "desk_delivery_test_result_v1",
    target_id: targetId,
    target_type: targetType,
    mode: value.mode === "live" ? "live" : "dry-run",
    ok: value.ok === true,
    status,
    title: optionalString(value.title),
    detail: optionalString(value.detail),
    error: optionalString(value.error),
    finished_at: optionalString(value.finished_at),
  };
}

export function sanitizeDeliveryChatDetectionResult(value: unknown): DeliveryChatDetectionResult | null {
  if (!isRecord(value) || value.schema_version !== "desk_delivery_chat_detection_v1") {
    return null;
  }
  const targetId = optionalString(value.target_id);
  const targetType = optionalString(value.target_type);
  const status = optionalString(value.status);
  const source = optionalString(value.source);
  if (!targetId || !targetType || !status || !source) {
    return null;
  }
  return {
    schema_version: "desk_delivery_chat_detection_v1",
    target_id: targetId,
    target_type: targetType,
    ok: value.ok === true,
    status,
    source,
    chat_id: optionalString(value.chat_id) ?? "",
    chat_type: optionalString(value.chat_type) ?? "",
    title: optionalString(value.title),
    detail: optionalString(value.detail),
    finished_at: optionalString(value.finished_at),
  };
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
  return {
    schema_version: value.schema_version === "desk_source_import_result_v1" ? value.schema_version : undefined,
    dry_run: value.dry_run === true,
    written: value.written === true,
    topic,
    added_count: nonNegativeIntegerOrDefault(value.added_count, 0),
    updated_count: nonNegativeIntegerOrDefault(value.updated_count, 0),
    unchanged_count: nonNegativeIntegerOrDefault(value.unchanged_count, 0),
    removed_count: nonNegativeIntegerOrDefault(value.removed_count, 0),
    enabled_count: nonNegativeIntegerOrDefault(value.enabled_count, 0),
    disabled_count: nonNegativeIntegerOrDefault(value.disabled_count, 0),
    source_count: nonNegativeIntegerOrDefault(value.source_count, 0),
    registry_path: registryPath,
    preview_sources: sanitizeSourceImportPreviewSources(value.preview_sources),
    resolved_plan: sanitizeResolvedSourcePlan(value.resolved_plan),
    preview_truncated_count: nonNegativeIntegerOrDefault(value.preview_truncated_count, 0),
    action: optionalString(value.action),
    llm_used: value.llm_used === true,
    title: optionalString(value.title),
    detail: optionalString(value.detail),
    next_action: optionalString(value.next_action),
    finished_at: optionalString(value.finished_at),
  };
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
      console.warn(`[tgcs dashboard schema] desk_sources.sources[${index}] missing required field`, record);
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
    return label && sourceId ? [{ label, source_id: sourceId }] : [];
  });
}
