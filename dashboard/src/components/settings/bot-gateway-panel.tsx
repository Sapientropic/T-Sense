import { CirclePause, CirclePlay, RadioTower, ShieldCheck, Wrench } from "lucide-react";

import type { DeskBotGatewayStatus, DeskBotIdentityResult } from "../../domain/types";

export function botGatewayStatusLine(status: DeskBotGatewayStatus | null) {
  if (!status) {
    return "Checking · token unknown · chats unknown";
  }
  const gatewayLabel = status.gateway_status === "running"
    ? "Running"
    : status.gateway_status === "stale"
      ? "Stale"
      : "Not detected";
  const tokenLabel = status.token_configured ? "token ready" : "token missing";
  const chatLabel = status.authorized_chat_count === 0
    ? "no chats"
    : `${status.authorized_chat_count} chat${status.authorized_chat_count === 1 ? "" : "s"}`;
  return `${gatewayLabel} · ${tokenLabel} · ${chatLabel}`;
}

function botGatewayBackendLabel(backend?: string) {
  if (backend === "windows_schtasks") {
    return "Windows Task Scheduler";
  }
  if (backend === "macos_launchd") {
    return "launchd";
  }
  if (backend === "linux_systemd_user") {
    return "systemd user";
  }
  return "local scheduler";
}

export function botGatewayBackgroundLine(status: DeskBotGatewayStatus | null) {
  if (!status) {
    return "Background mode unknown";
  }
  if (!status.token_configured) {
    return "Save token before background mode";
  }
  if (status.authorized_chat_count <= 0) {
    return "Add chat before background mode";
  }
  const backendLabel = botGatewayBackendLabel(status.background?.backend);
  if (status.background?.installed) {
    return `Background on · ${backendLabel}`;
  }
  if (status.background?.available) {
    return `Background off · ${backendLabel}`;
  }
  return `Background unavailable · ${backendLabel}`;
}

export function botGatewayLivenessLine(status: DeskBotGatewayStatus | null) {
  if (!status) {
    return "Bot status unknown";
  }
  if (!status.token_configured) {
    return "Bot needs a token";
  }
  if (status.authorized_chat_count <= 0) {
    return "Bot needs a chat";
  }
  if (status.gateway_status === "running") {
    return "Bot is running";
  }
  if (status.gateway_status === "stale") {
    return "Bot may be stopped";
  }
  return "Bot is stopped";
}

export function botGatewayRepairLabel(status: DeskBotGatewayStatus | null) {
  if (!status || status.gateway_status === "stale" || status.background?.installed) {
    return "Restart / repair bot";
  }
  return "Run in background";
}

export function botIdentityResultLine(result: DeskBotIdentityResult | null) {
  if (!result) {
    return "";
  }
  return `${result.name} identity applied · ${result.profile_photo_updated ? "photo updated" : "photo pending"}`;
}

function botGatewayUserLine(status: DeskBotGatewayStatus | null) {
  if (!status) {
    return "Checking the local bot connection.";
  }
  if (!status.token_configured) {
    return "Save a bot token before Signal Desk can send Telegram alerts.";
  }
  if (status.authorized_chat_count === 0) {
    return "Token is saved. Add a chat ID below before live alerts can send.";
  }
  if (status.gateway_status === "running") {
    return "Ready for local Telegram alerts while Signal Desk is running.";
  }
  if (status.background?.installed) {
    return "Background mode is on; Telegram alerts can keep working after login.";
  }
  if (status.gateway_status === "stale") {
    return "Bot was seen before. Turn on background mode or reopen Signal Desk to resume replies.";
  }
  return "Token and chat are saved. Turn on background mode if you want replies without keeping this window open.";
}

function botGatewayChatLabel(status: DeskBotGatewayStatus | null) {
  if (!status) {
    return "Checking";
  }
  if (status.authorized_chat_count <= 0) {
    return "Needs chat";
  }
  return `${status.authorized_chat_count} chat${status.authorized_chat_count === 1 ? "" : "s"}`;
}

function botGatewayBackgroundUserLabel(status: DeskBotGatewayStatus | null) {
  if (!status) {
    return "Checking";
  }
  if (!status.token_configured) {
    return "Needs token";
  }
  if (status.authorized_chat_count <= 0) {
    return "Needs chat";
  }
  if (status.background?.installed) {
    return "On";
  }
  if (status.background?.available) {
    return "Off";
  }
  return "Manual";
}

export function botGatewayCanInstallBackground(status: DeskBotGatewayStatus | null) {
  return Boolean(
    status?.token_configured === true &&
    status.authorized_chat_count > 0 &&
    status.background?.can_install === true &&
    !status.background.installed,
  );
}

function botGatewayCanRepair(status: DeskBotGatewayStatus | null) {
  return Boolean(
    status?.token_configured === true &&
      status.authorized_chat_count > 0 &&
      status.background?.can_install === true &&
      (status.background.installed || status.gateway_status === "stale"),
  );
}

export function BotGatewayPanel({
  status,
  error,
  identityResult,
  busy,
  applyBotIdentity,
  installBotGatewayAutostart,
  removeBotGatewayAutostart,
}: {
  status: DeskBotGatewayStatus | null;
  error: string | null;
  identityResult: DeskBotIdentityResult | null;
  busy: boolean;
  applyBotIdentity: () => Promise<void>;
  installBotGatewayAutostart: () => Promise<void>;
  removeBotGatewayAutostart: () => Promise<void>;
}) {
  const gatewayTone = status?.gateway_status === "running" ? "enabled" : status?.gateway_status === "stale" ? "pending" : "disabled";
  const canApplyIdentity = status?.token_configured === true;
  const canInstallBackground = botGatewayCanInstallBackground(status);
  const canRepair = botGatewayCanRepair(status);
  const canRemoveBackground = status?.background?.can_remove === true;
  const identityLine = botIdentityResultLine(identityResult);
  const repairLabel = botGatewayRepairLabel(status);
  return (
    <section className="bot-gateway-panel" aria-label="Bot Gateway status">
      <div className="notification-token-head">
        <RadioTower size={16} />
        <div>
          <strong>Telegram bot alerts</strong>
          <small>{botGatewayUserLine(status)}</small>
        </div>
        <span className={`status ${gatewayTone}`}>{status?.gateway_status === "running" ? "Live" : "Local"}</span>
      </div>
      <div className="bot-gateway-readout" aria-label="Bot Gateway readiness">
        <span className={`bot-gateway-health ${gatewayTone}`}>
          <strong>{botGatewayLivenessLine(status)}</strong>
          <small>{status?.safe_next_action || "Save bot setup, then repair from here if alerts stop."}</small>
        </span>
        <span>
          <strong>{status?.token_configured ? "Ready" : "Needed"}</strong>
          <small>bot token</small>
        </span>
        <span>
          <strong>{botGatewayChatLabel(status)}</strong>
          <small>alert chat</small>
        </span>
        <span>
          <strong>{botGatewayBackgroundUserLabel(status)}</strong>
          <small>background</small>
        </span>
        <span>
          <strong>{status?.commands_installed ? "Ready" : "Update"}</strong>
          <small>bot menu</small>
        </span>
      </div>
      <div className="bot-gateway-actions">
        <button
          className="text-button"
          disabled={busy || !canRepair}
          onClick={() => void installBotGatewayAutostart()}
          type="button"
        >
          <Wrench size={15} />
          <span>{busy ? "Working" : repairLabel}</span>
        </button>
        <button
          className="text-button secondary"
          disabled={busy || !canInstallBackground}
          onClick={() => void installBotGatewayAutostart()}
          type="button"
        >
          <CirclePlay size={15} />
          <span>{busy ? "Working" : "Run in background"}</span>
        </button>
        <button
          className="text-button secondary"
          disabled={busy || !canRemoveBackground}
          onClick={() => void removeBotGatewayAutostart()}
          type="button"
        >
          <CirclePause size={15} />
          <span>{busy ? "Working" : "Stop background"}</span>
        </button>
        <button
          className="text-button secondary"
          disabled={busy || !canApplyIdentity}
          onClick={() => void applyBotIdentity()}
          type="button"
        >
          <ShieldCheck size={15} />
          <span>{busy ? "Applying" : "Update bot menu"}</span>
        </button>
        <span>{identityLine || "Updates the bot name, menu, and description when a token is saved."}</span>
      </div>
      <details className="bot-gateway-technical">
        <summary>Technical details</summary>
        <div>
          <span>
            <strong>{botGatewayStatusLine(status)}</strong>
            <small>local status</small>
          </span>
          <span>
            <strong>{status?.supported_commands?.join(" ") || "/status /latest /scan"}</strong>
            <small>commands</small>
          </span>
          <span>
            <strong>{status?.start_command || "./tgcs bot run"}</strong>
            <small>manual start</small>
          </span>
          <span>
            <strong>{botGatewayBackgroundLine(status)}</strong>
            <small>scheduler</small>
          </span>
        </div>
      </details>
      <p className={error ? "delivery-token-warning" : "delivery-note"} role={error ? "alert" : undefined}>
        {error || status?.background?.detail || status?.local_first_note || "Bot replies only while the local gateway is running."}
      </p>
    </section>
  );
}
