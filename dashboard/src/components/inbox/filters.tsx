import type { Dispatch, SetStateAction } from "react";
import { FileDiff, UserRoundCog } from "lucide-react";

import { InlineEmpty } from "../common";
import { percentWidth, toneClass } from "../../domain/display";
import { decisionStatusLabel } from "../../domain/format";
import {
  countInboxCardsByRating,
  filterInboxCards,
  handledInboxCount,
  inboxFilterOptions,
  isActionableInboxCard,
  isMalformedInboxCard,
  isReviewQueueCard,
  reviewQueueCount,
  type InboxFilter,
} from "../../domain/inbox";
import type { DashboardState, ReviewCard } from "../../domain/types";

export function ReviewFilterEmptyState({
  activeFilter,
  busy = false,
  feedbackSummary,
  filters,
  onGenerateProfileSuggestions,
  onOpenProfiles,
  onSelectFilter,
}: {
  activeFilter: InboxFilter;
  busy?: boolean;
  feedbackSummary?: DashboardState["feedback_summary"];
  filters: ReturnType<typeof inboxFilterOptions>;
  onGenerateProfileSuggestions?: () => void;
  onOpenProfiles?: () => void;
  onSelectFilter: Dispatch<SetStateAction<InboxFilter>>;
}) {
  const nextFilter = nextNonEmptyReviewFilter(filters, activeFilter);
  const next = nextFilter ? filters.find((item) => item.id === nextFilter) : null;
  const reviewQueueTotal = filters
    .filter((item) => ["actionable", "new_changed", "medium"].includes(item.id))
    .reduce((sum, item) => sum + item.count, 0);
  const allCaughtUp = activeFilter === "actionable" && reviewQueueTotal === 0;
  const pendingDraftCount = feedbackSummary?.pending_profile_diff_count ?? 0;
  const exportableCount = feedbackSummary?.exportable_count ?? 0;
  const tuningSourceCount = feedbackSummary?.current_decision_count ?? exportableCount + (feedbackSummary?.non_exportable_follow_up_count ?? 0);
  const canShowLearningAction =
    allCaughtUp && ((pendingDraftCount > 0 && onOpenProfiles) || (tuningSourceCount > 0 && onGenerateProfileSuggestions));
  const learningAction = canShowLearningAction ? (
    <ReviewLearningAction
      busy={busy}
      onGenerateProfileSuggestions={onGenerateProfileSuggestions}
      onOpenProfiles={onOpenProfiles}
      pendingDraftCount={pendingDraftCount}
      tuningSourceCount={tuningSourceCount}
    />
  ) : null;
  const nextAction = next ? (
    <button type="button" onClick={() => onSelectFilter(next.id)}>
      Show {compactFilterLabel(next.label)} {next.count}
    </button>
  ) : undefined;
  return (
    <InlineEmpty
      title={allCaughtUp ? "All caught up" : activeFilter === "actionable" ? "No priority cards" : "No cards in this view"}
      detail={allCaughtUp ? reviewAllCaughtUpDetail(feedbackSummary, next?.label) : next ? reviewFilterEmptyDetail(next.label) : "This view is clear."}
      detailPlacement={allCaughtUp ? "icon" : "inline"}
      action={
        learningAction || nextAction ? (
          <>
            {learningAction}
            {nextAction}
          </>
        ) : undefined
      }
    />
  );
}

function ReviewLearningAction({
  busy,
  onGenerateProfileSuggestions,
  onOpenProfiles,
  pendingDraftCount,
  tuningSourceCount,
}: {
  busy: boolean;
  onGenerateProfileSuggestions?: () => void;
  onOpenProfiles?: () => void;
  pendingDraftCount: number;
  tuningSourceCount: number;
}) {
  if (pendingDraftCount > 0 && onOpenProfiles) {
    return (
      <button type="button" onClick={onOpenProfiles} disabled={busy}>
        <UserRoundCog size={15} />
        Review drafts {pendingDraftCount}
      </button>
    );
  }
  if (tuningSourceCount > 0 && onGenerateProfileSuggestions) {
    return (
      <button type="button" onClick={onGenerateProfileSuggestions} disabled={busy}>
        <FileDiff size={15} />
        Generate drafts {tuningSourceCount}
      </button>
    );
  }
  return null;
}

function reviewAllCaughtUpDetail(summary: DashboardState["feedback_summary"], nextLabel?: string) {
  if ((summary?.pending_profile_diff_count ?? 0) > 0) {
    return "Profile drafts are ready to review.";
  }
  if ((summary?.exportable_count ?? 0) > 0) {
    return "Use handled Review tags and notes to draft profile changes.";
  }
  if ((summary?.non_exportable_follow_up_count ?? 0) > 0) {
    return "Use saved notes to draft profile changes.";
  }
  return nextLabel ? reviewFilterEmptyDetail(nextLabel) : "This view is clear.";
}

function reviewFilterEmptyDetail(nextLabel: string) {
  if (nextLabel === "Handled") {
    return "Handled cards are saved as history.";
  }
  if (nextLabel === "Saved") {
    return "Saved cards are parked outside the review queue.";
  }
  if (nextLabel === "Duplicate") {
    return "Duplicate cards are kept out of the main queue.";
  }
  return `There are still cards in ${nextLabel}.`;
}

export function compactFilterLabel(label: string) {
  if (label === "Priority now") return "Priority";
  if (label === "New/Updated") return "New";
  if (label === "All cards") return "All";
  if (label === "Duplicate") return "Dupes";
  return label;
}

export function nextNonEmptyReviewFilter(filters: ReturnType<typeof inboxFilterOptions>, current: InboxFilter): InboxFilter | null {
  const preferred: InboxFilter[] =
    current === "actionable"
      ? ["new_changed", "medium", "saved", "duplicate", "handled"]
      : ["actionable", "new_changed", "medium", "saved", "handled", "duplicate"];
  return preferred.find((id) => id !== current && (filters.find((item) => item.id === id)?.count ?? 0) > 0) ?? null;
}

export function ReviewBacklogPanel({
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
    <section className="review-backlog-panel" aria-label="Other review buckets">
      <div className="review-backlog-copy">
        <span className="panel-kicker">Other cards</span>
        <strong>{waitingCount} outside this view</strong>
        <small>Switch buckets only when you need older or handled cards.</small>
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
        <div className="review-backlog-preview" aria-label="Other cards">
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
  if (rating === "low") {
    return "low";
  }
  if (["new", "changed"].includes(decisionStatus)) {
    return "new_changed";
  }
  if (rating === "medium") {
    return "medium";
  }
  return "all";
}

export function InboxTriageVisual({ cards, latestRunId }: { cards: ReviewCard[]; latestRunId?: string }) {
  const reviewCards = cards.filter((card) => isReviewQueueCard(card));
  const counts = {
    high: countInboxCardsByRating(reviewCards, "high"),
    medium: countInboxCardsByRating(reviewCards, "medium"),
    low: countInboxCardsByRating(reviewCards, "low"),
    action: filterInboxCards(cards, "actionable", latestRunId).length,
    malformed: cards.filter((card) => isMalformedInboxCard(card)).length,
    review: reviewQueueCount(cards),
    handled: handledInboxCount(cards),
  };
  const total = Math.max(1, counts.review);
  return (
    <div className="triage-visual" aria-label={`${counts.review} cards to review, ${counts.handled} handled cards`}>
      <div className="triage-stack" aria-hidden="true">
        <span className="high" style={{ width: percentWidth(counts.high / total) }} />
        <span className="medium" style={{ width: percentWidth(counts.medium / total) }} />
        <span className="low" style={{ width: percentWidth(counts.low / total) }} />
      </div>
      <div className="triage-legend">
        <span>
          <strong>{counts.action}</strong> priority
        </span>
        <span>
          <strong>{counts.review}</strong> to review
        </span>
        <span>
          <strong>{counts.handled}</strong> handled
        </span>
        {counts.malformed > 0 && (
          <span className="schema-warning">
            <strong>{counts.malformed}</strong> data
          </span>
        )}
      </div>
    </div>
  );
}
