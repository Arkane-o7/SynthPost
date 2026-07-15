# Pipeline guide

The queue-backed production pipeline contains eight registered stages. `pipeline/stages.py` is the executable registry for lane, required identity, output keys, retry safety, and artifact ownership. Manifest construction is a synchronous approval boundary between timeline and rendering.

## Lifecycle

| Stage / job type | Lane | Required inputs | Output contract | Primary artifacts/state |
|---|---|---|---|---|
| Discovery / `discovery` | editorial | enabled source definitions; optional episode/category | `candidate_count` | `story_candidates`, source check status |
| Research / `research` | editorial | selected `story_id`, lead candidate, optional SearXNG | `research_pack_id` | source documents, evidence, claims, research pack |
| Script / `script_generate` | editorial | research-ready story, provider, duration/mode | `script_id` | script revision, generation audit |
| Visuals / `visual_search` | media | approved script, episode media inbox, optional SearXNG | `visual_count` | downloaded/staged media, thumbnails, visual records |
| Timeline / `timeline_generate` | media | approved script and eligible visuals | `timeline_id` | timeline revision and validation messages |
| Avatar / `render_avatar` | render | approved timeline, renderer manifest, profile | `story_manifest`, `anchor_output_path` | avatar job, audio/lip-sync/render output |
| Composition / `render_story` | render | renderer manifest, anchor, eligible local visual paths | `story_manifest` | `preview.png`, `composited*.mp4` |
| Assembly / `assemble_episode` | render | episode story compositions and brand clips | `final_output_path` | final MP4, assembly work files, episode manifest |

## Approval boundary

`build_story_manifest()` requires an approved script and approved, valid timeline. It refreshes mutable rights/attribution metadata, replaces missing or blocked media with safe fallbacks, records provenance, and writes `story.json`. The renderer manifest is versioned and is the only supported input to `pipeline.run_story`; render code must not perform editorial discovery.

## Stage behavior

### Discovery

Sources are read from SQLite and fetched concurrently. URLs are canonicalized, duplicates clustered, deterministic scores calculated, and the optional assignment desk adds editorial ranking. Source failures update source health and remain visible. Run through the Studio or enqueue via `POST /api/discovery/start`.

### Research

The selected story remains the lead document. Related coverage is collected through SearXNG when configured, extracted, normalized, de-duplicated, and turned into evidence/claims. Network/provider errors are not converted into empty success. The result is independently testable through `build_research_pack(repository, story_id)`.

### Script

Script generation is narrative-first. The configured structured LLM provider first produces a story-level brief that allocates evidence across one progressive arc, then writes the complete uninterrupted narration in a single response. A deterministic quality gate rejects repeated scene openings, near-duplicate beats, repeated phrases, and obvious sentence-start grammar failures; a failed draft receives one whole-narrative continuity repair and must pass the gate afterward.

Only accepted narration is segmented. The segmentation response may reference stable narration beat IDs exactly once and in order, but cannot return or rewrite narration text. Each compact narration beat must link to at least one supported research claim. Section metadata, visual queries, template hints, lower thirds, and chyrons are derived after this boundary. The resulting sections are converted into the existing `ScriptDocument`, so visuals, timelines, manifests, and legacy stored scripts remain compatible. Every provider stage and normalization is recorded as a versioned generation audit. Generating or manually saving a new script revision returns the story to `script_review`, invalidating downstream workflow state without deleting its audit history. Only the newest script and timeline revisions can cross production approval boundaries, so an older approved revision cannot be rendered after a newer draft is saved. Approval is explicit and advances workflow state.

### Visual discovery and review

Sources run in registry order: the episode-isolated media inbox, then SearXNG if available. Downloaded media is probed for actual type, size, aspect, audio, and broadcast fit. A repeated result can be associated with every relevant section, but it is stored and downloaded only once. Re-searching or rescanning preserves acquired media and editor decisions; replacing or reacquiring the bytes of a local file deliberately clears stale approval and returns that asset to review. Same-named uploads and inbox files receive collision-safe destinations instead of overwriting one another.

Search results do not establish rights or content cleanliness. Newly acquired files remain `needs_review` until an editor approves them. A technically eligible local suggestion may be selected automatically, with a timeline warning, because visual approval is optional. Manual approval records the editorial rights and content-review decision and pins that choice above suggestions; the most recently approved candidate wins when an editor changes the pin. Yellow assets require manual approval to be pinned. An explicit manual override reclassifies a red candidate to yellow/manual-approved and remains visible in its metadata. Rejected or blocked assets never render.

Non-downloadable results remain research leads until acquired. Image acquisition first tries the discovered media URL, then the source page's Open Graph image; if both have expired but a cached search preview exists, the editor can still acquire that preview with an explicit quality warning. Missing, rejected, incompatible, or deleted media falls back to the presenter. Fallback records are anchor-only signals; SynthPost does not generate duplicate headline cards as substitute imagery.

### Timeline

The planner maps script sections, pinned or automatically selected eligible visuals, template capabilities, overlays, and audio policy into ordered `TimelineSegment` models. Validation checks timing, rights, file existence, template compatibility, automatic-selection warnings, and timeline approval. Timeline approval is required before manifest construction.

### Avatar

The direction adapter writes an avatar job and invokes the configured Avatar Engine renderer. Fresh outputs may be reused unless forced. Browser/Three.js and legacy Blender modes remain compatibility paths owned by `avatar-engine/`.

### Composition

Remotion consumes `story.json`. If the output is newer than the manifest, anchor, and visuals, it is reused unless `--force-composite` is given. Preview and composited video provenance is written back to the manifest.

### Assembly

FFmpeg normalizes story clips and joins them with brand intro/outro assets. Production and `TEST_MODE` outputs are distinct. Successful production assembly updates the episode and story completion states.

## Cache, skip, retry, and failure semantics

- Discovery/research/script/visual/timeline retries are controlled by `pipeline/jobs/policy.py`; transient network, timeout, rate-limit, and subprocess failures can be retried with bounded exponential backoff.
- Render jobs have a lower attempt budget because they are expensive and not assumed idempotent at arbitrary interruption points.
- Worker heartbeats prevent healthy long jobs from being reclaimed. Stale running jobs are released or failed after job-type-specific limits.
- Each lane has a configurable supervised process pool. SQLite claims are atomic, so independent projects can occupy multiple slots without claiming the same job twice.
- Jobs for the same story are serialized. Episode assembly does not overlap any other running work for that episode, while unrelated projects and episodes remain parallel.
- Avatar, composition, and assembly use file freshness/provenance checks and support explicit force flags.
- Cancellation is cooperative between progress callbacks and the SQLite job status.
- Validation/configuration failures are terminal and retain exception context in the job record/log.
- CLI episode runs print completed/cached/skipped/failed/cancelled counts.

## Independent commands

```bash
# One worker iteration or one lane
.venv/bin/python -m pipeline.jobs.worker --once --lane editorial
.venv/bin/python -m pipeline.jobs.worker --lane media --slot 1
.venv/bin/python -m pipeline.jobs.supervisor

# Render a pre-authored approved manifest
.venv/bin/python -m pipeline.run_story episodes/<episode>/stories/<story>/story.json \
  --render-profile preview --skip-avatar-render

# Create and run the deterministic TEST_MODE smoke episode
make smoke

# Verify two independent episode renders and assemblies overlap safely
make smoke-parallel

# Create the local demo with the offline mock provider
make render-demo
```

Default tests never call live providers, Blender, or a full production render.
