import { Download, GitBranch } from "lucide-react";

import type { GitUpdateStatus } from "../domain/types";
import { PanelHeader, StatusLine } from "./common";

function localChangeLabel(count: number) {
  return `${count} local ${count === 1 ? "change" : "changes"}`;
}

function repositorySummary(status: GitUpdateStatus | null) {
  if (!status) return "Workspace saved locally";
  if (status.dirty) return "Changes ready to save";
  if (status.status === "fetch_failed") return "Update check failed";
  if (status.behind > 0 && status.ahead > 0) return "Manual sync needed";
  if (status.behind > 0) return "Updates available";
  if (status.ahead > 0) return "Local commits ready";
  return "Up to date";
}

function repositoryDelta(status: GitUpdateStatus | null) {
  if (!status) return "Check when needed";
  if (status.dirty) return localChangeLabel(status.dirty_count);
  if (status.ahead > 0 || status.behind > 0) {
    return `${status.ahead} local / ${status.behind} remote`;
  }
  if (status.status === "fetch_failed") return "Try again later";
  return "No remote changes";
}

function repositoryMessage(status: GitUpdateStatus | null) {
  if (!status) return "Local workspace is saved here. Check updates only when you want to sync.";
  if (status.message) return status.message;
  return repositorySummary(status);
}

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
    <section className="table-section repository-panel" aria-label="App update controls">
      <PanelHeader icon={<GitBranch size={18} />} title="Updates" />
      <details className="repository-details">
        <summary>
          <span>{repositorySummary(gitStatus)}</span>
          <strong>{repositoryDelta(gitStatus)}</strong>
        </summary>
        <div className="repository-toolbar">
          <StatusLine label="Branch" value={gitStatus?.branch || "Local workspace"} />
          <StatusLine label="Remote" value={repositorySummary(gitStatus)} />
          <StatusLine label="Delta" value={repositoryDelta(gitStatus)} />
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
            {repositoryMessage(gitStatus)}
          </p>
        </div>
      </details>
    </section>
  );
}
