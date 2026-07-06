import React from 'react';
import { api } from '../api/client';
import { useStudio } from '../state/useStudio';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState } from '../components/EmptyState';
import type { ScriptDocument } from '../contracts';

export const ScriptPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [script, setScript] = React.useState<ScriptDocument | null>(null);
  const [headline, setHeadline] = React.useState('');
  const [text, setText] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(() => {
    api.readScript(storyId).then((s) => {
      setScript(s);
      setHeadline(s?.headline ?? '');
      setText(s?.sections.map((sec) => sec.text).join('\n\n') ?? '');
    }).catch(() => setScript(null));
  }, [storyId]);

  React.useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError('');
      setBusy(true);
      await fn();
      await studio.refreshAll();
      load();
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  if (!script) {
    return (
      <div className="animate-fade-in">
        <EmptyState
          icon="📝"
          title="No script yet"
          description="Generate a broadcast script from the research pack using Ollama, or write one manually."
        >
          <div className="row" style={{ justifyContent: 'center' }}>
            <button
              className="btn-primary btn-lg"
              disabled={busy}
              onClick={() => act(() => api.generateScript(storyId))}
            >
              {busy ? 'Generating…' : 'Generate with Ollama'}
            </button>
          </div>
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="section-editor animate-fade-in">
      {/* Section nav */}
      <div className="card stack">
        <h2>Sections</h2>
        <div className="section-list">
          {script.sections.map((sec) => (
            <button key={sec.section_id} className="btn-ghost" style={{ padding: '8px 10px' }}>
              <div style={{ fontWeight: 600, fontSize: 12 }}>{sec.section_type}</div>
              <div className="text-muted" style={{ fontSize: 11 }}>
                {Math.round(sec.estimated_duration_seconds)}s ·{' '}
                {sec.approval_status}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Script editor */}
      <div className="card stack">
        <h2>Script Editor</h2>
        <label>
          Headline
          <input
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            placeholder="Story headline"
          />
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          style={{ minHeight: 260 }}
        />
        <div className="row">
          <button
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.saveManualScript(storyId, headline, text);
              })
            }
          >
            Save Draft
          </button>
          <button
            disabled={busy}
            onClick={() => act(() => api.generateScript(storyId))}
          >
            Regenerate
          </button>
          <button
            className="btn-success"
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.approveScript(storyId);
              })
            }
          >
            ✓ Approve Script
          </button>
        </div>
      </div>

      {/* Metadata panel */}
      <div className="card stack">
        <h2>Metadata</h2>
        <div className="row-tight">
          <StatusBadge status={script.status}>{script.status}</StatusBadge>
          <span className="text-muted" style={{ fontSize: 12 }}>
            v{script.version}
          </span>
        </div>
        <div className="text-muted" style={{ fontSize: 13 }}>
          Duration: ~{Math.round(script.estimated_duration_seconds)}s
        </div>

        {script.warnings && script.warnings.length > 0 && (
          <div>
            <h3>⚠ Warnings</h3>
            <div className="stack" style={{ marginTop: 4 }}>
              {script.warnings.map((w) => (
                <div key={w} className="validation-msg validation-warning">
                  {w}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="text-muted" style={{ fontSize: 12, marginTop: 8 }}>
          Approved scripts are immutable. Saving creates a new revision.
        </div>
      </div>
    </div>
  );
};
