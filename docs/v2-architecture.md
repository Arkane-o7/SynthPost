# SynthPost Studio V2 Architecture

SynthPost Studio is a local-first newsroom production editor built around the retained renderer shell.

## Design principles

- Keep the working renderer/avatar/assembly shell intact.
- Rebuild the newsroom pipeline using explicit V2 contracts.
- Store workflow state in SQLite and reproducible artifacts on disk.
- Treat AI output as suggestions, never approvals.
- Render only from approved scripts, approved visuals, and approved timelines.
- Keep the newsroom application local on macOS while using explicitly configured hosted AI providers for production generation.

## Major directories

```text
contracts/
  schemas/synthpost.v2.schema.json     Canonical JSON Schema bundle
  typescript/index.ts                   Frontend-compatible TypeScript contracts

pipeline/
  models.py                             Pydantic V2 contract models
  workflow.py                           Story state machine
  db/                                   SQLite migration + repository layer
  discovery/                            Source seeds, RSS/Atom discovery, ranking
  research/                             Source extraction and research-pack builder
  llm/                                  Hosted Groq/Gemini structured-generation providers
  scripts/                              Script generation, revisions, grounding checks
  visuals/                              Local visual provider and rights review
  timeline/                             Template registry, draft planner, validator

projects/<project_id>/episodes/<episode_id>/media_inbox/
                                        Editor-managed local media isolated to one
                                        production; imports and browser uploads are
                                        copied here before analysis.
  jobs/                                 SQLite-backed local worker
  api/                                  FastAPI backend
  manifest_builder.py                   Approved state → renderer story.json
  run_episode.py                        High-level orchestration/smoke command

web/                                    SynthPost Studio React/Vite frontend
compositor/remotion_renderer/src/registry/templates.ts
                                        Renderer-side template registry
```

## Persistence model

SQLite tables store canonical JSON payloads and indexed fields:

- `projects`
- `episodes`
- `sources`
- `story_candidates`
- `source_documents`
- `research_packs`
- `script_revisions`
- `visual_candidates`
- `timeline_revisions`
- `render_jobs`
- `artifacts`
- `settings`
- `schema_migrations`

Migrations live in `pipeline/migrations/`. Tables are not created implicitly on random requests; startup/repository initialization applies versioned migrations.

## Filesystem artifact layout

V2 materializes reproducible artifacts under:

```text
episodes/<episode_id>/
  episode.json
  stories/<story_id>/
    story.json
    source_documents.json
    research_pack.json
    scripts/script_v001.json
    visuals/candidates.json
    visuals/media/
    visuals/thumbnails/
    timelines/timeline_v001.json
    timelines/approved_timeline.json
    preview.png
    composited.mp4
  final.mp4
```

SQLite indexes the workflow; JSON/files remain sufficient to inspect and rerender.

## Backend API

The FastAPI backend lives at `pipeline/api/main.py` and exposes endpoints for:

- Projects and episodes
- Source registry
- Story discovery and manual story entry
- Research pack generation
- Script generation/manual editing/approval
- Visual staging/upload/review
- Timeline generation/editing/validation/approval
- Manifest building
- Story rendering and episode assembly jobs
- Job state/logs/events
- Artifact serving

## Background jobs

`pipeline/jobs/worker.py` implements a local SQLite-backed worker with job states:

```text
queued → running → completed | failed | cancelled
```

Each job stores progress, stage, structured output paths, error, traceback, and a log file under `.synthpost/jobs/`.

No Redis, Celery, or cloud queue is used.

## Workflow state machine

Stories move through explicit states:

```text
draft → discovered → selected → researching → research_ready
→ script_generating → script_review → script_approved
→ visuals_searching → visuals_review
→ timeline_draft → timeline_review → timeline_approved
→ rendering_avatar → rendering_composition → assembling → completed
```

Invalid transitions raise errors in `pipeline/workflow.py`.

## Discovery and ranking

Initial discovery supports RSS/Atom feeds, custom topics, custom URLs, and manual stories. It implements:

- HTTP feed caching and stale-cache fallback
- URL canonicalization
- title normalization
- duplicate grouping
- published-time normalization
- source attribution
- basic language detection
- deterministic score components and human-readable score reasons

The seed registry includes global, India, tech, AI, business/economy, climate/energy, geopolitics, science, and internet-culture sources, but custom sources are editable.

## Research and script pipeline

Research is deterministic first:

- Fetch/extract selected source text when possible.
- Build source documents with hashes.
- Extract evidence excerpts and claims from source sentences.
- Extract simple people/org/location/date/number hints.
- Record extraction warnings and uncertainties.

Script generation uses a provider abstraction:

- `GroqProvider` and `GeminiProvider` for production generation.
- `HostedFallbackProvider` only when hosted failover is explicitly configured.
- `MockProvider` for deterministic automated tests and smoke demos only.

Structured stages request JSON, parse it, validate it into Pydantic models, retry on malformed output, and store warnings.

## Visual pipeline

The first working adapter is local upload/local drop-folder staging. It records:

- provider
- source path
- thumbnail path
- media metadata via ffprobe where available
- rights tier
- usage basis
- attribution
- manual review state

Rights rules are enforced in models and timeline validation:

- Red assets cannot be approved.
- Yellow assets require `manual_approved`.
- Green assets can be approved when metadata/usage basis supports it.

## Template registry

Python registry: `pipeline/timeline/templates.py`.

Renderer registry: `compositor/remotion_renderer/src/registry/templates.ts`.

Formal template IDs:

- `split_anchor_visual`
- `fullscreen_news_visual`
- `fullscreen_anchor`
- `fallback_anchor`
- `quote_card`
- `document_callout`
- `chart_explainer`
- `map_explainer`
- `timeline_explainer`
- `comparison_card`
- `bullet_summary`
- `source_screenshot`
- `fallback_context_card`

New templates are implemented as real Remotion components under `src/templates/explainers/EditorialCards.tsx` and consumed by `TimelineStory.tsx`.

## Timeline and audio design

`TimelinePlan` contains draft/review/approved revisions and segment-level:

- timing
- script text
- claim IDs
- anchor state
- visual assignment
- template ID
- audio mode (`narration`, `source`, `mixed`, `silent`)
- overlays
- approval status

`validate_timeline()` checks timing, overlaps/gaps, approved rights state, template compatibility, media existence, trim ranges, attribution warnings, audio policy, and total duration.

The current avatar integration still renders one story-level avatar clip from concatenated narration. V2 adds an explicit `audio_plan` and currently chooses `timeline_aligned_avatar`. Full source-audio pause synthesis is documented as the next audio hardening step.

## Manifest builder

`pipeline/manifest_builder.py` is the only layer that writes renderer `story.json` from Studio state.

It requires:

- approved script
- approved timeline
- timeline validation passing
- approved/right-safe visuals
- resolvable media paths

It writes a backward-compatible manifest for the retained `pipeline.run_story` and records an artifact row.

## Frontend: SynthPost Studio

`web/` is a React/Vite desktop editor with:

- Dashboard
- Sources
- Story Inbox
- Projects
- Episodes workspace
- Render Jobs
- Settings

The episode workspace has stage tabs:

- Story
- Research
- Script
- Visuals
- Timeline
- Preview
- Render

Important actions call the backend and persist state in SQLite/artifacts.

## Developer commands

```bash
make setup
make dev
make backend
make worker
make web
make test
make typecheck
make smoke
make render-demo
```

`make dev` starts backend, worker, and Vite in one command for local use.
