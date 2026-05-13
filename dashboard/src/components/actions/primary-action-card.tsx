import { ArrowRight, Play } from "lucide-react";

import type { DeskActiveAction } from "../../domain/types";
import type { JourneyStep } from "./journey-model";
import { ActiveActionProgress } from "./journey-step-card";

export type PrimaryReadyAction = {
  kind: "review" | "scan";
  title: string;
  detail: string;
  label: string;
  actionId?: string;
};

export function buildPrimaryReadyAction(step: JourneyStep | undefined, reviewCount: number, canOpenReview: boolean): PrimaryReadyAction | null {
  if (reviewCount > 0 && canOpenReview) {
    return {
      kind: "review",
      title: "Review cards first",
      detail: "Handle the current cards before changing automation.",
      label: `Review ${reviewCount} card${reviewCount === 1 ? "" : "s"}`,
    };
  }
  const button = step?.buttons.find((item) => item.variant === "primary") ?? step?.buttons[0];
  if (!button) {
    return null;
  }
  return {
    kind: "scan",
    title: step?.title || "Run another scan",
    detail: "Create fresh review cards. Nothing sends to Telegram unless live delivery is enabled.",
    label: button.label,
    actionId: button.actionId,
  };
}

export function StartPrimaryActionCard({
  action,
  activeActions,
  anyBusy,
  busyActionId,
  onOpenReview,
  onRun,
}: {
  action: PrimaryReadyAction;
  activeActions: DeskActiveAction[];
  anyBusy: boolean;
  busyActionId: string;
  onOpenReview?: () => void;
  onRun: (actionId: string) => Promise<void>;
}) {
  const busy = Boolean(action.actionId && busyActionId === action.actionId);
  const activeAction = action.actionId ? activeActions.find((item) => item.action_id === action.actionId) : undefined;
  return (
    <article className={`start-next-card is-${action.kind}`} aria-label="Recommended next action">
      <div>
        <span className="status new">Next</span>
        <h3>{action.title}</h3>
        <p>{action.detail}</p>
        {activeAction && <ActiveActionProgress action={activeAction} />}
      </div>
      <button
        className="journey-button"
        disabled={anyBusy}
        onClick={() => {
          if (action.kind === "review") {
            onOpenReview?.();
            return;
          }
          if (action.actionId) {
            void onRun(action.actionId);
          }
        }}
        type="button"
      >
        {action.kind === "review" ? <ArrowRight size={16} /> : <Play size={16} />}
        <span>{busy ? "Working" : action.label}</span>
      </button>
    </article>
  );
}
