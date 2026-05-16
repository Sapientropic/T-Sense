import { useEffect, useState } from "react";
import { Database } from "lucide-react";

import { InlineEmpty } from "../common";
import type { DeskSourcesResult, SourceStat } from "../../domain/types";
import {
  SOURCE_LIBRARY_PAGE_SIZE,
  filterDeskSourcesByQuery,
  paginatedDeskSources,
  sourceLibraryActivityLabel,
  sourceLibraryCountLabel,
} from "./source-library-model";
import { SourceLibraryRow } from "./source-library-row";

export {
  SOURCE_LIBRARY_PAGE_SIZE,
  filterDeskSourcesByQuery,
  paginatedDeskSources,
  sourceLibraryActivityLabel,
  sourceLibraryCountLabel,
  sourceTopicsEditState,
} from "./source-library-model";

export function SourceLibraryPanel({
  library,
  error,
  busy,
  removeSource,
  setSourceEnabled,
  setSourceTopics,
  sourceStats,
}: {
  library: DeskSourcesResult | null;
  error: string | null;
  busy: boolean;
  removeSource: (sourceId: string) => Promise<void>;
  setSourceEnabled: (sourceId: string, enabled: boolean) => Promise<void>;
  setSourceTopics: (sourceId: string, topics: string[]) => Promise<void>;
  sourceStats: SourceStat[];
}) {
  const sources = library?.sources ?? [];
  const isLoading = !library && !error;
  const [query, setQuery] = useState("");
  const [selectedTopic, setSelectedTopic] = useState("");
  const [showAllTopics, setShowAllTopics] = useState(false);
  const [showSourceList, setShowSourceList] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [visibleCount, setVisibleCount] = useState(SOURCE_LIBRARY_PAGE_SIZE);
  const filteredSources = filterDeskSourcesByQuery(sources, query, selectedTopic);
  const visibleSources = paginatedDeskSources(filteredSources, visibleCount);
  const hiddenSourceCount = Math.max(0, filteredSources.length - visibleSources.length);
  const topics = library?.topics ?? [];
  const topicPreview = showAllTopics ? topics : topics.slice(0, 12);
  const hiddenTopicCount = Math.max(0, topics.length - topicPreview.length);
  const hasFilters = Boolean(query.trim() || selectedTopic);
  const listVisible = showSourceList || hasFilters;
  const managementOpen = libraryOpen || hasFilters || showSourceList || isLoading || Boolean(error) || !sources.length;
  const activityLabel = sourceLibraryActivityLabel(sourceStats);
  const pausedCount = Math.max(0, (library?.source_count ?? sources.length) - (library?.enabled_count ?? sources.length));
  const countLabel = listVisible
    ? sourceLibraryCountLabel(visibleSources.length, filteredSources.length, hasFilters)
    : library
      ? `${library.enabled_count} tracked · ${pausedCount} paused · ${library.source_count} saved`
      : `${filteredSources.length} saved; search or manage when needed`;
  useEffect(() => {
    if (selectedTopic && !sources.some((source) => source.topics.includes(selectedTopic))) {
      setSelectedTopic("");
    }
  }, [selectedTopic, sources]);
  useEffect(() => {
    setVisibleCount(SOURCE_LIBRARY_PAGE_SIZE);
  }, [query, selectedTopic, library?.source_count]);
  return (
    <div className="table-section source-library-panel">
      <details
        className="source-library-details"
        onToggle={(event) => setLibraryOpen(event.currentTarget.open)}
        open={managementOpen}
      >
        <summary>
          <span className="panel-title">
            <Database size={18} />
            Saved Sources
          </span>
          <strong>{library?.source_count ?? sources.length}</strong>
          <small>{sources.length ? activityLabel || "Open to search or manage" : "No saved sources yet"}</small>
        </summary>
        {error && (
          <div className="source-library-error" role="status">
            <strong>Saved sources need a refresh</strong>
            <span>{error}</span>
          </div>
        )}
        {library && (
          <div className="source-library-summary" aria-label="Saved source summary">
            <span>
              <strong>{library.enabled_count}</strong>
              active
            </span>
            <span>
              <strong>{library.source_count - library.enabled_count}</strong>
              paused
            </span>
            <div className="source-library-topics" aria-label="Filter saved sources by topic" title={library.topics.join(", ")}>
              {topicPreview.length ? (
                <>
                  {topicPreview.map((topic) => (
                    <button
                      aria-pressed={selectedTopic === topic}
                      key={topic}
                      onClick={() => setSelectedTopic(selectedTopic === topic ? "" : topic)}
                      type="button"
                    >
                      {topic}
                    </button>
                  ))}
                  {(hiddenTopicCount > 0 || showAllTopics) && (
                    <button
                      aria-expanded={showAllTopics}
                      className="topic-overflow-toggle"
                      onClick={() => setShowAllTopics((current) => !current)}
                      type="button"
                    >
                      {showAllTopics ? "Show fewer" : `+${hiddenTopicCount}`}
                    </button>
                  )}
                </>
              ) : (
                <small>No topics yet</small>
              )}
            </div>
          </div>
        )}
        {sources.length > 0 && (
          <div className="source-library-search">
            <label htmlFor="source-library-query">Find source</label>
            <input
              id="source-library-query"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="@remote_jobs or jobs"
              type="search"
              value={query}
            />
            <small aria-live="polite">
              {countLabel}
            </small>
            {hasFilters && (
              <button
                className="text-button secondary source-library-clear"
                onClick={() => {
                  setQuery("");
                  setSelectedTopic("");
                }}
                type="button"
              >
                Clear filters
              </button>
            )}
          </div>
        )}
        {isLoading ? (
          <InlineEmpty title="Loading saved sources" />
        ) : sources.length && !listVisible ? (
          <div className="source-library-gate" aria-label="Saved source list collapsed">
            <div>
              <strong>{library?.source_count ?? sources.length} saved sources</strong>
              <span>Use search for one source, or open the list only when you need bulk cleanup.</span>
            </div>
            <button
              className="text-button secondary"
              onClick={() => setShowSourceList(true)}
              type="button"
            >
              Show first {SOURCE_LIBRARY_PAGE_SIZE}
            </button>
          </div>
        ) : sources.length ? (
          <div className="source-library-list">
            {visibleSources.map((source) => (
              <SourceLibraryRow
                busy={busy}
                key={source.source_id}
                removeSource={removeSource}
                setSourceEnabled={setSourceEnabled}
                setSourceTopics={setSourceTopics}
                source={source}
              />
            ))}
            {!filteredSources.length && <InlineEmpty title="No saved source matches" />}
            {hiddenSourceCount > 0 && (
              <button
                className="text-button secondary source-library-more"
                onClick={() => setVisibleCount((count) => count + SOURCE_LIBRARY_PAGE_SIZE)}
                type="button"
              >
                <span>Load 8 more</span>
                <small>{hiddenSourceCount} remaining</small>
              </button>
            )}
          </div>
        ) : (
          !error && <InlineEmpty title="No saved sources yet" />
        )}
      </details>
    </div>
  );
}
