import { useEffect, useState } from "react";
import { CircleDashed, PlugZap, Save } from "lucide-react";

import { deliveryTargetDetail, deliveryTargetName } from "../../domain/display";
import type { DeliveryChatDetectionResult, DeliveryTarget, DeliveryTestResult } from "../../domain/types";

function deliveryChatId(target: DeliveryTarget) {
  return typeof target.config.chat_id === "string" ? target.config.chat_id : "";
}

export function DeliveryTargetEditor({
  target,
  testResult,
  detectionResult,
  saveDeliveryTarget,
  detectDeliveryChatId,
  testDeliveryTarget,
  busy,
}: {
  target: DeliveryTarget;
  testResult: DeliveryTestResult | null;
  detectionResult: DeliveryChatDetectionResult | null;
  saveDeliveryTarget: (targetId: string, chatId: string, enabled: boolean) => Promise<void>;
  detectDeliveryChatId: (targetId: string) => Promise<DeliveryChatDetectionResult>;
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
          onClick={() =>
            void detectDeliveryChatId(target.target_id)
              .then((result) => {
                if (result.ok && result.chat_id) {
                  setChatId(result.chat_id);
                }
              })
              .catch(() => undefined)
          }
          type="button"
        >
          <PlugZap size={15} />
          <span>Detect chat ID</span>
        </button>
        <button
          className="text-button secondary"
          disabled={busy}
          onClick={() => void testDeliveryTarget(target.target_id, chatId)}
          type="button"
        >
          <CircleDashed size={15} />
          <span>Send test message</span>
        </button>
      </div>
      <p className="delivery-note">Sends a Telegram message to this chat so you can confirm the target is usable.</p>
      {hasUnsavedChanges && <span className="delivery-dirty">Unsaved changes</span>}
      {testResult && (
        <div className={`delivery-test-result ${testResult.ok ? "ok" : "failed"}`} role="status">
          <strong>{testResult.title || "Notification test"}</strong>
          <span>{testResult.detail || testResult.status}</span>
        </div>
      )}
      {detectionResult && (
        <div className={`delivery-test-result ${detectionResult.ok ? "ok" : "failed"}`} role="status">
          <strong>{detectionResult.title || "Chat ID detection"}</strong>
          <span>{detectionResult.detail || detectionResult.status}</span>
        </div>
      )}
    </form>
  );
}
