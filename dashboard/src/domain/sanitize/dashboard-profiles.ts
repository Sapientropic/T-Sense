import type { Profile, ProfilePatch } from "../types";
import { assignOptionalNumbers, isRecord, optionalString, sanitizeObjectArray, stringArray } from "./shared";
import { assignOptionalStrings, requiredString, stringOrDefault } from "./dashboard-common";

export function sanitizeProfiles(value: unknown): Profile[] {
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
    assignOptionalStrings(profile, record, [
      "display_name",
      "report_display_name",
      "display_path",
      "alert_schedule_mode",
      "timezone",
      "work_start",
      "work_end",
      "alert_rule",
    ]);
    const sourceTopics = stringArray(record.source_topics);
    if (sourceTopics.length) {
      profile.source_topics = sourceTopics;
    }
    const workdays = stringArray(record.workdays);
    if (workdays.length) {
      profile.workdays = workdays;
    }
    assignOptionalNumbers(profile, record, [
      "scan_window_hours",
      "semantic_max_messages",
      "work_interval_minutes",
      "off_hours_interval_minutes",
      "alert_max_age_minutes",
      "delivery_target_count",
    ]);
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

export function sanitizeProfilePatches(value: unknown): ProfilePatch[] {
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
      "replayed_from_patch_id",
      "applied_at",
    ]);
    const applyReadiness = sanitizeApplyReadiness(record.apply_readiness);
    if (applyReadiness) {
      patch.apply_readiness = applyReadiness;
    }
    return [patch];
  });
}

function sanitizeApplyReadiness(value: unknown): ProfilePatch["apply_readiness"] {
  if (!isRecord(value)) {
    return undefined;
  }
  const readiness: NonNullable<ProfilePatch["apply_readiness"]> = {};
  assignOptionalStrings(readiness, value, ["status", "label", "detail"]);
  return Object.keys(readiness).length ? readiness : undefined;
}
