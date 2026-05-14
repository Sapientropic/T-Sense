import { Bell, BellOff, CirclePause, CirclePlay, Save, Sun, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { alertMode } from "../../domain/display";
import { profileDisplayName } from "../../domain/format";
import type { Profile, ProfileRuntimeSettings } from "../../domain/types";
import { ProfileHelpTip } from "./profile-help-tip";
import {
  profileItemLimitLabel,
  profileNotificationLabel,
  profileScanWindowLabel,
  profileTopicLabel,
} from "./profile-labels";
import { ProfileMatchingPanel } from "./profile-matching-panel";
import {
  PROFILE_WEEKDAY_OPTIONS,
  detectedBrowserTimezone,
  isOptionalTimeValid,
  isOptionalTimezoneValid,
  normalizeWeekdays,
  parseOptionalIntegerField,
  timezoneOptions,
} from "./runtime-settings-model";

export function ProfileRow({
  profile,
  setAlertMode,
  setProfileEnabled,
  setProfileRuntimeSettings,
  deleteProfile,
  createProfileMatchingPreferencesDraft,
  busy,
}: {
  profile: Profile;
  setAlertMode: (profileId: string, mode: string) => void;
  setProfileEnabled: (profileId: string, enabled: boolean) => void;
  setProfileRuntimeSettings: (profileId: string, settings: ProfileRuntimeSettings) => void;
  deleteProfile: (profileId: string) => void;
  createProfileMatchingPreferencesDraft: (profileId: string, preferences: string) => Promise<void>;
  busy: boolean;
}) {
  const [open, setOpen] = useState(() => shouldOpenProfileByDefault());
  const [confirmDelete, setConfirmDelete] = useState(false);
  const profileName = profile.display_name || profileDisplayName(profile.profile_id);
  return (
    <details
      className={`table-row profile-row ${profile.enabled ? "" : "paused"}`}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary className="profile-summary" aria-label={`${profileName} profile summary`}>
        <span className="profile-summary-title">
          <strong>{profileName}</strong>
          <span className={profile.enabled ? "status enabled" : "status disabled"}>
            {profile.enabled ? "Monitoring" : "Paused"}
          </span>
        </span>
        <span className="profile-summary-meta" aria-label={`Quick settings for ${profileName}`}>
          <span>{profileScanWindowLabel(profile)}</span>
          <span>{profileItemLimitLabel(profile)}</span>
          <span>{profileTopicLabel(profile)}</span>
        </span>
        <span className="profile-summary-toggle">{open ? "Collapse" : "View / edit"}</span>
      </summary>
      <div className="profile-row-body">
        <ProfileMatchingPanel
          profile={profile}
          busy={busy}
          createProfileMatchingPreferencesDraft={createProfileMatchingPreferencesDraft}
        />
        <div className="profile-rhythm" aria-label={`Profile settings for ${profileName}`}>
          <span title="How far back each scan checks">{profileScanWindowLabel(profile)}</span>
          <span title="Maximum messages reviewed per scan">{profileItemLimitLabel(profile)}</span>
          <span title="Source group used by this monitor">{profileTopicLabel(profile)}</span>
          <span title="Notification destinations configured">{profileNotificationLabel(profile)}</span>
        </div>
        <div className="profile-control-groups">
          <div className="profile-control-group">
            <span className="profile-control-label">Monitoring</span>
            <ProfileEnabledControl profile={profile} setProfileEnabled={setProfileEnabled} busy={busy} />
          </div>
          <div className="profile-control-group">
            <span className="profile-control-label">
              Notifications
              <ProfileHelpTip text="Choose when this profile can notify you. This does not change what Signal Desk scans." />
            </span>
            <AlertModeControl profile={profile} setAlertMode={setAlertMode} busy={busy} />
            <NotificationDetailsControl
              busy={busy}
              profile={profile}
              setProfileRuntimeSettings={setProfileRuntimeSettings}
            />
            {!profile.enabled && <span className="profile-paused-note">Resume monitoring to adjust alerts.</span>}
          </div>
        </div>
        <div className="profile-row-actions" data-confirming-delete={confirmDelete ? "true" : "false"}>
          <div className="profile-delete-zone" data-confirming={confirmDelete ? "true" : "false"}>
            {confirmDelete ? (
              <>
                <div>
                  <strong>Delete {profileName}?</strong>
                  <span>This removes the profile from Signal Desk and clears its current Review cards. Run history stays available.</span>
                </div>
                <button className="profile-delete-confirm text-button danger" disabled={busy} onClick={() => deleteProfile(profile.profile_id)} type="button">
                  <Trash2 size={15} />
                  <span>Delete profile</span>
                </button>
                <button className="profile-delete-cancel text-button secondary" disabled={busy} onClick={() => setConfirmDelete(false)} type="button">
                  <X size={15} />
                  <span>Cancel</span>
                </button>
              </>
            ) : (
              <button className="profile-delete-trigger text-button secondary" disabled={busy} onClick={() => setConfirmDelete(true)} type="button">
                <Trash2 size={15} />
                <span>Delete profile</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </details>
  );
}

function shouldOpenProfileByDefault() {
  if (typeof window === "undefined") {
    return true;
  }
  return window.innerWidth > 680;
}

function ProfileEnabledControl({
  profile,
  setProfileEnabled,
  busy,
}: {
  profile: Profile;
  setProfileEnabled: (profileId: string, enabled: boolean) => void;
  busy: boolean;
}) {
  const nextEnabled = !profile.enabled;
  return (
    <button
      aria-label={`${profile.display_name || profileDisplayName(profile.profile_id)}: ${nextEnabled ? "Resume monitoring" : "Pause monitoring"}`}
      className={`profile-enable-button text-button ${profile.enabled ? "secondary" : ""}`}
      disabled={busy}
      onClick={() => setProfileEnabled(profile.profile_id, nextEnabled)}
      type="button"
    >
      {profile.enabled ? <CirclePause size={15} /> : <CirclePlay size={15} />}
      <span>{profile.enabled ? "Pause" : "Resume"}</span>
    </button>
  );
}

function AlertModeControl({
  profile,
  setAlertMode,
  busy,
}: {
  profile: Profile;
  setAlertMode: (profileId: string, mode: string) => void;
  busy: boolean;
}) {
  const mode = alertMode(profile);
  const modes = [
    { value: "work_hours", label: "Workday", title: "Notify during the workday", icon: <Sun size={14} /> },
    { value: "all_day", label: "Always", title: "Notify any time", icon: <Bell size={14} /> },
    { value: "muted", label: "Off", title: "Do not send notifications", icon: <BellOff size={14} /> },
  ];
  return (
    <div className="mode-controls" aria-label={`${profile.profile_id} alerts`}>
      {modes.map((item) => (
        <button
          className={mode === item.value ? "mode-button active" : "mode-button"}
          key={item.value}
          type="button"
          title={item.title}
          disabled={busy || !profile.enabled}
          onClick={() => setAlertMode(profile.profile_id, item.value)}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
}

type NotificationSettingsDraft = {
  timezoneText: string;
  workdays: string[];
  workStartText: string;
  workEndText: string;
  workIntervalText: string;
  offHoursIntervalText: string;
};

const HALF_HOUR_TIME_OPTIONS = Array.from({ length: 48 }, (_, index) => {
  const hour = Math.floor(index / 2).toString().padStart(2, "0");
  const minute = index % 2 === 0 ? "00" : "30";
  return `${hour}:${minute}`;
});

const NOTIFICATION_INTERVAL_OPTIONS = [5, 10, 15, 30, 60, 120, 240, 480, 720, 1440];
const WEEKDAY_VALUES = PROFILE_WEEKDAY_OPTIONS.map((day) => day.value);
const WORKDAY_VALUES = ["mon", "tue", "wed", "thu", "fri"];

function NotificationDetailsControl({
  profile,
  setProfileRuntimeSettings,
  busy,
}: {
  profile: Profile;
  setProfileRuntimeSettings: (profileId: string, settings: ProfileRuntimeSettings) => void;
  busy: boolean;
}) {
  const [draft, setDraft] = useState(() => notificationDraftFromProfile(profile));
  const saveState = notificationSettingsSaveState(profile, draft);
  const detectedTimezone = detectedBrowserTimezone();
  const timezoneChoices = timezoneOptions(draft.timezoneText, detectedTimezone);
  const workStartChoices = optionValuesWithCurrent(draft.workStartText, HALF_HOUR_TIME_OPTIONS);
  const workEndChoices = optionValuesWithCurrent(draft.workEndText, HALF_HOUR_TIME_OPTIONS);
  const workIntervalChoices = numericOptionsWithCurrent(Number(draft.workIntervalText), NOTIFICATION_INTERVAL_OPTIONS);
  const offHoursIntervalChoices = numericOptionsWithCurrent(Number(draft.offHoursIntervalText), NOTIFICATION_INTERVAL_OPTIONS);

  useEffect(() => {
    setDraft(notificationDraftFromProfile(profile));
  }, [
    profile.profile_id,
    profile.timezone,
    profile.workdays,
    profile.work_start,
    profile.work_end,
    profile.work_interval_minutes,
    profile.off_hours_interval_minutes,
  ]);

  return (
    <details className="profile-notification-details">
      <summary>Notification details</summary>
      <div className="profile-notification-detail-grid">
        <label>
          <span>Timezone</span>
          <select
            disabled={busy}
            onChange={(event) => setDraft((current) => ({ ...current, timezoneText: event.target.value }))}
            value={draft.timezoneText}
          >
            {timezoneChoices.map((timezone) => (
              <option key={timezone} value={timezone}>
                {timezone}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Work starts</span>
          <select
            disabled={busy}
            onChange={(event) => setDraft((current) => ({ ...current, workStartText: event.target.value }))}
            value={draft.workStartText}
          >
            {workStartChoices.map((time) => (
              <option key={time} value={time}>
                {time}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Work ends</span>
          <select
            disabled={busy}
            onChange={(event) => setDraft((current) => ({ ...current, workEndText: event.target.value }))}
            value={draft.workEndText}
          >
            {workEndChoices.map((time) => (
              <option key={time} value={time}>
                {time}
              </option>
            ))}
          </select>
        </label>
        <div className="profile-notification-weekdays" role="group" aria-label="Workdays">
          <span>Workdays</span>
          <div className="profile-notification-presets">
            <button
              aria-pressed={sameDays(draft.workdays, WEEKDAY_VALUES)}
              disabled={busy}
              onClick={() => setDraft((current) => ({ ...current, workdays: WEEKDAY_VALUES }))}
              type="button"
            >
              Every day
            </button>
            <button
              aria-pressed={sameDays(draft.workdays, WORKDAY_VALUES)}
              disabled={busy}
              onClick={() => setDraft((current) => ({ ...current, workdays: WORKDAY_VALUES }))}
              type="button"
            >
              Mon-Fri
            </button>
          </div>
          <div className="profile-notification-day-grid">
            {PROFILE_WEEKDAY_OPTIONS.map((day) => {
              const selected = draft.workdays.includes(day.value);
              return (
                <button
                  aria-pressed={selected}
                  className={selected ? "active" : ""}
                  disabled={busy}
                  key={day.value}
                  onClick={() => setDraft((current) => ({ ...current, workdays: toggleWeekday(current.workdays, day.value) }))}
                  type="button"
                >
                  {day.label}
                </button>
              );
            })}
          </div>
        </div>
        <label>
          <span>Workday interval (minutes)</span>
          <select
            disabled={busy}
            onChange={(event) => setDraft((current) => ({ ...current, workIntervalText: event.target.value }))}
            value={draft.workIntervalText}
          >
            {workIntervalChoices.map((minutes) => (
              <option key={minutes} value={minutes}>
                {minutes} min
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Off-hour interval (minutes)</span>
          <select
            disabled={busy}
            onChange={(event) => setDraft((current) => ({ ...current, offHoursIntervalText: event.target.value }))}
            value={draft.offHoursIntervalText}
          >
            {offHoursIntervalChoices.map((minutes) => (
              <option key={minutes} value={minutes}>
                {minutes} min
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        className="text-button profile-notification-save"
        disabled={busy || !saveState.canSave}
        onClick={() => setProfileRuntimeSettings(profile.profile_id, saveState.settings)}
        type="button"
      >
        <Save size={15} />
        <span>Save notification settings</span>
      </button>
    </details>
  );
}

function notificationDraftFromProfile(profile: Profile): NotificationSettingsDraft {
  const current = currentNotificationSettings(profile);
  return {
    timezoneText: current.timezone,
    workdays: current.workdays,
    workStartText: current.work_start,
    workEndText: current.work_end,
    workIntervalText: String(current.work_interval_minutes),
    offHoursIntervalText: String(current.off_hours_interval_minutes),
  };
}

function currentNotificationSettings(profile: Profile) {
  const workdays = normalizeWeekdays(profile.workdays);
  return {
    timezone: profile.timezone || "Asia/Shanghai",
    workdays: workdays.length ? workdays : WORKDAY_VALUES,
    work_start: profile.work_start || "09:00",
    work_end: profile.work_end || "18:00",
    work_interval_minutes: profile.work_interval_minutes ?? 15,
    off_hours_interval_minutes: profile.off_hours_interval_minutes ?? 60,
  };
}

function notificationSettingsSaveState(profile: Profile, draft: NotificationSettingsDraft) {
  const current = currentNotificationSettings(profile);
  const settings: ProfileRuntimeSettings = {};
  const timezone = draft.timezoneText.trim();
  const workStart = draft.workStartText.trim();
  const workEnd = draft.workEndText.trim();
  const workdays = normalizeWeekdays(draft.workdays);
  const workInterval = parseOptionalIntegerField(draft.workIntervalText, current.work_interval_minutes, 1, 1440);
  const offHoursInterval = parseOptionalIntegerField(draft.offHoursIntervalText, current.off_hours_interval_minutes, 1, 1440);
  const valid =
    isOptionalTimezoneValid(timezone, current.timezone) &&
    isOptionalTimeValid(workStart, current.work_start) &&
    isOptionalTimeValid(workEnd, current.work_end) &&
    workdays.length > 0 &&
    workInterval.valid &&
    offHoursInterval.valid;

  if (timezone && timezone !== current.timezone) {
    settings.timezone = timezone;
  }
  if (workStart && workStart !== current.work_start) {
    settings.work_start = workStart;
  }
  if (workEnd && workEnd !== current.work_end) {
    settings.work_end = workEnd;
  }
  if (workdays.join(",") !== current.workdays.join(",")) {
    settings.workdays = workdays;
  }
  if (workInterval.value !== undefined && workInterval.value !== current.work_interval_minutes) {
    settings.work_interval_minutes = workInterval.value;
  }
  if (offHoursInterval.value !== undefined && offHoursInterval.value !== current.off_hours_interval_minutes) {
    settings.off_hours_interval_minutes = offHoursInterval.value;
  }
  return {
    canSave: valid && Object.keys(settings).length > 0,
    settings,
  };
}

function optionValuesWithCurrent(current: string, defaults: string[]) {
  return Array.from(new Set([current, ...defaults].filter(Boolean))).sort();
}

function numericOptionsWithCurrent(current: number, defaults: number[]) {
  const options = Number.isInteger(current) && current > 0 ? [current, ...defaults] : defaults;
  return Array.from(new Set(options)).sort((left, right) => left - right);
}

function sameDays(left: string[], right: string[]) {
  return left.length === right.length && left.every((day, index) => day === right[index]);
}

function toggleWeekday(current: string[], day: string) {
  if (current.includes(day)) {
    return current.filter((item) => item !== day);
  }
  return WEEKDAY_VALUES.filter((item) => item === day || current.includes(item));
}
