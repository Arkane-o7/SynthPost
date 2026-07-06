import React from 'react';
import { api, artifactUrl } from '../api/client';
import { useStudio } from '../state/useStudio';

export const PreviewPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [manifest, setManifest] = React.useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = React.useState(false);

  const composition = manifest?.composition as
    | { preview_path?: string; output_path?: string }
    | undefined;

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError('');
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
    <div className="grid grid-2 animate-fade-in" style={{ alignItems: 'start' }}>
      {/* Controls */}
      <div className="card stack">
        <h2>Preview</h2>
        <p className="text-muted" style={{ fontSize: 13 }}>
          Preview uses the same Remotion composition as final rendering — this is
          not a separate mock preview.
        </p>
        <button
          disabled={busy}
          onClick={() =>
            act(async () => {
              setManifest(await api.buildManifest(storyId, 'preview', true));
            })
          }
        >
          Build Renderer Manifest
        </button>
        <button
          className="btn-primary"
          disabled={busy}
          onClick={() => act(() => api.renderStory(storyId, 'preview', true))}
        >
          Render Preview
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
            <img src={artifactUrl(composition.preview_path)} alt="Preview" />
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
