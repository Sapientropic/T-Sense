import { useState } from "react";
import { Check, ChevronDown, CirclePlay, FileDiff, UserRoundCog, X } from "lucide-react";

import { InlineEmpty, PanelHeader } from "./common";
import { NewProfilePanel } from "./profiles/new-profile-panel";
import { parseDiff } from "./profiles/diff";
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
  deleteProfile = () => undefined,
  createProfileDraftNote,
  createProfileMatchingPreferencesDraft,
  createProfileFromBrief,
  profileCreateResult,
  busy,
  onGenerateProfileSuggestions,
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
  deleteProfile?: (profileId: string) => void;
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
  onGenerateProfileSuggestions?: () => void;
  onOpenStart?: () => void;
}) {
  const [draftsOpen, setDraftsOpen] = useState(() => shouldOpenDraftsByDefault());
  const draftsPanelId = "profile-drafts-panel";
  const visiblePatches = patches.filter((patch) => patch.status === "pending");
  return (
    <section className="split-section profiles-section" data-has-drafts={visiblePatches.length > 0 ? "true" : "false"}>
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
                createProfileMatchingPreferencesDraft={createProfileMatchingPreferencesDraft}
                key={profile.profile_id}
                profile={profile}
                setAlertMode={setAlertMode}
                setProfileEnabled={setProfileEnabled}
                setProfileRuntimeSettings={setProfileRuntimeSettings}
                deleteProfile={deleteProfile}
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
      {visiblePatches.length > 0 && (
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
            <span className="count-badge">{visiblePatches.length}</span>
          </header>
          <div className="patch-list" hidden={!draftsOpen} id={draftsPanelId}>
            {visiblePatches.map((patch) => (
              <ProfileDraftCard
                applyPatch={applyPatch}
                busy={busy}
                key={patch.patch_id}
                patch={patch}
                revertPatch={revertPatch}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function ProfileDraftCard({
  applyPatch,
  busy,
  patch,
  revertPatch,
}: {
  applyPatch: (patchId: string) => void;
  busy: boolean;
  patch: ProfilePatch;
  revertPatch: (patchId: string) => void;
}) {
  const suggestionText = profileSuggestionText([patch]);
  const reviewDecisionCount = patch.source_card_count || (patch.card_id ? 1 : 0);
  const sourceLine = reviewDecisionCount > 0
    ? `${reviewDecisionCount} Review decision${reviewDecisionCount === 1 ? "" : "s"}`
    : "Manual profile draft";

  return (
    <article className="review-card patch-card profile-draft-ai-card">
      <div className="card-main">
        <div className="card-title-row">
          <h3>Profile draft</h3>
          <span className="status pending">Pending</span>
        </div>
        <div className="patch-context-row">
          <span>{sourceLine}</span>
          <span>{patch.profile_display_path || patch.profile_id}</span>
        </div>
        <p className="note-line">Review this drafted profile change, then apply or dismiss it.</p>
        <label className="profile-draft-suggestion-field">
          <span>Drafted matching changes</span>
          <textarea
            readOnly
            maxLength={5000}
            value={suggestionText}
          />
        </label>
        <div className="patch-actions">
          <button
            className="text-button"
            disabled={busy}
            onClick={() => applyPatch(patch.patch_id)}
            title="Apply this profile draft"
            type="button"
          >
            <Check size={15} />
            <span>Apply to profile</span>
          </button>
          <button
            className="text-button secondary"
            disabled={busy}
            onClick={() => revertPatch(patch.patch_id)}
            title="Dismiss this draft without changing the profile"
            type="button"
          >
            <X size={15} />
            <span>Dismiss draft</span>
          </button>
        </div>
      </div>
    </article>
  );
}

function profileSuggestionText(patches: ProfilePatch[]) {
  const lines: string[] = [];
  const seen = new Set<string>();
  const addLine = (value: string) => {
    const normalized = normalizeSuggestionLine(value);
    if (!normalized) {
      return;
    }
    const key = normalized.toLocaleLowerCase().replace(/\s+/g, " ");
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    lines.push(normalized);
  };
  patches.forEach((patch) => {
    patch.note.split("\n").forEach(addLine);
    const { added } = parseDiff(patch.diff_text || "");
    added.forEach(addLine);
  });
  return lines.length ? lines.join("\n") : "Use the latest Review feedback to update reusable matching rules.";
}

function normalizeSuggestionLine(value: string) {
  const text = value
    .replace(/^\s*[-*]\s+/, "")
    .replace(/^\s*(?:Add|Remove):\s*/i, "")
    .trim();
  if (!text || text === "## Follow-up Preferences") {
    return "";
  }
  if (isGenericProfileDraftNote(text) || isProfileSectionLabel(text) || isProfileSectionMetadataLine(text)) {
    return "";
  }
  if (text.startsWith("Desk feedback tuning:")) {
    return "";
  }
  return text;
}

function isGenericProfileDraftNote(text: string) {
  const normalized = text.toLocaleLowerCase();
  return (
    normalized === "user edited matching preferences in signal desk." ||
    normalized === "signal desk review learning batch: combine review decisions into future matching rules."
  );
}

function isProfileSectionLabel(text: string) {
  return [
    "Match profile",
    "How cards are judged",
    "Applied tuning notes",
    "Report preferences",
    "Suggested matching changes",
  ].some((label) => text.localeCompare(label, undefined, { sensitivity: "accent" }) === 0);
}

function isProfileSectionMetadataLine(text: string) {
  return /^(Role|Level|Work format|Location exclusions|Goal|Review style|Report title|Section high|Section medium|Section low):\s/i.test(text);
}

function shouldOpenDraftsByDefault() {
  if (typeof window === "undefined") {
    return true;
  }
  return window.innerWidth > 680;
}
