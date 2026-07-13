import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import type { GenerationAudit, NarrationMode, ScriptDocument } from "../contracts";

const NARRATION_MODES: Array<{
  id: NarrationMode;
  label: string;
  range: string;
  minSeconds: number;
  maxSeconds: number;
  marker: string;
  description: string;
}> = [
  {
    id: "signal",
    label: "Signal",
    range: "3–5 min",
    minSeconds: 180,
    maxSeconds: 300,
    marker: "01",
    description: "Fast, decisive: what happened, why now, who is affected, what comes next.",
  },
  {
    id: "explained",
    label: "Explained",
    range: "8–12 min",
    minSeconds: 480,
    maxSeconds: 720,
    marker: "02",
    description: "The main format: event, context, system, consequences and uncertainty.",
  },
  {
    id: "deep_dive",
    label: "Deep Dive",
    range: "15–25 min",
    minSeconds: 900,
    maxSeconds: 1500,
    marker: "03",
    description: "Patient and investigative: evidence, stakeholders, trade-offs and scenarios.",
  },
  {
    id: "india_builds",
    label: "India Builds",
    range: "30–120 min",
    minSeconds: 1800,
    maxSeconds: 7200,
    marker: "04",
    description: "Documentary systems narration for infrastructure, industry and national capability.",
  },
];

const NarrationModeSelector: React.FC<{
  value: NarrationMode;
  durationSeconds: number;
  disabled?: boolean;
  onChange: (mode: NarrationMode) => void;
}> = ({ value, durationSeconds, disabled, onChange }) => {
  const selected = NARRATION_MODES.find((mode) => mode.id === value)!;
  const outsideRange =
    durationSeconds < selected.minSeconds || durationSeconds > selected.maxSeconds;

  return (
    <fieldset className="narration-mode-fieldset" disabled={disabled}>
      <legend>
        <span>Narration format</span>
        <small>Independent from runtime</small>
      </legend>
      <div className="narration-mode-grid">
        {NARRATION_MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            data-narration-mode={mode.id}
            className={`narration-mode-card ${value === mode.id ? "is-selected" : ""}`}
            aria-pressed={value === mode.id}
            onClick={() => onChange(mode.id)}
          >
            <span className="narration-mode-marker">{mode.marker}</span>
            <span className="narration-mode-copy">
              <strong>SynthPost {mode.label}</strong>
              <small>{mode.range}</small>
              <em>{mode.description}</em>
            </span>
            <span className="narration-mode-check" aria-hidden="true">✓</span>
          </button>
        ))}
      </div>
      <p className={`narration-mode-guidance ${outsideRange ? "is-warning" : ""}`}>
        {outsideRange
          ? `${selected.label} is designed for ${selected.range}; your custom runtime will still be respected.`
          : `${selected.label} pacing matches the selected ${Math.round(durationSeconds / 60)}-minute runtime.`}
      </p>
    </fieldset>
  );
};

export const ScriptPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [script, setScript] = React.useState<ScriptDocument | null>(null);
  const [headline, setHeadline] = React.useState("");
  const [text, setText] = React.useState("");
  const [targetDurationSeconds, setTargetDurationSeconds] = React.useState(600);
  const [narrationMode, setNarrationMode] = React.useState<NarrationMode>("explained");
  const [busy, setBusy] = React.useState(false);
  const [audits, setAudits] = React.useState<GenerationAudit[]>([]);

  const story = studio.candidates.find(
    (candidate) => candidate.story_id === storyId,
  );
  const scriptJobs = studio.jobs.filter(
    (job) => job.story_id === storyId && job.job_type === "script_generate",
  );
  const activeScriptJob = scriptJobs.find((job) =>
    ["queued", "running"].includes(job.status),
  );
  const latestScriptJob = scriptJobs[0];
  const latestRequestedDuration = Number(
    latestScriptJob?.payload?.target_duration_seconds,
  );
  const latestRequestedMode = latestScriptJob?.payload?.narration_mode;
  const isGenerating = busy || Boolean(activeScriptJob);
  const providerWarning = script?.warnings?.find((warning) =>
    warning.startsWith("llm_provider="),
  );
  const isOfflineDraft = providerWarning === "llm_provider=mock";
  const warningList = script?.warnings ?? [];
  const generationDetails = warningList.filter(
    (warning) =>
      warning.startsWith("llm_") || warning.startsWith("structured_attempts="),
  );
  const nonBlockingClaimWarnings = warningList.filter((warning) =>
    /sec_\d+_(cold_open|outro): no linked claim_ids/.test(warning),
  );
  const editorialWarnings = warningList.filter(
    (warning) =>
      !generationDetails.includes(warning) &&
      !nonBlockingClaimWarnings.includes(warning),
  );
  const missingClaimWarnings = editorialWarnings.filter((warning) =>
    warning.endsWith(": no linked claim_ids"),
  );
  const otherEditorialWarnings = editorialWarnings.filter(
    (warning) => !missingClaimWarnings.includes(warning),
  );
  const missingClaimSections = missingClaimWarnings.map((warning) =>
    warning.replace(": no linked claim_ids", ""),
  );

  const load = React.useCallback(() => {
    api
      .readScript(storyId)
      .then((s) => {
        setScript(s);
        setHeadline(s?.headline ?? "");
        setText(s?.sections.map((sec) => sec.text).join("\n\n") ?? "");
        if (s?.narration_mode) setNarrationMode(s.narration_mode);
      })
      .catch(() => setScript(null));
  }, [storyId, studio.lastJobEventTimestamp]);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    void api
      .listGenerationAudits(storyId)
      .then(setAudits)
      .catch(() => setAudits([]));
  }, [storyId, studio.lastJobEventTimestamp]);

  React.useEffect(() => {
    if (Number.isFinite(latestRequestedDuration)) {
      setTargetDurationSeconds(
        Math.max(60, Math.min(7200, Math.round(latestRequestedDuration))),
      );
    }
  }, [latestRequestedDuration]);

  React.useEffect(() => {
    if (NARRATION_MODES.some((mode) => mode.id === latestRequestedMode)) {
      setNarrationMode(latestRequestedMode as NarrationMode);
    }
  }, [latestRequestedMode]);

  const normalizedTargetDuration = Math.max(
    60,
    Math.min(7200, Math.round(Number(targetDurationSeconds) || 600)),
  );

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError("");
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
    const manualHeadline = headline.trim() || story?.title || "Manual story";
    const canSaveManual = Boolean(text.trim());

    return (
      <div className="stack-lg animate-fade-in">
        <EmptyState
          icon="📝"
          title={
            activeScriptJob ? "Script generation running" : "No script yet"
          }
          description={
            activeScriptJob
              ? `Current job is ${activeScriptJob.status} at ${Math.round(activeScriptJob.progress)}% (${activeScriptJob.stage}).`
              : "Generate a broadcast script from the research pack, create an offline draft, or write one manually."
          }
        >
          <div className="stack" style={{ alignItems: "center" }}>
            <NarrationModeSelector
              value={narrationMode}
              durationSeconds={normalizedTargetDuration}
              disabled={isGenerating}
              onChange={setNarrationMode}
            />
            <label style={{ minWidth: 260, textAlign: "left" }}>
              Target video length
              <div className="row-tight">
                <input
                  type="number"
                  min={60}
                  max={7200}
                  step={5}
                  value={targetDurationSeconds}
                  onChange={(e) =>
                    setTargetDurationSeconds(Number(e.target.value))
                  }
                />
                <span className="text-muted" style={{ fontSize: 12 }}>
                  seconds
                </span>
              </div>
            </label>
            <div className="row" style={{ justifyContent: "center" }}>
              <button
                className="btn-primary btn-lg"
                disabled={isGenerating}
                onClick={() =>
                  act(() =>
                    api.generateScript(
                      storyId,
                      undefined,
                      normalizedTargetDuration,
                      narrationMode,
                    ),
                  )
                }
              >
                {isGenerating ? "Generating…" : "Generate with AI"}
              </button>
            </div>
          </div>
        </EmptyState>

        {latestScriptJob?.status === "failed" && (
          <div className="validation-msg validation-warning">
            Script generation failed:{" "}
            {latestScriptJob.error || latestScriptJob.stage}. Adjust the target
            length, retry the hosted provider, or write the script manually below.
          </div>
        )}

        <div className="card stack">
          <h2>Write Script Manually</h2>
          <p className="text-muted" style={{ fontSize: 13 }}>
            This bypasses AI generation and moves the story into script review.
            Use it when an editor deliberately wants to author the script.
          </p>
          <label>
            Headline
            <input
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder={story?.title || "Story headline"}
            />
          </label>
          <label>
            Script text
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Write the anchor narration here…"
              style={{ minHeight: 220 }}
            />
          </label>
          <button
            className="btn-primary"
            disabled={busy || !canSaveManual}
            onClick={() =>
              act(() => api.saveManualScript(storyId, manualHeadline, text))
            }
          >
            Save Manual Script
          </button>
        </div>
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
            <button
              key={sec.section_id}
              className="btn-ghost"
              style={{ padding: "8px 10px" }}
            >
              <div style={{ fontWeight: 600, fontSize: 12 }}>
                {sec.section_type}
              </div>
              <div className="text-muted" style={{ fontSize: 11 }}>
                {Math.round(sec.estimated_duration_seconds)}s ·{" "}
                {sec.approval_status}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Script editor */}
      <div className="card stack">
        <h2>Script Editor</h2>
        {isOfflineDraft && (
          <div className="validation-msg validation-warning">
            This is an offline/mock draft. Regenerate with your configured AI
            provider before approving it for production.
          </div>
        )}
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
        <label style={{ maxWidth: 280 }}>
          Target video length for regenerate
          <div className="row-tight">
            <input
              type="number"
              min={60}
              max={7200}
              step={5}
              value={targetDurationSeconds}
              onChange={(e) => setTargetDurationSeconds(Number(e.target.value))}
            />
            <span className="text-muted" style={{ fontSize: 12 }}>
              seconds
            </span>
          </div>
        </label>
        <NarrationModeSelector
          value={narrationMode}
          durationSeconds={normalizedTargetDuration}
          disabled={isGenerating}
          onChange={setNarrationMode}
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
            className={isOfflineDraft ? "btn-primary" : undefined}
            disabled={isGenerating}
            onClick={() =>
              act(() =>
                api.generateScript(
                  storyId,
                  undefined,
                  normalizedTargetDuration,
                  narrationMode,
                ),
              )
            }
          >
            {isGenerating ? "Generating…" : "Regenerate with AI"}
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

        {(missingClaimWarnings.length > 0 ||
          otherEditorialWarnings.length > 0) && (
          <div>
            <h3>⚠ Editorial checks</h3>
            <div className="stack" style={{ marginTop: 4 }}>
              {missingClaimWarnings.length > 0 && (
                <div className="validation-msg validation-warning">
                  {missingClaimWarnings.length} factual section
                  {missingClaimWarnings.length === 1 ? "" : "s"} need linked
                  research claims: {missingClaimSections.join(", ")}.
                </div>
              )}
              {otherEditorialWarnings.map((w) => (
                <div key={w} className="validation-msg validation-warning">
                  {w}
                </div>
              ))}
            </div>
          </div>
        )}

        {generationDetails.length > 0 && (
          <details>
            <summary className="text-muted" style={{ cursor: "pointer" }}>
              Generation details
            </summary>
            <div className="stack" style={{ marginTop: 8 }}>
              {generationDetails.map((w) => (
                <div key={w} className="text-muted" style={{ fontSize: 12 }}>
                  {w}
                </div>
              ))}
            </div>
          </details>
        )}

        <div className="text-muted" style={{ fontSize: 12, marginTop: 8 }}>
          Approved scripts are immutable. Saving creates a new revision.
        </div>
      </div>

      <div className="card stack generation-ledger">
        <div className="row-between">
          <div>
            <div className="generation-ledger-kicker">Inspectable AI</div>
            <h2>Generation Ledger</h2>
          </div>
          <span className="generation-ledger-count">{audits.length} records</span>
        </div>
        <p className="text-muted" style={{ fontSize: 12 }}>
          Every stored prompt, model response, validation attempt and normalization
          decision for this story. New records use editorial charter v1.
        </p>
        {audits.length === 0 ? (
          <div className="generation-ledger-empty">
            Existing scripts predate prompt auditing. Regenerate to create the first record.
          </div>
        ) : (
          <div className="generation-ledger-list">
            {audits.map((audit) => (
              <details key={audit.audit_id} className="generation-audit-record">
                <summary>
                  <span>
                    <b>{audit.stage.replace(/_/g, " ")}</b>
                    <small>{audit.prompt_version}</small>
                  </span>
                  <span>
                    <b>{audit.provider}</b>
                    <small>{audit.model || "model unavailable"}</small>
                  </span>
                  <StatusBadge status={audit.status}>{audit.status}</StatusBadge>
                </summary>
                <div className="generation-audit-body">
                  <div className="generation-audit-meta">
                    <span>Charter {audit.charter_version}</span>
                    <span>{audit.attempts.length} attempt{audit.attempts.length === 1 ? "" : "s"}</span>
                    <span>{audit.normalization_events.length} normalization decision{audit.normalization_events.length === 1 ? "" : "s"}</span>
                  </div>
                  <details>
                    <summary>Exact prompt</summary>
                    <pre>{audit.prompt_text}</pre>
                  </details>
                  <details>
                    <summary>Raw model response</summary>
                    <pre>{JSON.stringify(audit.response, null, 2)}</pre>
                  </details>
                  <details>
                    <summary>Validation attempts</summary>
                    <pre>{JSON.stringify(audit.validation_events, null, 2)}</pre>
                  </details>
                  <details>
                    <summary>Normalization decisions</summary>
                    <pre>{JSON.stringify(audit.normalization_events, null, 2)}</pre>
                  </details>
                </div>
              </details>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
