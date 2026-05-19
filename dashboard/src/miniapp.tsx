import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Archive, Ban, Bookmark, Check, Compass, ExternalLink, FileText, Play, PlusCircle, RefreshCcw, RotateCcw, SlidersHorizontal, Volume2, VolumeX, X } from "lucide-react";

import { loadMiniAppState, postMiniAppReviewCardAction, postMiniAppStarterSources, errorMessage } from "./api/client";
import { artifactHref } from "./domain/display";
import { formatDate, profileDisplayName, sourceRefLabel, titleCaseLabel } from "./domain/format";
import { filterInboxCards, isActionableInboxCard, isReviewQueueCard, sourceRefUrl } from "./domain/inbox";
import type { MiniAppAuth, MiniAppLearningSummary, MiniAppReviewState, MiniAppSourceRecommendation, ReviewCard } from "./domain/types";
import "./miniapp.css";

type TelegramWebApp = {
  initData?: string;
  version?: string;
  ready?: () => void;
  expand?: () => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  HapticFeedback?: {
    notificationOccurred?: (type: "success" | "warning" | "error" | string) => void;
    selectionChanged?: () => void;
    impactOccurred?: (style: "light" | "medium" | "heavy" | "rigid" | "soft" | string) => void;
  };
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

export type MiniAppCue = {
  tone: "positive" | "negative" | "tick";
  haptic: "success" | "warning" | "selection";
};

const MINIAPP_SOUND_STORAGE_KEY = "tgcs.miniapp.sound.enabled";

export function miniappCueForAction(action: string): MiniAppCue {
  const normalized = String(action || "").trim().toLowerCase();
  if (["applied", "saved", "keep", "follow_up", "reopen", "undo_decision", "source_added"].includes(normalized)) {
    return { tone: "positive", haptic: "success" };
  }
  if (["dismissed", "skip", "false_positive", "duplicate"].includes(normalized)) {
    return { tone: "negative", haptic: "warning" };
  }
  return { tone: "tick", haptic: "selection" };
}

export function miniappTriggerHaptic(app: Pick<TelegramWebApp, "HapticFeedback" | "version"> | undefined, cue: MiniAppCue) {
  if (app?.version && !telegramSupportsWebAppVersion(app, "6.1")) {
    return;
  }
  const feedback = app?.HapticFeedback;
  try {
    if (cue.haptic === "selection") {
      feedback?.selectionChanged?.();
      return;
    }
    feedback?.notificationOccurred?.(cue.haptic);
  } catch {
    // Haptics are a progressive enhancement in Telegram clients.
  }
}

function initialMiniAppSoundEnabled() {
  if (typeof window === "undefined") {
    return true;
  }
  try {
    return window.localStorage.getItem(MINIAPP_SOUND_STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
}

function saveMiniAppSoundEnabled(enabled: boolean) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(MINIAPP_SOUND_STORAGE_KEY, String(enabled));
  } catch {
    // Storage may be unavailable inside stricter webviews.
  }
}

let miniappAudioContext: AudioContext | null = null;

function playMiniAppSound(cue: MiniAppCue, enabled: boolean) {
  if (!enabled || typeof window === "undefined") {
    return;
  }
  type MiniAppAudioContextConstructor = new (contextOptions?: AudioContextOptions) => AudioContext;
  const audioWindow = window as Window & {
    AudioContext?: MiniAppAudioContextConstructor;
    webkitAudioContext?: MiniAppAudioContextConstructor;
  };
  const AudioContextConstructor = audioWindow.AudioContext || audioWindow.webkitAudioContext;
  if (!AudioContextConstructor) {
    return;
  }
  try {
    const context = miniappAudioContext || new AudioContextConstructor();
    miniappAudioContext = context;
    if (context.state === "suspended") {
      void context.resume();
    }
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const now = context.currentTime;
    const [startFrequency, endFrequency, duration, peakGain] = soundShape(cue.tone);
    oscillator.type = cue.tone === "negative" ? "triangle" : "sine";
    oscillator.frequency.setValueAtTime(startFrequency, now);
    oscillator.frequency.exponentialRampToValueAtTime(endFrequency, now + duration);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(peakGain, now + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(now);
    oscillator.stop(now + duration + 0.02);
  } catch {
    // Audio cues should never block review actions.
  }
}

function soundShape(tone: MiniAppCue["tone"]): [number, number, number, number] {
  if (tone === "positive") {
    return [660, 940, 0.13, 0.035];
  }
  if (tone === "negative") {
    return [260, 180, 0.16, 0.028];
  }
  return [520, 620, 0.07, 0.018];
}

export function miniappReviewCards(cards: ReviewCard[]) {
  return [...cards].sort((left, right) => {
    const leftHandled = reviewHandled(left) ? 1 : 0;
    const rightHandled = reviewHandled(right) ? 1 : 0;
    if (leftHandled !== rightHandled) {
      return leftHandled - rightHandled;
    }
    return ratingRank(left.rating) - ratingRank(right.rating);
  });
}

export type MiniAppFilter = "review" | "priority" | "saved" | "handled" | "duplicate" | "all";

export function miniappQueueSummary(cards: ReviewCard[]) {
  return {
    total: cards.length,
    review: cards.filter((card) => isReviewQueueCard(card)).length,
    priority: cards.filter((card) => isActionableInboxCard(card)).length,
    saved: filterInboxCards(cards, "saved").length,
    handled: filterInboxCards(cards, "handled").length,
    duplicate: filterInboxCards(cards, "duplicate").length,
  };
}

export function miniappFilterCards(cards: ReviewCard[], filter: MiniAppFilter) {
  const sortedCards = miniappReviewCards(cards);
  if (filter === "review") {
    return sortedCards.filter((card) => isReviewQueueCard(card));
  }
  if (filter === "priority") {
    return sortedCards.filter((card) => isActionableInboxCard(card));
  }
  if (filter === "saved") {
    return filterInboxCards(sortedCards, "saved");
  }
  if (filter === "handled") {
    return filterInboxCards(sortedCards, "handled");
  }
  if (filter === "duplicate") {
    return filterInboxCards(sortedCards, "duplicate");
  }
  return sortedCards;
}

export function miniappFilterOptions(cards: ReviewCard[]) {
  const summary = miniappQueueSummary(cards);
  const options: Array<{ id: MiniAppFilter; label: string; count: number }> = [
    { id: "review", label: "Review", count: summary.review },
    { id: "priority", label: "Priority", count: summary.priority },
    { id: "saved", label: "Saved", count: summary.saved },
    { id: "handled", label: "Handled", count: summary.handled },
    { id: "duplicate", label: "Duplicate", count: summary.duplicate },
    { id: "all", label: "All", count: summary.total },
  ];
  return options.filter((option) => option.id === "review" || option.id === "priority" || option.id === "all" || option.count > 0);
}

export function miniappFilterAriaLabel(option: { label: string; count: number }) {
  return `Show ${option.label} cards, ${option.count} ${option.count === 1 ? "result" : "results"}`;
}

export function miniappStatusLine(auth?: MiniAppAuth) {
  if (auth?.source === "telegram" && auth.user_id) {
    return `Telegram user ${auth.user_id}`;
  }
  if (auth?.source === "loopback_preview") {
    return "Local preview";
  }
  return "Telegram Mini App";
}

export type MiniAppActionStatus = {
  title: string;
  detail: string;
};

export function miniappActionStatus(action: string, learning?: MiniAppLearningSummary): MiniAppActionStatus {
  const normalized = String(action || "").trim().toLowerCase();
  if (normalized === "follow_up") {
    return { title: "Note saved", detail: miniappLearningReceiptDetail(learning) };
  }
  if (["keep", "skip", "false_positive"].includes(normalized)) {
    return { title: "Feedback saved", detail: miniappLearningReceiptDetail(learning) };
  }
  if (normalized === "applied" || normalized === "contacted") {
    return { title: "Applied saved", detail: "Moved out of Review. Open All if you need to undo." };
  }
  if (normalized === "saved") {
    return { title: "Saved for later", detail: "Moved to Saved. Open Saved or All to revisit." };
  }
  if (normalized === "dismissed") {
    return { title: "Marked not a fit", detail: "Moved out of Review. Open All if you need to undo." };
  }
  if (normalized === "duplicate") {
    return { title: "Marked duplicate", detail: "Moved out of Review. Open All if you need to undo." };
  }
  if (normalized === "reopen") {
    return { title: "Reopened", detail: "Card is back in Review." };
  }
  if (normalized === "undo_decision") {
    return { title: "Decision cleared", detail: "Card is back in Review." };
  }
  return { title: "Review updated", detail: "Action saved locally." };
}

export function miniappStateDetail(error: string, actionStatus: MiniAppActionStatus | null | undefined, generatedAt?: string) {
  if (error) {
    return error;
  }
  if (actionStatus?.detail) {
    return actionStatus.detail;
  }
  if (generatedAt) {
    return `Updated ${formatDate(generatedAt)}`;
  }
  return "Reading local state";
}

function miniappLearningReceiptDetail(learning?: MiniAppLearningSummary) {
  const pendingDrafts = learning?.pending_profile_diff_count ?? 0;
  if (pendingDrafts > 0) {
    return "Profile draft is ready in Desk; apply it before the next run.";
  }
  const decisions = learning?.current_decision_count ?? 0;
  if (decisions > 0) {
    return `${decisions} learning ${decisions === 1 ? "choice is" : "choices are"} ready for a profile draft.`;
  }
  return "Profile tuning updated.";
}

export function MiniAppCard({
  busy,
  card,
  allowReportLinks = true,
  initialTuningOpen = false,
  onAct,
  onCue = () => undefined,
}: {
  busy: boolean;
  card: ReviewCard;
  allowReportLinks?: boolean;
  initialTuningOpen?: boolean;
  onAct: (cardId: string, action: string, note?: string) => void;
  onCue?: (action: string) => void;
}) {
  const [tuningOpen, setTuningOpen] = useState(initialTuningOpen);
  const [note, setNote] = useState("");
  const sourceLinks = miniappSourceLinks(card);
  const hiddenSourceCount = miniappHiddenSourceCount(card);
  const sourceExcerpt = miniappDisplaySourceExcerpt(card.item.source_excerpt);
  const sourceExcerptHint = miniappSourceExcerptHint(card, sourceLinks.length > 0);
  const reportUrl = allowReportLinks && card.report_path ? artifactHref(card.report_path) : "";
  const openOpportunity = isOpenOpportunity(card);
  const reviewDecision = hasReviewDecision(card);
  const cardTitle = card.title || "card";
  return (
    <article className={`miniapp-card rating-${ratingClass(card.rating)}`} data-handled={reviewHandled(card) ? "true" : "false"}>
      <div className="miniapp-card-spine" aria-hidden="true">
        <span>{card.rating || "card"}</span>
      </div>
      <div className="miniapp-card-main">
        <div className="miniapp-card-head">
          <div>
            <span className="miniapp-eyebrow">{profileDisplayName(card.profile_id)}</span>
            <h2>{card.title}</h2>
          </div>
          <span className={`miniapp-rating ${ratingClass(card.rating)}`}>{card.rating || "card"}</span>
        </div>
        <p className="miniapp-reason">{card.item.why || "Decision reason unavailable."}</p>
        {sourceExcerpt && (
          <section className="miniapp-source-excerpt" aria-label="Source excerpt">
            <strong>Source excerpt</strong>
            <p>{sourceExcerpt}</p>
            <small>
              <span>Jump clue:</span> {sourceExcerptHint}
            </small>
          </section>
        )}
        <div className="miniapp-proof-strip" aria-label="Card signals">
          {miniappContextItems(card).map((item) => (
            <span className="miniapp-context-chip" key={item.key} title={item.title}>
              <strong>{item.label}</strong>
              <span>{item.value}</span>
            </span>
          ))}
        </div>
        <div className="miniapp-meta" aria-label="Card status and time">
          <span className={`miniapp-status-badge status-${opportunityStatusTone(card.opportunity_status)}`}>
            {opportunityStatusLabel(card.opportunity_status)}
          </span>
          <span>{formatDate(card.updated_at)}</span>
        </div>
        {(sourceLinks.length > 0 || reportUrl) && (
          <div className="miniapp-links" aria-label="Card links">
            {sourceLinks.map((source) => (
              <a aria-label={`Open ${source.label} in Telegram`} href={source.url} key={source.key} rel="noreferrer" target="_blank">
                <ExternalLink size={14} />
                <span>{source.actionLabel}</span>
                <small>{source.label}</small>
              </a>
            ))}
            {hiddenSourceCount > 0 && (
              <span className="miniapp-link-more" title={`${hiddenSourceCount} additional Telegram source${hiddenSourceCount === 1 ? "" : "s"}`}>
                +{hiddenSourceCount} source{hiddenSourceCount === 1 ? "" : "s"}
              </span>
            )}
            {reportUrl && (
              <a aria-label={`Open scan details for ${card.title}`} href={reportUrl} rel="noreferrer" target="_blank">
                <FileText size={14} />
                <span>Scan details</span>
              </a>
            )}
          </div>
        )}
      </div>
      <div className="miniapp-actions" aria-label="Review actions">
        {openOpportunity ? (
          <>
            <button aria-label={`Mark ${cardTitle} as applied`} className="miniapp-action" data-review-action="applied" data-sound-cue={miniappCueForAction("applied").tone} data-tone="positive" disabled={busy} onClick={() => onAct(card.card_id, "applied")} type="button">
              <Check size={16} />
              <span>Applied</span>
            </button>
            <button aria-label={`Save ${cardTitle} for later`} className="miniapp-action" data-review-action="saved" data-sound-cue={miniappCueForAction("saved").tone} data-tone="supportive" disabled={busy} onClick={() => onAct(card.card_id, "saved")} type="button">
              <Bookmark size={16} />
              <span>Save</span>
            </button>
            <button aria-label={`Mark ${cardTitle} as not a fit`} className="miniapp-action" data-review-action="dismissed" data-sound-cue={miniappCueForAction("dismissed").tone} data-tone="negative" disabled={busy} onClick={() => onAct(card.card_id, "dismissed")} type="button">
              <X size={16} />
              <span>Not a fit</span>
            </button>
          </>
        ) : (
          <button aria-label={`Reopen ${cardTitle} for review`} className="miniapp-action" data-review-action="reopen" data-sound-cue={miniappCueForAction("reopen").tone} data-tone="supportive" disabled={busy} onClick={() => onAct(card.card_id, "reopen")} type="button">
            <Play size={16} />
            <span>Reopen</span>
          </button>
        )}
        {reviewDecision && (
          <button aria-label={`Clear decision for ${cardTitle}`} className="miniapp-action" data-review-action="undo_decision" data-sound-cue={miniappCueForAction("undo_decision").tone} data-tone="caution" disabled={busy} onClick={() => onAct(card.card_id, "undo_decision")} type="button">
            <RotateCcw size={16} />
            <span>Undo</span>
          </button>
        )}
        <button aria-expanded={tuningOpen} aria-label={`${tuningOpen ? "Close" : "Open"} feedback for ${cardTitle}`} className="miniapp-action" data-expanded={tuningOpen ? "true" : "false"} data-review-action="feedback" data-sound-cue={miniappCueForAction("feedback").tone} data-tone="supportive" disabled={busy} onClick={() => {
          setTuningOpen((value) => !value);
          onCue("feedback");
        }} type="button">
          <SlidersHorizontal size={16} />
          <span>Feedback</span>
        </button>
      </div>
      {tuningOpen && (
        <div className="miniapp-note">
          <div className="miniapp-tuning-grid" aria-label="Profile tuning tags">
            <button aria-label={`Prefer matches similar to ${cardTitle}`} className="miniapp-action" data-review-action="keep" data-sound-cue={miniappCueForAction("keep").tone} data-tone="positive" disabled={busy} onClick={() => onAct(card.card_id, "keep")} type="button">
              <Check size={16} />
              <span>Prefer similar</span>
            </button>
            <button aria-label={`Deprioritize matches like ${cardTitle}`} className="miniapp-action" data-review-action="skip" data-sound-cue={miniappCueForAction("skip").tone} data-tone="caution" disabled={busy} onClick={() => onAct(card.card_id, "skip")} type="button">
              <X size={16} />
              <span>Deprioritize</span>
            </button>
            <button aria-label={`Mark ${cardTitle} as a wrong match`} className="miniapp-action" data-review-action="false_positive" data-sound-cue={miniappCueForAction("false_positive").tone} data-tone="negative" disabled={busy} onClick={() => onAct(card.card_id, "false_positive")} type="button">
              <Ban size={16} />
              <span>Wrong match</span>
            </button>
            <button aria-label={`Mark ${cardTitle} as duplicate`} className="miniapp-action" data-review-action="duplicate" data-sound-cue={miniappCueForAction("duplicate").tone} data-tone="negative" disabled={busy} onClick={() => onAct(card.card_id, "duplicate")} type="button">
              <Archive size={16} />
              <span>Duplicate</span>
            </button>
          </div>
          <textarea
            aria-label="Tuning note"
            disabled={busy}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Short tuning note"
            value={note}
          />
          <div className="miniapp-note-actions">
            <button
              aria-label={`Save feedback note for ${cardTitle}`}
              className="miniapp-action"
              data-sound-cue={miniappCueForAction("follow_up").tone}
              data-tone="positive"
              disabled={busy || !note.trim()}
              onClick={() => onAct(card.card_id, "follow_up", note.trim())}
              type="button"
            >
              <FileText size={16} />
              <span>Save note</span>
            </button>
            <button aria-label="Close feedback" className="miniapp-icon-button miniapp-note-close" data-sound-cue={miniappCueForAction("close").tone} disabled={busy} onClick={() => {
              setTuningOpen(false);
              onCue("close");
            }} title="Close feedback" type="button">
              <X size={16} />
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

export function miniappDisplaySourceExcerpt(value?: string) {
  return String(value || "")
    .trim()
    .replace(/^(?:(?:original|source)\s+(?:post|text|message)|post)\s*[:：-]\s*/i, "")
    .replace(/\s*\[link\]\s*/gi, " ")
    .replace(/\s+([.,!?;:])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function miniappSourceExcerptHint(card: ReviewCard, hasSourceJump: boolean) {
  if (!hasSourceJump) {
    return "Use this excerpt as source evidence; no Telegram jump is available.";
  }
  const fields = (card.item.decision_state?.material_change_fields ?? []).slice(0, 2).map(titleCaseLabel);
  if (fields.length) {
    return `Worth opening to verify ${joinReadable(fields)} before acting.`;
  }
  if (card.rating?.toLowerCase() === "high") {
    return "Worth opening to verify original details before acting.";
  }
  return "Open original if the excerpt is not enough to decide.";
}

function joinReadable(items: string[]) {
  if (items.length <= 1) {
    return items[0] || "original details";
  }
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

export function MiniAppSourceDiscovery({
  busy,
  recommendations,
  onAdd,
}: {
  busy: boolean;
  recommendations: MiniAppSourceRecommendation[];
  onAdd: (topic: string) => void;
}) {
  const visibleRecommendations = recommendations.slice(0, 6);
  if (!visibleRecommendations.length) {
    return null;
  }
  const pendingCount = visibleRecommendations.filter((source) => !source.installed).length;
  const installedCount = visibleRecommendations.length - pendingCount;
  const ready = pendingCount === 0;
  const topic = visibleRecommendations[0]?.topic || "jobs";
  const actionLabel = ready ? "Refresh channels" : "Add recommended channels";
  const actionAriaLabel = ready
    ? `Refresh ${visibleRecommendations.length} ready source${visibleRecommendations.length === 1 ? "" : "s"} for the next run`
    : `Add ${pendingCount} recommended source${pendingCount === 1 ? "" : "s"} for the next run`;
  const actionCue = ready ? "refresh" : "source_added";
  const countLabel = ready ? `${installedCount} ready` : `${pendingCount} to add`;
  const outcomeDetail = ready ? "Ready for rerun." : "Cards appear after rerun.";
  return (
    <section className="miniapp-source-discovery" aria-label="Source discovery" data-ready={ready ? "true" : "false"}>
      <div className="miniapp-source-discovery-head">
        <div>
          <span className="miniapp-eyebrow">Source discovery</span>
          <strong>Starter sources</strong>
          <div className="miniapp-source-badges" aria-label="Source discovery status">
            <span>{countLabel}</span>
            <span>Next run</span>
            <span>Metadata only</span>
          </div>
          <small>{outcomeDetail}</small>
        </div>
        <button aria-label={actionAriaLabel} className="miniapp-action miniapp-source-action" data-sound-cue={miniappCueForAction(actionCue).tone} data-tone="supportive" disabled={busy} onClick={() => onAdd(topic)} type="button">
          {pendingCount ? <PlusCircle size={16} /> : <RefreshCcw size={16} />}
          <span>{actionLabel}</span>
        </button>
      </div>
      <div className="miniapp-source-grid-label">
        <span>Channels</span>
        <small>Swipe {visibleRecommendations.length}</small>
      </div>
      <div className="miniapp-source-grid">
        {visibleRecommendations.map((source) => (
          <article aria-label={`${source.installed ? "Added" : "Recommended"} source ${source.label}`} className="miniapp-source-card" data-installed={source.installed ? "true" : "false"} key={source.source_id} title={source.reason || source.label}>
            <div>
              <Compass size={14} />
              <strong>{source.label}</strong>
            </div>
            <span>@{source.channel}</span>
            <div className="miniapp-source-tags" aria-label="Source traits">
              <small>{titleCaseLabel(source.topic || "public")}</small>
              <small>{miniappSourceNoiseTag(source.reason)}</small>
            </div>
            <em>{source.installed ? "Added" : "Recommended"}</em>
          </article>
        ))}
      </div>
    </section>
  );
}

function miniappSourceNoiseTag(reason?: string) {
  const normalized = String(reason || "").toLowerCase();
  if (normalized.includes("high expected noise")) {
    return "Noise high";
  }
  if (normalized.includes("low expected noise")) {
    return "Noise low";
  }
  if (normalized.includes("medium expected noise")) {
    return "Noise med";
  }
  return "Public";
}

export function MiniAppLearningLoop({ learning }: { learning?: MiniAppLearningSummary }) {
  const currentDecisions = learning?.current_decision_count ?? 0;
  const pendingDrafts = learning?.pending_profile_diff_count ?? 0;
  const stage = miniappLearningLoopStage(learning);
  const nextAction = pendingDrafts > 0 ? learning?.next_action : learning?.calibration_next_action || learning?.next_action;
  const active = currentDecisions > 0 || pendingDrafts > 0 || (learning?.applied_profile_diff_count ?? 0) > 0 || Boolean(nextAction?.label);
  const appliedDrafts = learning?.applied_profile_diff_count ?? 0;
  const nextActionDetail = miniappLearningNextDetail(nextAction?.detail, pendingDrafts);
  return (
    <section className="miniapp-learning-loop" aria-label="Learning loop" data-active={active ? "true" : "false"}>
      <div className="miniapp-learning-copy">
        <span className="miniapp-eyebrow">Learning loop</span>
        <strong>{stage.title}</strong>
        <div className="miniapp-learning-badges" aria-label="Learning loop status">
          <span>{currentDecisions} choice{currentDecisions === 1 ? "" : "s"}</span>
          <span>{pendingDrafts > 0 ? "Draft ready" : `${appliedDrafts} applied`}</span>
          <span>{learning?.changed_since_last_export ? "New evidence" : "Current"}</span>
        </div>
        <small>{stage.detail}</small>
      </div>
      {nextAction?.label && (
        <div className="miniapp-learning-next">
          <Check size={15} />
          <div>
            <strong>{miniappLearningNextLabel(nextAction.label)}</strong>
            {nextActionDetail && <small>{nextActionDetail}</small>}
          </div>
        </div>
      )}
    </section>
  );
}

export function MiniAppSoundToggle({ enabled, busy = false, onToggle }: { enabled: boolean; busy?: boolean; onToggle: () => void }) {
  const Icon = enabled ? Volume2 : VolumeX;
  const label = enabled ? "Mute sound cues" : "Enable sound cues";
  return (
    <button
      aria-label={label}
      aria-pressed={enabled}
      className="miniapp-icon-button miniapp-sound-toggle"
      data-sound-cue={miniappCueForAction("sound_toggle").tone}
      disabled={busy}
      onClick={onToggle}
      title={label}
      type="button"
    >
      <Icon size={16} />
    </button>
  );
}

function miniappLearningLoopStage(learning?: MiniAppLearningSummary) {
  const currentDecisions = learning?.current_decision_count ?? 0;
  const pendingDrafts = learning?.pending_profile_diff_count ?? 0;
  if (pendingDrafts > 0) {
    return {
      title: "Profile draft",
      detail: "Apply in Desk, then rerun.",
    };
  }
  if (currentDecisions > 0) {
    return {
      title: "Learning evidence",
      detail: "Turn Review choices into profile rules before rerun.",
    };
  }
  if ((learning?.applied_profile_diff_count ?? 0) > 0 || learning?.calibration_next_action?.label) {
    return {
      title: "Tuning applied",
      detail: "Run again to collect calibration evidence.",
    };
  }
  return {
    title: "Teach matches",
    detail: "Use Feedback to improve future matching.",
  };
}

function miniappLearningNextLabel(label?: string) {
  const normalized = String(label || "").trim().toLowerCase();
  if (normalized.includes("profile") && normalized.includes("draft")) {
    return "Review drafts";
  }
  if (normalized.includes("run")) {
    return "Run again";
  }
  return String(label || "Next step").trim() || "Next step";
}

function miniappLearningNextDetail(detail: string | undefined, pendingDrafts: number) {
  if (pendingDrafts > 0) {
    return "";
  }
  const compact = String(detail || "").trim();
  return compact || "Use the next local run to check calibration.";
}

function MiniApp() {
  const [state, setState] = useState<MiniAppReviewState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<MiniAppFilter>("review");
  const [lastActionStatus, setLastActionStatus] = useState<MiniAppActionStatus | null>(null);
  const [lastCueTone, setLastCueTone] = useState<MiniAppCue["tone"]>("tick");
  const [soundEnabled, setSoundEnabled] = useState(initialMiniAppSoundEnabled);
  const allCards = state?.cards ?? [];
  const summary = useMemo(() => miniappQueueSummary(allCards), [allCards]);
  const filterOptions = useMemo(() => miniappFilterOptions(allCards), [allCards]);
  const cards = useMemo(() => miniappFilterCards(allCards, filter), [allCards, filter]);
  const allowReportLinks = state?.auth?.source === "loopback_preview";
  const stateTitle = error ? "Review unavailable" : busy ? "Syncing review" : lastActionStatus?.title || "Review ready";
  const stateDetail = miniappStateDetail(error, lastActionStatus, state?.generated_at);

  useEffect(() => {
    const app = window.Telegram?.WebApp;
    if (telegramSupportsWebAppVersion(app, "6.1")) {
      app?.setHeaderColor?.("#101916");
      app?.setBackgroundColor?.("#101916");
    }
    app?.expand?.();
    app?.ready?.();
    void refresh();
  }, []);

  function cue(action: string) {
    const nextCue = miniappCueForAction(action);
    miniappTriggerHaptic(window.Telegram?.WebApp, nextCue);
    playMiniAppSound(nextCue, soundEnabled);
    setLastCueTone(nextCue.tone);
  }

  async function refresh(options: { interactive?: boolean } = {}) {
    if (options.interactive) {
      cue("refresh");
    }
    setBusy(true);
    setError("");
    setLastActionStatus(null);
    try {
      setState(await loadMiniAppState());
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setBusy(false);
    }
  }

  async function act(cardId: string, action: string, note = "") {
    setBusy(true);
    setError("");
    setLastActionStatus(null);
    try {
      await postMiniAppReviewCardAction(cardId, action, note);
      const nextState = await loadMiniAppState();
      setState(nextState);
      setLastActionStatus(miniappActionStatus(action, nextState.learning_summary));
      cue(action);
    } catch (actionError) {
      setError(errorMessage(actionError));
    } finally {
      setBusy(false);
    }
  }

  async function addStarterSources(topic: string) {
    setBusy(true);
    setError("");
    setLastActionStatus(null);
    try {
      const result = await postMiniAppStarterSources(topic || "jobs");
      setState(await loadMiniAppState());
      setLastActionStatus({
        title: result.title || "Sources added",
        detail: result.detail || "Recommended channels are ready for the next local run.",
      });
      cue("source_added");
    } catch (sourceError) {
      setError(errorMessage(sourceError));
    } finally {
      setBusy(false);
    }
  }

  function toggleSound() {
    const nextEnabled = !soundEnabled;
    setSoundEnabled(nextEnabled);
    saveMiniAppSoundEnabled(nextEnabled);
    miniappTriggerHaptic(window.Telegram?.WebApp, miniappCueForAction("sound_toggle"));
    playMiniAppSound(miniappCueForAction("sound_toggle"), nextEnabled);
  }

  return (
    <main className="miniapp-shell">
      <header className="miniapp-topbar">
        <div className="miniapp-brand">
          <img alt="" src="/tgcs-signal-icon.png" />
          <div>
            <strong>T-Sense</strong>
            <small>{miniappStatusLine(state?.auth)}</small>
          </div>
        </div>
        <div className="miniapp-top-actions">
          <MiniAppSoundToggle enabled={soundEnabled} busy={busy} onToggle={toggleSound} />
          <span className="miniapp-pill">{summary.review} to review</span>
        </div>
      </header>
      <section className="miniapp-state" data-flash={lastActionStatus ? lastCueTone : "idle"} role={error ? "alert" : "status"}>
        <div>
          <strong>{stateTitle}</strong>
          <small>{stateDetail}</small>
        </div>
        <button aria-label="Refresh review" className="miniapp-icon-button" data-sound-cue={miniappCueForAction("refresh").tone} disabled={busy} onClick={() => void refresh({ interactive: true })} title="Refresh review" type="button">
          <RefreshCcw size={16} />
        </button>
      </section>
      <section className="miniapp-summary" aria-label="Review queue summary">
        <span>
          <strong>{summary.priority}</strong>
          <small>Priority</small>
        </span>
        <span>
          <strong>{summary.review}</strong>
          <small>Review</small>
        </span>
        <span>
          <strong>{summary.saved}</strong>
          <small>Saved</small>
        </span>
        <span>
          <strong>{summary.total}</strong>
          <small>Total</small>
        </span>
      </section>
      <nav className="miniapp-filter-strip" aria-label="Review card filters">
        {filterOptions.map((option) => (
          <button
            aria-label={miniappFilterAriaLabel(option)}
            aria-pressed={filter === option.id}
            className={filter === option.id ? "active" : ""}
            data-sound-cue={miniappCueForAction("filter").tone}
            disabled={busy}
            key={option.id}
            onClick={() => {
              setFilter(option.id);
              cue("filter");
            }}
            type="button"
          >
            <span>{option.label}</span>
            <strong>{option.count}</strong>
          </button>
        ))}
      </nav>
      <MiniAppLearningLoop learning={state?.learning_summary} />
      {cards.length ? (
        <section className="miniapp-list" aria-label="Review cards">
          {cards.map((card) => (
            <MiniAppCard allowReportLinks={allowReportLinks} busy={busy} card={card} key={card.card_id} onAct={act} onCue={cue} />
          ))}
        </section>
      ) : (
        <section className="miniapp-empty">
          <strong>No {filter === "all" ? "review" : filter} cards</strong>
          <small>{busy ? "Reading local state" : emptyHint(state)}</small>
        </section>
      )}
      <MiniAppSourceDiscovery
        busy={busy}
        recommendations={state?.source_recommendations ?? []}
        onAdd={(topic) => void addStarterSources(topic)}
      />
    </main>
  );
}

type ContextItem = {
  key: string;
  label: string;
  value: string;
  title: string;
};

export function miniappContextItems(card: ReviewCard): ContextItem[] {
  return [noveltyContextItem(card), changeContextItem(card), alertContextItem(card)].filter(Boolean).slice(0, 3) as ContextItem[];
}

function noveltyContextItem(card: ReviewCard): ContextItem {
  const decisionState = card.item.decision_state ?? {};
  const status = String(decisionState.status || card.decision_status || "").toLowerCase();
  const seenCount = Number(decisionState.seen_count || 0);
  if (status === "new") {
    return { key: "new", label: "New", value: "First time", title: "First time this card appeared in the local review history" };
  }
  if (status === "changed") {
    return { key: "changed", label: "Updated", value: "Since last scan", title: "This card changed since an earlier review" };
  }
  if (seenCount > 1) {
    return { key: "seen-count", label: "Seen", value: `${seenCount} times`, title: "Repeated card from local review history" };
  }
  return { key: "status", label: "Status", value: titleCaseLabel(status || card.decision_status || "pending"), title: "Current card decision state" };
}

function changeContextItem(card: ReviewCard): ContextItem | null {
  const fields = (card.item.decision_state?.material_change_fields ?? []).slice(0, 2);
  if (!fields.length) {
    return null;
  }
  const [first = "", ...rest] = fields;
  return {
    key: "changed-fields",
    label: "Changed",
    value: rest.length ? `${titleCaseLabel(first)} +${rest.length}` : titleCaseLabel(first),
    title: "Important fields that changed since this card was last seen",
  };
}

function alertContextItem(card: ReviewCard): ContextItem | null {
  const summary = card.alert_summary;
  if (!summary?.alert_count) {
    return null;
  }
  return { key: "alert", label: "Alert", value: alertProofLabel(card), title: alertProofTitle(card) };
}

export function miniappSourceLinks(card: ReviewCard, limit = 3) {
  const seenUrls = new Set<string>();
  return card.source_refs.flatMap((ref, index) => {
    const url = sourceRefUrl(ref);
    if (!url || seenUrls.has(url)) {
      return [];
    }
    seenUrls.add(url);
    return [{ key: `${url}-${index}`, actionLabel: "Open in Telegram", label: sourceRefLabel(ref), url }];
  }).slice(0, limit);
}

export function telegramSupportsWebAppVersion(app: { version?: string } | undefined, minimum: string) {
  const actualParts = versionParts(app?.version);
  const minimumParts = versionParts(minimum);
  if (!actualParts || !minimumParts) {
    return false;
  }
  const [actualMajor, actualMinor] = actualParts;
  const [minimumMajor, minimumMinor] = minimumParts;
  return actualMajor > minimumMajor || (actualMajor === minimumMajor && actualMinor >= minimumMinor);
}

function versionParts(value: string | undefined): [number, number] | null {
  const match = String(value || "").match(/^(\d+)(?:\.(\d+))?/);
  if (!match) {
    return null;
  }
  return [Number(match[1]), Number(match[2] || 0)];
}

function miniappHiddenSourceCount(card: ReviewCard, limit = 3) {
  const seenUrls = new Set<string>();
  for (const ref of card.source_refs) {
    const url = sourceRefUrl(ref);
    if (url) {
      seenUrls.add(url);
    }
  }
  return Math.max(0, seenUrls.size - limit);
}

function alertProofLabel(card: ReviewCard) {
  const summary = card.alert_summary;
  if (!summary?.alert_count) {
    return "Not sent";
  }
  const deliveryStatus = String(summary.latest_delivery_status || summary.latest_status || "").toLowerCase();
  if (summary.latest_delivery_ok && deliveryStatus === "sent") {
    return "Sent";
  }
  if (summary.latest_delivery_ok && deliveryStatus === "dry_run") {
    return "Checked";
  }
  if (summary.latest_delivery_ok) {
    return titleCaseLabel(deliveryStatus || "Delivered");
  }
  return titleCaseLabel(deliveryStatus || "Failed");
}

function alertProofTitle(card: ReviewCard) {
  const summary = card.alert_summary;
  if (!summary?.alert_count) {
    return "No alert event has been recorded for this card";
  }
  const mode = deliveryModeSuffix(summary.latest_delivery_mode);
  const when = summary.latest_alerted_at ? ` at ${formatDate(summary.latest_alerted_at)}` : "";
  return `${summary.alert_count} Telegram notification${summary.alert_count === 1 ? "" : "s"}${mode}${when}`;
}

function deliveryModeSuffix(mode: unknown) {
  const normalized = String(mode || "").trim().toLowerCase().replace(/_/g, "-");
  if (!normalized || normalized === "live") {
    return "";
  }
  if (normalized === "dry-run") {
    return " (checked without sending)";
  }
  if (normalized === "off") {
    return " (notifications off)";
  }
  return ` (${titleCaseLabel(normalized)})`;
}

function reviewHandled(card: ReviewCard) {
  return String(card.status || "pending").toLowerCase() !== "pending" || String(card.opportunity_status || "open").toLowerCase() !== "open";
}

function isOpenOpportunity(card: ReviewCard) {
  return String(card.opportunity_status || "open").toLowerCase() === "open";
}

function hasReviewDecision(card: ReviewCard) {
  return String(card.status || "pending").toLowerCase() !== "pending";
}

function opportunityStatusLabel(status: string) {
  const normalized = String(status || "open").toLowerCase();
  const labels: Record<string, string> = {
    applied: "Applied",
    contacted: "Applied",
    dismissed: "Not a fit",
    duplicate: "Duplicate",
    open: "Open",
    saved: "Saved",
  };
  return labels[normalized] || titleCaseLabel(normalized);
}

function opportunityStatusTone(status: string) {
  const normalized = String(status || "open").toLowerCase();
  if (["applied", "contacted"].includes(normalized)) {
    return "done";
  }
  if (normalized === "duplicate") {
    return "duplicate";
  }
  if (normalized === "dismissed") {
    return "dismissed";
  }
  if (normalized === "saved") {
    return "saved";
  }
  return "open";
}

function emptyHint(state: MiniAppReviewState | null) {
  const hasUserGoal = state?.setup_status?.has_user_goal ?? state?.setup_status?.has_profiles;
  if (!hasUserGoal) {
    return "Create a profile in Signal Desk first.";
  }
  if (!state?.setup_status?.has_runs) {
    return "Run a local AI review from Signal Desk.";
  }
  return "Nothing matches this filter.";
}

function ratingRank(value: string) {
  const rating = String(value || "").toLowerCase();
  if (rating === "high") return 0;
  if (rating === "medium") return 1;
  if (rating === "low") return 2;
  return 3;
}

function ratingClass(value: string) {
  const rating = String(value || "").toLowerCase();
  return ["high", "medium", "low"].includes(rating) ? rating : "unknown";
}

if (typeof document !== "undefined") {
  const root = document.getElementById("root");
  if (root) {
    createRoot(root).render(
      <StrictMode>
        <MiniApp />
      </StrictMode>,
    );
  }
}
