import type { CSSProperties } from "react";
import { ListChecks, Settings2, ShieldCheck } from "lucide-react";

import { InlineEmpty, PanelHeader } from "../common";
import { metricShortLabel, percentWidth, sourceHeatClass, sourceSignalScore } from "../../domain/display";
import { channelDisplayName, formatPercent } from "../../domain/format";
import type { SourceInsight, SourceStat } from "../../domain/types";

const SOURCE_CARD_LIMIT = 3;
const SOURCE_HEAT_LIMIT = 72;
const SOURCE_ACTION_LIMIT = 6;

export function SourceInsightsPanel({
  sourceStats,
  sourceInsights,
  onManageSources,
  onReviewCards,
}: {
  sourceStats: SourceStat[];
  sourceInsights: SourceInsight[];
  onManageSources?: () => void;
  onReviewCards?: () => void;
}) {
  return (
    <details className="table-section source-recommendations-panel" aria-label="Source recommendations">
      <summary>
        <PanelHeader icon={<ShieldCheck size={18} />} title="Source recommendations" count={sourceInsights.length} />
      </summary>
      <div className="source-recommendations-body">
        <p className="delivery-note">Use recent scan results to decide which saved channels need review or cleanup.</p>
        <div className="source-recommendation-actions">
          <button className="text-button secondary" disabled={!onReviewCards} onClick={onReviewCards} type="button">
            <ListChecks size={15} />
            <span>Review cards</span>
          </button>
          <button className="text-button secondary" disabled={!onManageSources} onClick={onManageSources} type="button">
            <Settings2 size={15} />
            <span>Manage sources</span>
          </button>
        </div>
        <div className="settings-evidence-grid">
          {sourceStats.length ? <SourceYieldMap sources={sourceStats} /> : <InlineEmpty title="No source stats yet" />}
          {sourceInsights.length ? (
            <SourceActionGrid insights={sourceInsights} onManageSources={onManageSources} onReviewCards={onReviewCards} />
          ) : (
            <InlineEmpty title="No source changes suggested" />
          )}
        </div>
      </div>
    </details>
  );
}

function SourceYieldMap({ sources }: { sources: SourceStat[] }) {
  const visibleSources = sources.slice(0, SOURCE_CARD_LIMIT);
  const heatSources = sources.slice(0, SOURCE_HEAT_LIMIT);
  const activeCount = sources.filter((source) => (source.card_count ?? 0) > 0 || (source.latest_card_count ?? 0) > 0).length;
  const hotCount = sources.filter((source) => (source.high_count ?? 0) > 0).length;
  const riskCount = sources.filter((source) => source.scan_failure || source.scan_incomplete).length;
  return (
    <div className="source-yield-map" aria-label="Source activity map">
      <div className="source-heat-panel" aria-label="Source signal map">
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
            <MetricBar label="Found rate" value={source.card_yield_rate ?? 0} detail={formatPercent(source.card_yield_rate ?? 0)} />
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

function SourceActionGrid({
  insights,
  onManageSources,
  onReviewCards,
}: {
  insights: SourceInsight[];
  onManageSources?: () => void;
  onReviewCards?: () => void;
}) {
  const visible = insights.slice(0, SOURCE_ACTION_LIMIT);
  const hiddenCount = Math.max(0, insights.length - visible.length);
  return (
    <div className="insight-list">
      {visible.map((insight, index) => (
        <article className={`source-insight ${insight.kind}`} key={`${insight.kind}-${insight.channel}-${index}`}>
          <div className="source-insight-head">
            <span className={`status ${insight.kind}`}>{sourceInsightLabel(insight)}</span>
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
              label="High rate"
              value={insight.stats.high_rate ?? 0}
              detail={formatPercent(insight.stats.high_rate ?? 0)}
            />
          </div>
          <button
            className="source-next-action"
            disabled={insight.kind === "promote" ? !onReviewCards : !onManageSources}
            onClick={insight.kind === "promote" ? onReviewCards : onManageSources}
            title={insight.next_action?.detail || insight.reason}
            aria-label={`${sourceInsightButtonLabel(insight)}: ${insight.next_action?.detail || insight.reason}`}
            type="button"
          >
            {insight.kind === "promote" ? <ListChecks size={14} /> : <Settings2 size={14} />}
            <span>{sourceInsightButtonLabel(insight)}</span>
          </button>
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

function sourceInsightLabel(insight: SourceInsight) {
  if (insight.kind === "promote") {
    return "Good source";
  }
  if (insight.kind === "prune") {
    return "Needs cleanup";
  }
  if (insight.kind === "observe") {
    return "More data";
  }
  return insight.label || "Review source";
}

function sourceInsightButtonLabel(insight: SourceInsight) {
  return insight.kind === "promote" ? "Review cards" : "Manage sources";
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
