import { Check, FileUp, Plus } from "lucide-react";
import { useState } from "react";

import { InlineEmpty } from "../common";
import type { ProfileCreateResult } from "../../domain/types";

export function NewProfilePanel({
  busy,
  createProfileFromBrief,
  latestResult,
}: {
  busy: boolean;
  createProfileFromBrief: (payload: {
    brief: string;
    source_filename?: string;
    source_text?: string;
    source_base64?: string;
  }) => Promise<ProfileCreateResult>;
  latestResult: ProfileCreateResult | null;
}) {
  const [open, setOpen] = useState(false);
  const [brief, setBrief] = useState("");
  const [filePayload, setFilePayload] = useState<{ name: string; text?: string; base64?: string } | null>(null);
  const [localError, setLocalError] = useState("");
  const hasInput = Boolean(brief.trim() || filePayload);

  async function handleFile(file: File | null) {
    setLocalError("");
    setFilePayload(null);
    if (!file) {
      return;
    }
    const suffix = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!["md", "markdown", "txt", "pdf"].includes(suffix)) {
      setLocalError("Use a Markdown, text, or PDF profile file.");
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      setLocalError("Use a file under 4 MB.");
      return;
    }
    try {
      const payload = suffix === "pdf"
        ? { name: file.name, base64: await readFileAsDataUrl(file) }
        : { name: file.name, text: await readFileAsText(file) };
      setFilePayload(payload);
    } catch {
      setLocalError("Signal Desk could not read that file.");
    }
  }

  async function submitProfile() {
    if (!hasInput || busy) {
      return;
    }
    setLocalError("");
    try {
      await createProfileFromBrief({
        brief: brief.trim(),
        source_filename: filePayload?.name,
        source_text: filePayload?.text,
        source_base64: filePayload?.base64,
      });
      setBrief("");
      setFilePayload(null);
      setOpen(false);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Profile creation failed.");
    }
  }

  return (
    <section className="new-profile-panel" data-open={open ? "true" : "false"} aria-label="Create a profile">
      <button className="new-profile-toggle" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <Plus size={15} />
        <span>New profile</span>
        <small>Paste a plain-language goal or import Markdown, text, or PDF.</small>
      </button>
      {open && (
        <div className="new-profile-body">
          <label>
            <span>What should Signal Desk watch for?</span>
            <textarea
              value={brief}
              onChange={(event) => setBrief(event.target.value)}
              disabled={busy}
              placeholder="Example: Watch for senior remote AI engineering roles, paid agent projects, or founder requests that match my background. Avoid unpaid internships and vague promos."
            />
          </label>
          <label className="new-profile-file">
            <FileUp size={15} />
            <span>{filePayload ? filePayload.name : "Attach Markdown, text, or PDF"}</span>
            <input
              type="file"
              accept=".md,.markdown,.txt,.pdf,text/markdown,text/plain,application/pdf"
              disabled={busy}
              onChange={(event) => void handleFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <div className="new-profile-actions">
            <button className="text-button profile-primary-action" type="button" disabled={busy || !hasInput} onClick={() => void submitProfile()}>
              <Check size={15} />
              <span>{busy ? "Creating" : "Create profile"}</span>
            </button>
            <button className="text-button secondary" type="button" disabled={busy} onClick={() => setOpen(false)}>
              <span>Cancel</span>
            </button>
          </div>
          <small className="new-profile-note">
            Signal Desk creates a local profile first. Review its matching rules before using it for automation.
          </small>
          {localError && <InlineEmpty title={localError} tone="error" />}
        </div>
      )}
      {!open && latestResult && (
        <div className="new-profile-result">
          <strong>{latestResult.display_name}</strong>
          <span>{latestResult.detail}</span>
        </div>
      )}
    </section>
  );
}

function readFileAsText(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
