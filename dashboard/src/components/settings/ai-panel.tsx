import { useEffect, useRef, useState, type RefObject } from "react";
import { PlugZap, Save, ShieldCheck, Trash2 } from "lucide-react";

import { InlineEmpty, PanelHeader } from "../common";
import type { DeskAiSettingsStatus } from "../../domain/types";

export function AiApiSettingsPanel({
  status,
  error,
  busy,
  saveAiApiKey,
  clearAiApiKey,
  panelRef,
}: {
  status: DeskAiSettingsStatus | null;
  error: string | null;
  busy: boolean;
  saveAiApiKey: (provider: string, apiKey: string) => Promise<void>;
  clearAiApiKey: (provider: string) => Promise<void>;
  panelRef: RefObject<HTMLDivElement | null>;
}) {
  const providers = status?.providers ?? [];
  const firstProvider = providers[0]?.provider ?? "openai";
  const [provider, setProvider] = useState(firstProvider);
  const [apiKey, setApiKey] = useState("");
  const apiKeyInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!providers.some((item) => item.provider === provider) && firstProvider) {
      setProvider(firstProvider);
    }
  }, [firstProvider, provider, providers]);

  const selected = providers.find((item) => item.provider === provider);
  const selectedProviderKey = provider.toLowerCase();
  const showOpenAiOAuth = selectedProviderKey === "openai";
  const localStoreLabel = selected?.local_store_label ?? status?.local_store_label ?? "local secure storage";
  const canSave = Boolean(selected?.can_save && apiKey.trim());
  const canClear = Boolean(selected?.can_clear);
  const matchingKeyCount = status?.matching_configured_count ?? status?.configured_count ?? 0;
  return (
    <div className="table-section ai-api-panel" ref={panelRef} tabIndex={-1} aria-label="AI API keys">
      <PanelHeader icon={<PlugZap size={18} />} title="AI API" count={matchingKeyCount} />
      <div className="ai-provider-grid" aria-label="AI provider status">
        {providers.length ? (
          providers.map((item) => (
            <button
              aria-pressed={provider === item.provider}
              className={item.configured ? "configured" : ""}
              key={item.provider}
              onClick={() => setProvider(item.provider)}
              type="button"
            >
              <strong>{item.label}</strong>
              <span>{providerStatusLabel(item)}</span>
            </button>
          ))
        ) : (
          <InlineEmpty title="Loading AI API settings" />
        )}
      </div>
      {selected?.detail && <p className="ai-api-note">{selected.detail}</p>}
      {error && <p className="delivery-test-result failed">{error}</p>}
      {showOpenAiOAuth && (
        <div className="ai-oauth-card" aria-label="OpenAI subscription sign-in">
          <div>
            <strong>ChatGPT subscription sign-in</strong>
            <span>OAuth needs a local OpenAI client before it can run. API key is the working path now.</span>
          </div>
          <button className="text-button secondary" onClick={() => apiKeyInputRef.current?.focus()} type="button">
            <ShieldCheck size={15} />
            <span>Use API key</span>
          </button>
        </div>
      )}
      <form
        className="ai-api-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!canSave) {
            return;
          }
          void saveAiApiKey(provider, apiKey).then(() => setApiKey(""));
        }}
      >
        <label className="delivery-field">
          <span>Provider</span>
          <select disabled={busy || !providers.length} onChange={(event) => setProvider(event.target.value)} value={provider}>
            {providers.map((item) => (
              <option key={item.provider} value={item.provider}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="delivery-field">
          <span>API key</span>
          <input
            autoComplete="new-password"
            disabled={busy || selected?.can_save === false}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={selected?.configured ? "Paste a replacement key" : "Paste API key"}
            ref={apiKeyInputRef}
            type="password"
            value={apiKey}
          />
        </label>
        <div className="delivery-actions">
          <button className="text-button" disabled={busy || !canSave} type="submit">
            <Save size={15} />
            <span>{busy ? "Saving" : "Save key"}</span>
          </button>
          <button
            className="text-button secondary"
            disabled={busy || !canClear}
            onClick={() => void clearAiApiKey(provider)}
            type="button"
          >
            <Trash2 size={15} />
            <span>Clear saved key</span>
          </button>
        </div>
      </form>
      <p className="ai-api-note">
        Keys are stored locally in {localStoreLabel} when available. Environment variables still win when both are present.
      </p>
    </div>
  );
}

function providerStatusLabel(item: DeskAiSettingsStatus["providers"][number]) {
  if (!item.configured) {
    return "Missing";
  }
  if (item.verification_status === "verified") {
    return "Verified";
  }
  if (item.purpose === "ocr") {
    return item.env_configured ? "OCR ENV" : "OCR saved";
  }
  return item.env_configured ? "ENV, not tested" : "Saved, not tested";
}
