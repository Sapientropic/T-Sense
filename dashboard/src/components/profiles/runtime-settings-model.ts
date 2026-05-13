import type { ProfileRuntimeSettings } from "../../domain/types";

export const PROFILE_WEEKDAY_OPTIONS = [
  { value: "mon", label: "Mon" },
  { value: "tue", label: "Tue" },
  { value: "wed", label: "Wed" },
  { value: "thu", label: "Thu" },
  { value: "fri", label: "Fri" },
  { value: "sat", label: "Sat" },
  { value: "sun", label: "Sun" },
];

const PROFILE_WEEKDAY_SET = new Set(PROFILE_WEEKDAY_OPTIONS.map((day) => day.value));
const PROFILE_ALERT_RULES = new Set(["high_new_or_changed", "high_new_only"]);

export type RuntimeSettingsDraft = {
  scanWindowText: string;
  itemLimitText: string;
  timezoneText: string;
  workdays: string[];
  workStartText: string;
  workEndText: string;
  workIntervalText: string;
  offHoursIntervalText: string;
  alertRule: string;
  alertMaxAgeText: string;
};

export function runtimeSettingsSaveState(current: ProfileRuntimeSettings, draft: RuntimeSettingsDraft) {
  const settings: ProfileRuntimeSettings = {};
  const scanValue = parseIntegerField(draft.scanWindowText, 1, 168);
  const itemValue = parseIntegerField(draft.itemLimitText, 1, 500);
  const workIntervalValue = parseOptionalIntegerField(draft.workIntervalText, current.work_interval_minutes, 1, 1440);
  const offHoursIntervalValue = parseOptionalIntegerField(draft.offHoursIntervalText, current.off_hours_interval_minutes, 1, 1440);
  const alertMaxAgeValue = parseOptionalIntegerField(draft.alertMaxAgeText, current.alert_max_age_minutes, 1, 10080);
  const timezone = draft.timezoneText.trim();
  const workStart = draft.workStartText.trim();
  const workEnd = draft.workEndText.trim();
  const currentWorkdays = normalizeWeekdays(current.workdays);
  const draftWorkdays = normalizeWeekdays(draft.workdays);
  const hasWorkdayChange = currentWorkdays.join(",") !== draftWorkdays.join(",");
  const timezoneValid = isOptionalTimezoneValid(timezone, current.timezone);
  const workStartValid = isOptionalTimeValid(workStart, current.work_start);
  const workEndValid = isOptionalTimeValid(workEnd, current.work_end);
  const workdaysValid = draftWorkdays.length > 0 || currentWorkdays.length === 0;
  const alertRule = PROFILE_ALERT_RULES.has(draft.alertRule) ? draft.alertRule : "";
  const valid =
    scanValue.valid &&
    itemValue.valid &&
    workIntervalValue.valid &&
    offHoursIntervalValue.valid &&
    alertMaxAgeValue.valid &&
    timezoneValid &&
    workStartValid &&
    workEndValid &&
    workdaysValid &&
    Boolean(alertRule);
  if (scanValue.valid && scanValue.value !== current.scan_window_hours) {
    settings.scan_window_hours = scanValue.value;
  }
  if (itemValue.valid && itemValue.value !== current.semantic_max_messages) {
    settings.semantic_max_messages = itemValue.value;
  }
  if (timezone && timezone !== (current.timezone || "")) {
    settings.timezone = timezone;
  }
  if (hasWorkdayChange && draftWorkdays.length > 0) {
    settings.workdays = draftWorkdays;
  }
  if (workStart && workStart !== (current.work_start || "")) {
    settings.work_start = workStart;
  }
  if (workEnd && workEnd !== (current.work_end || "")) {
    settings.work_end = workEnd;
  }
  if (workIntervalValue.valid && workIntervalValue.value !== undefined && workIntervalValue.value !== current.work_interval_minutes) {
    settings.work_interval_minutes = workIntervalValue.value;
  }
  if (offHoursIntervalValue.valid && offHoursIntervalValue.value !== undefined && offHoursIntervalValue.value !== current.off_hours_interval_minutes) {
    settings.off_hours_interval_minutes = offHoursIntervalValue.value;
  }
  if (alertRule && alertRule !== (current.alert_rule || "high_new_or_changed")) {
    settings.alert_rule = alertRule;
  }
  if (alertMaxAgeValue.valid && alertMaxAgeValue.value !== undefined && alertMaxAgeValue.value !== current.alert_max_age_minutes) {
    settings.alert_max_age_minutes = alertMaxAgeValue.value;
  }
  return {
    canSave: valid && Object.keys(settings).length > 0,
    settings,
  };
}

export function parseIntegerField(text: string, min: number, max: number) {
  const value = Number(text);
  const valid = Number.isInteger(value) && value >= min && value <= max;
  return { valid, value };
}

export function parseOptionalIntegerField(text: string, current: number | undefined, min: number, max: number) {
  const trimmed = text.trim();
  if (!trimmed && current === undefined) {
    return { valid: true, value: undefined };
  }
  const value = Number(trimmed);
  const valid = Number.isInteger(value) && value >= min && value <= max;
  return { valid, value };
}

export function isOptionalTimezoneValid(value: string, current: string | undefined) {
  if (!value && !current) {
    return true;
  }
  return /^[A-Za-z0-9_+\-]+(?:\/[A-Za-z0-9_+\-]+)*$/.test(value) && !value.includes("..") && !value.includes("//");
}

export function isOptionalTimeValid(value: string, current: string | undefined) {
  if (!value && !current) {
    return true;
  }
  if (!/^\d{2}:\d{2}$/.test(value)) {
    return false;
  }
  const [hourText, minuteText] = value.split(":");
  const hour = Number(hourText);
  const minute = Number(minuteText);
  return Number.isInteger(hour) && Number.isInteger(minute) && hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
}

export function normalizeWeekdays(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  const normalized: string[] = [];
  value.forEach((item) => {
    if (typeof item !== "string") {
      return;
    }
    const day = item.trim().toLowerCase().slice(0, 3);
    if (PROFILE_WEEKDAY_SET.has(day) && !normalized.includes(day)) {
      normalized.push(day);
    }
  });
  return normalized;
}
