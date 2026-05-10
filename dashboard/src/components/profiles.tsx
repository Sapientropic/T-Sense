import { Bell, BellOff, Check, FileDiff, RefreshCw, Sun, UserRoundCog } from "lucide-react";

import { InlineEmpty, PanelHeader } from "./common";
import { alertMode, diffStats, toneClass } from "../domain/display";
import { formatDate, formatScanWindow, formatSemanticCap, formatTargetCount, profileDisplayName, titleCaseLabel } from "../domain/format";
import type { Profile, ProfilePatch } from "../domain/types";

export function ProfilesView({
  profiles,
  patches,
  applyPatch,
  revertPatch,
  setAlertMode,
  busy,
}: {
  profiles: Profile[];
  patches: ProfilePatch[];
  applyPatch: (patchId: string) => void;
  revertPatch: (patchId: string) => void;
  setAlertMode: (profileId: string, mode: string) => void;
  busy: boolean;
}) {
  return (
    <section className="split-section">
      <div className="plain-panel">
        <PanelHeader icon={<UserRoundCog size={18} />} title="Profiles" count={profiles.length} />
        {profiles.length ? (
          <div className="table-list">
            {profiles.map((profile) => (
              <div className="table-row profile-row" key={profile.profile_id}>
                <div className="profile-primary">
                  <strong>{profile.display_name || profileDisplayName(profile.profile_id)}</strong>
                  <span className={profile.enabled ? "status enabled" : "status disabled"}>
                    {profile.enabled ? "enabled" : "disabled"}
                  </span>
                </div>
                <code title={profile.display_path || "Profile path unavailable"}>
                  {profile.display_path || "Profile path unavailable"}
                </code>
                <div className="profile-rhythm" aria-label={`${profile.profile_id} monitor shape`}>
                  <span>{formatScanWindow(profile.scan_window_hours)}</span>
                  <span>{formatSemanticCap(profile.semantic_max_messages)}</span>
                  <span>{profile.source_topics?.[0] ? titleCaseLabel(profile.source_topics[0]) : "No topic"}</span>
                  <span>{formatTargetCount(profile.delivery_target_count)}</span>
                </div>
                <AlertModeControl profile={profile} setAlertMode={setAlertMode} busy={busy} />
              </div>
            ))}
          </div>
        ) : (
          <InlineEmpty title="No profiles registered" />
        )}
      </div>
      <div className="plain-panel">
        <PanelHeader icon={<FileDiff size={18} />} title="Profile Diffs" count={patches.length} />
        {patches.length ? (
          <div className="patch-list">
            {patches.map((patch) => {
              const stats = diffStats(patch.diff_text);
              return (
                <article className="review-card patch-card" key={patch.patch_id}>
                  <div className="card-main">
                    <div className="card-title-row">
                      <h3>{patch.card_title || patch.profile_id}</h3>
                      <span className={`status ${toneClass(patch.status)}`}>{patch.status}</span>
                    </div>
                    <div className="patch-context-row">
                      <span>{profileDisplayName(patch.profile_id)}</span>
                      <code title={patch.profile_display_path || "Profile path unavailable"}>
                        {patch.profile_display_path || "Profile path unavailable"}
                      </code>
                      <span>{formatDate(patch.created_at)}</span>
                      {patch.applied_at && <span>applied {formatDate(patch.applied_at)}</span>}
                      <span className="patch-diff-stat">+{stats.added} / -{stats.removed}</span>
                      {patch.base_profile_short_hash && <span>base {patch.base_profile_short_hash}</span>}
                    </div>
                    {patch.apply_readiness && (
                      <div className={`patch-readiness ${toneClass(patch.apply_readiness.status || "unknown")}`}>
                        <strong>{patch.apply_readiness.label || "Readiness check"}</strong>
                        {patch.apply_readiness.detail && <span>{patch.apply_readiness.detail}</span>}
                      </div>
                    )}
                    <p className="note-line">{patch.note || "Follow-up preference draft"}</p>
                    <details className="patch-diff-details">
                      <summary>
                        <FileDiff size={14} />
                        <span>View patch</span>
                      </summary>
                      <pre>{patch.diff_text || "No diff body recorded."}</pre>
                    </details>
                    <div className="patch-actions">
                      {patch.status === "pending" && (
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => applyPatch(patch.patch_id)}
                          disabled={busy}
                        >
                          <Check size={15} />
                          <span>Apply</span>
                        </button>
                      )}
                      {patch.status === "applied" && (
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => revertPatch(patch.patch_id)}
                          disabled={busy}
                          title="Restore the saved profile snapshot if the file has not changed"
                        >
                          <RefreshCw size={15} />
                          <span>Revert</span>
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <InlineEmpty title="No pending profile diffs" />
        )}
      </div>
    </section>
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
    { value: "work_hours", label: "Day", icon: <Sun size={14} /> },
    { value: "all_day", label: "All", icon: <Bell size={14} /> },
    { value: "muted", label: "Mute", icon: <BellOff size={14} /> },
  ];
  return (
    <div className="mode-controls" aria-label={`${profile.profile_id} alert mode`}>
      {modes.map((item) => (
        <button
          className={mode === item.value ? "mode-button active" : "mode-button"}
          key={item.value}
          type="button"
          title={item.label}
          disabled={busy}
          onClick={() => setAlertMode(profile.profile_id, item.value)}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
}
