import React from "react";
import {
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleStop,
  MoonStar,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { api } from "../api/client";
import type { AutonomyRunStatus, AutonomyRunView } from "../contracts";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "./StatusBadge";

const RUNNING_STATUSES = new Set<AutonomyRunStatus>(["queued", "running"]);
const RELEVANT_STATUSES = new Set<AutonomyRunStatus>([
  "queued",
  "running",
  "needs_attention",
  "ready_for_review",
]);

const AUTONOMY_STAGES = [
  "Research",
  "Script",
  "Voice",
  "Visuals",
  "Timeline",
  "Render",
  "Assembly",
  "QA",
];

const normalizedStageIndex = (run: AutonomyRunView | undefined) => {
  if (!run) return -1;
  if (["ready_for_review", "accepted", "rejected"].includes(run.status)) {
    return AUTONOMY_STAGES.length;
  }
  const value = run.current_stage.toLowerCase();
  if (value.includes("research")) return 0;
  if (value.includes("script")) return 1;
  if (value.includes("narrat") || value.includes("voice") || value.includes("tts")) return 2;
  if (value.includes("visual") || value.includes("media")) return 3;
  if (value.includes("timeline")) return 4;
  if (value.includes("render") || value.includes("avatar") || value.includes("compos")) return 5;
  if (value.includes("assembl") || value.includes("outro")) return 6;
  if (value.includes("qa") || value.includes("quality")) return 7;
  return run.status === "queued" ? -1 : 0;
};

const latestRun = (runs: AutonomyRunView[]) =>
  [...runs].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0];

const runLabel = (run: AutonomyRunView) => {
  switch (run.status) {
    case "queued":
      return "Night shift queued";
    case "running":
      return "Night shift in production";
    case "needs_attention":
      return "Night shift needs attention";
    case "ready_for_review":
      return "MP4 ready for your review";
    default:
      return "Autonomous production";
  }
};

export const AutonomyRunControl: React.FC<{
  storyId?: string;
  onOpenReviewQueue: () => void;
}> = ({ storyId, onOpenReviewQueue }) => {
  const studio = useStudio();
  const [busyAction, setBusyAction] = React.useState("");
  const episode = studio.episodes.find(
    (item) => item.episode_id === studio.selectedEpisodeId,
  );
  const project = studio.projects.find(
    (item) => item.project_id === studio.selectedProjectId,
  );
  const episodeRuns = studio.autonomyRuns.filter(
    (run) => run.episode_id === studio.selectedEpisodeId,
  );
  const run =
    latestRun(episodeRuns.filter((item) => RELEVANT_STATUSES.has(item.status))) ??
    latestRun(episodeRuns);
  const isRunning = Boolean(run && RUNNING_STATUSES.has(run.status));
  const activeJob = studio.jobs.find(
    (job) =>
      job.episode_id === studio.selectedEpisodeId &&
      ["queued", "paused", "running", "cancel_requested"].includes(job.status),
  );
  const rawProgress = Number(run?.progress);
  const progress = Number.isFinite(rawProgress)
    ? Math.max(0, Math.min(100, rawProgress))
    : Math.max(0, Math.min(100, activeJob?.progress ?? 0));
  const activeStageIndex = normalizedStageIndex(run);
  const configuredTargetSeconds =
    studio.selectedChannelProfile?.default_target_duration_seconds ?? 600;
  const narrationMode =
    studio.selectedChannelProfile?.default_narration_mode ?? "explained";
  const durationMode = run?.policy.duration_mode ?? "adaptive";
  const displayedTargetSeconds = run?.selected_duration_seconds;
  const durationLabel =
    durationMode === "adaptive"
      ? displayedTargetSeconds
        ? `Hermes chose ${Number((displayedTargetSeconds / 60).toFixed(1))} min`
        : "Hermes chooses length"
      : `${Math.round(
          (run?.policy.target_duration_seconds ?? configuredTargetSeconds) / 60,
        )} min target`;
  const launchBlocker =
    episode && episode.story_ids.length > 1
      ? "YOLO production currently supports one-story episodes only. Move the other stories to separate episodes first."
      : activeJob
        ? activeJob.status === "cancel_requested"
          ? `The ${activeJob.job_type.replace(/_/g, " ")} worker is stopping. Hermes can start again after it releases the episode safely.`
          : `Wait for the existing ${activeJob.job_type.replace(/_/g, " ")} job to finish or cancel it before starting Hermes.`
        : "";

  if (!episode) return null;

  const act = async (action: string, fn: () => Promise<AutonomyRunView>) => {
    try {
      setBusyAction(action);
      studio.setError("");
      const updatedRun = await fn();
      studio.mergeAutonomyRun(updatedRun);
      await studio.refreshAll();
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyAction("");
    }
  };

  const startRun = () =>
    act("start", () =>
      api.startAutonomyRun({
        episode_id: episode.episode_id,
        story_id: storyId || undefined,
        duration_mode: "adaptive",
        target_duration_seconds: configuredTargetSeconds,
        narration_mode: narrationMode,
        category: project?.default_category,
      }),
    );

  return (
    <section
      className={`autonomy-console autonomy-${run?.status ?? "idle"}`}
      aria-label="Autonomous video production"
      aria-busy={isRunning}
    >
      <div className="autonomy-console-beacon" aria-hidden="true">
        <MoonStar size={19} />
        <span />
      </div>

      <div className="autonomy-console-copy">
        <div className="autonomy-console-kicker">
          <span>Hermes night shift</span>
          {run && RELEVANT_STATUSES.has(run.status) && (
            <StatusBadge status={run.status}>
              {run.status.replace(/_/g, " ")}
            </StatusBadge>
          )}
        </div>
        <h2>{run && RELEVANT_STATUSES.has(run.status) ? runLabel(run) : "Hand the whole video to Hermes"}</h2>
        <p aria-live="polite" aria-atomic="true">
          {run?.status === "needs_attention"
            ? run.error || "A production gate exhausted its automatic repair attempts."
            : run?.status === "ready_for_review"
              ? "Research, script, media, narration, render, and final checks are complete. Nothing was uploaded."
              : isRunning
                ? `${run?.engine || "Hermes"} is working through ${run?.current_stage?.replace(/_/g, " ") || activeJob?.stage || "production"}. You can close Synthea Studio; the workers keep going.`
                : "One command researches, writes, voices, illustrates, edits, renders, and checks a production MP4 while you are away."}
        </p>
      </div>

      <div className="autonomy-policy" aria-label="Autonomy policy">
        <span><ShieldCheck size={13} /> Green-only media</span>
        <span title={run?.duration_rationale ?? undefined}>{durationLabel}</span>
        <span>{(run?.policy.render_profile ?? "production").replace(/_/g, " ")} render</span>
        <span>Never uploads</span>
      </div>

      {run && RELEVANT_STATUSES.has(run.status) && (
        <div className="autonomy-flight-path">
          <div className="autonomy-flight-progress">
            <span
              role="progressbar"
              aria-label="Autonomous production progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress)}
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="autonomy-stage-track">
            {AUTONOMY_STAGES.map((stage, index) => (
              <span
                key={stage}
                className={
                  index < activeStageIndex
                    ? "complete"
                    : index === activeStageIndex
                      ? "active"
                      : ""
                }
              >
                <i>{index < activeStageIndex ? "✓" : String(index + 1).padStart(2, "0")}</i>
                {stage}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="autonomy-console-actions">
        {(!run || !RELEVANT_STATUSES.has(run.status)) && (
          <div className="autonomy-launch-stack">
            <button
              type="button"
              className="autonomy-launch-button"
              disabled={Boolean(busyAction) || Boolean(launchBlocker)}
              title={launchBlocker || "Start unattended production"}
              onClick={() => void startRun()}
            >
              <Bot size={18} aria-hidden="true" />
              <span>
                <small>Go end-to-end</small>
                {busyAction === "start" ? "Starting shift…" : "YOLO Produce"}
              </span>
              <ChevronRight size={17} aria-hidden="true" />
            </button>
            {launchBlocker && (
              <span className="autonomy-launch-blocker" role="status">
                {launchBlocker}
              </span>
            )}
          </div>
        )}

        {isRunning && run && (
          <button
            type="button"
            className="autonomy-stop-button"
            disabled={Boolean(busyAction)}
            onClick={() =>
              void act("cancel", () => api.cancelAutonomyRun(run.run_id))
            }
          >
            <CircleStop size={16} aria-hidden="true" />
            {busyAction === "cancel" ? "Stopping…" : "Stop shift"}
          </button>
        )}

        {run?.status === "needs_attention" && (
          <>
            <button
              type="button"
              className="btn-primary"
              disabled={Boolean(busyAction)}
              onClick={() =>
                void act("retry", () => api.retryAutonomyRun(run.run_id))
              }
            >
              <RotateCcw size={16} aria-hidden="true" />
              {busyAction === "retry" ? "Restarting…" : "Retry from checkpoint"}
            </button>
            <button
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() =>
                void act("cancel", () => api.cancelAutonomyRun(run.run_id))
              }
            >
              Take over manually
            </button>
          </>
        )}

        {run?.status === "ready_for_review" && (
          <button
            type="button"
            className="autonomy-review-button"
            onClick={onOpenReviewQueue}
          >
            <CheckCircle2 size={17} aria-hidden="true" />
            Review MP4
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        )}
      </div>
    </section>
  );
};
