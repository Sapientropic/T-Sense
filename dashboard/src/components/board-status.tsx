import { type CSSProperties } from "react";

import { CopyableCommand, StatusLine } from "./common";
import {
  opportunityDetail,
  opportunityHeadline,
  opportunityTone,
  percentWidth,
  ratio,
} from "../domain/display";
import { profileDisplayName } from "../domain/format";
import type { DashboardState, Metric, OpportunitySummary, ValidationSummary } from "../domain/types";

export function OpportunitySummaryPanel({ summary }: { summary?: OpportunitySummary }) {
  if (!summary || summary.status === "no_runs") {
    return null;
  }
  const tone = opportunityTone(summary);
  return (
    <section className={`signal-brief ${tone}`} aria-label="Latest run opportunity summary">
      <div className="signal-brief-lede">
        <span className="panel-kicker">{summary.display_name || profileDisplayName(summary.profile_id || "profile")}</span>
        <strong>{opportunityHeadline(summary)}</strong>
        <small>{opportunityDetail(summary)}</small>
      </div>
      <OpportunityFunnel summary={summary} />
      {summary.next_action && (
        <div className="signal-next-action" aria-label="Recommended next action">
          <span className="panel-kicker">Next</span>
          <strong>{summary.next_action.label || "Review run"}</strong>
          <DecisionMemoryLine counts={summary.decision_counts} />
          {summary.next_action.command && (
            <div className="signal-command">
              <CopyableCommand command={summary.next_action.command} label="next action" compact iconOnly />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function OpportunityFunnel({ summary }: { summary: OpportunitySummary }) {
  const steps = [
    { label: "Scanned", value: summary.scanned_count ?? 0, tone: "teal" },
    { label: "Matched", value: summary.matched_count ?? 0, tone: "amber" },
    { label: "Cards", value: summary.review_card_count ?? 0, tone: "blue" },
    { label: "Action", value: summary.high_actionable_count ?? 0, tone: "rust" },
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
    ["new", counts.new ?? 0],
    ["changed", counts.changed ?? 0],
    ["seen", counts.seen ?? 0],
    ["recurring", counts.recurring ?? 0],
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

export function ValidationSummaryPanel({ summary }: { summary?: ValidationSummary }) {
  if (!summary) {
    return null;
  }
  const actions = Object.entries(summary.by_action ?? {}).filter(([, count]) => count > 0);
  return (
    <details className="validation-brief" aria-label="Local validation summary">
      <summary>
        <div className="validation-copy">
          <span className="panel-kicker">{summary.window_days ?? 14} day proof loop</span>
          <strong>{summary.next_action?.label || "Track real outcomes"}</strong>
          <small>{summary.next_action?.detail || "Keep behavior evidence local and note-free."}</small>
        </div>
        <span className="validation-disclosure-label">Evidence</span>
      </summary>
      <div className="validation-body">
        <div className="validation-stats">
          <StatusLine label="Runs" value={String(summary.runs_count ?? 0)} />
          <StatusLine label="High" value={String(summary.high_card_count ?? 0)} />
          <StatusLine label="Actions" value={String(summary.action_count ?? 0)} />
          <StatusLine label="Pending" value={String(summary.pending_count ?? 0)} />
        </div>
        <div className="validation-gauges" aria-label="Validation behavior rates">
          <ValidationGauge
            label="Reviewed"
            value={summary.triage_rate ?? ratio(summary.action_count, summary.card_count)}
            detail={`${summary.action_count ?? 0}/${summary.card_count ?? 0}`}
          />
          <ValidationGauge
            label="Keep rate"
            value={summary.keep_rate ?? 0}
            detail={`${Math.round((summary.keep_rate ?? 0) * 100)}%`}
          />
          {actions.length ? (
            actions.map(([action, count]) => (
              <span key={action}>
                {action.replace(/_/g, " ")} {count}
              </span>
            ))
          ) : (
            <span>No labeled actions yet</span>
          )}
        </div>
      </div>
    </details>
  );
}

export function CommandStrip({ state, metrics }: { state: DashboardState; metrics: Metric[] }) {
  const pulseWidth = Math.min(100, Math.max(8, state.inbox.length * 18));
  return (
    <section className="command-strip" aria-label="Dashboard status">
      <div className="pulse-panel">
        <span className="panel-kicker">Queue Pulse</span>
        <strong>{state.inbox.length}</strong>
        <small>{state.inbox.length ? "cards need review" : "queue clear"}</small>
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

function ValidationGauge({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="validation-gauge" aria-label={`${label}: ${detail}`}>
      <span>{label}</span>
      <div style={{ "--gauge": percentWidth(value) } as CSSProperties}>
        <i />
      </div>
      <strong>{detail}</strong>
    </div>
  );
}
