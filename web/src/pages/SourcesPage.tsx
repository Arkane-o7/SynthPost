import React from 'react';
import { api } from '../api/client';
import { useStudio } from '../state/useStudio';
import { StatusBadge } from '../components/StatusBadge';
import { relativeTime } from '../lib/formatters';

export const SourcesPage: React.FC = () => {
  const studio = useStudio();
  const [name, setName] = React.useState('');
  const [feedUrl, setFeedUrl] = React.useState('');
  const [category, setCategory] = React.useState('technology');
  const [busy, setBusy] = React.useState(false);
  const [testResults, setTestResults] = React.useState<Record<string, string>>({});

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
    <div>
      <div className="topbar">
        <div>
          <div className="topbar-kicker">SynthPost Studio</div>
          <h1>Sources</h1>
        </div>
      </div>

      <div className="grid grid-sidebar-main">
        {/* Add source form */}
        <div className="card stack">
          <h2>Add News Source</h2>
          <label>
            Source name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Ars Technica"
            />
          </label>
          <label>
            Feed URL
            <input
              value={feedUrl}
              onChange={(e) => setFeedUrl(e.target.value)}
              placeholder="https://feeds.example.com/rss"
            />
          </label>
          <label>
            Category
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              {[
                'technology', 'politics', 'science', 'world', 'business',
                'health', 'sports', 'entertainment', 'environment', 'other',
              ].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <button
            className="btn-primary"
            disabled={busy || !name.trim() || !feedUrl.trim()}
            onClick={() =>
              act(async () => {
                await api.createSource({
                  name: name.trim(),
                  source_type: 'rss',
                  feed_url: feedUrl.trim(),
                  category,
                  custom: true,
                });
                setName('');
                setFeedUrl('');
              })
            }
          >
            Add Source
          </button>
        </div>

        {/* Source registry */}
        <div className="stack">
          <h2>Source Registry</h2>
          {studio.sources.length === 0 ? (
            <div className="card text-muted" style={{ textAlign: 'center', padding: 32 }}>
              No sources configured. Add an RSS/Atom feed to get started.
            </div>
          ) : (
            studio.sources.map((source) => (
              <div key={source.source_id} className="source-card">
                <div className="stack" style={{ gap: 6 }}>
                  <div className="row-tight">
                    <strong style={{ fontSize: 15 }}>{source.name}</strong>
                    <StatusBadge tone={source.enabled ? 'green' : 'red'}>
                      {source.enabled ? 'enabled' : 'disabled'}
                    </StatusBadge>
                  </div>
                  <div className="text-muted" style={{ fontSize: 12 }}>
                    {source.category} · {source.source_type} · reliability{' '}
                    {source.reliability_score.toFixed(2)}
                  </div>
                  <div className="font-mono text-muted" style={{ fontSize: 11, wordBreak: 'break-all' }}>
                    {source.feed_url || source.homepage_url}
                  </div>
                  {source.last_checked_at && (
                    <div className="text-muted" style={{ fontSize: 11 }}>
                      Last checked: {relativeTime(source.last_checked_at)} · last pull {source.last_item_count} items
                      {source.last_success_at ? ` · last success ${relativeTime(source.last_success_at)}` : ''}
                    </div>
                  )}
                  {source.last_error && (
                    <div className="validation-msg validation-warning" style={{ fontSize: 11 }}>
                      Feed health: {source.consecutive_failures} consecutive failure{source.consecutive_failures === 1 ? '' : 's'} · {source.last_error}
                    </div>
                  )}
                  {testResults[source.source_id] && (
                    <div className="validation-msg validation-success" style={{ fontSize: 12 }}>
                      {testResults[source.source_id]}
                    </div>
                  )}
                </div>
                <div className="stack" style={{ gap: 6, justifyContent: 'flex-start' }}>
                  <button
                    disabled={busy}
                    onClick={async () => {
                      try {
                        const result = await api.testSource(source.source_id);
                        setTestResults((prev) => ({
                          ...prev,
                          [source.source_id]: `✓ Feed healthy · ${result.count} entries found`,
                        }));
                      } catch (err) {
                        setTestResults((prev) => ({
                          ...prev,
                          [source.source_id]: `✕ Test failed: ${err instanceof Error ? err.message : String(err)}`,
                        }));
                      }
                    }}
                  >
                    Test
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(() =>
                        api.updateSource(source.source_id, {
                          enabled: !source.enabled,
                        }),
                      )
                    }
                  >
                    {source.enabled ? 'Disable' : 'Enable'}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
