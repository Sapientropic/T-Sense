import { type CSSProperties } from "react";

import { StatusLine } from "./common";
import {
  opportunityDetail,
  opportunityHeadline,
  opportunityTone,
  percentWidth,
} from "../domain/display";
import { profileDisplayName } from "../domain/format";
import { handledInboxCount, reviewQueueCount } from "../domain/inbox";
import type { DashboardState, Metric, OpportunitySummary, ReviewCard, ValidationSummary } from "../domain/types";

export function OpportunitySummaryPanel({
  summary,
  latestPriorityCount,
}: {
  summary?: OpportunitySummary;
  latestPriorityCount?: number;
}) {
  if (!summary || summary.status === "no_runs") {
    return null;
  }
  const displaySummary = opportunityDisplaySummary(summary, latestPriorityCount);
  const tone = opportunityTone(displaySummary);
  const nextActionLabel = opportunityNextActionLabel(displaySummary.next_action?.label);
  return (
    <section className={`signal-brief ${tone}`} aria-label="Latest run opportunity summary">
      <div className="signal-brief-lede">
        <span className="panel-kicker">{displaySummary.display_name || profileDisplayName(displaySummary.profile_id || "profile")}</span>
        <strong>{opportunityHeadline(displaySummary)}</strong>
        <small>{opportunityDetail(displaySummary)}</small>
      </div>
      <OpportunityFunnel summary={displaySummary} />
      {displaySummary.next_action && (
        <div className="signal-next-action" aria-label="Recommended next action">
          <span className="panel-kicker">Next</span>
          <strong>{nextActionLabel || "Review run"}</strong>
          <DecisionMemoryLine counts={displaySummary.decision_counts} />
        </div>
      )}
    </section>
  );
}

function opportunityDisplaySummary(summary: OpportunitySummary, latestPriorityCount?: number): OpportunitySummary {
  if (typeof latestPriorityCount !== "number" || hasBlockingOpportunitySummary(summary)) {
    return summary;
  }
  const originalCount = summary.high_actionable_count ?? 0;
  if (latestPriorityCount === originalCount) {
    return summary;
  }
  const nextAction =
    latestPriorityCount === 0 && isPriorityReviewAction(summary.next_action?.label) ? undefined : summary.next_action;
  return {
    ...summary,
    high_actionable_count: latestPriorityCount,
    all_clear: latestPriorityCount === 0 ? true : summary.all_clear,
    next_action: nextAction,
  };
}

function hasBlockingOpportunitySummary(summary: OpportunitySummary) {
  return (summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed";
}

function isPriorityReviewAction(label?: string) {
  const normalized = opportunityNextActionLabel(label);
  return normalized === "Review priority cards";
}

function OpportunityFunnel({ summary }: { summary: OpportunitySummary }) {
  const steps = [
    { label: "Scanned", value: summary.scanned_count ?? 0, tone: "teal" },
    { label: "Matched", value: summary.matched_count ?? 0, tone: "amber" },
    { label: "Cards", value: summary.review_card_count ?? 0, tone: "blue" },
    { label: "Priority", value: summary.high_actionable_count ?? 0, tone: "rust" },
  ];
  const maxValue = Math.max(1, ...steps.map((step) => step.value));
  return (
    <div className="signal-funnel" aria-label="Latest run funnel">
      {steps.map((step) => (
        <div className={`signal-funnel-step ${step.tone}`} key={step.label}>
          <span>{step.label}</span>
          <i aria-hidden="true">
            <b style={{ width: percentWidth(step.value / maxValue) }} />
          </i>
          <strong>{step.value}</strong>
        </div>
      ))}
    </div>
  );
}

function DecisionMemoryLine({ counts }: { counts?: Record<string, number> }) {
  if (!counts) {
    return null;
  }
  const entries = [
    ["New", counts.new ?? 0],
    ["Updated", counts.changed ?? 0],
    ["Seen", counts.seen ?? 0],
    ["Repeated", counts.recurring ?? 0],
  ].filter(([, value]) => Number(value) > 0);
  if (!entries.length) {
    return null;
  }
  return (
    <div className="signal-memory" aria-label="Decision memory counts">
      {entries.map(([label, value]) => (
        <span key={label}>
          {String(label)} {String(value)}
        </span>
      ))}
    </div>
  );
}

export function ValidationSummaryPanel({ cards = [], summary }: { cards?: ReviewCard[]; summary?: ValidationSummary }) {
  if (!summary) {
    return null;
  }
  const currentQueueCount = cards.length ? reviewQueueCount(cards) : summary.pending_count ?? 0;
  const currentHandledCount = cards.length ? handledInboxCount(cards) : Math.max(0, (summary.card_count ?? 0) - (summary.pending_count ?? 0));
  const currentTotal = cards.length || summary.card_count || currentHandledCount + currentQueueCount;
  const actions = Object.entries(summary.by_action ?? {}).filter(([, count]) => count > 0);
  const firstDecision = firstDecisionLabel(summary);
  const display = validationDisplayCopy(summary, currentQueueCount, currentHandledCount);
  const keepRate = validationKeepRate(summary);
  return (
    <details className="validation-brief" aria-label="Local validation summary">
      <summary>
        <div className="validation-copy">
          <span className="panel-kicker">{summary.window_days ?? 14} day review window</span>
          <strong>{display.title}</strong>
          <small>{display.detail}</small>
        </div>
        <span className="validation-disclosure-label">Details</span>
      </summary>
      <div className="validation-body" data-compact={actions.length > 0 ? "false" : "true"}>
        <div className="validation-stats">
          <StatusLine label="Handled" value={`${currentHandledCount}/${currentTotal}`} />
          {keepRate && <StatusLine label="Keep rate" value={keepRate} />}
          {(summary.high_card_count ?? 0) > 0 && <StatusLine label="High cards" value={String(summary.high_card_count ?? 0)} />}
          {firstDecision !== "Waiting" && <StatusLine label="First action" value={firstDecision} />}
        </div>
        {actions.length > 0 && (
          <div className="validation-gauges compact" aria-label="Learning choice breakdown">
            {actions.map(([action, count]) => (
              <span key={action}>
                {validationActionLabel(action)} {count}
              </span>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

function validationDisplayCopy(summary: ValidationSummary, queueCount: number, handledCount: number) {
  if (queueCount === 0 && handledCount > 0) {
    return {
      title: "All review cards handled",
      detail: `${handledCount} handled card${handledCount === 1 ? "" : "s"} saved as history.`,
    };
  }
  const nextActionDetail = validationNextActionDetail(summary.next_action?.detail);
  return {
    title: summary.next_action?.label || "Track real outcomes",
    detail: nextActionDetail || `${queueCount} card${queueCount === 1 ? "" : "s"} still need review.`,
  };
}

function validationKeepRate(summary: ValidationSummary) {
  const actionCount = summary.action_count ?? 0;
  if (actionCount <= 0 && typeof summary.keep_rate !== "number") {
    return "";
  }
  const rawRate =
    typeof summary.keep_rate === "number"
      ? summary.keep_rate
      : actionCount > 0
        ? (summary.by_action?.keep ?? 0) / actionCount
        : 0;
  const boundedRate = Math.max(0, Math.min(1, rawRate));
  return `${Math.round(boundedRate * 100)}%`;
}

function validationActionLabel(action: string) {
  const labels: Record<string, string> = {
    false_positive: "Wrong match",
    follow_up: "Profile draft",
    keep: "Preferred",
    skip: "Deprioritized",
  };
  return labels[action] || action.replace(/_/g, " ");
}

function opportunityNextActionLabel(label?: string) {
  const normalized = String(label || "").trim();
  if (normalized === "Review action signals") {
    return "Review priority cards";
  }
  return normalized;
}

function validationNextActionDetail(detail?: string) {
  const normalized = String(detail || "").trim();
  if (normalized === "Mark keep, skip, false positive, or follow-up so the validation window has behavior evidence.") {
    return "Mark what happened so future matches improve.";
  }
  return normalized;
}

function firstDecisionLabel(summary: ValidationSummary) {
  if (typeof summary.first_decision_minutes !== "number") {
    return (summary.runs_count ?? 0) > 0 ? "Waiting" : "Not started";
  }
  const minutes = Math.max(0, Math.round(summary.first_decision_minutes));
  const timing = minutes < 1 ? "<1 min" : `${minutes} min`;
  const action = summary.first_decision_action?.trim().replace(/_/g, " ");
  return action ? `${timing} (${action})` : timing;
}

export function CommandStrip({ state, metrics }: { state: DashboardState; metrics: Metric[] }) {
  const queueCount = reviewQueueCount(state.inbox);
  const handledCount = handledInboxCount(state.inbox);
  const pulseWidth = queueCount ? Math.min(100, Math.max(8, queueCount * 18)) : 0;
  return (
    <section className="command-strip" aria-label="Dashboard status">
      <div className="pulse-panel">
        <span className="panel-kicker">Review queue</span>
        <strong>{queueCount}</strong>
        <small>{queueCount ? "cards to decide" : handledCount ? `${handledCount} handled` : "queue clear"}</small>
        <div className="pulse-meter" style={{ "--pulse": `${pulseWidth}%` } as CSSProperties} aria-hidden="true">
          <span />
        </div>
      </div>
      <div className="metric-grid">
        {metrics.map((metric) => (
          <MetricTile key={metric.label} metric={metric} />
        ))}
      </div>
    </section>
  );
}

function MetricTile({ metric }: { metric: Metric }) {
  return (
    <article className={`metric-tile ${metric.tone}`} title={metric.detail}>
      <span>{metric.label}</span>
      <strong>{metric.value}</strong>
      {typeof metric.meter === "number" && (
        <div className="metric-tile-meter" style={{ "--meter": percentWidth(metric.meter) } as CSSProperties} aria-hidden="true">
          <i />
        </div>
      )}
    </article>
  );
}
