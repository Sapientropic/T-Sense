import { profileDisplayName } from "../../domain/format";
import type { Profile } from "../../domain/types";
import { useState } from "react";

export function ProfileMatchingPanel({ profile }: { profile: Profile }) {
  const [open, setOpen] = useState(() => shouldOpenMatchingByDefault());
  const sections = profile.matching_profile?.sections ?? [];
  if (!sections.length) {
    return (
      <div className="profile-matching-panel is-empty">
        <span className="panel-kicker">Matching profile</span>
        <strong>No readable matching rules yet</strong>
        <p>Edit this profile to add plain-language rules Signal Desk can use.</p>
      </div>
    );
  }
  const primarySections = sections.filter((section) => section.key !== "report").slice(0, 3);
  const extraSections = sections.filter((section) => !primarySections.includes(section));
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
        <div className="profile-matching-grid">
          {primarySections.map((section) => (
            <section className={`profile-match-section is-${section.key}`} key={section.key}>
              <span>{section.label}</span>
              <ul>
                {section.items.slice(0, section.key === "rules" ? 4 : 3).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        {extraSections.length > 0 && (
          <details className="profile-matching-more">
            <summary>More matching context</summary>
            {extraSections.map((section) => (
              <section key={section.key}>
                <span>{section.label}</span>
                <ul>
                  {section.items.slice(0, 5).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ))}
          </details>
        )}
      </div>
    </details>
  );
}

function shouldOpenMatchingByDefault() {
  if (typeof window === "undefined") {
    return true;
  }
  return window.innerWidth > 680;
}
