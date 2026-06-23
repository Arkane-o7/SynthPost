# SynthPost

SynthPost is a local, manifest-driven pipeline for generating an AI-assisted YouTube news episode. The current build focuses on Milestone 2: one hand-authored story flows through direction, Avatar-Engine integration, Remotion compositing, and ffmpeg assembly.

## Current Slice

- `avatar-engine/` is cloned from `https://github.com/Arkane-o7/Avatar-Engine.git` and is treated as a black box.
- Every story is driven by one `story.json` manifest.
- `pipeline/run_story.py` runs direction, optional Avatar rendering, compositor rendering, and optional assembly.
- The Remotion templates include **Split Main** (`split_main` / `split-main`) and **Full Screen Anchor** (`full_screen_anchor` / `full-screen-anchor`) at `1920x1080`.
- `full_screen_anchor` is for opening remarks, conclusions, and “our take” segments. It reuses the shared SynthPost logo/lower-third/chyron components and asks Avatar-Engine for the `landscape_intro` camera.
- The Remotion renderer also includes a reusable **SynthPostEndscreen** composition. Render it with `npm run render:endscreen -- <endscreen.json>` or `python3 -m pipeline.endscreen <episode_id>`.
- `assembly/stitch_episode.py` normalizes intro, story clips, and outro before concatenation.
- `src/synthpost/visuals/` plans story visuals with provider metadata, ranking, licensing notes, and timed manifest output.

## Quick Start

Install Remotion dependencies:

```bash
cd compositor/remotion_renderer
npm install
```

Render the sample story after an anchor clip exists:

```bash
python3 -m pipeline.run_story episodes/ep_2026-06-20/stories/story_001/story.json --skip-avatar-render --force-composite
python3 assembly/stitch_episode.py ep_2026-06-20
```

To let SynthPost call Avatar-Engine directly:

```bash
python3 -m pipeline.run_story episodes/ep_2026-06-20/stories/story_001/story.json --test-mode --force-avatar --force-composite
```

The anchor output expected by the sample story is:

```text
episodes/ep_2026-06-20/stories/story_001/anchor.mp4
```

## Avatar-Engine Notes

The current `avatar-engine/README.md` says the main command is:

```bash
python3 scripts/run_job.py jobs/news_anchor_preview.json --force-all
```

It also exposes a TTS-only command through `scripts/generate_tts.py`, so SynthPost's direction stage supports a future two-pass timing mode with `SYNTHPOST_AVATAR_TTS_PROBE=1`. Without that flag, v1 uses a words-per-minute estimate and scales deterministic camera/gesture timing.

Local doctor status observed during setup:

- Blender, ffmpeg, and Rhubarb were detected.
- Kokoro was not installed, so Avatar-Engine would use placeholder WAV fallback unless Kokoro is added.
- The current Avatar-Engine doctor reported missing required template objects in `avatar_template.blend`; the user chose to handle the standalone sample render manually.

## Environment

Copy `config/.env.example` into your shell or a local `.env` loader if desired. External services are optional for Milestone 2; missing providers fall back to deterministic local behavior where possible.

## Manifest Contract

Each stage reads `episodes/<episode_id>/stories/<story_id>/story.json` and writes only its own section:

- `raw`: collected or hand-authored source material
- `script`: spoken copy and headline
- `direction`: Avatar-Engine job data and anchor output path
- `visuals`: timed story media
- `points`: lower-third bullet facts
- `composition`: Remotion template and output path

The schema lives at `pipeline/schemas/story_manifest.schema.json`.

## News Visuals

`pipeline/visuals/default.py` is now a thin adapter over `src/synthpost/visuals`. It builds a timed visual rundown from the story manifest, writes rich provenance metadata into `visuals[]` and `visual_assets[]`, and saves an audit file at:

```text
episodes/<episode_id>/stories/<story_id>/visuals/visuals_audit.json
```

Provider priority is newsroom-style and rights-aware:

- `manifest_media`: explicit story media from `raw.visual_assets`, `raw.media_assets`, `raw.official_media`, `raw.image_urls`, or `raw.video_urls`
- India official drop folders: `pb_shabd_dropfolder`, `pib_india`, `isro_media`, `pm_india_media`, `india_ministry_media`, `mea_india_media`
- Global official/public-domain drop folders: `dvids`, `nasa_media`, `eu_av`, `white_house_media`, `us_state_department_flickr`, `noaa_media`, `usgs_media`, `copernicus_data`
- Open/public archives: `wikimedia`, `openverse`, `library_of_congress`, `nara_archives`, `internet_archive`, `natural_earth_maps`
- Context/document sources: `official_page_screenshot`, `document_screenshot`, `court_document_source`, `parliament_or_legislature_source`, `company_press_kit`
- Social: `social_media_leads` collects leads; `social_reference_ingest` only renders approved yellow references when `SYNTHPOST_ALLOW_RISKY_SOCIAL=1`
- Stock fallback: `pexels_pixabay_optional` remains available, but is marked as `content_role: atmosphere` and ranks last

Every selected visual carries `rights_tier`, `rights_confidence`, `usage_basis`, `source_authority`, `content_role`, `media_type`, `risk_level`, `manual_review_status`, attribution fields, and a still-image `motion` preset. Green assets are auto-selectable. Yellow assets require explicit enablement and approval metadata. Red assets are never auto-selected.

PB-SHABD and PIB are separate sources. PB-SHABD is modeled as a safe authenticated/manual export source, not as an access-control bypass. Put exports in a configured folder such as:

```text
media/sources/pb_shabd_dropfolder/
media/sources/pib_india/
```

Each media file can have a sidecar:

```json
{
  "title": "Cabinet briefing visuals",
  "source_url": "https://shabd.prasarbharati.org/",
  "source_name": "PB-SHABD / Prasar Bharati",
  "license": "official_press",
  "usage_basis": "official_press",
  "rights_tier": "green",
  "rights_confidence": "verified",
  "attribution_required": true,
  "attribution_text": "Source: PB-SHABD / Prasar Bharati",
  "keywords": ["cabinet", "briefing", "india"],
  "safe_to_use": true
}
```

Generic stock video is intentionally ranked below manifest, official, open archive, document/map/chart, and approved social media. It is used only when there is no better rights-clear visual for that segment, and it is never presented as actual event evidence.

To provide official or rights-cleared media directly in a story manifest:

```json
"raw": {
  "official_media": [
    {
      "url": "https://example.gov/media/briefing.mp4",
      "asset_type": "video",
      "source_name": "Example Agency",
      "license": "public domain",
      "usage_note": "Official government briefing footage.",
      "rights_tier": "green",
      "rights_confidence": "verified",
      "usage_basis": "public_domain",
      "source_authority": "official",
      "content_role": "evidence",
      "media_type": "video",
      "manual_review_status": "not_required",
      "safe_to_use": true,
      "keywords": ["briefing", "agency", "policy"]
    }
  ]
}
```

Visual pacing is duration-based by default. Use `SYNTHPOST_VISUAL_SECONDS_PER_BEAT`, `SYNTHPOST_VISUAL_MIN_SEGMENTS`, and `SYNTHPOST_VISUAL_MAX_SEGMENTS` to tune how often the right panel changes, or set `SYNTHPOST_VISUAL_SEGMENTS` to force an exact count. Still images get motion presets in Remotion: photos push in, documents scan, maps zoom, charts reveal, screenshots focus, and stock gets a restrained atmospheric pan.

To refresh visuals without rerendering the anchor:

```bash
python3 -m pipeline.run_story episodes/ep_2026-06-21-ferc-grid/stories/story_001/story.json --force-visuals --skip-avatar-render --force-composite
```
