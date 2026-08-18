import React from "react";
import {
  ArrowLeft,
  Bot,
  Check,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileVideo2,
  FolderSearch2,
  RotateCcw,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import { api, artifactUrl } from "../api/client";
import type { AutonomyRunStatus, AutonomyRunView } from "../contracts";
import { formatDuration, relativeTime } from "../lib/formatters";
import { useStudio } from "../state/useStudio";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";

const OPEN_STATUSES = new Set<AutonomyRunStatus>([
  "queued",
  "running",
  "needs_attention",
  "ready_for_review",
]);

const statusPriority: Record<AutonomyRunStatus, number> = {
  ready_for_review: 0,
  needs_attention: 1,
  running: 2,
  queued: 3,
  accepted: 4,
  rejected: 5,
  cancelled: 6,
};

const sortedOpenRuns = (runs: AutonomyRunView[]) =>
  runs
    .filter((run) => OPEN_STATUSES.has(run.status))
    .sort(
      (left, right) =>
        statusPriority[left.status] - statusPriority[right.status] ||
        right.updated_at.localeCompare(left.updated_at),
    );

const displayTitle = (run: AutonomyRunView) =>
  run.story_title || run.episode_title || "Untitled production";

const numericValue = (value: unknown) => {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

const formatBytes = (input?: number | string | null) => {
  const bytes = numericValue(input);
  if (!bytes || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
};

const findingLabel = (code: string) =>
  code
    .split("_")
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");

const isAutonomyRunResponse = (value: unknown): value is AutonomyRunView =>
  Boolean(
    value &&
      typeof value === "object" &&
      "run_id" in value &&
      "episode_id" in value &&
      "status" in value,
  );

export const ReviewQueuePage: React.FC<{
  onOpenCommandCenter: () => void;
}> = ({ onOpenCommandCenter }) => {
  const studio = useStudio();
  const runs = React.useMemo(
    () => sortedOpenRuns(studio.autonomyRuns),
    [studio.autonomyRuns],
  );
  const [selectedRunId, setSelectedRunId] = React.useState("");
  const [busyAction, setBusyAction] = React.useState("");

  React.useEffect(() => {
    if (!runs.length) {
      setSelectedRunId("");
      return;
    }
    if (!runs.some((run) => run.run_id === selectedRunId)) {
      setSelectedRunId(runs[0].run_id);
    }
  }, [runs, selectedRunId]);

  const selectedRun =
    runs.find((run) => run.run_id === selectedRunId) ?? runs[0];
  const qaStreams = selectedRun?.qa?.probe.streams ?? [];
  const qaVideo = qaStreams.find((stream) => stream.codec_type === "video");
  const qaAudio = qaStreams.find((stream) => stream.codec_type === "audio");
  const qaDuration = numericValue(
    selectedRun?.qa?.probe.format?.duration ?? qaVideo?.duration,
  );
  const readyCount = runs.filter(
    (run) => run.status === "ready_for_review",
  ).length;
  const attentionCount = runs.filter(
    (run) => run.status === "needs_attention",
  ).length;
  const activeCount = runs.filter((run) =>
    ["queued", "running"].includes(run.status),
  ).length;

  const act = async (action: string, fn: () => Promise<unknown>) => {
    try {
      setBusyAction(action);
      studio.setError("");
      const result = await fn();
      if (isAutonomyRunResponse(result)) {
        studio.mergeAutonomyRun(result);
      }
      if (action !== "reveal") await studio.refreshAll();
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyAction("");
    }
  };

  const navigateToRun = async (run: AutonomyRunView) => {
    await studio.openEpisode(run.project_id, run.episode_id);
    if (run.story_id) studio.setSelectedStoryId(run.story_id);
    onOpenCommandCenter();
  };

  const openRunInStudio = async (run: AutonomyRunView) => {
    try {
      setBusyAction("open");
      studio.setError("");
      await navigateToRun(run);
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyAction("");
    }
  };

  const rejectAndOpen = async (run: AutonomyRunView) => {
    try {
      setBusyAction("reject");
      studio.setError("");
      const rejectedRun = await api.rejectAutonomyRun(run.run_id);
      studio.mergeAutonomyRun(rejectedRun);
      await studio.refreshAutonomyRuns();
      await navigateToRun(run);
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyAction("");
    }
  };

  return (
    <div className="review-queue-page animate-fade-in">
      <header className="review-queue-header">
        <button
          type="button"
          className="review-back-button"
          onClick={onOpenCommandCenter}
        >
          <ArrowLeft size={16} aria-hidden="true" />
          Synthea Studio
        </button>
        <div className="review-queue-heading">
          <div className="review-queue-kicker">Morning screening room</div>
          <h1>Final MP4 review</h1>
          <p>
            Hermes can finish the shift. You remain the only person who decides
            what leaves the building.
          </p>
        </div>
        <div className="review-queue-totals" aria-label="Review queue summary">
          <span><b>{readyCount}</b> ready</span>
          <span className={attentionCount ? "warn" : ""}><b>{attentionCount}</b> attention</span>
          <span><b>{activeCount}</b> working</span>
        </div>
      </header>

      {runs.length === 0 ? (
        <section className="review-queue-empty">
          <EmptyState
            icon="✓"
            title="The review desk is clear"
            description="Start a YOLO production from an episode. Finished MP4s will wait here; SynthPost never uploads them automatically."
          >
            <button className="btn-primary" onClick={onOpenCommandCenter}>
              Return to Synthea Studio
            </button>
          </EmptyState>
        </section>
      ) : (
        <div className="review-queue-layout">
          <aside className="review-run-list" aria-label="Open production runs">
            <div className="review-run-list-heading">
              <span>Open runs</span>
              <b>{runs.length.toString().padStart(2, "0")}</b>
            </div>
            {runs.map((run, index) => (
              <button
                type="button"
                key={run.run_id}
                className={`review-run-card ${run.run_id === selectedRun?.run_id ? "selected" : ""}`}
                aria-pressed={run.run_id === selectedRun?.run_id}
                onClick={() => setSelectedRunId(run.run_id)}
              >
                <span className="review-run-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="review-run-card-copy">
                  <strong>{displayTitle(run)}</strong>
                  <small>{run.episode_title || "Episode"} · {relativeTime(run.updated_at)}</small>
                  <span>
                    {run.status === "running" || run.status === "queued"
                      ? `${Math.round(Number(run.progress) || 0)}% · ${run.current_stage.replace(/_/g, " ")}`
                      : run.status === "needs_attention"
                        ? run.error || "Automatic repair stopped"
                        : "Production MP4 and QA report ready"}
                  </span>
                </span>
                <StatusBadge status={run.status}>
                  {run.status === "ready_for_review"
                    ? "ready"
                    : run.status.replace(/_/g, " ")}
                </StatusBadge>
              </button>
            ))}
          </aside>

          {selectedRun && (
            <section className="review-screening-panel" aria-label="Selected production review">
              <div className="review-screening-titlebar">
                <div>
                  <div className="review-queue-kicker">
                    {selectedRun.project_title || "Project"} / {selectedRun.episode_title || "Episode"}
                  </div>
                  <h2>{displayTitle(selectedRun)}</h2>
                </div>
                <StatusBadge status={selectedRun.status}>
                  {selectedRun.status.replace(/_/g, " ")}
                </StatusBadge>
              </div>

              {selectedRun.final_output_path ? (
                <div className="review-player-shell">
                  <div className="review-player-label">
                    <span><FileVideo2 size={14} /> Production master</span>
                    <span>Local review only · no upload credentials</span>
                  </div>
                  <video
                    controls
                    preload="metadata"
                    aria-label={`Review ${displayTitle(selectedRun)} production MP4`}
                    src={artifactUrl(
                      selectedRun.final_output_path,
                      selectedRun.final_output_sha256 || selectedRun.updated_at,
                    )}
                  />
                </div>
              ) : (
                <div className="review-run-live-state">
                  {selectedRun.status === "needs_attention" ? (
                    <TriangleAlert size={28} aria-hidden="true" />
                  ) : (
                    <Bot size={28} aria-hidden="true" />
                  )}
                  <div>
                    <div className="review-queue-kicker">Hermes production floor</div>
                    <h3>
                      {selectedRun.status === "needs_attention"
                        ? "A checkpoint needs you"
                        : "The MP4 is still being built"}
                    </h3>
                    <p>
                      {selectedRun.error ||
                        `${selectedRun.current_stage.replace(/_/g, " ")} · ${Math.round(Number(selectedRun.progress) || 0)}%`}
                    </p>
                  </div>
                  </div>
                )}

              {selectedRun.warnings.length > 0 && (
                <section
                  id={`run-warnings-${selectedRun.run_id}`}
                  className="review-run-warnings"
                  aria-labelledby={`run-warnings-title-${selectedRun.run_id}`}
                >
                  <div className="review-run-warnings-heading">
                    <span aria-hidden="true"><TriangleAlert size={17} /></span>
                    <div>
                      <div className="review-queue-kicker">Editorial watchlist</div>
                      <h3 id={`run-warnings-title-${selectedRun.run_id}`}>
                        Review {selectedRun.warnings.length} production warning
                        {selectedRun.warnings.length === 1 ? "" : "s"} before accepting
                      </h3>
                    </div>
                    <StatusBadge status="warning">
                      {selectedRun.warnings.length} open
                    </StatusBadge>
                  </div>
                  <ul>
                    {selectedRun.warnings.map((warning, index) => (
                      <li key={`${index}:${warning}`}>{warning}</li>
                    ))}
                  </ul>
                </section>
              )}

              <div className="review-evidence-grid">
                <section className="review-qa-card">
                  <div className="review-card-heading">
                    <span><ShieldCheck size={15} /> Automated final checks</span>
                    <StatusBadge status={selectedRun.qa?.status ?? "pending"}>
                      {selectedRun.qa?.status ?? "pending"}
                    </StatusBadge>
                  </div>
                  {selectedRun.qa?.findings.length ? (
                    <div className="review-check-list">
                      {selectedRun.qa.findings.map((finding) => (
                        <div key={finding.code} className={`review-check review-check-${finding.severity}`}>
                          <TriangleAlert size={14} aria-hidden="true" />
                          <span><strong>{findingLabel(finding.code)}</strong><small>{finding.message}</small></span>
                        </div>
                      ))}
                    </div>
                  ) : selectedRun.qa?.passed ? (
                    <div className="review-check-list">
                      <div className="review-check review-check-passed">
                        <Check size={14} aria-hidden="true" />
                        <span>
                          <strong>Technical gate passed</strong>
                          <small>Streams, decode, profile, A/V sync, and loudness are within policy.</small>
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="review-card-empty">
                      {selectedRun.status === "ready_for_review"
                        ? "No structured check details were returned. Watch the full MP4 before accepting it."
                        : "Checks begin after final assembly."}
                    </p>
                  )}
                </section>

                <section className="review-output-card">
                  <div className="review-card-heading">
                    <span><Clock3 size={15} /> Output facts</span>
                  </div>
                  <dl>
                    <div><dt>Runtime</dt><dd>{qaDuration ? formatDuration(qaDuration) : "—"}</dd></div>
                    <div><dt>Frame</dt><dd>{qaVideo?.width && qaVideo.height ? `${qaVideo.width} × ${qaVideo.height}` : "—"}</dd></div>
                    <div><dt>Video</dt><dd>{qaVideo?.codec_name || "—"}</dd></div>
                    <div><dt>Audio</dt><dd>{qaAudio?.codec_name || "—"}</dd></div>
                    <div><dt>File</dt><dd>{formatBytes(selectedRun.qa?.probe.format?.size)}</dd></div>
                    <div><dt>Media policy</dt><dd>{selectedRun.policy?.rights_policy?.replace(/_/g, " ") || "green only"}</dd></div>
                  </dl>
                  {selectedRun.final_output_path && (
                    <code>{selectedRun.final_output_path}</code>
                  )}
                </section>
              </div>

              <div className="review-decision-bar">
                <div>
                  <div className="review-queue-kicker">Human shipping gate</div>
                  <strong>
                    {selectedRun.status === "ready_for_review"
                      ? selectedRun.warnings.length
                        ? `Watch it end-to-end and review the ${selectedRun.warnings.length} warning${selectedRun.warnings.length === 1 ? "" : "s"} above before recording your decision.`
                        : "Watch it end-to-end, then record your decision."
                      : selectedRun.status === "needs_attention"
                        ? "Retry the checkpoint or return to the editor."
                        : "You can leave this screen; the run continues locally."}
                  </strong>
                </div>
                <div className="review-decision-actions">
                  {selectedRun.final_output_path && (
                    <button
                      type="button"
                      disabled={Boolean(busyAction)}
                      onClick={() =>
                        void act("reveal", () =>
                          api.revealAutonomyOutput(selectedRun.run_id),
                        )
                      }
                    >
                      <FolderSearch2 size={16} aria-hidden="true" />
                      {busyAction === "reveal" ? "Opening…" : "Finder"}
                    </button>
                  )}
                  {selectedRun.status === "needs_attention" && (
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={Boolean(busyAction)}
                      onClick={() =>
                        void act("retry", () =>
                          api.retryAutonomyRun(selectedRun.run_id),
                        )
                      }
                    >
                      <RotateCcw size={16} aria-hidden="true" />
                      {busyAction === "retry" ? "Restarting…" : "Retry checkpoint"}
                    </button>
                  )}
                  {selectedRun.status === "ready_for_review" && (
                    <>
                      <button
                        type="button"
                        className="review-reject-button"
                        disabled={Boolean(busyAction)}
                        onClick={() => void rejectAndOpen(selectedRun)}
                      >
                        <X size={16} aria-hidden="true" />
                        {busyAction === "reject" ? "Rejecting…" : "Reject & edit"}
                      </button>
                      <button
                        type="button"
                        className="review-accept-button"
                        disabled={Boolean(busyAction)}
                        aria-describedby={
                          selectedRun.warnings.length
                            ? `run-warnings-${selectedRun.run_id}`
                            : undefined
                        }
                        onClick={() =>
                          void act("accept", () =>
                            api.acceptAutonomyRun(selectedRun.run_id),
                          )
                        }
                      >
                        <CheckCircle2 size={17} aria-hidden="true" />
                        {busyAction === "accept" ? "Recording…" : "Accept MP4"}
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    disabled={Boolean(busyAction)}
                    onClick={() => void openRunInStudio(selectedRun)}
                  >
                    <ExternalLink size={16} aria-hidden="true" />
                    Open editor
                  </button>
                </div>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
};
