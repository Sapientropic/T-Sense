import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
  Activity,
  Bell,
  CircleDashed,
  CirclePause,
  CirclePlay,
  Database,
  Eye,
  KeyRound,
  Save,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react";

import { InlineEmpty, PanelHeader } from "./common";
import {
  deliveryTargetDetail,
  deliveryTargetName,
  metricShortLabel,
  percentWidth,
  sourceHeatClass,
  sourceSignalScore,
} from "../domain/display";
import { channelDisplayName, formatPercent } from "../domain/format";
import { LearningPanel } from "./settings/learning-panel";
import type {
  DashboardState,
  DeskNotificationTokenStatus,
  DeskSource,
  DeskSourcesResult,
  DeliveryTestResult,
  DeliveryTarget,
  FeedbackExportResult,
  SourceImportResult,
  SourceInsight,
  SourceStat,
} from "../domain/types";

const SOURCE_CARD_LIMIT = 3;
const SOURCE_HEAT_LIMIT = 72;
const SOURCE_ACTION_LIMIT = 6;
export const SOURCE_LIBRARY_PAGE_SIZE = 8;

type SettingsTask = "sources" | "notifications" | "learning";

export function SettingsView({
  targets,
  sourceStats,
  sourceInsights,
  feedbackSummary,
  feedbackExport,
  exportFeedback,
  clearFeedback,
  undoFeedbackDecision,
  runAgainWithLearning,
  deliveryTest,
  notificationTokenStatus,
  notificationTokenError,
  sourceLibrary,
  sourceLibraryError,
  sourceImportResult,
  saveDeliveryTarget,
  saveNotificationToken,
  clearNotificationToken,
  testDeliveryTarget,
  previewSourceImport,
  importSources,
  setSourceEnabled,
  setSourceTopics,
  busy,
  focusTarget,
  onFocusHandled,
}: {
  targets: DeliveryTarget[];
  sourceStats: SourceStat[];
  sourceInsights: SourceInsight[];
  feedbackSummary?: DashboardState["feedback_summary"];
  feedbackExport: FeedbackExportResult | null;
  exportFeedback: () => void;
  clearFeedback: () => void;
  undoFeedbackDecision: (cardId: string) => void;
  runAgainWithLearning: () => void;
  deliveryTest: DeliveryTestResult | null;
  notificationTokenStatus: DeskNotificationTokenStatus | null;
  notificationTokenError: string | null;
  sourceLibrary: DeskSourcesResult | null;
  sourceLibraryError: string | null;
  sourceImportResult: SourceImportResult | null;
  saveDeliveryTarget: (targetId: string, chatId: string, enabled: boolean) => Promise<void>;
  saveNotificationToken: (token: string) => Promise<void>;
  clearNotificationToken: () => Promise<void>;
  testDeliveryTarget: (targetId: string, chatId: string) => Promise<void>;
  previewSourceImport: (sources: string, topic: string) => Promise<SourceImportResult>;
  importSources: (sources: string, topic: string) => Promise<SourceImportResult>;
  setSourceEnabled: (sourceId: string, enabled: boolean) => Promise<void>;
  setSourceTopics: (sourceId: string, topics: string[]) => Promise<void>;
  busy: boolean;
  focusTarget?: "notifications" | null;
  onFocusHandled?: () => void;
}) {
  const notificationsPanelRef = useRef<HTMLDivElement | null>(null);
  const [activeTask, setActiveTask] = useState<SettingsTask>("sources");

  useEffect(() => {
    if (focusTarget !== "notifications") {
      return;
    }
    setActiveTask("notifications");
    const panel = notificationsPanelRef.current;
    if (!panel) {
      return;
    }
    panel.scrollIntoView({ block: "start", behavior: "auto" });
    const target =
      panel.querySelector<HTMLElement>("input:not(:disabled), button:not(:disabled), textarea:not(:disabled), select:not(:disabled)") ?? panel;
    target.focus({ preventScroll: true });
    onFocusHandled?.();
  }, [focusTarget, onFocusHandled]);

  return (
    <section className="settings-workbench" aria-label="Settings workspace">
      <SettingsTaskSwitch
        activeTask={activeTask}
        feedbackCount={feedbackSummary?.exportable_count ?? 0}
        notificationCount={targets.length}
        onSelect={setActiveTask}
        sourceCount={sourceLibrary?.source_count ?? sourceStats.length}
      />
      <section
        className="settings-section settings-section-sources"
        aria-label="Sources settings"
        data-active={activeTask === "sources" ? "true" : "false"}
      >
        <div className="settings-grid sources-settings-grid">
          <SourceImportPanel
            busy={busy}
            importSources={importSources}
            previewSourceImport={previewSourceImport}
            result={sourceImportResult}
          />
          <SourceLibraryPanel
            busy={busy}
            error={sourceLibraryError}
            library={sourceLibrary}
            setSourceEnabled={setSourceEnabled}
            setSourceTopics={setSourceTopics}
          />
        </div>
        <details className="settings-evidence">
          <summary>
            <Activity size={16} />
            <span>Source evidence</span>
          </summary>
          <div className="settings-evidence-grid">
            <div className="table-section source-yield-panel">
              <PanelHeader icon={<Activity size={18} />} title="Yield History" count={sourceStats.length} />
              {sourceStats.length ? <SourceYieldMap sources={sourceStats} /> : <InlineEmpty title="No source stats yet" />}
            </div>
            <div className="table-section source-actions-panel">
              <PanelHeader icon={<ShieldCheck size={18} />} title="Source Actions" count={sourceInsights.length} />
              {sourceInsights.length ? <SourceActionGrid insights={sourceInsights} /> : <InlineEmpty title="No source actions yet" />}
            </div>
          </div>
        </details>
      </section>

      <section
        className="settings-section settings-section-notifications"
        aria-label="Notifications settings"
        data-active={activeTask === "notifications" ? "true" : "false"}
      >
        <div className="table-section delivery-targets-panel" ref={notificationsPanelRef} tabIndex={-1} aria-label="Notifications">
          <PanelHeader icon={<Bell size={18} />} title="Notifications" count={targets.length} />
          <NotificationTokenPanel
            busy={busy}
            clearNotificationToken={clearNotificationToken}
            error={notificationTokenError}
            saveNotificationToken={saveNotificationToken}
            status={notificationTokenStatus}
          />
          {targets.length ? (
            <div className="delivery-target-list">
              {targets.map((target) => (
                <DeliveryTargetEditor
                  busy={busy}
                  key={target.target_id}
                  saveDeliveryTarget={saveDeliveryTarget}
                  target={target}
                  testDeliveryTarget={testDeliveryTarget}
                  testResult={deliveryTest?.target_id === target.target_id ? deliveryTest : null}
                />
              ))}
            </div>
          ) : (
            <InlineEmpty title="No notification channels set up" />
          )}
        </div>
      </section>

      <section
        className="settings-section settings-section-feedback"
        aria-label="Feedback settings"
        data-active={activeTask === "learning" ? "true" : "false"}
      >
        <LearningPanel
          busy={busy}
          clearFeedback={clearFeedback}
          exportFeedback={exportFeedback}
          exportResult={feedbackExport}
          runAgainWithLearning={runAgainWithLearning}
          summary={feedbackSummary}
          undoFeedbackDecision={undoFeedbackDecision}
        />
      </section>
    </section>
  );
}

function SettingsTaskSwitch({
  activeTask,
  sourceCount,
  notificationCount,
  feedbackCount,
  onSelect,
}: {
  activeTask: SettingsTask;
  sourceCount: number;
  notificationCount: number;
  feedbackCount: number;
  onSelect: (task: SettingsTask) => void;
}) {
  const tasks: Array<{ id: SettingsTask; label: string; count: number; detail: string }> = [
    { id: "sources", label: "Sources", count: sourceCount, detail: "Add and manage channels" },
    { id: "notifications", label: "Notify", count: notificationCount, detail: "Token and delivery" },
    { id: "learning", label: "Learning", count: feedbackCount, detail: "Export feedback" },
  ];
  return (
    <div className="settings-task-switch" aria-label="Settings task switcher">
      {tasks.map((task) => (
        <button
          aria-pressed={activeTask === task.id}
          key={task.id}
          onClick={() => onSelect(task.id)}
          type="button"
        >
          <span>{task.label}</span>
          <strong>{task.count}</strong>
          <small>{task.detail}</small>
        </button>
      ))}
    </div>
  );
}

function NotificationTokenPanel({
  status,
  error,
  busy,
  saveNotificationToken,
  clearNotificationToken,
}: {
  status: DeskNotificationTokenStatus | null;
  error: string | null;
  busy: boolean;
  saveNotificationToken: (token: string) => Promise<void>;
  clearNotificationToken: () => Promise<void>;
}) {
  const [token, setToken] = useState("");
  const configured = status?.configured === true;
  const sourceLabel = notificationTokenSourceLabel(status?.source);
  const canSave = status?.can_save !== false;
  const canClear = status?.can_clear === true;
  return (
    <form
      className="notification-token-panel"
      onSubmit={(event) => {
        event.preventDefault();
        if (!token.trim() || !canSave) {
          return;
        }
        void saveNotificationToken(token).then(() => setToken(""));
      }}
    >
      <div className="notification-token-head">
        <KeyRound size={16} />
        <div>
          <strong>Telegram bot token</strong>
          <small>{status ? `${configured ? "Configured" : "Missing"} · ${sourceLabel}` : "Checking token status"}</small>
        </div>
        <span className={configured ? "status enabled" : "status disabled"}>{configured ? "Ready" : "Needed"}</span>
      </div>
      <label className="delivery-field">
        <span>Bot token</span>
        <input
          autoComplete="new-password"
          disabled={busy || !canSave}
          onChange={(event) => setToken(event.target.value)}
          placeholder={canSave ? "123456:ABC..." : "Windows Credential Manager unavailable"}
          type="password"
          value={token}
        />
      </label>
      <p className="delivery-note">
        Token text is never shown again. Environment variables still take priority; dry-run tests do not send Telegram messages.
      </p>
      {(status?.detail || error) && (
        <p className={error ? "delivery-token-warning" : "delivery-note"} role={error ? "alert" : undefined}>
          {error || status?.detail}
        </p>
      )}
      <div className="delivery-actions">
        <button className="text-button" disabled={busy || !canSave || !token.trim()} type="submit">
          <Save size={15} />
          <span>{busy ? "Saving" : "Save token"}</span>
        </button>
        <button
          className="text-button secondary"
          disabled={busy || !canClear}
          onClick={() => void clearNotificationToken()}
          type="button"
        >
          <Trash2 size={15} />
          <span>Clear saved token</span>
        </button>
      </div>
    </form>
  );
}

function notificationTokenSourceLabel(source?: string) {
  if (source === "environment") {
    return "environment override";
  }
  if (source === "windows_credential_manager") {
    return "Windows Credential Manager";
  }
  if (source === "credential_error") {
    return "credential store error";
  }
  return "not configured";
}

function SourceLibraryPanel({
  library,
  error,
  busy,
  setSourceEnabled,
  setSourceTopics,
}: {
  library: DeskSourcesResult | null;
  error: string | null;
  busy: boolean;
  setSourceEnabled: (sourceId: string, enabled: boolean) => Promise<void>;
  setSourceTopics: (sourceId: string, topics: string[]) => Promise<void>;
}) {
  const sources = library?.sources ?? [];
  const isLoading = !library && !error;
  const [query, setQuery] = useState("");
  const [selectedTopic, setSelectedTopic] = useState("");
  const [showAllTopics, setShowAllTopics] = useState(false);
  const [showSourceList, setShowSourceList] = useState(false);
  const [visibleCount, setVisibleCount] = useState(SOURCE_LIBRARY_PAGE_SIZE);
  const filteredSources = filterDeskSourcesByQuery(sources, query, selectedTopic);
  const visibleSources = paginatedDeskSources(filteredSources, visibleCount);
  const hiddenSourceCount = Math.max(0, filteredSources.length - visibleSources.length);
  const topics = library?.topics ?? [];
  const topicPreview = showAllTopics ? topics : topics.slice(0, 12);
  const hiddenTopicCount = Math.max(0, topics.length - topicPreview.length);
  const hasFilters = Boolean(query.trim() || selectedTopic);
  const listVisible = showSourceList || hasFilters;
  const countLabel = listVisible
    ? sourceLibraryCountLabel(visibleSources.length, filteredSources.length, hasFilters)
    : `${filteredSources.length} saved; search or manage when needed`;
  useEffect(() => {
    if (selectedTopic && !sources.some((source) => source.topics.includes(selectedTopic))) {
      setSelectedTopic("");
    }
  }, [selectedTopic, sources]);
  useEffect(() => {
    setVisibleCount(SOURCE_LIBRARY_PAGE_SIZE);
  }, [query, selectedTopic, library?.source_count]);
  return (
    <div className="table-section source-library-panel">
      <PanelHeader icon={<Database size={18} />} title="Saved Sources" count={library?.source_count} />
      {error && (
        <div className="source-library-error" role="status">
          <strong>Saved sources need a refresh</strong>
          <span>{error}</span>
        </div>
      )}
      {library && (
        <div className="source-library-summary" aria-label="Saved source summary">
          <span>
            <strong>{library.enabled_count}</strong>
            active
          </span>
          <span>
            <strong>{library.source_count - library.enabled_count}</strong>
            paused
          </span>
          <div className="source-library-topics" aria-label="Filter saved sources by topic" title={library.topics.join(", ")}>
            {topicPreview.length ? (
              <>
                {topicPreview.map((topic) => (
                  <button
                    aria-pressed={selectedTopic === topic}
                    key={topic}
                    onClick={() => setSelectedTopic(selectedTopic === topic ? "" : topic)}
                    type="button"
                  >
                    {topic}
                  </button>
                ))}
                {(hiddenTopicCount > 0 || showAllTopics) && (
                  <button
                    aria-expanded={showAllTopics}
                    className="topic-overflow-toggle"
                    onClick={() => setShowAllTopics((current) => !current)}
                    type="button"
                  >
                    {showAllTopics ? "Show fewer" : `+${hiddenTopicCount}`}
                  </button>
                )}
              </>
            ) : (
              <small>No topics yet</small>
            )}
          </div>
        </div>
      )}
      {sources.length > 0 && (
        <div className="source-library-search">
          <label htmlFor="source-library-query">Find source</label>
          <input
            id="source-library-query"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="@remote_jobs or jobs"
            type="search"
            value={query}
          />
          <small aria-live="polite">
            {countLabel}
          </small>
          {hasFilters && (
            <button
              className="text-button secondary source-library-clear"
              onClick={() => {
                setQuery("");
                setSelectedTopic("");
              }}
              type="button"
            >
              Clear filters
            </button>
          )}
        </div>
      )}
      {isLoading ? (
        <InlineEmpty title="Loading saved sources" />
      ) : sources.length && !listVisible ? (
        <div className="source-library-gate" aria-label="Saved source list collapsed">
          <div>
            <strong>{library?.source_count ?? sources.length} saved sources</strong>
            <span>Use search for one source, or open the list only when you need bulk cleanup.</span>
          </div>
          <button
            className="text-button secondary"
            onClick={() => setShowSourceList(true)}
            type="button"
          >
            Show first {SOURCE_LIBRARY_PAGE_SIZE}
          </button>
        </div>
      ) : sources.length ? (
        <div className="source-library-list">
          {visibleSources.map((source) => (
            <SourceLibraryRow
              busy={busy}
              key={source.source_id}
              setSourceEnabled={setSourceEnabled}
              setSourceTopics={setSourceTopics}
              source={source}
            />
          ))}
          {!filteredSources.length && <InlineEmpty title="No saved source matches" />}
          {hiddenSourceCount > 0 && (
            <button
              className="text-button secondary source-library-more"
              onClick={() => setVisibleCount((count) => count + SOURCE_LIBRARY_PAGE_SIZE)}
              type="button"
            >
              <span>Load 8 more</span>
              <small>{hiddenSourceCount} remaining</small>
            </button>
          )}
        </div>
      ) : (
        !error && <InlineEmpty title="No saved sources yet" />
      )}
    </div>
  );
}

export function filterDeskSourcesByQuery(sources: DeskSource[], query: string, selectedTopic = "") {
  const normalizedQuery = query.trim().toLowerCase();
  const normalizedTopic = selectedTopic.trim().toLowerCase();
  if (!normalizedQuery && !normalizedTopic) {
    return sources;
  }
  return sources.filter((source) => {
    const matchesTopic = normalizedTopic
      ? source.topics.some((topic) => topic.trim().toLowerCase() === normalizedTopic)
      : true;
    if (!matchesTopic) {
      return false;
    }
    if (!normalizedQuery) {
      return true;
    }
    return [source.label, source.channel, source.priority, ...source.topics]
      .join(" ")
      .toLowerCase()
      .includes(normalizedQuery);
  });
}

export function paginatedDeskSources(sources: DeskSource[], visibleCount = SOURCE_LIBRARY_PAGE_SIZE) {
  return sources.slice(0, Math.max(0, visibleCount));
}

export function sourceLibraryCountLabel(visibleCount: number, filteredCount: number, hasFilters: boolean) {
  const visible = Math.max(0, visibleCount);
  const filtered = Math.max(0, filteredCount);
  if (hasFilters) {
    if (!filtered) {
      return "No matching sources";
    }
    return visible >= filtered ? `${filtered} matching shown` : `${visible} of ${filtered} matching shown`;
  }
  if (!filtered) {
    return "No saved sources";
  }
  return visible >= filtered ? `Showing all ${filtered}` : `Showing first ${visible} of ${filtered}`;
}

function SourceLibraryRow({
  source,
  busy,
  setSourceEnabled,
  setSourceTopics,
}: {
  source: DeskSource;
  busy: boolean;
  setSourceEnabled: (sourceId: string, enabled: boolean) => Promise<void>;
  setSourceTopics: (sourceId: string, topics: string[]) => Promise<void>;
}) {
  const [editingTopics, setEditingTopics] = useState(false);
  const [topicText, setTopicText] = useState(source.topics.join(", "));
  const [saveError, setSaveError] = useState("");
  const topicInputRef = useRef<HTMLInputElement | null>(null);
  const editorId = `source-topic-editor-${source.source_id.replace(/[^a-z0-9_-]/gi, "-")}`;
  const topicState = sourceTopicsEditState(source.topics, topicText);

  useEffect(() => {
    setTopicText(source.topics.join(", "));
    setEditingTopics(false);
    setSaveError("");
  }, [source.source_id, source.topics]);

  useEffect(() => {
    if (editingTopics) {
      topicInputRef.current?.focus();
    }
  }, [editingTopics]);

  return (
    <article className={`source-library-row ${source.enabled ? "enabled" : "paused"}`}>
      <div className="source-library-main">
        <strong title={source.label}>{source.label}</strong>
        <small title={`@${source.channel}`}>@{source.channel}</small>
      </div>
      <div className="source-library-tags" aria-label={`${source.label} topics`}>
        {source.topics.map((topic) => (
          <span key={topic} title={`Topic: ${topic}`}>
            {topic}
          </span>
        ))}
        <span title="Recent messages scanned for this source">{source.scan_window_hours}h window</span>
        <span title="Source priority">{source.priority}</span>
      </div>
      <div className="source-library-side">
        <span className={source.enabled ? "status enabled" : "status disabled"}>
          {source.enabled ? "Active" : "Paused"}
        </span>
        <button
          aria-label={`${source.label}: ${source.enabled ? "Pause" : "Use"}`}
          className={`text-button ${source.enabled ? "secondary" : ""}`}
          disabled={busy}
          onClick={() => void setSourceEnabled(source.source_id, !source.enabled)}
          type="button"
        >
          {source.enabled ? <CirclePause size={15} /> : <CirclePlay size={15} />}
          <span>{source.enabled ? "Pause" : "Use"}</span>
        </button>
        <button
          aria-controls={editorId}
          aria-expanded={editingTopics}
          aria-label={`${source.label}: ${editingTopics ? "Hide topic editor" : "Edit topics"}`}
          className="text-button secondary"
          disabled={busy}
          onClick={() => {
            setSaveError("");
            setEditingTopics((current) => !current);
          }}
          type="button"
        >
          <span>{editingTopics ? "Hide editor" : "Edit topics"}</span>
        </button>
      </div>
      {editingTopics && (
        <form
          id={editorId}
          className="source-topic-editor"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setTopicText(source.topics.join(", "));
              setSaveError("");
              setEditingTopics(false);
            }
          }}
          onSubmit={(event) => {
            event.preventDefault();
            if (!topicState.canSave) {
              return;
            }
            setSaveError("");
            void setSourceTopics(source.source_id, topicState.topics)
              .then(() => setEditingTopics(false))
              .catch((error: unknown) => {
                setSaveError(error instanceof Error ? error.message : "Could not save topics.");
              });
          }}
        >
          <label>
            <span>Topics</span>
            <input
              maxLength={200}
              onChange={(event) => {
                setTopicText(event.target.value);
                setSaveError("");
              }}
              placeholder="jobs, remote-work"
              ref={topicInputRef}
              type="text"
              value={topicText}
            />
          </label>
          <small aria-live="polite">{saveError || topicState.message}</small>
          <div className="source-topic-actions">
            <button className="text-button" disabled={busy || !topicState.canSave} type="submit">
              <Save size={15} />
              <span>Save topics</span>
            </button>
            <button
              className="text-button secondary"
              disabled={busy}
              onClick={() => {
                setTopicText(source.topics.join(", "));
                setSaveError("");
                setEditingTopics(false);
              }}
              type="button"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </article>
  );
}

export function sourceTopicsEditState(currentTopics: string[], text: string) {
  const rawTopics = text
    .split(/[,\n]/)
    .map((topic) => topic.trim().toLowerCase())
    .filter(Boolean);
  const topics = Array.from(new Set(rawTopics));
  const invalid = topics.find((topic) => !/^[a-z0-9][a-z0-9_-]{1,40}$/.test(topic));
  const normalizedCurrent = currentTopics.map((topic) => topic.trim().toLowerCase()).filter(Boolean);
  const unchanged = topics.join("\0") === normalizedCurrent.join("\0");
  if (invalid) {
    return { canSave: false, topics, message: "Use short tags like jobs or remote-work." };
  }
  if (!topics.length) {
    return { canSave: false, topics, message: "Add at least one topic tag." };
  }
  if (topics.length > 8) {
    return { canSave: false, topics, message: "Use fewer topic tags." };
  }
  if (unchanged) {
    return { canSave: false, topics, message: "Topics are unchanged." };
  }
  return { canSave: true, topics, message: "Comma-separated tags. These tags only organize your sources." };
}

function SourceImportPanel({
  result,
  previewSourceImport,
  importSources,
  busy,
}: {
  result: SourceImportResult | null;
  previewSourceImport: (sources: string, topic: string) => Promise<SourceImportResult>;
  importSources: (sources: string, topic: string) => Promise<SourceImportResult>;
  busy: boolean;
}) {
  const [sources, setSources] = useState("");
  const [topic, setTopic] = useState("jobs");
  const [previewKey, setPreviewKey] = useState("");
  const currentKey = `${sources.trim()}\n${topic.trim().toLowerCase() || "jobs"}`;
  const canPreview = sources.trim().length > 0;
  const canImport = canPreview && previewKey === currentKey && result?.dry_run === true;
  const previewSources = result?.preview_sources ?? [];
  return (
    <form
      className="table-section source-import-panel"
      onSubmit={(event) => {
        event.preventDefault();
        if (!canPreview) {
          return;
        }
        void previewSourceImport(sources, topic)
          .then((next) => {
            if (next.dry_run) {
              setPreviewKey(currentKey);
            }
          })
          .catch(() => undefined);
      }}
    >
      <PanelHeader icon={<Upload size={18} />} title="Add Sources" />
      <label className="source-import-field">
        <span>Telegram channels</span>
        <textarea
          onChange={(event) => setSources(event.target.value)}
          placeholder={"@remote_jobs\nhttps://t.me/s/miniapps_jobs"}
          rows={5}
          value={sources}
        />
      </label>
      <label className="source-import-topic">
        <span>Topic</span>
        <input onChange={(event) => setTopic(event.target.value)} type="text" value={topic} />
      </label>
      <p className="delivery-note">Paste channel handles or t.me links, one per line. Preview checks duplicates before anything is saved.</p>
      <div className="source-import-actions">
        <button className="text-button secondary" disabled={busy || !canPreview} type="submit">
          <Eye size={15} />
          <span>{busy ? "Checking" : "Preview sources"}</span>
        </button>
        <button
          className="text-button"
          disabled={busy || !canImport}
          onClick={() => void importSources(sources, topic).catch(() => undefined)}
          type="button"
        >
          <Upload size={15} />
          <span>Import sources</span>
        </button>
      </div>
      {canPreview && !canImport && result?.dry_run && <span className="delivery-dirty">Preview again before importing</span>}
      {result && (
        <div className={`source-import-result ${result.written ? "written" : "preview"}`} role="status">
          <strong>{result.title || (result.written ? "Sources saved" : "Source preview ready")}</strong>
          <span>
            {result.added_count} new / {result.updated_count} updated / {result.unchanged_count} already saved
          </span>
          {previewSources.length > 0 && (
            <div className="source-import-preview-list" aria-label="Preview sources">
              {previewSources.map((source) => (
                <small key={source.source_id}>{source.label}</small>
              ))}
              {result.preview_truncated_count > 0 && <small>+{result.preview_truncated_count} more</small>}
            </div>
          )}
          {result.next_action && <em>{result.next_action}</em>}
        </div>
      )}
    </form>
  );
}

function deliveryChatId(target: DeliveryTarget) {
  return typeof target.config.chat_id === "string" ? target.config.chat_id : "";
}

function DeliveryTargetEditor({
  target,
  testResult,
  saveDeliveryTarget,
  testDeliveryTarget,
  busy,
}: {
  target: DeliveryTarget;
  testResult: DeliveryTestResult | null;
  saveDeliveryTarget: (targetId: string, chatId: string, enabled: boolean) => Promise<void>;
  testDeliveryTarget: (targetId: string, chatId: string) => Promise<void>;
  busy: boolean;
}) {
  const [chatId, setChatId] = useState(deliveryChatId(target));
  const [enabled, setEnabled] = useState(target.enabled);

  useEffect(() => {
    setChatId(deliveryChatId(target));
    setEnabled(target.enabled);
  }, [target]);

  const canEnable = !enabled || chatId.trim().length > 0;
  const hasUnsavedChanges = chatId !== deliveryChatId(target) || enabled !== target.enabled;
  return (
    <form
      className="delivery-target-editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (!canEnable) {
          return;
        }
        void saveDeliveryTarget(target.target_id, chatId, enabled);
      }}
    >
      <div className="delivery-target-head">
        <div>
          <strong title={target.display_name || deliveryTargetName(target)}>
            {target.display_name || deliveryTargetName(target)}
          </strong>
          <small>{target.detail || deliveryTargetDetail(target)}</small>
        </div>
        <span className={target.enabled ? "status enabled" : "status disabled"}>
          {target.status_label || (target.enabled ? "Live" : "Muted")}
        </span>
      </div>
      <label className="delivery-field">
        <span>Telegram chat ID</span>
        <input
          autoComplete="off"
          onChange={(event) => setChatId(event.target.value)}
          placeholder="@channel or -1001234567890"
          type="text"
          value={chatId}
        />
      </label>
      <label className="delivery-toggle">
        <input checked={enabled} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" />
        <span>Allow live notifications</span>
      </label>
      <p className="delivery-note">Paste a Telegram channel handle or the numeric chat ID you want alerts to use.</p>
      <div className="delivery-actions">
        <button className="text-button" disabled={busy || !canEnable} type="submit">
          <Save size={15} />
          <span>{busy ? "Saving" : hasUnsavedChanges ? "Save changes" : "Save settings"}</span>
        </button>
        <button
          className="text-button secondary"
          disabled={busy}
          onClick={() => void testDeliveryTarget(target.target_id, chatId)}
          type="button"
        >
          <CircleDashed size={15} />
          <span>Test without sending</span>
        </button>
      </div>
      <p className="delivery-note">The dry run checks the saved target without sending a Telegram message.</p>
      {hasUnsavedChanges && <span className="delivery-dirty">Unsaved changes</span>}
      {testResult && (
        <div className={`delivery-test-result ${testResult.ok ? "ok" : "failed"}`} role="status">
          <strong>{testResult.title || "Notification test"}</strong>
          <span>{testResult.detail || testResult.status}</span>
        </div>
      )}
    </form>
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
            <span>{insight.next_action?.label || "Review source"}</span>
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
