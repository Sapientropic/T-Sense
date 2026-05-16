import { useState, type RefObject } from "react";
import { Bell, KeyRound, Save, Trash2 } from "lucide-react";

import { BotGatewayPanel } from "./bot-gateway-panel";
import { DeliveryTargetEditor } from "./delivery-target-editor";
import { PanelHeader } from "../common";
import type {
  DeskBotGatewayStatus,
  DeskBotIdentityResult,
  DeskNotificationTokenStatus,
  DeliveryChatDetectionResult,
  DeliveryTarget,
  DeliveryTestResult,
} from "../../domain/types";

const DEFAULT_TELEGRAM_TARGET_ID = "telegram-bot-default";

export function NotificationsPanel({
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
  busy,
  panelRef,
}: {
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
  busy: boolean;
  panelRef: RefObject<HTMLDivElement | null>;
}) {
  const editableTargets = targets.length ? targets : [defaultTelegramDeliveryTarget()];
  return (
    <div className="table-section delivery-targets-panel" ref={panelRef} tabIndex={-1} aria-label="Notifications">
      <PanelHeader icon={<Bell size={18} />} title="Notifications" count={targets.length} />
      <NotificationTokenPanel
        busy={busy}
        clearNotificationToken={clearNotificationToken}
        error={notificationTokenError}
        saveNotificationToken={saveNotificationToken}
        status={notificationTokenStatus}
      />
      <BotGatewayPanel
        applyBotIdentity={applyBotIdentity}
        busy={busy}
        error={botGatewayError}
        identityResult={botIdentityResult}
        installBotGatewayAutostart={installBotGatewayAutostart}
        removeBotGatewayAutostart={removeBotGatewayAutostart}
        status={botGatewayStatus}
      />
      <div className="delivery-target-list">
        {editableTargets.map((target) => (
          <DeliveryTargetEditor
            busy={busy}
            detectionResult={deliveryChatDetection?.target_id === target.target_id ? deliveryChatDetection : null}
            detectDeliveryChatId={detectDeliveryChatId}
            key={target.target_id}
            saveDeliveryTarget={saveDeliveryTarget}
            target={target}
            testDeliveryTarget={testDeliveryTarget}
            testResult={deliveryTest?.target_id === target.target_id ? deliveryTest : null}
          />
        ))}
      </div>
    </div>
  );
}

function defaultTelegramDeliveryTarget(): DeliveryTarget {
  return {
    schema_version: "delivery_target_v1",
    target_id: DEFAULT_TELEGRAM_TARGET_ID,
    type: "telegram_bot",
    enabled: false,
    config: {},
    display_name: "Default notification chat",
    status_label: "Not saved",
    detail: "Add a Telegram chat ID to create the default private bot notification target.",
    updated_at: "",
  };
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
  const sourceLabel = notificationTokenSourceLabel(status?.source, status?.local_store_label);
  const canSave = status?.can_save !== false;
  const canClear = status?.can_clear === true;
  const tokenEditor = (showDetail = true) => (
    <>
      <label className="delivery-field">
        <span>Bot token</span>
        <input
          autoComplete="new-password"
          disabled={busy || !canSave}
          onChange={(event) => setToken(event.target.value)}
          placeholder={canSave ? "123456:ABC..." : "Local secure storage unavailable"}
          type="password"
          value={token}
        />
      </label>
      <p
        className="delivery-note"
        title="Token text is never shown again. Environment variables still take priority."
      >
        Stored locally. Never shown again.
      </p>
      {showDetail && (status?.detail || error) && (
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
    </>
  );
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
          <small>{status ? `${configured ? "Saved" : "Missing"} · ${sourceLabel}` : "Checking token status"}</small>
        </div>
        <span className={configured ? "status enabled" : "status disabled"}>{configured ? "Saved" : "Needed"}</span>
      </div>
      {configured && !token ? (
        <>
          <p className="delivery-note">Token is saved, not verified. Use this only when rotating or removing the bot token.</p>
          {error && (
            <p className="delivery-token-warning" role="alert">
              {error}
            </p>
          )}
          <details className="notification-token-change">
            <summary>Change saved token</summary>
            {tokenEditor(!error)}
          </details>
        </>
      ) : (
        tokenEditor()
      )}
    </form>
  );
}

function notificationTokenSourceLabel(source?: string, localStoreLabel?: string) {
  if (source === "environment") {
    return "environment override";
  }
  if (source === "windows_credential_manager" || source === "keyring") {
    return localStoreLabel || "local secure storage";
  }
  if (source === "credential_error") {
    return "credential store error";
  }
  return "not configured";
}
