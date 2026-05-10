import { StrictMode, useEffect, useMemo, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  Inbox,
  Play,
  RefreshCw,
  Settings,
  ShieldCheck,
  UserRoundCog,
} from "lucide-react";
import signalIcon from "./assets/tgcs-signal-icon.png";
import { CommandStrip, OpportunitySummaryPanel, ValidationSummaryPanel } from "./components/board-status";
import { InboxView } from "./components/inbox";
import { ProfilesView } from "./components/profiles";
import { RunsView } from "./components/runs";
import { SettingsView } from "./components/settings";
import { StatusRail } from "./components/status-rail";
import { buildProfileReportNames } from "./domain/display";
import { isActionableInboxCard } from "./domain/inbox";
import {
  buildBoardMeta,
  buildMetrics,
  buildTabCounts,
  hasBlockingOpportunitySummary,
} from "./domain/projections";
import {
  emptyDashboardState,
  sanitizeDashboardState,
  sanitizeFeedbackExportResult,
  sanitizeGitUpdateStatus,
} from "./domain/sanitize";
import type {
  DashboardState,
  FeedbackExportResult,
  GitUpdateStatus,
  Tab,
} from "./domain/types";
import "./styles.css";

const projectRepoUrl = "https://github.com/Sapientropic/tg-channel-scanner";

const tabShell: Array<{ tab: Tab; icon: ReactNode; label: string }> = [
  { tab: "inbox", icon: <Inbox size={17} />, label: "Inbox" },
  { tab: "profiles", icon: <UserRoundCog size={17} />, label: "Profiles" },
  { tab: "runs", icon: <Play size={17} />, label: "Runs" },
  { tab: "settings", icon: <Settings size={17} />, label: "Settings" },
];

function App() {
  const { state, refresh, loadError } = useDashboardState();
  const [activeTab, setActiveTab] = useState<Tab>("inbox");
  const [busy, setBusy] = useState(false);
  const [gitBusy, setGitBusy] = useState(false);
  const [gitStatus, setGitStatus] = useState<GitUpdateStatus | null>(null);
  const [feedbackExport, setFeedbackExport] = useState<FeedbackExportResult | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const metrics = useMemo(() => buildMetrics(state), [state]);
  const profileReportNames = useMemo(() => buildProfileReportNames(state.profiles), [state.profiles]);
  const tabCounts = useMemo(() => buildTabCounts(state), [state]);
  const boardMeta = useMemo(() => buildBoardMeta(activeTab, state), [activeTab, state]);
  const latestRunId = state.runs[0]?.run_id;
  const hasLatestActionCards = state.inbox.some((card) => isActionableInboxCard(card, latestRunId));
  const hasBlockingSummary = hasBlockingOpportunitySummary(state.opportunity_summary);
  const showCommandStrip = activeTab === "inbox" && !hasLatestActionCards;
  const showOpportunitySummary = activeTab === "inbox" && (!hasLatestActionCards || hasBlockingSummary);
  const showValidationSummary = activeTab === "inbox" && !hasLatestActionCards;
  const showBoardStatusStack = showCommandStrip || showOpportunitySummary || showValidationSummary;

  async function refreshNow() {
    setBusy(true);
    try {
      await refresh();
      setNotice({ tone: "success", text: "State refreshed" });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function act(cardId: string, action: string, note = "") {
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetch(`/api/review-cards/${encodeURIComponent(cardId)}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, note }),
      });
      await assertOk(response);
      await refresh();
      setNotice({ tone: "success", text: action === "follow_up" ? "Profile diff drafted" : "Inbox updated" });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function applyPatch(patchId: string) {
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetch(`/api/profile-patches/${encodeURIComponent(patchId)}/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      await assertOk(response);
      await refresh();
      setNotice({ tone: "success", text: "Profile snapshot saved and diff applied" });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function revertPatch(patchId: string) {
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetch(`/api/profile-patches/${encodeURIComponent(patchId)}/revert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      await assertOk(response);
      await refresh();
      setNotice({ tone: "success", text: "Profile diff reverted from saved snapshot" });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function setAlertMode(profileId: string, mode: string) {
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/alert-mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      await assertOk(response);
      await refresh();
      setNotice({ tone: "success", text: "Alert mode updated" });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function checkUpdates() {
    setGitBusy(true);
    setNotice(null);
    try {
      const response = await fetch("/api/git/check-updates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = await readJson(response);
      const git = sanitizeGitUpdateStatus(payload.git);
      if (!git) {
        throw new Error("Invalid git status response");
      }
      setGitStatus(git);
      setNotice({ tone: "success", text: "Remote status checked" });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setGitBusy(false);
    }
  }

  async function exportFeedback() {
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetch("/api/feedback/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = await readJson(response);
      const result = sanitizeFeedbackExportResult(payload.export);
      if (!result) {
        throw new Error("Invalid feedback export response");
      }
      setFeedbackExport(result);
      setNotice({ tone: "success", text: `Feedback exported: ${result.feedback_count} rows` });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function pullLatest() {
    if (!gitStatus?.pull_allowed) {
      return;
    }
    const confirmed = window.confirm("Pull latest with git pull --ff-only? Local changes must already be clean.");
    if (!confirmed) {
      return;
    }
    setGitBusy(true);
    setNotice(null);
    try {
      const response = await fetch("/api/git/pull-latest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      const payload = await readJson(response);
      const git = sanitizeGitUpdateStatus(payload.git);
      if (!git) {
        throw new Error("Invalid git status response");
      }
      setGitStatus(git);
      setNotice({ tone: "success", text: "Pulled latest upstream changes" });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setGitBusy(false);
    }
  }

  return (
    <main className="app-shell" data-testid="tgcs-dashboard">
      <div className="pixel-grid" aria-hidden="true" />
      <header className="console-header">
        <div className="brand-station">
          <a
            className="pixel-mark"
            href={projectRepoUrl}
            target="_blank"
            rel="noreferrer"
            aria-label="Open TGCS Git repository"
            title="Open Git repository"
          >
            <img src={signalIcon} alt="" />
          </a>
          <div className="brand-copy">
            <p className="eyebrow">TG Channel Scanner</p>
            <h1>Signal Desk</h1>
            <div className="header-readout" aria-label="Local dashboard boundary">
              <span>SQLite local</span>
              <span>127.0.0.1</span>
              <span>raw text redacted</span>
            </div>
          </div>
        </div>
        <button className="refresh-button" onClick={refreshNow} disabled={busy} title="Refresh state" type="button">
          <RefreshCw size={18} className={busy ? "spin" : ""} />
          <span>Refresh</span>
        </button>
      </header>

      {(notice || loadError) && (
        <div className={`notice ${notice?.tone === "error" || loadError ? "error" : "success"}`} role="status">
          {loadError || notice?.text}
        </div>
      )}

      <section className="workbench">
        <aside className="nav-rail" aria-label="Dashboard navigation">
          <nav className="tabs" aria-label="Dashboard tabs">
            {tabShell.map((tab) => (
              <TabButton
                key={tab.tab}
                {...tab}
                active={activeTab}
                count={tabCounts[tab.tab]}
                setActive={setActiveTab}
              />
            ))}
          </nav>
          <div className="rail-note">
            <ShieldCheck size={16} />
            <span>Tokens stay outside SQLite</span>
          </div>
        </aside>

        <section className="main-board" aria-label={boardMeta.title}>
          <WorkbenchHeader meta={boardMeta} />
          {showBoardStatusStack && (
            <div className="board-status-stack" aria-label="Board status summary">
              {showCommandStrip && <CommandStrip state={state} metrics={metrics} />}
              {showOpportunitySummary && <OpportunitySummaryPanel summary={state.opportunity_summary} />}
              <ValidationSummaryPanel summary={showValidationSummary ? state.validation_summary : undefined} />
            </div>
          )}
          <div className="board-body">
            {activeTab === "inbox" && (
              <InboxView
                cards={state.inbox}
                latestRunId={latestRunId}
                setupStatus={state.setup_status}
                profileReportNames={profileReportNames}
                act={act}
                busy={busy}
              />
            )}
            {activeTab === "profiles" && (
              <ProfilesView
                profiles={state.profiles}
                patches={state.profile_patch_suggestions}
                applyPatch={applyPatch}
                revertPatch={revertPatch}
                setAlertMode={setAlertMode}
                busy={busy}
              />
            )}
            {activeTab === "runs" && <RunsView runs={state.runs} />}
            {activeTab === "settings" && (
              <>
                <SettingsView
                  targets={state.delivery_targets}
                  sourceStats={state.source_stats}
                  sourceInsights={state.source_insights}
                  feedbackSummary={state.feedback_summary}
                  feedbackExport={feedbackExport}
                  exportFeedback={exportFeedback}
                  busy={busy}
                />
                <StatusRail
                  gitStatus={gitStatus}
                  gitBusy={gitBusy}
                  onCheckUpdates={checkUpdates}
                  onPullLatest={pullLatest}
                />
              </>
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

function useDashboardState() {
  const [state, setState] = useState<DashboardState>(emptyDashboardState);
  const [loadError, setLoadError] = useState("");

  async function load(signal?: AbortSignal) {
    const response = await fetch("/api/state", { signal });
    await assertOk(response);
    const payload = (await response.json()) as Partial<DashboardState>;
    setState(sanitizeDashboardState(payload));
    setLoadError("");
  }

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setLoadError(errorMessage(error));
      setState(emptyDashboardState);
    });
    return () => controller.abort();
  }, []);

  return { state, refresh: () => load(), loadError };
}

function TabButton({
  tab,
  active,
  count,
  setActive,
  icon,
  label,
}: {
  tab: Tab;
  active: Tab;
  count: number;
  setActive: (tab: Tab) => void;
  icon: ReactNode;
  label: string;
}) {
  return (
    <button className={active === tab ? "tab active" : "tab"} onClick={() => setActive(tab)} type="button">
      <span className="tab-icon">{icon}</span>
      <span className="tab-label">{label}</span>
      <span className="tab-count">{count}</span>
    </button>
  );
}

function WorkbenchHeader({
  meta,
}: {
  meta: {
    title: string;
    detail: string;
    value: string;
    tone: "amber" | "teal" | "rust" | "blue";
  };
}) {
  return (
    <header className="board-header" title={meta.detail}>
      <div>
        <h2>{meta.title}</h2>
      </div>
      <strong className={`board-token ${meta.tone}`}>{meta.value}</strong>
    </header>
  );
}

async function assertOk(response: Response) {
  if (response.ok) {
    return;
  }
  let detail = response.statusText;
  try {
    const payload = await response.json();
    if (payload && typeof payload.error === "string") {
      detail = payload.error;
    }
  } catch {
    // Keep the HTTP status text when the server did not return JSON.
  }
  throw new Error(detail || `HTTP ${response.status}`);
}

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof payload.error === "string" ? payload.error : response.statusText || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as Record<string, unknown>;
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
