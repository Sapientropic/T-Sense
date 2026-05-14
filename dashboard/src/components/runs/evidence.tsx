import { useState, type CSSProperties } from "react";
import { ExternalLink } from "lucide-react";

import {
  artifactDisplayName,
  artifactHref,
  artifactShortDetail,
  artifactShortLabel,
  diagnosticTone,
  percentWidth,
  runDisplayDetail,
  runDisplayTitle,
  toneClass,
} from "../../domain/display";
import { formatRunDiagnostics, runHealthDetail } from "../../domain/projections";
import { historicalRunOutcome, type RunEvidenceCluster, type RunEvidenceGroup } from "./model";

export function RunEvidenceGroupPanel({ group, scaleMax }: { group: RunEvidenceGroup; scaleMax: number }) {
  const [open, setOpen] = useState(() => shouldOpenRunEvidenceByDefault());
  const historyOnly = group.key === "attention" && group.tone !== "danger";
  return (
    <details
      aria-label={group.title}
      className={`run-evidence-group is-${group.tone}`}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary className="run-evidence-head">
        <strong>{group.title}</strong>
        <span>{group.detail}</span>
        <b>{open ? "Collapse" : "View"}</b>
      </summary>
      <div className="run-evidence-body">
        {group.key === "attention" && (
          <p className="run-evidence-next">
            {group.tone === "danger"
              ? runEvidenceRepairPrompt(group.repairKind)
              : "Latest scan recovered. These older failures are kept only for troubleshooting history."}
          </p>
        )}
        <div className="table-list">
          {group.clusters.map((cluster) => (
            <RunClusterRow key={cluster.key} cluster={cluster} scaleMax={scaleMax} historyOnly={historyOnly} />
          ))}
        </div>
      </div>
    </details>
  );
}

function runEvidenceRepairPrompt(kind: RunEvidenceGroup["repairKind"]) {
  if (kind === "profile_scope") {
    return "Fix order: Tune profile, Check setup, then Run fresh scan.";
  }
  if (kind === "source_access") {
    return "Fix order: Fix channels, Check setup, then Run fresh scan.";
  }
  return "Fix order: Check setup, then Run fresh scan.";
}

function shouldOpenRunEvidenceByDefault() {
  if (typeof window === "undefined") {
    return true;
  }
  return window.innerWidth > 680;
}

export function RunClusterRow({ cluster, scaleMax, historyOnly = false }: { cluster: RunEvidenceCluster; scaleMax: number; historyOnly?: boolean }) {
  const run = cluster.sample;
  const artifact = run.report_artifact ?? null;
  const outcome = historyOnly ? historicalRunOutcome(cluster.outcome, cluster.failed) : cluster.outcome;
  const runCountLabel = cluster.runs.length === 1 ? runDisplayDetail(run) : `${cluster.runs.length} runs · latest ${runDisplayDetail(run)}`;
  const statusLabel = historyOnly ? "History" : cluster.runs.length === 1 ? run.status : cluster.failed > 0 ? `${cluster.failed} failed` : `${cluster.runs.length} runs`;
  const outcomeDetail = outcome.detail;
  return (
    <div className="table-row run-row" data-run-tone={outcome.tone}>
      <div className="run-primary">
        <strong>{outcome.title}</strong>
        <small>{[runDisplayTitle(run), runCountLabel].filter(Boolean).join(" · ")}</small>
        <span>{outcomeDetail}</span>
      </div>
      <span className={`status ${historyOnly ? "unknown" : toneClass(statusLabel)}`}>{statusLabel}</span>
      <RunCountBars cards={cluster.cards} alerts={cluster.alerts} scaleMax={scaleMax} />
      <div className="run-health" title={runHealthDetail(run.quality)}>
        <span className={diagnosticTone(run.quality)}>{formatRunDiagnostics(run.quality)}</span>
      </div>
      {artifact ? (
        <a
          className="artifact-link"
          href={artifactHref(artifact.path)}
          aria-label={`Open ${artifactDisplayName(artifact, run)}`}
          rel="noreferrer"
          target="_blank"
          title={artifact.display_path || artifactDisplayName(artifact, run)}
        >
          <ExternalLink size={14} />
          <span>{artifactShortLabel(artifact)}</span>
          <small>{cluster.runs.length === 1 ? artifactShortDetail(artifact, run) : `Latest report · 1 of ${cluster.runs.length} runs`}</small>
        </a>
      ) : (
        <span className="run-report-missing">No report</span>
      )}
    </div>
  );
}

function RunCountBars({ cards, alerts, scaleMax }: { cards: number; alerts: number; scaleMax: number }) {
  const maxValue = Math.max(1, scaleMax, cards, alerts);
  return (
    <div className="run-count-bars" aria-label={`${cards} cards, ${alerts} alerts`}>
      <span style={{ "--bar": percentWidth(cards / maxValue) } as CSSProperties}>
        <i />
        <b>{cards}</b>
        <em>cards</em>
      </span>
      <span style={{ "--bar": percentWidth(alerts / maxValue) } as CSSProperties}>
        <i />
        <b>{alerts}</b>
        <em>alerts</em>
      </span>
    </div>
  );
}
