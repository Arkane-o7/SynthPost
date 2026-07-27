import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import {
  isNarrationMode,
  NarrationModeSelector,
} from "../components/NarrationModeSelector";
import { StatusBadge } from "../components/StatusBadge";
import type { NarrationMode, ResearchPack } from "../contracts";
import { ScriptPanel } from "./ScriptPanel";

export const ResearchScriptPanel: React.FC<{ storyId: string }> = ({
  storyId,
}) => {
  const studio = useStudio();
  const [pack, setPack] = React.useState<ResearchPack | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [targetDurationSeconds, setTargetDurationSeconds] = React.useState(600);
  const [narrationMode, setNarrationMode] =
    React.useState<NarrationMode>("explained");

  const load = React.useCallback(() => {
    void api
      .readResearch(storyId)
      .then(setPack)
      .catch(() => setPack(null));
  }, [storyId]);

  React.useEffect(() => {
    load();
  }, [load, studio.lastJobEventTimestamp]);

  const editorialJobs = studio.jobs.filter(
    (job) =>
      job.story_id === storyId &&
      ["research", "script_generate"].includes(job.job_type),
  );
  const activeJob = editorialJobs.find((job) =>
    ["queued", "running"].includes(job.status),
  );
  const latestConfiguredJob = editorialJobs.find(
    (job) =>
      job.payload?.target_duration_seconds != null ||
      job.payload?.narration_mode != null,
  );
  const latestRequestedDuration = Number(
    latestConfiguredJob?.payload?.target_duration_seconds,
  );
  const latestRequestedMode = latestConfiguredJob?.payload?.narration_mode;

  React.useEffect(() => {
    if (Number.isFinite(latestRequestedDuration)) {
      setTargetDurationSeconds(
        Math.max(60, Math.min(7200, Math.round(latestRequestedDuration))),
      );
    }
  }, [latestRequestedDuration]);

  React.useEffect(() => {
    if (isNarrationMode(latestRequestedMode)) {
      setNarrationMode(latestRequestedMode);
    }
  }, [latestRequestedMode]);

  const normalizedTargetDuration = Math.max(
    60,
    Math.min(7200, Math.round(Number(targetDurationSeconds) || 600)),
  );

  const act = async () => {
    try {
      studio.setError("");
      setBusy(true);
      await api.researchAndScript(
        storyId,
        undefined,
        normalizedTargetDuration,
        narrationMode,
      );
      await studio.refreshAll();
      load();
    } catch (error) {
      studio.setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  if (!pack) {
    return (
      <section className="research-script-setup animate-fade-in">
        <header className="research-script-setup-heading">
          <div>
            <div className="generation-ledger-kicker">Editorial setup</div>
            <h2>Configure the research and script</h2>
            <p>
              Choose the narration format and target runtime before SynthPost
              researches the story and writes the first draft.
            </p>
          </div>
          {activeJob && (
            <StatusBadge tone="blue">
              {activeJob.job_type === "research" ? "Researching" : "Writing"}
              {" · "}
              {Math.round(activeJob.progress)}%
            </StatusBadge>
          )}
        </header>

        <NarrationModeSelector
          value={narrationMode}
          durationSeconds={normalizedTargetDuration}
          disabled={busy || Boolean(activeJob)}
          onChange={setNarrationMode}
        />

        <div className="research-script-setup-footer">
          <label className="research-script-duration">
            Target video length
            <div className="research-script-duration-input">
              <input
                type="number"
                min={60}
                max={7200}
                step={5}
                value={targetDurationSeconds}
                disabled={busy || Boolean(activeJob)}
                onChange={(event) =>
                  setTargetDurationSeconds(Number(event.target.value))
                }
              />
              <span>seconds</span>
            </div>
          </label>

          <div className="research-script-commit">
            <p aria-live="polite">
              {activeJob
                ? `${activeJob.stage} · SynthPost will continue from research into script generation automatically.`
                : "Nothing starts until you confirm these settings."}
            </p>
            <button
              type="button"
              className="btn-primary btn-lg"
              disabled={busy || Boolean(activeJob)}
              onClick={() => void act()}
            >
              {activeJob
                ? "Researching & Writing…"
                : "Research & Generate Script"}
            </button>
          </div>
        </div>
      </section>
    );
  }

  const supportedClaims = pack.claims.filter((claim) => claim.supported);

  return (
    <div className="draft-desk animate-fade-in">
      <aside className="draft-source-rail">
        <div className="draft-source-heading">
          <div>
            <div className="generation-ledger-kicker">Source dossier</div>
            <h2>Evidence behind the script</h2>
          </div>
          <StatusBadge tone="green">
            {supportedClaims.length}/{pack.claims.length} supported
          </StatusBadge>
        </div>

        <p className="draft-research-summary">{pack.research_summary}</p>

        <div className="draft-source-metrics">
          <span><b>{pack.documents.length}</b> sources</span>
          <span><b>{pack.claims.length}</b> claims</span>
          <span><b>{pack.uncertainties.length}</b> caveats</span>
        </div>

        <section className="draft-source-section">
          <h3>Sources</h3>
          <div className="draft-source-list">
            {pack.documents.map((document, index) => (
              <article key={document.document_id} className="draft-source-item">
                <span className="draft-source-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  {document.url ? (
                    <a href={document.url} target="_blank" rel="noreferrer">
                      {document.title} ↗
                    </a>
                  ) : (
                    <strong>{document.title}</strong>
                  )}
                  <small>
                    {document.publisher || "Editor-provided"}
                    {document.relevance_score != null
                      ? ` · ${Math.round(document.relevance_score * 100)}% match`
                      : ""}
                  </small>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="draft-source-section">
          <h3>Key claims</h3>
          <div className="draft-claim-list">
            {pack.claims.slice(0, 8).map((claim) => (
              <article key={claim.claim_id} className="draft-claim-item">
                <span className={claim.supported ? "is-supported" : ""}>
                  {claim.supported ? "✓" : "?"}
                </span>
                <div>
                  <p>{claim.claim_text}</p>
                  <small>
                    {Math.round(claim.confidence * 100)}% confidence ·{" "}
                    {claim.evidence_ids.length} evidence link
                    {claim.evidence_ids.length === 1 ? "" : "s"}
                  </small>
                </div>
              </article>
            ))}
          </div>
        </section>

        {(pack.contradictions.length > 0 || pack.uncertainties.length > 0) && (
          <details className="draft-caveats">
            <summary>
              Caveats ({pack.contradictions.length + pack.uncertainties.length})
            </summary>
            <ul>
              {[...pack.contradictions, ...pack.uncertainties].map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        )}

        <button disabled={busy || Boolean(activeJob)} onClick={() => void act()}>
          {activeJob ? "Updating draft…" : "Refresh Research & Rewrite"}
        </button>
      </aside>

      <main className="draft-script-workspace">
        <div className="draft-script-heading">
          <div>
            <div className="generation-ledger-kicker">Broadcast draft</div>
            <h2>Script editor</h2>
          </div>
          {activeJob && (
            <StatusBadge tone="blue">
              {activeJob.job_type === "research" ? "Researching" : "Writing"} ·{" "}
              {Math.round(activeJob.progress)}%
            </StatusBadge>
          )}
        </div>
        <ScriptPanel storyId={storyId} />
      </main>
    </div>
  );
};
