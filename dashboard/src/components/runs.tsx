import { Activity } from "lucide-react";

import { PanelHeader } from "./common";
import type { Run } from "../domain/types";
import { RunClusterRow, RunEvidenceGroupPanel } from "./runs/evidence";
import { RunsEmptyState } from "./runs/empty-state";
import { RunHealthChart } from "./runs/health-chart";
import {
  buildRunEvidenceGroups,
  buildSingleRunCluster,
  RECENT_RUN_LIMIT,
  runCountScaleMax,
} from "./runs/model";

export {
  buildCompactRunTimeline,
  buildRunEvidenceClusters,
  buildRunEvidenceGroups,
  buildRunHealthDecision,
  buildRunOutcome,
  runCountScaleMax,
} from "./runs/model";

export function RunsView({
  runs,
  onRunDeskAction,
  onOpenReview,
  onOpenProfiles,
}: {
  runs: Run[];
  onRunDeskAction?: (actionId: string, body?: Record<string, unknown>) => void;
  onOpenReview?: () => void;
  onOpenProfiles?: () => void;
}) {
  if (!runs.length) {
    return (
      <RunsEmptyState
        title="No runs yet"
        detail="Run a local AI review before judging source quality."
        onRunDeskAction={onRunDeskAction}
      />
    );
  }
  const evidenceGroups = buildRunEvidenceGroups(runs);
  const visibleClusters = evidenceGroups.flatMap((group) => group.clusters);
  const visibleScaleMax = runCountScaleMax(visibleClusters);
  const visibleRunCount = evidenceGroups.reduce((sum, group) => sum + group.runs.length, 0);
  const archivedRuns = runs.slice(RECENT_RUN_LIMIT);
  const archivedClusters = archivedRuns.map((run) => buildSingleRunCluster(run));
  const archivedScaleMax = runCountScaleMax(archivedClusters);
  return (
    <section className="table-section" aria-label="Run history">
      <PanelHeader icon={<Activity size={18} />} title="Runs" />
      <RunHealthChart
        runs={runs}
        onOpenProfiles={onOpenProfiles}
        onOpenReview={onOpenReview}
        onRunDeskAction={onRunDeskAction}
      />
      <div className="run-list-head">
        <strong>Recent scans</strong>
        <span>
          {visibleRunCount} recent · {runs.length} total
        </span>
      </div>
      <div className="run-evidence-groups">
        {evidenceGroups.map((group) => (
          <RunEvidenceGroupPanel group={group} key={group.key} scaleMax={visibleScaleMax} />
        ))}
      </div>
      {archivedRuns.length > 0 && (
        <details className="run-archive">
          <summary>Older scan history ({archivedRuns.length})</summary>
          <div className="table-list">
            {archivedClusters.map((cluster) => (
              <RunClusterRow key={cluster.key} cluster={cluster} scaleMax={archivedScaleMax} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
