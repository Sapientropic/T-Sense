import { StrictMode, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  Ban,
  Bell,
  BellOff,
  Check,
  Clock3,
  Copy,
  Download,
  ExternalLink,
  FileDiff,
  GitBranch,
  Inbox,
  ListFilter,
  Play,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sun,
  UserRoundCog,
  X,
} from "lucide-react";
import signalIcon from "./assets/tgcs-signal-icon.png";
import "./styles.css";

type SourceRef = {
  channel: string;
  id: string | number;
};

type DecisionState = {
  status?: string;
  signals?: string[];
  explanations?: Record<string, string>;
};

type ReviewCard = {
  schema_version: "review_card_v1";
  card_id: string;
  profile_id: string;
  title: string;
  rating: string;
  decision_status: string;
  source_refs: SourceRef[];
  item: {
    why?: string;
    decision_state?: DecisionState;
  };
  status: string;
  report_path?: string;
  dashboard_url?: string;
  updated_at: string;
};

type Profile = {
  profile_id: string;
  path: string;
  enabled: boolean;
  config: Record<string, unknown>;
  updated_at: string;
};

type SourceStat = {
  channel: string;
  card_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  pending_count: number;
  handled_count: number;
  false_positive_count: number;
  alert_count: number;
  high_rate: number;
  latest_card_count?: number;
  latest_high_count?: number;
  raw_count?: number;
  kept_count?: number;
  scan_keep_rate?: number;
  card_yield_rate?: number;
  latest_run_id?: string;
  scan_failure?: boolean;
  scan_incomplete?: boolean;
};

type SourceInsight = {
  kind: "promote" | "prune" | "watch" | string;
  channel: string;
  label: string;
  reason: string;
  priority: number;
  stats: SourceStat;
};

type RunArtifact = {
  type?: string;
  path: string;
  sha256?: string;
};

type Run = {
  run_id: string;
  profile_id: string;
  status: string;
  started_at: string;
  completed_at?: string;
  manifest: {
    alert_count?: number;
    review_card_count?: number;
    artifacts?: RunArtifact[];
  };
  quality?: {
    prefilter?: string;
    semantic_stage?: string;
    llm_provider?: string;
    cache_hit_rate?: number | null;
    latency_ms?: number | null;
    completion_tokens?: number | null;
    diagnostic_count?: number;
    diagnostic_failure_count?: number;
    diagnostic_warning_count?: number;
    diagnostic_info_count?: number;
    top_diagnostic_code?: string;
  };
};

type DeliveryTarget = {
  target_id: string;
  type: string;
  enabled: boolean;
  config: Record<string, unknown>;
  updated_at: string;
};

type ProfilePatch = {
  patch_id: string;
  profile_id: string;
  profile_path?: string;
  card_id?: string;
  card_title?: string;
  note: string;
  status: string;
  diff_text: string;
  base_profile_hash?: string;
  created_at: string;
  applied_at?: string;
};

type DashboardState = {
  schema_version?: "dashboard_state_v1";
  profiles: Profile[];
  inbox: ReviewCard[];
  runs: Run[];
  delivery_targets: DeliveryTarget[];
  profile_patch_suggestions: ProfilePatch[];
  source_stats: SourceStat[];
  source_insights: SourceInsight[];
  feedback_summary?: {
    schema_version?: "dashboard_feedback_summary_v1";
    exportable_count?: number;
    by_action?: Record<string, number>;
    by_rating?: Record<string, number>;
    by_decision_status?: Record<string, number>;
  };
  opportunity_summary?: OpportunitySummary;
  validation_summary?: ValidationSummary;
  setup_status?: {
    schema_version?: "dashboard_setup_status_v1";
    stage?: string;
    next_step?: string;
    has_profiles?: boolean;
    has_runs?: boolean;
    has_delivery_targets?: boolean;
    has_enabled_delivery_targets?: boolean;
    checks?: SetupCheck[];
  };
};

type ValidationSummary = {
  schema_version?: "dashboard_validation_summary_v1";
  window_days?: number;
  since?: string;
  runs_count?: number;
  card_count?: number;
  high_card_count?: number;
  pending_count?: number;
  action_count?: number;
  by_action?: Record<string, number>;
  keep_rate?: number;
  false_positive_rate?: number;
  next_action?: {
    label?: string;
    detail?: string;
    command?: string;
  };
};

type OpportunitySummaryItem = {
  card_id: string;
  title: string;
  rating: string;
  decision_status: string;
  status: string;
  why?: string;
  source_refs?: SourceRef[];
  updated_at?: string;
};

type OpportunitySummary = {
  schema_version?: "dashboard_opportunity_summary_v1";
  status?: string;
  run_id?: string;
  profile_id?: string;
  scanned_count?: number;
  matched_count?: number;
  review_card_count?: number;
  alert_count?: number;
  high_actionable_count?: number;
  all_clear?: boolean;
  top_items?: OpportunitySummaryItem[];
  diagnostics?: {
    failure_count?: number;
    warning_count?: number;
    top_code?: string;
  };
  decision_counts?: Record<string, number>;
  next_action?: {
    label?: string;
    detail?: string;
    command?: string;
  };
};

type SetupCheck = {
  check_id: string;
  label: string;
  status: "done" | "active" | "blocked" | "todo" | string;
  detail?: string;
  command?: string;
};

type Tab = "inbox" | "profiles" | "runs" | "settings";
type InboxFilter = "all" | "high" | "new_changed" | "low_medium";

type Metric = {
  label: string;
  value: string;
  detail: string;
  tone: "amber" | "teal" | "rust" | "blue";
};

type GitUpdateStatus = {
  schema_version: "git_update_status_v1";
  status: string;
  message: string;
  branch: string;
  upstream?: string | null;
  repo_url?: string | null;
  head?: string | null;
  remote_head?: string | null;
  ahead: number;
  behind: number;
  dirty: boolean;
  dirty_count: number;
  pull_allowed: boolean;
  checked_at: string;
};

type FeedbackExportResult = {
  schema_version: "feedback_export_result_v1";
  feedback_count: number;
  output_path: string;
};

const emptyState: DashboardState = {
  profiles: [],
  inbox: [],
  runs: [],
  delivery_targets: [],
  profile_patch_suggestions: [],
  source_stats: [],
  source_insights: [],
  feedback_summary: undefined,
  opportunity_summary: undefined,
  validation_summary: undefined,
  setup_status: undefined,
};

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
  const tabCounts = buildTabCounts(state);
  const boardMeta = buildBoardMeta(activeTab, state);

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
      setGitStatus(payload.git as GitUpdateStatus);
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
      const result = payload.export as FeedbackExportResult;
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
      setGitStatus(payload.git as GitUpdateStatus);
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

      <CommandStrip state={state} metrics={metrics} />
      <OpportunitySummaryPanel summary={state.opportunity_summary} />
      <ValidationSummaryPanel summary={state.validation_summary} />

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
          <div className="board-body">
            {activeTab === "inbox" && (
              <InboxView cards={state.inbox} setupStatus={state.setup_status} act={act} busy={busy} />
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
              <SettingsView
                targets={state.delivery_targets}
                sourceStats={state.source_stats}
                sourceInsights={state.source_insights}
                feedbackSummary={state.feedback_summary}
                feedbackExport={feedbackExport}
                exportFeedback={exportFeedback}
                busy={busy}
              />
            )}
          </div>
        </section>

        <StatusRail
          gitStatus={gitStatus}
          gitBusy={gitBusy}
          onCheckUpdates={checkUpdates}
          onPullLatest={pullLatest}
        />
      </section>
    </main>
  );
}

function useDashboardState() {
  const [state, setState] = useState<DashboardState>(emptyState);
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
      setState(emptyState);
    });
    return () => controller.abort();
  }, []);

  return { state, refresh: () => load(), loadError };
}

function sanitizeDashboardState(payload: Partial<DashboardState>): DashboardState {
  return {
    schema_version: payload.schema_version,
    profiles: Array.isArray(payload.profiles) ? payload.profiles : [],
    inbox: Array.isArray(payload.inbox) ? payload.inbox : [],
    runs: Array.isArray(payload.runs) ? payload.runs : [],
    delivery_targets: Array.isArray(payload.delivery_targets) ? payload.delivery_targets : [],
    profile_patch_suggestions: Array.isArray(payload.profile_patch_suggestions)
      ? payload.profile_patch_suggestions
      : [],
    source_stats: Array.isArray(payload.source_stats) ? payload.source_stats : [],
    source_insights: Array.isArray(payload.source_insights) ? payload.source_insights : [],
    feedback_summary: typeof payload.feedback_summary === "object" ? payload.feedback_summary : undefined,
    opportunity_summary: typeof payload.opportunity_summary === "object" ? payload.opportunity_summary : undefined,
    validation_summary: typeof payload.validation_summary === "object" ? payload.validation_summary : undefined,
    setup_status: typeof payload.setup_status === "object" ? payload.setup_status : undefined,
  };
}

function OpportunitySummaryPanel({ summary }: { summary?: OpportunitySummary }) {
  const [copiedNextAction, setCopiedNextAction] = useState(false);
  if (!summary || summary.status === "no_runs") {
    return null;
  }
  const topItems = Array.isArray(summary.top_items) ? summary.top_items : [];
  const tone = opportunityTone(summary);
  async function copyNextAction() {
    const command = summary?.next_action?.command;
    if (!command || !navigator.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(command);
      setCopiedNextAction(true);
      window.setTimeout(() => setCopiedNextAction(false), 1200);
    } catch {
      setCopiedNextAction(false);
    }
  }
  return (
    <section className={`signal-brief ${tone}`} aria-label="Latest run opportunity summary">
      <div className="signal-brief-lede">
        <span className="panel-kicker">{summary.profile_id || "profile"}</span>
        <strong>{opportunityHeadline(summary)}</strong>
        <small>{opportunityDetail(summary)}</small>
      </div>
      <div className="signal-brief-stats" aria-label="Latest run counts">
        <StatusLine label="Scanned" value={String(summary.scanned_count ?? 0)} />
        <StatusLine label="Matched" value={String(summary.matched_count ?? 0)} />
        <StatusLine label="Alerts" value={String(summary.alert_count ?? 0)} />
      </div>
      {summary.next_action && (
        <div className="signal-next-action" aria-label="Recommended next action">
          <span className="panel-kicker">Next</span>
          <strong>{summary.next_action.label || "Review run"}</strong>
          {summary.next_action.detail && <small>{summary.next_action.detail}</small>}
          <DecisionMemoryLine counts={summary.decision_counts} />
          {summary.next_action.command && (
            <div className="signal-command">
              <code>{summary.next_action.command}</code>
              <button
                aria-label="Copy next action command"
                onClick={() => void copyNextAction()}
                title={copiedNextAction ? "Copied" : "Copy command"}
                type="button"
              >
                {copiedNextAction ? <Check size={14} /> : <Copy size={14} />}
              </button>
            </div>
          )}
        </div>
      )}
      {topItems.length ? (
        <div className="signal-top-list" aria-label="Top opportunity cards">
          {topItems.map((item) => (
            <div className="signal-top-item" key={item.card_id}>
              <span className={`rating ${toneClass(item.rating)}`}>{item.rating}</span>
              <div>
                <strong>{item.title}</strong>
                <small>
                  {item.decision_status}
                  {item.source_refs?.[0] ? ` / ${item.source_refs[0].channel}#${item.source_refs[0].id}` : ""}
                </small>
                {item.why && <p>{item.why}</p>}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="signal-brief-empty">{opportunityEmptyCopy(summary)}</p>
      )}
    </section>
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

function ValidationSummaryPanel({ summary }: { summary?: ValidationSummary }) {
  if (!summary) {
    return null;
  }
  const actions = Object.entries(summary.by_action ?? {}).filter(([, count]) => count > 0);
  return (
    <section className="validation-brief" aria-label="Local validation summary">
      <div className="validation-copy">
        <span className="panel-kicker">{summary.window_days ?? 14} day proof loop</span>
        <strong>{summary.next_action?.label || "Track real outcomes"}</strong>
        <small>{summary.next_action?.detail || "Keep behavior evidence local and note-free."}</small>
      </div>
      <div className="validation-stats">
        <StatusLine label="Runs" value={String(summary.runs_count ?? 0)} />
        <StatusLine label="High" value={String(summary.high_card_count ?? 0)} />
        <StatusLine label="Actions" value={String(summary.action_count ?? 0)} />
        <StatusLine label="Pending" value={String(summary.pending_count ?? 0)} />
      </div>
      <div className="validation-actions" aria-label="Validation action counts">
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
    </section>
  );
}

function opportunityTone(summary: OpportunitySummary) {
  if ((summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed") {
    return "blocked";
  }
  if ((summary.high_actionable_count ?? 0) > 0) {
    return "hot";
  }
  if (summary.all_clear) {
    return "clear";
  }
  return "quiet";
}

function opportunityHeadline(summary: OpportunitySummary) {
  if ((summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed") {
    return "Source check needed";
  }
  const count = summary.high_actionable_count ?? 0;
  if (count > 0) {
    return `${count} action signal${count === 1 ? "" : "s"}`;
  }
  if (summary.all_clear) {
    return "All Clear";
  }
  return "Latest run ready";
}

function opportunityDetail(summary: OpportunitySummary) {
  if ((summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed") {
    return summary.diagnostics?.top_code ? `Top diagnostic: ${summary.diagnostics.top_code}` : "Open Runs for diagnostics.";
  }
  const matched = summary.matched_count ?? 0;
  const scanned = summary.scanned_count ?? 0;
  return `${matched}/${scanned} messages reached the opportunity lane.`;
}

function opportunityEmptyCopy(summary: OpportunitySummary) {
  if ((summary.diagnostics?.failure_count ?? 0) > 0 || summary.status === "failed") {
    return "Fix source access before evaluating opportunities.";
  }
  if (summary.all_clear) {
    return "No high-priority new or changed opportunities in the latest run.";
  }
  return "No ranked opportunity cards were produced by the latest run.";
}

function CommandStrip({ state, metrics }: { state: DashboardState; metrics: Metric[] }) {
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

function MetricTile({ metric }: { metric: Metric }) {
  return (
    <article className={`metric-tile ${metric.tone}`}>
      <span>{metric.label}</span>
      <strong>{metric.value}</strong>
      <small>{metric.detail}</small>
    </article>
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
    <header className="board-header">
      <div>
        <p className="eyebrow">Workspace</p>
        <h2>{meta.title}</h2>
        <span>{meta.detail}</span>
      </div>
      <strong className={`board-token ${meta.tone}`}>{meta.value}</strong>
    </header>
  );
}

function InboxView({
  cards,
  setupStatus,
  act,
  busy,
}: {
  cards: ReviewCard[];
  setupStatus?: DashboardState["setup_status"];
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
}) {
  const [filter, setFilter] = useState<InboxFilter>("all");
  if (!cards.length) {
    return (
      <EmptyState
        icon={<Inbox size={24} />}
        title="Inbox clear"
        detail={setupStatus?.next_step ? `Next: ${setupStatus.next_step}` : "SQLite connected. Pending review cards are currently zero."}
        setupStatus={setupStatus}
      />
    );
  }
  const filters = inboxFilterOptions(cards);
  const filteredCards = filterInboxCards(cards, filter);
  return (
    <section className="list-section" aria-label="Pending review cards">
      <div className="inbox-toolbar" aria-label="Inbox triage filters">
        <span className="panel-title">
          <ListFilter size={16} />
          Triage
        </span>
        <div className="inbox-filter-group">
          {filters.map((item) => (
            <button
              className={filter === item.id ? "filter-chip active" : "filter-chip"}
              key={item.id}
              onClick={() => setFilter(item.id)}
              type="button"
            >
              <span>{item.label}</span>
              <strong>{item.count}</strong>
            </button>
          ))}
        </div>
      </div>
      {filteredCards.length ? filteredCards.map((card) => (
        <article className={`review-card rating-${toneClass(card.rating)}`} key={card.card_id}>
          <div className="card-spine" aria-hidden="true">
            <span>{card.rating}</span>
          </div>
          <div className="card-main">
            <div className="card-title-row">
              <h3>{card.title}</h3>
              <span className={`rating ${toneClass(card.rating)}`}>{card.rating}</span>
            </div>
            <p className="reason">{card.item.why || "Decision reason unavailable."}</p>
            <div className="meta-row">
              <span>{card.profile_id}</span>
              <span>{card.decision_status}</span>
              <span>{formatDate(card.updated_at)}</span>
            </div>
            <SourceRefs refs={card.source_refs} />
            {card.report_path && <code className="report-path">{card.report_path}</code>}
          </div>
          <CardActions card={card} act={act} busy={busy} />
        </article>
      )) : <InlineEmpty title="No cards in this filter" />}
    </section>
  );
}

function inboxFilterOptions(cards: ReviewCard[]) {
  return [
    { id: "all" as const, label: "All", count: cards.length },
    { id: "high" as const, label: "High", count: filterInboxCards(cards, "high").length },
    { id: "new_changed" as const, label: "New/Changed", count: filterInboxCards(cards, "new_changed").length },
    { id: "low_medium" as const, label: "Low/Medium", count: filterInboxCards(cards, "low_medium").length },
  ];
}

function filterInboxCards(cards: ReviewCard[], filter: InboxFilter) {
  if (filter === "high") {
    return cards.filter((card) => card.rating.toLowerCase() === "high");
  }
  if (filter === "new_changed") {
    return cards.filter((card) => ["new", "changed"].includes(card.decision_status.toLowerCase()));
  }
  if (filter === "low_medium") {
    return cards.filter((card) => ["low", "medium"].includes(card.rating.toLowerCase()));
  }
  return cards;
}

function CardActions({
  card,
  act,
  busy,
}: {
  card: ReviewCard;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
}) {
  const [note, setNote] = useState("");
  return (
    <div className="card-actions">
      <div className="action-cluster" aria-label="Review actions">
        <button title="Keep" type="button" onClick={() => act(card.card_id, "keep")} disabled={busy}>
          <Check size={16} />
          <span>Keep</span>
        </button>
        <button title="Skip" type="button" onClick={() => act(card.card_id, "skip")} disabled={busy}>
          <X size={16} />
          <span>Skip</span>
        </button>
        <button
          title="False positive"
          type="button"
          onClick={() => act(card.card_id, "false_positive")}
          disabled={busy}
        >
          <Ban size={16} />
          <span>False</span>
        </button>
      </div>
      <label className="follow-up">
        <span>Profile note</span>
        <div className="follow-up-control">
          <textarea
            aria-label="Follow-up note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Add profile preference"
            disabled={busy}
          />
          <button
            title={note.trim() ? "Create profile diff" : "Add a note first"}
            type="button"
            onClick={() => act(card.card_id, "follow_up", note)}
            disabled={busy || !note.trim()}
          >
            <FileDiff size={16} />
          </button>
        </div>
      </label>
    </div>
  );
}

function ProfilesView({
  profiles,
  patches,
  applyPatch,
  revertPatch,
  setAlertMode,
  busy,
}: {
  profiles: Profile[];
  patches: ProfilePatch[];
  applyPatch: (patchId: string) => void;
  revertPatch: (patchId: string) => void;
  setAlertMode: (profileId: string, mode: string) => void;
  busy: boolean;
}) {
  return (
    <section className="split-section">
      <div className="plain-panel">
        <PanelHeader icon={<UserRoundCog size={18} />} title="Profiles" count={profiles.length} />
        {profiles.length ? (
          <div className="table-list">
            {profiles.map((profile) => (
              <div className="table-row profile-row" key={profile.profile_id}>
                <strong>{profile.profile_id}</strong>
                <span className={profile.enabled ? "status enabled" : "status disabled"}>
                  {profile.enabled ? "enabled" : "disabled"}
                </span>
                <code>{profile.path}</code>
                <AlertModeControl profile={profile} setAlertMode={setAlertMode} busy={busy} />
              </div>
            ))}
          </div>
        ) : (
          <InlineEmpty title="No profiles registered" />
        )}
      </div>
      <div className="plain-panel">
        <PanelHeader icon={<FileDiff size={18} />} title="Profile Diffs" count={patches.length} />
        {patches.length ? (
          <div className="patch-list">
            {patches.map((patch) => {
              const stats = diffStats(patch.diff_text);
              return (
                <article className="review-card patch-card" key={patch.patch_id}>
                  <div className="card-main">
                    <div className="card-title-row">
                      <h3>{patch.card_title || patch.profile_id}</h3>
                      <span className={`status ${toneClass(patch.status)}`}>{patch.status}</span>
                    </div>
                    <div className="patch-context-row">
                      <span>{patch.profile_id}</span>
                      <code>{patch.profile_path || "profile path unavailable"}</code>
                      <span>{formatDate(patch.created_at)}</span>
                      {patch.applied_at && <span>applied {formatDate(patch.applied_at)}</span>}
                      <span className="patch-diff-stat">+{stats.added} / -{stats.removed}</span>
                    </div>
                    <p className="note-line">{patch.note || "Follow-up preference draft"}</p>
                    <pre>{patch.diff_text || "No diff body recorded."}</pre>
                    <div className="patch-actions">
                      {patch.status === "pending" && (
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => applyPatch(patch.patch_id)}
                          disabled={busy}
                        >
                          <Check size={15} />
                          <span>Apply</span>
                        </button>
                      )}
                      {patch.status === "applied" && (
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => revertPatch(patch.patch_id)}
                          disabled={busy}
                          title="Restore the saved profile snapshot if the file has not changed"
                        >
                          <RefreshCw size={15} />
                          <span>Revert</span>
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <InlineEmpty title="No pending profile diffs" />
        )}
      </div>
    </section>
  );
}

function AlertModeControl({
  profile,
  setAlertMode,
  busy,
}: {
  profile: Profile;
  setAlertMode: (profileId: string, mode: string) => void;
  busy: boolean;
}) {
  const mode = alertMode(profile);
  const modes = [
    { value: "work_hours", label: "Day", icon: <Sun size={14} /> },
    { value: "all_day", label: "All", icon: <Bell size={14} /> },
    { value: "muted", label: "Mute", icon: <BellOff size={14} /> },
  ];
  return (
    <div className="mode-controls" aria-label={`${profile.profile_id} alert mode`}>
      {modes.map((item) => (
        <button
          className={mode === item.value ? "mode-button active" : "mode-button"}
          key={item.value}
          type="button"
          title={item.label}
          disabled={busy}
          onClick={() => setAlertMode(profile.profile_id, item.value)}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
}

function RunsView({ runs }: { runs: Run[] }) {
  if (!runs.length) {
    return <EmptyState icon={<Clock3 size={24} />} title="No runs yet" detail="Run history is empty in this database." />;
  }
  return (
    <section className="table-section" aria-label="Run history">
      <PanelHeader icon={<Activity size={18} />} title="Runs" count={runs.length} />
      <div className="table-list">
        {runs.map((run) => {
          const artifact = selectRunArtifact(run.manifest.artifacts);
          return (
            <div className="table-row run-row" key={run.run_id}>
              <div className="run-primary">
                <strong>{run.profile_id}</strong>
                <code>{shortId(run.run_id)}</code>
              </div>
              <span className={`status ${toneClass(run.status)}`}>{run.status}</span>
              <div className="run-metrics">
                <span>{run.manifest.review_card_count ?? 0} cards</span>
                <span>{run.manifest.alert_count ?? 0} alerts</span>
              </div>
              <div className="run-quality">
                <span>{run.quality?.prefilter || "prefilter n/a"}</span>
                <span>{formatRunQuality(run.quality)}</span>
                <span className={diagnosticTone(run.quality)}>{formatRunDiagnostics(run.quality)}</span>
              </div>
              {artifact ? (
                <a
                  className="artifact-link"
                  href={artifactHref(artifact.path)}
                  rel="noreferrer"
                  target="_blank"
                  title={artifact.path}
                >
                  <ExternalLink size={14} />
                  <span>Open report</span>
                  <code>{shortPath(artifact.path)}</code>
                </a>
              ) : (
                <code>artifact unset</code>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function SettingsView({
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
  const exportableCount = feedbackExport?.feedback_count ?? feedbackSummary?.exportable_count ?? 0;
  return (
    <section className="split-section" aria-label="Delivery and source settings">
      <div className="table-section">
        <PanelHeader icon={<Settings size={18} />} title="Delivery Targets" count={targets.length} />
        {targets.length ? (
          <div className="table-list">
            {targets.map((target) => (
              <div className="table-row target-row" key={target.target_id}>
                <strong>{target.target_id}</strong>
                <span>{target.type}</span>
                <span className={target.enabled ? "status enabled" : "status disabled"}>
                  {target.enabled ? "enabled" : "disabled"}
                </span>
                <code>{String(target.config.chat_id || "chat unset")}</code>
              </div>
            ))}
          </div>
        ) : (
          <InlineEmpty title="No delivery targets registered" />
        )}
      </div>
      <div className="table-section">
        <PanelHeader icon={<Activity size={18} />} title="Source Yield" count={sourceStats.length} />
        {sourceStats.length ? (
          <div className="table-list">
            {sourceStats.slice(0, 12).map((source) => (
              <div className="table-row source-stat-row" key={source.channel}>
                <strong>{source.channel}</strong>
                <div className="source-yield-meter" aria-label={`${source.channel} scan keep rate`}>
                  <span style={{ width: percentWidth(source.scan_keep_rate) }} />
                </div>
                <span>{source.kept_count ?? 0}/{source.raw_count ?? 0} kept</span>
                <span>{formatPercent(source.card_yield_rate ?? 0)} card yield</span>
                <span>{source.latest_high_count ?? source.high_count} high</span>
                <span>{source.latest_card_count ?? source.card_count} cards</span>
                <span>{source.alert_count} alerts</span>
              </div>
            ))}
          </div>
        ) : (
          <InlineEmpty title="No source stats yet" />
        )}
      </div>
      <div className="table-section feedback-export-panel">
        <PanelHeader icon={<Download size={18} />} title="Feedback Export" count={exportableCount} />
        <div className="feedback-breakdown" aria-label="Feedback action counts">
          <span>Keep {feedbackSummary?.by_action?.keep ?? 0}</span>
          <span>Skip {feedbackSummary?.by_action?.skip ?? 0}</span>
          <span>False {feedbackSummary?.by_action?.false_positive ?? 0}</span>
          <span>High {feedbackSummary?.by_rating?.high ?? 0}</span>
          <span>Changed {feedbackSummary?.by_decision_status?.changed ?? 0}</span>
        </div>
        <div className="feedback-export-row">
          <button className="text-button" type="button" onClick={exportFeedback} disabled={busy}>
            <Download size={15} />
            <span>{busy ? "Exporting" : "Export feedback"}</span>
          </button>
          <code>{feedbackExport?.output_path || "output/dashboard-feedback.jsonl"}</code>
        </div>
      </div>
      <div className="table-section source-actions-panel">
        <PanelHeader icon={<ShieldCheck size={18} />} title="Source Actions" count={sourceInsights.length} />
        {sourceInsights.length ? (
          <div className="insight-list">
            {sourceInsights.slice(0, 8).map((insight) => (
              <article className={`source-insight ${insight.kind}`} key={`${insight.kind}-${insight.channel}`}>
                <span className={`status ${insight.kind}`}>{insight.label}</span>
                <strong>{insight.channel}</strong>
                <p>{insight.reason}</p>
                <small>
                  {insight.stats.kept_count ?? 0}/{insight.stats.raw_count ?? 0} kept /{" "}
                  {insight.stats.latest_card_count ?? insight.stats.card_count} cards / {insight.stats.high_count} high /{" "}
                  {insight.stats.false_positive_count} false
                </small>
              </article>
            ))}
          </div>
        ) : (
          <InlineEmpty title="No source actions yet" />
        )}
      </div>
    </section>
  );
}

function alertMode(profile: Profile) {
  const value = profile.config.alert_schedule_mode;
  return typeof value === "string" ? value : "work_hours";
}

function formatPercent(value: number) {
  if (!Number.isFinite(value)) {
    return "0%";
  }
  return `${Math.round(value * 100)}%`;
}

function percentWidth(value?: number) {
  const bounded = Math.max(0, Math.min(1, Number.isFinite(value ?? NaN) ? Number(value) : 0));
  return `${Math.round(bounded * 100)}%`;
}

function diffStats(diffText: string) {
  return diffText.split(/\r?\n/).reduce(
    (stats, line) => {
      if (line.startsWith("+") && !line.startsWith("+++")) {
        stats.added += 1;
      } else if (line.startsWith("-") && !line.startsWith("---")) {
        stats.removed += 1;
      }
      return stats;
    },
    { added: 0, removed: 0 },
  );
}

function topSourceDetail(sources: SourceStat[]) {
  if (!sources.length) {
    return "no source stats";
  }
  const top = sources[0];
  if ((top.kept_count ?? 0) > 0 || (top.raw_count ?? 0) > 0) {
    return `${top.channel}: ${top.kept_count ?? 0}/${top.raw_count ?? 0} kept, ${top.latest_card_count ?? top.card_count} cards`;
  }
  return `${top.channel}: ${formatPercent(top.high_rate)} high`;
}

function StatusRail({
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
    <aside className="context-rail" aria-label="Repository update controls">
      <RailPanel icon={<GitBranch size={18} />} title="Repository">
        <StatusLine label="Branch" value={gitStatus?.branch || "unchecked"} />
        <StatusLine label="Remote" value={formatGitRemoteState(gitStatus)} />
        {gitStatus && <StatusLine label="Delta" value={`${gitStatus.ahead} ahead / ${gitStatus.behind} behind`} />}
        <div className="git-actions">
          <button type="button" onClick={onCheckUpdates} disabled={gitBusy}>
            <GitBranch size={15} />
            <span>{gitBusy ? "Checking" : "Check updates"}</span>
          </button>
          <button type="button" onClick={onPullLatest} disabled={gitBusy || !gitStatus?.pull_allowed}>
            <Download size={15} />
            <span>Pull latest</span>
          </button>
        </div>
        <p className={`git-message ${gitStatus?.status || "unchecked"}`}>
          {gitStatus ? gitStatus.message : "Check remote status before pulling."}
        </p>
      </RailPanel>
    </aside>
  );
}

function RailPanel({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="rail-panel">
      <PanelHeader icon={icon} title={title} />
      <div className="rail-body">{children}</div>
    </section>
  );
}

function PanelHeader({ icon, title, count }: { icon: ReactNode; title: string; count?: number }) {
  return (
    <header className="panel-header">
      <span className="panel-title">
        {icon}
        {title}
      </span>
      {typeof count === "number" && <span className="count-badge">{count}</span>}
    </header>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyState({
  icon,
  title,
  detail,
  setupStatus,
}: {
  icon: ReactNode;
  title: string;
  detail?: string;
  setupStatus?: DashboardState["setup_status"];
}) {
  return (
    <section className="empty-state">
      <div className="empty-radar" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="empty-icon">{icon}</div>
      <div className="empty-copy">
        <h3>{title}</h3>
        {detail && <p>{detail}</p>}
      </div>
      <SetupChecklist setupStatus={setupStatus} />
      <div className="empty-readout" aria-label="Empty state readout">
        <StatusLine label="DB" value="online" />
        <StatusLine label="Run" value={setupStatus?.has_runs ? "history" : "needed"} />
        <StatusLine label="Next" value={setupStatus?.stage || "local"} />
      </div>
    </section>
  );
}

function SetupChecklist({ setupStatus }: { setupStatus?: DashboardState["setup_status"] }) {
  const [copiedCheckId, setCopiedCheckId] = useState("");
  const checks = Array.isArray(setupStatus?.checks) ? setupStatus.checks : [];
  if (!checks.length) {
    return null;
  }

  async function copyCommand(check: SetupCheck) {
    if (!check.command || !navigator.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(check.command);
      setCopiedCheckId(check.check_id);
      window.setTimeout(() => setCopiedCheckId(""), 1200);
    } catch {
      setCopiedCheckId("");
    }
  }

  return (
    <div className="setup-checklist" aria-label="First useful report checklist">
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
            {check.command && (
              <div className="setup-command">
                <code>{check.command}</code>
                <button
                  aria-label={`Copy ${check.label} command`}
                  onClick={() => void copyCommand(check)}
                  title={copiedCheckId === check.check_id ? "Copied" : "Copy command"}
                  type="button"
                >
                  {copiedCheckId === check.check_id ? <Check size={14} /> : <Copy size={14} />}
                </button>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function setupCheckTone(status: string) {
  if (status === "done") {
    return "done";
  }
  if (status === "blocked") {
    return "blocked";
  }
  if (status === "active") {
    return "active";
  }
  return "todo";
}

function setupCheckLabel(status: string) {
  if (status === "done") {
    return "Done";
  }
  if (status === "blocked") {
    return "Blocked";
  }
  if (status === "active") {
    return "Next";
  }
  return "Later";
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

function InlineEmpty({ title }: { title: string }) {
  return (
    <div className="inline-empty">
      <AlertTriangle size={16} />
      <span>{title}</span>
    </div>
  );
}

function SourceRefs({ refs }: { refs: SourceRef[] }) {
  if (!refs.length) {
    return (
      <div className="source-row">
        <span className="source-chip muted">source refs unavailable</span>
      </div>
    );
  }
  return (
    <div className="source-row" aria-label="Source references">
      {refs.slice(0, 4).map((ref) => {
        const href = telegramMessageUrl(ref);
        const label = `${ref.channel}#${ref.id}`;
        if (!href) {
          return (
            <span className="source-chip" key={`${ref.channel}-${ref.id}`}>
              {label}
            </span>
          );
        }
        return (
          <a
            className="source-chip source-link"
            href={href}
            key={`${ref.channel}-${ref.id}`}
            target="_blank"
            rel="noreferrer"
            title="Open Telegram source"
          >
            <span>{label}</span>
            <ExternalLink size={12} aria-hidden="true" />
          </a>
        );
      })}
      {refs.length > 4 && <span className="source-chip muted">+{refs.length - 4}</span>}
    </div>
  );
}

function telegramMessageUrl(ref: SourceRef) {
  const channel = String(ref.channel || "").trim().replace(/^@+/, "");
  const id = String(ref.id || "").trim();
  if (!/^[A-Za-z][A-Za-z0-9_]{3,31}$/.test(channel) || !/^\d+$/.test(id)) {
    return "";
  }
  return `https://t.me/${channel}/${id}`;
}

function buildMetrics(state: DashboardState): Metric[] {
  const activeProfiles = state.profiles.filter((profile) => profile.enabled).length;
  const totalAlerts = state.runs.reduce((sum, run) => sum + (run.manifest.alert_count ?? 0), 0);
  const pendingPatches = state.profile_patch_suggestions.filter((patch) => patch.status === "pending").length;
  const activeTargets = state.delivery_targets.filter((target) => target.enabled).length;

  return [
    { label: "Runs", value: String(state.runs.length), detail: latestRunDetail(state.runs), tone: "teal" },
    { label: "Alerts", value: String(totalAlerts), detail: `${activeTargets} target${activeTargets === 1 ? "" : "s"}`, tone: "rust" },
    { label: "Profiles", value: String(activeProfiles), detail: `${pendingPatches} diff${pendingPatches === 1 ? "" : "s"}`, tone: "blue" },
    { label: "Sources", value: String(state.source_stats.length), detail: topSourceDetail(state.source_stats), tone: "amber" },
  ];
}

function buildTabCounts(state: DashboardState): Record<Tab, number> {
  const feedbackCount = state.feedback_summary?.exportable_count ?? 0;
  return {
    inbox: state.inbox.length,
    profiles: state.profiles.length,
    runs: state.runs.length,
    settings: state.delivery_targets.length + state.source_insights.length + feedbackCount,
  };
}

function buildBoardMeta(activeTab: Tab, state: DashboardState) {
  const metas: Record<Tab, { title: string; detail: string; value: string; tone: "amber" | "teal" | "rust" | "blue" }> = {
    inbox: {
      title: "Review Queue",
      detail: state.inbox.length ? "Pending review cards sorted by latest signal." : "Queue is clear in the current database.",
      value: `${state.inbox.length}`,
      tone: "amber",
    },
    profiles: {
      title: "Profile Control",
      detail: `${state.profiles.filter((profile) => profile.enabled).length} enabled profiles, ${
        state.profile_patch_suggestions.filter((patch) => patch.status === "pending").length
      } pending diffs.`,
      value: `${state.profiles.length}`,
      tone: "blue",
    },
    runs: {
      title: "Run Ledger",
      detail: state.runs.length ? `Latest run started ${formatDate(state.runs[0].started_at)}.` : "Run history is empty.",
      value: `${state.runs.length}`,
      tone: "teal",
    },
    settings: {
      title: "Delivery Matrix",
      value: `${
        state.delivery_targets.length +
        state.source_stats.length +
        state.source_insights.length +
        (state.feedback_summary?.exportable_count ?? 0)
      }`,
      detail: `${state.delivery_targets.filter((target) => target.enabled).length} active targets, ${
        state.source_stats.length
      } sources tracked, ${state.source_insights.length} source actions.`,
      tone: "rust",
    },
  };
  return metas[activeTab];
}

function latestRunDetail(runs: Run[]) {
  if (!runs.length) {
    return "no history";
  }
  return formatDate(runs[0].started_at);
}

function formatRunQuality(quality?: Run["quality"]) {
  if (!quality) {
    return "quality n/a";
  }
  if (!quality.llm_provider) {
    return quality.semantic_stage || "semantic n/a";
  }
  const provider = quality.llm_provider || quality.semantic_stage || "semantic n/a";
  const cache =
    typeof quality.cache_hit_rate === "number" ? `${Math.round(quality.cache_hit_rate * 100)}% cache` : "cache n/a";
  const latency = typeof quality.latency_ms === "number" ? `${quality.latency_ms}ms` : "latency n/a";
  return `${provider} / ${cache} / ${latency}`;
}

function formatRunDiagnostics(quality?: Run["quality"]) {
  const count = quality?.diagnostic_count ?? 0;
  if (!count) {
    return "diagnostics ok";
  }
  const failures = quality?.diagnostic_failure_count ?? 0;
  const warnings = quality?.diagnostic_warning_count ?? 0;
  const code = quality?.top_diagnostic_code || "diagnostic";
  if (failures) {
    return `${failures} failure / ${code}`;
  }
  if (warnings) {
    return `${warnings} warning / ${code}`;
  }
  return `${count} info / ${code}`;
}

function diagnosticTone(quality?: Run["quality"]) {
  if ((quality?.diagnostic_failure_count ?? 0) > 0) {
    return "diagnostic-pill danger";
  }
  if ((quality?.diagnostic_warning_count ?? 0) > 0) {
    return "diagnostic-pill warn";
  }
  if ((quality?.diagnostic_count ?? 0) > 0) {
    return "diagnostic-pill info";
  }
  return "diagnostic-pill ok";
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

function toneClass(value: string) {
  const normalized = value.toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
  return normalized || "unknown";
}

function shortId(value: string) {
  if (value.length <= 18) {
    return value;
  }
  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}

function formatDate(value?: string) {
  if (!value) {
    return "unknown";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

function selectRunArtifact(artifacts?: RunArtifact[]) {
  if (!artifacts?.length) {
    return null;
  }
  return artifacts.find(isReportHtmlArtifact) ?? artifacts.find(isReportMarkdownArtifact) ?? null;
}

function isReportHtmlArtifact(artifact: RunArtifact) {
  return artifact.path.endsWith("report.html");
}

function isReportMarkdownArtifact(artifact: RunArtifact) {
  return artifact.path.endsWith("report.md") && Boolean(artifact.type?.includes("report"));
}

function artifactHref(path: string) {
  return `/artifacts/${encodeURIComponent(path)}`;
}

function shortPath(path: string) {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.length > 2 ? parts.slice(-2).join("/") : path;
}

function formatGitRemoteState(status: GitUpdateStatus | null) {
  if (!status) {
    return "unchecked";
  }
  if (status.dirty) {
    return `dirty ${status.dirty_count}`;
  }
  return status.status.replace(/_/g, " ");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
