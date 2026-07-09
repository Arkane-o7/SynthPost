import React from 'react';
import { api } from '../api/client';
import { useStudio } from '../state/useStudio';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState } from '../components/EmptyState';

type ResearchPackData = Awaited<ReturnType<typeof api.readResearch>>;

export const ResearchPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [pack, setPack] = React.useState<ResearchPackData>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    void api
      .readResearch(storyId)
      .then(setPack)
      .catch(() => setPack(null));
  }, [storyId, studio.lastJobEventTimestamp]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError('');
      setLoading(true);
      await fn();
      await studio.refreshAll();
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  if (!pack) {
    return (
      <div className="animate-fade-in">
        <EmptyState
          icon="🔬"
          title="No research pack generated yet"
          description="The research job will analyze the story source, extract claims, identify key entities, and compile supporting evidence documents."
        >
          <button
            className="btn-primary btn-lg"
            disabled={loading}
            onClick={() => act(() => api.startResearch(storyId))}
          >
            {loading ? 'Starting…' : 'Start Research Job'}
          </button>
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="grid grid-3 animate-fade-in" style={{ alignItems: 'start' }}>
      {/* Summary column */}
      <div className="card stack">
        <h2>Summary</h2>
        <p style={{ lineHeight: 1.6 }}>{pack.research_summary}</p>
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 4 }}>
          <div className="text-muted" style={{ fontSize: 13 }}>
            {pack.claims.length} claims · {pack.documents.length} documents
          </div>
          {pack.contradictions.length > 0 && (
            <div className="text-muted" style={{ fontSize: 13 }}>
              {pack.contradictions.length} contradictions
            </div>
          )}
        </div>
        <button
          disabled={loading}
          onClick={() =>
            act(async () => {
              await api.startResearch(storyId);
            })
          }
        >
          {loading ? 'Running…' : 'Re-run Research'}
        </button>
      </div>

      {/* Claims column */}
      <div className="card stack">
        <h2>Claims & Evidence</h2>
        {pack.claims.map((claim) => (
          <div
            key={claim.claim_id}
            style={{
              padding: 'var(--sp-3)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            <strong style={{ fontSize: 13 }}>{claim.claim_text}</strong>
            <div className="row-tight" style={{ marginTop: 6 }}>
              <StatusBadge tone={claim.supported ? 'green' : 'amber'}>
                {claim.supported ? 'Supported' : 'Uncertain'}
              </StatusBadge>
              <span className="text-muted" style={{ fontSize: 12 }}>
                confidence {Math.round(claim.confidence * 100)}%
              </span>
            </div>
            {claim.evidence_ids.length > 0 && (
              <div
                className="text-muted font-mono"
                style={{ fontSize: 11, marginTop: 4 }}
              >
                Evidence: {claim.evidence_ids.join(', ')}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Entities & Warnings column */}
      <div className="card stack">
        <h2>Entities & Warnings</h2>
        {pack.people.length > 0 && (
          <div>
            <h3>People</h3>
            <div className="row-tight" style={{ marginTop: 4 }}>
              {pack.people.map((p) => (
                <StatusBadge key={p} tone="blue">{p}</StatusBadge>
              ))}
            </div>
          </div>
        )}
        {pack.organizations.length > 0 && (
          <div>
            <h3>Organizations</h3>
            <div className="row-tight" style={{ marginTop: 4 }}>
              {pack.organizations.map((o) => (
                <StatusBadge key={o} tone="blue">{o}</StatusBadge>
              ))}
            </div>
          </div>
        )}
        {pack.locations.length > 0 && (
          <div>
            <h3>Locations</h3>
            <div className="row-tight" style={{ marginTop: 4 }}>
              {pack.locations.map((l) => (
                <StatusBadge key={l} tone="blue">{l}</StatusBadge>
              ))}
            </div>
          </div>
        )}
        {pack.uncertainties.length > 0 && (
          <div>
            <h3>⚠ Uncertainties</h3>
            <div className="stack" style={{ marginTop: 4 }}>
              {pack.uncertainties.map((u) => (
                <div key={u} className="validation-msg validation-warning">
                  {u}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
