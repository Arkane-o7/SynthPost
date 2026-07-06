import React from 'react';
import { api, artifactUrl } from '../api/client';
import { useStudio } from '../state/useStudio';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState } from '../components/EmptyState';
import type { VisualCandidate } from '../contracts';

export const VisualsPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [visuals, setVisuals] = React.useState<VisualCandidate[]>([]);
  const [path, setPath] = React.useState('');
  const [file, setFile] = React.useState<File | null>(null);
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(
    () => api.listVisuals(storyId).then(setVisuals).catch(() => setVisuals([])),
    [storyId],
  );
  React.useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError('');
      setBusy(true);
      await fn();
      await load();
      await studio.refreshAll();
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack-lg animate-fade-in">
      {/* Toolbar */}
      <div className="card">
        <div className="row-between" style={{ marginBottom: 12 }}>
          <h2>Visuals</h2>
          <button
            className="btn-primary"
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.searchVisuals(storyId);
              })
            }
          >
            Search Local Drop Folder
          </button>
        </div>
        <div className="row">
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="Stage a local media path…"
            style={{ maxWidth: 320 }}
          />
          <button
            disabled={busy || !path}
            onClick={() =>
              act(async () => {
                await api.stageLocalVisual(storyId, {
                  path,
                  rights_tier: 'yellow',
                });
                setPath('');
              })
            }
          >
            Stage
          </button>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            style={{ maxWidth: 220 }}
          />
          <button
            disabled={busy || !file}
            onClick={() =>
              act(async () => {
                if (file) await api.uploadVisual(storyId, file);
                setFile(null);
              })
            }
          >
            Upload
          </button>
        </div>
      </div>

      {/* Visual grid */}
      {visuals.length === 0 ? (
        <EmptyState
          icon="🖼"
          title="No visuals added yet"
          description="Visuals are images, videos, and documents that appear alongside the anchor in the final render. Search the local drop folder or upload files."
        />
      ) : (
        <div className="grid grid-3">
          {visuals.map((v) => (
            <div
              key={v.asset_id}
              className={`visual-card rights-${v.rights_tier}`}
            >
              <div className="visual-thumb">
                {v.thumbnail_path ? (
                  <img
                    src={artifactUrl(v.thumbnail_path)}
                    alt={v.title}
                  />
                ) : (
                  <span style={{ fontSize: 24, opacity: 0.3 }}>
                    {v.media_type === 'image'
                      ? '🖼'
                      : v.media_type === 'video'
                        ? '🎬'
                        : '📄'}
                  </span>
                )}
              </div>
              <div className="visual-body">
                <strong className="truncate" style={{ fontSize: 13 }}>
                  {v.title}
                </strong>
                <div className="row-tight">
                  <StatusBadge tone={v.rights_tier === 'green' ? 'green' : v.rights_tier === 'red' ? 'red' : 'amber'}>
                    {v.rights_tier}
                  </StatusBadge>
                  <StatusBadge status={v.review_status}>
                    {v.review_status}
                  </StatusBadge>
                </div>
                <div className="text-muted" style={{ fontSize: 12 }}>
                  {v.provider} · {v.content_role}
                </div>

                {/* Rights warnings */}
                {v.rights_tier === 'yellow' && (
                  <div className="rights-warning warn-amber">
                    ⚠ Manual review recommended
                  </div>
                )}
                {v.rights_tier === 'red' && (
                  <div className="rights-warning warn-red">
                    ⛔ Rights concern — review before use
                  </div>
                )}

                {/* Attribution */}
                <input
                  defaultValue={v.attribution_text ?? ''}
                  placeholder="Attribution text…"
                  style={{ fontSize: 12 }}
                  onBlur={(e) =>
                    void api
                      .updateVisual(v.asset_id, {
                        attribution_text: e.target.value,
                      })
                      .then(load)
                  }
                />

                {/* Actions */}
                <div className="row-tight">
                  <button
                    className="btn-success"
                    style={{ fontSize: 12, padding: '5px 10px' }}
                    onClick={() =>
                      act(() =>
                        api.manualApproveVisual(
                          v.asset_id,
                          v.attribution_text ?? undefined,
                        ),
                      )
                    }
                  >
                    ✓ Approve
                  </button>
                  <button
                    className="btn-danger"
                    style={{ fontSize: 12, padding: '5px 10px' }}
                    onClick={() => act(() => api.rejectVisual(v.asset_id))}
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
