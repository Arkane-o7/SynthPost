import React from "react";
import { api, artifactUrl } from "../api/client";
import { useStudio } from "../state/useStudio";

export const PreviewPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [manifest, setManifest] = React.useState<Record<
    string,
    unknown
  > | null>(null);
  const [busy, setBusy] = React.useState(false);

  const activeRenderJob = studio.jobs.find(
    (job) =>
      job.story_id === storyId &&
      job.job_type === "render_story" &&
      ["queued", "running"].includes(job.status),
  );
  const isRendering = busy || Boolean(activeRenderJob);

  const composition = manifest?.composition as
    | { preview_path?: string; output_path?: string }
    | undefined;

  const loadManifest = React.useCallback(async () => {
    setManifest(await api.buildManifest(storyId, "preview", true));
  }, [storyId, studio.lastJobEventTimestamp]);

  React.useEffect(() => {
    void loadManifest().catch(() => setManifest(null));
  }, [loadManifest]);

  const latestRenderCompletedAt = studio.jobs.find(
    (job) =>
      job.story_id === storyId &&
      job.job_type === "render_story" &&
      job.status === "completed",
  )?.completed_at;

  React.useEffect(() => {
    if (latestRenderCompletedAt) {
      void loadManifest().catch(() => setManifest(null));
    }
  }, [latestRenderCompletedAt, loadManifest]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError("");
      setBusy(true);
      await fn();
      await studio.refreshAll();
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="grid grid-2 animate-fade-in"
      style={{ alignItems: "start" }}
    >
      {/* Controls */}
      <div className="card stack">
        <h2>Preview</h2>
        <p className="text-muted" style={{ fontSize: 13 }}>
          Preview uses the same Remotion composition as final rendering — this
          is not a separate mock preview.
        </p>
        <button disabled={isRendering} onClick={() => act(loadManifest)}>
          Build Renderer Manifest
        </button>
        <button
          className="btn-primary"
          disabled={isRendering}
          onClick={() =>
            act(() => api.renderStory(storyId, "preview", true))
          }
        >
          {isRendering ? "Rendering Preview…" : "Render Preview"}
        </button>

        {composition?.output_path && (
          <div className="font-mono text-muted" style={{ fontSize: 12 }}>
            Output: {composition.output_path}
          </div>
        )}
      </div>

      {/* Preview frame */}
      <div className="card">
        <div className="preview-frame">
          {composition?.preview_path ? (
            <img
              src={artifactUrl(
                composition.preview_path,
                latestRenderCompletedAt,
              )}
              alt="Preview"
            />
          ) : (
            <span className="text-muted" style={{ fontSize: 14 }}>
              Build manifest and render to see a preview frame
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
