import React from "react";
import { api, artifactUrl } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import type { VisualCandidate } from "../contracts";

export const VisualsPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [visuals, setVisuals] = React.useState<VisualCandidate[]>([]);
  const [path, setPath] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [attributions, setAttributions] = React.useState<Record<string, string>>(
    {},
  );

  const load = React.useCallback(
    () =>
      api
        .listVisuals(storyId)
        .then((items) => {
          setVisuals(items);
          setAttributions((current) => {
            const next = { ...current };
            for (const item of items) {
              if (!(item.asset_id in next)) {
                next[item.asset_id] = item.attribution_text ?? "";
              }
            }
            return next;
          });
        })
        .catch(() => setVisuals([])),
    [storyId, studio.lastJobEventTimestamp],
  );
  React.useEffect(() => {
    void load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      studio.setError("");
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
            Search Local + Web Visuals
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
                  rights_tier: "yellow",
                });
                setPath("");
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
          title="No local visuals staged"
          description="Search the local drop folder and your configured SearXNG instance, or upload rights-cleared media. Web results remain review leads until a local file and valid usage basis are confirmed."
        />
      ) : (
        <div className="grid grid-3">
          {visuals.map((v) => (
            <div
              key={v.asset_id}
              className={`visual-card rights-${v.rights_tier}`}
            >
              <div className="visual-thumb">
                {v.content_role === "fallback" ? (
                  <div style={{ textAlign: "center", padding: 16 }}>
                    <div style={{ fontSize: 30 }}>🎙️</div>
                    <div className="text-muted" style={{ fontSize: 11 }}>
                      Presenter-only fallback
                    </div>
                  </div>
                ) : v.thumbnail_path ? (
                  <img src={artifactUrl(v.thumbnail_path)} alt={v.title} />
                ) : (
                  <span style={{ fontSize: 24, opacity: 0.3 }}>
                    {v.media_type === "image"
                      ? "🖼"
                      : v.media_type === "video"
                        ? "🎬"
                        : "📄"}
                  </span>
                )}
              </div>
              <div className="visual-body">
                <strong className="truncate" style={{ fontSize: 13 }}>
                  {v.title}
                </strong>
                <div className="row-tight">
                  <StatusBadge
                    tone={
                      v.rights_tier === "green"
                        ? "green"
                        : v.rights_tier === "red"
                          ? "red"
                          : "amber"
                    }
                  >
                    {v.rights_tier}
                  </StatusBadge>
                  <StatusBadge status={v.review_status}>
                    {v.review_status}
                  </StatusBadge>
                  <StatusBadge
                    tone={
                      v.content_cleanliness_status === "passed"
                        ? "green"
                        : v.content_cleanliness_status === "rejected"
                          ? "red"
                          : "amber"
                    }
                  >
                    {v.content_cleanliness_status.replace("_", " ")}
                  </StatusBadge>
                </div>
                <div className="text-muted" style={{ fontSize: 12 }}>
                  {v.provider} · {v.content_role}
                </div>
                <div className="text-muted" style={{ fontSize: 11 }}>
                  {v.width && v.height ? `${v.width}×${v.height} · ` : ""}
                  source: {v.source_identity || v.source_domain || "unknown"}
                  {v.source_verified ? " · verified registry entry" : ""}
                </div>
                {v.source_url && (
                  <a
                    href={v.source_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: 12 }}
                  >
                    Open source page ↗
                  </a>
                )}

                {!v.download_path &&
                  !v.quarantine_path &&
                  v.content_role !== "fallback" && (
                  <div className="rights-warning warn-amber">
                    Research lead only — no local render file
                  </div>
                )}
                {v.quarantine_path && (
                  <div className="rights-warning warn-red">
                    Quarantined — local file is blocked from the timeline
                  </div>
                )}

                {v.contact_sheet_path && (
                  <img
                    src={artifactUrl(v.contact_sheet_path)}
                    alt={`Analysis contact sheet for ${v.title}`}
                    style={{
                      width: "100%",
                      borderRadius: 6,
                      border: "1px solid rgba(255,255,255,0.12)",
                    }}
                  />
                )}

                {v.content_role !== "fallback" && (
                  <details style={{ fontSize: 11 }}>
                    <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                      Source & content evidence
                    </summary>
                    <div className="stack" style={{ marginTop: 8, gap: 5 }}>
                      <div>Source class: {v.source_class}</div>
                      {v.source_channel_name && (
                        <div>Channel: {v.source_channel_name}</div>
                      )}
                      <div>
                        Clean B-roll score: {Math.round(v.clean_broll_score * 100)}%
                      </div>
                      <div>Frames scanned: {v.scan_timestamps.length}</div>
                      <div>
                        Detected brands: {v.detected_brands.join(", ") || "none"}
                      </div>
                      <div>
                        Flags: {[
                          v.contains_third_party_logo && "third-party logo",
                          v.contains_lower_third && "lower-third",
                          v.contains_ticker && "ticker",
                          v.contains_presenter && "presenter package",
                        ]
                          .filter(Boolean)
                          .join(", ") || "none"}
                      </div>
                      {v.content_analysis_evidence.map((item) => (
                        <div key={`evidence-${item}`}>• {item}</div>
                      ))}
                      {v.approval_blockers.map((item) => (
                        <div
                          key={`blocker-${item}`}
                          style={{ color: "#ff8f87" }}
                        >
                          ⛔ {item}
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {/* Rights warnings */}
                {v.rights_tier === "yellow" && (
                  <div className="rights-warning warn-amber">
                    ⚠ Manual review recommended
                  </div>
                )}
                {v.rights_tier === "red" && (
                  <div className="rights-warning warn-red">
                    ⛔ Rights concern — review before use
                  </div>
                )}
                {v.warnings.map((warning) => (
                  <div
                    key={warning}
                    className="text-muted"
                    style={{ fontSize: 11, lineHeight: 1.4 }}
                  >
                    {warning}
                  </div>
                ))}

                {/* Attribution */}
                {v.content_role !== "fallback" && (
                  <input
                    value={attributions[v.asset_id] ?? v.attribution_text ?? ""}
                    placeholder="Attribution text…"
                    style={{ fontSize: 12 }}
                    onChange={(e) =>
                      setAttributions((current) => ({
                        ...current,
                        [v.asset_id]: e.target.value,
                      }))
                    }
                    onBlur={(e) =>
                      void api
                        .updateVisual(v.asset_id, {
                          attribution_text: e.target.value,
                        })
                        .then(load)
                    }
                  />
                )}

                {/* Actions */}
                <div className="row-tight">
                  <button
                    style={{ fontSize: 12, padding: "5px 10px" }}
                    disabled={
                      busy ||
                      (!v.download_path && !v.quarantine_path) ||
                      v.content_role === "fallback"
                    }
                    onClick={() => act(() => api.analyzeVisual(v.asset_id))}
                  >
                    Analyze
                  </button>
                  <button
                    className="btn-success"
                    style={{ fontSize: 12, padding: "5px 10px" }}
                    disabled={
                      !v.download_path ||
                      v.content_role === "fallback" ||
                      v.content_cleanliness_status !== "passed" ||
                      v.approval_blockers.length > 0
                    }
                    onClick={() =>
                      act(() =>
                        api.manualApproveVisual(
                          v.asset_id,
                          attributions[v.asset_id] ??
                            v.attribution_text ??
                            undefined,
                        ),
                      )
                    }
                  >
                    {v.content_role === "fallback"
                      ? "Automatic"
                      : v.download_path
                        ? "✓ Approve"
                        : "Lead only"}
                  </button>
                  <button
                    className="btn-danger"
                    style={{ fontSize: 12, padding: "5px 10px" }}
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
