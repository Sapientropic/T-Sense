import { AlertTriangle, CircleDashed, LockKeyhole, Play } from "lucide-react";
import { useState } from "react";

import type { TelegramControls } from "./types";

export function TelegramLoginPanel({ telegram }: { telegram: TelegramControls }) {
  const [apiId, setApiId] = useState("");
  const [apiHash, setApiHash] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const status = telegram.status;
  const busy = Boolean(telegram.busy);
  const needsCode = status?.login_state === "code_sent" || status?.login_state === "needs_password";
  const needsPassword = status?.login_state === "needs_password";
  const credentialsReady = Boolean(status?.credentials_ready);
  const connected = Boolean(status?.session_ready);
  const ready = credentialsReady && connected;
  const credentialsLabel = !credentialsReady ? "Missing" : connected || status?.credentials_status === "verified" ? "Verified" : "Saved";
  const credentialForm = (title: string, detail: string) => (
    <form
      className="telegram-form credentials"
      onSubmit={(event) => {
        event.preventDefault();
        void telegram.saveCredentials(apiId, apiHash).then(() => {
          setApiHash("");
        }).catch(() => undefined);
      }}
    >
      <div className="telegram-form-intro">
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      <label>
        <span>Telegram app ID</span>
        <input
          autoComplete="off"
          inputMode="numeric"
          onChange={(event) => setApiId(event.target.value)}
          placeholder="123456"
          type="text"
          value={apiId}
        />
      </label>
      <label>
        <span>Telegram app hash</span>
        <input
          autoComplete="off"
          onChange={(event) => setApiHash(event.target.value)}
          placeholder="32-character app hash"
          type="password"
          value={apiHash}
        />
      </label>
      <button className="journey-button secondary" disabled={busy || !apiId.trim() || !apiHash.trim()} type="submit">
        <LockKeyhole size={15} />
        <span>{telegram.busy === "credentials" ? "Saving" : "Save app details"}</span>
      </button>
    </form>
  );

  return (
    <div className="telegram-panel" aria-label="Telegram login controls">
      <div className="telegram-status-grid">
        <span className={credentialsReady ? (connected ? "ready" : "pending") : "blocked"}>
          <strong>{credentialsLabel}</strong>
          App credentials
        </span>
        <span className={connected ? "ready" : "blocked"}>
          <strong>{connected ? "Ready" : "Needs login"}</strong>
          Telegram login
        </span>
      </div>
      {status?.detail && <p className="telegram-status-note">{status.detail}</p>}
      {telegram.error && <p className="telegram-error">{telegram.error}</p>}

      {!ready && (
        <div className="telegram-forms">
          {!credentialsReady &&
            credentialForm(
              "Step 1: Save app details",
              "Get your Telegram app ID and app hash from my.telegram.org. They look like a number and a long letter code.",
            )}

          {credentialsReady && !connected && (
            <>
              <details className="telegram-credential-repair">
                <summary>Change app details</summary>
                {credentialForm(
                  "Replace saved app details",
                  "Use this when Telegram rejects the app ID/hash or you copied the wrong values.",
                )}
              </details>
              <form
                className="telegram-form login"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (needsCode) {
                    void telegram.verifyCode(code, password).then((next) => {
                      if (next.session_ready) {
                        setCode("");
                        setPassword("");
                      }
                    }).catch(() => undefined);
                    return;
                  }
                  void telegram.sendCode(phone).catch(() => undefined);
                }}
              >
                <div className="telegram-form-intro">
                  <strong>Step 2: Log in</strong>
                  <span>Use the phone number for your Telegram account. Signal Desk stores the session only on this computer.</span>
                </div>
                <label>
                  <span>Phone number</span>
                  <input
                    autoComplete="tel"
                    disabled={needsCode}
                    onChange={(event) => setPhone(event.target.value)}
                    pattern="\+?[0-9][0-9 ()-]{5,24}"
                    placeholder="+1..."
                    type="tel"
                    value={phone}
                  />
                </label>
                {needsCode && (
                  <label>
                    <span>Verification code</span>
                    <input
                      autoComplete="one-time-code"
                      inputMode="numeric"
                      onChange={(event) => setCode(event.target.value)}
                      placeholder="Code from Telegram"
                      type="text"
                      value={code}
                    />
                  </label>
                )}
                {needsPassword && (
                  <label>
                    <span>Two-step verification password</span>
                    <input
                      autoComplete="current-password"
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="Telegram password"
                      type="password"
                      value={password}
                    />
                  </label>
                )}
                <div className="telegram-form-actions">
                  <button
                    className="journey-button"
                    disabled={busy || (needsCode ? !code.trim() : !phone.trim())}
                    type="submit"
                  >
                    <Play size={15} />
                    <span>{telegram.busy === "send-code" ? "Sending" : telegram.busy === "verify-code" ? "Verifying" : needsCode ? "Finish login" : "Send code"}</span>
                  </button>
                  <button className="journey-button secondary" disabled={busy} onClick={() => void telegram.refresh().catch(() => undefined)} type="button">
                    <CircleDashed size={15} />
                    <span>Check</span>
                  </button>
                  {needsCode && (
                    <button className="journey-button secondary" disabled={busy} onClick={() => void telegram.cancelLogin().catch(() => undefined)} type="button">
                      <AlertTriangle size={15} />
                      <span>Cancel</span>
                    </button>
                  )}
                </div>
              </form>
            </>
          )}
        </div>
      )}
    </div>
  );
}
