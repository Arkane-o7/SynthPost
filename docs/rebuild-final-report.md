# SynthPost Studio V2 Rebuild Final Report

Date: 2026-07-03

## 1. Architecture summary

SynthPost Studio V2 is a local-first editorial production application built around the retained render shell. It uses:

- FastAPI backend in `pipeline/api/`
- SQLite state with versioned migration in `pipeline/migrations/001_initial.sql`
- Filesystem artifacts under `episodes/<episode_id>/...`
- Pydantic contracts in `pipeline/models.py`
- Canonical JSON Schema in `contracts/schemas/synthpost.v2.schema.json`
- TypeScript contracts in `contracts/typescript/index.ts`
- React/Vite frontend in `web/`
- Local SQLite worker in `pipeline/jobs/worker.py`
- Existing Remotion renderer and FFmpeg assembly retained as rendering boundaries

The app is designed as a newsroom production editor: AI suggestions and automated discovery create draft material, but scripts, visuals, and timelines require explicit approval before rendering.

## 2. Repository audit findings

Baseline audit recorded in `docs/rebuild-baseline.md`.

Findings:

- `pipeline/run_story.py` was healthy as a low-level renderer entry point.
- `pipeline/direction/avatar.py` creates one story-level Avatar Engine job from `script.text` and estimates duration from WPM or existing browser-avatar audio.
- `pipeline/compositor.py` is a thin Remotion wrapper and should remain thin.
- `compositor/remotion_renderer/src/renderStory.ts` accepts `visuals`, `compositor_visuals`, and `approved_timeline` and writes composition metadata back to `story.json`.
- Existing timeline rendering already had basic support for split visual, fullscreen visual, fullscreen anchor, quote card, and document callout.
- Dynamic Remotion endscreen was already removed; assembly uses static `assets/brand/outro.mp4`.
- The retained renderer tests and avatar direction tests passed before V2 work began.

## 3. Files and directories created

Major new files/directories:

```text
contracts/
contracts/schemas/synthpost.v2.schema.json
contracts/typescript/index.ts

docs/rebuild-baseline.md
docs/v2-architecture.md
docs/rebuild-final-report.md

pipeline/models.py
pipeline/workflow.py
pipeline/artifacts.py
pipeline/manifest_builder.py
pipeline/run_episode.py
pipeline/migrations/001_initial.sql
pipeline/db/sqlite.py
pipeline/db/repository.py
pipeline/discovery/seeds.py
pipeline/discovery/discover.py
pipeline/research/extract.py
pipeline/llm/providers.py
pipeline/scripts/generation.py
pipeline/visuals/providers.py
pipeline/timeline/templates.py
pipeline/timeline/validation.py
pipeline/timeline/planner.py
pipeline/jobs/worker.py
pipeline/api/main.py

web/package.json
web/package-lock.json
web/tsconfig.json
web/vite.config.ts
web/index.html
web/src/App.tsx
web/src/main.tsx
web/src/api/client.ts
web/src/contracts/index.ts
web/src/state/useStudio.tsx
web/src/styles/studio.css
web/public/fonts/Anton-Regular.ttf

compositor/remotion_renderer/src/registry/templates.ts
compositor/remotion_renderer/src/templates/explainers/EditorialCards.tsx

requirements.txt
Makefile

tests/test_v2_contracts.py
tests/test_v2_pipeline.py
```

## 4. Files modified

Key modified retained files:

```text
README.md
.gitignore
compositor/remotion_renderer/src/types.ts
compositor/remotion_renderer/src/renderStory.ts
compositor/remotion_renderer/src/templates/TimelineStory.tsx
```

Renderer changes were additive: formalized timeline props and added real template rendering branches. Existing template files/components were not replaced.

## 5. Database schema

SQLite migration: `pipeline/migrations/001_initial.sql`.

Tables:

- `schema_migrations`
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

The schema stores canonical JSON payloads plus indexed workflow fields. This keeps state queryable while preserving complete reproducible objects.

Default DB path:

```text
.synthpost/synthpost.sqlite3
```

Override:

```bash
SYNTHPOST_DB_PATH=/path/to/synthpost.sqlite3
```

## 6. Canonical contracts

Contracts are defined in three places:

- `pipeline/models.py` — runtime Pydantic models
- `contracts/schemas/synthpost.v2.schema.json` — JSON Schema bundle
- `contracts/typescript/index.ts` — frontend TypeScript types

Required contracts implemented:

- Project
- Episode
- Source Definition
- Story Candidate
- Source Document
- Evidence Item
- Claim
- Research Pack
- Script Document
- Script Section
- Visual Candidate
- Timeline Plan
- Timeline Segment
- Audio Plan
- Render Job
- Artifact Record

Persisted JSON uses snake_case.

## 7. API routes

Backend: `pipeline/api/main.py`.

Implemented route groups:

### Health and templates

- `GET /api/health`
- `GET /api/templates`

### Projects and episodes

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `GET /api/episodes`
- `POST /api/projects/{project_id}/episodes`
- `GET /api/episodes/{episode_id}`
- `PATCH /api/episodes/{episode_id}`

### Sources

- `GET /api/sources`
- `POST /api/sources`
- `PATCH /api/sources/{source_id}`
- `POST /api/sources/{source_id}/test`

### Discovery

- `POST /api/discovery/start`
- `GET /api/discovery/candidates`
- `GET /api/discovery/candidates/{candidate_id}`
- `POST /api/discovery/candidates/{candidate_id}/select`
- `POST /api/discovery/candidates/{candidate_id}/reject`
- `POST /api/discovery/custom-topic`
- `POST /api/discovery/custom-url`
- `POST /api/discovery/manual-story`

### Research

- `POST /api/stories/{story_id}/research/start`
- `GET /api/stories/{story_id}/research`

### Script

- `POST /api/stories/{story_id}/script/generate`
- `GET /api/stories/{story_id}/script`
- `POST /api/stories/{story_id}/script/manual`
- `POST /api/stories/{story_id}/script/approve`

### Visuals

- `POST /api/stories/{story_id}/visuals/search`
- `GET /api/stories/{story_id}/visuals`
- `POST /api/stories/{story_id}/visuals/stage-local`
- `POST /api/stories/{story_id}/visuals/upload-bytes`
- `POST /api/visuals/{asset_id}/approve`
- `POST /api/visuals/{asset_id}/manual-approve`
- `POST /api/visuals/{asset_id}/reject`
- `POST /api/visuals/{asset_id}/block`
- `PATCH /api/visuals/{asset_id}`

### Timeline

- `POST /api/stories/{story_id}/timeline/generate`
- `GET /api/stories/{story_id}/timeline`
- `POST /api/stories/{story_id}/timeline/save`
- `POST /api/stories/{story_id}/timeline/validate`
- `POST /api/stories/{story_id}/timeline/approve`

### Rendering and jobs

- `POST /api/stories/{story_id}/manifest/build`
- `POST /api/stories/{story_id}/render/avatar`
- `POST /api/stories/{story_id}/render/story`
- `POST /api/episodes/{episode_id}/assemble`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `POST /api/jobs/{job_id}/retry`
- `GET /api/jobs/{job_id}/logs`
- `GET /api/jobs/events`
- `GET /api/artifacts/{artifact_path:path}`

Structured error responses are returned by FastAPI exception handlers for validation and not-found cases.

## 8. Frontend pages

Frontend: `web/`, named **SynthPost Studio**.

Main navigation:

- Dashboard
- Sources
- Story Inbox
- Projects
- Episodes
- Render Jobs
- Settings

Episode workspace tabs:

- Story
- Research
- Script
- Visuals
- Timeline
- Preview
- Render

The UI calls backend APIs and refreshes persisted SQLite state. Important actions are not frontend-only mocks.

## 9. Provider integrations

Implemented providers:

### News/source discovery

- RSS/Atom feed registry using `feedparser`
- Custom topic
- Custom URL
- Manual story

### LLM

- Ollama provider using `/api/generate` with JSON format
- Deterministic mock provider for tests/smoke demos

Environment variables:

```bash
SYNTHPOST_LLM_PROVIDER=ollama|mock
SYNTHPOST_OLLAMA_BASE_URL=http://127.0.0.1:11434
SYNTHPOST_OLLAMA_MODEL=gemma4:26b
SYNTHPOST_OLLAMA_FALLBACK_MODELS=gemma4:e2b-mlx
SYNTHPOST_OLLAMA_TIMEOUT=240
SYNTHPOST_OLLAMA_TEMPERATURE=0.2
SYNTHPOST_OLLAMA_CONTEXT_SIZE=8192
```

### Visuals

- Local upload/stage path
- Local drop folder via `SYNTHPOST_MEDIA_DROP_DIR`
- ffprobe metadata summary where available
- thumbnail generation for images and videos

Remote visual providers are intentionally not bulk-scaffolded yet.

## 10. Template registry

Python registry:

```text
pipeline/timeline/templates.py
```

Renderer registry:

```text
compositor/remotion_renderer/src/registry/templates.ts
```

Template IDs:

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

New Remotion components live in:

```text
compositor/remotion_renderer/src/templates/explainers/EditorialCards.tsx
```

`TimelineStory.tsx` dispatches through the registry and renders each template as a real composition branch.

## 11. Timeline and audio design

Timeline contract supports:

- revision history
- draft/review/approved state
- segment timing
- section mapping
- claim IDs
- anchor visibility/speaking/camera
- visual assignment
- template assignment
- overlays
- audio mode
- status

Validator: `pipeline/timeline/validation.py`.

Validation checks include:

- unique segment IDs
- positive ordered timing
- overlaps and gaps
- approved visual state
- rights tier enforcement
- media path existence
- template compatibility
- trim range validity
- source-audio/anchor speaking conflicts
- quote claim requirements
- attribution warnings

Audio plan:

- `AudioPlan` model exists.
- Segment audio modes: `narration`, `source`, `mixed`, `silent`.
- Current strategy is `timeline_aligned_avatar` with a warning that full source-audio pause synthesis is the next hardening step.

## 12. Avatar integration design

The retained Avatar Engine integration remains the boundary:

```text
pipeline/direction/avatar.py
pipeline/run_story.py
```

Current behavior:

- Manifest builder writes `script.text` as concatenated approved sections.
- `pipeline.run_story` invokes Avatar Engine when the selected template requires avatar.
- Smoke/test mode can skip real Avatar Engine and allow a generated placeholder anchor for Remotion validation.

Future hardening:

- Generate segment-level narration/audio regions.
- Insert explicit silence/source-audio pauses.
- Either render one timeline-aligned avatar clip or deterministic segment-level avatar clips.

## 13. Setup commands

```bash
make setup
```

Installs:

- Python requirements
- Remotion package dependencies
- SynthPost Studio web dependencies

## 14. Development commands

```bash
make dev       # backend + worker + web
make backend   # FastAPI only
make worker    # SQLite worker only
make web       # Vite only
```

## 15. Test commands

```bash
make test
make typecheck
make smoke
```

## 16. Test results

Passed:

```bash
python3 -m unittest discover -s tests
```

Result:

```text
Ran 17 tests
OK
```

Passed:

```bash
make typecheck
```

Includes:

- Python compile checks
- Remotion TypeScript typecheck
- SynthPost Studio TypeScript typecheck

Passed:

```bash
make smoke
```

Rendered through retained Remotion renderer and assembled final TEST_MODE MP4.

## 17. End-to-end demo steps

Run:

```bash
make smoke
```

What it does:

1. Creates a local project if needed.
2. Creates a demo episode.
3. Adds a manual story.
4. Selects the story.
5. Builds a research pack.
6. Saves and approves a manual script.
7. Stages a retained local image as a green test visual.
8. Approves the visual.
9. Generates and approves a timeline.
10. Builds the renderer manifest.
11. Renders the story through Remotion with placeholder anchor in TEST_MODE.
12. Assembles the final episode through ffmpeg.

## 18. Generated demo artifact paths

Latest successful smoke run wrote:

```text
episodes/ep_a6fc045cf4ba/stories/story_d453623f46b4/story.json
episodes/ep_a6fc045cf4ba/stories/story_d453623f46b4/preview.png
episodes/ep_a6fc045cf4ba/stories/story_d453623f46b4/composited_TEST_MODE.mp4
episodes/ep_a6fc045cf4ba/final_TEST_MODE.mp4
```

These files are intentionally ignored by Git via `episodes/`.

## 19. Known limitations

The implemented system is a working V2 foundation and local manual vertical slice. It does not yet fully satisfy every long-term newsroom requirement.

Known limitations:

- Remote visual providers such as Wikimedia/NASA/DVIDS/EC are not implemented yet.
- Article extraction is deterministic but basic; it does not handle every publisher layout.
- Research extraction is simple and should be strengthened with better NLP and primary-source discovery.
- Grounding validation catches missing claims and unsupported numbers/quotes at a basic level, but causal/contradiction analysis needs hardening.
- Script section regeneration and per-section approval UI are not fully implemented.
- Studio preview currently displays generated render artifacts; direct Remotion Player integration is still a next step.
- Avatar/audio sync has an explicit `audio_plan`, but retained Avatar Engine still renders story-level narration by default.
- Multi-story episode ordering/editing exists in data model and assembly path, but the UI needs a richer reorder surface.

## 20. Recommended next improvements

Priority order:

1. Add direct Remotion Player integration in Studio using normalized timeline props.
2. Implement full audio-plan synthesis with narration pauses and source-audio regions.
3. Add a production Avatar Engine smoke command for licensed local assets.
4. Add Wikimedia Commons and NASA media adapters with rights metadata.
5. Harden article extraction with readability heuristics and fixtures.
6. Add per-section script regeneration and approval-state editing.
7. Add richer visual trim editor and still-image motion controls.
8. Add multi-story episode reorder UI.
9. Add end-to-end Playwright/UI tests once the interaction model stabilizes.
10. Add backup/export/import for `.synthpost` SQLite plus artifact folders.
