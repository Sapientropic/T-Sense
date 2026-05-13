import { ExternalLink } from "lucide-react";

import type { DeskActionResult } from "../../domain/types";

export function JourneyResults({ actionIds, results }: { actionIds: string[]; results: Record<string, DeskActionResult> }) {
  const visibleResults = actionIds.map((actionId) => results[actionId]).filter(Boolean);
  if (!visibleResults.length) {
    return null;
  }
  return (
    <div className="journey-results" aria-label="Recent Desk results">
      {visibleResults.map((result) => (
        <div className={`journey-result is-${result.status}`} key={result.action_id}>
          <strong>{result.title}</strong>
          {result.detail && <span>{result.detail}</span>}
          {result.artifact_path && (
            <a href={artifactHref(result.artifact_path)} target="_blank" rel="noreferrer">
              <ExternalLink size={14} />
              <span>Open result</span>
            </a>
          )}
          {result.next_action && <em>{result.next_action}</em>}
        </div>
      ))}
    </div>
  );
}

function artifactHref(path: string) {
  const clean = path.replace(/^\/+/, "");
  return `/artifacts/${clean.split("/").map(encodeURIComponent).join("/")}`;
}
