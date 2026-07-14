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
| Composition / `render_story` | render | renderer manifest, anchor, approved visual paths | `story_manifest` | `preview.png`, `composited*.mp4` |
| Assembly / `assemble_episode` | render | episode story compositions and brand clips | `final_output_path` | final MP4, assembly work files, episode manifest |

## Approval boundary

`build_story_manifest()` requires an approved script and approved, valid timeline. It refreshes mutable rights/attribution metadata, replaces missing or blocked media with safe fallbacks, records provenance, and writes `story.json`. The renderer manifest is versioned and is the only supported input to `pipeline.run_story`; render code must not perform editorial discovery.

## Stage behavior

### Discovery

Sources are read from SQLite and fetched concurrently. URLs are canonicalized, duplicates clustered, deterministic scores calculated, and the optional assignment desk adds editorial ranking. Source failures update source health and remain visible. Run through the Studio or enqueue via `POST /api/discovery/start`.

### Research

The selected story remains the lead document. Related coverage is collected through SearXNG when configured, extracted, normalized, de-duplicated, and turned into evidence/claims. Network/provider errors are not converted into empty success. The result is independently testable through `build_research_pack(repository, story_id)`.

### Script

The configured structured LLM provider receives a versioned prompt and schema. Provider output is normalized and validated before a `ScriptDocument` revision is saved. Manual edits create a new revision. Approval is explicit and advances workflow state.

### Visual discovery and review

Sources run in registry order: the episode-isolated media inbox, then SearXNG if available. Downloaded media is probed for type, size, aspect, audio, and broadcast fit. Search results do not establish rights; yellow assets require manual approval and red assets cannot be approved. Rights-safe generated cards ensure each section has a fallback.

### Timeline

The planner maps script sections, approved visuals, template capabilities, overlays, and audio policy into ordered `TimelineSegment` models. Validation checks timing, rights, file existence, template compatibility, and approval. Timeline approval is required before manifest construction.

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
- Avatar, composition, and assembly use file freshness/provenance checks and support explicit force flags.
- Cancellation is cooperative between progress callbacks and the SQLite job status.
- Validation/configuration failures are terminal and retain exception context in the job record/log.
- CLI episode runs print completed/cached/skipped/failed/cancelled counts.

## Independent commands

```bash
# One worker iteration or one lane
.venv/bin/python -m pipeline.jobs.worker --once --lane editorial
.venv/bin/python -m pipeline.jobs.worker --lane media

# Render a pre-authored approved manifest
.venv/bin/python -m pipeline.run_story episodes/<episode>/stories/<story>/story.json \
  --render-profile preview --skip-avatar-render

# Create and run the deterministic TEST_MODE smoke episode
make smoke

# Create the local demo with the offline mock provider
make render-demo
```

Default tests never call live providers, Blender, or a full production render.
