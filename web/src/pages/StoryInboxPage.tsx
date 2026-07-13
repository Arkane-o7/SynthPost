import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { scorePercent, relativeTime } from "../lib/formatters";

type InboxTab = "candidates" | "custom";
type FitFilter = "charter" | "off_charter" | "all";

export const StoryInboxPage: React.FC<{
  onStorySelected?: () => void;
}> = ({ onStorySelected }) => {
  const studio = useStudio();
  const [tab, setTab] = React.useState<InboxTab>("candidates");
  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");
  const [fitFilter, setFitFilter] = React.useState<FitFilter>("charter");
  const [busy, setBusy] = React.useState(false);

  // Custom story form state
  const [topic, setTopic] = React.useState("");
  const [customUrl, setCustomUrl] = React.useState("");
  const [manualBody, setManualBody] = React.useState("");

  const candidates = studio.candidates.filter((c) => {
    if (search && !c.title.toLowerCase().includes(search.toLowerCase()))
      return false;
    if (statusFilter && c.selection_status !== statusFilter) return false;
    const assessed = c.editorial_fit?.reasons?.length > 0;
    if (fitFilter === "charter" && assessed && !c.editorial_fit.eligible)
      return false;
    if (fitFilter === "off_charter" && (!assessed || c.editorial_fit.eligible))
      return false;
    return true;
  });

  const suggestedCount = studio.candidates.filter(
    (c) => c.selection_status === "suggested",
  ).length;
  const charterCount = studio.candidates.filter(
    (c) => c.editorial_fit?.eligible,
  ).length;
  const offCharterCount = studio.candidates.filter(
    (c) => c.editorial_fit?.reasons?.length && !c.editorial_fit.eligible,
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

      <section className="editorial-charter-strip">
        <div>
          <span className="editorial-charter-kicker">Global assignment desk · charter v1.1</span>
          <strong>Global shifts. India consequences.</strong>
          <p>
            Technology, AI, science, business, infrastructure and geopolitical power—selected
            for global consequence and a concrete India angle. Local crime, ceremonies,
            appointments and routine political churn are filtered out.
          </p>
        </div>
        <div className="editorial-charter-counts" aria-label="Editorial fit summary">
          <span><b>{charterCount}</b> on charter</span>
          <span><b>{offCharterCount}</b> filtered out</span>
        </div>
      </section>

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
        <select
          value={fitFilter}
          aria-label="Editorial fit"
          onChange={(e) => setFitFilter(e.target.value as FitFilter)}
        >
          <option value="charter">On-charter first</option>
          <option value="off_charter">Off-charter review</option>
          <option value="all">All editorial states</option>
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
              const hasFit = Boolean(c.editorial_fit?.reasons?.length);
              const pct = scorePercent(
                hasFit ? c.editorial_fit.score : c.final_score,
              );
              const isSelected = c.selection_status === "selected";
              const isActive =
                isSelected && c.story_id === studio.selectedStoryId;
              const isRejected = c.selection_status === "rejected";

              return (
                <div
                  key={c.candidate_id}
                  className={`story-card editorial-story-card ${isActive ? "story-selected" : ""} ${isRejected ? "story-rejected" : ""} ${hasFit && !c.editorial_fit.eligible ? "story-off-charter" : ""}`}
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
                    <span>{pct}</span>
                    <small>{hasFit ? "fit" : "rank"}</small>
                  </div>

                  {/* Content */}
                  <div className="stack" style={{ gap: 8 }}>
                    <div className="editorial-story-heading">
                      <strong>{c.title}</strong>
                      {hasFit && (
                        <span className={c.editorial_fit.eligible ? "fit-verdict fit-verdict-on" : "fit-verdict fit-verdict-off"}>
                          {c.editorial_fit.eligible ? "On charter" : "Off charter"}
                        </span>
                      )}
                    </div>
                    <div className="text-muted" style={{ fontSize: 12 }}>
                      {c.source_name} · {c.category} ·{" "}
                      {relativeTime(c.published_at)}
                    </div>
                    {hasFit && (
                      <div className="editorial-fit-meta">
                        <span>{c.editorial_fit.primary_topic.replace(/_/g, " ")}</span>
                        <span>India angle {Math.round(c.editorial_fit.india_relevance * 100)}%</span>
                        <span>Charter {c.editorial_fit.charter_version}</span>
                      </div>
                    )}
                    {c.summary && (
                      <p className="text-muted" style={{ fontSize: 13 }}>
                        {c.summary.length > 200
                          ? c.summary.slice(0, 200) + "…"
                          : c.summary}
                      </p>
                    )}
                    {hasFit ? (
                      <div className="editorial-fit-reasons">
                        {c.editorial_fit.strengths.slice(0, 4).map((reason) => (
                          <span key={reason} className="fit-reason fit-reason-positive">✓ {reason}</span>
                        ))}
                        {c.editorial_fit.penalties.map((reason) => (
                          <span key={reason} className="fit-reason fit-reason-negative">× {reason}</span>
                        ))}
                      </div>
                    ) : (
                      <div className="row-tight">
                        {c.score_reasons.slice(0, 4).map((r) => (
                          <StatusBadge key={r} tone="blue">{r}</StatusBadge>
                        ))}
                      </div>
                    )}
                    {hasFit && (
                      <details className="editorial-fit-details">
                        <summary>Why the assignment desk scored it this way</summary>
                        <div>
                          {c.editorial_fit.reasons.map((reason) => <p key={reason}>{reason}</p>)}
                        </div>
                      </details>
                    )}
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
                                : hasFit && !c.editorial_fit.eligible
                                  ? "Editorial override: select an off-charter story"
                                  : "Select this story for the current episode"
                        }
                        onClick={() => selectForEpisode(c)}
                      >
                        {isActive
                          ? "Current in Command Center"
                          : isSelected
                            ? "Switch to this Story"
                            : hasFit && !c.editorial_fit.eligible
                              ? "Select with Override"
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
