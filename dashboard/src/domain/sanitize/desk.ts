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
  ProfileCreateResult,
  SourceImportResult,
} from "../types";

export function sanitizeGitUpdateStatus(value: unknown): GitUpdateStatus | null {
  if (!isRecord(value) || value.schema_version !== "git_update_status_v1") {
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

function sanitizeLocalRelativePath(value: string): string | null {
  const cleaned = value.trim().replace(/\\/g, "/");
  if (
    !cleaned ||
    cleaned.startsWith("/") ||
    /^[A-Za-z]:/.test(cleaned) ||
    /^[a-z][a-z0-9+.-]*:\/\//i.test(cleaned) ||
    /[\u0000-\u001F\u007F]/.test(cleaned)
  ) {
    return null;
  }
  const parts = cleaned.split("/").filter(Boolean);
  if (!parts.length || parts.includes("..")) {
    return null;
  }
  return cleaned;
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
  const sourceAccess = sanitizeSourceAccessActionSummary(value.source_access);
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

function sanitizeSourceAccessActionSummary(value: unknown): DeskActionResult["source_access"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const summary: NonNullable<DeskActionResult["source_access"]> = {
    schema_version: value.schema_version === "desk_source_access_health_v1" ? value.schema_version : undefined,
    checked_at: optionalString(value.checked_at) ?? "",
    source_count: nonNegativeIntegerOrDefault(value.source_count, 0),
    checked_count: nonNegativeIntegerOrDefault(value.checked_count, 0),
    accessible_count: nonNegativeIntegerOrDefault(value.accessible_count, 0),
    quiet_count: nonNegativeIntegerOrDefault(value.quiet_count, 0),
    inaccessible_count: nonNegativeIntegerOrDefault(value.inaccessible_count, 0),
    truncated_count: nonNegativeIntegerOrDefault(value.truncated_count, 0),
  };
  assignOptionalNumbers(summary, value, ["probe_window_hours", "probe_window_hours_min", "probe_window_hours_max"]);
  const reasonCounts = sanitizeNumberRecord(value.reason_counts);
  if (reasonCounts) {
    summary.reason_counts = reasonCounts;
  }
  return summary;
}

export function sanitizeDeskSchedulerStatus(value: unknown): DeskSchedulerStatus | null {
  if (!isRecord(value) || value.schema_version !== "desk_scheduler_status_v1") {
    return null;
  }
  const status = optionalString(value.status);
  const taskLabel = optionalString(value.task_label);
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
  return {
    schema_version: "desk_telegram_status_v1",
    credentials_ready: value.credentials_ready === true,
    session_ready: value.session_ready === true,
    login_state: loginState,
    detail,
    next_step: nextStep,
    config_path: configPath,
    session_path: sessionPath,
  };
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
    mode: "dry-run",
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

function sanitizeObjectArray(value: unknown, scope: string): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    if (value !== undefined && value !== null) {
      console.warn(`[tgcs dashboard schema] ${scope} expected array`, value);
    }
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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

function numberOrDefault(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nonNegativeIntegerOrDefault(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : fallback;
}

function nonNegativeInteger(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
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

function sanitizeNumberRecord(value: unknown): Record<string, number> | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const clean = Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1])),
  );
  return Object.keys(clean).length ? clean : undefined;
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
