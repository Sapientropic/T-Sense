import { useEffect, useState } from "react";
import { Eye, FolderSearch, Save } from "lucide-react";

import type { Profile, SourceImportResult } from "../../domain/types";

export function SourceImportPanel({
  result,
  previewSourceImport,
  importSources,
  importStarterSources,
  previewSourceAssistant,
  applySourceAssistant,
  busy,
  hasSavedSources,
  profiles,
}: {
  result: SourceImportResult | null;
  previewSourceImport: (sources: string, topic: string) => Promise<SourceImportResult>;
  importSources: (sources: string, topic: string) => Promise<SourceImportResult>;
  importStarterSources: (topic: string) => Promise<SourceImportResult>;
  previewSourceAssistant: (
    instruction: string,
    topic: string,
    confirmExternalAi?: boolean,
    profileId?: string,
    folderName?: string,
  ) => Promise<SourceImportResult>;
  applySourceAssistant: (
    instruction: string,
    topic: string,
    confirmExternalAi?: boolean,
    resolvedPlan?: SourceImportResult["resolved_plan"],
    profileId?: string,
    folderName?: string,
  ) => Promise<SourceImportResult>;
  busy: boolean;
  hasSavedSources: boolean;
  profiles: Profile[];
}) {
  const [assistantPreviewKey, setAssistantPreviewKey] = useState("");
  const activeProfiles = profiles.filter((profile) => profile.enabled);
  const selectableProfiles = activeProfiles.length ? activeProfiles : profiles;
  const initialProfileId = selectableProfiles[0]?.profile_id ?? "";
  const [profileId, setProfileId] = useState(initialProfileId);
  const [folderName, setFolderName] = useState("");
  const selectedProfile = selectableProfiles.find((profile) => profile.profile_id === profileId) ?? selectableProfiles[0];
  const selectedProfileId = selectedProfile?.profile_id ?? "";
  const selectedProfileLabel = selectedProfile?.display_name || selectedProfile?.report_display_name || selectedProfile?.profile_id || "Profile";
  const topic = selectedProfile?.source_topics?.[0] || selectedProfileId || "default";
  const folder = folderName.trim();
  const instruction = folder
    ? `Scan Telegram folder "${folder}" and let AI select sources for ${selectedProfileLabel}.`
    : `Scan all Telegram channels and let AI select sources for ${selectedProfileLabel}.`;
  const assistantKey = `${selectedProfileId}\n${folder.toLowerCase()}\n${topic}`;
  const assistantOperationCount = result
    ? result.added_count + result.updated_count + (result.removed_count ?? 0) + (result.enabled_count ?? 0) + (result.disabled_count ?? 0)
    : 0;
  const canAssistantPreview = Boolean(selectedProfileId);
  const canAssistantApply =
    canAssistantPreview &&
    assistantPreviewKey === assistantKey &&
    result?.dry_run === true &&
    result.action === "assistant" &&
    assistantOperationCount > 0 &&
    !!result.resolved_plan;
  const previewSources = result?.preview_sources ?? [];
  void previewSourceImport;
  void importSources;
  void importStarterSources;

  useEffect(() => {
    if (!profileId && initialProfileId) {
      setProfileId(initialProfileId);
    }
  }, [initialProfileId, profileId]);

  return (
    <details className="table-section source-import-panel source-import-details" open={!hasSavedSources}>
      <summary>
        <span className="panel-title">
          <FolderSearch size={18} />
          Discover Sources
        </span>
      </summary>
      <form
        className="source-import-form source-assistant-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!canAssistantPreview) {
            return;
          }
          void previewSourceAssistant(instruction, topic, true, selectedProfileId, folder || undefined)
            .then((next) => {
              if (next.dry_run && next.action === "assistant") {
                setAssistantPreviewKey(assistantKey);
              }
            })
            .catch(() => undefined);
        }}
      >
        <p className="delivery-note">AI filters your Telegram channels against the selected profile.</p>
        <label className="source-import-field">
          <span>Profile</span>
          <select
            onChange={(event) => {
              setProfileId(event.target.value);
              setAssistantPreviewKey("");
            }}
            value={selectedProfileId}
          >
            {selectableProfiles.map((profile) => (
              <option key={profile.profile_id} value={profile.profile_id}>
                {profile.display_name || profile.report_display_name || profile.profile_id}
              </option>
            ))}
          </select>
        </label>
        <label className="source-import-field">
          <span>Telegram folder</span>
          <input
            onChange={(event) => {
              setFolderName(event.target.value);
              setAssistantPreviewKey("");
            }}
            placeholder="Optional folder name"
            type="text"
            value={folderName}
          />
        </label>
        <label className="source-assistant-ai">
          <input checked={!folder} readOnly type="checkbox" />
          <span>Scan all channels</span>
        </label>
        <div className="source-import-actions">
          <button className="text-button secondary" disabled={busy || !canAssistantPreview} type="submit">
            <Eye size={15} />
            <span>{busy ? "Checking" : "Preview AI selection"}</span>
          </button>
          <button
            className="text-button"
            disabled={busy || !canAssistantApply}
            onClick={() =>
              void applySourceAssistant(instruction, topic, true, result?.resolved_plan, selectedProfileId, folder || undefined).catch(
                () => undefined,
              )
            }
            type="button"
          >
            <Save size={15} />
            <span>Apply selected list</span>
          </button>
        </div>
        {canAssistantPreview && assistantPreviewKey !== assistantKey && result?.dry_run && (
          <span className="delivery-dirty">Preview again before applying</span>
        )}
        {result && (
          <div className={`source-import-result ${result.written ? "written" : "preview"}`} role="status">
            <strong>{result.title || (result.written ? "Sources saved" : "Source preview ready")}</strong>
            <span>
              {result.added_count} new / {result.updated_count} updated / {result.unchanged_count} already saved
              {result.removed_count ? ` / ${result.removed_count} removed` : ""}
              {result.enabled_count ? ` / ${result.enabled_count} enabled` : ""}
              {result.disabled_count ? ` / ${result.disabled_count} paused` : ""}
            </span>
            {previewSources.length > 0 && (
              <div className="source-import-preview-list" aria-label="Preview sources">
                {previewSources.map((source) => (
                  <small key={source.source_id}>{source.label}</small>
                ))}
                {result.preview_truncated_count > 0 && <small>+{result.preview_truncated_count} more</small>}
              </div>
            )}
            {result.next_action && <em>{result.next_action}</em>}
          </div>
        )}
      </form>
    </details>
  );
}
