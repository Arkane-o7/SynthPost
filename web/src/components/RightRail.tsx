import React from "react";
import { useStudio } from "../state/useStudio";
import { MiniJobCard } from "./InlineJobCard";
import { relativeTime } from "../lib/formatters";
import { api } from "../api/client";
import type {
  RenderJob,
  ScriptDocument,
  TimelinePlan,
} from "../contracts";
import {
  Activity,
  ChevronRight,
  History,
  MonitorPlay,
  TriangleAlert,
  X,
} from "lucide-react";

export const RightRail: React.FC<{
  mobileOpen?: boolean;
  onMobileClose?: () => void;
  onOpenReviewQueue?: () => void;
}> = ({ mobileOpen = false, onMobileClose, onOpenReviewQueue }) => {
  const studio = useStudio();
  const [cancellingJobId, setCancellingJobId] = React.useState("");

  const story = studio.candidates.find(
    (c) => c.story_id === studio.selectedStoryId,
  );
  const currentEpisodeId = story?.episode_id ?? studio.selectedEpisodeId;
  const isCurrentContextJob = (job: RenderJob) => {
    if (job.channel_id !== studio.selectedChannelId) return false;
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
    ["queued", "paused", "running", "cancel_requested"].includes(j.status),
  );
  const recentJobs = contextJobs.slice(0, 5);
  const reviewRuns = studio.autonomyRuns.filter((run) =>
    ["ready_for_review", "needs_attention"].includes(run.status),
  );
  const readyRunCount = reviewRuns.filter(
    (run) => run.status === "ready_for_review",
  ).length;
  const attentionRunCount = reviewRuns.length - readyRunCount;
  const activeAutonomyRun = studio.autonomyRuns.find(
    (run) =>
      run.episode_id === currentEpisodeId &&
      (["queued", "running", "needs_attention"].includes(run.status) ||
        (run.status === "cancelled" && run.active_job_ids.length > 0)),
  );
  const [script, setScript] = React.useState<ScriptDocument | null>(null);
  const [timeline, setTimeline] = React.useState<TimelinePlan | null>(null);

  const cancelJob = async (job: RenderJob) => {
    try {
      setCancellingJobId(job.job_id);
      studio.setError("");
      if (job.autonomy_run_id) {
        const run = await api.cancelAutonomyRun(job.autonomy_run_id);
        studio.mergeAutonomyRun(run);
      } else {
        await api.cancelJob(job.job_id);
      }
      await studio.refreshAll();
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setCancellingJobId("");
    }
  };

  React.useEffect(() => {
    if (!studio.selectedStoryId) {
      setScript(null);
      setTimeline(null);
      return;
    }
    let cancelled = false;
    void Promise.all([
      api.readScript(studio.selectedStoryId).catch(() => null),
      api.readTimeline(studio.selectedStoryId).catch(() => null),
    ]).then(([nextScript, nextTimeline]) => {
      if (cancelled) return;
      setScript(nextScript);
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
  if (story && !activeAutonomyRun) {
    if (
      !script &&
      ["selected", "research_ready"].includes(story.workflow_state ?? "")
    ) {
      blockers.push("No script is ready yet");
    } else if (script && script.status !== "approved") {
      blockers.push("Script awaiting approval");
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
    <aside className={`right-rail ${mobileOpen ? "mobile-open" : ""}`}>
      <div className="mobile-attention-heading">
        <div>
          <div className="mobile-section-kicker">Remote watch desk</div>
          <h2>Attention center</h2>
        </div>
        <button type="button" aria-label="Close attention center" onClick={onMobileClose}>
          <X size={19} aria-hidden="true" />
        </button>
      </div>
      {reviewRuns.length > 0 && (
        <div className="right-rail-section right-rail-review-callout">
          <h3 className="rail-section-title">
            <MonitorPlay size={14} aria-hidden="true" />
            Final review
          </h3>
          <button
            type="button"
            onClick={() => {
              onMobileClose?.();
              onOpenReviewQueue?.();
            }}
          >
            <span>
              <strong>{readyRunCount} MP4{readyRunCount === 1 ? "" : "s"} ready</strong>
              <small>
                {attentionRunCount
                  ? `${attentionRunCount} run${attentionRunCount === 1 ? "" : "s"} need attention`
                  : "Waiting at the human shipping gate"}
              </small>
            </span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </div>
      )}
      {/* Active Jobs */}
      <div className="right-rail-section">
        <h3 className="rail-section-title">
          <Activity size={14} aria-hidden="true" />
          Active Jobs {activeJobs.length > 0 && `(${activeJobs.length})`}
        </h3>
        {activeJobs.length === 0 ? (
          <p className="text-muted" style={{ fontSize: 12 }}>
            No running jobs.
          </p>
        ) : (
          <div className="stack">
            {activeJobs.map((job) => (
              <MiniJobCard
                key={job.job_id}
                job={job}
                cancelling={cancellingJobId === job.job_id}
                cancelLabel={job.autonomy_run_id ? "Stop shift" : undefined}
                onCancel={() => void cancelJob(job)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Blockers & Warnings */}
      {blockers.length > 0 && (
        <div className="right-rail-section">
          <h3 className="rail-section-title">
            <TriangleAlert size={14} aria-hidden="true" />
            Blockers
          </h3>
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
        <h3 className="rail-section-title">
          <History size={14} aria-hidden="true" />
          Recent Jobs
        </h3>
        <div className="stack">
          {recentJobs.map((job) => (
            <div key={job.job_id} className="recent-job-card">
              <div className="row-between">
                <span className="recent-job-name">
                  {job.job_type.replace(/_/g, " ")}
                </span>
                <span className="recent-job-time">
                  {relativeTime(
                    job.completed_at ??
                      job.started_at ??
                      job.created_at ??
                      null,
                  )}
                </span>
              </div>
              <div className="recent-job-status">
                <span className={`recent-job-dot status-${job.status}`} aria-hidden="true" />
                <span>{job.status}</span>
                {job.error ? ` · ${job.error}` : ""}
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
};
