import React from "react";
import { api, artifactUrl } from "../api/client";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import type { ScriptDocument, ScriptSection, VisualCandidate } from "../contracts";

const sectionLabel = (value: string) =>
  value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

type VisualFilter =
  | "local"
  | "review"
  | "approved"
  | "video"
  | "image"
  | "leads"
  | "rejected"
  | "all";

const isEditorialVisual = (visual: VisualCandidate) =>
  visual.content_role !== "fallback";

const isLocalMedia = (visual: VisualCandidate) =>
  Boolean(visual.download_path) && isEditorialVisual(visual);

const isReadyToApprove = (visual: VisualCandidate) =>
  Boolean(visual.download_path) &&
  visual.content_role !== "fallback" &&
  !["approved", "manual_approved"].includes(visual.review_status);

const isLeadOnly = (visual: VisualCandidate) =>
  !visual.download_path && !visual.quarantine_path && isEditorialVisual(visual);

const isApproved = (visual: VisualCandidate) =>
  ["approved", "manual_approved"].includes(visual.review_status);

const isRejected = (visual: VisualCandidate) =>
  ["rejected", "blocked"].includes(visual.review_status);

const matchesFilter = (visual: VisualCandidate, filter: VisualFilter) => {
  if (!isEditorialVisual(visual)) return false;
  if (filter === "local") return isLocalMedia(visual) && !isRejected(visual);
  if (filter === "review") return isReadyToApprove(visual) && !isRejected(visual);
  if (filter === "approved") return isApproved(visual);
  if (filter === "video") return visual.media_type === "video";
  if (filter === "image") return visual.media_type === "image";
  if (filter === "leads") return isLeadOnly(visual);
  if (filter === "rejected") return isRejected(visual);
  return true;
};

const VisualCandidateCard: React.FC<{
  visual: VisualCandidate;
  busy: boolean;
  attribution: string;
  onAttributionChange: (value: string) => void;
  onAttributionSave: (value: string) => void;
  onDownload: () => void;
  onAnalyze: () => void;
  onApprove: () => void;
  onReject: () => void;
}> = ({
  visual: v,
  busy,
  attribution,
  onAttributionChange,
  onAttributionSave,
  onDownload,
  onAnalyze,
  onApprove,
  onReject,
}) => (
  <article className={`visual-card visual-carousel-card rights-${v.rights_tier}`}>
    <div className="visual-thumb">
      {v.content_role === "fallback" ? (
        <div className="visual-fallback-thumb">
          <div aria-hidden="true">🎙️</div>
          <span>Presenter-only fallback</span>
        </div>
      ) : v.thumbnail_path ? (
        <img src={artifactUrl(v.thumbnail_path)} alt={v.title} />
      ) : (
        <span className="visual-media-placeholder" aria-hidden="true">
          {v.media_type === "image" ? "🖼" : v.media_type === "video" ? "🎬" : "📄"}
        </span>
      )}
      {v.media_type === "image" || v.media_type === "video" ? (
        <div
          className={`visual-media-type visual-media-type-${v.media_type}`}
          aria-label={`Media type: ${v.media_type}`}
        >
          <span aria-hidden="true">{v.media_type === "video" ? "▶" : "▣"}</span>
          {v.media_type}
        </div>
      ) : null}
      <div className="visual-card-rank">
        {Math.round((v.relevance_score + v.visual_quality_score) * 50)}
        <span>fit</span>
      </div>
    </div>
    <div className="visual-body">
      <strong className="visual-card-title">{v.title || "Untitled visual"}</strong>
      <div className="row-tight">
        <StatusBadge
          tone={v.rights_tier === "green" ? "green" : v.rights_tier === "red" ? "red" : "amber"}
        >
          {v.rights_tier}
        </StatusBadge>
        <StatusBadge status={v.review_status}>{v.review_status}</StatusBadge>
      </div>
      <div className="visual-card-meta">
        <span>{v.provider}</span>
        <span>{v.content_role.split("_").join(" ")}</span>
        {v.width && v.height ? <span>{v.width}×{v.height}</span> : null}
      </div>
      <div className="text-muted" style={{ fontSize: 11 }}>
        Source: {v.source_identity || v.source_domain || "unknown"}
        {v.source_verified ? " · verified" : ""}
      </div>
      {v.source_url && (
        <a href={v.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
          Open source page ↗
        </a>
      )}

      {!v.download_path && !v.quarantine_path && v.content_role !== "fallback" && (
        <div className="rights-warning warn-amber">Research lead only — no local render file</div>
      )}
      {v.quarantine_path && (
        <div className="rights-warning warn-amber">Legacy quarantined file — restore it for editor review</div>
      )}

      {v.contact_sheet_path && (
        <img
          className="visual-contact-sheet"
          src={artifactUrl(v.contact_sheet_path)}
          alt={`Analysis contact sheet for ${v.title}`}
        />
      )}

      {v.content_role !== "fallback" && (
        <details className="visual-evidence">
          <summary>Source details</summary>
          <div className="stack">
            <div>Source class: {v.source_class}</div>
            {v.source_channel_name && <div>Channel: {v.source_channel_name}</div>}
            <div>License metadata: {v.license || "not provided"}</div>
            <div>Usage basis: {v.usage_basis.split("_").join(" ")}</div>
          </div>
        </details>
      )}

      {v.rights_tier === "yellow" && <div className="rights-warning warn-amber">⚠ Manual review recommended</div>}
      {v.rights_tier === "red" && <div className="rights-warning warn-red">⛔ Rights concern — review before use</div>}
      {v.warnings.filter((warning) => !/cleanliness|publisher branding|lower-third|ticker|presenter package|source metadata preflight|competing publisher/i.test(warning) && !(v.download_path && /video download failed|research lead only|requested format is not available|yt-dlp completed without/i.test(warning))).map((warning) => (
        <div key={warning} className="text-muted visual-warning">{warning}</div>
      ))}

      {v.content_role !== "fallback" && (
        <input
          value={attribution}
          placeholder="Attribution text…"
          className="visual-attribution"
          onChange={(event) => onAttributionChange(event.target.value)}
          onBlur={(event) => onAttributionSave(event.target.value)}
        />
      )}

      <div className="row-tight visual-card-actions">
        {isLeadOnly(v) ? (
          v.media_type === "video" ? (
            <button
              type="button"
              className="btn-download"
              disabled={busy}
              title="Download a local, renderable copy of this video, then review and approve it."
              onClick={onDownload}
            >
              {busy ? "Downloading…" : "↓ Download video"}
            </button>
          ) : (
            <button type="button" disabled title="This search result has no downloaded local media file.">
              No local file
            </button>
          )
        ) : v.quarantine_path ? (
          <button
            type="button"
            disabled={busy}
            title="Restore this legacy quarantined file to the editor-controlled review flow."
            onClick={onAnalyze}
          >
            Restore local
          </button>
        ) : null}
        <button
          type="button"
          className="btn-success"
          disabled={busy || !isReadyToApprove(v)}
          title={
            ["approved", "manual_approved"].includes(v.review_status)
              ? "This visual is already approved."
              : !v.download_path
                ? "Approval requires a downloaded local file."
                : undefined
          }
          onClick={onApprove}
        >
          {["approved", "manual_approved"].includes(v.review_status)
            ? "✓ Approved"
            : v.content_role === "fallback"
              ? "Automatic"
              : "✓ Approve"}
        </button>
        <button type="button" className="btn-danger" disabled={busy} onClick={onReject}>Reject</button>
      </div>
    </div>
  </article>
);

const SectionVisualRow: React.FC<{
  section: ScriptSection;
  index: number;
  lowerThird: string;
  visuals: VisualCandidate[];
  renderVisual: (visual: VisualCandidate) => React.ReactNode;
  onApproveAll: (visuals: VisualCandidate[]) => void;
  busy: boolean;
}> = ({ section, index, lowerThird, visuals, renderVisual, onApproveAll, busy }) => {
  const trackRef = React.useRef<HTMLDivElement>(null);
  const approvable = visuals.filter(isReadyToApprove);
  // Older saved scripts and a backend that was already running before timed
  // headlines were introduced do not include `headline_cues`. Keep the
  // Visuals workspace usable while those scripts are regenerated or migrated.
  const headlineCues =
    Array.isArray(section.headline_cues) && section.headline_cues.length > 0
      ? section.headline_cues
      : [lowerThird];
  const scroll = (direction: -1 | 1) => {
    trackRef.current?.scrollBy({ left: direction * 344, behavior: "smooth" });
  };

  return (
    <section className="visual-section-row" data-visual-section={section.section_id}>
      <header className="visual-section-brief">
        <div className="visual-section-index">{String(index + 1).padStart(2, "0")}</div>
        <div>
          <div className="visual-section-kicker">{sectionLabel(section.section_type)}</div>
          <h3>{section.text}</h3>
        </div>
        <div className="visual-lower-third">
          <span>Timed lower thirds · {headlineCues.length}</span>
          <div className="visual-headline-cues">
            {headlineCues.map((headline, cueIndex) => (
              <strong key={`${cueIndex}-${headline}`}>
                <i>{String(cueIndex + 1).padStart(2, "0")}</i>
                {headline}
              </strong>
            ))}
          </div>
        </div>
        <div className="visual-section-foot">
          <span>~{Math.round(section.estimated_duration_seconds)}s</span>
          <span>{visuals.length} candidate{visuals.length === 1 ? "" : "s"}</span>
        </div>
        {section.suggested_visual_types.length > 0 && (
          <div className="visual-direction">
            {section.suggested_visual_types.slice(0, 3).map((type) => (
              <span key={type}>{sectionLabel(type)}</span>
            ))}
          </div>
        )}
      </header>

      <div className="visual-carousel-shell">
        <div className="visual-carousel-heading">
          <div>
            <span className="visual-carousel-eyebrow">Recommended media</span>
            <strong>{visuals.length ? "Choose the shot that carries this beat" : "No candidates linked to this section"}</strong>
          </div>
          {visuals.length > 1 && (
            <div className="visual-carousel-controls" aria-label="Section visual actions">
              {approvable.length > 0 && (
                <button
                  type="button"
                  className="visual-batch-button visual-batch-approve"
                  disabled={busy}
                  onClick={() => onApproveAll(approvable)}
                >
                  Approve ready ({approvable.length})
                </button>
              )}
              <button type="button" className="visual-arrow-button" aria-label={`Previous visuals for section ${index + 1}`} onClick={() => scroll(-1)}>←</button>
              <button type="button" className="visual-arrow-button" aria-label={`Next visuals for section ${index + 1}`} onClick={() => scroll(1)}>→</button>
            </div>
          )}
        </div>
        {visuals.length ? (
          <div className="visual-carousel-track" data-visual-carousel={section.section_id} ref={trackRef} tabIndex={0}>
            {visuals.map(renderVisual)}
          </div>
        ) : (
          <div className="visual-carousel-empty">
            <span aria-hidden="true">＋</span>
            <p>Search again or stage media specifically for this section.</p>
          </div>
        )}
      </div>
    </section>
  );
};

export const VisualsPanel: React.FC<{ storyId: string }> = ({ storyId }) => {
  const studio = useStudio();
  const [visuals, setVisuals] = React.useState<VisualCandidate[]>([]);
  const [script, setScript] = React.useState<ScriptDocument | null>(null);
  const [path, setPath] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [filter, setFilter] = React.useState<VisualFilter>("local");
  const [localFolder, setLocalFolder] = React.useState("");
  const [attributions, setAttributions] = React.useState<Record<string, string>>(
    {},
  );
  const reviewPositionRef = React.useRef<{
    scrollY: number;
    sectionId?: string;
    sectionViewportTop?: number;
    carousels: Record<string, number>;
  } | null>(null);

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
  React.useEffect(() => {
    void api.readScript(storyId).then(setScript).catch(() => setScript(null));
  }, [storyId, studio.lastJobEventTimestamp]);
  React.useEffect(() => {
    void api
      .localVisualFolder(storyId)
      .then((value) => setLocalFolder(value.path))
      .catch(() => setLocalFolder(""));
  }, [storyId]);

  const captureReviewPosition = () => {
    const active =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const section = active?.closest<HTMLElement>("[data-visual-section]");
    const carousels: Record<string, number> = {};
    document
      .querySelectorAll<HTMLElement>("[data-visual-carousel]")
      .forEach((track) => {
        const key = track.dataset.visualCarousel;
        if (key) carousels[key] = track.scrollLeft;
      });
    reviewPositionRef.current = {
      scrollY: window.scrollY,
      sectionId: section?.dataset.visualSection,
      sectionViewportTop: section?.getBoundingClientRect().top,
      carousels,
    };
    active?.blur();
  };

  const restoreReviewPosition = () => {
    const saved = reviewPositionRef.current;
    if (!saved) return;
    reviewPositionRef.current = null;
    window.requestAnimationFrame(() =>
      window.requestAnimationFrame(() => {
        for (const [key, left] of Object.entries(saved.carousels)) {
          const track = document.querySelector<HTMLElement>(
            `[data-visual-carousel="${key}"]`,
          );
          if (track) track.scrollLeft = left;
        }
        const section = saved.sectionId
          ? document.querySelector<HTMLElement>(
              `[data-visual-section="${saved.sectionId}"]`,
            )
          : null;
        if (section && saved.sectionViewportTop !== undefined) {
          window.scrollBy({
            top: section.getBoundingClientRect().top - saved.sectionViewportTop,
            left: 0,
            behavior: "auto",
          });
        } else {
          window.scrollTo({ top: saved.scrollY, left: 0, behavior: "auto" });
        }
      }),
    );
  };

  const act = async (fn: () => Promise<unknown>) => {
    try {
      captureReviewPosition();
      studio.setError("");
      setBusy(true);
      await fn();
      await load();
      await studio.refreshAll();
    } catch (err) {
      studio.setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      restoreReviewPosition();
    }
  };

  const renderVisual = (v: VisualCandidate) => (
    <VisualCandidateCard
      key={v.asset_id}
      visual={v}
      busy={busy}
      attribution={attributions[v.asset_id] ?? v.attribution_text ?? ""}
      onAttributionChange={(value) =>
        setAttributions((current) => ({ ...current, [v.asset_id]: value }))
      }
      onAttributionSave={(value) => void api.updateVisual(v.asset_id, { attribution_text: value }).then(load)}
      onDownload={() => void act(() => api.downloadVisual(v.asset_id))}
      onAnalyze={() => void act(() => api.analyzeVisual(v.asset_id))}
      onApprove={() => void act(() => api.manualApproveVisual(v.asset_id, attributions[v.asset_id] ?? v.attribution_text ?? undefined))}
      onReject={() => void act(() => api.rejectVisual(v.asset_id))}
    />
  );

  const unassignedVisuals = visuals.filter((visual) => visual.section_ids.length === 0);
  const filteredVisuals = visuals.filter((visual) => matchesFilter(visual, filter));
  const filteredUnassignedVisuals = unassignedVisuals.filter((visual) =>
    matchesFilter(visual, filter),
  );
  const filterCounts: Record<VisualFilter, number> = {
    local: visuals.filter((visual) => matchesFilter(visual, "local")).length,
    review: visuals.filter((visual) => matchesFilter(visual, "review")).length,
    approved: visuals.filter((visual) => matchesFilter(visual, "approved")).length,
    video: visuals.filter((visual) => matchesFilter(visual, "video")).length,
    image: visuals.filter((visual) => matchesFilter(visual, "image")).length,
    leads: visuals.filter(isLeadOnly).length,
    rejected: visuals.filter((visual) => matchesFilter(visual, "rejected")).length,
    all: visuals.filter(isEditorialVisual).length,
  };

  const approveAll = (items: VisualCandidate[]) =>
    void act(async () => {
      for (const visual of items) {
        await api.manualApproveVisual(
          visual.asset_id,
          attributions[visual.asset_id] ?? visual.attribution_text ?? undefined,
        );
      }
    });

  return (
    <div className="stack-lg animate-fade-in">
      {/* Toolbar */}
      <div className="card">
        <div className="row-between visual-toolbar-heading" style={{ marginBottom: 12 }}>
          <h2>Visuals</h2>
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api.searchVisuals(storyId);
              })
            }
          >
            Search This Episode + Web
          </button>
        </div>
        <div className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
          Episode media inbox: <code>{localFolder || "Loading…"}</code>
          <br />Only files placed in this project and episode are scanned.
        </div>
        <div className="row">
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="Stage a file into this episode…"
            style={{ maxWidth: 320 }}
          />
          <button
            type="button"
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
            type="button"
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

      {script?.sections.length && visuals.length > 0 ? (
        <div className="visual-filter-bar" aria-label="Filter visual candidates">
          <div>
            <span className="visual-filter-label">Show</span>
            {(
              [
                ["local", "Local media"],
                ["review", "Needs decision"],
                ["approved", "Approved"],
                ["video", "Videos"],
                ["image", "Images"],
                ["leads", "Search leads"],
                ["rejected", "Rejected"],
                ["all", "All"],
              ] as Array<[VisualFilter, string]>
            ).map(([value, label]) => (
              <button
                type="button"
                key={value}
                data-filter={value}
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {label} <span>{filterCounts[value]}</span>
              </button>
            ))}
          </div>
          <p>
            Local media is ready for your editorial decision. Search leads are references that were not downloaded.
          </p>
        </div>
      ) : null}

      {/* Section-led visual edit */}
      {script?.sections.length ? (
        <div className="visual-section-list">
          {script.sections.map((section, index) => (
            <SectionVisualRow
              key={section.section_id}
              section={section}
              index={index}
              lowerThird={
                section.lower_third ?? script.lower_thirds[index] ?? script.headline
              }
              visuals={filteredVisuals.filter((visual) => visual.section_ids.includes(section.section_id))}
              renderVisual={renderVisual}
              onApproveAll={approveAll}
              busy={busy}
            />
          ))}
          {filteredUnassignedVisuals.length > 0 && (
            <section className="visual-unassigned-section">
              <div className="visual-unassigned-heading">
                <span>Unassigned media</span>
                <strong>{filteredUnassignedVisuals.length} candidate{filteredUnassignedVisuals.length === 1 ? "" : "s"} available to any section</strong>
              </div>
              <div className="visual-carousel-track" data-visual-carousel="unassigned" tabIndex={0}>
                {filteredUnassignedVisuals.map(renderVisual)}
              </div>
            </section>
          )}
        </div>
      ) : visuals.length === 0 ? (
        <EmptyState
          icon="🖼"
          title="No local visuals staged"
          description="Create or load a script to see section-specific visual lanes, then search or stage media for this episode."
        />
      ) : (
        <div className="visual-unassigned-section">
          <div className="visual-unassigned-heading">
            <span>Visual library</span>
            <strong>Script sections are unavailable, so candidates are shown together.</strong>
          </div>
          <div className="visual-carousel-track" tabIndex={0}>{visuals.map(renderVisual)}</div>
        </div>
      )}
    </div>
  );
};
