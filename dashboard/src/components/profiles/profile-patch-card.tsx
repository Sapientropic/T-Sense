import { Check, FileDiff, RefreshCw } from "lucide-react";

import { toneClass } from "../../domain/display";
import { formatDate, profileDisplayName } from "../../domain/format";
import type { ProfilePatch } from "../../domain/types";
import { parseDiff } from "./diff";

export function ProfilePatchCard({
  patch,
  applyPatch,
  revertPatch,
  replayPatch,
  busy,
}: {
  patch: ProfilePatch;
  applyPatch: (patchId: string) => void;
  revertPatch: (patchId: string) => void;
  replayPatch: (patchId: string) => void;
  busy: boolean;
}) {
  const { added, removed } = parseDiff(patch.diff_text || "");
  const draftSummary = profileDraftUserSummary(patch.note);
  return (
    <article className="review-card patch-card">
      <div className="card-main">
        <div className="card-title-row">
          <h3>{patch.card_title || profileDisplayName(patch.profile_id)}</h3>
          <span className={`status ${toneClass(patch.status)}`}>{patch.status}</span>
        </div>
        <div className="patch-context-row">
          <span>Profile change</span>
          <span>{formatDate(patch.created_at)}</span>
          {added.length > 0 && <span>{added.length} added</span>}
          {removed.length > 0 && <span>{removed.length} removed</span>}
        </div>
        {patch.apply_readiness && (
          <div className={`patch-readiness ${toneClass(patch.apply_readiness.status || "unknown")}`}>
            <strong>{patch.apply_readiness.label || "Readiness check"}</strong>
            {patch.apply_readiness.detail && <span>{patch.apply_readiness.detail}</span>}
          </div>
        )}
        <div className="patch-user-explainer">
          <strong>{profileDraftEffectTitle(patch.note)}</strong>
          <p>{profileDraftEffectDetail(patch.note)}</p>
        </div>
        <p className="note-line">{draftSummary}</p>
        <details className="patch-diff-details">
          <summary>
            <FileDiff size={14} />
            <span>Preview changes</span>
          </summary>
          <div className="visual-diff">
            {added.length > 0 && (
              <div className="diff-added">
                <strong>Added rules</strong>
                <ul>
                  {added.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {removed.length > 0 && (
              <div className="diff-removed">
                <strong>Removed rules</strong>
                <ul>
                  {removed.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            {added.length === 0 && removed.length === 0 && (
              <p>No readable rule changes were found. Use expert details before applying.</p>
            )}
            <details className="expert-diff-details">
              <summary>Expert raw diff</summary>
              <pre>{patch.diff_text || "No diff body recorded."}</pre>
            </details>
          </div>
        </details>
        <div className="patch-actions">
          {patch.status === "pending" && (
            <button
              className="text-button"
              type="button"
              onClick={() => applyPatch(patch.patch_id)}
              disabled={busy}
              title="Apply this draft to the local profile file after checking it."
            >
              <Check size={15} />
              <span>Apply to profile</span>
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
          {patch.status === "reverted" && (
            <button
              className="text-button"
              type="button"
              onClick={() => replayPatch(patch.patch_id)}
              disabled={busy}
              title="Create a fresh pending diff from this reverted profile change if the file still matches the saved snapshot"
            >
              <RefreshCw size={15} />
              <span>Replay</span>
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

function profileDraftEffectTitle(note: string) {
  if (note.startsWith("User edited matching preferences")) {
    return "Updates your matching rules";
  }
  return note.startsWith("Desk feedback tuning") ? "Learns from your Review choices" : "Adds your manual preference";
}

function profileDraftEffectDetail(note: string) {
  if (note.startsWith("Desk feedback tuning")) {
    return "Signal Desk should generalize your Keep, Skip, and Wrong Match decisions into reusable rules. It should not copy single card titles as permanent preferences.";
  }
  if (note.startsWith("User edited matching preferences")) {
    return "Apply this after checking the preview. Future scans will use these plain-language rules when ranking matches.";
  }
  return "Apply this after checking it. Future scans will use this background or preference note when ranking matches for this profile.";
}

function profileDraftUserSummary(note: string) {
  if (!note) {
    return "Profile rule change awaiting review.";
  }
  if (note.startsWith("Desk feedback tuning")) {
    return "Draft from learning loop: extract broad rules from confirmed Review choices.";
  }
  if (note.startsWith("User edited matching preferences")) {
    return "Draft from your profile editor: update the editable matching rules.";
  }
  return note;
}
