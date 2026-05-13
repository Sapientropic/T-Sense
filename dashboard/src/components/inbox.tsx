import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { AlertTriangle, Archive, Ban, Bookmark, Check, Clock3, ExternalLink, FileDiff, Inbox, ListFilter, Play, Send, X } from "lucide-react";

import { CopyableCommand, EmptyStateShell, InlineEmpty } from "./common";
import { artifactFormatFromPath, artifactHref, percentWidth, reportProfileName, toneClass } from "../domain/display";
import { decisionStatusLabel, formatDate, profileDisplayName, sourceRefLabel } from "../domain/format";
import {
  filterInboxCards,
  inboxFilterOptions,
  countInboxCardsByRating,
  isActionableInboxCard,
  isMalformedInboxCard,
  setupCheckLabel,
  setupCheckTone,
  setupNeedsAttention,
  sourceRefUrl,
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
  onOpenStart,
}: {
  cards: ReviewCard[];
  latestRunId?: string;
  setupStatus?: DashboardState["setup_status"];
  profileReportNames: Record<string, string>;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
  onOpenStart?: () => void;
}) {
  const [filter, setFilter] = useState<InboxFilter>("actionable");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filters = inboxFilterOptions(cards, latestRunId);
  const activeFilterCount = filters.find((item) => item.id === filter)?.count ?? 0;
  useEffect(() => {
    if (!cards.length || activeFilterCount > 0) {
      return;
    }
    const nextFilter = nextNonEmptyReviewFilter(filters, filter);
    if (nextFilter && nextFilter !== filter) {
      setFilter(nextFilter);
      setFiltersOpen(false);
    }
  }, [activeFilterCount, cards.length, filter, filters]);
  if (!cards.length) {
    return (
      <InboxEmptyState
        title="Inbox clear"
        detail={setupStatus?.next_step ? `Next: ${appFirstNextStep(setupStatus.next_step)}` : "SQLite connected. Pending review cards are currently zero."}
        setupStatus={setupStatus}
        onOpenStart={onOpenStart}
      />
    );
  }
  const filteredCards = filterInboxCards(cards, filter, latestRunId);
  const activeFilter = filters.find((item) => item.id === filter) ?? filters[0];
  const primaryFilters = filters.filter((item) => item.id === "actionable" || item.id === "all");
  const secondaryFilters = filters.filter((item) => item.id !== "actionable" && item.id !== "all");
  const shouldShowFilter = (item: (typeof filters)[number]) => item.id === "all" || item.id === filter || item.count > 0;
  const renderFilterButton = (item: (typeof filters)[number]) => (
    <button
      className={filter === item.id ? "filter-chip active" : "filter-chip"}
      key={item.id}
      onClick={() => {
        setFilter(item.id);
        setFiltersOpen(false);
      }}
      type="button"
    >
      <span>{item.label}</span>
      <strong>{item.count}</strong>
    </button>
  );
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
        <button
          aria-label={`Review filter: ${activeFilter.label} (${activeFilter.count})`}
          aria-expanded={filtersOpen}
          className="inbox-filter-toggle"
          onClick={() => setFiltersOpen((value) => !value)}
          type="button"
        >
          <ListFilter size={14} />
          <span>{compactFilterLabel(activeFilter.label)}</span>
          <strong>{activeFilter.count}</strong>
        </button>
        <div className="inbox-filter-group" data-open={filtersOpen ? "true" : "false"}>
          {primaryFilters.filter(shouldShowFilter).map(renderFilterButton)}
          <div className="inbox-secondary-filter-list" aria-label="Other review buckets">
            {secondaryFilters.filter(shouldShowFilter).map(renderFilterButton)}
          </div>
        </div>
      </div>
      {filteredCards.length ? (
        <>
          {filteredCards.map((card) => (
            <ReviewCardArticle
              act={act}
              busy={busy}
              card={card}
              key={card.card_id}
              profileReportNames={profileReportNames}
            />
          ))}
          {filteredCards.length < cards.length && (
            <ReviewBacklogPanel
              activeFilter={filter}
              cards={cards}
              latestRunId={latestRunId}
              onSelectFilter={setFilter}
              visibleCount={filteredCards.length}
            />
          )}
        </>
      ) : (
        <ReviewFilterEmptyState activeFilter={filter} filters={filters} onSelectFilter={setFilter} />
      )}
    </section>
  );
}

function ReviewFilterEmptyState({
  activeFilter,
  filters,
  onSelectFilter,
}: {
  activeFilter: InboxFilter;
  filters: ReturnType<typeof inboxFilterOptions>;
  onSelectFilter: Dispatch<SetStateAction<InboxFilter>>;
}) {
  const nextFilter = nextNonEmptyReviewFilter(filters, activeFilter);
  const next = nextFilter ? filters.find((item) => item.id === nextFilter) : null;
  return (
    <InlineEmpty
      title={activeFilter === "actionable" ? "No latest action cards" : "No cards in this view"}
      detail={next ? reviewFilterEmptyDetail(next.label) : "This filter is clear."}
      action={
        next ? (
          <button type="button" onClick={() => onSelectFilter(next.id)}>
            Show {compactFilterLabel(next.label)} {next.count}
          </button>
        ) : undefined
      }
    />
  );
}

function reviewFilterEmptyDetail(nextLabel: string) {
  if (nextLabel === "Handled") {
    return "Applied, Contacted, and Dismissed cards are in Handled.";
  }
  if (nextLabel === "Saved") {
    return "Saved cards are parked outside Latest action.";
  }
  if (nextLabel === "Duplicate") {
    return "Duplicate cards are kept out of the main queue.";
  }
  return `There is still work in ${nextLabel}.`;
}

function compactFilterLabel(label: string) {
  if (label === "Latest action") return "Latest";
  if (label === "New/Changed") return "New";
  if (label === "Low/Medium") return "Low/Med";
  if (label === "Duplicate") return "Dupes";
  return label;
}

export function nextNonEmptyReviewFilter(filters: ReturnType<typeof inboxFilterOptions>, current: InboxFilter): InboxFilter | null {
  const preferred: InboxFilter[] = current === "actionable"
    ? ["handled", "saved", "duplicate", "high", "new_changed", "low_medium", "all"]
    : ["actionable", "high", "new_changed", "low_medium", "saved", "handled", "duplicate", "all"];
  return preferred.find((id) => id !== current && (filters.find((item) => item.id === id)?.count ?? 0) > 0) ?? null;
}

function ReviewBacklogPanel({
  cards,
  latestRunId,
  activeFilter,
  visibleCount,
  onSelectFilter,
}: {
  cards: ReviewCard[];
  latestRunId?: string;
  activeFilter: InboxFilter;
  visibleCount: number;
  onSelectFilter: Dispatch<SetStateAction<InboxFilter>>;
}) {
  const options = inboxFilterOptions(cards, latestRunId).filter((item) => item.id !== activeFilter && item.count > 0);
  const activeCardIds = new Set(filterInboxCards(cards, activeFilter, latestRunId).map((card) => card.card_id));
  const previewCards = cards.filter((card) => !activeCardIds.has(card.card_id)).slice(0, 3);
  const waitingCount = Math.max(0, cards.length - visibleCount);
  return (
    <section className="review-backlog-panel" aria-label="Review backlog map">
      <div className="review-backlog-copy">
        <span className="panel-kicker">Backlog map</span>
        <strong>{waitingCount} waiting outside this view</strong>
        <small>Use a bucket when the latest action is handled.</small>
      </div>
      <div className="review-backlog-buckets">
        {options.map((item) => (
          <button key={item.id} type="button" onClick={() => onSelectFilter(item.id)}>
            <span>{item.label}</span>
            <strong>{item.count}</strong>
          </button>
        ))}
      </div>
      {previewCards.length > 0 && (
        <div className="review-backlog-preview" aria-label="Next backlog cards">
          {previewCards.map((card) => (
            <button
              className="review-backlog-row"
              key={card.card_id}
              onClick={() => onSelectFilter(backlogFilterForCard(card, latestRunId))}
              title={`Show ${card.title}`}
              type="button"
            >
              <strong>{card.title}</strong>
              <span className={`rating ${toneClass(card.rating)}`}>{card.rating}</span>
              <small>{decisionStatusLabel(card.decision_status)}</small>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function backlogFilterForCard(card: ReviewCard, latestRunId?: string): InboxFilter {
  if (isActionableInboxCard(card, latestRunId)) {
    return "actionable";
  }
  const opportunityStatus = String(card.opportunity_status || "open").toLowerCase();
  if (opportunityStatus === "saved") {
    return "saved";
  }
  if (opportunityStatus === "duplicate") {
    return "duplicate";
  }
  if (["applied", "contacted", "dismissed"].includes(opportunityStatus)) {
    return "handled";
  }
  const rating = String(card.rating || "").toLowerCase();
  const decisionStatus = String(card.decision_status || "").toLowerCase();
  if (rating === "high") {
    return "high";
  }
  if (["new", "changed"].includes(decisionStatus)) {
    return "new_changed";
  }
  if (["low", "medium"].includes(rating)) {
    return "low_medium";
  }
  return "all";
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
        <MobileActionStrip
          act={act}
          busy={busy}
          card={card}
          setShowFollowUp={setShowFollowUp}
          showFollowUp={showFollowUp}
        />
        <p className="reason">{card.item.why || "Decision reason unavailable."}</p>
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
        {setupStatus?.next_step && <small>Next: {appFirstNextStep(setupStatus.next_step)}</small>}
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
            <button className="secondary-action" title="Dismiss opportunity" type="button" data-review-action="dismissed" onClick={() => act(card.card_id, "dismissed")} disabled={busy}>
              <X size={16} />
              <span>Dismiss</span>
            </button>
            <button className="secondary-action" title="Mark duplicate opportunity" type="button" data-review-action="duplicate" onClick={() => act(card.card_id, "duplicate")} disabled={busy}>
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

function InboxEmptyState({
  title,
  detail,
  setupStatus,
  onOpenStart,
}: {
  title: string;
  detail?: string;
  setupStatus?: DashboardState["setup_status"];
  onOpenStart?: () => void;
}) {
  return (
    <EmptyStateShell
      icon={<Inbox size={24} />}
      title={title}
      detail={detail}
      readout={[
        { label: "Data", value: "online" },
        { label: "Scans", value: setupStatus?.has_runs ? "history" : "needed" },
        { label: "Stage", value: setupStatus?.stage || "local" },
      ]}
    >
      {onOpenStart && (
        <div className="empty-actions" aria-label="Inbox next actions">
          <button type="button" onClick={onOpenStart}>
            <Play size={15} />
            <span>{setupStatus?.has_runs ? "Open Start" : "Run first scan"}</span>
          </button>
        </div>
      )}
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
              <details className="setup-command">
                <summary>Troubleshooting command</summary>
                <CopyableCommand command={check.command} label={check.label} />
              </details>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function appFirstNextStep(nextStep: string) {
  const text = nextStep.trim();
  if (!text) {
    return "";
  }
  if (text.includes("sources import")) {
    return "Open Settings, update Sources, then run another scan.";
  }
  if (text.includes("monitor run")) {
    return "Open Start and run the first practice scan.";
  }
  if (text.includes("delivery test")) {
    return "Open Settings and add a notification target, or keep manual review.";
  }
  if (text.includes("init-config")) {
    return "Open Start and create the local workspace.";
  }
  if (text.includes("profiles.toml")) {
    return "Open Profiles and resume an existing profile.";
  }
  return text;
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
