import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { ProfilesView, runtimeSettingsSaveState } from "./profiles";
import { runtimeSettingsSaveState as runtimeSettingsSaveStateFromModel } from "./profiles/runtime-settings-model";
import type { Profile, ProfilePatch } from "../domain/types";

function profile(overrides: Partial<Profile>): Profile {
  return {
    profile_id: "jobs-fast",
    display_name: "Jobs Fast",
    display_path: "Profiles/jobs.md",
    enabled: true,
    alert_schedule_mode: "work_hours",
    source_topics: ["jobs"],
    scan_window_hours: 2,
    semantic_max_messages: 20,
    delivery_target_count: 1,
    updated_at: "2026-05-10T00:00:00Z",
    ...overrides,
  };
}

const createProfileFromBrief = vi.fn(async () => ({
  schema_version: "desk_profile_create_result_v1" as const,
  profile_id: "new-profile",
  display_name: "New Profile",
  profile_path: "profiles/desk/new-profile.md",
  created: true,
  detail: "Profile created.",
  next_action: "Review the new profile.",
}));

describe("ProfilesView", () => {
  it("keeps the split runtime settings model helper on the public profiles API", () => {
    expect(runtimeSettingsSaveStateFromModel).toBe(runtimeSettingsSaveState);
  });

  it("renders monitoring controls as human actions", () => {
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[profile({ enabled: true }), profile({ profile_id: "market-news", display_name: "Market News", enabled: false })]}
        patches={[]}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
        onGenerateProfileSuggestions={vi.fn()}
      />,
    );

    expect(html).toContain("Pause");
    expect(html).toContain("Resume");
    expect(html).toContain("Jobs Fast: Pause monitoring");
    expect(html).toContain("Market News: Resume monitoring");
    expect(html).toContain("Monitoring");
    expect(html).toContain("Paused");
    expect(html).toContain("2h history");
    expect(html).toContain("20 messages");
    expect(html).toContain("1 notification");
    expect(html).toContain("Notification details");
    expect(html).toContain("<select");
    expect(html).toContain("Work starts");
    expect(html).toContain("Work ends");
    expect(html).toContain("Every day");
    expect(html).toContain("Mon-Fri");
    expect(html).toContain("Workday interval (minutes)");
    expect(html).toContain("Off-hour interval (minutes)");
    expect(html).toContain(">15 min<");
    expect(html).toContain(">60 min<");
    expect(html).toContain("Save notification settings");
    expect(html).toContain("Delete profile");
    expect(html).not.toContain("placeholder=\"mon, tue, wed, thu, fri\"");
    expect(html).not.toContain("inputMode=\"numeric\"");
    expect(html).not.toContain("Edit profile");
    expect(html).not.toContain("Editable profile settings");
    expect(html).not.toContain("Detailed scan and alert defaults");
    expect(html).not.toContain("per run");
    expect(html).not.toContain("WINDOW");
    expect(html).not.toContain("ITEMS");
    expect(html).toContain("Resume monitoring to adjust alerts.");
    expect(html).toMatch(/disabled=""/);
    expect(html).not.toContain("Profiles/jobs.md");
    expect(html).not.toContain("SEMANTIC");
    expect(html).not.toContain("COPY COMMAND");
    expect(html).not.toContain("tgcs monitor run");
    expect(html).not.toContain("Profile Drafts");
    expect(html).not.toContain("No pending preference drafts");
  });

  it("keeps new profile creation visible without opening editor noise by default", () => {
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[]}
        patches={[]}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
      />,
    );

    expect(html).toContain("New profile");
    expect(html).toContain("Markdown, text, or PDF");
    expect(html).toContain("No profiles yet");
  });

  it("shows preference drafts as reviewable profile changes with explicit actions", () => {
    const patch: ProfilePatch = {
      patch_id: "patch-1",
      profile_id: "jobs-fast",
      card_title: "React contract role",
      note: "Prefer remote React roles.",
      status: "pending",
      diff_text: "-old\n+new",
      source_card_count: 2,
      created_at: "2026-05-10T00:00:00Z",
    };
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[profile({ enabled: true })]}
        patches={[patch]}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
      />,
    );

    expect(html).toContain("Profile Drafts");
    expect(html).toContain("aria-expanded=\"true\"");
    expect(html).toContain("Profile draft");
    expect(html).toContain("2 Review decisions");
    expect(html).toContain("Review this drafted profile change, then apply or dismiss it.");
    expect(html).toContain("Drafted matching changes");
    expect(html).toContain("Apply to profile");
    expect(html).toContain("Dismiss draft");
    expect(html).not.toContain(">Preview<");
    expect(html).not.toContain("Edit the suggestion, preview it, then apply the draft.");
    expect(html).not.toContain("AI profile suggestions");
    expect(html).not.toContain("AI modification suggestions");
    expect(html).not.toContain("Regenerate with AI");
    expect(html).not.toContain("Preview with AI");
    expect(html).not.toContain("Apply AI suggestions");
    expect(html).not.toContain("Apply batch");
    expect(html).not.toContain("Jobs Fast feedback batch");
    expect(html).not.toContain("Adds your manual preference");
  });

  it("does not turn profile section labels into draft suggestion text", () => {
    const patch: ProfilePatch = {
      patch_id: "patch-1",
      profile_id: "jobs-fast",
      note: "User edited matching preferences in Signal Desk.",
      status: "pending",
      diff_text: [
        "--- current-profile",
        "+++ proposed-profile",
        "@@ -1,3 +1,8 @@",
        " ## Follow-up Preferences",
        "+Match profile",
        "+Role: Frontend / full-stack developer opportunities worth acting on",
        "+How cards are judged",
        "+Exclude full-stack roles; prefer focused frontend or specialist scopes.",
        "+Report preferences",
      ].join("\n"),
      source_card_count: 0,
      created_at: "2026-05-10T00:00:00Z",
    };
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[profile({ enabled: true })]}
        patches={[patch]}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
      />,
    );

    expect(html).toContain("Exclude full-stack roles");
    expect(html).not.toContain("User edited matching preferences");
    expect(html).not.toContain("Match profile");
    expect(html).not.toContain("How cards are judged");
    expect(html).not.toContain("Report preferences");
    expect(html).not.toContain("Role: Frontend");
  });

  it("hides applied and reverted profile diffs from the default review queue", () => {
    const patch: ProfilePatch = {
      patch_id: "patch-1",
      profile_id: "jobs-fast",
      note: "Prefer remote React roles.",
      status: "applied",
      diff_text: "-old\n+new",
      created_at: "2026-05-10T00:00:00Z",
    };
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[profile({ enabled: true })]}
        patches={[patch]}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
      />,
    );

    expect(html).not.toContain("Profile Drafts");
    expect(html).not.toContain("Apply to profile");
    expect(html).not.toContain("Revert");
    expect(html).not.toContain("Replay");
  });

  it("does not block stale profile drafts or duplicate diff and note text", () => {
    const patches: ProfilePatch[] = [{
      patch_id: "patch-1",
      profile_id: "jobs-fast",
      note: "not fullstack",
      status: "pending",
      diff_text: "+not fullstack",
      apply_readiness: {
        status: "blocked",
        label: "Profile changed",
        detail: "Regenerate before applying.",
      },
      created_at: "2026-05-10T00:00:00Z",
    }, {
      patch_id: "patch-2",
      profile_id: "jobs-fast",
      note: "not full stack",
      status: "pending",
      diff_text: "+not full stack",
      created_at: "2026-05-10T00:01:00Z",
    }];
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[profile({ enabled: true })]}
        patches={patches}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
      />,
    );

    expect(html).not.toContain("Profile changed");
    expect(html).not.toContain("Regenerate before applying.");
    expect(html).not.toContain("Regenerate with AI");
    expect(html).not.toContain("Add: not fullstack");
    expect(html).not.toContain("Add: not full stack");
    expect(html.match(/not fullstack/g) ?? []).toHaveLength(1);
    expect(html.match(/not full stack/g) ?? []).toHaveLength(1);
    expect(html).toContain("Apply to profile");
    expect(html).toContain("Apply");
    expect(html).toContain("Dismiss draft");
    expect(html).toContain("title=\"Apply this profile draft\" type=\"button\"");
    expect(html).not.toContain("Regenerate the stale suggestion before applying");
  });

  it("lets users edit matching rule sections directly from the matching panel", () => {
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[
          profile({
            enabled: true,
            matching_profile: {
              summary: "Current matching rules",
              learned_preferences: [],
              editable_text: "- Prefer senior AI roles\n- Avoid unpaid internships",
              sections: [
                {
                  key: "rules",
                  label: "How cards are judged",
                  items: ["Prefer senior AI roles", "Avoid unpaid internships"],
                },
              ],
            },
          }),
        ]}
        patches={[]}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
      />,
    );

    expect(html).toContain("Create draft");
    expect(html).toContain("Prefer senior AI roles");
    expect(html).toContain("textarea");
    expect(html).toContain("edit profile tuning notes");
    expect(html).not.toContain("jobs-fast How cards are judged directly edit matching rules");
    expect(html).not.toContain("Editable profile settings");
  });

  it("keeps internal tuning prompts out of user-editable tuning notes", () => {
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[
          profile({
            enabled: true,
            matching_profile: {
              summary: "Current matching rules",
              learned_preferences: ["not full stack", "not lead"],
              editable_text: "- Prefer senior AI roles",
              sections: [
                {
                  key: "rules",
                  label: "How cards are judged",
                  items: ["Prefer senior AI roles"],
                },
                {
                  key: "learned",
                  label: "Applied tuning notes",
                  items: [
                    "not full stack",
                    "Desk feedback tuning: Analyze the recent Keep/Skip/Wrong Match feedback.",
                  ],
                },
              ],
            },
          }),
        ]}
        patches={[]}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
      />,
    );

    expect(html).toContain("Tuning notes");
    expect(html).toContain("not full stack");
    expect(html).toContain("not lead");
    expect(html).toContain("aria-label=\"jobs-fast Tuning notes edit profile tuning notes\"");
    expect(html).not.toContain("Applied tuning notes directly edit matching rules");
    expect(html).not.toContain("Desk feedback tuning");
  });

  it("shows learned exclusions as the effective matching profile instead of conflicting base text", () => {
    const html = renderToStaticMarkup(
      <ProfilesView
        profiles={[
          profile({
            enabled: true,
            matching_profile: {
              summary: "Role: Frontend / full-stack developer opportunities worth acting on",
              learned_preferences: ["not full stack", "i don't want full stack", "not lead"],
              editable_text: "",
              sections: [
                {
                  key: "basics",
                  label: "Match profile",
                  items: [
                    "Role: Frontend / full-stack developer opportunities worth acting on",
                    "Level: Middle to senior, or specialist contract work with clear budget",
                  ],
                },
                {
                  key: "learned",
                  label: "Applied tuning notes",
                  items: ["not full stack", "i don't want full stack", "not lead"],
                },
              ],
            },
          }),
        ]}
        patches={[]}
        applyPatch={vi.fn()}
        revertPatch={vi.fn()}
        replayPatch={vi.fn()}
        setAlertMode={vi.fn()}
        setProfileEnabled={vi.fn()}
        setProfileRuntimeSettings={vi.fn()}
        createProfileDraftNote={vi.fn()}
        createProfileMatchingPreferencesDraft={vi.fn()}
        createProfileFromBrief={createProfileFromBrief}
        profileCreateResult={null}
        busy={false}
      />,
    );

    expect(html).toContain("Role: Frontend developer opportunities worth acting on");
    expect(html).toContain("not full stack");
    expect(html).toContain("not lead");
    expect(html).not.toContain("Frontend / full-stack");
    expect(html).not.toContain("full-stack developer opportunities");
  });

  it("validates profile scan setting edits before save", () => {
    const current = {
      scan_window_hours: 2,
      semantic_max_messages: 20,
      timezone: "Asia/Shanghai",
      workdays: ["mon", "tue", "wed", "thu", "fri"],
      work_start: "09:00",
      work_end: "18:00",
      work_interval_minutes: 15,
      off_hours_interval_minutes: 60,
      alert_rule: "high_new_or_changed",
      alert_max_age_minutes: 60,
    };
    const draft = {
      scanWindowText: "2",
      itemLimitText: "20",
      timezoneText: "Asia/Shanghai",
      workdays: ["mon", "tue", "wed", "thu", "fri"],
      workStartText: "09:00",
      workEndText: "18:00",
      workIntervalText: "15",
      offHoursIntervalText: "60",
      alertRule: "high_new_or_changed",
      alertMaxAgeText: "60",
    };
    expect(runtimeSettingsSaveState(current, draft)).toMatchObject({ canSave: false, settings: {} });
    expect(runtimeSettingsSaveState(current, { ...draft, scanWindowText: "5", itemLimitText: "35" })).toMatchObject({
      canSave: true,
      settings: {
        scan_window_hours: 5,
        semantic_max_messages: 35,
      },
    });
    expect(runtimeSettingsSaveState(current, { ...draft, alertRule: "high_new_only", workdays: ["mon", "wed", "fri"] })).toMatchObject({
      canSave: true,
      settings: {
        alert_rule: "high_new_only",
        workdays: ["mon", "wed", "fri"],
      },
    });
    expect(runtimeSettingsSaveState(current, { ...draft, timezoneText: "../secret" })).toMatchObject({ canSave: false });
    expect(runtimeSettingsSaveState(current, { ...draft, workStartText: "25:00" })).toMatchObject({ canSave: false });
    expect(runtimeSettingsSaveState(current, { ...draft, workIntervalText: "0" })).toMatchObject({ canSave: false });
    expect(runtimeSettingsSaveState(current, { ...draft, alertMaxAgeText: "10081" })).toMatchObject({ canSave: false });
  });
});
