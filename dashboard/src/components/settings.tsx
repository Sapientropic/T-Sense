import { type CSSProperties } from "react";
import { Activity, Download, Settings, ShieldCheck } from "lucide-react";

import { CopyableCommand, InlineEmpty, PanelHeader } from "./common";
import {
  deliveryTargetDetail,
  deliveryTargetName,
  feedbackImpactKey,
  formatActionLabel,
  metricShortLabel,
  percentWidth,
  sourceHeatClass,
  sourceSignalScore,
  toneClass,
} from "../domain/display";
import { channelDisplayName, formatPercent } from "../domain/format";
import type {
  DashboardNextAction,
  DashboardState,
  DeliveryTarget,
  FeedbackExportResult,
  FeedbackImpact,
  SourceInsight,
  SourceStat,
} from "../domain/types";

const SOURCE_CARD_LIMIT = 3;
const SOURCE_HEAT_LIMIT = 72;
const SOURCE_ACTION_LIMIT = 6;
const FEEDBACK_IMPACT_LIMIT = 4;

export function SettingsView({
  targets,
  sourceStats,
  sourceInsights,
  feedbackSummary,
  feedbackExport,
  exportFeedback,
  busy,
}: {
  targets: DeliveryTarget[];
  sourceStats: SourceStat[];
  sourceInsights: SourceInsight[];
  feedbackSummary?: DashboardState["feedback_summary"];
  feedbackExport: FeedbackExportResult | null;
  exportFeedback: () => void;
  busy: boolean;
}) {
  const exportableCount = feedbackSummary?.exportable_count ?? feedbackExport?.feedback_count ?? 0;
  return (
    <section className="split-section settings-grid" aria-label="Delivery and source settings">
      <div className="table-section delivery-targets-panel">
        <PanelHeader icon={<Settings size={18} />} title="Delivery Targets" count={targets.length} />
        {targets.length ? (
          <div className="table-list">
            {targets.map((target) => (
              <div className="table-row target-row" key={target.target_id}>
                <strong title={target.display_name || deliveryTargetName(target)}>
                  {target.display_name || deliveryTargetName(target)}
                </strong>
                <span className={target.enabled ? "status enabled" : "status disabled"}>
                  {target.status_label || (target.enabled ? "Live" : "Muted")}
                </span>
                <small>{target.detail || deliveryTargetDetail(target)}</small>
              </div>
            ))}
          </div>
        ) : (
          <InlineEmpty title="No delivery targets registered" />
        )}
      </div>
      <div className="table-section source-yield-panel">
        <PanelHeader icon={<Activity size={18} />} title="Yield History" count={sourceStats.length} />
        {sourceStats.length ? <SourceYieldMap sources={sourceStats} /> : <InlineEmpty title="No source stats yet" />}
      </div>
      <div className="table-section feedback-export-panel">
        <PanelHeader icon={<Download size={18} />} title="Feedback Export" count={exportableCount} />
        <FeedbackBreakdown summary={feedbackSummary} exportableCount={exportableCount} />
        {feedbackSummary?.next_action && <FeedbackNextAction action={feedbackSummary.next_action} />}
        <FeedbackFlow summary={feedbackSummary} />
        <FeedbackImpactList impacts={feedbackSummary?.recent_impacts ?? []} />
        <div className="feedback-export-row">
          <button className="text-button" type="button" onClick={exportFeedback} disabled={busy}>
            <Download size={15} />
            <span>{busy ? "Exporting" : "Export feedback file"}</span>
          </button>
          <span className="artifact-chip" title="Saved under Feedback exports">
            Feedback export file
          </span>
        </div>
      </div>
      <div className="table-section source-actions-panel">
        <PanelHeader icon={<ShieldCheck size={18} />} title="Source Actions" count={sourceInsights.length} />
        {sourceInsights.length ? <SourceActionGrid insights={sourceInsights} /> : <InlineEmpty title="No source actions yet" />}
      </div>
    </section>
  );
}

function SourceYieldMap({ sources }: { sources: SourceStat[] }) {
  const visibleSources = sources.slice(0, SOURCE_CARD_LIMIT);
  const heatSources = sources.slice(0, SOURCE_HEAT_LIMIT);
  const activeCount = sources.filter((source) => (source.card_count ?? 0) > 0 || (source.latest_card_count ?? 0) > 0).length;
  const hotCount = sources.filter((source) => (source.high_count ?? 0) > 0).length;
  const riskCount = sources.filter((source) => source.scan_failure || source.scan_incomplete).length;
  return (
    <div className="source-yield-map" aria-label="Source yield map">
      <div className="source-heat-panel" aria-label="Source signal heat map">
        <div className="source-heat-grid">
          {heatSources.map((source) => (
            <span
              className={`source-heat-cell ${sourceHeatClass(source)}`}
              key={source.channel}
              title={`${source.display_name || channelDisplayName(source.channel)} · ${source.high_count} high · ${source.card_count} cards`}
              style={{ "--heat": percentWidth(sourceSignalScore(source)) } as CSSProperties}
            />
          ))}
        </div>
        <div className="source-heat-legend">
          <strong>{sources.length}</strong>
          <span>sources</span>
          <small>
            {hotCount} hot / {activeCount} active{riskCount ? ` / ${riskCount} risk` : ""}
          </small>
        </div>
      </div>
      {visibleSources.map((source) => (
        <article
          className={`source-yield-card ${source.scan_failure ? "risk" : ""} ${source.high_count ? "" : "zero"}`}
          key={source.channel}
        >
          <div className="source-yield-head">
            <SourceChannelCell source={source} />
            <span className="source-yield-score" title={`${source.high_count} high-signal cards`}>
              <strong>{source.high_count}</strong>
              <small>high</small>
            </span>
          </div>
          <div className="source-bars">
            <MetricBar
              label="Latest kept"
              value={source.scan_keep_rate ?? 0}
              detail={`${source.kept_count ?? 0}/${source.raw_count ?? 0}`}
            />
            <MetricBar label="Card yield" value={source.card_yield_rate ?? 0} detail={formatPercent(source.card_yield_rate ?? 0)} />
          </div>
          <div className="source-mini-stats">
            <SourceMiniStats
              emptyLabel="quiet"
              items={[
                { label: "cards", value: source.latest_card_count ?? source.card_count },
                { label: "alerts", value: source.alert_count },
                { label: "false", value: source.false_positive_count },
              ]}
            />
          </div>
        </article>
      ))}
    </div>
  );
}

function MetricBar({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <div className="metric-line" aria-label={`${label}: ${detail}`} title={`${label}: ${detail}`}>
      <span className="metric-label">{metricShortLabel(label)}</span>
      <div className={`metric-bar ${value <= 0 ? "empty" : ""}`}>
        <span style={{ width: percentWidth(value) }} />
      </div>
      <span className="metric-detail">{detail}</span>
    </div>
  );
}

function FeedbackFlow({ summary }: { summary?: DashboardState["feedback_summary"] }) {
  return (
    <div className="feedback-flow" aria-label="Feedback learning flow">
      <span title="Ready for note-free feedback export">
        <strong>{summary?.exportable_count ?? 0}</strong>
        export
      </span>
      <span title="Profile diffs waiting for review">
        <strong>{summary?.pending_profile_diff_count ?? 0}</strong>
        diff
      </span>
      <span title="Applied profile diffs">
        <strong>{summary?.applied_profile_diff_count ?? 0}</strong>
        applied
      </span>
    </div>
  );
}

function FeedbackBreakdown({
  summary,
  exportableCount,
}: {
  summary?: DashboardState["feedback_summary"];
  exportableCount: number;
}) {
  const items = [
    { label: "Keep", value: summary?.by_action?.keep ?? 0 },
    { label: "Skip", value: summary?.by_action?.skip ?? 0 },
    { label: "False", value: summary?.by_action?.false_positive ?? 0 },
    { label: "Diff", value: summary?.non_exportable_follow_up_count ?? 0 },
    { label: "High", value: summary?.by_rating?.high ?? 0 },
    { label: "Changed", value: summary?.by_decision_status?.changed ?? 0 },
  ].filter((item) => item.value > 0);
  if (!items.length) {
    return (
      <InlineEmpty
        title={exportableCount > 0 ? "Feedback rows need action labels" : "No feedback actions yet"}
      />
    );
  }
  return (
    <div className="feedback-breakdown" aria-label="Feedback action counts">
      {items.map((item) => (
        <span className={item.value > 0 ? "" : "muted"} key={item.label}>
          {item.label} {item.value}
        </span>
      ))}
    </div>
  );
}

function SourceActionGrid({ insights }: { insights: SourceInsight[] }) {
  const visible = insights.slice(0, SOURCE_ACTION_LIMIT);
  const hiddenCount = Math.max(0, insights.length - visible.length);
  return (
    <div className="insight-list">
      {visible.map((insight, index) => (
        <article className={`source-insight ${insight.kind}`} key={`${insight.kind}-${insight.channel}-${index}`}>
          <div className="source-insight-head">
            <span className={`status ${insight.kind}`}>{insight.label}</span>
            <small>{insight.confidence || "medium"}</small>
          </div>
          <strong title={`@${insight.channel}`}>{insight.display_name || channelDisplayName(insight.channel)}</strong>
          <div className="source-insight-bars">
            <MetricBar
              label="Latest kept"
              value={insight.stats.scan_keep_rate ?? 0}
              detail={`${insight.stats.kept_count ?? 0}/${insight.stats.raw_count ?? 0}`}
            />
            <MetricBar
              label="High-rate"
              value={insight.stats.high_rate ?? 0}
              detail={formatPercent(insight.stats.high_rate ?? 0)}
            />
          </div>
          <div
            className="source-next-action"
            title={insight.next_action?.detail || insight.reason}
            aria-label={`${insight.next_action?.label || "Review source"}: ${insight.next_action?.detail || insight.reason}`}
          >
            {insight.next_action?.command ? (
              <CopyableCommand
                command={insight.next_action.command}
                label={`${insight.display_name || channelDisplayName(insight.channel)} source action`}
                compact
              />
            ) : (
              <span>{insight.next_action?.label || "Review source"}</span>
            )}
          </div>
          <div className="source-mini-stats">
            <SourceMiniStats
              emptyLabel="no noise"
              items={[
                { label: "high", value: insight.stats.high_count },
                { label: "cards", value: insight.stats.latest_card_count ?? insight.stats.card_count },
                { label: "false", value: insight.stats.false_positive_count },
              ]}
            />
          </div>
        </article>
      ))}
      {hiddenCount > 0 && <div className="list-overflow-note">+{hiddenCount} more source actions queued</div>}
    </div>
  );
}

function FeedbackNextAction({ action }: { action: DashboardNextAction }) {
  return (
    <div className="feedback-next-action" aria-label="Feedback next action">
      <span className="panel-kicker">Learning loop</span>
      <strong>{action.label || "Collect feedback"}</strong>
      {action.detail && <small>{action.detail}</small>}
      {action.command && <CopyableCommand command={action.command} label="feedback next action" compact />}
    </div>
  );
}

function FeedbackImpactList({ impacts }: { impacts: FeedbackImpact[] }) {
  const visible = impacts.slice(0, FEEDBACK_IMPACT_LIMIT);
  const hiddenCount = Math.max(0, impacts.length - visible.length);
  if (!visible.length) {
    return <InlineEmpty title="No feedback impact yet" />;
  }
  return (
    <div className="feedback-impact-list" aria-label="Recent feedback impact">
      {visible.map((impact, index) => (
        <article className={`feedback-impact ${toneClass(impact.impact_status || "unknown")}`} key={feedbackImpactKey(impact, index)}>
          <span>{impact.impact_label || "Feedback recorded"}</span>
          <strong>{impact.item_title || "Review card"}</strong>
          <small>
            {formatActionLabel(impact.action || "feedback")} / {impact.rating || "unknown"} /{" "}
            {impact.decision_status || "unknown"}
          </small>
        </article>
      ))}
      {hiddenCount > 0 && <div className="list-overflow-note">+{hiddenCount} more feedback impacts saved</div>}
    </div>
  );
}

function SourceMiniStats({
  items,
  emptyLabel,
}: {
  items: Array<{ label: string; value?: number | null }>;
  emptyLabel: string;
}) {
  const visible = items.filter((item) => (item.value ?? 0) > 0);
  if (!visible.length) {
    return <span className="muted">{emptyLabel}</span>;
  }
  return (
    <>
      {visible.map((item) => (
        <span key={item.label}>
          {item.value} {item.label}
        </span>
      ))}
    </>
  );
}

function SourceChannelCell({ source }: { source: SourceStat }) {
  return (
    <div className="source-channel-cell">
      <strong title={`@${source.channel}`}>{source.display_name || channelDisplayName(source.channel)}</strong>
      {(source.scan_failure || source.scan_incomplete) && (
        <span className={source.scan_failure ? "source-risk-badge failure" : "source-risk-badge incomplete"}>
          {source.scan_failure ? "Access" : "Incomplete"}
        </span>
      )}
    </div>
  );
}
