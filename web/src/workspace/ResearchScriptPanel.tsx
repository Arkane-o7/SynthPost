import React from "react";
import { api } from "../api/client";
import { useStudio } from "../state/useStudio";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import type { ResearchPack } from "../contracts";
import { ScriptPanel } from "./ScriptPanel";

export const ResearchScriptPanel: React.FC<{ storyId: string }> = ({
  storyId,
}) => {
  const studio = useStudio();
  const [pack, setPack] = React.useState<ResearchPack | null>(null);
  const [busy, setBusy] = React.useState(false);

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

  const act = async () => {
    try {
      studio.setError("");
      setBusy(true);
      await api.researchAndScript(storyId);
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
      <div className="animate-fade-in">
        <EmptyState
          icon="✦"
          title={activeJob ? "Building your editorial draft" : "Research and write in one pass"}
          description={
            activeJob
              ? `${activeJob.stage} · ${Math.round(activeJob.progress)}%. SynthPost will move from source research into script writing automatically.`
              : "One action gathers multiple sources, extracts supported claims, and writes the first broadcast script. You can inspect both in the same workspace."
          }
        >
          <button
            className="btn-primary btn-lg"
            disabled={busy || Boolean(activeJob)}
            onClick={() => void act()}
          >
            {activeJob ? "Researching & Writing…" : "Research & Write Draft"}
          </button>
        </EmptyState>
      </div>
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
