import { useState } from "react";
import { ChevronDown, CirclePlay, FileDiff, UserRoundCog } from "lucide-react";

import { InlineEmpty, PanelHeader } from "./common";
import { NewProfilePanel } from "./profiles/new-profile-panel";
import { ProfilePatchCard } from "./profiles/profile-patch-card";
import { ProfileRow } from "./profiles/profile-row";
import type { Profile, ProfileCreateResult, ProfilePatch, ProfileRuntimeSettings } from "../domain/types";

export { runtimeSettingsSaveState } from "./profiles/runtime-settings-model";

export function ProfilesView({
  profiles,
  patches,
  applyPatch,
  revertPatch,
  replayPatch,
  setAlertMode,
  setProfileEnabled,
  setProfileRuntimeSettings,
  createProfileDraftNote,
  createProfileMatchingPreferencesDraft,
  createProfileFromBrief,
  profileCreateResult,
  busy,
  onOpenStart,
}: {
  profiles: Profile[];
  patches: ProfilePatch[];
  applyPatch: (patchId: string) => void;
  revertPatch: (patchId: string) => void;
  replayPatch: (patchId: string) => void;
  setAlertMode: (profileId: string, mode: string) => void;
  setProfileEnabled: (profileId: string, enabled: boolean) => void;
  setProfileRuntimeSettings: (profileId: string, settings: ProfileRuntimeSettings) => void;
  createProfileDraftNote: (profileId: string, note: string) => Promise<void>;
  createProfileMatchingPreferencesDraft: (profileId: string, preferences: string) => Promise<void>;
  createProfileFromBrief: (payload: {
    brief: string;
    source_filename?: string;
    source_text?: string;
    source_base64?: string;
  }) => Promise<ProfileCreateResult>;
  profileCreateResult: ProfileCreateResult | null;
  busy: boolean;
  onOpenStart?: () => void;
}) {
  const [draftsOpen, setDraftsOpen] = useState(() => shouldOpenDraftsByDefault());
  const draftsPanelId = "profile-drafts-panel";
  return (
    <section className="split-section profiles-section" data-has-drafts={patches.length > 0 ? "true" : "false"}>
      <div className="plain-panel">
        <PanelHeader icon={<UserRoundCog size={18} />} title="Profiles" />
        <NewProfilePanel
          busy={busy}
          createProfileFromBrief={createProfileFromBrief}
          latestResult={profileCreateResult}
        />
        {profiles.length ? (
          <div className="table-list">
            {profiles.map((profile) => (
              <ProfileRow
                busy={busy}
                createProfileDraftNote={createProfileDraftNote}
                createProfileMatchingPreferencesDraft={createProfileMatchingPreferencesDraft}
                key={profile.profile_id}
                profile={profile}
                setAlertMode={setAlertMode}
                setProfileEnabled={setProfileEnabled}
                setProfileRuntimeSettings={setProfileRuntimeSettings}
              />
            ))}
          </div>
        ) : (
          <InlineEmpty
            title="No profiles yet"
            detail="Create or import a monitor before Review can produce useful cards."
            action={
              onOpenStart ? (
                <button type="button" onClick={onOpenStart}>
                  <CirclePlay size={15} />
                  <span>Open setup</span>
                </button>
              ) : undefined
            }
          />
        )}
      </div>
      {patches.length > 0 && (
        <div className="plain-panel profile-drafts-panel" data-collapsed={draftsOpen ? "false" : "true"}>
          <header className="panel-header profile-drafts-header">
            <button
              aria-controls={draftsPanelId}
              aria-expanded={draftsOpen}
              className="profile-drafts-toggle"
              onClick={() => setDraftsOpen((value) => !value)}
              type="button"
            >
              <span className="panel-title">
                <FileDiff size={18} />
                Profile Drafts
              </span>
              <span className="profile-drafts-toggle-copy">{draftsOpen ? "Collapse" : "Review drafts"}</span>
              <ChevronDown size={17} />
            </button>
            <span className="count-badge">{patches.length}</span>
          </header>
          <div className="patch-list" hidden={!draftsOpen} id={draftsPanelId}>
            {patches.map((patch) => (
              <ProfilePatchCard
                applyPatch={applyPatch}
                busy={busy}
                key={patch.patch_id}
                patch={patch}
                replayPatch={replayPatch}
                revertPatch={revertPatch}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function shouldOpenDraftsByDefault() {
  if (typeof window === "undefined") {
    return true;
  }
  return window.innerWidth > 680;
}
