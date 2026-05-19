import { useEffect, useState } from "react";
import { Eye, FolderSearch, Link2, Save, Sparkles } from "lucide-react";

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
    folderId?: string,
  ) => Promise<SourceImportResult>;
  applySourceAssistant: (
    instruction: string,
    topic: string,
    confirmExternalAi?: boolean,
    resolvedPlan?: SourceImportResult["resolved_plan"],
    profileId?: string,
    folderName?: string,
    folderId?: string,
  ) => Promise<SourceImportResult>;
  busy: boolean;
  hasSavedSources: boolean;
  profiles: Profile[];
}) {
  const [assistantPreviewKey, setAssistantPreviewKey] = useState("");
  const activeProfiles = profiles.filter((profile) => profile.enabled);
  const selectableProfiles = activeProfiles.length ? activeProfiles : profiles;
  const initialProfileId = selectableProfiles[0]?.profile_id ?? "";
  const hasSelectableProfiles = selectableProfiles.length > 0;
  const [profileId, setProfileId] = useState(initialProfileId);
  const [folderName, setFolderName] = useState("");
  const [folderId, setFolderId] = useState("");
  const [publicSources, setPublicSources] = useState("");
  const [scanScope, setScanScope] = useState<"all" | "folder">("all");
  const selectedProfile = selectableProfiles.find((profile) => profile.profile_id === profileId) ?? selectableProfiles[0];
  const selectedProfileId = selectedProfile?.profile_id ?? "";
  const selectedProfileLabel = selectedProfile?.display_name || selectedProfile?.report_display_name || selectedProfile?.profile_id || "Profile";
  const topic = selectedProfile?.source_topics?.[0] || selectedProfileId || "market-news";
  const folder = scanScope === "folder" ? folderName.trim() : "";
  const folderIdValue = scanScope === "folder" ? folderId.trim() : "";
  const folderDescriptor = folder ? `"${folder}"${folderIdValue ? ` (#${folderIdValue})` : ""}` : folderIdValue ? `#${folderIdValue}` : "";
  const instruction = folderDescriptor
    ? `Scan Telegram folder ${folderDescriptor} and let AI select sources for ${selectedProfileLabel}.`
    : `Scan all Telegram channels and let AI select sources for ${selectedProfileLabel}.`;
  const assistantKey = `${selectedProfileId}\n${scanScope}\n${folder.toLowerCase()}\n${folderIdValue}\n${topic}`;
  const assistantOperationCount = result
    ? result.added_count + result.updated_count + (result.removed_count ?? 0) + (result.enabled_count ?? 0) + (result.disabled_count ?? 0)
    : 0;
  const canAssistantPreview = Boolean(selectedProfileId) && (scanScope === "all" || Boolean(folder || folderIdValue));
  const canPublicLinks = publicSources.trim().length > 0;
  const canAssistantApply =
    canAssistantPreview &&
    assistantPreviewKey === assistantKey &&
    result?.dry_run === true &&
    result.action === "assistant" &&
    assistantOperationCount > 0 &&
    !!result.resolved_plan;
  const previewSources = result?.preview_sources ?? [];

  useEffect(() => {
    if (!profileId && initialProfileId) {
      setProfileId(initialProfileId);
    }
  }, [initialProfileId, profileId]);

  const publicSourceSection = (
    <section className="source-public-links" aria-label="Public Telegram source links">
      <div>
        <strong>Known public sources</strong>
        <small>Add links, candidate JSON, or starter recommendations without scanning your Telegram folders.</small>
      </div>
      <label className="source-import-field">
        <span>Public links or candidate JSON</span>
        <textarea
          onChange={(event) => setPublicSources(event.target.value)}
          placeholder="https://t.me/example_channel&#10;@another_public_channel&#10;or public_source_candidates_v1 JSON"
          value={publicSources}
        />
      </label>
      <div className="source-import-actions source-public-actions">
        <button
          className="text-button secondary"
          disabled={busy || !canPublicLinks}
          onClick={() => void previewSourceImport(publicSources, topic).catch(() => undefined)}
          type="button"
        >
          <Eye size={15} />
          <span>Preview links</span>
        </button>
        <button
          className="text-button"
          disabled={busy || !canPublicLinks}
          onClick={() => void importSources(publicSources, topic).catch(() => undefined)}
          type="button"
        >
          <Link2 size={15} />
          <span>Add links</span>
        </button>
        <button
          className="text-button secondary"
          disabled={busy}
          onClick={() => void importStarterSources(topic).catch(() => undefined)}
          type="button"
        >
          <Sparkles size={15} />
          <span>Starter recommendations</span>
        </button>
      </div>
    </section>
  );

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
          void previewSourceAssistant(instruction, topic, true, selectedProfileId, folder || undefined, folderIdValue || undefined)
            .then((next) => {
              if (next.dry_run && next.action === "assistant") {
                setAssistantPreviewKey(assistantKey);
              }
            })
            .catch(() => undefined);
        }}
      >
        {!hasSelectableProfiles && publicSourceSection}
        {hasSelectableProfiles ? (
          <>
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
            <div className="source-scope-control" role="group" aria-label="Telegram discovery scope">
              <button
                aria-pressed={scanScope === "all"}
                onClick={() => {
                  setScanScope("all");
                  setAssistantPreviewKey("");
                }}
                type="button"
              >
                All channels
              </button>
              <button
                aria-pressed={scanScope === "folder"}
                onClick={() => {
                  setScanScope("folder");
                  setAssistantPreviewKey("");
                }}
                type="button"
              >
                Telegram folder
              </button>
            </div>
            <label className="source-import-field" data-disabled={scanScope === "all" ? "true" : "false"}>
              <span>Folder name</span>
              <input
                disabled={scanScope === "all"}
                onChange={(event) => {
                  setFolderName(event.target.value);
                  setAssistantPreviewKey("");
                }}
                placeholder="Folder name from Telegram"
                type="text"
                value={folderName}
              />
            </label>
            <label className="source-import-field" data-disabled={scanScope === "all" ? "true" : "false"}>
              <span>Folder ID</span>
              <input
                disabled={scanScope === "all"}
                inputMode="numeric"
                onChange={(event) => {
                  setFolderId(event.target.value.replace(/[^\d]/g, ""));
                  setAssistantPreviewKey("");
                }}
                placeholder="Optional numeric ID"
                type="text"
                value={folderId}
              />
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
                  void applySourceAssistant(
                    instruction,
                    topic,
                    true,
                    result?.resolved_plan,
                    selectedProfileId,
                    folder || undefined,
                    folderIdValue || undefined,
                  ).catch(() => undefined)
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
          </>
        ) : (
          <section className="source-public-links" aria-label="AI Telegram discovery locked">
            <div>
              <strong>Create a profile to unlock AI Telegram folder discovery.</strong>
              <small>Until then, use starter recommendations or known public links to build your first source list.</small>
            </div>
          </section>
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
        {hasSelectableProfiles && publicSourceSection}
      </form>
    </details>
  );
}
