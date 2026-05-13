import { Bell, Wrench } from "lucide-react";

import type { DeskAction } from "../../domain/types";
import type { StartSummaryItem } from "./journey-model";

export function StartSummary({
  actionMap,
  busyActionId,
  items,
  onRun,
}: {
  actionMap: Map<string, DeskAction>;
  busyActionId: string;
  items: StartSummaryItem[];
  onRun: (actionId: string) => Promise<void>;
}) {
  return (
    <div className="start-summary" aria-label="Setup summary">
      {items.map((item) => {
        const actionId = item.actionId;
        const showAction = Boolean(actionId && actionMap.has(actionId));
        return (
          <div className={showAction ? "is-actionable" : ""} key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            {showAction && actionId && (
              <button
                aria-label={`${item.label}: ${item.actionLabel}`}
                className="start-summary-action"
                disabled={Boolean(busyActionId)}
                onClick={() => void onRun(actionId)}
                title={item.actionLabel}
                type="button"
              >
                {item.actionLabel === "Open settings" ? <Wrench size={14} /> : <Bell size={14} />}
                <span>{item.actionLabel}</span>
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
