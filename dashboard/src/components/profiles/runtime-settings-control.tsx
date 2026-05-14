import { SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";

import type { Profile, ProfileRuntimeSettings } from "../../domain/types";
import {
  normalizeWeekdays,
  runtimeSettingsSaveState,
} from "./runtime-settings-model";
import {
  RuntimeAlertFields,
  RuntimeMatchingRulesField,
  RuntimeScanScopeFields,
  RuntimeSettingsActions,
  RuntimeWorkHoursFields,
} from "./runtime-settings-sections";
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
      <div className="profile-runtime-head">
        <div>
          <strong>Profile settings</strong>
          <span>Control how much this profile reads, when it checks, and what counts as a match.</span>
        </div>
      </div>

      <RuntimeScanScopeFields
        profileId={profile.profile_id}
        busy={busy}
        scanWindowHours={scanWindowHours}
        setScanWindowHours={setScanWindowHours}
        itemLimit={itemLimit}
        setItemLimit={setItemLimit}
      />

      <RuntimeWorkHoursFields
        profileId={profile.profile_id}
        busy={busy}
        timezone={timezone}
        setTimezone={setTimezone}
        workStart={workStart}
        setWorkStart={setWorkStart}
        workEnd={workEnd}
        setWorkEnd={setWorkEnd}
        workdays={workdays}
        setWorkdays={setWorkdays}
      />

      <RuntimeAlertFields
        profileId={profile.profile_id}
        busy={busy}
        workInterval={workInterval}
        setWorkInterval={setWorkInterval}
        offHoursInterval={offHoursInterval}
        setOffHoursInterval={setOffHoursInterval}
        alertRule={alertRule}
        setAlertRule={setAlertRule}
        alertMaxAge={alertMaxAge}
        setAlertMaxAge={setAlertMaxAge}
      />

      <RuntimeMatchingRulesField
        profileId={profile.profile_id}
        busy={busy}
        currentPreferences={currentPreferences}
        preferenceNote={preferenceNote}
        setPreferenceNote={setPreferenceNote}
      />
      <RuntimeSettingsActions
        profileId={profile.profile_id}
        busy={busy}
        canSaveSettings={saveState.canSave}
        settings={saveState.settings}
        canDraftPreferences={canDraftPreferences}
        normalizedPreference={normalizedPreference}
        setProfileRuntimeSettings={setProfileRuntimeSettings}
        createProfileDraftNote={createProfileDraftNote}
        createProfileMatchingPreferencesDraft={createProfileMatchingPreferencesDraft}
        closeEditor={() => setEditing(false)}
        resetDraft={() => {
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
        }}
      />
    </div>
  );
}
