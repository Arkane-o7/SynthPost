# Change Log

## Unreleased — SynthPost CC4 browser runtime update

Baseline for this change log: `5e7c6dc` / `origin/main` (`Add render profiles for news anchor outputs`).

This update adds a fast local 3D avatar rendering path for the SynthPost anchor while preserving the legacy Blender pipeline.

### Added

- New `avatar_engine/` Python package with renderer abstraction and CLI entry point:
  - `avatar_engine.render_avatar`
  - `AvatarJob`, `AvatarRenderResult`, renderer factory, and renderer adapters.
- Custom browser/Three.js CC4/Reallusion runtime under `web_avatar_runtime/`.
- Compatibility renderer key `rocketbox` for the active CC4 runtime.
- Local browser rendering pipeline:
  - loads local GLB avatar assets,
  - consumes precomputed Rhubarb visemes,
  - captures deterministic PNG frames from the WebGL canvas,
  - muxes final MP4 with FFmpeg and original WAV audio.
- Reallusion/CC4 facial animation support:
  - Rhubarb/Oculus visemes mapped to Reallusion `V_*` morphs,
  - blink and soft neutral expression,
  - jaw/lower teeth/upper teeth/tongue bone motion,
  - smoothed speech-driven tongue movement.
- Procedural anchor body animation:
  - relaxed torso/head motion,
  - lowered shoulder pose,
  - subtle smoothed forearm/hand motion while speaking.
- Active SynthPost anchor metadata:
  - `assets/avatars/synthpost_anchor_v1/avatar.json`
  - active binary expected at `assets/avatars/synthpost_anchor_v1/anchor.glb`.
- SynthPost CC4 jobs:
  - `jobs/synthpost_anchor_v1_quick_test.json`
  - `jobs/synthpost_anchor_v1_preview.json`
  - `jobs/synthpost_anchor_v1_chroma.json`
  - `jobs/synthpost_anchor_v1_tts_af_bella.json`
- Kokoro TTS audition tooling:
  - `scripts/audition_kokoro_voices.py`
  - `scripts/audition_indian_english.py`
- Browser runtime dependencies and config:
  - `web_avatar_runtime/package.json`
  - Vite/TypeScript config and runtime sources.
- Tests and fixtures for renderer selection, TalkingHead/3D job handling, manifests, and Rhubarb conversion.
- Third-party license notes for the included TalkingHead spike dependency/reference.
- New docs:
  - current 3D runtime design,
  - SynthPost integration guide,
  - updated browser renderer performance notes.

### Changed

- Default Kokoro voice in `config/default.yaml` is now:

  ```yaml
  tts:
    engine: kokoro
    voice: af_bella
    speed: 1.0
    sample_rate: 24000
    lang_code: a
  ```

- Current SynthPost 3D jobs now point at generated `af_bella` audio/Rhubarb paths under `assets/output/tts/`.
- `.gitignore` now excludes generated runtime outputs, browser build outputs, avatar binaries, and bulky CC/Reallusion texture export folders.
- `requirements.txt` now includes browser/runtime dependencies needed by the 3D path.
- Documentation now treats Blender as the legacy path and the CC4 browser runtime as the current SynthPost anchor path.

### Preserved

- Legacy Blender jobs and `scripts/run_job.py` flow remain available.
- Existing Blender render profiles and `combined` / `native_segments` export modes remain documented.
- 2D face mode via `FACE_Surface` / `FACE_Backdrop` remains supported in the Blender path.
- `assets/output/`, `assets/temp/`, and `assets/renders/` remain generated artifacts and are not committed.

### Migration notes for downstream projects

1. Pull this commit and install Python dependencies from `requirements.txt`.
2. Install the browser runtime dependencies:

   ```bash
   npm --prefix web_avatar_runtime install
   ```

3. Provide the CC4 GLB asset at:

   ```text
   assets/avatars/synthpost_anchor_v1/anchor.glb
   ```

   The GLB is intentionally not committed because avatar binaries are large/licensed assets.

4. Generate story-specific Kokoro WAV + Rhubarb JSON, or regenerate the default selected voice sample:

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

5. Render with the compatibility key:

   ```bash
   .venv/bin/python3 -c 'import runpy, sys; sys.argv=["render_avatar","--job","jobs/synthpost_anchor_v1_preview.json","--renderer","rocketbox"]; runpy.run_module("avatar_engine.render_avatar", run_name="__main__")'
   ```

6. For compositor usage, prefer `jobs/synthpost_anchor_v1_chroma.json` and chroma-key the generated MP4.

### Known compatibility caveat

The active 3D renderer is selected with `renderer: "rocketbox"`, but it is no longer a Rocketbox renderer. It is a custom Three.js driver for the current CC4/Reallusion SynthPost anchor. Future cleanup should add a clearer renderer alias such as `cc4_threejs` while preserving `rocketbox` for older jobs.
