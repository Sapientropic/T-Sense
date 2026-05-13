import { FileDiff, Save, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";

import type { Profile, ProfileRuntimeSettings } from "../../domain/types";
import {
  PROFILE_WEEKDAY_OPTIONS,
  normalizeWeekdays,
  runtimeSettingsSaveState,
} from "./runtime-settings-model";
import { ProfileHelpTip } from "./profile-help-tip";
import { profileDisplayName } from "../../domain/format";

export function ProfileRuntimeSettingsControl({
  profile,
  setProfileRuntimeSettings,
  createProfileDraftNote,
  createProfileMatchingPreferencesDraft,
  busy,
}: {
  profile: Profile;
  setProfileRuntimeSettings: (profileId: string, settings: ProfileRuntimeSettings) => void;
  createProfileDraftNote: (profileId: string, note: string) => Promise<void>;
  createProfileMatchingPreferencesDraft: (profileId: string, preferences: string) => Promise<void>;
  busy: boolean;
}) {
  const currentScanWindow = typeof profile.scan_window_hours === "number" ? profile.scan_window_hours : 24;
  const currentItemLimit = typeof profile.semantic_max_messages === "number" ? profile.semantic_max_messages : 20;
  const currentTimezone = profile.timezone || "";
  const currentWorkdays = normalizeWeekdays(profile.workdays);
  const currentWorkStart = profile.work_start || "";
  const currentWorkEnd = profile.work_end || "";
  const currentWorkInterval = typeof profile.work_interval_minutes === "number" ? profile.work_interval_minutes : undefined;
  const currentOffHoursInterval = typeof profile.off_hours_interval_minutes === "number" ? profile.off_hours_interval_minutes : undefined;
  const currentAlertRule = profile.alert_rule || "high_new_or_changed";
  const currentAlertMaxAge = typeof profile.alert_max_age_minutes === "number" ? profile.alert_max_age_minutes : undefined;
  const currentPreferences = profile.matching_profile?.editable_text || "";
  const [scanWindowHours, setScanWindowHours] = useState(String(currentScanWindow));
  const [itemLimit, setItemLimit] = useState(String(currentItemLimit));
  const [timezone, setTimezone] = useState(currentTimezone);
  const [workdays, setWorkdays] = useState<string[]>(currentWorkdays);
  const [workStart, setWorkStart] = useState(currentWorkStart);
  const [workEnd, setWorkEnd] = useState(currentWorkEnd);
  const [workInterval, setWorkInterval] = useState(currentWorkInterval ? String(currentWorkInterval) : "");
  const [offHoursInterval, setOffHoursInterval] = useState(currentOffHoursInterval ? String(currentOffHoursInterval) : "");
  const [alertRule, setAlertRule] = useState(currentAlertRule);
  const [alertMaxAge, setAlertMaxAge] = useState(currentAlertMaxAge ? String(currentAlertMaxAge) : "");
  const [preferenceNote, setPreferenceNote] = useState(currentPreferences);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    setScanWindowHours(String(currentScanWindow));
    setItemLimit(String(currentItemLimit));
    setTimezone(currentTimezone);
    setWorkdays(currentWorkdays);
    setWorkStart(currentWorkStart);
    setWorkEnd(currentWorkEnd);
    setWorkInterval(currentWorkInterval ? String(currentWorkInterval) : "");
    setOffHoursInterval(currentOffHoursInterval ? String(currentOffHoursInterval) : "");
    setAlertRule(currentAlertRule);
    setAlertMaxAge(currentAlertMaxAge ? String(currentAlertMaxAge) : "");
    if (!editing) {
      setPreferenceNote(currentPreferences);
    }
  }, [
    currentScanWindow,
    currentItemLimit,
    currentTimezone,
    currentWorkdays.join(","),
    currentWorkStart,
    currentWorkEnd,
    currentWorkInterval,
    currentOffHoursInterval,
    currentAlertRule,
    currentAlertMaxAge,
    currentPreferences,
    editing,
  ]);

  const saveState = runtimeSettingsSaveState(
    {
      scan_window_hours: currentScanWindow,
      semantic_max_messages: currentItemLimit,
      timezone: currentTimezone,
      workdays: currentWorkdays,
      work_start: currentWorkStart,
      work_end: currentWorkEnd,
      work_interval_minutes: currentWorkInterval,
      off_hours_interval_minutes: currentOffHoursInterval,
      alert_rule: currentAlertRule,
      alert_max_age_minutes: currentAlertMaxAge,
    },
    {
      scanWindowText: scanWindowHours,
      itemLimitText: itemLimit,
      timezoneText: timezone,
      workdays,
      workStartText: workStart,
      workEndText: workEnd,
      workIntervalText: workInterval,
      offHoursIntervalText: offHoursInterval,
      alertRule,
      alertMaxAgeText: alertMaxAge,
    },
  );
  const normalizedPreference = preferenceNote.trim();
  const canDraftPreferences = Boolean(normalizedPreference) && normalizedPreference !== currentPreferences.trim();

  if (!editing) {
    return (
      <button className="profile-edit-settings text-button" disabled={busy} onClick={() => setEditing(true)} type="button">
        <SlidersHorizontal size={15} />
        <span>Edit profile</span>
      </button>
    );
  }

  return (
    <div className="profile-runtime-settings" aria-label={`Editable profile settings for ${profile.display_name || profileDisplayName(profile.profile_id)}`}>
      <div className="profile-runtime-numbers">
        <label>
          <span className="profile-field-title">
            Hours to check
            <ProfileHelpTip text="How far back each scan reads saved-channel posts." />
          </span>
          <input
            aria-label={`${profile.profile_id} scan window hours`}
            disabled={busy}
            inputMode="numeric"
            max={168}
            min={1}
            onChange={(event) => setScanWindowHours(event.target.value)}
            step={1}
            type="number"
            value={scanWindowHours}
          />
          <small>hours back</small>
        </label>
        <label>
          <span className="profile-field-title">
            Posts to read
            <ProfileHelpTip text="Maximum recent posts Signal Desk ranks for this profile each scan." />
          </span>
          <input
            aria-label={`${profile.profile_id} item limit`}
            disabled={busy}
            inputMode="numeric"
            max={500}
            min={1}
            onChange={(event) => setItemLimit(event.target.value)}
            step={1}
            type="number"
            value={itemLimit}
          />
          <small>per scan</small>
        </label>
      </div>
      <div className="profile-runtime-schedule">
        <label>
          <span className="profile-field-title">
            Timezone
            <ProfileHelpTip text="IANA timezone used for work-hours scheduling." />
          </span>
          <input
            aria-label={`${profile.profile_id} timezone`}
            disabled={busy}
            onChange={(event) => setTimezone(event.target.value)}
            placeholder="Asia/Shanghai"
            value={timezone}
          />
        </label>
        <label>
          <span className="profile-field-title">
            Work starts
            <ProfileHelpTip text="Start of the local work-hours notification window." />
          </span>
          <input
            aria-label={`${profile.profile_id} work start`}
            disabled={busy}
            onChange={(event) => setWorkStart(event.target.value)}
            type="time"
            value={workStart}
          />
        </label>
        <label>
          <span className="profile-field-title">
            Work ends
            <ProfileHelpTip text="End of the local work-hours notification window." />
          </span>
          <input
            aria-label={`${profile.profile_id} work end`}
            disabled={busy}
            onChange={(event) => setWorkEnd(event.target.value)}
            type="time"
            value={workEnd}
          />
        </label>
        <label>
          <span className="profile-field-title">
            Work interval
            <ProfileHelpTip text="Dry-run scheduler cadence during work hours." />
          </span>
          <input
            aria-label={`${profile.profile_id} work interval minutes`}
            disabled={busy}
            inputMode="numeric"
            max={1440}
            min={1}
            onChange={(event) => setWorkInterval(event.target.value)}
            step={1}
            type="number"
            value={workInterval}
          />
          <small>minutes</small>
        </label>
        <label>
          <span className="profile-field-title">
            Quiet interval
            <ProfileHelpTip text="Dry-run scheduler cadence outside work hours." />
          </span>
          <input
            aria-label={`${profile.profile_id} off hours interval minutes`}
            disabled={busy}
            inputMode="numeric"
            max={1440}
            min={1}
            onChange={(event) => setOffHoursInterval(event.target.value)}
            step={1}
            type="number"
            value={offHoursInterval}
          />
          <small>minutes</small>
        </label>
        <label>
          <span className="profile-field-title">
            Alert rule
            <ProfileHelpTip text="Use high-new-only for noisy profiles where changed items should not alert again." />
          </span>
          <select
            aria-label={`${profile.profile_id} alert rule`}
            disabled={busy}
            onChange={(event) => setAlertRule(event.target.value)}
            value={alertRule}
          >
            <option value="high_new_or_changed">High new or changed</option>
            <option value="high_new_only">High new only</option>
          </select>
        </label>
        <label>
          <span className="profile-field-title">
            Alert age
            <ProfileHelpTip text="Maximum age for high-signal items before notifications are skipped." />
          </span>
          <input
            aria-label={`${profile.profile_id} alert max age minutes`}
            disabled={busy}
            inputMode="numeric"
            max={10080}
            min={1}
            onChange={(event) => setAlertMaxAge(event.target.value)}
            step={1}
            type="number"
            value={alertMaxAge}
          />
          <small>minutes</small>
        </label>
      </div>
      <fieldset className="profile-runtime-weekdays">
        <legend className="profile-field-title">
          Workdays
          <ProfileHelpTip text="Days included in this profile's work-hours schedule." />
        </legend>
        <div className="profile-weekday-options">
          {PROFILE_WEEKDAY_OPTIONS.map((day) => (
            <label className="profile-weekday-toggle" key={day.value}>
              <input
                checked={workdays.includes(day.value)}
                disabled={busy}
                onChange={(event) => {
                  if (event.target.checked) {
                    setWorkdays(normalizeWeekdays([...workdays, day.value]));
                  } else {
                    setWorkdays(workdays.filter((value) => value !== day.value));
                  }
                }}
                type="checkbox"
              />
              <span>{day.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="profile-preference-note">
        <span className="profile-field-title">
          Matching rules
          <ProfileHelpTip text={currentPreferences
            ? "Edit learned rules here. Signal Desk will preview a draft before the rules affect matching."
            : "Write plain-language rules here. Signal Desk will preview a draft before applying them."}
          />
        </span>
        <textarea
          aria-label={`${profile.profile_id} background and match rules`}
          disabled={busy}
          maxLength={4000}
          onChange={(event) => setPreferenceNote(event.target.value)}
          placeholder={"- Prefer senior remote AI engineering roles\n- Avoid unpaid internships and vague promos"}
          value={preferenceNote}
        />
        {preferenceNote.length > 3600 && <small>{4000 - preferenceNote.length} characters left before the preview limit.</small>}
      </label>
      <div className="profile-runtime-actions">
        <button
          className="profile-save-settings profile-primary-action text-button"
          disabled={busy || !saveState.canSave}
          onClick={() => {
            if (!saveState.canSave) {
              return;
            }
            setProfileRuntimeSettings(profile.profile_id, {
              ...saveState.settings,
            });
            setEditing(false);
          }}
          type="button"
        >
          <Save size={15} />
          <span>Save scan settings</span>
        </button>
        <button
          className="profile-save-settings profile-secondary-action text-button"
          disabled={busy || !canDraftPreferences}
          onClick={() => {
            if (!canDraftPreferences) {
              return;
            }
            void createProfileMatchingPreferencesDraft(profile.profile_id, normalizedPreference).then(() => {
              setEditing(false);
            });
          }}
          title={canDraftPreferences ? "Preview these matching-rule changes" : "Change the matching rules first"}
          type="button"
        >
          <FileDiff size={15} />
          <span>Preview matching changes</span>
        </button>
        <button
          className="profile-save-settings profile-tertiary-action text-button secondary"
          disabled={busy || !normalizedPreference}
          onClick={() => {
            if (!normalizedPreference) {
              return;
            }
            void createProfileDraftNote(profile.profile_id, normalizedPreference).then(() => {
              setEditing(false);
            });
          }}
          title={normalizedPreference ? "Add this as a separate profile note" : "Write a matching note first"}
          type="button"
        >
          <FileDiff size={15} />
          <span>Add as draft note</span>
        </button>
        <button
          className="profile-cancel-settings text-button"
          disabled={busy}
          onClick={() => {
            setScanWindowHours(String(currentScanWindow));
            setItemLimit(String(currentItemLimit));
            setTimezone(currentTimezone);
            setWorkdays(currentWorkdays);
            setWorkStart(currentWorkStart);
            setWorkEnd(currentWorkEnd);
            setWorkInterval(currentWorkInterval ? String(currentWorkInterval) : "");
            setOffHoursInterval(currentOffHoursInterval ? String(currentOffHoursInterval) : "");
            setAlertRule(currentAlertRule);
            setAlertMaxAge(currentAlertMaxAge ? String(currentAlertMaxAge) : "");
            setPreferenceNote(currentPreferences);
            setEditing(false);
          }}
          type="button"
        >
          <span>Cancel</span>
        </button>
      </div>
    </div>
  );
}
