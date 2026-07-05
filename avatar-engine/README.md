# desk-avatar-engine

`desk-avatar-engine` is the local news-anchor rendering module for an AI-automated news channel. It supports two local-first paths:

- a legacy Blender desk scene pipeline for 2D/texture-mouth anchor renders, and
- a fast browser/Three.js CC4/Reallusion avatar pipeline for the current 3D SynthPost anchor.

The current 3D path loads a local GLB avatar, generates/consumes Kokoro TTS audio, generates Rhubarb mouth cues, drives Reallusion facial morphs and CC4 skeleton bones, captures deterministic PNG frames from the browser canvas, and muxes the final MP4 with FFmpeg.

This is intentionally not a photorealistic MetaHuman pipeline and does not use cloud APIs.

## Current Status

- The local pipeline runs end to end from a job JSON to an MP4.
- The active 3D anchor is `assets/avatars/synthpost_anchor_v1/anchor.glb` with metadata in `assets/avatars/synthpost_anchor_v1/avatar.json`.
- The active 3D renderer is a custom Three.js CC4/Reallusion runtime under the legacy `rocketbox` renderer name. The name is kept for compatibility; it is not using Rocketbox assets anymore.
- The 3D runtime maps Rhubarb/Oculus visemes to Reallusion `V_*` morphs and drives jaw, lower/upper teeth, tongue, blink, head/body posture, and subtle procedural speaking gestures.
- Browser capture uses deterministic canvas PNG frames plus FFmpeg audio muxing. Do not use Playwright viewport video or canvas `MediaRecorder` for production captures.
- Rhubarb, Blender, FFmpeg, and local Kokoro TTS defaults can be configured through `config/default.yaml`.
- The selected default Kokoro voice is `af_bella` at `speed: 1.0`, `lang_code: a`.
- `blender/avatar_template.blend` is the protected legacy production scene. Runtime scripts load it only and must not overwrite it.
- 2D face mode still uses `FACE_Backdrop` and `FACE_Surface`; Rhubarb cues swap mouth PNG textures on `FACE_Surface`.
- Legacy Blender camera jobs use semantic POVs: `landscape_intro`, `portrait_main`, and `landscape_conclusion`.
- Export supports either one combined preview MP4 or separate native-aspect camera clips for downstream editing.

## Documentation

- [News Anchor Workflow](docs/NEWS_ANCHOR_WORKFLOW.md): how this module fits into the AI news channel.
- [Current 3D Runtime Design](docs/talkinghead_runtime_design.md): custom Three.js/CC4 renderer, capture path, and job contract.
- [SynthPost Integration Guide](docs/synthpost_integration.md): how downstream projects should call Avatar-Engine.
- [Renderer Benchmark Notes](docs/talkinghead_benchmark.md): current browser renderer timing notes and caveats.
- [Change Log](CHANGELOG.md): migration-oriented summary since the last GitHub baseline.
- [Blender Scene Guide](docs/BLENDER_SCENE_GUIDE.md): required objects, cameras, face setup, Actions, and scene contract.
- [Rendering And Optimization](docs/RENDERING_AND_OPTIMIZATION.md): preview vs final quality, polygon reduction, baking, and speed tips.
- [Avatar 01 Notes](assets/characters/avatar_01/README.md): legacy character asset expectations and mouth texture setup.
- [Gesture Asset Notes](assets/characters/avatar_01/gestures/README.md): placeholder for future exported gesture clips.
- [Agent Notes](AGENTS.md): repo guardrails for future agent work.

## Project Flow

Input:

```text
jobs/sample_job.json
```

Output:

```text
assets/output/<job_id>.mp4
```

Native segment jobs output a folder instead:

```text
assets/output/<job_id>/
```

Legacy Blender pipeline:

1. Load and validate the job JSON.
2. Generate local Kokoro TTS audio when available, or a placeholder WAV when Kokoro is missing or test mode is enabled.
3. Generate Rhubarb lip-sync cues, or fake Rhubarb-style cues when Rhubarb is missing.
4. Run Blender in background mode when Blender and `blender/avatar_template.blend` are available.
5. Animate mouth cues, expressions, gestures, and camera cuts.
6. Render PNG frames to `assets/renders/<job_id>/`.
7. Export an MP4 with FFmpeg when FFmpeg is available.

Current 3D CC4 pipeline:

1. Generate or provide a WAV file.
2. Generate Rhubarb JSON for that WAV.
3. Render a `rocketbox`/custom-Three.js job with `avatar_engine.render_avatar`.
4. Browser runtime loads `anchor.glb`, applies Reallusion morphs/bones, captures PNG frames, and FFmpeg muxes the original WAV into the MP4.

## Quick 3D SynthPost Anchor Commands

Run from the repository root (`desk-avatar-engine`) unless noted.

Generate the selected `af_bella` Kokoro voice and Rhubarb cues:

```bash
.venv/bin/python3 scripts/generate_tts.py \
  jobs/synthpost_anchor_v1_tts_af_bella.json \
  assets/output/tts/synthpost_anchor_v1_af_bella_s100.wav \
  --config config/default.yaml

.venv/bin/python3 scripts/generate_lipsync.py \
  assets/output/tts/synthpost_anchor_v1_af_bella_s100.wav \
  assets/output/tts/synthpost_anchor_v1_af_bella_s100_rhubarb.json \
  --config config/default.yaml
```

Render the current 3D anchor preview:

```bash
npm --prefix web_avatar_runtime run build
.venv/bin/python3 -c 'import runpy, sys; sys.argv=["render_avatar","--job","jobs/synthpost_anchor_v1_preview.json","--renderer","rocketbox"]; runpy.run_module("avatar_engine.render_avatar", run_name="__main__")'
```

Render chroma output for compositing:

```bash
.venv/bin/python3 -c 'import runpy, sys; sys.argv=["render_avatar","--job","jobs/synthpost_anchor_v1_chroma.json","--renderer","rocketbox"]; runpy.run_module("avatar_engine.render_avatar", run_name="__main__")'
```

Outputs:

```text
assets/output/synthpost_anchor_v1_preview.mp4
assets/output/synthpost_anchor_v1_chroma.mp4
```

## Quick Legacy Blender News Anchor Commands

Always activate the venv first:

```bash
source .venv/bin/activate
```

Fast preview:

```bash
python3 scripts/run_job.py jobs/news_anchor_preview.json --force-all
```

Backend/editor segment export:

```bash
python3 scripts/run_job.py jobs/news_anchor_native_segments.json --force-all
```

Final-quality segment:

```bash
python3 scripts/run_job.py jobs/news_anchor_segment.json --force-all
```

Check stale/reuse status:

```bash
python3 scripts/run_job.py jobs/news_anchor_segment.json --status
```

## Demo Outputs

Generate the quick combined demo:

```bash
python3 scripts/run_job.py jobs/news_anchor_preview.json --force-all
```

This writes:

```text
assets/output/news_anchor_preview.mp4
```

Generate the backend/editor demo with separate native camera clips:

```bash
python3 scripts/run_job.py jobs/news_anchor_native_segments.json --force-all
```

This writes:

```text
assets/output/news_anchor_native_segments/
  001_landscape_intro.mp4
  002_portrait_main.mp4
  003_landscape_conclusion.mp4
  edit_manifest.json
```

Expected demo clip shapes:

- `001_landscape_intro.mp4`: landscape, `1920x1080`
- `002_portrait_main.mp4`: portrait, `900x1328`
- `003_landscape_conclusion.mp4`: landscape, `1920x1080`

Generated demo videos are build artifacts and are not committed. Regenerate them locally when needed.

## Required Tools

Required for the full normal pipeline:

- Python 3.11+
- Blender
- FFmpeg
- Rhubarb Lip Sync
- A prepared `blender/avatar_template.blend`

Optional:

- Kokoro local TTS

The MVP can run in test mode without Kokoro, Rhubarb, Blender, or FFmpeg. Missing tools print clear warnings. If Kokoro is missing or installed incorrectly, the runner writes the same placeholder WAV fallback. If Blender is missing, the runner creates placeholder PNG frames. If FFmpeg is missing, MP4 export is skipped in test mode.

## Install

```bash
cd desk-avatar-engine
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `python3.11` is not the command on your machine, use any Python 3.11+ interpreter.

## Configure Tools

Edit `config/default.yaml`:

```yaml
tools:
  blender: blender
  rhubarb: rhubarb
  ffmpeg: ffmpeg

tts:
  engine: kokoro
  voice: af_bella
  speed: 1.0
  sample_rate: 24000
  lang_code: a

render_profiles:
  preview:
    fps: 12
    resolution: [960, 540]
    render_quality: draft
    render_samples: 4
    disable_shadows: true
    camera_resolution_scale: 1.0
    export_mode: combined
  production:
    fps: 24
    resolution: [1920, 1080]
    camera_resolution_scale: 1.0
    camera_resolution_overrides:
      portrait_main:
        scale: 1.0
    export_mode: native_segments
```

Each value can be either a command available on `PATH` or an absolute path to the binary.

`tts.voice`, `tts.speed`, `tts.sample_rate`, and `tts.lang_code` are defaults. A job can override them in its `voice` block with `voice_id` or `voice`, `speed`, `sample_rate`, and `engine`.

## Health Check

Run the doctor before debugging a job:

```bash
python3 scripts/doctor.py
```

It checks Python, config loading, Blender, FFmpeg, Rhubarb, Kokoro availability, the production Blender template, sample job loading, asset folders, and required mouth textures. Kokoro is reported as `OK` when importable and `WARN` when the placeholder fallback will be used.

## Kokoro TTS

Kokoro is optional but preferred for normal local speech generation. Install and configure Kokoro in the same Python environment used to run `scripts/run_job.py` and `avatar_engine.render_avatar`.

The current selected voice for SynthPost anchor tests is:

```yaml
tts:
  engine: kokoro
  voice: af_bella
  speed: 1.0
  sample_rate: 24000
  lang_code: a
```

Audition helpers are available for choosing future voices:

```bash
.venv/bin/python3 scripts/audition_kokoro_voices.py --speed 0.95
.venv/bin/python3 scripts/audition_kokoro_voices.py --speed 1.10
.venv/bin/python3 scripts/audition_kokoro_voices.py \
  --output-dir assets/output/tts/auditions/indian_accent_english_s110 \
  --voices hf_alpha,hf_beta,hm_omega,hm_psi \
  --speed 1.10
```

Generated audition WAVs are written under `assets/output/tts/auditions/` and are intentionally ignored by Git.

For the common Python package setup:

```bash
source .venv/bin/activate
pip install kokoro
```

If Kokoro needs additional local model or phonemizer setup on your machine, follow the Kokoro package instructions, then rerun:

```bash
python3 scripts/doctor.py
```

Audio-only smoke test:

```bash
source .venv/bin/activate
python scripts/generate_tts.py jobs/sample_job.json --config config/default.yaml
afplay assets/temp/sample_desk_avatar/audio.wav
```

The standalone command writes to `assets/temp/<job_id>/audio.wav` by default. To choose a path:

```bash
python scripts/generate_tts.py jobs/sample_job.json assets/temp/sample_desk_avatar/audio.wav --config config/default.yaml
```

When Kokoro is not importable, lacks the expected `KPipeline` API, or fails during synthesis, the script logs a warning and writes a placeholder WAV instead of crashing. Test mode always uses the placeholder WAV.

## Validate The Blender Template

To inspect the production template for required object names without saving it:

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b blender/avatar_template.blend --python blender/validate_template.py
```

Required objects:

- `CHAR_Avatar`
- `ARM_Avatar`
- `FACE_Surface`
- `FACE_Backdrop`
- `CAM_Portrait_Main`
- `CAM_Landscape_Intro`
- `CAM_Landscape_Conclusion`

## Run Test Mode

```bash
python3 scripts/run_job.py jobs/sample_job.json --test-mode
```

Test mode will:

- Generate a local placeholder WAV at `assets/temp/<job_id>/audio.wav`.
- Generate fake Rhubarb-style cues at `assets/temp/<job_id>/mouth_cues.json`.
- Create placeholder PNG frames if Blender or the template file is unavailable.
- Export `assets/output/<job_id>.mp4` if FFmpeg is installed.
- Skip MP4 export with a warning if FFmpeg is unavailable.

## Run Normal Mode

Set `test_mode: false` in `config/default.yaml`, install the required tools, prepare the Blender template, then run:

```bash
python3 scripts/run_job.py jobs/sample_job.json
```

You can also keep config defaults and force test mode only when needed:

```bash
python3 scripts/run_job.py jobs/sample_job.json --test-mode
```

Useful development flags:

```bash
python3 scripts/run_job.py jobs/sample_job.json --status
python3 scripts/run_job.py jobs/sample_job.json --skip-render
python3 scripts/run_job.py jobs/sample_job.json --skip-export
python3 scripts/run_job.py jobs/sample_job.json --skip-render --skip-export
python3 scripts/run_job.py jobs/sample_job.json --skip-tts --skip-lipsync
python3 scripts/run_job.py jobs/sample_job.json --force-all
python3 scripts/run_job.py jobs/sample_job.json --clean
```

Skip flags reuse existing generated files under `assets/temp/<job_id>/` and `assets/renders/<job_id>/`. The runner checks dependencies and prints stale-output warnings when reused files do not match the current job, config, audio, mouth cues, frames, or MP4.

Use `--skip-render` only when audio and mouth cues have not changed since the frames were rendered. Do not use `--skip-render` after changing the script text, voice settings, TTS output, Rhubarb output, mouth textures, camera cuts, or anything visual in the Blender scene. If you are unsure, run without `--skip-render`.

Use `--status` to inspect what is fresh, stale, or missing without running Kokoro, Rhubarb, Blender, or FFmpeg:

```bash
python3 scripts/run_job.py jobs/sample_job.json --status
```

Use `--force-all` when you want a clean dependency-respecting rebuild of generated outputs:

```bash
python3 scripts/run_job.py jobs/sample_job.json --force-all
```

Stage-specific force flags are also available: `--force-tts`, `--force-lipsync`, `--force-render`, and `--force-export`. Force flags regenerate that stage even if a skip flag was passed. `--clean` removes only this job's generated temp folder, render folder, and generated output MP4 or segment folder before running.

## News Anchor Cameras

Use these semantic camera names in job JSON:

- `landscape_intro`: wide opening newsroom/desk shot.
- `portrait_main`: tight anchor shot.
- `landscape_conclusion`: alternate wide or closing shot.

They map to:

- `CAM_Landscape_Intro`
- `CAM_Portrait_Main`
- `CAM_Landscape_Conclusion`

The production template uses per-camera resolution settings. Keep that enabled for mixed POV jobs so portrait shots keep their vertical framing.

## Export Modes

The default export mode is `combined`. It creates one MP4 at `output_path`. When the job mixes landscape and portrait cameras, FFmpeg scales and pads each frame into the job's final canvas instead of cropping it. This is convenient for quick previews and human review.

```json
"export_mode": "combined",
"output_path": "assets/output/news_anchor_preview.mp4"
```

For backend use in another editor/compositor project, prefer `native_segments`. It exports one MP4 per camera cut at that cut's native camera aspect ratio, plus an `edit_manifest.json` describing the timeline.

```json
"export_mode": "native_segments",
"segment_output_dir": "assets/output/news_anchor_native_segments",
"output_path": "assets/output/news_anchor_native_segments.mp4"
```

The `output_path` field remains required for compatibility. In `native_segments` mode, `segment_output_dir` is the folder consumed by the downstream project:

```text
assets/output/news_anchor_native_segments/
  001_landscape_intro.mp4
  002_portrait_main.mp4
  003_landscape_conclusion.mp4
  edit_manifest.json
```

Use `native_segments` when this repo is acting as a backend for another project. It gives the editor/compositor clean portrait and landscape clips without black bars baked into the video.

## Render Profiles

Jobs can use a render profile from `config/default.yaml`:

```json
"render_profile": "preview"
```

Profiles fill in render/export defaults before the job is validated and before Blender runs. Job fields still win over profile fields, so a job can override a specific setting when needed.

Built-in profiles:

- `preview`: fast draft mode, `12 fps`, `960x540`, low samples, shadows disabled, `combined` MP4 export.
- `production`: final-news mode, `24 fps`, `1920x1080`, native camera scale, portrait camera override, `native_segments` export.

With the current template camera settings, `production` renders native segment clips around `1920x1080` for landscape cameras and about `900x1328` for the portrait camera. These source clips are close to the final `1920x1080` episode canvas instead of being oversized. Use `preview` for iteration and `production` only when you are ready for the backend/editor-quality output.

For the automated news backend, use `production` as the normal path:

```json
"render_profile": "production",
"segment_output_dir": "assets/output/news_anchor_segment"
```

The runner writes the merged job used by Blender to:

```text
assets/temp/<job_id>/effective_job.json
```

Profiles already set common resolution and quality values. `camera_resolution_scale` is the global multiplier applied to every Blender camera's saved custom resolution:

```json
"resolution": [1920, 1080],
"camera_resolution_scale": 1.0
```

Use `camera_resolution_overrides` when only one camera should change. The nested `scale` is also a resolution multiplier, but it applies only to that camera and wins over `camera_resolution_scale`:

```json
"camera_resolution_overrides": {
  "portrait_main": {
    "scale": 1.0
  }
}
```

For fast previews:

```json
"resolution": [960, 540],
"camera_resolution_scale": 1.0,
"render_quality": "draft",
"render_samples": 4
```

## Preparing `blender/avatar_template.blend`

`blender/avatar_template.blend` is the real production scene used by normal pipeline runs. The pipeline only loads this file; it should not be generated or overwritten by runtime code.

Create or copy your production Blender scene to:

```text
blender/avatar_template.blend
```

There is also a manual dummy-template utility. Do not run it unless you intentionally want to create a basic placeholder scene. It writes to `blender/avatar_template_BASIC.blend`, not the production template.

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b -P blender/create_basic_template.py -- --force
```

Without `-- --force`, the helper refuses to overwrite an existing dummy template. This creates a basic desk scene with `CHAR_Avatar`, `ARM_Avatar`, `FACE_Surface`, `CAM_Portrait_Main`, `CAM_Landscape_Intro`, `CAM_Landscape_Conclusion`, desk, and lights. It is intentionally primitive, and you can inspect or manually copy from it while building your real scene.

For the MVP, the scene should include:

- Objects named `CHAR_Avatar`, `ARM_Avatar`, `FACE_Surface`, and `FACE_Backdrop`.
- Cameras named `CAM_Portrait_Main`, `CAM_Landscape_Intro`, and `CAM_Landscape_Conclusion`.
- A 2D face surface object named `FACE_Surface` when `face_mode` is `"2d"`.
- An avatar mesh with shape keys when using `face_mode` `"3d"`.
- Shape keys matching `blender/mouth_mapping.py` and `blender/expression_presets.py`.
- An armature with common bones such as `Head`, `UpperArm.L`, `UpperArm.R`, and `Hand.R` for placeholder gestures.

The Blender driver skips missing optional objects safely and prints warnings so a rough template can be improved incrementally.

## Blender Action Gestures

Presenter gestures can be authored as Blender Actions in `blender/avatar_template.blend` and scheduled from job JSON. Create Actions on the `ARM_Avatar` armature, key only rig/bone motion, and leave `FACE_Surface` and `FACE_Backdrop` alone. Those face objects should follow naturally through their parented character/head setup.

Optional Action names checked by the validator:

- `IDLE_Neutral`
- `HEAD_Nod_Small`
- `HEAD_Shake_Small`
- `RIGHT_Hand_Emphasis`
- `LEFT_Hand_Emphasis`
- `BOTH_Hands_Open`
- `LEAN_Forward`
- `LEAN_Back`
- `SHOULDER_Shrug`
- `RESET_Seated_Pose`

The names are warnings, not hard requirements. Missing Actions are logged and skipped so renders continue.

Job gesture format:

```json
"gestures": [
  { "time": 1.0, "action": "HEAD_Nod_Small" },
  { "time": 3.5, "action": "RIGHT_Hand_Emphasis", "duration": 1.2, "strength": 0.9 },
  { "time": 6.0, "action": "BOTH_Hands_Open", "blend_in": 0.15, "blend_out": 0.25 }
]
```

Supported optional fields are `duration`, `strength`, `blend_in`, and `blend_out`. Times and blend values are seconds. `strength` is clamped between 0 and 1. If `IDLE_Neutral` exists, it is applied lightly across the full shot behind scheduled gestures.

Run the gesture sample:

```bash
python3 scripts/run_job.py jobs/sample_gestures.json --force-all
```

## 2D Mouth Textures

For `face_mode: "2d"`, put transparent PNG mouth drawings in:

```text
assets/characters/avatar_01/mouth_textures/
```

Required filenames:

- `mouth_X.png` and `mouth_A.png`: closed/rest
- `mouth_B.png`: M/B/P
- `mouth_C.png`: E/I
- `mouth_D.png`: A/open
- `mouth_E.png`: O
- `mouth_F.png`: U/W
- `mouth_G.png`: F/V
- `mouth_H.png`: L

The PNGs should have the same canvas size, for example 512x512, with transparent background around the mouth art. During Blender renders, Rhubarb cues in `assets/temp/<job_id>/mouth_cues.json` swap the image texture on `FACE_Surface` frame by frame. Missing cue textures fall back to `mouth_X.png` with a warning; if `mouth_X.png` is also missing, the driver uses a flat fallback material and continues.

## Generated Files

Generated files are written only under:

- `assets/temp/<job_id>/`
- `assets/renders/<job_id>/`
- `assets/output/`

Each run writes a manifest to:

```text
assets/temp/<job_id>/run_manifest.json
```

The manifest records the job/config/script hashes, TTS engine used, audio hash and duration, mouth cue hash and duration, expected and actual frame counts, render and output paths, output duration, Blender template path and mtime, run timestamp, stale status, and the CLI flags used. The runner uses this manifest plus file mtimes/counts/durations to warn about stale audio, mouth cues, render frames, and MP4s.

For `native_segments` jobs, the run manifest also records `render_profile`, `export_mode`, the segment folder path, the segment clip paths, and the segment `edit_manifest.json` path.

These generated folders, media files, `.DS_Store`, `__pycache__`, and virtual environments should not be committed. Source files, jobs, config, character assets, mouth textures, and `blender/avatar_template.blend` are not deleted by `run_job.py`.

## Sample Jobs

- `jobs/news_anchor_preview.json`: fast news-anchor preview job.
- `jobs/news_anchor_native_segments.json`: fast backend sample that exports native portrait/landscape clips.
- `jobs/news_anchor_segment.json`: final-quality news-anchor segment sample.
- `jobs/sample_job.json`: full default sample.
- `jobs/sample_short_test.json`: short smoke test.
- `jobs/sample_portrait.json`: portrait camera sample.
- `jobs/sample_landscape_intro.json`: landscape camera sample.
- `jobs/sample_gestures.json`: Action-based presenter gesture sample.
