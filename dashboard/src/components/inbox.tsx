import { useEffect, useState } from "react";
import { ListFilter } from "lucide-react";

import {
  filterInboxCards,
  inboxFilterOptions,
  type InboxFilter,
} from "../domain/inbox";
import type { DashboardState, ReviewCard } from "../domain/types";
import {
  compactFilterLabel,
  InboxTriageVisual,
  nextNonEmptyReviewFilter,
  ReviewBacklogPanel,
  ReviewFilterEmptyState,
} from "./inbox/filters";
import { ReviewCardArticle } from "./inbox/review-card";
import { appFirstNextStep, InboxEmptyState, SetupChecklistBanner } from "./inbox/setup";

export { nextNonEmptyReviewFilter } from "./inbox/filters";

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
              latestRunId={latestRunId}
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
