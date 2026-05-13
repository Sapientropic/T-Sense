import { Bell, BellOff, CirclePause, CirclePlay, Sun } from "lucide-react";
import { useState } from "react";

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
import { ProfileRuntimeSettingsControl } from "./runtime-settings-control";

export function ProfileRow({
  profile,
  setAlertMode,
  setProfileEnabled,
  setProfileRuntimeSettings,
  createProfileDraftNote,
  createProfileMatchingPreferencesDraft,
  busy,
}: {
  profile: Profile;
  setAlertMode: (profileId: string, mode: string) => void;
  setProfileEnabled: (profileId: string, enabled: boolean) => void;
  setProfileRuntimeSettings: (profileId: string, settings: ProfileRuntimeSettings) => void;
  createProfileDraftNote: (profileId: string, note: string) => Promise<void>;
  createProfileMatchingPreferencesDraft: (profileId: string, preferences: string) => Promise<void>;
  busy: boolean;
}) {
  const [open, setOpen] = useState(() => shouldOpenProfileByDefault());
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
        <ProfileMatchingPanel profile={profile} />
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
            {!profile.enabled && <span className="profile-paused-note">Resume monitoring to adjust alerts.</span>}
          </div>
        </div>
        <ProfileRuntimeSettingsControl
          profile={profile}
          setProfileRuntimeSettings={setProfileRuntimeSettings}
          createProfileDraftNote={createProfileDraftNote}
          createProfileMatchingPreferencesDraft={createProfileMatchingPreferencesDraft}
          busy={busy}
        />
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
