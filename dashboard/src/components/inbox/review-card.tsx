import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { Archive, Ban, Bookmark, Check, ExternalLink, FileDiff, Play, Send, X } from "lucide-react";

import { artifactFormatFromPath, artifactHref, reportProfileName, toneClass } from "../../domain/display";
import { decisionStatusLabel, formatDate, profileDisplayName, sourceRefLabel, titleCaseLabel } from "../../domain/format";
import { sourceRefUrl, telegramMessageUrl } from "../../domain/inbox";
import type { ReviewCard, SourceRef } from "../../domain/types";

export function ReviewCardArticle({
  card,
  latestRunId,
  profileReportNames,
  act,
  busy,
}: {
  card: ReviewCard;
  latestRunId?: string;
  profileReportNames: Record<string, string>;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
}) {
  const [showFollowUp, setShowFollowUp] = useState(false);
  return (
    <article className={`review-card rating-${toneClass(card.rating)}`} data-actions-expanded={showFollowUp ? "true" : "false"}>
      <div className="card-spine" aria-hidden="true">
        <span>{card.rating}</span>
      </div>
      <div className="card-main">
        <div className="card-title-row">
          <h3>{card.title}</h3>
          <span className={`rating ${toneClass(card.rating)}`}>{card.rating}</span>
        </div>
        <MobileActionStrip
          act={act}
          busy={busy}
          card={card}
          setShowFollowUp={setShowFollowUp}
          showFollowUp={showFollowUp}
        />
        <p className="reason">{card.item.why || "Decision reason unavailable."}</p>
        <ActionProofStrip card={card} latestRunId={latestRunId} profileReportNames={profileReportNames} />
        <div className="meta-row">
          <span>{reportProfileName(card.profile_id, profileReportNames)}</span>
          <span>{decisionStatusLabel(card.decision_status)}</span>
          <span className={`opportunity-badge status-${opportunityStatusTone(card.opportunity_status)}`}>
            {opportunityStatusLabel(card.opportunity_status)}
          </span>
          <span>{formatDate(card.updated_at)}</span>
        </div>
        <SourceRefs refs={card.source_refs} />
        {card.report_path && (
          <ReportArtifactChip
            path={card.report_path}
            profileId={card.profile_id}
            profileReportNames={profileReportNames}
            updatedAt={card.updated_at}
          />
        )}
      </div>
      <CardActions card={card} act={act} busy={busy} setShowFollowUp={setShowFollowUp} showFollowUp={showFollowUp} />
    </article>
  );
}

function ActionProofStrip({
  card,
  latestRunId,
  profileReportNames,
}: {
  card: ReviewCard;
  latestRunId?: string;
  profileReportNames: Record<string, string>;
}) {
  const decisionState = card.item.decision_state ?? {};
  const proofItems = [
    {
      label: "Profile",
      value: reportProfileName(card.profile_id, profileReportNames),
      title: "Profile that evaluated this card",
    },
    {
      label: "Decision",
      value: decisionStatusLabel(card.decision_status),
      title: decisionProofTitle(decisionState),
    },
    {
      label: "Review",
      value: reviewStatusLabel(card.status),
      title: "Current local review decision",
    },
    {
      label: "Evidence",
      value: sourceRefCountLabel(card.source_refs.length),
      title: sourceRefProofTitle(card.source_refs),
    },
    {
      label: "Run",
      value: runProofLabel(card, latestRunId),
      title: runProofTitle(card, latestRunId),
    },
  ];
  const signals = (decisionState.signals ?? []).slice(0, 2);
  signals.forEach((signal) => {
    proofItems.push({
      label: "Signal",
      value: titleCaseLabel(signal),
      title: "Decision signal carried by this review card",
    });
  });
  const materialChangeFields = (decisionState.material_change_fields ?? []).slice(0, 2);
  materialChangeFields.forEach((field) => {
    proofItems.push({
      label: "Changed",
      value: titleCaseLabel(field),
      title: "Material field that changed since earlier review memory",
    });
  });

  return (
    <div className="action-proof-strip" aria-label="Action proof">
      {proofItems.map((item) => (
        <span className="action-proof-chip" key={`${item.label}-${item.value}`} title={item.title}>
          <strong>{item.label}</strong>
          <span>{item.value}</span>
        </span>
      ))}
    </div>
  );
}

function decisionProofTitle(decisionState: NonNullable<ReviewCard["item"]["decision_state"]>) {
  const parts = [
    decisionState.seen_count ? `Seen ${decisionState.seen_count} time${decisionState.seen_count === 1 ? "" : "s"}` : "",
    decisionState.first_seen_at ? `First seen ${formatDate(decisionState.first_seen_at)}` : "",
    decisionState.last_seen_at ? `Last seen ${formatDate(decisionState.last_seen_at)}` : "",
  ].filter(Boolean);
  return parts.join(" · ") || "Novelty state from local decision memory";
}

function reviewStatusLabel(status?: string) {
  const normalized = String(status || "pending").toLowerCase();
  const labels: Record<string, string> = {
    false_positive: "Wrong match",
    follow_up: "Profile draft",
    kept: "Preferred",
    pending: "Needs decision",
    skipped: "Deprioritized",
  };
  return labels[normalized] || titleCaseLabel(normalized);
}

function sourceRefCountLabel(count: number) {
  if (count <= 0) {
    return "No source ref";
  }
  return `${count} source ref${count === 1 ? "" : "s"}`;
}

function sourceRefProofTitle(refs: SourceRef[]) {
  if (!refs.length) {
    return "No Telegram source reference was saved for this card";
  }
  return refs
    .slice(0, 3)
    .map((ref) => `@${String(ref.channel || "").replace(/^@+/, "")} #${String(ref.id || "")}`)
    .join(" · ");
}

function runProofLabel(card: ReviewCard, latestRunId?: string) {
  if (!card.last_run_id) {
    return "Run unknown";
  }
  if (latestRunId && card.last_run_id === latestRunId) {
    return card.report_path ? "Latest + report" : "Latest run";
  }
  return card.report_path ? "Prior + report" : "Prior run";
}

function runProofTitle(card: ReviewCard, latestRunId?: string) {
  if (!card.last_run_id) {
    return "No run id is attached to this card";
  }
  const relation = latestRunId && card.last_run_id === latestRunId ? "latest dashboard run" : "earlier run";
  return `From ${relation}: ${card.last_run_id}${card.report_path ? " with report artifact" : ""}`;
}

function opportunityStatusLabel(status: string) {
  const normalized = String(status || "open").toLowerCase();
  const labels: Record<string, string> = {
    open: "Open",
    saved: "Saved",
    applied: "Applied",
    contacted: "Contacted",
    dismissed: "Dismissed",
    duplicate: "Duplicate",
  };
  return labels[normalized] || "Open";
}

function opportunityStatusTone(status: string) {
  const normalized = String(status || "open").toLowerCase();
  if (["applied", "contacted"].includes(normalized)) {
    return "done";
  }
  if (normalized === "duplicate") {
    return "duplicate";
  }
  if (normalized === "dismissed") {
    return "dismissed";
  }
  if (normalized === "saved") {
    return "saved";
  }
  return "open";
}

function isOpenOpportunity(card: ReviewCard) {
  return String(card.opportunity_status || "open").toLowerCase() === "open";
}

function MobileActionStrip({
  card,
  act,
  busy,
  showFollowUp,
  setShowFollowUp,
}: {
  card: ReviewCard;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
  showFollowUp: boolean;
  setShowFollowUp: Dispatch<SetStateAction<boolean>>;
}) {
  return (
    <div className="mobile-action-strip" aria-label="Quick review actions">
      {isOpenOpportunity(card) ? (
        <>
          <button
            aria-label="Mark opportunity applied"
            title="Mark opportunity applied"
            type="button"
            data-review-action="applied"
            onClick={() => act(card.card_id, "applied")}
            disabled={busy}
          >
            <Check size={16} />
            <span>Applied</span>
          </button>
          <button
            aria-label="Save opportunity for later"
            title="Save opportunity for later"
            type="button"
            data-review-action="saved"
            onClick={() => act(card.card_id, "saved")}
            disabled={busy}
          >
            <Bookmark size={16} />
            <span>Save</span>
          </button>
          <button
            aria-label="Mark opportunity contacted"
            title="Mark opportunity contacted"
            type="button"
            data-review-action="contacted"
            onClick={() => act(card.card_id, "contacted")}
            disabled={busy}
          >
            <Send size={16} />
            <span>Contacted</span>
          </button>
        </>
      ) : (
        <button
          aria-label="Reopen opportunity"
          title="Reopen opportunity"
          type="button"
          data-review-action="reopen"
          onClick={() => act(card.card_id, "reopen")}
          disabled={busy}
        >
          <Play size={16} />
          <span>Reopen</span>
        </button>
      )}
      <button
        aria-label={showFollowUp ? "Hide match tuning tools" : "Tune profile or mark wrong match"}
        className="secondary-action"
        data-review-action="tune"
        title={showFollowUp ? "Hide match tuning tools" : "Tune profile or mark wrong match"}
        type="button"
        onClick={() => setShowFollowUp((value) => !value)}
        disabled={busy}
      >
        <FileDiff size={16} />
        <span>{showFollowUp ? "Hide tools" : "Tune profile"}</span>
      </button>
    </div>
  );
}

function ReportArtifactChip({
  path,
  profileId,
  profileReportNames,
  updatedAt,
}: {
  path: string;
  profileId: string;
  profileReportNames: Record<string, string>;
  updatedAt?: string;
}) {
  const label = profileReportNames[profileId] || `${profileDisplayName(profileId)} Report`;
  const format = artifactFormatFromPath(path);
  return (
    <a className="report-chip" href={artifactHref(path)} aria-label={`Open ${label}`} rel="noreferrer" target="_blank" title={label}>
      <ExternalLink size={13} />
      <span>Open report</span>
      <small>
        {format} · {formatDate(updatedAt)}
      </small>
    </a>
  );
}

function CardActions({
  card,
  act,
  busy,
  showFollowUp,
  setShowFollowUp,
}: {
  card: ReviewCard;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
  showFollowUp: boolean;
  setShowFollowUp: Dispatch<SetStateAction<boolean>>;
}) {
  const [note, setNote] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const noteId = `profile-diff-note-${card.card_id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  useEffect(() => {
    if (!showFollowUp) {
      return;
    }

    const timer = window.setTimeout(() => {
      const textarea = textareaRef.current;
      if (!textarea) {
        return;
      }
      const prefersReducedMotion =
        typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      textarea.focus({ preventScroll: true });
      if (typeof textarea.scrollIntoView === "function") {
        textarea.scrollIntoView({
          behavior: prefersReducedMotion ? "auto" : "smooth",
          block: "nearest",
        });
      }
    }, 0);

    return () => window.clearTimeout(timer);
  }, [showFollowUp]);

  return (
    <div className="card-actions">
      <div className="action-cluster lifecycle-cluster" aria-label="Opportunity lifecycle actions">
        <span className="action-cluster-label">Opportunity</span>
        {isOpenOpportunity(card) ? (
          <>
            <button title="Mark opportunity applied" type="button" data-review-action="applied" onClick={() => act(card.card_id, "applied")} disabled={busy}>
              <Check size={16} />
              <span>Applied</span>
            </button>
            <button title="Save opportunity for later" type="button" data-review-action="saved" onClick={() => act(card.card_id, "saved")} disabled={busy}>
              <Bookmark size={16} />
              <span>Saved</span>
            </button>
            <button title="Mark opportunity contacted" type="button" data-review-action="contacted" onClick={() => act(card.card_id, "contacted")} disabled={busy}>
              <Send size={16} />
              <span>Contacted</span>
            </button>
            <button
              className="secondary-action"
              title="Dismiss opportunity"
              type="button"
              data-review-action="dismissed"
              onClick={() => act(card.card_id, "dismissed")}
              disabled={busy}
            >
              <X size={16} />
              <span>Dismiss</span>
            </button>
            <button
              className="secondary-action"
              title="Mark duplicate opportunity"
              type="button"
              data-review-action="duplicate"
              onClick={() => act(card.card_id, "duplicate")}
              disabled={busy}
            >
              <Archive size={16} />
              <span>Duplicate</span>
            </button>
          </>
        ) : (
          <button title="Reopen opportunity" type="button" data-review-action="reopen" onClick={() => act(card.card_id, "reopen")} disabled={busy}>
            <Play size={16} />
            <span>Reopen</span>
          </button>
        )}
      </div>
      {!showFollowUp && (
        <div className="tune-profile-entry" aria-label="Profile tuning entry">
          <button
            className="tune-profile-trigger"
            data-review-action="tune"
            title="Tune profile from this card"
            type="button"
            onClick={() => setShowFollowUp(true)}
            disabled={busy}
          >
            <FileDiff size={17} />
            <span>Tune profile</span>
            <small>Signals + note</small>
          </button>
        </div>
      )}
      {showFollowUp && (
        <div className="follow-up">
          <div className="follow-up-head">
            <label htmlFor={noteId}>Profile tuning note</label>
            <button
              className="follow-up-close"
              title="Hide profile tuning note"
              type="button"
              onClick={() => setShowFollowUp(false)}
              disabled={busy}
            >
              <X size={14} />
              <span>Hide</span>
            </button>
          </div>
          <div className="follow-up-signal-grid" aria-label="Preference training actions">
            <button
              className="follow-up-signal"
              title="Prefer similar future matches"
              type="button"
              data-review-action="keep"
              onClick={() => act(card.card_id, "keep")}
              disabled={busy}
            >
              <Check size={16} />
              <span>Prefer similar</span>
            </button>
            <button
              className="follow-up-signal"
              title="Deprioritize similar future matches"
              type="button"
              data-review-action="skip"
              onClick={() => act(card.card_id, "skip")}
              disabled={busy}
            >
              <X size={16} />
              <span>Deprioritize</span>
            </button>
            <button
              className="follow-up-signal"
              data-review-action="avoid"
              title="Mark as wrong match and avoid similar future matches"
              type="button"
              onClick={() => act(card.card_id, "false_positive")}
              disabled={busy}
            >
              <Ban size={16} />
              <span>Wrong match</span>
            </button>
          </div>
          <div className="follow-up-control">
            <textarea
              id={noteId}
              ref={textareaRef}
              aria-label="Profile tuning note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Describe what future matches should change"
              disabled={busy}
            />
          </div>
          <div className="follow-up-footer">
            <small>Creates a reviewable profile change. The note stays local and is not included in exports.</small>
            <button
              className="follow-up-submit"
              title={note.trim() ? "Create profile change" : "Add a note first"}
              type="button"
              onClick={() => act(card.card_id, "follow_up", note.trim())}
              disabled={busy || !note.trim()}
            >
              <FileDiff size={16} />
              <span>{note.trim() ? "Create change" : "Add note"}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SourceRefs({ refs }: { refs: SourceRef[] }) {
  if (!refs.length) {
    return (
      <div className="source-row">
        <span className="source-chip muted">source refs unavailable</span>
      </div>
    );
  }
  return (
    <div className="source-row" aria-label="Source references">
      {refs.slice(0, 4).map((ref) => {
        const href = sourceRefUrl(ref);
        const label = sourceRefLabel(ref);
        const sourceTitle = `@${String(ref.channel || "").replace(/^@+/, "")} #${String(ref.id || "")}`;
        if (!href) {
          return (
            <span className="source-chip" key={`${ref.channel}-${ref.id}`} title={sourceTitle}>
              {label}
            </span>
          );
        }
        return (
          <a
            className="source-chip source-link"
            href={href}
            key={`${ref.channel}-${ref.id}`}
            target="_blank"
            rel="noreferrer"
            title={telegramMessageUrl(ref) || ref.url ? `Open Telegram source: ${sourceTitle}` : `Open Telegram channel: ${label}`}
          >
            <span>{label}</span>
            <ExternalLink size={12} aria-hidden="true" />
          </a>
        );
      })}
      {refs.length > 4 && <span className="source-chip muted">+{refs.length - 4}</span>}
    </div>
  );
}
