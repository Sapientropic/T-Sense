import { StrictMode, useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  Inbox,
  Rocket,
  Play,
  Settings,
  UserRoundCog,
} from "lucide-react";
import { errorMessage, postReviewCardAction, undoReviewCardAction } from "./api/client";
import { ActionsView } from "./components/actions";
import { CommandStrip, OpportunitySummaryPanel, ValidationSummaryPanel } from "./components/board-status";
import { InboxView } from "./components/inbox";
import { ProfilesView } from "./components/profiles";
import { RunsView } from "./components/runs";
import { SettingsView, type SettingsTask } from "./components/settings";
import { ConsoleHeader, NavigationRail, WorkbenchHeader } from "./components/shell";
import { buildProfileReportNames } from "./domain/display";
import { isActionableInboxCard, reviewQueueCount } from "./domain/inbox";
import {
  buildBoardMeta,
  buildMetrics,
  buildTabCounts,
  hasBlockingOpportunitySummary,
} from "./domain/projections";
import { useDashboardState } from "./hooks/use-dashboard-state";
import { useDeskActions } from "./hooks/use-desk-actions";
import { useDeskTelegram } from "./hooks/use-desk-telegram";
import { useDeliverySettings } from "./hooks/use-delivery-settings";
import { useFeedbackActions } from "./hooks/use-feedback-actions";
import { useGitActions } from "./hooks/use-git-actions";
import { useProfileActions } from "./hooks/use-profile-actions";
import { useSourceSettings } from "./hooks/use-source-settings";
import { useStatusSurfaces } from "./hooks/use-status-surfaces";
import type { Tab } from "./domain/types";
import "./styles.css";

const tabShell: Array<{ tab: Tab; icon: ReactNode; label: string }> = [
  { tab: "inbox", icon: <Inbox size={17} />, label: "Review" },
  { tab: "actions", icon: <Rocket size={17} />, label: "Start" },
  { tab: "profiles", icon: <UserRoundCog size={17} />, label: "Profiles" },
  { tab: "runs", icon: <Play size={17} />, label: "Runs" },
  { tab: "settings", icon: <Settings size={17} />, label: "Settings" },
];
const startStepCount = 6;

type DeskActionConfirmation = {
  actionId: string;
  title: string;
  detail: string;
  confirmLabel: string;
};

function App() {
  const {
    actions: deskActions,
    results: deskActionResults,
    busyActionId,
    loadError: deskActionsLoadError,
    runError: deskActionRunError,
    runAction,
  } = useDeskActions();
  const deskTelegram = useDeskTelegram();
  const [activeTab, setActiveTab] = useState<Tab>("actions");
  const [busy, setBusy] = useState(false);
  const headerBusy = busy || Boolean(busyActionId) || Boolean(deskTelegram.busy);
  const { state, refresh, loadError } = useDashboardState({ busy: headerBusy });
  const [pendingDeskAction, setPendingDeskAction] = useState<DeskActionConfirmation | null>(null);
  const pendingDeskActionReturnFocus = useRef<HTMLElement | null>(null);
  const [settingsFocusTarget, setSettingsFocusTarget] = useState<SettingsTask | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const { gitBusy, gitStatus, checkUpdates, pullLatest } = useGitActions({ setNotice });
  const updateAvailableCount = Math.max(0, gitStatus?.behind ?? 0);
  const {
    aiSettingsStatus,
    aiSettingsError,
    deskSchedulerStatus,
    deskSchedulerError,
    refreshStatusSurfaces,
    refreshDeskSchedulerStatus,
    saveAiApiKey,
    clearAiApiKey,
  } = useStatusSurfaces({ setBusy, setNotice });
  const {
    deskSources,
    deskSourcesError,
    sourceImportResult,
    previewSourceImport,
    importSources,
    importStarterSources,
    previewSourceAssistant,
    applySourceAssistant,
    removeSource,
    setSourceEnabled,
    setSourceTopics,
  } = useSourceSettings({ refresh, setBusy, setNotice });
  const {
    feedbackExport,
    feedbackProfileSuggestions,
    exportFeedback,
    generateFeedbackProfileSuggestions,
    clearFeedback,
    undoFeedbackDecision,
  } = useFeedbackActions({
    refresh,
    setActiveTab,
    setBusy,
    setNotice,
  });
  const {
    profileCreateResult,
    applyPatch,
    revertPatch,
    replayPatch,
    setAlertMode,
    setProfileEnabled,
    setProfileRuntimeSettings,
    createProfileDraftNote,
    createProfileMatchingPreferencesDraft,
    createProfileFromBrief,
    deleteProfile,
  } = useProfileActions({
    refresh,
    setActiveTab,
    setBusy,
    setNotice,
  });
  const {
    deliveryTest,
    deliveryChatDetection,
    notificationTokenStatus,
    notificationTokenError,
    botGatewayStatus,
    botGatewayError,
    botIdentityResult,
    refreshDeliverySettings,
    saveDeliveryTarget,
    testDeliveryTarget,
    detectDeliveryChatId,
    saveNotificationToken,
    clearNotificationToken,
    applyBotIdentity,
    setBotGatewayAutostart,
  } = useDeliverySettings({
    refresh,
    runAction,
    setBusy,
    setNotice,
  });

  const metrics = useMemo(() => buildMetrics(state), [state]);
  const profileReportNames = useMemo(() => buildProfileReportNames(state.profiles), [state.profiles]);
  const tabCounts = useMemo(() => buildTabCounts(state, startStepCount), [state]);
  const boardMeta = useMemo(() => buildBoardMeta(activeTab, state, startStepCount), [activeTab, state]);
  const latestRunId = state.runs[0]?.run_id;
  const pendingReviewCount = useMemo(() => reviewQueueCount(state.inbox), [state.inbox]);
  const latestActionCount = state.inbox.filter((card) => isActionableInboxCard(card, latestRunId)).length;
  const hasLatestActionCards = latestActionCount > 0;
  const hasBlockingSummary = hasBlockingOpportunitySummary(state.opportunity_summary);
  const showCommandStrip = activeTab === "inbox" && !hasLatestActionCards;
  const showOpportunitySummary = activeTab === "inbox" && (!hasLatestActionCards || hasBlockingSummary);
  const showValidationSummary = activeTab === "inbox" && !hasLatestActionCards;
  const showBoardStatusStack = showCommandStrip || showOpportunitySummary || showValidationSummary;

  useEffect(() => {
    // Mobile bottom navigation can otherwise carry the previous tab's scroll
    // offset into the next screen, hiding the new tab's main decision surface.
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [activeTab]);

  async function act(cardId: string, action: string, note = "") {
    setBusy(true);
    setNotice(null);
    try {
      if (action === "undo_decision") {
        await undoReviewCardAction(cardId);
      } else {
        await postReviewCardAction(cardId, action, note);
      }
      await refresh();
      const text =
        action === "follow_up"
          ? "Profile diff drafted"
          : action === "undo_decision"
            ? "Review decision undone"
            : "Inbox updated";
      setNotice({ tone: "success", text });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  async function executeDeskAction(actionId: string, body: Record<string, unknown> = {}) {
    if (actionId === "schedule_install_dry_run") {
      body.confirm = true;
    }
    if (actionId === "schedule_remove_dry_run") {
      body.confirm = true;
    }
    if (actionId === "sources_pause_inaccessible" || actionId === "sources_keep_accessible") {
      body.confirm = true;
    }
    let progressTimer: number | undefined;
    if (actionId === "sources_probe_access" || actionId === "monitor_jobs_dry_run") {
      progressTimer = window.setInterval(() => {
        void refresh().catch(() => undefined);
      }, 5000);
    }
    try {
      const result = await runAction(actionId, body);
      if (actionId === "schedule_install_dry_run" || actionId === "schedule_remove_dry_run") {
        await refreshDeskSchedulerStatus().catch(() => undefined);
      }
      if (result.status === "success") {
        await refresh();
        setNotice({ tone: "success", text: result.title });
        return;
      }
      setNotice({ tone: result.status === "needs_human" ? "success" : "error", text: result.title });
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
    } finally {
      if (progressTimer !== undefined) {
        window.clearInterval(progressTimer);
      }
    }
  }

  function openSettings(task: SettingsTask = "sources") {
    setActiveTab("settings");
    setSettingsFocusTarget(task);
  }

  async function runDeskAction(actionId: string, body: Record<string, unknown> = {}) {
    setNotice(null);
    if (actionId === "live_delivery_human") {
      openSettings("notifications");
      setNotice({ tone: "success", text: "Opened notification settings" });
      return;
    }
    if (actionId === "settings_ai") {
      openSettings("ai");
      setNotice({ tone: "success", text: "Opened AI API settings" });
      return;
    }
    const confirmation = deskActionConfirmation(actionId);
    if (confirmation) {
      pendingDeskActionReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setPendingDeskAction(confirmation);
      return;
    }
    await executeDeskAction(actionId, body);
  }

  const cancelPendingDeskAction = useCallback(() => {
    setPendingDeskAction(null);
  }, []);

  const clearSettingsFocusTarget = useCallback(() => {
    setSettingsFocusTarget(null);
  }, []);

  const confirmPendingDeskAction = useCallback(() => {
    setPendingDeskAction((confirmation) => {
      if (confirmation) {
        void executeDeskAction(confirmation.actionId);
      }
      return null;
    });
  }, []);

  return (
    <main className="app-shell" data-testid="tgcs-dashboard">
      <a className="skip-link" href="#active-board">
        Skip to active board
      </a>
      <div className="pixel-grid" aria-hidden="true" />
      <ConsoleHeader
        busy={headerBusy}
        onNewScan={() => void runDeskAction("monitor_jobs_dry_run")}
        onOpenUpdates={() => openSettings("updates")}
        updateAvailableCount={updateAvailableCount}
      />

      {(notice || loadError) && (
        <div className={`notice ${notice?.tone === "error" || loadError ? "error" : "success"}`} role="status">
          {loadError || notice?.text}
        </div>
      )}

      <section className="workbench">
        <NavigationRail tabs={tabShell} activeTab={activeTab} tabCounts={tabCounts} setActiveTab={setActiveTab} />

        <section className="main-board" id="active-board" aria-label={boardMeta.title} tabIndex={-1}>
          <WorkbenchHeader meta={boardMeta} />
          {showBoardStatusStack && (
            <div className="board-status-stack" aria-label="Board status summary">
              {showCommandStrip && <CommandStrip state={state} metrics={metrics} />}
              {showOpportunitySummary && <OpportunitySummaryPanel summary={state.opportunity_summary} latestPriorityCount={latestActionCount} />}
              <ValidationSummaryPanel cards={state.inbox} summary={showValidationSummary ? state.validation_summary : undefined} />
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
                feedbackSummary={state.feedback_summary}
                onGenerateProfileSuggestions={generateFeedbackProfileSuggestions}
                onOpenStart={() => setActiveTab("actions")}
                onOpenProfiles={() => setActiveTab("profiles")}
              />
            )}
            {activeTab === "actions" && (
              <ActionsView
                actions={deskActions}
                activeActions={state.active_actions ?? []}
                results={deskActionResults}
                busyActionId={busyActionId}
                loadError={deskActionsLoadError || deskActionRunError || deskSchedulerError || ""}
                setupStatus={state.setup_status}
                scheduler={deskSchedulerStatus}
                targets={state.delivery_targets}
                reviewCount={pendingReviewCount}
                telegram={{
                  status: deskTelegram.status,
                  busy: deskTelegram.busy,
                  error: deskTelegram.error,
                  saveCredentials: deskTelegram.saveCredentials,
                  sendCode: deskTelegram.sendCode,
                  verifyCode: deskTelegram.verifyCode,
                  refresh: deskTelegram.refreshTelegram,
                  cancelLogin: deskTelegram.cancelLogin,
                }}
                onOpenReview={() => setActiveTab("inbox")}
                onOpenProfiles={() => setActiveTab("profiles")}
                onOpenRuns={() => setActiveTab("runs")}
                onOpenSettings={openSettings}
                onRun={runDeskAction}
              />
            )}
            {activeTab === "profiles" && (
              <ProfilesView
                profiles={state.profiles}
                patches={state.profile_patch_suggestions}
                applyPatch={applyPatch}
                replayPatch={replayPatch}
                revertPatch={revertPatch}
                setAlertMode={setAlertMode}
                setProfileEnabled={setProfileEnabled}
                setProfileRuntimeSettings={setProfileRuntimeSettings}
                deleteProfile={deleteProfile}
                createProfileDraftNote={createProfileDraftNote}
                createProfileMatchingPreferencesDraft={createProfileMatchingPreferencesDraft}
                createProfileFromBrief={createProfileFromBrief}
                profileCreateResult={profileCreateResult}
                busy={busy}
                onGenerateProfileSuggestions={generateFeedbackProfileSuggestions}
                onOpenStart={() => setActiveTab("actions")}
              />
            )}
            {activeTab === "runs" && (
              <RunsView
                runs={state.runs}
                onOpenProfiles={() => setActiveTab("profiles")}
                onOpenReview={() => setActiveTab("inbox")}
                onRunDeskAction={(actionId, body) => void runDeskAction(actionId, body)}
              />
            )}
            {activeTab === "settings" && (
              <>
                <SettingsView
                  sources={{
                    sourceStats: state.source_stats,
                    sourceInsights: state.source_insights,
                    sourceLibrary: deskSources,
                    sourceLibraryError: deskSourcesError,
                    sourceImportResult,
                    profiles: state.profiles,
                    previewSourceImport,
                    importSources,
                    importStarterSources,
                    previewSourceAssistant,
                    applySourceAssistant,
                    openReviewCards: () => setActiveTab("inbox"),
                    setSourceEnabled,
                    removeSource,
                    setSourceTopics,
                  }}
                  notifications={{
                    targets: state.delivery_targets,
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
                    installBotGatewayAutostart: () => setBotGatewayAutostart(true),
                    removeBotGatewayAutostart: () => setBotGatewayAutostart(false),
                    testDeliveryTarget,
                  }}
                  ai={{
                    aiSettingsStatus,
                    aiSettingsError,
                    saveAiApiKey,
                    clearAiApiKey,
                  }}
                  learning={{
                    feedbackSummary: state.feedback_summary,
                    feedbackExport,
                    feedbackProfileSuggestions,
                    exportFeedback,
                    generateFeedbackProfileSuggestions,
                    openProfileDrafts: () => setActiveTab("profiles"),
                    openReviewCards: () => setActiveTab("inbox"),
                    clearFeedback,
                    undoFeedbackDecision,
                    runAgainWithLearning: () => void runDeskAction("monitor_jobs_dry_run"),
                  }}
                  updates={{
                    gitStatus,
                    gitBusy,
                    checkUpdates,
                    pullLatest,
                  }}
                  busy={busy}
                  focusTarget={settingsFocusTarget}
                  onFocusHandled={clearSettingsFocusTarget}
                />
              </>
            )}
          </div>
        </section>
      </section>
      {pendingDeskAction && (
        <DeskActionConfirmDialog
          confirmation={pendingDeskAction}
          returnFocusRef={pendingDeskActionReturnFocus}
          busy={Boolean(busyActionId)}
          onCancel={cancelPendingDeskAction}
          onConfirm={confirmPendingDeskAction}
        />
      )}
    </main>
  );
}

function deskActionConfirmation(actionId: string): DeskActionConfirmation | null {
  if (actionId === "schedule_install_dry_run") {
    return {
      actionId,
      title: "Turn on automatic AI reviews?",
      detail: "Signal Desk will check for new Review cards every 15 minutes in the background. It stays local and sends no live Telegram alerts.",
      confirmLabel: "Turn on auto review",
    };
  }
  if (actionId === "schedule_remove_dry_run") {
    return {
      actionId,
      title: "Turn off automatic AI reviews?",
      detail: "Background checks will stop. Manual AI reviews in Signal Desk will still work.",
      confirmLabel: "Turn off auto review",
    };
  }
  if (actionId === "sources_pause_inaccessible") {
    return {
      actionId,
      title: "Pause unreadable channels?",
      detail: "Signal Desk will disable only saved channels that the latest check could not open. It will not delete them.",
      confirmLabel: "Pause unreadable",
    };
  }
  if (actionId === "sources_keep_accessible") {
    return {
      actionId,
      title: "Keep only active channels?",
      detail: "Signal Desk will disable unreadable and quiet saved channels from the latest check. Quiet channels are readable; they just had no recent messages.",
      confirmLabel: "Keep active only",
    };
  }
  return null;
}

function DeskActionConfirmDialog({
  busy,
  confirmation,
  onCancel,
  onConfirm,
  returnFocusRef,
}: {
  busy: boolean;
  confirmation: DeskActionConfirmation;
  onCancel: () => void;
  onConfirm: () => void;
  returnFocusRef: MutableRefObject<HTMLElement | null>;
}) {
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
      if (!focusable.length) {
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      const restoreFocusTarget = returnFocusRef.current;
      returnFocusRef.current = null;
      window.setTimeout(() => restoreFocusTarget?.focus(), 0);
    };
  }, [onCancel, returnFocusRef]);

  return (
    <div className="desk-confirm-backdrop" onClick={(event) => event.currentTarget === event.target && onCancel()} role="presentation">
      <section
        className="desk-confirm-dialog"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="desk-confirm-title"
        aria-describedby="desk-confirm-detail"
      >
        <div>
          <span className="panel-kicker">Confirm local change</span>
          <h2 id="desk-confirm-title">{confirmation.title}</h2>
          <p id="desk-confirm-detail">{confirmation.detail}</p>
        </div>
        <div className="desk-confirm-actions">
          <button className="journey-button secondary" disabled={busy} onClick={onCancel} ref={cancelButtonRef} type="button">
            Cancel
          </button>
          <button className="journey-button" disabled={busy} onClick={onConfirm} type="button">
            {confirmation.confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
