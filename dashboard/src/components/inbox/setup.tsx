import { AlertTriangle, Check, Clock3, Inbox, Play } from "lucide-react";

import { EmptyStateShell } from "../common";
import { setupCheckLabel, setupCheckTone, setupNeedsAttention } from "../../domain/inbox";
import type { DashboardState } from "../../domain/types";

export function SetupChecklistBanner({ setupStatus }: { setupStatus?: DashboardState["setup_status"] }) {
  const checks = Array.isArray(setupStatus?.checks) ? setupStatus.checks : [];
  if (!setupNeedsAttention(checks)) {
    return null;
  }
  return (
    <section className="setup-banner" aria-label="First useful report checklist">
      <div className="setup-banner-copy">
        <span className="panel-kicker">Setup path</span>
        <strong>{setupStatus?.stage === "ready" ? "Ready to review" : "Complete first useful report"}</strong>
        {setupStatus?.next_step && <small>Next: {appFirstNextStep(setupStatus.next_step)}</small>}
      </div>
      <SetupChecklist setupStatus={setupStatus} compact />
    </section>
  );
}

export function InboxEmptyState({
  title,
  detail,
  setupStatus,
  onOpenStart,
}: {
  title: string;
  detail?: string;
  setupStatus?: DashboardState["setup_status"];
  onOpenStart?: () => void;
}) {
  return (
    <EmptyStateShell
      icon={<Inbox size={24} />}
      title={title}
      detail={detail}
      readout={[
        { label: "Data", value: "online" },
        { label: "Scans", value: setupStatus?.has_runs ? "history" : "needed" },
        { label: "Stage", value: setupStatus?.stage || "local" },
      ]}
    >
      {onOpenStart && (
        <div className="empty-actions" aria-label="Inbox next actions">
          <button type="button" onClick={onOpenStart}>
            <Play size={15} />
            <span>Open Start</span>
          </button>
        </div>
      )}
      <SetupChecklist setupStatus={setupStatus} />
    </EmptyStateShell>
  );
}

export function appFirstNextStep(nextStep: string) {
  const text = nextStep.trim();
  if (!text) {
    return "";
  }
  if (text.includes("sources import")) {
    return "Open Settings, discover Sources with AI, then run another AI review.";
  }
  if (text.includes("AI API key")) {
    return "Open Settings and add an AI API key.";
  }
  if (text.includes("monitor run")) {
    return "Open Start and run the first AI review.";
  }
  if (text.includes("delivery test")) {
    return "Open Settings and add a notification target, or keep manual review.";
  }
  if (text.includes("init-config")) {
    return "Open Start and create the local workspace.";
  }
  if (text.includes("profiles.toml")) {
    return "Open Profiles and resume an existing profile.";
  }
  return text;
}

function SetupChecklist({ setupStatus, compact = false }: { setupStatus?: DashboardState["setup_status"]; compact?: boolean }) {
  const allChecks = Array.isArray(setupStatus?.checks) ? setupStatus.checks : [];
  const checks = compact ? allChecks.filter((check) => ["active", "blocked"].includes(String(check.status || ""))) : allChecks;
  if (!checks.length) {
    return null;
  }

  return (
    <div className={compact ? "setup-checklist compact" : "setup-checklist"} aria-label="First useful report checklist">
      {checks.map((check) => (
        <div className={`setup-step ${setupCheckTone(check.status)}`} key={check.check_id}>
          <span className="setup-step-icon" aria-hidden="true">
            {setupCheckIcon(check.status)}
          </span>
          <div className="setup-step-copy">
            <div className="setup-step-title">
              <strong>{check.label}</strong>
              <span>{setupCheckLabel(check.status)}</span>
            </div>
            {check.detail && <p>{check.detail}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

function setupCheckIcon(status: string) {
  if (status === "done") {
    return <Check size={15} />;
  }
  if (status === "blocked") {
    return <AlertTriangle size={15} />;
  }
  if (status === "active") {
    return <Play size={15} />;
  }
  return <Clock3 size={15} />;
}
