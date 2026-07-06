import React from 'react';

export const SettingsPage: React.FC = () => (
  <div>
    <div className="topbar">
      <div>
        <div className="topbar-kicker">SynthPost Studio</div>
        <h1>Settings</h1>
      </div>
    </div>

    <div className="grid grid-2" style={{ alignItems: 'start' }}>
      {/* Local AI */}
      <div className="card stack">
        <h2>Local AI / Ollama</h2>
        <div className="stack" style={{ gap: 8 }}>
          {[
            { label: 'Provider', env: 'SYNTHPOST_LLM_PROVIDER' },
            { label: 'Ollama Base URL', env: 'SYNTHPOST_OLLAMA_BASE_URL' },
            { label: 'Model', env: 'SYNTHPOST_OLLAMA_MODEL' },
            { label: 'Timeout', env: 'SYNTHPOST_OLLAMA_TIMEOUT' },
            { label: 'Temperature', env: 'SYNTHPOST_OLLAMA_TEMPERATURE' },
          ].map((item) => (
            <div key={item.env} className="row-between">
              <span className="text-muted" style={{ fontSize: 13 }}>
                {item.label}
              </span>
              <code
                className="font-mono"
                style={{
                  fontSize: 11,
                  padding: '3px 8px',
                  background: 'var(--surface-inset)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                {item.env}
              </code>
            </div>
          ))}
        </div>
        <div className="validation-msg validation-warning" style={{ fontSize: 12 }}>
          ℹ These are set via environment variables at server start. Changes
          require a server restart.
        </div>
      </div>

      {/* Renderer */}
      <div className="card stack">
        <h2>Renderer & Avatar Engine</h2>
        <div className="stack" style={{ gap: 8 }}>
          {[
            {
              label: 'Remotion composition',
              value: 'compositor/remotion_renderer',
            },
            {
              label: 'Avatar engine',
              value: 'pipeline/direction/avatar.py',
            },
            { label: 'Assembly output', value: 'episodes/{project}/{episode}/' },
          ].map((item) => (
            <div key={item.label} className="row-between">
              <span className="text-muted" style={{ fontSize: 13 }}>
                {item.label}
              </span>
              <code
                className="font-mono"
                style={{
                  fontSize: 11,
                  padding: '3px 8px',
                  background: 'var(--surface-inset)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                {item.value}
              </code>
            </div>
          ))}
        </div>
        <div className="validation-msg validation-warning" style={{ fontSize: 12 }}>
          ℹ Renderer configuration is managed in compositor/config and
          avatar-engine/config.
        </div>
      </div>
    </div>
  </div>
);
