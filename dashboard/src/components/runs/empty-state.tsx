import { Activity, Clock3 } from "lucide-react";

import { EmptyStateShell } from "../common";

export function RunsEmptyState({
  title,
  detail,
  onRunDeskAction,
}: {
  title: string;
  detail?: string;
  onRunDeskAction?: (actionId: string) => void;
}) {
  return (
    <EmptyStateShell
      icon={<Clock3 size={24} />}
      title={title}
      detail={detail}
      readout={[
        { label: "DB", value: "online" },
        { label: "Run", value: "needed" },
        { label: "Next", value: "local" },
      ]}
    >
      <div className="empty-actions" aria-label="Run history next actions">
        <button type="button" onClick={() => onRunDeskAction?.("monitor_jobs_dry_run")} disabled={!onRunDeskAction}>
          <Activity size={15} />
          <span>Run first AI review</span>
        </button>
        <button type="button" onClick={() => onRunDeskAction?.("doctor_jobs")} disabled={!onRunDeskAction}>
          <Clock3 size={15} />
          <span>Check setup</span>
        </button>
      </div>
    </EmptyStateShell>
  );
}
