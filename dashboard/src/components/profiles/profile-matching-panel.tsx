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
  const learnedItems = learnedMatchingItems(profile);
  const currentDraftSections = editableMatchingDraftSections(learnedItems);
  const currentEditableText = serializeDraftSections(currentDraftSections);
  const [draftSections, setDraftSections] = useState(currentDraftSections);
  const normalizedRulesText = serializeDraftSections(draftSections).trim();
  const canPreviewRules = Boolean(normalizedRulesText) && normalizedRulesText !== currentEditableText.trim();
  const matchingSummary =
    resolveMatchingItemConflicts(profile.matching_profile?.summary || "", learnedItems) || "Current rules used for matching";

  useEffect(() => {
    setDraftSections(currentDraftSections);
  }, [currentEditableText, profile.profile_id]);

  if (!sections.length) {
    return (
      <div className="profile-matching-panel is-empty">
        <span className="panel-kicker">Matching profile</span>
        <strong>No readable matching rules yet</strong>
        <p>Add plain-language tuning notes here, then create a reviewable profile draft.</p>
        <div className="profile-matching-grid" aria-label="edit profile tuning notes">
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
  const overviewSections = overviewMatchingSections(profile, learnedItems);
  const primarySections = overviewSections.slice(0, 2);
  const extraSections = overviewSections.slice(2);
  return (
    <details
      className="profile-matching-panel"
      aria-label={`Matching rules for ${profile.display_name || profileDisplayName(profile.profile_id)}`}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary className="profile-matching-head">
        <span className="panel-kicker">Matching profile</span>
        <strong>{matchingSummary}</strong>
        <small>{open ? "Collapse rules" : "View rules"}</small>
      </summary>
      <div className="profile-matching-body">
        <div className="profile-matching-grid" aria-label="current matching rules">
          {primarySections.map((section) => (
            <ReadOnlyMatchSection draft={section} key={section.key} profileId={profile.profile_id} />
          ))}
        </div>
        {(extraSections.length > 0 || draftSections.length > 0) && (
          <details className="profile-matching-more">
            <summary>More matching context</summary>
            {extraSections.map((section) => (
              <ReadOnlyMatchSection draft={section} key={section.key} profileId={profile.profile_id} />
            ))}
            {draftSections.map((section) => (
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
        aria-label={`${profileId} ${draft.label} edit profile tuning notes`}
        disabled={busy}
        maxLength={2200}
        onChange={(event) => onChange(event.target.value)}
        placeholder={"Exclude full-stack roles unless the profile explicitly asks for them\nPrefer focused frontend or specialist scopes"}
        value={draft.text}
      />
    </label>
  );
}

function ReadOnlyMatchSection({
  draft,
  profileId,
}: {
  draft: MatchingDraftSection;
  profileId: string;
}) {
  return (
    <section className={`profile-match-section is-${draft.key} is-readonly`} aria-label={`${profileId} ${draft.label}`}>
      <span>{draft.label}</span>
      <ul>
        {draft.text.split("\n").filter(Boolean).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
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
      <strong>Profile draft</strong>
      <button
        className="text-button profile-matching-preview-action"
        disabled={busy || !canPreviewRules}
        onClick={onPreview}
        title={canPreviewRules ? "Create a reviewable profile draft from these tuning notes" : "Change the tuning notes first"}
        type="button"
      >
        Create draft
      </button>
    </div>
  );
}

function editableMatchingDraftSections(learnedItems: string[]): MatchingDraftSection[] {
  return [
    {
      key: "learned",
      label: "Tuning notes",
      text: learnedItems.join("\n"),
    },
  ];
}

function learnedMatchingItems(profile: Profile) {
  const sections = profile.matching_profile?.sections ?? [];
  const learnedSection = sections.find((section) => section.key === "learned");
  return cleanMatchingItems(
    (profile.matching_profile?.learned_preferences?.length ? profile.matching_profile.learned_preferences : learnedSection?.items) ?? [],
  ).filter((item) => item !== "No extra learned preferences yet.");
}

function overviewMatchingSections(profile: Profile, learnedItems: string[]): MatchingDraftSection[] {
  const sections = profile.matching_profile?.sections ?? [];
  return sections
    .filter((section) => section.key !== "learned")
    .map((section) => ({
      key: section.key,
      label: section.label,
      text: cleanMatchingItems(section.items)
        .map((item) => resolveMatchingItemConflicts(item, learnedItems))
        .filter(Boolean)
        .join("\n"),
    }))
    .filter((section) => section.text.trim());
}

function cleanMatchingItems(items: string[]) {
  return items.map((item) => item.trim()).filter((item) => item && !isInternalTuningInstruction(item));
}

function isInternalTuningInstruction(item: string) {
  const normalized = item.toLowerCase();
  return normalized.startsWith("desk feedback tuning:") || normalized.startsWith("signal desk review learning batch:");
}

function resolveMatchingItemConflicts(item: string, learnedItems: string[]) {
  const fullStackExcluded = learnedItems.some(isFullStackExclusion);
  if (!fullStackExcluded || !FULL_STACK_PATTERN.test(item) || isFullStackExclusion(item)) {
    return item;
  }
  const resolved = item
    .replace(/\s*\/\s*full[-\s]?stack(?=\s+(?:developer|engineer|role|roles|opportunities)\b)/gi, "")
    .replace(/\bfull[-\s]?stack\s*\/\s*/gi, "")
    .replace(/\s*,\s*full[-\s]?stack\b/gi, "")
    .replace(/\bfull[-\s]?stack\s*,\s*/gi, "")
    .replace(/\s+([,.;:])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .replace(/^[,;/\s]+|[,;/\s]+$/g, "");
  return FULL_STACK_PATTERN.test(resolved) ? "" : resolved;
}

const FULL_STACK_PATTERN = /\bfull[-\s]?stack\b/i;
const NEGATIVE_PREFERENCE_PATTERN =
  /\b(?:not|no|never|exclude|avoid|without|don't|do not|doesn't|isn't|reject|skip)\b|不要|不想|不是|非全栈|排除|拒绝|避免/i;

function isFullStackExclusion(item: string) {
  return FULL_STACK_PATTERN.test(item) && NEGATIVE_PREFERENCE_PATTERN.test(item);
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
      return text;
    })
    .filter(Boolean)
    .join("\n\n");
}

function shouldOpenMatchingByDefault() {
  return false;
}
