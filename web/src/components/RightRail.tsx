import React from "react";
import { useStudio } from "../state/useStudio";
import { MiniJobCard } from "./InlineJobCard";
import { relativeTime } from "../lib/formatters";
import { api } from "../api/client";
import type {
  RenderJob,
  ScriptDocument,
  TimelinePlan,
  VisualCandidate,
} from "../contracts";

export const RightRail: React.FC = () => {
  const studio = useStudio();

  const story = studio.candidates.find(
    (c) => c.story_id === studio.selectedStoryId,
  );
  const currentEpisodeId = story?.episode_id ?? studio.selectedEpisodeId;
  const isCurrentContextJob = (job: RenderJob) => {
    if (studio.selectedStoryId) {
      if (job.story_id) return job.story_id === studio.selectedStoryId;
      if (job.episode_id) return job.episode_id === currentEpisodeId;
      return false;
    }
    if (currentEpisodeId) return job.episode_id === currentEpisodeId;
    return true;
  };
  const contextJobs = studio.jobs.filter(isCurrentContextJob);
  const activeJobs = contextJobs.filter((j) =>
    ["queued", "running"].includes(j.status),
  );
  const recentJobs = contextJobs.slice(0, 5);
  const [script, setScript] = React.useState<ScriptDocument | null>(null);
  const [visuals, setVisuals] = React.useState<VisualCandidate[]>([]);
  const [timeline, setTimeline] = React.useState<TimelinePlan | null>(null);

  React.useEffect(() => {
    if (!studio.selectedStoryId) {
      setScript(null);
      setVisuals([]);
      setTimeline(null);
      return;
    }
    let cancelled = false;
    void Promise.all([
      api.readScript(studio.selectedStoryId).catch(() => null),
      api.listVisuals(studio.selectedStoryId).catch(() => []),
      api.readTimeline(studio.selectedStoryId).catch(() => null),
    ]).then(([nextScript, nextVisuals, nextTimeline]) => {
      if (cancelled) return;
      setScript(nextScript);
      setVisuals(nextVisuals);
      setTimeline(nextTimeline);
    });
    return () => {
      cancelled = true;
    };
  }, [
    studio.selectedStoryId,
    story?.workflow_state,
    studio.jobs.length,
    studio.lastJobEventTimestamp,
  ]);

  const blockers: string[] = [];
  if (story) {
    if (
      !script &&
      ["selected", "research_ready"].includes(story.workflow_state ?? "")
    ) {
      blockers.push("No script is ready yet");
    } else if (script && script.status !== "approved") {
      blockers.push("Script awaiting approval");
    }

    const unapprovedVisuals = visuals.filter(
      (visual) =>
        !["approved", "manual_approved", "rejected", "blocked"].includes(
          visual.review_status,
        ),
    );
    const redVisuals = visuals.filter(
      (visual) =>
        visual.rights_tier === "red" &&
        !["rejected", "blocked"].includes(visual.review_status),
    );
    const yellowVisuals = visuals.filter(
      (visual) =>
        visual.rights_tier === "yellow" &&
        !["manual_approved", "rejected", "blocked"].includes(
          visual.review_status,
        ),
    );
    if (unapprovedVisuals.length > 0) {
      blockers.push(
        `${unapprovedVisuals.length} visual${unapprovedVisuals.length === 1 ? "" : "s"} awaiting approval`,
      );
    }
    if (redVisuals.length > 0) {
      blockers.push(
        `${redVisuals.length} red-rights visual${redVisuals.length === 1 ? "" : "s"} need rejection or replacement`,
      );
    }
    if (yellowVisuals.length > 0) {
      blockers.push(
        `${yellowVisuals.length} yellow-rights visual${yellowVisuals.length === 1 ? "" : "s"} need manual rights approval`,
      );
    }

    if (timeline) {
      if (timeline.validation_errors?.length) {
        blockers.push(
          `${timeline.validation_errors.length} timeline validation error${timeline.validation_errors.length === 1 ? "" : "s"}`,
        );
      }
      if (
        timeline.status !== "approved" &&
        [
          "timeline_review",
          "timeline_approved",
          "rendering_composition",
          "assembling",
        ].includes(story.workflow_state ?? "")
      ) {
        blockers.push("Timeline awaiting approval");
      }
    } else if (
      [
        "timeline_review",
        "timeline_approved",
        "rendering_composition",
        "assembling",
      ].includes(story.workflow_state ?? "")
    ) {
      blockers.push("No timeline found for this story");
    }
  }
  const failedJobs = contextJobs.filter((job) => {
    if (job.status !== "failed") return false;
    const failureTime =
      job.updated_at ?? job.completed_at ?? job.created_at ?? "";
    const recovered = contextJobs.some((other) => {
      if (other.status !== "completed") return false;
      const otherTime =
        other.updated_at ?? other.completed_at ?? other.created_at ?? "";
      if (otherTime <= failureTime) return false;
      if (other.job_type === job.job_type) {
        return job.story_id ? other.story_id === job.story_id : true;
      }
      if (job.job_type === "render_avatar") {
        return (
          (other.job_type === "render_story" &&
            other.story_id === job.story_id) ||
          (other.job_type === "assemble_episode" &&
            story?.episode_id &&
            other.episode_id === story.episode_id)
        );
      }
      return false;
    });
    return !recovered;
  });
  for (const fj of failedJobs.slice(0, 2)) {
    blockers.push(
      `Failed job: ${fj.job_type} — ${fj.error ?? "unknown error"}`,
    );
  }

  return (
    <aside className="right-rail">
      {/* Active Jobs */}
      <div className="right-rail-section">
        <h3>Active Jobs {activeJobs.length > 0 && `(${activeJobs.length})`}</h3>
        {activeJobs.length === 0 ? (
          <p className="text-muted" style={{ fontSize: 12 }}>
            No running jobs.
          </p>
        ) : (
          <div className="stack">
            {activeJobs.map((job) => (
              <MiniJobCard key={job.job_id} job={job} />
            ))}
          </div>
        )}
      </div>

      {/* Blockers & Warnings */}
      {blockers.length > 0 && (
        <div className="right-rail-section">
          <h3>Blockers</h3>
          <div className="stack">
            {blockers.map((b, i) => (
              <div key={i} className="validation-msg validation-warning">
                ⚠ {b}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Activity */}
      <div className="right-rail-section">
        <h3>Recent Jobs</h3>
        <div className="stack">
          {recentJobs.map((job) => (
            <div key={job.job_id} className="job-card job-card-compact">
              <div className="row-between">
                <span style={{ fontWeight: 600, fontSize: 12 }}>
                  {job.job_type}
                </span>
                <span className="text-muted" style={{ fontSize: 11 }}>
                  {relativeTime(
                    job.completed_at ??
                      job.started_at ??
                      job.created_at ??
                      null,
                  )}
                </span>
              </div>
              <div className="text-muted" style={{ fontSize: 11 }}>
                {job.status}
                {job.error ? ` · ${job.error}` : ""}
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
};
