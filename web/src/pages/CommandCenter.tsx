import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { EpisodeHeader } from "../components/EpisodeHeader";
import { WorkflowStepper } from "../components/WorkflowStepper";
import { NextActionCard } from "../components/NextActionCard";
import { EmptyState } from "../components/EmptyState";
import { getActiveStage, type StageKey } from "../lib/workflowUtils";

import { StoryPanel } from "../workspace/StoryPanel";
import { ResearchPanel } from "../workspace/ResearchPanel";
import { ScriptPanel } from "../workspace/ScriptPanel";
import { VisualsPanel } from "../workspace/VisualsPanel";
import { TimelinePanel } from "../workspace/TimelinePanel";
import { PreviewPanel } from "../workspace/PreviewPanel";
import { RenderPanel } from "../workspace/RenderPanel";
import { AssemblePanel } from "../workspace/AssemblePanel";

const WorkspacePanel: React.FC<{ stage: StageKey; storyId: string }> = ({
  stage,
  storyId,
}) => {
  switch (stage) {
    case "story":
      return <StoryPanel storyId={storyId} />;
    case "research":
      return <ResearchPanel storyId={storyId} />;
    case "script":
      return <ScriptPanel storyId={storyId} />;
    case "visuals":
      return <VisualsPanel storyId={storyId} />;
    case "timeline":
      return <TimelinePanel storyId={storyId} />;
    case "preview":
      return <PreviewPanel storyId={storyId} />;
    case "render":
      return <RenderPanel storyId={storyId} />;
    case "assemble":
      return <AssemblePanel storyId={storyId} />;
    default:
      return null;
  }
};

export const CommandCenter: React.FC<{
  onNavigateToInbox: () => void;
}> = ({ onNavigateToInbox }) => {
  const studio = useStudio();
  const [projectTitle, setProjectTitle] = React.useState("");
  const [episodeTitle, setEpisodeTitle] = React.useState("");

  const story = studio.candidates.find(
    (c) => c.story_id === studio.selectedStoryId,
  );
  const defaultStage = getActiveStage(story?.workflow_state);
  const [activeStage, setActiveStage] = React.useState<StageKey>(defaultStage);

  // Sync active stage when workflow state changes
  React.useEffect(() => {
    setActiveStage(getActiveStage(story?.workflow_state));
  }, [story?.workflow_state]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError("");
      await fn();
      await studio.refreshAll();
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
    }
  };

  // State A: No project
  if (!studio.selectedProjectId) {
    return (
      <div className="onboarding-card">
        <div className="card stack-lg" style={{ textAlign: "center" }}>
          <div>
            <div className="topbar-kicker">Welcome to</div>
            <h1 className="font-display" style={{ fontSize: 52, marginTop: 4 }}>
              SynthPost Studio
            </h1>
          </div>
          <p className="text-muted">
            Create your first project to begin producing news video episodes.
          </p>
          <label style={{ textAlign: "left" }}>
            Project name
            <input
              value={projectTitle}
              onChange={(e) => setProjectTitle(e.target.value)}
              placeholder="e.g. Tech Daily Briefing"
            />
          </label>
          <button
            className="btn-primary btn-lg"
            disabled={!projectTitle.trim()}
            onClick={() =>
              act(async () => {
                const p = await api.createProject(projectTitle.trim());
                studio.setSelectedProjectId(p.project_id);
                setProjectTitle("");
              })
            }
          >
            Create Project
          </button>
          {studio.projects.length > 0 && (
            <p className="text-muted" style={{ fontSize: 12 }}>
              Or select an existing project from the sidebar.
            </p>
          )}
        </div>
      </div>
    );
  }

  // State B: No episode
  if (!studio.selectedEpisodeId) {
    const project = studio.projects.find(
      (p) => p.project_id === studio.selectedProjectId,
    );
    return (
      <div className="stack-lg" style={{ maxWidth: 640 }}>
        <div>
          <div className="topbar-kicker">{project?.title ?? "Project"}</div>
          <h1 className="font-display" style={{ fontSize: 40, marginTop: 4 }}>
            Create an episode
          </h1>
        </div>
        <div className="card stack">
          <p className="text-muted">
            An episode is a single rendered news segment. Each episode contains
            one or more stories.
          </p>
          <label>
            Episode title
            <input
              value={episodeTitle}
              onChange={(e) => setEpisodeTitle(e.target.value)}
              placeholder="e.g. July 6 Briefing"
            />
          </label>
          <button
            className="btn-primary"
            disabled={!episodeTitle.trim()}
            onClick={() =>
              act(async () => {
                const ep = await api.createEpisode(
                  studio.selectedProjectId,
                  episodeTitle.trim(),
                );
                studio.setSelectedEpisodeId(ep.episode_id);
                setEpisodeTitle("");
              })
            }
          >
            Create Episode
          </button>
        </div>

        {studio.episodes.length > 0 && (
          <div className="card stack">
            <h2>Existing Episodes</h2>
            {studio.episodes.map((ep) => (
              <div key={ep.episode_id} className="row-between">
                <div>
                  <span style={{ fontWeight: 600 }}>{ep.title}</span>
                  <span
                    className="text-muted"
                    style={{ fontSize: 12, marginLeft: 8 }}
                  >
                    {ep.story_ids.length} stories · {ep.status}
                  </span>
                </div>
                <button
                  onClick={() => studio.setSelectedEpisodeId(ep.episode_id)}
                >
                  Select
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // State C: No story selected
  if (!studio.selectedStoryId || !story) {
    return (
      <div className="stack-lg">
        <EpisodeHeader story={null} />
        <WorkflowStepper
          workflowState={undefined}
          activeStage="story"
          onStageClick={() => {}}
        />
        <EmptyState
          icon="📰"
          title="Select a story to begin production"
          description="Head to the Story Inbox to discover candidates from your RSS sources, or add a custom story."
        >
          <div className="row" style={{ justifyContent: "center" }}>
            <button className="btn-primary btn-lg" onClick={onNavigateToInbox}>
              Go to Story Inbox
            </button>
          </div>
        </EmptyState>
      </div>
    );
  }

  // State D: Full production flow
  return (
    <div className="stack-lg">
      <EpisodeHeader story={story} />
      <WorkflowStepper
        workflowState={story.workflow_state}
        activeStage={activeStage}
        onStageClick={setActiveStage}
      />
      <NextActionCard
        workflowState={story.workflow_state}
        onNavigate={setActiveStage}
        onApiAction={(action) => {
          if (action === "startResearch") {
            void act(() => api.startResearch(studio.selectedStoryId));
          } else if (action === "generateScript") {
            void act(() => api.generateScript(studio.selectedStoryId));
          }
        }}
      />
      <WorkspacePanel stage={activeStage} storyId={studio.selectedStoryId} />
    </div>
  );
};
