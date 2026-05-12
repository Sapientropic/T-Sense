import {
  sanitizeDashboardState,
  sanitizeDeskAiSettingsStatus,
  sanitizeDeskActions,
  sanitizeDeskActionResult,
  sanitizeDeskNotificationTokenStatus,
  sanitizeDeskSchedulerStatus,
  sanitizeDeskSourcesResult,
  sanitizeDeskTelegramStatus,
  sanitizeDeliveryChatDetectionResult,
  sanitizeDeliveryTestResult,
  sanitizeFeedbackExportResult,
  sanitizeFeedbackProfileSuggestionsResult,
  sanitizeGitUpdateStatus,
  sanitizeProfileCreateResult,
  sanitizeSourceImportResult,
} from "../domain/sanitize";
import type {
  DashboardState,
  DeskAction,
  DeskActionResult,
  DeskAiSettingsStatus,
  DeskNotificationTokenStatus,
  DeskSchedulerStatus,
  DeskSourcesResult,
  DeskTelegramStatus,
  DeliveryChatDetectionResult,
  DeliveryTarget,
  DeliveryTestResult,
  FeedbackExportResult,
  FeedbackProfileSuggestionsResult,
  GitUpdateStatus,
  ProfileCreateResult,
  SourceImportResult,
} from "../domain/types";

export async function loadDashboardState(signal?: AbortSignal): Promise<DashboardState> {
  const response = await fetch("/api/state", { signal });
  await assertOk(response);
  const payload = await response.json();
  assertDashboardStatePayload(payload);
  return sanitizeDashboardState(payload);
}

export async function postReviewCardAction(cardId: string, action: string, note = "") {
  const response = await fetch(`/api/review-cards/${encodeURIComponent(cardId)}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, note }),
  });
  await assertOk(response);
}

export async function undoReviewCardAction(cardId: string) {
  const response = await fetch(`/api/review-cards/${encodeURIComponent(cardId)}/undo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  await assertOk(response);
}

export async function applyProfilePatch(patchId: string) {
  const response = await fetch(`/api/profile-patches/${encodeURIComponent(patchId)}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  await assertOk(response);
}

export async function revertProfilePatch(patchId: string) {
  const response = await fetch(`/api/profile-patches/${encodeURIComponent(patchId)}/revert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  await assertOk(response);
}

export async function setProfileAlertMode(profileId: string, mode: string) {
  const response = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/alert-mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  await assertOk(response);
}

export async function setProfileEnabled(profileId: string, enabled: boolean) {
  const response = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/enabled`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  await assertOk(response);
}

export async function setProfileRuntimeSettings(
  profileId: string,
  settings: { scan_window_hours?: number; semantic_max_messages?: number },
) {
  const response = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/runtime-settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  await assertOk(response);
}

export async function createProfileDraftNote(profileId: string, note: string) {
  const response = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/draft-note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  await assertOk(response);
}

export async function createProfileMatchingPreferencesDraft(profileId: string, preferences: string) {
  const response = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/matching-preferences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preferences }),
  });
  await assertOk(response);
}

export async function createProfileFromBrief(payload: {
  brief: string;
  source_filename?: string;
  source_text?: string;
  source_base64?: string;
}): Promise<ProfileCreateResult> {
  const resultPayload = await postJson("/api/profiles/create", payload);
  const result = sanitizeProfileCreateResult(resultPayload.profile);
  if (!result) {
    throw new Error("Invalid profile creation response");
  }
  return result;
}

export async function checkGitUpdates(): Promise<GitUpdateStatus> {
  const payload = await postJson("/api/git/check-updates", {});
  const git = sanitizeGitUpdateStatus(payload.git);
  if (!git) {
    throw new Error("Invalid git status response");
  }
  return git;
}

export async function pullLatestGit(): Promise<GitUpdateStatus> {
  const payload = await postJson("/api/git/pull-latest", { confirm: true });
  const git = sanitizeGitUpdateStatus(payload.git);
  if (!git) {
    throw new Error("Invalid git status response");
  }
  return git;
}

export async function exportFeedback(): Promise<FeedbackExportResult> {
  const payload = await postJson("/api/feedback/export", {});
  const result = sanitizeFeedbackExportResult(payload.export);
  if (!result) {
    throw new Error("Invalid feedback export response");
  }
  return result;
}

export async function generateFeedbackProfileSuggestions(): Promise<FeedbackProfileSuggestionsResult> {
  const payload = await postJson("/api/feedback/profile-suggestions", {});
  const result = sanitizeFeedbackProfileSuggestionsResult(payload.suggestions);
  if (!result) {
    throw new Error("Invalid feedback profile suggestions response");
  }
  return result;
}

export async function clearFeedbackDecisions(): Promise<number> {
  const payload = await postJson("/api/feedback/clear", {});
  const feedback = payload.feedback as Record<string, unknown> | undefined;
  if (!feedback || typeof feedback !== "object" || typeof feedback.cleared_count !== "number") {
    throw new Error("Invalid feedback clear response");
  }
  return feedback.cleared_count;
}

export async function loadDeskActions(signal?: AbortSignal): Promise<DeskAction[]> {
  const response = await fetch("/api/desk/actions", { signal });
  const payload = await readJson(response);
  assertDeskActionsPayload(payload);
  return sanitizeDeskActions(payload);
}

export async function loadDeskSchedulerStatus(signal?: AbortSignal): Promise<DeskSchedulerStatus> {
  const response = await fetch("/api/desk/scheduler-status", { signal });
  const payload = await readJson(response);
  const result = sanitizeDeskSchedulerStatus(payload.scheduler);
  if (!result) {
    throw new Error("Invalid scheduler status response");
  }
  return result;
}

export async function loadDeskNotificationTokenStatus(signal?: AbortSignal): Promise<DeskNotificationTokenStatus> {
  const response = await fetch("/api/desk/notification-token/status", { signal });
  const payload = await readJson(response);
  const result = sanitizeDeskNotificationTokenStatus(payload.token);
  if (!result) {
    throw new Error("Invalid notification token response");
  }
  return result;
}

export async function loadDeskAiSettingsStatus(signal?: AbortSignal): Promise<DeskAiSettingsStatus> {
  const response = await fetch("/api/desk/ai-settings/status", { signal });
  const payload = await readJson(response);
  const result = sanitizeDeskAiSettingsStatus(payload.ai);
  if (!result) {
    throw new Error("Invalid AI API settings response");
  }
  return result;
}

export async function saveDeskAiApiKey(provider: string, apiKey: string): Promise<DeskAiSettingsStatus> {
  const payload = await postJson("/api/desk/ai-settings", { provider, api_key: apiKey });
  const result = sanitizeDeskAiSettingsStatus(payload.ai);
  if (!result) {
    throw new Error("Invalid AI API settings response");
  }
  return result;
}

export async function clearDeskAiApiKey(provider: string): Promise<DeskAiSettingsStatus> {
  const payload = await postJson("/api/desk/ai-settings", { provider, clear: true });
  const result = sanitizeDeskAiSettingsStatus(payload.ai);
  if (!result) {
    throw new Error("Invalid AI API settings response");
  }
  return result;
}

export async function saveDeskNotificationToken(token: string): Promise<DeskNotificationTokenStatus> {
  const payload = await postJson("/api/desk/notification-token", { token });
  const result = sanitizeDeskNotificationTokenStatus(payload.token);
  if (!result) {
    throw new Error("Invalid notification token response");
  }
  return result;
}

export async function clearDeskNotificationToken(): Promise<DeskNotificationTokenStatus> {
  const payload = await postJson("/api/desk/notification-token", { clear: true });
  const result = sanitizeDeskNotificationTokenStatus(payload.token);
  if (!result) {
    throw new Error("Invalid notification token response");
  }
  return result;
}

export async function loadDeskSources(signal?: AbortSignal): Promise<DeskSourcesResult> {
  const response = await fetch("/api/desk/sources", { signal });
  const payload = await readJson(response);
  return readDeskSourcesResult(payload.sources);
}

export async function runDeskAction(
  actionId: string,
  body: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<DeskActionResult> {
  const payload = await postJson(`/api/desk/actions/${encodeURIComponent(actionId)}/run`, body, signal);
  const result = sanitizeDeskActionResult(payload.result);
  if (!result) {
    throw new Error("Invalid Desk action response");
  }
  return result;
}

export async function loadDeskTelegramStatus(signal?: AbortSignal): Promise<DeskTelegramStatus> {
  const response = await fetch("/api/desk/telegram-status", { signal });
  const payload = await readJson(response);
  const result = sanitizeDeskTelegramStatus(payload.telegram);
  if (!result) {
    throw new Error("Invalid Telegram status response");
  }
  return result;
}

export async function saveDeskTelegramCredentials(apiId: string, apiHash: string): Promise<DeskTelegramStatus> {
  const payload = await postJson("/api/desk/telegram-credentials", { api_id: apiId, api_hash: apiHash });
  const result = sanitizeDeskTelegramStatus(payload.telegram);
  if (!result) {
    throw new Error("Invalid Telegram credentials response");
  }
  return result;
}

export async function sendDeskTelegramCode(phone: string): Promise<DeskTelegramStatus> {
  const payload = await postJson("/api/desk/telegram-login/send-code", { phone });
  const result = sanitizeDeskTelegramStatus(payload.telegram);
  if (!result) {
    throw new Error("Invalid Telegram login response");
  }
  return result;
}

export async function verifyDeskTelegramCode(code: string, password = ""): Promise<DeskTelegramStatus> {
  const payload = await postJson("/api/desk/telegram-login/verify-code", { code, password });
  const result = sanitizeDeskTelegramStatus(payload.telegram);
  if (!result) {
    throw new Error("Invalid Telegram login response");
  }
  return result;
}

export async function cancelDeskTelegramLogin(): Promise<DeskTelegramStatus> {
  const payload = await postJson("/api/desk/telegram-login/cancel", {});
  const result = sanitizeDeskTelegramStatus(payload.telegram);
  if (!result) {
    throw new Error("Invalid Telegram login response");
  }
  return result;
}

export async function saveDeskDeliveryTarget(
  targetId: string,
  chatId: string,
  enabled: boolean,
): Promise<DeliveryTarget> {
  const payload = await postJson(`/api/desk/delivery-targets/${encodeURIComponent(targetId)}`, {
    chat_id: chatId,
    enabled,
  });
  const state = sanitizeDashboardState({ delivery_targets: [payload.target] });
  const target = state.delivery_targets[0];
  if (!target) {
    throw new Error("Invalid notification target response");
  }
  return target;
}

export async function testDeskDeliveryTarget(targetId: string, chatId: string): Promise<DeliveryTestResult> {
  const payload = await postJson(`/api/desk/delivery-targets/${encodeURIComponent(targetId)}/test`, { chat_id: chatId });
  const result = sanitizeDeliveryTestResult(payload.result);
  if (!result) {
    throw new Error("Invalid notification test response");
  }
  return result;
}

export async function detectDeskDeliveryChatId(targetId: string): Promise<DeliveryChatDetectionResult> {
  const payload = await postJson(`/api/desk/delivery-targets/${encodeURIComponent(targetId)}/detect-chat-id`, {});
  const result = sanitizeDeliveryChatDetectionResult(payload.result);
  if (!result) {
    throw new Error("Invalid notification chat detection response");
  }
  return result;
}

export async function previewDeskSourceImport(sources: string, topic: string): Promise<SourceImportResult> {
  const payload = await postJson("/api/desk/sources/preview", { sources, topic });
  return readSourceImportResult(payload.result, "Invalid source preview response");
}

export async function importDeskSources(sources: string, topic: string): Promise<SourceImportResult> {
  const payload = await postJson("/api/desk/sources/import", { sources, topic });
  return readSourceImportResult(payload.result, "Invalid source import response");
}

export async function importStarterSources(topic: string): Promise<SourceImportResult> {
  const payload = await postJson("/api/desk/sources/starter", { topic });
  return readSourceImportResult(payload.result, "Invalid starter source response");
}

export async function previewSourceAssistant(
  instruction: string,
  topic: string,
  confirmExternalAi = false,
): Promise<SourceImportResult> {
  const payload = await postJson("/api/desk/sources/assistant", {
    instruction,
    topic,
    dry_run: true,
    confirm_external_ai: confirmExternalAi,
  });
  return readSourceImportResult(payload.result, "Invalid source assistant response");
}

export async function applySourceAssistant(
  instruction: string,
  topic: string,
  confirmExternalAi = false,
  resolvedPlan?: SourceImportResult["resolved_plan"],
): Promise<SourceImportResult> {
  const payload = await postJson("/api/desk/sources/assistant", {
    instruction,
    topic,
    dry_run: false,
    confirm_external_ai: confirmExternalAi,
    ...(resolvedPlan ? { resolved_plan: resolvedPlan } : {}),
  });
  return readSourceImportResult(payload.result, "Invalid source assistant response");
}

export async function setDeskSourceEnabled(sourceId: string, enabled: boolean): Promise<DeskSourcesResult> {
  const payload = await postJson(`/api/desk/sources/${encodeURIComponent(sourceId)}/enabled`, { enabled });
  return readDeskSourcesResult(payload.sources);
}

export async function removeDeskSource(sourceId: string): Promise<DeskSourcesResult> {
  const payload = await postJson(`/api/desk/sources/${encodeURIComponent(sourceId)}/remove`, { confirm: true });
  return readDeskSourcesResult(payload.sources);
}

export async function setDeskSourceTopics(sourceId: string, topics: string[]): Promise<DeskSourcesResult> {
  assertDeskSourceTopics(topics);
  const payload = await postJson(`/api/desk/sources/${encodeURIComponent(sourceId)}/topics`, { topics });
  return readDeskSourcesResult(payload.sources);
}

function readDeskSourcesResult(value: unknown): DeskSourcesResult {
  assertSchemaVersion(value, "desk_sources_v1", "Invalid source library response");
  const result = sanitizeDeskSourcesResult(value);
  if (!result) {
    throw new Error("Invalid source library response");
  }
  return result;
}

function readSourceImportResult(value: unknown, message: string): SourceImportResult {
  assertSchemaVersion(value, "desk_source_import_result_v1", message);
  const result = sanitizeSourceImportResult(value);
  if (!result) {
    throw new Error(message);
  }
  return result;
}

function assertDeskSourceTopics(topics: string[]) {
  if (!Array.isArray(topics) || topics.length < 1 || topics.length > 8) {
    throw new Error("Use 1 to 8 topic tags.");
  }
  for (const topic of topics) {
    if (typeof topic !== "string" || !/^[a-z0-9][a-z0-9_-]{1,40}$/.test(topic)) {
      throw new Error("Use short topic tags like jobs or remote-work.");
    }
  }
}

async function postJson(path: string, body: Record<string, unknown>, signal?: AbortSignal) {
  return readJson(
    await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    }),
  );
}

async function assertOk(response: Response) {
  if (response.ok) {
    return;
  }
  let detail = response.statusText;
  try {
    const payload = await response.json();
    if (payload && typeof payload.error === "string") {
      detail = payload.error;
    }
  } catch {
    // Keep the HTTP status text when the server did not return JSON.
  }
  throw new Error(detail || `HTTP ${response.status}`);
}

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof payload.error === "string" ? payload.error : response.statusText || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function assertDashboardStatePayload(value: unknown): asserts value is Record<string, unknown> {
  if (!isRecord(value) || value.schema_version !== "dashboard_state_v1") {
    throw new Error("Invalid dashboard state response");
  }
  const requiredArrayFields = [
    "profiles",
    "inbox",
    "runs",
    "delivery_targets",
    "profile_patch_suggestions",
    "source_stats",
    "source_insights",
  ];
  for (const field of requiredArrayFields) {
    if (!Array.isArray(value[field])) {
      throw new Error("Invalid dashboard state response");
    }
  }
}

function assertDeskActionsPayload(value: unknown): asserts value is Record<string, unknown> {
  if (!isRecord(value) || value.schema_version !== "desk_actions_v1" || !Array.isArray(value.actions)) {
    throw new Error("Invalid Desk actions response");
  }
}

function assertSchemaVersion(value: unknown, schemaVersion: string, message: string): asserts value is Record<string, unknown> {
  if (!isRecord(value) || value.schema_version !== schemaVersion) {
    throw new Error(message);
  }
}

export function errorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  return normalizeDashboardError(message);
}

export function normalizeDashboardError(message: string) {
  const text = message.trim();
  if (!text) {
    return "Signal Desk hit an unknown local error. Refresh once; if it repeats, restart the dashboard server.";
  }
  if (/failed to fetch|networkerror|load failed/i.test(text)) {
    return "Local dashboard API is unreachable. Start or restart Signal Desk, then refresh.";
  }
  if (/internal server error|http 500/i.test(text)) {
    return "Local dashboard API hit an internal error. Refresh once; if it repeats, restart Signal Desk.";
  }
  if (/invalid .* response/i.test(text)) {
    return "Local dashboard API returned data this screen cannot read. Refresh once; if it repeats, restart Signal Desk.";
  }
  return text;
}
