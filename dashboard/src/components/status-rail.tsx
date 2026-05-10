import { Download, GitBranch } from "lucide-react";

import { formatGitRemoteState } from "../domain/display";
import type { GitUpdateStatus } from "../domain/types";
import { PanelHeader, StatusLine } from "./common";

export function StatusRail({
  gitStatus,
  gitBusy,
  onCheckUpdates,
  onPullLatest,
}: {
  gitStatus: GitUpdateStatus | null;
  gitBusy: boolean;
  onCheckUpdates: () => void;
  onPullLatest: () => void;
}) {
  return (
    <section className="table-section repository-panel" aria-label="Repository update controls">
      <PanelHeader icon={<GitBranch size={18} />} title="Repository" />
      <details className="repository-details">
        <summary>
          <span>{formatGitRemoteState(gitStatus)}</span>
          <strong>{gitStatus ? `${gitStatus.ahead} ahead / ${gitStatus.behind} behind` : "--"}</strong>
        </summary>
        <div className="repository-toolbar">
          <StatusLine label="Branch" value={gitStatus?.branch || "unchecked"} />
          <StatusLine label="Remote" value={formatGitRemoteState(gitStatus)} />
          <StatusLine label="Delta" value={gitStatus ? `${gitStatus.ahead} ahead / ${gitStatus.behind} behind` : "--"} />
          <div className="git-actions">
            <button type="button" onClick={onCheckUpdates} disabled={gitBusy}>
              <GitBranch size={15} />
              <span>{gitBusy ? "Checking" : "Check updates"}</span>
            </button>
            <button className="danger-action" type="button" onClick={onPullLatest} disabled={gitBusy || !gitStatus?.pull_allowed}>
              <Download size={15} />
              <span>Pull latest</span>
            </button>
          </div>
          <p className={`git-message ${gitStatus?.status || "unchecked"}`}>
            {gitStatus?.message || "Remote status unchecked"}
          </p>
        </div>
      </details>
    </section>
  );
}
