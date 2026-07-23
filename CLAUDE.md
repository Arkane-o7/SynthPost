# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What SynthPost is

SynthPost is a local-first video production system. Its main runtime shape is:

```text
React/Vite Studio
  -> FastAPI
  -> SQLite workflow state and job queue
  -> supervised editorial/media/render workers
  -> local artifacts, Avatar Engine, Remotion, and FFmpeg
```

SQLite is authoritative for editable workflow state. JSON, audio, images, and video files are inspectable materializations and renderer inputs. The Studio must access state and files through the API, not SQLite or episode directories directly.

The intended dependency direction is:

```text
API / CLI / worker -> feature service -> domain model + provider/repository
```

Do not introduce dependencies from domain or service code back into HTTP or presentation layers.

## Prerequisites and setup

The primary environment is macOS on Apple Silicon with Python 3.11+, Node.js, npm, FFmpeg, and ffprobe. The Studio's locked Vite version requires Node 20.19+ or 22.12+. Docker, Tesseract, yt-dlp, Blender, Rhubarb, Playwright Chromium, and Tailscale are optional by feature.

```bash
cp .env.example .env
make setup
make doctor
```

`make setup` creates `.venv`, installs `requirements.txt`, and installs packages for `web/` and `compositor/remotion_renderer/`. It does not install the standalone dependencies under `avatar-engine/`.

After configuration changes, run:

```bash
make config-check
```

Configuration is loaded into immutable grouped Pydantic settings in `pipeline/config.py`. Add new variables to the grouped settings, `.env.example`, documentation, and diagnostics as appropriate; do not add direct `os.environ` reads to new pipeline modules. `.env` is loaded before `.env.local`, and existing non-empty values are not overwritten, so `.env.local` fills missing values rather than overriding `.env`.

## Running the application

```bash
make dev                 # FastAPI + worker supervisor + Vite Studio
make backend             # FastAPI on 127.0.0.1:8765
make workers             # configured worker supervisor
make web                 # Vite Studio on 127.0.0.1:5173
```

Run one manually controlled worker with:

```bash
make worker LANE=editorial
make worker LANE=media
make worker LANE=render SLOT=1
.venv/bin/python -m pipeline.jobs.worker --once --lane editorial
```

Valid lanes are `all`, `editorial`, `media`, and `render`; `SLOT` is a 1-based configured worker slot.

Render an already-approved story manifest without rerunning editorial stages:

```bash
.venv/bin/python -m pipeline.run_story \
  episodes/<episode_id>/stories/<story_id>/story.json \
  --render-profile preview --skip-avatar-render
```

Other useful services:

```bash
make searxng-up
make searxng-down
make remote               # private Studio through Tailscale Serve
make remote-status
make remote-off
```

## Build and validation

The default pre-PR gate is:

```bash
make check
```

It runs configuration validation, the root Python unit suite, Python bytecode compilation, TypeScript type checks for Remotion and the Studio, and the Studio production build.

Individual commands:

```bash
make test
make typecheck
make build
```

There is no root formatter or repository-wide lint command. Do not invent `make lint` or a root `npm run lint`. The Avatar browser runtime has its own ESLint command:

```bash
npm --prefix avatar-engine/web_avatar_runtime run lint
```

`make check` does not run Avatar Engine tests or render smoke tests. Run them when relevant:

```bash
make test-avatar            # Avatar Engine Python tests
make smoke                  # deterministic mock-provider preview render
make smoke-parallel         # two concurrent preview renders
make render-demo            # deterministic local demo
```

Root tests must remain offline and deterministic; do not add live provider calls, paid APIs, or production Blender renders to `make test`.

### Running focused tests

Tests use `unittest` dotted selectors:

```bash
.venv/bin/python -m unittest tests.test_direction
.venv/bin/python -m unittest \
  tests.test_direction.DirectionTemplateTests.test_full_screen_anchor_uses_landscape_intro
```

Avatar tests need their package on `PYTHONPATH`:

```bash
PYTHONPATH=avatar-engine .venv/bin/python -m unittest \
  tests.test_renderer_selection.TestResolveRendererName.test_default_is_blender
```

There is currently no JavaScript test runner configured in `web/`, `compositor/remotion_renderer/`, or `avatar-engine/web_avatar_runtime/`.

## Architecture and production flow

### Entrypoints

- `pipeline/api/main.py`: FastAPI application and API composition.
- `pipeline/jobs/supervisor.py`: expands configured lane/slot capacity into worker processes and restarts unexpected exits.
- `pipeline/jobs/worker.py`: queue consumer and stage-handler dispatch.
- `pipeline/run_episode.py`: direct episode orchestration and deterministic demo/smoke entrypoint.
- `pipeline/run_story.py`: downstream-only rendering of an approved `story.json`; do not add research, script generation, visual selection, or timeline planning here.
- `assembly/stitch_episode.py`: normalizes and concatenates story outputs, then appends the brand outro.
- `compositor/remotion_renderer/`: stages local media and renders preview/composited video from the renderer manifest.

### Editorial-to-render flow

The executable stage registry is `pipeline/stages.py`. The high-level flow is:

```text
discovery
-> story selection
-> multi-source research
-> narrative-first structured script generation
-> script approval
-> Kokoro narration + visual discovery
-> timeline generation/review/approval
-> renderer manifest
-> avatar render
-> Remotion composition
-> FFmpeg assembly
```

Most long-running stages are SQLite jobs. Timeline generation and renderer-manifest construction are currently synchronous approval-boundary operations in the API; prefer current executable code over older prose when documentation differs.

### Workflow state and approval boundaries

Story state transitions are explicit in `pipeline/workflow.py` and are enforced through `Repository.transition_story()`. Do not assign arbitrary workflow states or bypass the transition API.

Important invariants:

- A newer script revision invalidates downstream state and reopens completed production for review.
- Only the latest script and timeline revisions may be approved.
- Script approval queues narration and visual discovery.
- Timeline approval requires current, non-test narration and successful timeline validation.
- `build_story_manifest()` requires the latest approved script and timeline, compatible current narration, and valid media.
- Rendering consumes approved editor state; renderer code must not invent editorial choices.
- Kokoro narration timings come from actual PCM sample counts. The same WAV and beat clock drive the timeline, lip sync, avatar, and composition.

### Jobs and concurrency

There is no Redis or Celery queue. Jobs are SQLite records divided into lanes:

- `editorial`: discovery, research, script, narration
- `media`: visual search, timeline
- `render`: avatar, composition, assembly

Workers use Unix/macOS `fcntl` locks for the supervisor and numbered lane slots. Atomic claiming allows independent projects and episodes to run concurrently while serializing conflicting mutations to one story. Narration generation and visual search are the explicit safe-overlap pair: they share an immutable approved script but write independent artifacts. Episode assembly is exclusive with other work in that episode. Heartbeats, cooperative cancellation, stale-job recovery, and bounded retries are implemented in `pipeline/jobs/` and `pipeline/db/repository.py`.

Adding a job type normally requires coordinated changes to `StageName`, `STAGE_CONTRACTS`, the worker `HANDLERS` map, lane/retry policy, API/client surfaces, tests, and pipeline documentation. Handler and contract keys must match exactly.

### Persistence and artifacts

SQLite uses WAL and ordered SQL migrations under `pipeline/migrations/`. Initialization is filesystem-locked because the API and workers may cold-start concurrently.

Migration rules:

- Never edit or reorder an applied migration; add the next ordered migration.
- Reconstruct persisted JSON through strict Pydantic models.
- Add compatibility readers/defaults before changing persisted writers.

`pipeline/storage.py` and `pipeline/artifacts.py` use temporary files followed by atomic replacement for important JSON/manifest writes. Preserve that pattern.

Runtime and generated data includes `.synthpost/`, `.cache/`, `.venv/`, `projects/`, `episodes/`, staged Remotion files, and Avatar Engine outputs. Do not treat these as source code or delete user project/episode data during normal maintenance.

### Shared contracts

`pipeline/models.py` is the Python source of truth and uses `extra="forbid"`. Cross-runtime mirrors are maintained manually in:

- `contracts/schemas/synthpost.v2.schema.json`
- `contracts/typescript/index.ts`

TypeScript fields intentionally remain `snake_case` to match API and persisted JSON. HTTP input models belong in `pipeline/api/schemas.py`, also with unknown fields forbidden.

When changing a shared contract, update the Pydantic model, JSON Schema, TypeScript type, API client, fixtures/compatibility adapters, and relevant documentation together. Preserve the API error envelope `{error: {code, message}}`; errors must not expose secrets or arbitrary local paths. `story.json` with contract version `synthpost.v2.renderer_manifest` is the supported bridge from approved editor state into rendering.

### Providers, editorial policy, and visuals

Structured generation goes through `LLMProvider.generate_json()` in `pipeline/llm/providers.py`. Provider adapters own credentials, HTTP/SDK details, timeouts, normalization, and provider-specific errors; feature services own editorial policy. Availability checks must not make network or paid calls. The deterministic mock provider is for tests and smoke/demo runs.

`editorial/charters/synthpost.v1.json` is executable product policy, not merely documentation. Scripts are generated narrative-first and every production beat must remain linked to supported research claims.

Visual source order is deterministic: episode-local media inbox, optional SearXNG, then rights-safe anchor fallbacks. Preserve the review boundaries:

- Red assets cannot render as approved assets.
- Yellow assets require explicit manual approval.
- Search/downloaded media begins in editor review.
- Manual approval pins an editorial choice.
- Missing, rejected, incompatible, or deleted media falls back to the anchor.

Python and TypeScript template registries must remain synchronized:

- `pipeline/timeline/templates.py`
- `compositor/remotion_renderer/src/registry/templates.ts`

A template component existing does not make it production-eligible; `production_enabled` is the gate.

### Studio frontend

The Studio is a typed FastAPI client. All HTTP calls go through `web/src/api/client.ts` and `web/src/api/http.ts`; presentation components should not call `fetch` directly.

`web/src/state/useStudio.tsx` owns selection, shared server snapshots, local-storage selection IDs, and refresh orchestration. Workspace panels own feature-specific editing state. `useJobEvents` owns EventSource parsing and notifications. The SSE endpoint polls SQLite once per second and emits only when the serialized job list changes.

Vite proxies `/api` to port 8765. When `web/dist` exists, FastAPI serves it at `/`. Remote access is intended through private Tailscale Serve, not a public bind or Funnel.

### Avatar Engine

Before modifying `avatar-engine/`, read `avatar-engine/AGENTS.md`; it contains subsystem-specific compatibility constraints. In particular:

- The current Three.js/Reallusion renderer retains the name `rocketbox` for compatibility.
- Preserve PNG-frame browser capture followed by FFmpeg muxing.
- Never overwrite `avatar-engine/blender/avatar_template.blend`.
- Preserve legacy camera names, render profiles, export modes, test jobs, and 2D fallback contracts.
- Licensed character assets and generated outputs are not committed.
- Renderer fallback is opt-in only.

The executable root/config defaults are the runtime truth when older Avatar Engine prose differs.

## Documentation precedence

When sources disagree, use this order:

1. Executable contracts and registries: models, workflow transitions, stage registry, migrations, provider/template registries.
2. Current root documentation: `README.md`, `docs/ARCHITECTURE.md`, `docs/PIPELINE.md`, `docs/DEVELOPMENT.md`, and `docs/CONFIGURATION.md`.
3. Subsystem documentation and `avatar-engine/AGENTS.md`.
4. Historical rebuild reports and older architecture documents only as context.
