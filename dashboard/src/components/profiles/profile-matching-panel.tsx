import { profileDisplayName } from "../../domain/format";
import type { Profile } from "../../domain/types";
import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

type MatchingDraftSection = {
  key: string;
  label: string;
  text: string;
};

export function ProfileMatchingPanel({
  profile,
  busy,
  createProfileMatchingPreferencesDraft,
}: {
  profile: Profile;
  busy: boolean;
  createProfileMatchingPreferencesDraft: (profileId: string, preferences: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(() => shouldOpenMatchingByDefault());
  const sections = profile.matching_profile?.sections ?? [];
  const currentDraftSections = editableMatchingDraftSections(profile);
  const currentEditableText = serializeDraftSections(currentDraftSections);
  const [draftSections, setDraftSections] = useState(currentDraftSections);
  const normalizedRulesText = serializeDraftSections(draftSections).trim();
  const canPreviewRules = Boolean(normalizedRulesText) && normalizedRulesText !== currentEditableText.trim();

  useEffect(() => {
    setDraftSections(currentDraftSections);
  }, [currentEditableText, profile.profile_id]);

  if (!sections.length) {
    return (
      <div className="profile-matching-panel is-empty">
        <span className="panel-kicker">Matching profile</span>
        <strong>No readable matching rules yet</strong>
        <p>Edit plain-language matching rules here, then preview a reviewable draft.</p>
        <div className="profile-matching-grid" aria-label="directly edit matching rules">
          {draftSections.map((section) => (
            <EditableMatchSection
              busy={busy}
              draft={section}
              key={section.key}
              onChange={(value) => updateDraftSection(setDraftSections, section.key, value)}
              profileId={profile.profile_id}
            />
          ))}
        </div>
        <MatchingRulesActions
          busy={busy}
          canPreviewRules={canPreviewRules}
          onPreview={() => void createProfileMatchingPreferencesDraft(profile.profile_id, normalizedRulesText)}
        />
      </div>
    );
  }
  const primarySections = draftSections.filter((section) => section.key !== "report").slice(0, 3);
  const extraSections = draftSections.filter((section) => !primarySections.includes(section));
  return (
    <details
      className="profile-matching-panel"
      aria-label={`Matching rules for ${profile.display_name || profileDisplayName(profile.profile_id)}`}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary className="profile-matching-head">
        <span className="panel-kicker">Matching profile</span>
        <strong>{profile.matching_profile?.summary || "Current rules used for matching"}</strong>
        <small>{open ? "Collapse rules" : "View rules"}</small>
      </summary>
      <div className="profile-matching-body">
        <div className="profile-matching-grid" aria-label="directly edit matching rules">
          {primarySections.map((section) => (
            <EditableMatchSection
              busy={busy}
              draft={section}
              key={section.key}
              onChange={(value) => updateDraftSection(setDraftSections, section.key, value)}
              profileId={profile.profile_id}
            />
          ))}
        </div>
        {extraSections.length > 0 && (
          <details className="profile-matching-more">
            <summary>More matching context</summary>
            {extraSections.map((section) => (
              <EditableMatchSection
                busy={busy}
                draft={section}
                key={section.key}
                onChange={(value) => updateDraftSection(setDraftSections, section.key, value)}
                profileId={profile.profile_id}
              />
            ))}
          </details>
        )}
        <MatchingRulesActions
          busy={busy}
          canPreviewRules={canPreviewRules}
          onPreview={() => void createProfileMatchingPreferencesDraft(profile.profile_id, normalizedRulesText)}
        />
      </div>
    </details>
  );
}

function EditableMatchSection({
  busy,
  draft,
  onChange,
  profileId,
}: {
  busy: boolean;
  draft: MatchingDraftSection;
  onChange: (value: string) => void;
  profileId: string;
}) {
  return (
    <label className={`profile-match-section is-${draft.key}`}>
      <span>{draft.label}</span>
      <textarea
        aria-label={`${profileId} ${draft.label} directly edit matching rules`}
        disabled={busy}
        maxLength={2200}
        onChange={(event) => onChange(event.target.value)}
        placeholder={"Prefer senior remote AI engineering roles\nAvoid unpaid internships and vague promos"}
        value={draft.text}
      />
    </label>
  );
}

function MatchingRulesActions({
  busy,
  canPreviewRules,
  onPreview,
}: {
  busy: boolean;
  canPreviewRules: boolean;
  onPreview: () => void;
}) {
  return (
    <div className="profile-matching-editor">
      <strong>Draft</strong>
      <button
        className="text-button profile-matching-preview-action"
        disabled={busy || !canPreviewRules}
        onClick={onPreview}
        title={canPreviewRules ? "Turn these rules into a reviewable profile draft" : "Change the matching rules first"}
        type="button"
      >
        Preview
      </button>
    </div>
  );
}

function editableMatchingDraftSections(profile: Profile): MatchingDraftSection[] {
  const explicitText = profile.matching_profile?.editable_text?.trim();
  const sections = profile.matching_profile?.sections ?? [];
  if (sections.length) {
    const drafts = sections.map((section) => ({
      key: section.key,
      label: section.label,
      text: section.items.join("\n"),
    }));
    const learned = profile.matching_profile?.learned_preferences ?? [];
    if (learned.length && !drafts.some((section) => section.key === "learned")) {
      drafts.push({
        key: "learned",
        label: "Learned preferences",
        text: learned.join("\n"),
      });
    }
    return drafts;
  }
  return [
    {
      key: "rules",
      label: "Plain-language rules",
      text: explicitText || "",
    },
  ];
}

function updateDraftSection(
  setDraftSections: Dispatch<SetStateAction<MatchingDraftSection[]>>,
  key: string,
  value: string,
) {
  setDraftSections((current) => current.map((section) => (section.key === key ? { ...section, text: value } : section)));
}

function serializeDraftSections(sections: MatchingDraftSection[]) {
  return sections
    .map((section) => {
      const text = section.text.trim();
      return text ? `${section.label}\n${text}` : "";
    })
    .filter(Boolean)
    .join("\n\n");
}

function shouldOpenMatchingByDefault() {
  return false;
}
