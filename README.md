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
5. Build a multi-source research pack from the lead story plus related SearXNG news coverage.
6. Generate a script via a configured hosted Groq or Gemini provider.
7. Save manual script revisions and approve the script.
8. Search the active episode's isolated media inbox and SearXNG image/video sources, or upload media manually.
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
pipeline/search/                   SearXNG JSON client and result normalization
pipeline/news/                     Related-news coverage discovery
pipeline/research/                 Multi-source extraction and research-pack generation
pipeline/llm/                      Hosted Groq/Gemini structured-generation providers
pipeline/scripts/                  Script generation/editing/grounding checks
pipeline/visuals/                  Local + SearXNG visual discovery, download, and rights review
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

## SearXNG research and visual search

SynthPost includes a localhost-only SearXNG container configured to expose the
JSON search API:

```bash
make searxng-up
curl 'http://127.0.0.1:8888/search?q=world+news&categories=news&format=json'
```

If Docker Desktop is installed on macOS but another context is selected, use
`DOCKER_CONTEXT=desktop-linux make searxng-up`.

Then set this in `.env`:

```bash
SYNTHPOST_SEARXNG_URL=http://127.0.0.1:8888
```

Research jobs retain the selected story as the lead document and add related
news results up to `SYNTHPOST_RESEARCH_MAX_DOCUMENTS`. Visual jobs derive search
queries through the configured structured AI provider immediately before
SearXNG. The AI receives the topic, headline, section narration, claim IDs, and
visual direction, then returns one grounded still-image query and one distinct
footage query per section. The deterministic script-query planner is used only
when `SYNTHPOST_AI_VISUAL_QUERY_PLANNING=0`.

`SYNTHPOST_SEARXNG_VISUAL_MAX_QUERIES` is a hard cap on the number of actual
image/video search requests sent to SearXNG per visual job. The default of 12
supports one image plus one video query for a typical six-section story. When
the cap is smaller, the allocator covers each section's preferred media type
before spending remaining requests on its secondary media type.

Supported images are downloaded directly. Set
`SYNTHPOST_SEARXNG_DOWNLOAD_VIDEOS=1` to let the worker use `yt-dlp` for eligible
video pages. `SYNTHPOST_SEARXNG_VIDEO_DOWNLOAD_LIMIT` caps downloads per job and
`SYNTHPOST_SEARXNG_VIDEO_CLIP_SECONDS` limits each research clip.

Render-ready visual media must also pass the broadcast-fit gate. By default it
must be at least 1920×1080, horizontal, and close to either the 1300×860 split
visual panel (~3:2) or the 1920×1080 fullscreen visual (16:9). The AI explicitly
requests landscape 1080p media, `yt-dlp` filters formats before download, and
downloaded images/videos are probed again before staging. Portrait, undersized,
or extreme-aspect media remains a review lead without a renderable local file.
Tune this using `SYNTHPOST_VISUAL_MIN_WIDTH`, `SYNTHPOST_VISUAL_MIN_HEIGHT`, and
`SYNTHPOST_VISUAL_ASPECT_TOLERANCE`; approval enforces the same gate.

### Video source and editorial-cleanliness quarantine

Visual video queries request official video, raw footage, B-roll, or press
footage rather than finished news coverage. Before a video download, `yt-dlp`
performs a metadata-only preflight and records the channel/uploader identity.
Known competing news publishers are blocked before download. Editor-maintained
channel IDs and source-name fragments can be configured with
`SYNTHPOST_VIDEO_APPROVED_CHANNEL_IDS`,
`SYNTHPOST_VIDEO_APPROVED_SOURCE_NAMES`, and
`SYNTHPOST_VIDEO_BLOCKED_SOURCE_NAMES`.

Every technically valid downloaded image/video enters content quarantine. For
video, SynthPost samples seven timestamps across the clip; images use one frame.
Tesseract OCR identifies known publisher brands and persistent screen-fixed text
in corner, lower-third, and ticker regions. A structured AI classifier then
reviews only the source metadata and deterministic evidence—it cannot override
a deterministic publisher/overlay blocker. The result is persisted as one of
`not_scanned`, `needs_review`, `passed`, or `rejected`, with timestamps, OCR
findings, a contact sheet, evidence, and approval blockers.

Only `passed` media receives or retains `download_path`. Uncertain or rejected
files retain a `quarantine_path` for evidence review but cannot be approved,
selected by the timeline planner, or rendered. Studio shows the contact sheet,
source identity, detected brands, clean-B-roll score, flags, reasons, and an
Analyze action. A human still confirms relevance and usage rights for clean
yellow-tier media; content cleanliness is not a licence grant.

Every web result is yellow-tier because search discovery does not establish a
license. The editor must verify ownership/license, attribution, and editorial-use
basis before manual approval. A result without a local `download_path` cannot be
approved or placed on the render timeline.

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

## Hosted LLM configuration

Production generation uses an explicitly selected hosted provider:

```bash
SYNTHPOST_LLM_PROVIDER=groq
GROQ_API_KEY=replace_with_your_groq_api_key
SYNTHPOST_GROQ_MODEL=openai/gpt-oss-120b
```

Gemini can be selected explicitly with `SYNTHPOST_LLM_PROVIDER=gemini`. An
explicit `hosted_fallback` option uses Groq first and Gemini second; it never
invokes a local model. Provider errors otherwise fail visibly. The deterministic
mock provider is reserved for automated tests and smoke demos, not production
script generation.

For deterministic tests only:

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

- SearXNG video results often point to watch pages rather than direct media.
  Optional `yt-dlp` acquisition makes them previewable, but semantic/editorial
  fitness and usage rights still require review before approval.
- Stronger article extraction for difficult publisher pages.
- More robust NLP/entity extraction and claim contradiction checks.
- Section-level regeneration and richer approval history in the UI.
- Remotion Player embedded directly in Studio for interactive playback; current Studio consumes generated preview/render artifacts.
- Full timeline-aligned avatar/source-audio pause synthesis. The explicit `audio_plan` exists, but the retained Avatar Engine is still invoked as a story-level render by default.
- Multi-story episode editing UI beyond assembling the selected episode story list.

See `docs/rebuild-baseline.md`, `docs/v2-architecture.md`, and `docs/rebuild-final-report.md` for implementation details.
