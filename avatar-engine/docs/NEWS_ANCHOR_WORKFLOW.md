# News Anchor Workflow

`desk-avatar-engine` is the local rendering component for an AI-automated news channel. Upstream systems can generate a script and camera plan; this project turns that job JSON into a talking news-anchor MP4.

## Role In The Larger Pipeline

Typical channel flow:

1. Collect or write news stories.
2. Generate a short anchor script.
3. Choose camera cuts and basic gestures.
4. Write a `jobs/<job_id>.json` file.
5. Run `scripts/run_job.py`.
6. Hand the generated MP4 or native camera-clip folder to the episode compositor/editor.

This repo owns only the anchor-render stage. It does not fetch news, decide editorial content, publish videos, or call cloud TTS APIs.

## Main Commands

Always activate the project venv first:

```bash
source .venv/bin/activate
```

Fast framing/lip-sync preview:

```bash
python3 scripts/run_job.py jobs/news_anchor_preview.json --force-all
```

Final-quality anchor segment:

```bash
python3 scripts/run_job.py jobs/news_anchor_segment.json --force-all
```

Native portrait/landscape clip export for downstream editing:

```bash
python3 scripts/run_job.py jobs/news_anchor_native_segments.json --force-all
```

Check what would be reused or regenerated:

```bash
python3 scripts/run_job.py jobs/news_anchor_segment.json --status
```

## Job JSON Contract

Required fields:

- `job_id`: output folder and manifest id.
- `script`: spoken anchor copy.
- `character`: character asset id, currently `avatar_01`.
- `face_mode`: usually `"2d"`.
- `camera_cuts`: semantic camera sequence.
- `output_path`: final MP4 path.

Common optional fields:

- `voice`: overrides TTS defaults.
- `performance_beats`: placeholder gestures and expression presets.
- `gestures`: Blender Action gestures if the template contains matching Actions.
- `render_profile`: `"preview"` or `"production"`.
- `fps`: render/export framerate; usually provided by `render_profile`.
- `resolution`: final MP4 canvas size; usually provided by `render_profile`.
- `render_quality`: set to `"draft"` for quick previews.
- `render_samples`: lower samples for draft mode.
- `disable_shadows`: use only for throwaway previews.
- `camera_resolution_scale`: multiplies each template camera's saved per-camera resolution.
- `use_per_camera_resolution`: defaults to `true`; keep it true for mixed portrait/landscape camera framing.
- `export_mode`: `"combined"` or `"native_segments"`.
- `segment_output_dir`: output folder for native segment clips.

## Camera Semantics

Use semantic camera names in jobs:

- `landscape_intro`: wide opening desk or newsroom shot.
- `portrait_main`: tight anchor shot.
- `landscape_conclusion`: wide/alternate closing shot.

These map to Blender objects:

- `CAM_Landscape_Intro`
- `CAM_Portrait_Main`
- `CAM_Landscape_Conclusion`

The Blender template uses the Per-Camera Resolution addon. The runner preserves each camera's aspect ratio during render.

## Export Modes

Use `combined` for quick review videos:

```json
"export_mode": "combined",
"output_path": "assets/output/news_anchor_preview.mp4"
```

This creates one MP4. Portrait frames are padded into the final landscape canvas, so this mode is convenient for preview but less ideal for editing.

Use `native_segments` when this repo acts as a backend for another editing/compositing project:

```json
"export_mode": "native_segments",
"segment_output_dir": "assets/output/news_anchor_native_segments",
"output_path": "assets/output/news_anchor_native_segments.mp4"
```

This writes one MP4 per camera cut and preserves each cut's native aspect ratio:

```text
assets/output/news_anchor_native_segments/
  001_landscape_intro.mp4
  002_portrait_main.mp4
  003_landscape_conclusion.mp4
  edit_manifest.json
```

The segment `edit_manifest.json` records the camera name, time range, frame range, clip duration, source resolution, and clip path. Downstream tools should consume this folder instead of a black-barred combined preview.

## Render Profiles

Render profiles live in `config/default.yaml` and are merged into the job before validation, stale checks, TTS, Blender rendering, and FFmpeg export.

Use `preview` for fast human checks:

```json
"render_profile": "preview"
```

The preview profile uses draft render settings and `combined` MP4 export.

Use `production` for the automated news backend:

```json
"render_profile": "production",
"segment_output_dir": "assets/output/<job_id>"
```

The production profile uses native camera segment export by default. Jobs can still override individual profile fields, but the normal production path should keep `native_segments` so portrait and landscape camera views remain separate for editing.

The runner writes the merged job to:

```text
assets/temp/<job_id>/effective_job.json
```

## Demo Jobs

The combined preview demo is for quick human review:

```bash
python3 scripts/run_job.py jobs/news_anchor_preview.json --force-all
```

It writes:

```text
assets/output/news_anchor_preview.mp4
```

The native segment demo is for backend/editor integration:

```bash
python3 scripts/run_job.py jobs/news_anchor_native_segments.json --force-all
```

It writes:

```text
assets/output/news_anchor_native_segments/
  001_landscape_intro.mp4
  002_portrait_main.mp4
  003_landscape_conclusion.mp4
  edit_manifest.json
```

The expected demo dimensions are `1920x1080` for landscape clips and `900x1328` for the portrait clip with the current template/camera scale. Generated demo videos are local build artifacts and should be regenerated, not committed.

## Preview Vs Final

Preview jobs should optimize for speed:

```json
"render_profile": "preview"
```

Production jobs should optimize for image quality and downstream editing:

```json
"render_profile": "production"
```

Do not use `disable_shadows` for final news segments. It makes previews fast, but it removes depth and newsroom lighting.

## Generated Files

Each job writes only generated files under:

- `assets/temp/<job_id>/`
- `assets/renders/<job_id>/`
- `assets/output/`

Each job also writes:

```text
assets/temp/<job_id>/run_manifest.json
```

The manifest records hashes, durations, frame counts, stale status, render paths, output paths, and the Blender template mtime.

For `native_segments` jobs, the manifest records the render profile, segment folder, and all exported clip artifacts.

## Safety Rules

- Runtime commands must not save or overwrite `blender/avatar_template.blend`.
- Use `blender/avatar_template.blend` as the production scene.
- Keep alternate `.blend` experiments local unless intentionally promoting one to production.
- Use `--status` before reusing frames with skip flags.
- Use `--force-all` after changing script text, voice settings, mouth textures, cameras, Blender scene contents, or render quality.
