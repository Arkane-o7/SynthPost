import React from "react";
import { api, artifactUrl } from "./api/client";
import type {
  RenderJob,
  ScriptDocument,
  TimelinePlan,
  TimelineSegment,
  VisualCandidate,
} from "./contracts";
import { StudioProvider, useStudio } from "./state/useStudio";
import "./styles/studio.css";

const stages = [
  "selected",
  "research_ready",
  "script_review",
  "script_approved",
  "visuals_review",
  "timeline_review",
  "timeline_approved",
  "rendering_composition",
  "assembling",
  "completed",
];

type Page =
  | "dashboard"
  | "sources"
  | "inbox"
  | "projects"
  | "episodes"
  | "jobs"
  | "settings";

type WorkspaceTab =
  | "story"
  | "research"
  | "script"
  | "visuals"
  | "timeline"
  | "preview"
  | "render";

function useAsyncAction() {
  const studio = useStudio();
  return async (fn: () => Promise<unknown>) => {
    try {
      studio.setError("");
      await fn();
      await studio.refreshAll();
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    }
  };
}

const Badge: React.FC<{
  children: React.ReactNode;
  tone?: "green" | "yellow" | "red";
}> = ({ children, tone }) => (
  <span className={`badge ${tone ?? ""}`}>{children}</span>
);

const JobCard: React.FC<{ job: RenderJob }> = ({ job }) => (
  <div className="job">
    <div className="row space">
      <strong>{job.job_type}</strong>
      <Badge
        tone={
          job.status === "completed"
            ? "green"
            : job.status === "failed"
              ? "red"
              : undefined
        }
      >
        {job.status}
      </Badge>
    </div>
    <div className="meta mono">{job.job_id}</div>
    <div className="progress">
      <div style={{ width: `${job.progress}%` }} />
    </div>
    <div className="meta">
      {job.stage}
      {job.error ? ` · ${job.error}` : ""}
    </div>
  </div>
);

const Sidebar: React.FC<{ page: Page; setPage: (page: Page) => void }> = ({
  page,
  setPage,
}) => {
  const studio = useStudio();
  return (
    <aside className="sidebar">
      <div className="logo-mark">
        Synth<span>Post</span>
        <br />
        Studio
      </div>
      <div className="submark">local newsroom editor</div>
      <nav className="nav">
        {(
          [
            "dashboard",
            "sources",
            "inbox",
            "projects",
            "episodes",
            "jobs",
            "settings",
          ] as Page[]
        ).map((item) => (
          <button
            key={item}
            className={page === item ? "active" : ""}
            onClick={() => setPage(item)}
          >
            {item.replace("_", " ")}
          </button>
        ))}
      </nav>
      <div className="context-selectors">
        <label>
          Project
          <select
            value={studio.selectedProjectId}
            onChange={(event) =>
              studio.setSelectedProjectId(event.target.value)
            }
          >
            <option value="">No project</option>
            {studio.projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Episode
          <select
            value={studio.selectedEpisodeId}
            onChange={(event) =>
              studio.setSelectedEpisodeId(event.target.value)
            }
          >
            <option value="">No episode</option>
            {studio.episodes.map((episode) => (
              <option key={episode.episode_id} value={episode.episode_id}>
                {episode.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Story
          <select
            value={studio.selectedStoryId}
            onChange={(event) => studio.setSelectedStoryId(event.target.value)}
          >
            <option value="">No story</option>
            {studio.candidates
              .filter((candidate) => candidate.story_id)
              .map((candidate) => (
                <option
                  key={candidate.candidate_id}
                  value={candidate.story_id ?? ""}
                >
                  {candidate.title}
                </option>
              ))}
          </select>
        </label>
      </div>
    </aside>
  );
};

const Dashboard: React.FC = () => {
  const studio = useStudio();
  const activeJobs = studio.jobs.filter((job) =>
    ["queued", "running"].includes(job.status),
  );
  const selectedCandidate = studio.candidates.find(
    (candidate) => candidate.story_id === studio.selectedStoryId,
  );
  return (
    <div className="grid three">
      <div className="card strong">
        <h3>Projects</h3>
        <h1>{studio.projects.length}</h1>
        <p className="meta">Local production projects tracked in SQLite.</p>
      </div>
      <div className="card strong">
        <h3>Episodes</h3>
        <h1>{studio.episodes.length}</h1>
        <p className="meta">
          Episode artifacts live under predictable `episodes/` paths.
        </p>
      </div>
      <div className="card strong">
        <h3>Active jobs</h3>
        <h1>{activeJobs.length}</h1>
        <p className="meta">SQLite-backed local worker queue.</p>
      </div>
      <div className="card" style={{ gridColumn: "span 2" }}>
        <h2>Current story</h2>
        {selectedCandidate ? (
          <>
            <p>{selectedCandidate.title}</p>
            <div className="workflow-strip">
              {stages.map((stage) => (
                <div
                  key={stage}
                  className={`workflow-dot ${stage === selectedCandidate.workflow_state ? "active" : ""}`}
                  title={stage}
                />
              ))}
            </div>
            <p className="meta">State: {selectedCandidate.workflow_state}</p>
          </>
        ) : (
          <div className="empty">
            Select a story from the Story Inbox or Episode Workspace.
          </div>
        )}
      </div>
      <div className="card">
        <h2>Recent jobs</h2>
        <div className="stack">
          {studio.jobs.slice(0, 4).map((job) => (
            <JobCard key={job.job_id} job={job} />
          ))}
        </div>
      </div>
    </div>
  );
};

const ProjectsPage: React.FC = () => {
  const studio = useStudio();
  const act = useAsyncAction();
  const [projectTitle, setProjectTitle] = React.useState("");
  const [episodeTitle, setEpisodeTitle] = React.useState("");
  return (
    <div className="grid two">
      <div className="card stack">
        <h2>Create project</h2>
        <input
          value={projectTitle}
          onChange={(event) => setProjectTitle(event.target.value)}
          placeholder="Project title"
        />
        <button
          className="primary"
          onClick={() =>
            act(async () => {
              const project = await api.createProject(projectTitle);
              studio.setSelectedProjectId(project.project_id);
              setProjectTitle("");
            })
          }
        >
          Create project
        </button>
      </div>
      <div className="card stack">
        <h2>Create episode</h2>
        <input
          value={episodeTitle}
          onChange={(event) => setEpisodeTitle(event.target.value)}
          placeholder="Episode title"
        />
        <button
          disabled={!studio.selectedProjectId}
          className="primary"
          onClick={() =>
            act(async () => {
              const episode = await api.createEpisode(
                studio.selectedProjectId,
                episodeTitle,
              );
              studio.setSelectedEpisodeId(episode.episode_id);
              setEpisodeTitle("");
            })
          }
        >
          Create episode
        </button>
      </div>
      <div className="card stack">
        <h2>Projects</h2>
        {studio.projects.map((project) => (
          <div key={project.project_id} className="row space">
            <span>{project.title}</span>
            <button
              onClick={() => studio.setSelectedProjectId(project.project_id)}
            >
              Select
            </button>
          </div>
        ))}
      </div>
      <div className="card stack">
        <h2>Episodes</h2>
        {studio.episodes.map((episode) => (
          <div key={episode.episode_id} className="row space">
            <span>{episode.title}</span>
            <span className="meta">{episode.story_ids.length} stories</span>
            <button
              onClick={() => studio.setSelectedEpisodeId(episode.episode_id)}
            >
              Select
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

const SourcesPage: React.FC = () => {
  const studio = useStudio();
  const act = useAsyncAction();
  const [name, setName] = React.useState("");
  const [feedUrl, setFeedUrl] = React.useState("");
  const [category, setCategory] = React.useState("technology");
  return (
    <div className="grid sidebar-main">
      <div className="card stack">
        <h2>Add RSS / Atom feed</h2>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Source name"
        />
        <input
          value={feedUrl}
          onChange={(event) => setFeedUrl(event.target.value)}
          placeholder="Feed URL"
        />
        <input
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          placeholder="Category"
        />
        <button
          className="primary"
          onClick={() =>
            act(async () => {
              await api.createSource({
                name,
                source_type: "rss",
                feed_url: feedUrl,
                category,
                custom: true,
              });
              setName("");
              setFeedUrl("");
            })
          }
        >
          Add source
        </button>
      </div>
      <div className="card stack">
        <h2>Source registry</h2>
        {studio.sources.map((source) => (
          <div
            key={source.source_id}
            className="story-card"
            style={{ gridTemplateColumns: "1fr auto" }}
          >
            <div>
              <strong>{source.name}</strong>
              <div className="meta">
                {source.category} · {source.source_type} · reliability{" "}
                {source.reliability_score}
              </div>
              <div className="meta mono">
                {source.feed_url || source.homepage_url}
              </div>
            </div>
            <div className="stack">
              <Badge tone={source.enabled ? "green" : "red"}>
                {source.enabled ? "enabled" : "disabled"}
              </Badge>
              <button
                onClick={() =>
                  act(() =>
                    api.updateSource(source.source_id, {
                      enabled: !source.enabled,
                    }),
                  )
                }
              >
                {source.enabled ? "Disable" : "Enable"}
              </button>
              <button
                onClick={() => act(() => api.testSource(source.source_id))}
              >
                Test
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const InboxPage: React.FC = () => {
  const studio = useStudio();
  const act = useAsyncAction();
  const [search, setSearch] = React.useState("");
  const [topic, setTopic] = React.useState("");
  const [manualBody, setManualBody] = React.useState("");
  const [url, setUrl] = React.useState("");
  const candidates = studio.candidates.filter(
    (candidate) =>
      !search || candidate.title.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="grid sidebar-main">
      <div className="card stack">
        <h2>Discovery controls</h2>
        <button
          className="primary"
          onClick={() =>
            act(() => api.startDiscovery(studio.selectedEpisodeId || undefined))
          }
        >
          Refresh discovery
        </button>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search candidates"
        />
        <h3>Add custom topic</h3>
        <input
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder="Topic headline"
        />
        <button
          onClick={() =>
            act(async () => {
              await api.addCustomTopic({
                episode_id: studio.selectedEpisodeId || undefined,
                title: topic,
              });
              setTopic("");
            })
          }
        >
          Add topic
        </button>
        <h3>Add URL</h3>
        <input
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://..."
        />
        <button
          onClick={() =>
            act(async () => {
              await api.addCustomUrl({
                episode_id: studio.selectedEpisodeId || undefined,
                url,
              });
              setUrl("");
            })
          }
        >
          Add URL
        </button>
        <h3>Paste manual story</h3>
        <textarea
          value={manualBody}
          onChange={(event) => setManualBody(event.target.value)}
          placeholder="Paste source text or story brief"
        />
        <button
          onClick={() =>
            act(async () => {
              await api.addManualStory({
                episode_id: studio.selectedEpisodeId || undefined,
                title: topic || "Manual story",
                body: manualBody,
              });
              setManualBody("");
            })
          }
        >
          Add manual story
        </button>
      </div>
      <div className="card stack">
        <h2>Story Inbox</h2>
        {!candidates.length ? (
          <div className="empty">
            No candidates yet. Refresh discovery or add a manual story.
          </div>
        ) : (
          candidates.map((candidate) => (
            <div key={candidate.candidate_id} className="story-card">
              <div className="score">
                {Math.round(candidate.final_score * 100)}
              </div>
              <div className="stack">
                <div className="row space">
                  <strong>{candidate.title}</strong>
                  <Badge>{candidate.selection_status}</Badge>
                </div>
                <div className="meta">
                  {candidate.source_name} · {candidate.category} ·{" "}
                  {candidate.published_at ?? "date unknown"}
                </div>
                <p className="meta">{candidate.summary}</p>
                <div className="row">
                  {candidate.score_reasons.slice(0, 5).map((reason) => (
                    <Badge key={reason}>{reason}</Badge>
                  ))}
                </div>
                <div className="row">
                  <button
                    disabled={!studio.selectedEpisodeId}
                    className="primary"
                    onClick={() =>
                      act(async () => {
                        const selected = await api.selectCandidate(
                          candidate.candidate_id,
                          studio.selectedEpisodeId,
                        );
                        studio.setSelectedStoryId(selected.story_id ?? "");
                      })
                    }
                  >
                    Select story
                  </button>
                  <button
                    className="danger"
                    onClick={() =>
                      act(() =>
                        api.rejectCandidate(candidate.candidate_id, [
                          "editor rejected",
                        ]),
                      )
                    }
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

const ResearchWorkspace: React.FC<{ storyId: string }> = ({ storyId }) => {
  const act = useAsyncAction();
  const [pack, setPack] =
    React.useState<Awaited<ReturnType<typeof api.readResearch>>>(null);
  React.useEffect(() => {
    void api
      .readResearch(storyId)
      .then(setPack)
      .catch(() => setPack(null));
  }, [storyId]);
  return (
    <div className="grid two">
      <div className="card stack">
        <h2>Research Pack</h2>
        <button
          className="primary"
          onClick={() =>
            act(async () => {
              await api.startResearch(storyId);
            })
          }
        >
          Start research job
        </button>
        {pack ? (
          <>
            <p>{pack.research_summary}</p>
            <div className="meta">
              Claims: {pack.claims.length} · Documents: {pack.documents.length}
            </div>
            {pack.uncertainties.map((warning) => (
              <Badge key={warning} tone="yellow">
                {warning}
              </Badge>
            ))}
          </>
        ) : (
          <div className="empty">No research pack yet.</div>
        )}
      </div>
      <div className="card stack">
        <h2>Claims and evidence</h2>
        {pack?.claims.map((claim) => (
          <div key={claim.claim_id} className="job">
            <strong>{claim.claim_text}</strong>
            <div className="meta">
              {claim.claim_id} · evidence {claim.evidence_ids.join(", ")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const ScriptWorkspace: React.FC<{ storyId: string }> = ({ storyId }) => {
  const act = useAsyncAction();
  const [script, setScript] = React.useState<ScriptDocument | null>(null);
  const [headline, setHeadline] = React.useState("");
  const [text, setText] = React.useState("");
  const load = React.useCallback(
    () =>
      api.readScript(storyId).then((value) => {
        setScript(value);
        setHeadline(value?.headline ?? "");
        setText(
          value?.sections.map((section) => section.text).join("\n\n") ?? "",
        );
      }),
    [storyId],
  );
  React.useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="section-editor">
      <div className="card section-list">
        <h2>Sections</h2>
        {script?.sections.map((section) => (
          <button key={section.section_id}>
            {section.section_type}
            <br />
            <small>
              {Math.round(section.estimated_duration_seconds)}s ·{" "}
              {section.approval_status}
            </small>
          </button>
        ))}
      </div>
      <div className="card stack">
        <h2>Script editor</h2>
        <input
          value={headline}
          onChange={(event) => setHeadline(event.target.value)}
          placeholder="Headline"
        />
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <div className="row">
          <button
            onClick={() =>
              act(async () => {
                await api.saveManualScript(storyId, headline, text);
                await load();
              })
            }
          >
            Save revision
          </button>
          <button onClick={() => act(() => api.generateScript(storyId))}>
            Generate with Ollama
          </button>
          <button
            className="primary"
            onClick={() =>
              act(async () => {
                await api.approveScript(storyId);
                await load();
              })
            }
          >
            Approve script
          </button>
        </div>
      </div>
      <div className="card stack">
        <h2>Warnings</h2>
        {script?.warnings?.length ? (
          script.warnings.map((warning) => (
            <Badge key={warning} tone="yellow">
              {warning}
            </Badge>
          ))
        ) : (
          <p className="meta">No script warnings loaded.</p>
        )}
        <div className="meta">
          Approved scripts are never overwritten; saving creates a new revision.
        </div>
      </div>
    </div>
  );
};

const VisualsWorkspace: React.FC<{ storyId: string }> = ({ storyId }) => {
  const act = useAsyncAction();
  const [visuals, setVisuals] = React.useState<VisualCandidate[]>([]);
  const [path, setPath] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const load = React.useCallback(
    () => api.listVisuals(storyId).then(setVisuals),
    [storyId],
  );
  React.useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="grid sidebar-main">
      <div className="card stack">
        <h2>Add visuals</h2>
        <button
          className="primary"
          onClick={() =>
            act(async () => {
              await api.searchVisuals(storyId);
              await load();
            })
          }
        >
          Search local drop folder
        </button>
        <input
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="Project-relative or absolute media path"
        />
        <button
          onClick={() =>
            act(async () => {
              await api.stageLocalVisual(storyId, {
                path,
                rights_tier: "yellow",
              });
              setPath("");
              await load();
            })
          }
        >
          Stage local path
        </button>
        <input
          type="file"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <button
          disabled={!file}
          onClick={() =>
            act(async () => {
              if (file) await api.uploadVisual(storyId, file);
              setFile(null);
              await load();
            })
          }
        >
          Upload file
        </button>
      </div>
      <div className="grid three">
        {visuals.map((visual) => (
          <div key={visual.asset_id} className="visual-card">
            <div className="visual-thumb">
              {visual.thumbnail_path ? (
                <img src={artifactUrl(visual.thumbnail_path)} />
              ) : (
                visual.media_type
              )}
            </div>
            <div className="visual-body">
              <strong>{visual.title}</strong>
              <div className="row">
                <Badge
                  tone={
                    visual.rights_tier === "green"
                      ? "green"
                      : visual.rights_tier === "red"
                        ? "red"
                        : "yellow"
                  }
                >
                  {visual.rights_tier}
                </Badge>
                <Badge>{visual.review_status}</Badge>
              </div>
              <div className="meta">
                {visual.provider} · {visual.content_role}
              </div>
              <input
                defaultValue={visual.attribution_text ?? ""}
                onBlur={(event) =>
                  void api
                    .updateVisual(visual.asset_id, {
                      attribution_text: event.target.value,
                    })
                    .then(load)
                }
              />
              <div className="row">
                <button
                  onClick={() =>
                    act(async () => {
                      await api.manualApproveVisual(
                        visual.asset_id,
                        visual.attribution_text ?? undefined,
                      );
                      await load();
                    })
                  }
                >
                  Manual approve
                </button>
                <button
                  onClick={() =>
                    act(async () => {
                      await api.rejectVisual(visual.asset_id);
                      await load();
                    })
                  }
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

function reorder<T>(items: T[], from: number, to: number): T[] {
  const copy = [...items];
  const [item] = copy.splice(from, 1);
  copy.splice(to, 0, item);
  return copy;
}

const TimelineWorkspace: React.FC<{ storyId: string }> = ({ storyId }) => {
  const act = useAsyncAction();
  const [timeline, setTimeline] = React.useState<TimelinePlan | null>(null);
  const [dragIndex, setDragIndex] = React.useState<number | null>(null);
  const load = React.useCallback(
    () => api.readTimeline(storyId).then(setTimeline),
    [storyId],
  );
  React.useEffect(() => {
    void load();
  }, [load]);
  const updateSegments = (segments: TimelineSegment[]) => {
    if (!timeline) return;
    let cursor = 0;
    const fixed = segments.map((segment) => {
      const duration = Math.max(1, Number(segment.duration));
      const next = {
        ...segment,
        start_time: Number(cursor.toFixed(3)),
        end_time: Number((cursor + duration).toFixed(3)),
        duration,
      };
      cursor += duration;
      return next;
    });
    setTimeline({ ...timeline, segments: fixed });
  };
  return (
    <div className="card stack">
      <div className="row">
        <button
          className="primary"
          onClick={() =>
            act(async () => {
              setTimeline(await api.generateTimeline(storyId));
            })
          }
        >
          Generate timeline
        </button>
        <button
          disabled={!timeline}
          onClick={() =>
            timeline &&
            act(async () => {
              const result = await api.validateTimeline(storyId, timeline);
              setTimeline({
                ...timeline,
                validation_errors: result.errors,
                validation_warnings: result.warnings,
              });
            })
          }
        >
          Validate
        </button>
        <button
          disabled={!timeline}
          onClick={() =>
            timeline &&
            act(async () => {
              await api.saveTimeline(storyId, timeline);
              await load();
            })
          }
        >
          Save draft
        </button>
        <button
          disabled={!timeline}
          className="primary"
          onClick={() =>
            act(async () => {
              await api.approveTimeline(storyId);
              await load();
            })
          }
        >
          Approve timeline
        </button>
      </div>
      {timeline ? (
        <>
          <div className="timeline">
            {timeline.segments.map((segment, index) => (
              <div
                className="timeline-row"
                key={segment.segment_id}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => {
                  if (dragIndex !== null)
                    updateSegments(
                      reorder(timeline.segments, dragIndex, index),
                    );
                  setDragIndex(null);
                }}
              >
                <div className="timeline-label">
                  {segment.start_time.toFixed(1)}–{segment.end_time.toFixed(1)}s
                </div>
                <div
                  draggable
                  onDragStart={() => setDragIndex(index)}
                  onDragEnd={() => setDragIndex(null)}
                  className={`timeline-block ${dragIndex === index ? "dragging" : ""}`}
                >
                  <strong>{segment.template.template_id}</strong>
                  <p className="meta">{segment.script_text}</p>
                </div>
                <select
                  value={segment.template.template_id}
                  onChange={(event) =>
                    updateSegments(
                      timeline.segments.map((item, itemIndex) =>
                        itemIndex === index
                          ? {
                              ...item,
                              template: {
                                ...item.template,
                                template_id: event.target.value,
                              },
                            }
                          : item,
                      ),
                    )
                  }
                >
                  {[
                    "split_anchor_visual",
                    "fullscreen_news_visual",
                    "fullscreen_anchor",
                    "quote_card",
                    "document_callout",
                    "chart_explainer",
                    "map_explainer",
                    "timeline_explainer",
                    "comparison_card",
                    "bullet_summary",
                    "source_screenshot",
                    "fallback_context_card",
                  ].map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  value={segment.duration}
                  onChange={(event) =>
                    updateSegments(
                      timeline.segments.map((item, itemIndex) =>
                        itemIndex === index
                          ? { ...item, duration: Number(event.target.value) }
                          : item,
                      ),
                    )
                  }
                />
              </div>
            ))}
          </div>
          {timeline.validation_errors?.map((error) => (
            <Badge key={error} tone="red">
              {error}
            </Badge>
          ))}
          {timeline.validation_warnings?.map((warning) => (
            <Badge key={warning} tone="yellow">
              {warning}
            </Badge>
          ))}
        </>
      ) : (
        <div className="empty">No timeline yet.</div>
      )}
    </div>
  );
};

const PreviewWorkspace: React.FC<{ storyId: string }> = ({ storyId }) => {
  const act = useAsyncAction();
  const [manifest, setManifest] = React.useState<Record<
    string,
    unknown
  > | null>(null);
  const composition = manifest?.composition as
    | { preview_path?: string; output_path?: string }
    | undefined;
  return (
    <div className="grid two">
      <div className="card stack">
        <h2>Preview from retained renderer</h2>
        <button
          onClick={() =>
            act(async () => {
              setManifest(await api.buildManifest(storyId, "preview", true));
            })
          }
        >
          Build renderer manifest
        </button>
        <button
          className="primary"
          onClick={() => act(() => api.renderStory(storyId, "preview", true))}
        >
          Render preview/story
        </button>
        <p className="meta">
          Preview artifacts are produced by the same Remotion composition used
          for final rendering, not a separate mock preview.
        </p>
      </div>
      <div className="card">
        <div className="preview-frame">
          {composition?.preview_path ? (
            <img src={artifactUrl(composition.preview_path)} />
          ) : (
            <span className="meta">Build/render to see preview.png</span>
          )}
        </div>
        <div className="meta mono">{composition?.output_path}</div>
      </div>
    </div>
  );
};

const RenderWorkspace: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const act = useAsyncAction();
  return (
    <div className="grid two">
      <div className="card stack">
        <h2>Final render controls</h2>
        <button
          onClick={() => act(() => api.renderAvatar(storyId, "preview", true))}
        >
          Render avatar TEST_MODE
        </button>
        <button
          onClick={() => act(() => api.renderStory(storyId, "preview", true))}
        >
          Render story TEST_MODE
        </button>
        <button
          className="primary"
          disabled={!studio.selectedEpisodeId}
          onClick={() =>
            act(() =>
              api.assembleEpisode(studio.selectedEpisodeId, "preview", true),
            )
          }
        >
          Assemble episode TEST_MODE
        </button>
        <p className="meta">
          Final production rendering is blocked server-side by
          script/timeline/rights validation before manifest build.
        </p>
      </div>
      <div className="card stack">
        <h2>Render jobs</h2>
        {studio.jobs.slice(0, 8).map((job) => (
          <JobCard key={job.job_id} job={job} />
        ))}
      </div>
    </div>
  );
};

const EpisodeWorkspace: React.FC = () => {
  const studio = useStudio();
  const [tab, setTab] = React.useState<WorkspaceTab>("story");
  const story = studio.candidates.find(
    (candidate) => candidate.story_id === studio.selectedStoryId,
  );
  if (!studio.selectedStoryId || !story)
    return (
      <div className="empty">
        Select a story from the sidebar or Story Inbox.
      </div>
    );
  return (
    <div className="stack">
      <div className="card strong">
        <div className="row space">
          <div>
            <h2>{story.title}</h2>
            <div className="meta">
              {story.source_name} · {story.workflow_state}
            </div>
          </div>
          <Badge>{story.selection_status}</Badge>
        </div>
        <div className="workflow-strip" style={{ marginTop: 14 }}>
          {stages.map((stage) => (
            <div
              key={stage}
              className={`workflow-dot ${stage === story.workflow_state ? "active" : ""}`}
              title={stage}
            />
          ))}
        </div>
      </div>
      <div className="tabs">
        {(
          [
            "story",
            "research",
            "script",
            "visuals",
            "timeline",
            "preview",
            "render",
          ] as WorkspaceTab[]
        ).map((item) => (
          <button
            key={item}
            className={tab === item ? "active" : ""}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </div>
      {tab === "story" && (
        <div className="card">
          <h2>Story source</h2>
          <p>{story.summary || story.manual_body}</p>
          <div className="meta mono">{story.canonical_url}</div>
        </div>
      )}
      {tab === "research" && (
        <ResearchWorkspace storyId={studio.selectedStoryId} />
      )}
      {tab === "script" && <ScriptWorkspace storyId={studio.selectedStoryId} />}
      {tab === "visuals" && (
        <VisualsWorkspace storyId={studio.selectedStoryId} />
      )}
      {tab === "timeline" && (
        <TimelineWorkspace storyId={studio.selectedStoryId} />
      )}
      {tab === "preview" && (
        <PreviewWorkspace storyId={studio.selectedStoryId} />
      )}
      {tab === "render" && <RenderWorkspace storyId={studio.selectedStoryId} />}
    </div>
  );
};

const JobsPage: React.FC = () => {
  const studio = useStudio();
  const act = useAsyncAction();
  return (
    <div className="card stack">
      <h2>Render and pipeline jobs</h2>
      {studio.jobs.map((job) => (
        <div key={job.job_id} className="job">
          <JobCard job={job} />
          <div className="row">
            <button onClick={() => act(() => api.retryJob(job.job_id))}>
              Retry
            </button>
            <button onClick={() => act(() => api.cancelJob(job.job_id))}>
              Cancel
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

const SettingsPage: React.FC = () => (
  <div className="grid two">
    <div className="card stack">
      <h2>Local AI</h2>
      <p className="meta">
        Backend uses environment variables: SYNTHPOST_LLM_PROVIDER,
        SYNTHPOST_OLLAMA_BASE_URL, SYNTHPOST_OLLAMA_MODEL,
        SYNTHPOST_OLLAMA_TIMEOUT, SYNTHPOST_OLLAMA_TEMPERATURE.
      </p>
    </div>
    <div className="card stack">
      <h2>Renderer</h2>
      <p className="meta">
        Retained renderer lives in compositor/remotion_renderer. Avatar Engine
        remains external and is invoked through pipeline/direction/avatar.py.
      </p>
    </div>
  </div>
);

const Main: React.FC = () => {
  const [page, setPage] = React.useState<Page>("dashboard");
  const studio = useStudio();
  const title =
    page === "inbox" ? "Story Inbox" : page === "jobs" ? "Render Jobs" : page;
  return (
    <div className="app-shell">
      <Sidebar page={page} setPage={setPage} />
      <main className="main">
        <div className="topbar">
          <div>
            <div className="kicker">SynthPost V2</div>
            <h1>{title}</h1>
          </div>
          <button onClick={() => void studio.refreshAll()}>Refresh</button>
        </div>
        {studio.error && <div className="error">{studio.error}</div>}
        {studio.loading ? (
          <div className="empty">Loading Studio state from SQLite…</div>
        ) : (
          <>
            {page === "dashboard" && <Dashboard />}
            {page === "sources" && <SourcesPage />}
            {page === "inbox" && <InboxPage />}
            {page === "projects" && <ProjectsPage />}
            {page === "episodes" && <EpisodeWorkspace />}
            {page === "jobs" && <JobsPage />}
            {page === "settings" && <SettingsPage />}
          </>
        )}
      </main>
    </div>
  );
};

export default function App() {
  return (
    <StudioProvider>
      <Main />
    </StudioProvider>
  );
}
