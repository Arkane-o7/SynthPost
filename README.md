# SynthPost Studio

SynthPost Studio is a local-first newsroom and video-production editor rebuilt around the retained SynthPost rendering shell.

The repository keeps the working render infrastructure:

- `avatar-engine/` as an external dependency
- `pipeline/direction/avatar.py` avatar job integration
- `pipeline/compositor.py` Remotion render boundary
- `pipeline/run_story.py` low-level story render entry point
- `compositor/remotion_renderer/` templates/components/styles
- `assembly/stitch_episode.py` ffmpeg episode assembly with static brand intro/outro
- `assets/brand/` brand clips/placeholders

The old newsroom pipeline was **not restored**. V2 is built with new contracts, SQLite workflow state, reproducible JSON artifacts, and a React editor called **SynthPost Studio**.

## What works now

The current V2 implementation supports a real local vertical slice:

1. Create a project and episode.
2. Seed/list/edit news sources.
3. Discover RSS/Atom candidates or add a custom topic, URL, or manual story.
4. Select a story into an episode.
5. Build a research pack from source/manual text.
6. Generate a script via local Ollama or deterministic mock provider.
7. Save manual script revisions and approve the script.
8. Stage/upload local visuals with rights metadata.
9. Approve or reject visuals with rights checks.
10. Generate a multi-template timeline.
11. Edit/reorder timeline segments in SynthPost Studio.
12. Validate and approve the timeline.
13. Build a deterministic renderer `story.json` manifest from approved state.
14. Render through the retained Remotion package.
15. Assemble `final.mp4` / `final_TEST_MODE.mp4` with ffmpeg and brand assets.
16. Track jobs, logs, artifacts, and generated files.

## Architecture

```text
contracts/                         Canonical V2 JSON Schema + TypeScript contracts
pipeline/models.py                 Pydantic models for contracts
pipeline/workflow.py               Explicit story workflow state machine
pipeline/db/                       SQLite migrations and repository layer
pipeline/discovery/                Source registry, RSS/Atom discovery, ranking
pipeline/research/                 Source extraction and research-pack generation
pipeline/llm/                      Ollama/mock structured-generation providers
pipeline/scripts/                  Script generation/editing/grounding checks
pipeline/visuals/                  Local upload/drop-folder visual provider and rights review
pipeline/timeline/                 Template registry, timeline generation, validation
pipeline/jobs/                     SQLite-backed local worker
pipeline/api/                      FastAPI backend
pipeline/manifest_builder.py       Approved Studio state → renderer story.json
pipeline/run_episode.py            High-level demo/smoke orchestration
web/                               SynthPost Studio React/Vite frontend
compositor/remotion_renderer/      Retained Remotion renderer + formalized templates
assembly/stitch_episode.py         FFmpeg final assembly
```

## Local setup

```bash
make setup
```

This installs Python requirements, Remotion dependencies, and SynthPost Studio frontend dependencies.

## Development

Run the full local Studio stack:

```bash
make dev
```

This starts:

- FastAPI backend on `http://127.0.0.1:8765`
- SQLite-backed background worker
- SynthPost Studio Vite app on `http://127.0.0.1:5173`

You can also run services separately:

```bash
make backend
make worker
make web
```

## Testing and validation

```bash
make test
make typecheck
```

Current validation covers:

- Existing avatar direction tests
- Existing retained Remotion surface tests
- V2 contract drift checks
- Workflow transitions
- URL canonicalization and duplicate grouping
- Deterministic story scoring
- Rights-tier enforcement
- Timeline validation
- Manifest building vertical slice
- Python compile checks
- Remotion TypeScript typecheck
- SynthPost Studio TypeScript typecheck

## Smoke render

Create a deterministic local test episode, render with a placeholder anchor in `TEST_MODE`, and assemble a validation video:

```bash
make smoke
```

The smoke command writes ignored local artifacts under:

```text
episodes/<episode_id>/
  stories/<story_id>/story.json
  stories/<story_id>/preview.png
  stories/<story_id>/composited_TEST_MODE.mp4
  final_TEST_MODE.mp4
```

`TEST_MODE` outputs are explicitly not production outputs.

## Real demo render

Create a deterministic local demo episode and render a non-`TEST_MODE` demo MP4:

```bash
make render-demo
```

This writes:

```text
episodes/<episode_id>/
  stories/<story_id>/story.json
  stories/<story_id>/preview.png
  stories/<story_id>/composited.mp4
  final.mp4
```

By default this does not mutate or install anything inside `avatar-engine/`; if Avatar Engine is not already set up, use the existing placeholder-anchor fallback. For a real avatar render, set up Avatar Engine and run `python3 -m pipeline.run_episode <episode_id> --with-avatar`.

## Render a pre-authored story manifest

The retained low-level render entry point still works:

```bash
python3 -m pipeline.run_story episodes/<episode_id>/stories/<story_id>/story.json \
  --skip-avatar-render \
  --force-composite \
  --render-profile preview
```

Render with Avatar Engine:

```bash
SYNTHPOST_AVATAR_RENDERER=rocketbox \
python3 -m pipeline.run_story episodes/<episode_id>/stories/<story_id>/story.json \
  --force-avatar \
  --force-composite \
  --render-profile production
```

Assemble all story clips in an episode:

```bash
python3 assembly/stitch_episode.py <episode_id> --render-profile production
```

## Ollama configuration

Structured local generation uses Ollama by default:

```bash
SYNTHPOST_LLM_PROVIDER=ollama
SYNTHPOST_OLLAMA_BASE_URL=http://127.0.0.1:11434
SYNTHPOST_OLLAMA_MODEL=llama3.1:8b
SYNTHPOST_OLLAMA_TIMEOUT=90
SYNTHPOST_OLLAMA_TEMPERATURE=0.2
```

For deterministic tests/demos:

```bash
SYNTHPOST_LLM_PROVIDER=mock
```

## Avatar Engine notes

`avatar-engine/` remains an external dependency and was not rewritten by V2.

One-time setup, if you want real avatar rendering:

```bash
python3.11 -m venv avatar-engine/.venv
avatar-engine/.venv/bin/pip install -r avatar-engine/requirements.txt
npm --prefix avatar-engine/web_avatar_runtime install
```

Expected local licensed avatar asset:

```text
avatar-engine/assets/avatars/synthpost_anchor_v1/anchor.glb
```

Useful environment overrides:

```bash
SYNTHPOST_AVATAR_ENGINE_PATH=/absolute/path/to/Avatar-Engine
SYNTHPOST_AVATAR_RENDERER=rocketbox
SYNTHPOST_AVATAR_ASSET_PATH=assets/avatars/synthpost_anchor_v1/anchor.glb
SYNTHPOST_AVATAR_META_PATH=assets/avatars/synthpost_anchor_v1/avatar.json
SYNTHPOST_AVATAR_RENDER_BACKGROUND=charcoal
SYNTHPOST_AVATAR_VOICE_ID=af_heart
SYNTHPOST_AVATAR_VOICE_SPEED=1.10
```

## Production safety rules implemented

- Red-tier assets cannot be approved or rendered.
- Yellow-tier assets require manual approval before timeline approval/rendering.
- Approved timeline is the rendering source of truth.
- The manifest builder refuses to render without approved script and approved timeline.
- Timeline validation checks media existence, timing, overlaps, rights, approval state, template compatibility, trim ranges, and attribution warnings.
- AI structured output is parsed/validated/retried rather than blindly accepted.
- TEST_MODE outputs are labeled and separated.

## Known limitations

This is a working V2 foundation and manual vertical slice, not the final newsroom product. Important next work:

- Full remote visual providers beyond local upload/drop-folder.
- Stronger article extraction for difficult publisher pages.
- More robust NLP/entity extraction and claim contradiction checks.
- Section-level regeneration and richer approval history in the UI.
- Remotion Player embedded directly in Studio for interactive playback; current Studio consumes generated preview/render artifacts.
- Full timeline-aligned avatar/source-audio pause synthesis. The explicit `audio_plan` exists, but the retained Avatar Engine is still invoked as a story-level render by default.
- Multi-story episode editing UI beyond assembling the selected episode story list.

See `docs/rebuild-baseline.md`, `docs/v2-architecture.md`, and `docs/rebuild-final-report.md` for implementation details.
