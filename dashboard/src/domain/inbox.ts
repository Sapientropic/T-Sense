export type InboxFilter =
  | "actionable"
  | "all"
  | "high"
  | "new_changed"
  | "medium"
  | "low"
  | "low_medium"
  | "saved"
  | "handled"
  | "duplicate";

export type InboxCardLike = {
  rating?: unknown;
  decision_status?: unknown;
  opportunity_status?: unknown;
  status?: unknown;
  last_run_id?: string | null;
};

export type SetupCheckLike = {
  status?: unknown;
};

export type SourceRefLike = {
  channel?: unknown;
  id?: unknown;
  url?: unknown;
};

function normalizeInboxToken(value: unknown) {
  return typeof value === "string" ? value.toLowerCase() : "";
}

export function isMalformedInboxCard(card: InboxCardLike) {
  return [card.rating, card.decision_status].some(
    (value) => value !== null && value !== undefined && typeof value !== "string",
  );
}

export function isReviewQueueCard(card: InboxCardLike) {
  const opportunityStatus = normalizeInboxToken(card.opportunity_status || "open");
  const reviewStatus = normalizeInboxToken(card.status || "pending");
  return opportunityStatus === "open" && reviewStatus === "pending";
}

export function reviewQueueCount<T extends InboxCardLike>(cards: T[]) {
  return cards.filter((card) => isReviewQueueCard(card)).length;
}

export function handledInboxCount<T extends InboxCardLike>(cards: T[]) {
  return cards.length - reviewQueueCount(cards);
}

export function isActionableInboxCard(card: InboxCardLike, latestRunId?: string) {
  const isLatest = latestRunId ? card.last_run_id === latestRunId : true;
  return (
    isReviewQueueCard(card) &&
    isLatest &&
    normalizeInboxToken(card.rating) === "high" &&
    ["new", "changed"].includes(normalizeInboxToken(card.decision_status))
  );
}

export function filterInboxCards<T extends InboxCardLike>(cards: T[], filter: InboxFilter, latestRunId?: string) {
  const reviewQueueCards = cards.filter((card) => isReviewQueueCard(card));
  if (filter === "actionable") {
    return cards.filter((card) => isActionableInboxCard(card, latestRunId));
  }
  if (filter === "high") {
    return reviewQueueCards.filter((card) => normalizeInboxToken(card.rating) === "high");
  }
  if (filter === "new_changed") {
    return reviewQueueCards.filter(
      (card) => ["new", "changed"].includes(normalizeInboxToken(card.decision_status)) && normalizeInboxToken(card.rating) !== "low",
    );
  }
  if (filter === "medium") {
    return reviewQueueCards.filter((card) => normalizeInboxToken(card.rating) === "medium");
  }
  if (filter === "low") {
    return reviewQueueCards.filter((card) => normalizeInboxToken(card.rating) === "low");
  }
  if (filter === "low_medium") {
    return reviewQueueCards.filter((card) => ["low", "medium"].includes(normalizeInboxToken(card.rating)));
  }
  if (filter === "saved") {
    return cards.filter((card) => normalizeInboxToken(card.opportunity_status) === "saved");
  }
  if (filter === "handled") {
    return cards.filter((card) => {
      const opportunityStatus = normalizeInboxToken(card.opportunity_status || "open");
      const reviewStatus = normalizeInboxToken(card.status || "pending");
      return ["applied", "contacted", "dismissed"].includes(opportunityStatus) || (opportunityStatus === "open" && reviewStatus !== "pending");
    });
  }
  if (filter === "duplicate") {
    return cards.filter((card) => normalizeInboxToken(card.opportunity_status) === "duplicate");
  }
  return cards;
}

export function countInboxCardsByRating<T extends InboxCardLike>(cards: T[], rating: "high" | "medium" | "low") {
  return cards.filter((card) => normalizeInboxToken(card.rating) === rating).length;
}

export function inboxFilterOptions<T extends InboxCardLike>(cards: T[], latestRunId?: string) {
  const baseOptions = [
    { id: "actionable" as const, label: "Priority now", count: filterInboxCards(cards, "actionable", latestRunId).length },
    { id: "all" as const, label: "All cards", count: cards.length },
    { id: "new_changed" as const, label: "New/Updated", count: filterInboxCards(cards, "new_changed", latestRunId).length },
    { id: "medium" as const, label: "Middle", count: filterInboxCards(cards, "medium", latestRunId).length },
    { id: "low" as const, label: "Low", count: filterInboxCards(cards, "low", latestRunId).length },
  ];
  return [
    ...baseOptions,
    { id: "saved" as const, label: "Saved", count: filterInboxCards(cards, "saved", latestRunId).length },
    { id: "handled" as const, label: "Handled", count: filterInboxCards(cards, "handled", latestRunId).length },
    { id: "duplicate" as const, label: "Duplicate", count: filterInboxCards(cards, "duplicate", latestRunId).length },
  ].filter((option) => !["saved", "handled", "duplicate"].includes(option.id) || option.count > 0);
}

export function setupNeedsAttention(checks: SetupCheckLike[]) {
  return checks.some((check) => ["active", "blocked"].includes(String(check.status || "")));
}

export function setupCheckTone(status: string) {
  if (status === "done") {
    return "done";
  }
  if (status === "blocked") {
    return "blocked";
  }
  if (status === "active") {
    return "active";
  }
  return "todo";
}

export function setupCheckLabel(status: string) {
  if (status === "done") {
    return "Done";
  }
  if (status === "blocked") {
    return "Blocked";
  }
  if (status === "active") {
    return "Next";
  }
  return "Later";
}

export function telegramMessageUrl(ref: SourceRefLike) {
  const channel = String(ref.channel || "").trim().replace(/^@+/, "");
  const id = String(ref.id || "").trim();
  if (!/^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(channel) || !/^\d+$/.test(id)) {
    return "";
  }
  return `https://t.me/${channel}/${id}`;
}

export function telegramChannelUrl(ref: SourceRefLike) {
  const channel = String(ref.channel || "").trim().replace(/^@+/, "");
  if (!/^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(channel)) {
    return "";
  }
  return `https://t.me/${channel}`;
}

export function sourceRefUrl(ref: SourceRefLike) {
  const explicit = typeof ref.url === "string" ? ref.url.trim() : "";
  if (/^https:\/\/t\.me\/[A-Za-z0-9_+/.-]+$/i.test(explicit)) {
    return explicit;
  }
  return telegramMessageUrl(ref) || telegramChannelUrl(ref);
}
