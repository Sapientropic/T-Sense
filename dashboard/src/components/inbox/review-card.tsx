import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { Archive, Ban, Bookmark, Check, ExternalLink, Eye, FileDiff, Play, RotateCcw, X } from "lucide-react";

import { artifactFormatFromPath, artifactHref, reportProfileName, toneClass } from "../../domain/display";
import { formatDate, profileDisplayName, sourceRefLabel, titleCaseLabel } from "../../domain/format";
import { sourceRefUrl, telegramMessageUrl } from "../../domain/inbox";
import type { ReviewCard, SourceRef } from "../../domain/types";

export function ReviewCardArticle({
  card,
  profileReportNames,
  act,
  busy,
}: {
  card: ReviewCard;
  profileReportNames: Record<string, string>;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
}) {
  const [showFollowUp, setShowFollowUp] = useState(false);
  const [sourcePreview, setSourcePreview] = useState<SourcePreviewSelection | null>(null);
  const sourcePreviewId = `source-preview-${card.card_id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  return (
    <article className={`review-card rating-${toneClass(card.rating)}`} data-actions-expanded={showFollowUp ? "true" : "false"}>
      <div className="card-spine" aria-hidden="true">
        <span>{card.rating}</span>
      </div>
      <div className="card-main">
        <div className="card-title-row">
          <h3>{card.title}</h3>
          <span className={`rating ${toneClass(card.rating)}`}>{card.rating}</span>
        </div>
        <MobileActionStrip
          act={act}
          busy={busy}
          card={card}
          setShowFollowUp={setShowFollowUp}
          showFollowUp={showFollowUp}
        />
        <p className="reason">{card.item.why || "Decision reason unavailable."}</p>
        <CardContextStrip card={card} />
        <div className="meta-row">
          <span>{reportProfileName(card.profile_id, profileReportNames)}</span>
          <span className={`opportunity-badge status-${opportunityStatusTone(card.opportunity_status)}`}>
            {opportunityStatusLabel(card.opportunity_status)}
          </span>
          <span>{formatDate(card.updated_at)}</span>
        </div>
        <CardSourceRow
          activePreviewKey={sourcePreview?.key ?? ""}
          card={card}
          profileReportNames={profileReportNames}
          previewId={sourcePreviewId}
          onPreviewSource={(nextPreview) =>
            setSourcePreview((currentPreview) => (currentPreview?.key === nextPreview.key ? null : nextPreview))
          }
        />
        {sourcePreview && (
          <SourcePreviewPanel
            card={card}
            id={sourcePreviewId}
            preview={sourcePreview}
            onClose={() => setSourcePreview(null)}
          />
        )}
      </div>
      <CardActions card={card} act={act} busy={busy} setShowFollowUp={setShowFollowUp} showFollowUp={showFollowUp} />
    </article>
  );
}

type SourcePreviewSelection = {
  key: string;
  ref: SourceRef;
  index: number;
};

type SourcePreviewContent =
  | { status: "loading" }
  | { status: "ready"; html: string }
  | { status: "missing"; detail: string }
  | { status: "error"; detail: string };

function CardContextStrip({ card }: { card: ReviewCard }) {
  const items = cardContextItems(card);
  if (!items.length) {
    return null;
  }
  return (
    <div className="card-context-strip" aria-label="Card context">
      {items.map((item) => (
        <span className="card-context-chip" key={item.key} title={item.title}>
          <strong>{item.label}</strong>
          <span>{item.value}</span>
        </span>
      ))}
    </div>
  );
}

function cardContextItems(card: ReviewCard): ContextItem[] {
  return [noveltyContextItem(card), changeContextItem(card), alertContextItem(card)].filter(Boolean).slice(0, 3) as ContextItem[];
}

function noveltyContextItem(card: ReviewCard): ContextItem | null {
  const decisionState = card.item.decision_state ?? {};
  const status = String(decisionState.status || card.decision_status || "").toLowerCase();
  const seenCount = Number(decisionState.seen_count || 0);
  if (status === "new") {
    return {
      label: "New",
      value: "First time",
      title: "First time this card appeared in the local review history",
      key: "novelty-new",
    };
  }
  if (status === "changed") {
    return {
      label: "Updated",
      value: "Since last scan",
      title: "This card changed since an earlier review",
      key: "novelty-changed",
    };
  }
  if (seenCount > 1) {
    return {
      label: "Seen before",
      value: `${seenCount} times`,
      title: "Repeated card from the local review history",
      key: "novelty-seen-count",
    };
  }
  if (status === "seen" || status === "recurring") {
    return {
      label: "Seen before",
      value: "Repeated",
      title: "Repeated card from the local review history",
      key: "novelty-seen",
    };
  }
  return null;
}

function changeContextItem(card: ReviewCard): ContextItem | null {
  const decisionState = card.item.decision_state ?? {};
  const fields = (decisionState.material_change_fields ?? []).slice(0, 2);
  if (!fields.length) {
    return null;
  }
  const [first = "", ...rest] = fields;
  return {
    label: "Changed",
    value: rest.length ? `${titleCaseLabel(first)} +${rest.length}` : titleCaseLabel(first),
    title: "Important fields that changed since this card was last seen",
    key: "changed-fields",
  };
}

function alertContextItem(card: ReviewCard): ContextItem | null {
  if (!card.alert_summary?.alert_count) {
    return null;
  }
  return {
    label: "Alert",
    value: alertProofLabel(card),
    title: alertProofTitle(card),
    key: "alert",
  };
}

type ContextItem = {
  label: string;
  value: string;
  title: string;
  key: string;
};

function reviewStatusLabel(status?: string) {
  const normalized = String(status || "pending").toLowerCase();
  const labels: Record<string, string> = {
    false_positive: "Wrong match",
    follow_up: "Profile draft",
    kept: "Preferred",
    pending: "Needs decision",
    skipped: "Deprioritized",
  };
  return labels[normalized] || titleCaseLabel(normalized);
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
  const target = summary.latest_target_type || summary.latest_target_id || "delivery target";
  const when = summary.latest_alerted_at ? ` at ${formatDate(summary.latest_alerted_at)}` : "";
  return `${summary.alert_count} alert event${summary.alert_count === 1 ? "" : "s"} via ${target}${mode}${when}`;
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

function opportunityStatusLabel(status: string) {
  const normalized = String(status || "open").toLowerCase();
  const labels: Record<string, string> = {
    open: "Open",
    saved: "Saved",
    applied: "Applied",
    contacted: "Applied",
    dismissed: "Not a fit",
    duplicate: "Duplicate",
  };
  return labels[normalized] || "Open";
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

function isOpenOpportunity(card: ReviewCard) {
  return String(card.opportunity_status || "open").toLowerCase() === "open";
}

function hasReviewDecision(card: ReviewCard) {
  return String(card.status || "pending").toLowerCase() !== "pending";
}

function MobileActionStrip({
  card,
  act,
  busy,
  showFollowUp,
  setShowFollowUp,
}: {
  card: ReviewCard;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
  showFollowUp: boolean;
  setShowFollowUp: Dispatch<SetStateAction<boolean>>;
}) {
  return (
    <div className="mobile-action-strip" aria-label="Quick review actions">
      {isOpenOpportunity(card) ? (
        <>
          <button
            aria-label="Mark opportunity applied"
            title="Mark opportunity applied"
            type="button"
            data-review-action="applied"
            data-review-tone="positive"
            onClick={() => act(card.card_id, "applied")}
            disabled={busy}
          >
            <Check size={16} />
            <span>Applied</span>
          </button>
          <button
            aria-label="Save opportunity for later"
            title="Save opportunity for later"
            type="button"
            data-review-action="saved"
            data-review-tone="supportive"
            onClick={() => act(card.card_id, "saved")}
            disabled={busy}
          >
            <Bookmark size={16} />
            <span>Save</span>
          </button>
        </>
      ) : (
        <button
          aria-label="Reopen opportunity"
          title="Reopen opportunity"
          type="button"
          data-review-action="reopen"
          data-review-tone="supportive"
          onClick={() => act(card.card_id, "reopen")}
          disabled={busy}
        >
          <Play size={16} />
          <span>Reopen</span>
        </button>
      )}
      {hasReviewDecision(card) && (
        <button
          aria-label={`Undo ${reviewStatusLabel(card.status)} review decision`}
          className="secondary-action"
          title={`Undo ${reviewStatusLabel(card.status)} review decision`}
          type="button"
          data-review-action="undo_decision"
          data-review-tone="caution"
          onClick={() => act(card.card_id, "undo_decision")}
          disabled={busy}
        >
          <RotateCcw size={16} />
          <span>Undo</span>
        </button>
      )}
      <button
        aria-label={showFollowUp ? "Hide feedback tools" : "Explain why this is not a fit or tune the profile"}
        className="secondary-action"
        data-review-action="tune"
        data-review-tone="negative"
        title={showFollowUp ? "Hide feedback tools" : "Explain why this is not a fit or tune the profile"}
        type="button"
        onClick={() => setShowFollowUp((value) => !value)}
        disabled={busy}
      >
        <FileDiff size={16} />
        <span>{showFollowUp ? "Hide tools" : "Not a fit"}</span>
      </button>
    </div>
  );
}

function ReportArtifactChip({
  path,
  profileId,
  profileReportNames,
  updatedAt,
}: {
  path: string;
  profileId: string;
  profileReportNames: Record<string, string>;
  updatedAt?: string;
}) {
  const label = profileReportNames[profileId] || `${profileDisplayName(profileId)} Report`;
  const format = artifactFormatFromPath(path);
  return (
    <a className="report-chip" href={artifactHref(path)} aria-label={`Open scan details: ${label}`} rel="noreferrer" target="_blank" title={label}>
      <ExternalLink size={13} />
      <span>Scan details</span>
      <small>
        {format} · {formatDate(updatedAt)}
      </small>
    </a>
  );
}

function CardActions({
  card,
  act,
  busy,
  showFollowUp,
  setShowFollowUp,
}: {
  card: ReviewCard;
  act: (cardId: string, action: string, note?: string) => void;
  busy: boolean;
  showFollowUp: boolean;
  setShowFollowUp: Dispatch<SetStateAction<boolean>>;
}) {
  const [note, setNote] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const noteId = `profile-diff-note-${card.card_id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  useEffect(() => {
    if (!showFollowUp) {
      return;
    }

    const timer = window.setTimeout(() => {
      const textarea = textareaRef.current;
      if (!textarea) {
        return;
      }
      const prefersReducedMotion =
        typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      textarea.focus({ preventScroll: true });
      if (typeof textarea.scrollIntoView === "function") {
        textarea.scrollIntoView({
          behavior: prefersReducedMotion ? "auto" : "smooth",
          block: "nearest",
        });
      }
    }, 0);

    return () => window.clearTimeout(timer);
  }, [showFollowUp]);

  return (
    <div className="card-actions">
      <div className="action-cluster lifecycle-cluster" aria-label="Opportunity lifecycle actions">
        <span className="action-cluster-label">Opportunity</span>
        {isOpenOpportunity(card) ? (
          <>
            <button
              title="Mark opportunity applied"
              type="button"
              data-review-action="applied"
              data-review-tone="positive"
              onClick={() => act(card.card_id, "applied")}
              disabled={busy}
            >
              <Check size={16} />
              <span>Applied</span>
            </button>
            <button
              title="Save opportunity for later"
              type="button"
              data-review-action="saved"
              data-review-tone="supportive"
              onClick={() => act(card.card_id, "saved")}
              disabled={busy}
            >
              <Bookmark size={16} />
              <span>Saved</span>
            </button>
          </>
        ) : (
          <button
            title="Reopen opportunity"
            type="button"
            data-review-action="reopen"
            data-review-tone="supportive"
            onClick={() => act(card.card_id, "reopen")}
            disabled={busy}
          >
            <Play size={16} />
            <span>Reopen</span>
          </button>
        )}
      </div>
      {!showFollowUp && (
        <div className="tune-profile-entry" aria-label="Profile tuning entry">
          {hasReviewDecision(card) && (
            <button
              className="decision-undo-trigger"
              data-review-action="undo_decision"
              data-review-tone="caution"
              title={`Undo ${reviewStatusLabel(card.status)} review decision`}
              type="button"
              onClick={() => act(card.card_id, "undo_decision")}
              disabled={busy}
            >
              <RotateCcw size={16} />
              <span>Undo decision</span>
              <small>{reviewStatusLabel(card.status)}</small>
            </button>
          )}
          <button
            className="tune-profile-trigger"
            data-review-action="tune"
            data-review-tone="negative"
            title="Explain why this is not a fit or tune the profile"
            type="button"
            onClick={() => setShowFollowUp(true)}
            disabled={busy}
          >
            <FileDiff size={17} />
            <span>Not a fit</span>
            <small>Reasons + signals</small>
          </button>
        </div>
      )}
      {showFollowUp && (
        <div className="follow-up">
          <div className="follow-up-head">
            <label htmlFor={noteId}>Feedback</label>
            <button
              className="follow-up-close"
              title="Hide feedback tools"
              type="button"
              onClick={() => setShowFollowUp(false)}
              disabled={busy}
            >
              <X size={14} />
              <span>Hide</span>
            </button>
          </div>
          <div className="follow-up-group">
            <span className="follow-up-group-label">Close card</span>
            <div className="follow-up-signal-grid follow-up-reason-grid" aria-label="Close card reasons">
              <button
                className="follow-up-signal"
                title="Close this opportunity because it is not a fit"
                type="button"
                data-review-action="dismissed"
                data-review-tone="negative"
                onClick={() => act(card.card_id, "dismissed")}
                disabled={busy}
              >
                <X size={16} />
                <span>Not a fit</span>
              </button>
              <button
                className="follow-up-signal"
                title="Close this opportunity as a duplicate"
                type="button"
                data-review-action="duplicate"
                data-review-tone="neutral"
                onClick={() => act(card.card_id, "duplicate")}
                disabled={busy}
              >
                <Archive size={16} />
                <span>Duplicate</span>
              </button>
            </div>
          </div>
          <div className="follow-up-group">
            <span className="follow-up-group-label">Teach matching</span>
            <div className="follow-up-signal-grid" aria-label="Preference training actions">
              <button
                className="follow-up-signal"
                title="Prefer similar future matches"
                type="button"
                data-review-action="keep"
                data-review-tone="positive"
                onClick={() => act(card.card_id, "keep")}
                disabled={busy}
              >
                <Check size={16} />
                <span>Prefer similar</span>
              </button>
              <button
                className="follow-up-signal"
                title="Deprioritize similar future matches"
                type="button"
                data-review-action="skip"
                data-review-tone="caution"
                onClick={() => act(card.card_id, "skip")}
                disabled={busy}
              >
                <X size={16} />
                <span>Deprioritize</span>
              </button>
              <button
                className="follow-up-signal"
                data-review-action="avoid"
                data-review-tone="negative"
                title="Mark as wrong match and avoid similar future matches"
                type="button"
                onClick={() => act(card.card_id, "false_positive")}
                disabled={busy}
              >
                <Ban size={16} />
                <span>Wrong match</span>
              </button>
            </div>
          </div>
          <div className="follow-up-control">
            <textarea
              id={noteId}
              ref={textareaRef}
              aria-label="Feedback note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Describe what future matches should change"
              disabled={busy}
            />
          </div>
          <div className="follow-up-footer">
            <small>Creates a reviewable profile change. The note stays local and is not included in exports.</small>
            <button
              className="follow-up-submit"
              data-review-tone="supportive"
              title={note.trim() ? "Create profile change" : "Add a note first"}
              type="button"
              onClick={() => act(card.card_id, "follow_up", note.trim())}
              disabled={busy || !note.trim()}
            >
              <FileDiff size={16} />
              <span>{note.trim() ? "Create change" : "Add note"}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CardSourceRow({
  activePreviewKey,
  card,
  onPreviewSource,
  previewId,
  profileReportNames,
}: {
  activePreviewKey: string;
  card: ReviewCard;
  onPreviewSource: (preview: SourcePreviewSelection) => void;
  previewId: string;
  profileReportNames: Record<string, string>;
}) {
  return (
    <div className="source-row" aria-label="Original sources and scan details">
      <SourceLinks
        activePreviewKey={activePreviewKey}
        previewId={previewId}
        refs={card.source_refs}
        onPreviewSource={onPreviewSource}
      />
      {card.report_path && (
        <ReportArtifactChip
          path={card.report_path}
          profileId={card.profile_id}
          profileReportNames={profileReportNames}
          updatedAt={card.updated_at}
        />
      )}
    </div>
  );
}

function SourceLinks({
  activePreviewKey,
  onPreviewSource,
  previewId,
  refs,
}: {
  activePreviewKey: string;
  onPreviewSource: (preview: SourcePreviewSelection) => void;
  previewId: string;
  refs: SourceRef[];
}) {
  if (!refs.length) {
    return <span className="source-chip muted">Original unavailable</span>;
  }
  return (
    <>
      {refs.slice(0, 4).map((ref, index) => {
        const href = sourceRefUrl(ref);
        const label = sourceRefLabel(ref);
        const sourceTitle = `@${String(ref.channel || "").replace(/^@+/, "")} #${String(ref.id || "")}`;
        const actionLabel = index === 0 ? "View original" : `Original ${index + 1}`;
        const key = sourcePreviewKey(ref, index);
        return (
          <button
            aria-controls={previewId}
            aria-expanded={activePreviewKey === key}
            className={index === 0 ? "source-chip source-link source-primary" : "source-chip source-link"}
            data-source-preview={key}
            key={key}
            onClick={() => onPreviewSource({ key, ref, index })}
            title={href ? `Preview Telegram source: ${sourceTitle}` : `Preview source details: ${label}`}
            type="button"
          >
            <span>{actionLabel}</span>
            <small>{label}</small>
            <Eye size={12} aria-hidden="true" />
          </button>
        );
      })}
      {refs.length > 4 && <span className="source-chip muted">+{refs.length - 4} originals</span>}
    </>
  );
}

function SourcePreviewPanel({
  card,
  id,
  onClose,
  preview,
}: {
  card: ReviewCard;
  id: string;
  onClose: () => void;
  preview: SourcePreviewSelection;
}) {
  const href = sourceRefUrl(preview.ref);
  const label = sourceRefLabel(preview.ref);
  const messageId = String(preview.ref.id || "").trim();
  const [content, setContent] = useState<SourcePreviewContent>(() =>
    card.report_path ? { status: "loading" } : { status: "missing", detail: "Original text is not available for this scan." },
  );

  useEffect(() => {
    let cancelled = false;
    setContent(card.report_path ? { status: "loading" } : { status: "missing", detail: "Original text is not available for this scan." });
    if (!card.report_path) {
      return;
    }
    loadRenderedOriginalSource(card, preview.ref)
      .then((result) => {
        if (!cancelled) {
          setContent(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setContent({ status: "error", detail: "Original text could not be loaded from scan details." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [card.report_path, card.title, preview.key]);

  return (
    <div className="source-preview-panel" id={id} role="region" aria-label="Original source preview">
      <div className="source-preview-head">
        <span>
          <Eye size={14} />
          Original source
        </span>
        <button type="button" onClick={onClose} title="Close original source preview">
          <X size={14} />
          <span>Close</span>
        </button>
      </div>
      <div className="source-preview-body">
        <SourcePreviewOriginal content={content} />
        <div className="source-preview-meta" aria-label="Original source details">
          <span>
            <strong>Channel</strong>
            {label}
          </span>
          {messageId && (
            <span>
              <strong>Message</strong>
              #{messageId}
            </span>
          )}
        </div>
        <div className="source-preview-actions">
          {href ? (
            <a href={href} rel="noreferrer" target="_blank" title={telegramMessageUrl(preview.ref) || preview.ref.url || href}>
              <ExternalLink size={14} />
              <span>Open in Telegram</span>
            </a>
          ) : (
            <span className="source-preview-unavailable">Telegram link unavailable</span>
          )}
        </div>
      </div>
    </div>
  );
}

function SourcePreviewOriginal({ content }: { content: SourcePreviewContent }) {
  if (content.status === "loading") {
    return <div className="source-preview-loading">Loading original text...</div>;
  }
  if (content.status === "ready") {
    return <div className="source-original-html" dangerouslySetInnerHTML={{ __html: content.html }} />;
  }
  return <div className="source-preview-loading">{content.detail}</div>;
}

async function loadRenderedOriginalSource(card: ReviewCard, ref: SourceRef): Promise<SourcePreviewContent> {
  if (!card.report_path) {
    return { status: "missing", detail: "Original text is not available for this scan." };
  }
  const response = await fetch(artifactHref(card.report_path), { credentials: "same-origin" });
  if (!response.ok) {
    return { status: "error", detail: "Original text could not be loaded from scan details." };
  }
  const documentText = await response.text();
  const parsed = new DOMParser().parseFromString(documentText, "text/html");
  const article = findReportArticleForSource(parsed, ref);
  const rawBody = article?.querySelector(".raw-content-body");
  if (!rawBody?.innerHTML.trim()) {
    return { status: "missing", detail: "Original text was not saved in this scan." };
  }
  return { status: "ready", html: sanitizeSourcePreviewHtml(rawBody.innerHTML) };
}

function findReportArticleForSource(parsed: Document, ref: SourceRef) {
  const articles = Array.from(parsed.querySelectorAll<HTMLElement>("[data-feedback-card]"));
  return articles.find((article) => {
    const payload = parseFeedbackPayload(article.getAttribute("data-feedback-payload"));
    return payload.some((candidate) => sourceRefsMatch(candidate, ref));
  });
}

function parseFeedbackPayload(value: string | null): SourceRef[] {
  if (!value) {
    return [];
  }
  try {
    const payload = JSON.parse(value) as { source_message_refs?: SourceRef[] };
    return Array.isArray(payload.source_message_refs) ? payload.source_message_refs : [];
  } catch {
    return [];
  }
}

function sourceRefsMatch(left: SourceRef, right: SourceRef) {
  return sourceChannelKey(left.channel) === sourceChannelKey(right.channel) && String(left.id || "") === String(right.id || "");
}

function sourceChannelKey(value: unknown) {
  return String(value || "").trim().replace(/^@+/, "").toLowerCase();
}

function sanitizeSourcePreviewHtml(html: string) {
  const parsed = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const sourceRoot = parsed.body.firstElementChild;
  const cleanDocument = document.implementation.createHTMLDocument("");
  const cleanRoot = cleanDocument.createElement("div");
  for (const child of Array.from(sourceRoot?.childNodes ?? [])) {
    const cleanChild = sanitizeSourcePreviewNode(child, cleanDocument);
    if (cleanChild) {
      cleanRoot.appendChild(cleanChild);
    }
  }
  return cleanRoot.innerHTML;
}

function sanitizeSourcePreviewNode(node: Node, cleanDocument: Document): Node | null {
  if (node.nodeType === Node.TEXT_NODE) {
    return cleanDocument.createTextNode(node.textContent || "");
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return null;
  }
  const element = node as Element;
  const tag = element.tagName.toLowerCase();
  if (!["a", "br", "code", "em", "hr", "span", "strong"].includes(tag)) {
    const fragment = cleanDocument.createDocumentFragment();
    for (const child of Array.from(element.childNodes)) {
      const cleanChild = sanitizeSourcePreviewNode(child, cleanDocument);
      if (cleanChild) {
        fragment.appendChild(cleanChild);
      }
    }
    return fragment;
  }
  const cleanElement = cleanDocument.createElement(tag);
  if (tag === "a") {
    const href = element.getAttribute("href") || "";
    if (safeSourceHref(href)) {
      cleanElement.setAttribute("href", href);
      cleanElement.setAttribute("target", "_blank");
      cleanElement.setAttribute("rel", "noopener noreferrer");
    }
  } else if (tag === "span") {
    const safeClasses = (element.getAttribute("class") || "")
      .split(/\s+/)
      .filter((name) => ["channel-label", "inline-ref-list"].includes(name));
    if (safeClasses.length) {
      cleanElement.setAttribute("class", safeClasses.join(" "));
    }
  } else if (tag === "hr" && element.classList.contains("raw-divider")) {
    cleanElement.setAttribute("class", "raw-divider");
  }
  for (const child of Array.from(element.childNodes)) {
    const cleanChild = sanitizeSourcePreviewNode(child, cleanDocument);
    if (cleanChild) {
      cleanElement.appendChild(cleanChild);
    }
  }
  return cleanElement;
}

function safeSourceHref(href: string) {
  return /^(https?:|mailto:)/i.test(href.trim());
}

function sourcePreviewKey(ref: SourceRef, index: number) {
  return `${String(ref.channel || "")}:${String(ref.id || "")}:${index}`;
}
