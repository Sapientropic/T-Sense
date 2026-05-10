export type InboxFilter = "actionable" | "all" | "high" | "new_changed" | "low_medium";

export type InboxCardLike = {
  rating?: unknown;
  decision_status?: unknown;
  last_run_id?: string | null;
};

export type SetupCheckLike = {
  status?: unknown;
};

export type SourceRefLike = {
  channel?: unknown;
  id?: unknown;
};

function normalizeInboxToken(value: unknown) {
  return typeof value === "string" ? value.toLowerCase() : "";
}

export function isMalformedInboxCard(card: InboxCardLike) {
  return [card.rating, card.decision_status].some(
    (value) => value !== null && value !== undefined && typeof value !== "string",
  );
}

export function isActionableInboxCard(card: InboxCardLike, latestRunId?: string) {
  const isLatest = latestRunId ? card.last_run_id === latestRunId : true;
  return (
    isLatest &&
    normalizeInboxToken(card.rating) === "high" &&
    ["new", "changed"].includes(normalizeInboxToken(card.decision_status))
  );
}

export function filterInboxCards<T extends InboxCardLike>(cards: T[], filter: InboxFilter, latestRunId?: string) {
  if (filter === "actionable") {
    return cards.filter((card) => isActionableInboxCard(card, latestRunId));
  }
  if (filter === "high") {
    return cards.filter((card) => normalizeInboxToken(card.rating) === "high");
  }
  if (filter === "new_changed") {
    return cards.filter((card) => ["new", "changed"].includes(normalizeInboxToken(card.decision_status)));
  }
  if (filter === "low_medium") {
    return cards.filter((card) => ["low", "medium"].includes(normalizeInboxToken(card.rating)));
  }
  return cards;
}

export function countInboxCardsByRating<T extends InboxCardLike>(cards: T[], rating: "high" | "medium" | "low") {
  return cards.filter((card) => normalizeInboxToken(card.rating) === rating).length;
}

export function inboxFilterOptions<T extends InboxCardLike>(cards: T[], latestRunId?: string) {
  return [
    { id: "actionable" as const, label: "Latest action", count: filterInboxCards(cards, "actionable", latestRunId).length },
    { id: "all" as const, label: "All", count: cards.length },
    { id: "high" as const, label: "High", count: filterInboxCards(cards, "high", latestRunId).length },
    { id: "new_changed" as const, label: "New/Changed", count: filterInboxCards(cards, "new_changed", latestRunId).length },
    { id: "low_medium" as const, label: "Low/Medium", count: filterInboxCards(cards, "low_medium", latestRunId).length },
  ];
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
