import { useEffect, useState } from "react";

import {
  applySourceAssistant as applySourceAssistantRequest,
  errorMessage,
  importDeskSources,
  importStarterSources as importStarterSourcesRequest,
  loadDeskSources,
  previewDeskSourceImport,
  previewSourceAssistant as previewSourceAssistantRequest,
  removeDeskSource as removeDeskSourceRequest,
  setDeskSourceEnabled as setDeskSourceEnabledRequest,
  setDeskSourceTopics as setDeskSourceTopicsRequest,
} from "../api/client";
import type { DeskSourcesResult, SourceImportResult } from "../domain/types";

type Notice = { tone: "success" | "error"; text: string } | null;

export function useSourceSettings({
  refresh,
  setBusy,
  setNotice,
}: {
  refresh: () => Promise<void>;
  setBusy: (busy: boolean) => void;
  setNotice: (notice: Notice) => void;
}) {
  const [sourceImportResult, setSourceImportResult] = useState<SourceImportResult | null>(null);
  const [deskSources, setDeskSources] = useState<DeskSourcesResult | null>(null);
  const [deskSourcesError, setDeskSourcesError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadDeskSources(controller.signal)
      .then((sources) => {
        setDeskSources(sources);
        setDeskSourcesError(null);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setDeskSourcesError(errorMessage(error));
        }
      });
    return () => controller.abort();
  }, []);

  async function refreshDeskSources() {
    const sources = await loadDeskSources();
    setDeskSources(sources);
    setDeskSourcesError(null);
    return sources;
  }

  async function previewSourceImport(sources: string, topic: string) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await previewDeskSourceImport(sources, topic);
      setSourceImportResult(result);
      setNotice({ tone: "success", text: result.detail || result.title || "Source preview ready" });
      return result;
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
      throw error;
    } finally {
      setBusy(false);
    }
  }

  async function importSources(sources: string, topic: string) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await importDeskSources(sources, topic);
      setSourceImportResult(result);
      await refresh();
      try {
        await refreshDeskSources();
      } catch (error) {
        setDeskSourcesError(errorMessage(error));
      }
      setNotice({ tone: "success", text: result.detail || result.title || "Sources saved" });
      return result;
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
      throw error;
    } finally {
      setBusy(false);
    }
  }

  async function importStarterSources(topic: string) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await importStarterSourcesRequest(topic);
      setSourceImportResult(result);
      await refresh();
      await refreshDeskSources();
      setNotice({ tone: "success", text: result.detail || result.title || "Starter sources installed" });
      return result;
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
      throw error;
    } finally {
      setBusy(false);
    }
  }

  async function previewSourceAssistant(
    instruction: string,
    topic: string,
    confirmExternalAi = false,
    profileId?: string,
    folderName?: string,
  ) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await previewSourceAssistantRequest(instruction, topic, confirmExternalAi, profileId, folderName);
      setSourceImportResult(result);
      setNotice({ tone: "success", text: result.detail || result.title || "Source plan ready" });
      return result;
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
      throw error;
    } finally {
      setBusy(false);
    }
  }

  async function applySourceAssistant(
    instruction: string,
    topic: string,
    confirmExternalAi = false,
    resolvedPlan?: SourceImportResult["resolved_plan"],
    profileId?: string,
    folderName?: string,
  ) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await applySourceAssistantRequest(instruction, topic, confirmExternalAi, resolvedPlan, profileId, folderName);
      setSourceImportResult(result);
      await refresh();
      await refreshDeskSources();
      setNotice({ tone: "success", text: result.detail || result.title || "Source plan applied" });
      return result;
    } catch (error) {
      setNotice({ tone: "error", text: errorMessage(error) });
      throw error;
    } finally {
      setBusy(false);
    }
  }

  async function removeSource(sourceId: string) {
    setBusy(true);
    setNotice(null);
    try {
      const sources = await removeDeskSourceRequest(sourceId);
      setDeskSources(sources);
      await refresh();
      setNotice({ tone: "success", text: "Source removed" });
    } catch (error) {
      const message = errorMessage(error);
      setDeskSourcesError(message);
      setNotice({ tone: "error", text: message });
      throw error;
    } finally {
      setBusy(false);
    }
  }

  async function setSourceEnabled(sourceId: string, enabled: boolean) {
    setBusy(true);
    setNotice(null);
    try {
      const sources = await setDeskSourceEnabledRequest(sourceId, enabled);
      setDeskSources(sources);
      setDeskSourcesError(null);
      await refresh();
      setNotice({ tone: "success", text: enabled ? "Source enabled" : "Source paused" });
    } catch (error) {
      const message = errorMessage(error);
      setDeskSourcesError(message);
      setNotice({ tone: "error", text: message });
    } finally {
      setBusy(false);
    }
  }

  async function setSourceTopics(sourceId: string, topics: string[]) {
    setBusy(true);
    setNotice(null);
    try {
      const sources = await setDeskSourceTopicsRequest(sourceId, topics);
      setDeskSources(sources);
      setDeskSourcesError(null);
      await refresh();
      setNotice({ tone: "success", text: "Source topics saved" });
    } catch (error) {
      const message = errorMessage(error);
      setDeskSourcesError(message);
      setNotice({ tone: "error", text: message });
      throw error;
    } finally {
      setBusy(false);
    }
  }

  return {
    deskSources,
    deskSourcesError,
    sourceImportResult,
    refreshDeskSources,
    previewSourceImport,
    importSources,
    importStarterSources,
    previewSourceAssistant,
    applySourceAssistant,
    removeSource,
    setSourceEnabled,
    setSourceTopics,
  };
}
