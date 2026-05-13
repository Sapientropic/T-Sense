import type { ReviewCard } from "../types";
import { assignOptionalNumbers, isRecord, optionalString, optionalStringOrNull, sanitizeStringRecord, stringArray } from "./shared";
import { assignOptionalStrings, requiredString, sanitizeSourceRefs, stringOrDefault } from "./dashboard-common";

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
  warnUnexpectedInboxField(index, "opportunity_status", record.opportunity_status);
  warnUnexpectedInboxField(index, "opportunity_updated_at", record.opportunity_updated_at);
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
    opportunity_status: stringOrDefault(record.opportunity_status, "open"),
    opportunity_updated_at: stringOrDefault(record.opportunity_updated_at, ""),
    updated_at: stringOrDefault(record.updated_at, ""),
  };
  const firstRunId = optionalString(record.first_run_id);
  const lastRunId = optionalString(record.last_run_id);
  const reportPath = optionalString(record.report_path);
  const dashboardUrl = optionalString(record.dashboard_url);
  const duplicateOfCardId = optionalStringOrNull(record.duplicate_of_card_id);
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
  if (duplicateOfCardId !== undefined) {
    sanitized.duplicate_of_card_id = duplicateOfCardId;
  }
  return sanitized;
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


function sanitizeDecisionState(value: unknown): ReviewCard["item"]["decision_state"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const decisionState: NonNullable<ReviewCard["item"]["decision_state"]> = {};
  assignOptionalStrings(decisionState, value, ["status", "first_seen_at", "last_seen_at"]);
  assignOptionalNumbers(decisionState, value, ["seen_count"]);
  const signals = stringArray(value.signals);
  if (signals.length) {
    decisionState.signals = signals;
  }
  const materialChangeFields = stringArray(value.material_change_fields);
  if (materialChangeFields.length) {
    decisionState.material_change_fields = materialChangeFields;
  }
  const explanations = sanitizeStringRecord(
    value.explanations,
    PRIVATE_STRING_RECORD_KEYS,
    PRIVATE_STRING_RECORD_SUFFIXES,
  );
  if (explanations) {
    decisionState.explanations = explanations;
  }
  return Object.keys(decisionState).length ? decisionState : undefined;
}

const PRIVATE_STRING_RECORD_KEYS = new Set([
  "api_key",
  "argv",
  "authorization",
  "bot_token",
  "command",
  "cookie",
  "cookies",
  "cwd",
  "env",
  "environment",
  "headers",
  "password",
  "path",
  "profile_path",
  "raw",
  "raw_text",
  "request",
  "response",
  "scan_path",
  "secret",
  "session",
  "session_path",
  "token",
]);

const PRIVATE_STRING_RECORD_SUFFIXES = ["_api_key", "_client_secret", "_password", "_secret", "_session_path", "_token"];

function warnUnexpectedInboxField(index: number, field: string, value: unknown) {
  if (value === null || value === undefined || typeof value === "string") {
    return;
  }
  console.warn(`[tgcs dashboard schema] inbox[${index}].${field} expected string/null/undefined`, value);
}
