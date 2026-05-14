import { useCallback, useEffect, useState } from "react";

import { errorMessage, loadDashboardState } from "../api/client";
import { emptyDashboardState } from "../domain/sanitize";
import type { DashboardState } from "../domain/types";

export const DASHBOARD_STATE_AUTO_REFRESH_MS = 15000;

type DashboardStatePollingContext = {
  busy: boolean;
  visibilityState: DocumentVisibilityState | "visible" | "hidden";
};

export function shouldPollDashboardState({ busy, visibilityState }: DashboardStatePollingContext) {
  return !busy && visibilityState === "visible";
}

export function useDashboardState({ busy = false }: { busy?: boolean } = {}) {
  const [state, setState] = useState<DashboardState>(emptyDashboardState);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    const nextState = await loadDashboardState(signal);
    setState(nextState);
    setLoadError("");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setLoadError(errorMessage(error));
      setState(emptyDashboardState);
    });
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    function loadQuietly() {
      const visibilityState = typeof document === "undefined" ? "visible" : document.visibilityState;
      if (!shouldPollDashboardState({ busy, visibilityState })) {
        return;
      }
      load().catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setLoadError(errorMessage(error));
      });
    }
    const intervalId = window.setInterval(loadQuietly, DASHBOARD_STATE_AUTO_REFRESH_MS);
    document.addEventListener("visibilitychange", loadQuietly);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", loadQuietly);
    };
  }, [busy, load]);

  return { state, refresh: () => load(), loadError };
}
