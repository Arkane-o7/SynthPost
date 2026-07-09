import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { scorePercent, relativeTime } from "../lib/formatters";

type InboxTab = "candidates" | "custom";

export const StoryInboxPage: React.FC<{
  onStorySelected?: () => void;
}> = ({ onStorySelected }) => {
  const studio = useStudio();
  const [tab, setTab] = React.useState<InboxTab>("candidates");
  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  // Custom story form state
  const [topic, setTopic] = React.useState("");
  const [customUrl, setCustomUrl] = React.useState("");
  const [manualBody, setManualBody] = React.useState("");

  const candidates = studio.candidates.filter((c) => {
    if (search && !c.title.toLowerCase().includes(search.toLowerCase()))
      return false;
    if (statusFilter && c.selection_status !== statusFilter) return false;
    return true;
  });

  const suggestedCount = studio.candidates.filter(
    (c) => c.selection_status === "suggested",
  ).length;

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError("");
      setBusy(true);
      await fn();
      await studio.refreshAll();
      return true;
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const selectForEpisode = async (
    candidate: (typeof studio.candidates)[number],
  ) => {
    const ok = await act(async () => {
      const selected =
        candidate.selection_status === "selected" && candidate.story_id
          ? candidate
          : await api.selectCandidate(
              candidate.candidate_id,
              studio.selectedEpisodeId,
            );
      studio.setSelectedStoryId(selected.story_id ?? "");
    });
    if (ok) onStorySelected?.();
  };

  return (
    <div>
      <div className="topbar">
        <div>
          <div className="topbar-kicker">SynthPost Studio</div>
          <h1>Story Inbox</h1>
        </div>
        <button
          className="btn-primary"
          disabled={busy}
          onClick={() =>
            act(() => api.startDiscovery(studio.selectedEpisodeId || undefined))
          }
        >
          {busy ? "Refreshing…" : "Refresh Discovery"}
        </button>
      </div>

      {/* Filters */}
      <div className="filter-toolbar" style={{ marginBottom: 16 }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search stories…"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="suggested">Suggested</option>
          <option value="selected">Selected</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        <button
          className={`tab-btn ${tab === "candidates" ? "tab-active" : ""}`}
          onClick={() => setTab("candidates")}
        >
          Candidates ({suggestedCount})
        </button>
        <button
          className={`tab-btn ${tab === "custom" ? "tab-active" : ""}`}
          onClick={() => setTab("custom")}
        >
          Add Custom
        </button>
      </div>

      {/* Candidates tab */}
      {tab === "candidates" && (
        <div className="stack">
          {candidates.length === 0 ? (
            <EmptyState
              icon="📭"
              title="No story candidates"
              description="Refresh discovery to pull stories from your RSS sources, or switch to the 'Add Custom' tab to enter a story manually."
            />
          ) : (
            candidates.map((c) => {
              const pct = scorePercent(c.final_score);
              const isSelected = c.selection_status === "selected";
              const isActive =
                isSelected && c.story_id === studio.selectedStoryId;
              const isRejected = c.selection_status === "rejected";

              return (
                <div
                  key={c.candidate_id}
                  className={`story-card ${isActive ? "story-selected" : ""} ${isRejected ? "story-rejected" : ""}`}
                >
                  {/* Score circle */}
                  <div
                    className={`score-circle ${
                      pct >= 80
                        ? "score-high"
                        : pct >= 60
                          ? "score-mid"
                          : "score-low"
                    }`}
                  >
                    {pct}
                  </div>

                  {/* Content */}
                  <div className="stack" style={{ gap: 8 }}>
                    <strong style={{ fontSize: 16 }}>{c.title}</strong>
                    <div className="text-muted" style={{ fontSize: 12 }}>
                      {c.source_name} · {c.category} ·{" "}
                      {relativeTime(c.published_at)}
                    </div>
                    {c.summary && (
                      <p className="text-muted" style={{ fontSize: 13 }}>
                        {c.summary.length > 200
                          ? c.summary.slice(0, 200) + "…"
                          : c.summary}
                      </p>
                    )}
                    <div className="row-tight">
                      {c.score_reasons.slice(0, 5).map((r) => (
                        <StatusBadge key={r} tone="blue">
                          {r}
                        </StatusBadge>
                      ))}
                    </div>
                    <div className="row-tight">
                      <button
                        className="btn-primary"
                        disabled={busy || !studio.selectedEpisodeId}
                        title={
                          !studio.selectedEpisodeId
                            ? "Select an episode in the sidebar first"
                            : isActive
                              ? "This story is currently open in the Command Center"
                              : isSelected
                                ? "Switch the Command Center to this selected story"
                                : "Select this story for the current episode"
                        }
                        onClick={() => selectForEpisode(c)}
                      >
                        {isActive
                          ? "Current in Command Center"
                          : isSelected
                            ? "Switch to this Story"
                            : "Select for Episode"}
                      </button>
                      <button
                        className="btn-danger"
                        disabled={busy}
                        onClick={() =>
                          act(() =>
                            api.rejectCandidate(c.candidate_id, [
                              "editor rejected",
                            ]),
                          )
                        }
                      >
                        Reject
                      </button>
                    </div>
                  </div>

                  {/* Status badge */}
                  <div>
                    <StatusBadge
                      status={isActive ? "selected" : c.selection_status}
                    >
                      {isActive ? "current" : c.selection_status}
                    </StatusBadge>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Custom tab */}
      {tab === "custom" && (
        <div className="grid grid-3" style={{ alignItems: "start" }}>
          {/* Custom topic */}
          <div className="card stack">
            <h2>Custom Topic</h2>
            <p className="text-muted" style={{ fontSize: 13 }}>
              Add a topic headline. SynthPost will try to find sources
              automatically.
            </p>
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Topic headline"
            />
            <button
              className="btn-primary"
              disabled={busy || !topic.trim()}
              onClick={() =>
                act(async () => {
                  await api.addCustomTopic({
                    episode_id: studio.selectedEpisodeId || undefined,
                    title: topic.trim(),
                  });
                  setTopic("");
                })
              }
            >
              Add Topic
            </button>
          </div>

          {/* Custom URL */}
          <div className="card stack">
            <h2>Custom URL</h2>
            <p className="text-muted" style={{ fontSize: 13 }}>
              Provide a direct URL to a news article. SynthPost will scrape and
              analyze it.
            </p>
            <input
              value={customUrl}
              onChange={(e) => setCustomUrl(e.target.value)}
              placeholder="https://…"
            />
            <button
              className="btn-primary"
              disabled={busy || !customUrl.trim()}
              onClick={() =>
                act(async () => {
                  await api.addCustomUrl({
                    episode_id: studio.selectedEpisodeId || undefined,
                    url: customUrl.trim(),
                  });
                  setCustomUrl("");
                })
              }
            >
              Add URL
            </button>
          </div>

          {/* Manual story */}
          <div className="card stack">
            <h2>Manual Story</h2>
            <p className="text-muted" style={{ fontSize: 13 }}>
              Paste source text or a story brief directly.
            </p>
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Story headline"
            />
            <textarea
              value={manualBody}
              onChange={(e) => setManualBody(e.target.value)}
              placeholder="Paste source text or story brief…"
              style={{ minHeight: 100 }}
            />
            <button
              className="btn-primary"
              disabled={busy || !manualBody.trim()}
              onClick={() =>
                act(async () => {
                  await api.addManualStory({
                    episode_id: studio.selectedEpisodeId || undefined,
                    title: topic || "Manual story",
                    body: manualBody,
                  });
                  setManualBody("");
                  setTopic("");
                })
              }
            >
              Add Manual Story
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
