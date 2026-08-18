import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { scorePercent, relativeTime } from "../lib/formatters";

type InboxTab = "candidates" | "custom";
type DeskFilter = "recommended" | "global_watch" | "rejected" | "all";

const assignmentLane = (candidate: {
  assignment_lane?: string | null;
  editorial_fit?: { eligible?: boolean } | null;
}) =>
  candidate.assignment_lane ||
  (candidate.editorial_fit?.eligible ? "recommended" : "unassessed");

export const StorySelectionPanel: React.FC = () => {
  const studio = useStudio();
  const autoStartedEpisodes = React.useRef(new Set<string>());
  const [tab, setTab] = React.useState<InboxTab>("candidates");
  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");
  const [deskFilter, setDeskFilter] = React.useState<DeskFilter>("all");
  const [busy, setBusy] = React.useState(false);
  const discoveryCategory = studio.projects.find(
    (project) => project.project_id === studio.selectedProjectId,
  )?.default_category;
  const episodeDiscoveryJobs = studio.jobs.filter(
    (job) =>
      job.job_type === "discovery" &&
      job.episode_id === studio.selectedEpisodeId,
  );
  const activeDiscovery = episodeDiscoveryJobs.find((job) =>
    ["queued", "running"].includes(job.status),
  );
  const hasDiscoveryAttempt = episodeDiscoveryJobs.length > 0;

  // Custom story form state
  const [topic, setTopic] = React.useState("");
  const [customUrl, setCustomUrl] = React.useState("");
  const [manualBody, setManualBody] = React.useState("");

  const candidates = studio.candidates.filter((c) => {
    if (search && !c.title.toLowerCase().includes(search.toLowerCase()))
      return false;
    if (statusFilter && c.selection_status !== statusFilter) return false;
    const lane = assignmentLane(c);
    if (deskFilter !== "all" && lane !== deskFilter) return false;
    return true;
  });

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

  React.useEffect(() => {
    const episodeId = studio.selectedEpisodeId;
    if (
      !episodeId ||
      studio.candidates.length > 0 ||
      activeDiscovery ||
      hasDiscoveryAttempt ||
      autoStartedEpisodes.current.has(episodeId)
    ) {
      return;
    }
    autoStartedEpisodes.current.add(episodeId);
    void act(() => api.startDiscovery(episodeId, discoveryCategory));
  }, [
    studio.selectedEpisodeId,
    studio.candidates.length,
    activeDiscovery,
    hasDiscoveryAttempt,
    discoveryCategory,
  ]);

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
  };

  return (
    <div className="story-selection-stage">
      {activeDiscovery && (
        <div className="story-discovery-live" role="status">
          <span className="story-discovery-pulse" aria-hidden="true" />
          <div>
            <strong>Building this episode’s story list</strong>
            <p>{activeDiscovery.stage}</p>
          </div>
          <b>{Math.round(activeDiscovery.progress)}%</b>
        </div>
      )}

      {/* Filters */}
      <div className="filter-toolbar story-selection-filters" style={{ marginBottom: 16 }}>
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
          value={deskFilter}
          aria-label="Assignment desk lane"
          onChange={(e) => setDeskFilter(e.target.value as DeskFilter)}
        >
          <option value="recommended">Recommended</option>
          <option value="global_watch">Global watch</option>
          <option value="rejected">Filtered out</option>
          <option value="all">All desk lanes</option>
        </select>
        <button
          type="button"
          className="story-refresh-button"
          disabled={busy || Boolean(activeDiscovery)}
          onClick={() =>
            void act(() =>
              api.startDiscovery(
                studio.selectedEpisodeId || undefined,
                discoveryCategory,
              ),
            )
          }
        >
          {activeDiscovery ? "Discovering…" : busy ? "Refreshing…" : "Refresh Stories"}
        </button>
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        <button
          className={`tab-btn ${tab === "candidates" ? "tab-active" : ""}`}
          onClick={() => setTab("candidates")}
        >
          Candidates ({studio.candidates.length})
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
              icon={activeDiscovery ? "⌁" : "📭"}
              title={activeDiscovery ? "Finding current stories…" : "No story candidates"}
              description={
                activeDiscovery
                  ? "Synthea is scanning this channel's enabled feeds, identifying genuinely new entries, and ranking the strongest candidates for this episode."
                  : "Refresh discovery to pull stories from your RSS sources, or switch to the 'Add Custom' tab to enter a story manually."
              }
            />
          ) : (
            candidates.map((c) => {
              const hasFit = Boolean(c.editorial_fit?.reasons?.length);
              const pct = scorePercent(c.final_score);
              const lane = assignmentLane(c);
              const isSelected = c.selection_status === "selected";
              const isActive =
                isSelected && c.story_id === studio.selectedStoryId;
              const isRejected = c.selection_status === "rejected";

              return (
                <div
                  key={c.candidate_id}
                  className={`story-card editorial-story-card ${isActive ? "story-selected" : ""} ${isRejected ? "story-rejected" : ""} ${lane === "rejected" ? "story-off-charter" : ""}`}
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
                    <small>desk</small>
                  </div>

                  {/* Content */}
                  <div className="stack" style={{ gap: 8 }}>
                    <div className="editorial-story-heading">
                      <strong>{c.title}</strong>
                      <span className={`fit-verdict desk-lane desk-lane-${lane}`}>
                        {lane.replace(/_/g, " ")}
                      </span>
                    </div>
                    <div className="text-muted" style={{ fontSize: 12 }}>
                      {c.source_name} · {c.category} ·{" "}
                      {relativeTime(c.published_at)}
                    </div>
                    {hasFit && (
                      <div className="editorial-fit-meta">
                        <span>{c.editorial_fit.primary_topic.replace(/_/g, " ")}</span>
                        <span>India impact confidence {Math.round(c.editorial_fit.india_impact_confidence * 100)}%</span>
                        <span>{c.cluster_size} article{c.cluster_size === 1 ? "" : "s"} · {c.supporting_sources.length || 1} source{(c.supporting_sources.length || 1) === 1 ? "" : "s"}</span>
                        <span>Evidence {Math.round(c.evidence_score * 100)}%</span>
                        <span>{c.recommended_format.replace(/_/g, " ")}</span>
                        <span>Charter {c.editorial_fit.charter_version}</span>
                      </div>
                    )}
                    {c.editorial_fit?.india_impact && (
                      <p className="assignment-india-impact">
                        <strong>India consequence to verify:</strong> {c.editorial_fit.india_impact}
                      </p>
                    )}
                    {c.assignment_summary && (
                      <p className="assignment-desk-summary">{c.assignment_summary}</p>
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
                                : lane !== "recommended"
                                  ? "Editorial override: select an off-charter story"
                                  : "Select this story for the current episode"
                        }
                        onClick={() => selectForEpisode(c)}
                      >
                        {isActive
                          ? "Current in Command Center"
                          : isSelected
                            ? "Switch to this Story"
                            : lane !== "recommended"
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
              Add a topic headline. Synthea will try to find sources
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
              Provide a direct URL to a news article. Synthea will scrape and
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
