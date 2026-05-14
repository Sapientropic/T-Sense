import { useEffect, useRef, useState } from "react";

import { AiApiSettingsPanel } from "./settings/ai-panel";
import { LearningPanel } from "./settings/learning-panel";
import { NotificationsPanel } from "./settings/notifications-panel";
import { SourceImportPanel } from "./settings/source-import-panel";
import { SourceInsightsPanel } from "./settings/source-insights-panel";
import { SourceLibraryPanel } from "./settings/source-library-panel";
import { SettingsTaskSwitch, type SettingsTask } from "./settings/task-switch";
import { UpdatesPanel } from "./settings/updates-panel";
import type {
  DashboardState,
  DeskAiSettingsStatus,
  DeskBotGatewayStatus,
  DeskBotIdentityResult,
  DeskNotificationTokenStatus,
  DeskSourcesResult,
  DeliveryChatDetectionResult,
  DeliveryTestResult,
  DeliveryTarget,
  FeedbackExportResult,
  FeedbackProfileSuggestionsResult,
  GitUpdateStatus,
  Profile,
  SourceImportResult,
  SourceInsight,
  SourceStat,
} from "../domain/types";

export type { SettingsTask } from "./settings/task-switch";
export {
  botGatewayBackgroundLine,
  botGatewayCanInstallBackground,
  botGatewayStatusLine,
  botIdentityResultLine,
} from "./settings/bot-gateway-panel";
export {
  SOURCE_LIBRARY_PAGE_SIZE,
  filterDeskSourcesByQuery,
  paginatedDeskSources,
  sourceLibraryActivityLabel,
  sourceLibraryCountLabel,
  sourceTopicsEditState,
} from "./settings/source-library-panel";

export type SettingsSourcesController = {
  sourceStats: SourceStat[];
  sourceInsights: SourceInsight[];
  sourceLibrary: DeskSourcesResult | null;
  sourceLibraryError: string | null;
  sourceImportResult: SourceImportResult | null;
  profiles: Profile[];
  previewSourceImport: (sources: string, topic: string) => Promise<SourceImportResult>;
  importSources: (sources: string, topic: string) => Promise<SourceImportResult>;
  importStarterSources: (topic: string) => Promise<SourceImportResult>;
  previewSourceAssistant: (
    instruction: string,
    topic: string,
    confirmExternalAi?: boolean,
    profileId?: string,
    folderName?: string,
  ) => Promise<SourceImportResult>;
  applySourceAssistant: (
    instruction: string,
    topic: string,
    confirmExternalAi?: boolean,
    resolvedPlan?: SourceImportResult["resolved_plan"],
    profileId?: string,
    folderName?: string,
  ) => Promise<SourceImportResult>;
  setSourceEnabled: (sourceId: string, enabled: boolean) => Promise<void>;
  removeSource: (sourceId: string) => Promise<void>;
  setSourceTopics: (sourceId: string, topics: string[]) => Promise<void>;
};

export type SettingsNotificationsController = {
  targets: DeliveryTarget[];
  deliveryTest: DeliveryTestResult | null;
  deliveryChatDetection: DeliveryChatDetectionResult | null;
  notificationTokenStatus: DeskNotificationTokenStatus | null;
  notificationTokenError: string | null;
  botGatewayStatus: DeskBotGatewayStatus | null;
  botGatewayError: string | null;
  botIdentityResult: DeskBotIdentityResult | null;
  saveDeliveryTarget: (targetId: string, chatId: string, enabled: boolean) => Promise<void>;
  detectDeliveryChatId: (targetId: string) => Promise<DeliveryChatDetectionResult>;
  saveNotificationToken: (token: string) => Promise<void>;
  clearNotificationToken: () => Promise<void>;
  applyBotIdentity: () => Promise<void>;
  installBotGatewayAutostart: () => Promise<void>;
  removeBotGatewayAutostart: () => Promise<void>;
  testDeliveryTarget: (targetId: string, chatId: string) => Promise<void>;
};

export type SettingsAiController = {
  aiSettingsStatus: DeskAiSettingsStatus | null;
  aiSettingsError: string | null;
  saveAiApiKey: (provider: string, apiKey: string) => Promise<void>;
  clearAiApiKey: (provider: string) => Promise<void>;
};

export type SettingsLearningController = {
  feedbackSummary?: DashboardState["feedback_summary"];
  feedbackExport: FeedbackExportResult | null;
  feedbackProfileSuggestions: FeedbackProfileSuggestionsResult | null;
  exportFeedback: () => void;
  generateFeedbackProfileSuggestions: () => void;
  openProfileDrafts: () => void;
  clearFeedback: () => void;
  undoFeedbackDecision: (cardId: string) => void;
  runAgainWithLearning: () => void;
};

export type SettingsUpdatesController = {
  gitStatus: GitUpdateStatus | null;
  gitBusy: boolean;
  checkUpdates: () => void;
  pullLatest: () => void;
};

export function SettingsView({
  sources,
  notifications,
  ai,
  learning,
  updates,
  busy,
  focusTarget,
  onFocusHandled,
}: {
  sources: SettingsSourcesController;
  notifications: SettingsNotificationsController;
  ai: SettingsAiController;
  learning: SettingsLearningController;
  updates: SettingsUpdatesController;
  busy: boolean;
  focusTarget?: SettingsTask | null;
  onFocusHandled?: () => void;
}) {
  const {
    sourceStats,
    sourceInsights,
    sourceLibrary,
    sourceLibraryError,
    sourceImportResult,
    profiles,
    previewSourceImport,
    importSources,
    importStarterSources,
    previewSourceAssistant,
    applySourceAssistant,
    setSourceEnabled,
    removeSource,
    setSourceTopics,
  } = sources;
  const {
    targets,
    deliveryTest,
    deliveryChatDetection,
    notificationTokenStatus,
    notificationTokenError,
    botGatewayStatus,
    botGatewayError,
    botIdentityResult,
    saveDeliveryTarget,
    detectDeliveryChatId,
    saveNotificationToken,
    clearNotificationToken,
    applyBotIdentity,
    installBotGatewayAutostart,
    removeBotGatewayAutostart,
    testDeliveryTarget,
  } = notifications;
  const { aiSettingsStatus, aiSettingsError, saveAiApiKey, clearAiApiKey } = ai;
  const {
    feedbackSummary,
    feedbackExport,
    feedbackProfileSuggestions,
    exportFeedback,
    generateFeedbackProfileSuggestions,
    openProfileDrafts,
    clearFeedback,
    undoFeedbackDecision,
    runAgainWithLearning,
  } = learning;
  const { gitStatus, gitBusy, checkUpdates, pullLatest } = updates;
  const notificationsPanelRef = useRef<HTMLDivElement | null>(null);
  const aiPanelRef = useRef<HTMLDivElement | null>(null);
  const [activeTask, setActiveTask] = useState<SettingsTask>("sources");

  useEffect(() => {
    if (!focusTarget) {
      return;
    }
    setActiveTask(focusTarget);
    const panel = focusTarget === "notifications" ? notificationsPanelRef.current : focusTarget === "ai" ? aiPanelRef.current : null;
    if (!panel) {
      onFocusHandled?.();
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
        feedbackCount={(feedbackSummary?.exportable_count ?? 0) + (feedbackSummary?.pending_profile_diff_count ?? 0)}
        evidenceCount={sourceStats.length}
        updateCount={settingsUpdateCount(gitStatus)}
        aiCount={aiSettingsStatus?.configured_count ?? 0}
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
            hasSavedSources={Boolean(sourceLibrary?.source_count)}
            importSources={importSources}
            importStarterSources={importStarterSources}
            previewSourceAssistant={previewSourceAssistant}
            applySourceAssistant={applySourceAssistant}
            previewSourceImport={previewSourceImport}
            profiles={profiles}
            result={sourceImportResult}
          />
          <SourceLibraryPanel
            busy={busy}
            error={sourceLibraryError}
            library={sourceLibrary}
            removeSource={removeSource}
            setSourceEnabled={setSourceEnabled}
            setSourceTopics={setSourceTopics}
            sourceStats={sourceStats}
          />
        </div>
      </section>

      <section
        className="settings-section settings-section-ai"
        aria-label="AI API settings"
        data-active={activeTask === "ai" ? "true" : "false"}
      >
        <AiApiSettingsPanel
          busy={busy}
          clearAiApiKey={clearAiApiKey}
          error={aiSettingsError}
          saveAiApiKey={saveAiApiKey}
          status={aiSettingsStatus}
          panelRef={aiPanelRef}
        />
      </section>

      <section
        className="settings-section settings-section-notifications"
        aria-label="Notifications settings"
        data-active={activeTask === "notifications" ? "true" : "false"}
      >
        <NotificationsPanel
          applyBotIdentity={applyBotIdentity}
          botGatewayError={botGatewayError}
          botGatewayStatus={botGatewayStatus}
          botIdentityResult={botIdentityResult}
          busy={busy}
          clearNotificationToken={clearNotificationToken}
          deliveryChatDetection={deliveryChatDetection}
          deliveryTest={deliveryTest}
          detectDeliveryChatId={detectDeliveryChatId}
          installBotGatewayAutostart={installBotGatewayAutostart}
          notificationTokenError={notificationTokenError}
          notificationTokenStatus={notificationTokenStatus}
          panelRef={notificationsPanelRef}
          removeBotGatewayAutostart={removeBotGatewayAutostart}
          saveDeliveryTarget={saveDeliveryTarget}
          saveNotificationToken={saveNotificationToken}
          targets={targets}
          testDeliveryTarget={testDeliveryTarget}
        />
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
          generateProfileSuggestions={generateFeedbackProfileSuggestions}
          openProfileDrafts={openProfileDrafts}
          runAgainWithLearning={runAgainWithLearning}
          summary={feedbackSummary}
          suggestionResult={feedbackProfileSuggestions}
          undoFeedbackDecision={undoFeedbackDecision}
        />
      </section>

      <section
        className="settings-section settings-section-evidence"
        aria-label="Source evidence settings"
        data-active={activeTask === "evidence" ? "true" : "false"}
      >
        <SourceInsightsPanel sourceInsights={sourceInsights} sourceStats={sourceStats} />
      </section>
      <section
        className="settings-section settings-section-updates"
        aria-label="Updates settings"
        data-active={activeTask === "updates" ? "true" : "false"}
      >
        <UpdatesPanel gitBusy={gitBusy} gitStatus={gitStatus} onCheckUpdates={checkUpdates} onPullLatest={pullLatest} />
      </section>
    </section>
  );
}

function settingsUpdateCount(status: GitUpdateStatus | null) {
  if (!status) {
    return 0;
  }
  return Math.max(0, status.behind);
}
