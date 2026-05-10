import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { AlertTriangle, Ban, Check, Clock3, ExternalLink, FileDiff, Inbox, ListFilter, Play, X } from "lucide-react";

import { CopyableCommand, EmptyStateShell, InlineEmpty } from "./common";
import { artifactFormatFromPath, artifactHref, percentWidth, reportProfileName, toneClass } from "../domain/display";
import { decisionStatusLabel, formatDate, profileDisplayName, sourceRefLabel } from "../domain/format";
import {
  filterInboxCards,
  inboxFilterOptions,
  countInboxCardsByRating,
  isMalformedInboxCard,
  setupCheckLabel,
  setupCheckTone,
  setupNeedsAttention,
  telegramMessageUrl,
  type InboxFilter,
} from "../domain/inbox";
import type { DashboardState, ReviewCard, SourceRef } from "../domain/types";

export function InboxView({
  cards,
  latestRunId,
  setupStatus,
  profileReportNames,
  act,
  busy,
}: {
  cards: ReviewCard[];
  latestRunId?: string;
  setupStatus?: DashboardState["setup_status"];
  profileReportNames: Record<string, string>;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
}) {
  const [filter, setFilter] = useState<InboxFilter>("actionable");
  const filters = inboxFilterOptions(cards, latestRunId);
  if (!cards.length) {
    return (
      <InboxEmptyState
        title="Inbox clear"
        detail={setupStatus?.next_step ? `Next: ${setupStatus.next_step}` : "SQLite connected. Pending review cards are currently zero."}
        setupStatus={setupStatus}
      />
    );
  }
  const filteredCards = filterInboxCards(cards, filter, latestRunId);
  return (
    <section className="list-section" aria-label="Pending review cards">
      <SetupChecklistBanner setupStatus={setupStatus} />
      <div className="inbox-toolbar" aria-label="Inbox triage filters">
        <div className="triage-copy">
          <span className="panel-title">
            <ListFilter size={16} />
            Triage
          </span>
          <InboxTriageVisual cards={cards} latestRunId={latestRunId} />
        </div>
        <div className="inbox-filter-group">
          {filters.map((item) => (
            <button
              className={filter === item.id ? "filter-chip active" : "filter-chip"}
              key={item.id}
              onClick={() => setFilter(item.id)}
              type="button"
            >
              <span>{item.label}</span>
              <strong>{item.count}</strong>
            </button>
          ))}
        </div>
      </div>
      {filteredCards.length ? (
        filteredCards.map((card) => (
          <ReviewCardArticle
            act={act}
            busy={busy}
            card={card}
            key={card.card_id}
            profileReportNames={profileReportNames}
          />
        ))
      ) : (
        <InlineEmpty title={filter === "actionable" ? "No latest action cards; switch to All for backlog" : "No cards in this filter"} />
      )}
    </section>
  );
}

function ReviewCardArticle({
  card,
  profileReportNames,
  act,
  busy,
}: {
  card: ReviewCard;
  profileReportNames: Record<string, string>;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
}) {
  const [showFollowUp, setShowFollowUp] = useState(false);
  return (
    <article
      className={`review-card rating-${toneClass(card.rating)}`}
      data-actions-expanded={showFollowUp ? "true" : "false"}
    >
      <div className="card-spine" aria-hidden="true">
        <span>{card.rating}</span>
      </div>
      <div className="card-main">
        <div className="card-title-row">
          <h3>{card.title}</h3>
          <span className={`rating ${toneClass(card.rating)}`}>{card.rating}</span>
        </div>
        <p className="reason">{card.item.why || "Decision reason unavailable."}</p>
        <div className="meta-row">
          <span>{reportProfileName(card.profile_id, profileReportNames)}</span>
          <span>{decisionStatusLabel(card.decision_status)}</span>
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

function SetupChecklistBanner({ setupStatus }: { setupStatus?: DashboardState["setup_status"] }) {
  const checks = Array.isArray(setupStatus?.checks) ? setupStatus.checks : [];
  if (!setupNeedsAttention(checks)) {
    return null;
  }
  return (
    <section className="setup-banner" aria-label="First useful report checklist">
      <div className="setup-banner-copy">
        <span className="panel-kicker">Setup path</span>
        <strong>{setupStatus?.stage === "ready" ? "Ready to review" : "Complete first useful report"}</strong>
        {setupStatus?.next_step && <small>Next: {setupStatus.next_step}</small>}
      </div>
      <SetupChecklist setupStatus={setupStatus} compact />
    </section>
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
    <a
      className="report-chip"
      href={artifactHref(path)}
      aria-label={`Open ${label}`}
      rel="noreferrer"
      target="_blank"
      title={label}
    >
      <ExternalLink size={13} />
      <span>Open report</span>
      <small>
        {format} · {formatDate(updatedAt)}
      </small>
    </a>
  );
}

function InboxTriageVisual({ cards, latestRunId }: { cards: ReviewCard[]; latestRunId?: string }) {
  const counts = {
    high: countInboxCardsByRating(cards, "high"),
    medium: countInboxCardsByRating(cards, "medium"),
    low: countInboxCardsByRating(cards, "low"),
    action: filterInboxCards(cards, "actionable", latestRunId).length,
    malformed: cards.filter((card) => isMalformedInboxCard(card)).length,
  };
  const total = Math.max(1, cards.length);
  return (
    <div className="triage-visual" aria-label={`${counts.action} latest action cards, ${cards.length} total cards`}>
      <div className="triage-stack" aria-hidden="true">
        <span className="high" style={{ width: percentWidth(counts.high / total) }} />
        <span className="medium" style={{ width: percentWidth(counts.medium / total) }} />
        <span className="low" style={{ width: percentWidth(counts.low / total) }} />
      </div>
      <div className="triage-legend">
        <span>
          <strong>{counts.action}</strong> action
        </span>
        <span>
          <strong>{cards.length}</strong> backlog
        </span>
        {counts.malformed > 0 && (
          <span className="schema-warning">
            <strong>{counts.malformed}</strong> schema
          </span>
        )}
      </div>
    </div>
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
      <div className="action-cluster" aria-label="Review actions">
        <span className="action-cluster-label">Review action</span>
        <button title="Keep" type="button" onClick={() => act(card.card_id, "keep")} disabled={busy}>
          <Check size={16} />
          <span>Keep</span>
        </button>
        <button title="Skip" type="button" onClick={() => act(card.card_id, "skip")} disabled={busy}>
          <X size={16} />
          <span>Skip</span>
        </button>
        <button
          title="False positive"
          type="button"
          onClick={() => act(card.card_id, "false_positive")}
          disabled={busy}
        >
          <Ban size={16} />
          <span>False positive</span>
        </button>
        {!showFollowUp && (
          <button title="Draft profile diff" type="button" onClick={() => setShowFollowUp(true)} disabled={busy}>
            <FileDiff size={16} />
            <span>Draft diff</span>
          </button>
        )}
      </div>
      {showFollowUp && (
        <div className="follow-up">
          <div className="follow-up-head">
            <label htmlFor={noteId}>Profile diff note</label>
            <button
              className="follow-up-close"
              title="Hide profile diff note"
              type="button"
              onClick={() => setShowFollowUp(false)}
              disabled={busy}
            >
              <X size={14} />
              <span>Hide diff</span>
            </button>
          </div>
          <div className="follow-up-control">
            <textarea
              id={noteId}
              ref={textareaRef}
              aria-label="Profile diff note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Describe what future matches should change"
              disabled={busy}
            />
          </div>
          <div className="follow-up-footer">
            <small>Creates a reviewable profile diff. The note stays local and is not included in exports.</small>
            <button
              className="follow-up-submit"
              title={note.trim() ? "Create profile diff" : "Add a note first"}
              type="button"
              onClick={() => act(card.card_id, "follow_up", note.trim())}
              disabled={busy || !note.trim()}
            >
              <FileDiff size={16} />
              <span>{note.trim() ? "Create diff" : "Add note"}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function InboxEmptyState({
  title,
  detail,
  setupStatus,
}: {
  title: string;
  detail?: string;
  setupStatus?: DashboardState["setup_status"];
}) {
  return (
    <EmptyStateShell
      icon={<Inbox size={24} />}
      title={title}
      detail={detail}
      readout={[
        { label: "DB", value: "online" },
        { label: "Run", value: setupStatus?.has_runs ? "history" : "needed" },
        { label: "Next", value: setupStatus?.stage || "local" },
      ]}
    >
      <SetupChecklist setupStatus={setupStatus} />
    </EmptyStateShell>
  );
}

function SetupChecklist({ setupStatus, compact = false }: { setupStatus?: DashboardState["setup_status"]; compact?: boolean }) {
  const allChecks = Array.isArray(setupStatus?.checks) ? setupStatus.checks : [];
  const checks = compact
    ? allChecks.filter((check) => ["active", "blocked"].includes(String(check.status || "")))
    : allChecks;
  if (!checks.length) {
    return null;
  }

  return (
    <div className={compact ? "setup-checklist compact" : "setup-checklist"} aria-label="First useful report checklist">
      {checks.map((check) => (
        <div className={`setup-step ${setupCheckTone(check.status)}`} key={check.check_id}>
          <span className="setup-step-icon" aria-hidden="true">
            {setupCheckIcon(check.status)}
          </span>
          <div className="setup-step-copy">
            <div className="setup-step-title">
              <strong>{check.label}</strong>
              <span>{setupCheckLabel(check.status)}</span>
            </div>
            {check.detail && <p>{check.detail}</p>}
            {check.command && (
              <div className="setup-command">
                <CopyableCommand command={check.command} label={check.label} />
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function setupCheckIcon(status: string) {
  if (status === "done") {
    return <Check size={15} />;
  }
  if (status === "blocked") {
    return <AlertTriangle size={15} />;
  }
  if (status === "active") {
    return <Play size={15} />;
  }
  return <Clock3 size={15} />;
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
        const href = telegramMessageUrl(ref);
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
            title={`Open Telegram source: ${sourceTitle}`}
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
