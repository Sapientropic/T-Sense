import type { MiniAppAuth, MiniAppLearningSummary, MiniAppReviewState, MiniAppSourceRecommendation, ReviewCard, SourceRef } from "../types";
import { isRecord, nonNegativeIntegerOrDefault, optionalString, stringArray } from "./shared";
import { requiredString, stringOrDefault } from "./dashboard-common";

export function sanitizeMiniAppReviewState(value: unknown): MiniAppReviewState {
  const payload = isRecord(value) ? value : {};
  const auth = sanitizeMiniAppAuth(payload.auth);
  const state: MiniAppReviewState = {
    schema_version: payload.schema_version === "miniapp_review_state_v1" ? "miniapp_review_state_v1" : undefined,
    cards: sanitizeMiniAppCards(payload.cards, { includeReportPath: auth?.source === "loopback_preview" }),
  };
  const generatedAt = optionalString(payload.generated_at);
  const setupStatus = sanitizeMiniAppSetupStatus(payload.setup_status);
  const sourceRecommendations = sanitizeMiniAppSourceRecommendations(payload.source_recommendations);
  const learningSummary = sanitizeMiniAppLearningSummary(payload.learning_summary);
  if (auth) {
    state.auth = auth;
  }
  if (generatedAt) {
    state.generated_at = generatedAt;
  }
  if (setupStatus) {
    state.setup_status = setupStatus;
  }
  if (sourceRecommendations.length) {
    state.source_recommendations = sourceRecommendations;
  }
  if (learningSummary) {
    state.learning_summary = learningSummary;
  }
  return state;
}

function sanitizeMiniAppCards(value: unknown, options: { includeReportPath: boolean }): ReviewCard[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((card, index) => {
    if (!isRecord(card)) {
      return [];
    }
    const cardId = requiredString(index, "card_id", card.card_id, "miniapp.cards");
    const profileId = requiredString(index, "profile_id", card.profile_id, "miniapp.cards");
    const title = requiredString(index, "title", card.title, "miniapp.cards");
    if (!cardId || !profileId || !title) {
      return [];
    }
    const result: ReviewCard = {
      schema_version: "review_card_v1",
      card_id: cardId,
      profile_id: profileId,
      title,
      rating: stringOrDefault(card.rating, "unknown"),
      decision_status: stringOrDefault(card.decision_status, "unknown"),
      source_refs: sanitizeMiniAppSourceRefs(card.source_refs),
      item: sanitizeMiniAppItem(card.item),
      status: stringOrDefault(card.status, "pending"),
      opportunity_status: stringOrDefault(card.opportunity_status, "open"),
      opportunity_updated_at: stringOrDefault(card.opportunity_updated_at, ""),
      updated_at: stringOrDefault(card.updated_at, ""),
    };
    const alertSummary = sanitizeMiniAppAlertSummary(card.alert_summary);
    const reportPath = options.includeReportPath ? sanitizeMiniAppReportPath(card.report_path) : undefined;
    if (alertSummary) {
      result.alert_summary = alertSummary;
    }
    if (reportPath) {
      result.report_path = reportPath;
    }
    return [result];
  });
}

function sanitizeMiniAppItem(value: unknown): ReviewCard["item"] {
  if (!isRecord(value)) {
    return {};
  }
  const item: ReviewCard["item"] = {};
  const why = optionalString(value.why);
  const sourceExcerpt = optionalString(value.source_excerpt);
  const decisionState = sanitizeMiniAppDecisionState(value.decision_state);
  if (why) {
    item.why = why;
  }
  if (sourceExcerpt) {
    item.source_excerpt = sourceExcerpt;
  }
  if (decisionState) {
    item.decision_state = decisionState;
  }
  return item;
}

function sanitizeMiniAppDecisionState(value: unknown): ReviewCard["item"]["decision_state"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const state: NonNullable<ReviewCard["item"]["decision_state"]> = {};
  for (const field of ["status", "first_seen_at", "last_seen_at"] as const) {
    const text = optionalString(value[field]);
    if (text) {
      state[field] = text;
    }
  }
  if (typeof value.seen_count === "number" && Number.isFinite(value.seen_count)) {
    state.seen_count = value.seen_count;
  }
  const signals = stringArray(value.signals);
  if (signals.length) {
    state.signals = signals;
  }
  const materialChangeFields = stringArray(value.material_change_fields);
  if (materialChangeFields.length) {
    state.material_change_fields = materialChangeFields;
  }
  return Object.keys(state).length ? state : undefined;
}

function sanitizeMiniAppSourceRefs(value: unknown): SourceRef[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((ref) => {
    if (!isRecord(ref) || typeof ref.channel !== "string" || (typeof ref.id !== "string" && typeof ref.id !== "number")) {
      return [];
    }
    const cleanRef: SourceRef = { channel: ref.channel, id: ref.id };
    const url = optionalTelegramUrl(ref.url);
    if (url) {
      cleanRef.url = url;
    }
    return [cleanRef];
  });
}

function sanitizeMiniAppSourceRecommendations(value: unknown): MiniAppSourceRecommendation[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((recommendation) => {
    if (!isRecord(recommendation)) {
      return [];
    }
    const sourceId = optionalString(recommendation.source_id);
    const channel = optionalString(recommendation.channel);
    const label = optionalString(recommendation.label);
    const topic = optionalString(recommendation.topic);
    if (!sourceId || !channel || !label || !topic) {
      return [];
    }
    return [
      {
        schema_version:
          recommendation.schema_version === "miniapp_source_recommendation_v1"
            ? "miniapp_source_recommendation_v1"
            : undefined,
        source_id: sourceId,
        channel,
        label,
        topic,
        reason: optionalString(recommendation.reason) || "",
        installed: typeof recommendation.installed === "boolean" ? recommendation.installed : false,
      },
    ];
  });
}

function sanitizeMiniAppAlertSummary(value: unknown): ReviewCard["alert_summary"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const alertCount = nonNegativeIntegerOrDefault(value.alert_count, 0);
  if (alertCount <= 0) {
    return undefined;
  }
  const summary: NonNullable<ReviewCard["alert_summary"]> = {
    schema_version: value.schema_version === "review_card_alert_summary_v1" ? "review_card_alert_summary_v1" : undefined,
    alert_count: alertCount,
  };
  for (const field of ["latest_status", "latest_delivery_mode", "latest_delivery_status", "latest_alerted_at"] as const) {
    const text = optionalString(value[field]);
    if (text) {
      summary[field] = text;
    }
  }
  if (typeof value.latest_delivery_ok === "boolean") {
    summary.latest_delivery_ok = value.latest_delivery_ok;
  }
  return summary;
}

function sanitizeMiniAppLearningSummary(value: unknown): MiniAppLearningSummary | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const summary: MiniAppLearningSummary = {
    schema_version: value.schema_version === "miniapp_learning_summary_v1" ? "miniapp_learning_summary_v1" : undefined,
    current_decision_count: nonNegativeIntegerOrDefault(value.current_decision_count, 0),
    exportable_count: nonNegativeIntegerOrDefault(value.exportable_count, 0),
    non_exportable_follow_up_count: nonNegativeIntegerOrDefault(value.non_exportable_follow_up_count, 0),
    pending_profile_diff_count: nonNegativeIntegerOrDefault(value.pending_profile_diff_count, 0),
    applied_profile_diff_count: nonNegativeIntegerOrDefault(value.applied_profile_diff_count, 0),
    changed_since_last_export: typeof value.changed_since_last_export === "boolean" ? value.changed_since_last_export : false,
  };
  const nextAction = sanitizeMiniAppLearningAction(value.next_action);
  const calibrationNextAction = sanitizeMiniAppLearningAction(value.calibration_next_action);
  if (nextAction) {
    summary.next_action = nextAction;
  }
  if (calibrationNextAction) {
    summary.calibration_next_action = calibrationNextAction;
  }
  return summary;
}

function sanitizeMiniAppLearningAction(value: unknown): MiniAppLearningSummary["next_action"] | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const action = {
    label: optionalString(value.label),
    detail: optionalString(value.detail),
  };
  return Object.values(action).some(Boolean) ? action : undefined;
}

function sanitizeMiniAppReportPath(value: unknown) {
  const text = optionalString(value);
  if (!text) {
    return undefined;
  }
  const cleaned = text.replace(/\\/g, "/");
  const parts = cleaned.split("/").filter(Boolean);
  if (cleaned.startsWith("/") || /^[A-Za-z]:/.test(cleaned) || /^[a-z][a-z0-9+.-]*:\/\//i.test(cleaned) || parts.includes("..")) {
    return undefined;
  }
  return parts[0] === "output" && parts.length >= 2 && isReportArtifactName(parts[parts.length - 1] ?? "") ? cleaned : undefined;
}

function isReportArtifactName(value: string) {
  const lower = value.toLowerCase();
  return lower === "report.html" || lower === "report.md" || (/\.(html|md)$/.test(lower) && lower.split(".")[0].split("-").includes("report"));
}

function optionalTelegramUrl(value: unknown) {
  const text = optionalString(value);
  if (!text) {
    return undefined;
  }
  try {
    const parsed = new URL(text);
    return parsed.protocol === "https:" && parsed.hostname.toLowerCase() === "t.me" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}

function sanitizeMiniAppAuth(value: unknown): MiniAppAuth | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const auth: MiniAppAuth = {
    schema_version: value.schema_version === "telegram_miniapp_auth_v1" ? "telegram_miniapp_auth_v1" : undefined,
    source: optionalString(value.source),
  };
  const userId = optionalString(value.user_id);
  if (userId) {
    auth.user_id = userId;
  }
  return Object.values(auth).some(Boolean) ? auth : undefined;
}

function sanitizeMiniAppSetupStatus(value: unknown): MiniAppReviewState["setup_status"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const setup = {
    stage: optionalString(value.stage),
    next_step: optionalString(value.next_step),
    has_runs: typeof value.has_runs === "boolean" ? value.has_runs : undefined,
    has_profiles: typeof value.has_profiles === "boolean" ? value.has_profiles : undefined,
    has_user_goal: typeof value.has_user_goal === "boolean" ? value.has_user_goal : undefined,
  };
  return Object.values(setup).some((item) => item !== undefined && item !== "") ? setup : undefined;
}
