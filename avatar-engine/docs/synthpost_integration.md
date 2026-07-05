# SynthPost ↔ Avatar-Engine Integration Guide

## Overview

SynthPost calls Avatar-Engine to render the anchor avatar clip for each story. The current production-practical path is a local browser/Three.js renderer for a CC4/Reallusion GLB avatar. It is still selected with the legacy renderer key `rocketbox` for compatibility.

High-level flow:

```text
story script
→ Kokoro TTS WAV
→ Rhubarb mouth cues JSON
→ Avatar-Engine custom Three.js CC4 renderer
→ preview/chroma MP4
→ SynthPost compositor
```

The legacy Blender renderer remains available for older 2D/desk-scene jobs.

---

## 1. Environment variables (SynthPost side)

Recommended SynthPost settings:

```bash
# Current fast 3D CC4 renderer. Name is legacy; implementation is custom Three.js.
SYNTHPOST_AVATAR_RENDERER=rocketbox

# Absolute path to the desk-avatar-engine repository
SYNTHPOST_AVATAR_ENGINE_PATH=/path/to/desk-avatar-engine

# Avatar asset paths relative to Avatar-Engine repo root
SYNTHPOST_AVATAR_ASSET_PATH=assets/avatars/synthpost_anchor_v1/anchor.glb
SYNTHPOST_AVATAR_META_PATH=assets/avatars/synthpost_anchor_v1/avatar.json

# Current default output mode for compositor
SYNTHPOST_AVATAR_RENDER_BACKGROUND=chroma_green

# Optional fallback to Blender only if the calling app explicitly wants it
# AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK=1
```

Asset packaging note: `anchor.glb` is ignored by Git in this repo because GLB/texture exports are large. Downstream deployments must provide that file at the expected path or adapt the job metadata to another compatible CC4/Reallusion GLB.

---

## 2. TTS and lipsync contract

The active selected voice is:

```json
{
  "engine": "kokoro",
  "voice_id": "af_bella",
  "speed": 1.0,
  "sample_rate": 24000,
  "lang_code": "a"
}
```

Generate audio and lipsync before rendering:

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

For dynamic SynthPost stories, generate story-specific WAV/Rhubarb files and place those paths into `audio_path` and `viseme_path` in the render job.

---

## 3. Current 3D job shape

```json
{
  "renderer": "rocketbox",
  "episode_id": "ep01",
  "story_id": "story001",
  "script_text": "Good evening. This is the story script.",
  "audio_path": "episodes/ep01/stories/story001/audio/voice.wav",
  "viseme_path": "episodes/ep01/stories/story001/lipsync/rhubarb.json",
  "avatar": {
    "asset_path": "assets/avatars/synthpost_anchor_v1/anchor.glb",
    "metadata_path": "assets/avatars/synthpost_anchor_v1/avatar.json",
    "style": "professional_news_anchor",
    "face_type": "3d",
    "body_form": "F",
    "requires_3d_lips": true
  },
  "camera": {
    "name": "front_close",
    "width": 1280,
    "height": 720,
    "fps": 24,
    "duration_seconds": 8.0
  },
  "avatar_transform": {
    "rotation_y_degrees": -3
  },
  "camera_overrides": {
    "distance_multiplier": 3.5,
    "target_height_factor": 0.84,
    "height_factor": 0.86
  },
  "render": {
    "background": "chroma_green",
    "output_path": "episodes/ep01/stories/story001/anchor/anchor.mp4",
    "preview_png_path": "episodes/ep01/stories/story001/anchor/anchor_preview.png"
  },
  "animation": {
    "idle_loop": "procedural_anchor",
    "gesture_events": []
  },
  "face": {
    "mode": "3d_viseme",
    "viseme_source": "rhubarb",
    "blendshape_profile": "reallusion_viseme",
    "fallback_mode": "legacy_2d",
    "allow_fallback": false
  }
}
```

The `duration_seconds` should be at least the audio duration. The renderer also uses the decoded audio duration internally, but matching duration in the job keeps provenance and capture-frame expectations clear.

---

## 4. How SynthPost should call Avatar-Engine

### CLI subprocess (recommended)

```python
import os
import subprocess


def render_anchor_cc4(job_json_path: str, engine_path: str) -> int:
    venv_python = os.path.join(engine_path, ".venv", "bin", "python3")
    cmd = [
        venv_python,
        "-m",
        "avatar_engine.render_avatar",
        "--job",
        job_json_path,
        "--renderer",
        "rocketbox",
        "--config",
        os.path.join(engine_path, "config", "default.yaml"),
    ]
    env = {**os.environ, "PYTHONPATH": engine_path}
    result = subprocess.run(cmd, cwd=engine_path, env=env)
    return result.returncode
```

### Direct Python import

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, engine_path)
from avatar_engine import AvatarJob, get_renderer

with open(job_json_path) as f:
    raw = json.load(f)

job = AvatarJob(raw=raw, job_path=Path(job_json_path))
renderer = get_renderer(job, override="rocketbox")
result = renderer.render(job)
```

---

## 5. Skip-avatar-render behaviour

When SynthPost is run with `--skip-avatar-render`, preserve the expected output path and record a skipped avatar provenance entry:

```json
{
  "avatar": {
    "avatar_renderer": "rocketbox",
    "avatar_asset_id": "synthpost_anchor_v1",
    "avatar_face_mode": "3d_viseme",
    "render_wall_time_seconds": 0,
    "realtime_factor": 0,
    "output_path": "episodes/ep01/stories/story001/anchor/anchor.mp4",
    "skipped": true
  }
}
```

The compositor can then use a placeholder, skip the anchor layer, or reuse a cached clip.

---

## 6. Provenance record

After a successful render, store at least:

```json
{
  "avatar": {
    "avatar_renderer": "rocketbox",
    "avatar_runtime": "custom_threejs_cc4",
    "avatar_asset_id": "synthpost_anchor_v1",
    "avatar_face_mode": "3d_viseme",
    "avatar_engine_commit": "<git rev-parse HEAD in engine repo>",
    "voice_engine": "kokoro",
    "voice_id": "af_bella",
    "voice_speed": 1.0,
    "rhubarb_path": "episodes/ep01/stories/story001/lipsync/rhubarb.json",
    "render_wall_time_seconds": 27.2,
    "realtime_factor": 0.18,
    "output_path": "episodes/ep01/stories/story001/anchor/anchor.mp4",
    "preview_png_path": "episodes/ep01/stories/story001/anchor/anchor_preview.png",
    "manifest_path": "episodes/ep01/stories/story001/anchor/avatar_render_manifest.json"
  }
}
```

Read exact wall time, realtime factor, warnings, and manifest path from `AvatarRenderResult` / the generated render manifest.

---

## 7. Compositor contract

SynthPost should continue to read the anchor MP4 path from its existing direction/provenance field. For the chroma job, the MP4 is H.264/AAC with a green background and can be used by the current chromakey compositor.

No compositor-side change is required if it already accepts an anchor MP4 layer.

---

## 8. Backward compatibility

- `renderer=blender` continues to route to the legacy Blender path.
- Legacy Blender jobs without the 3D fields remain valid.
- `renderer=rocketbox` currently means custom CC4 Three.js runtime, not Rocketbox assets.
- Existing `combined` and `native_segments` export modes are preserved for Blender jobs.
- Generated WAV/MP4/render outputs remain ignored by Git and should be regenerated per deployment/story.

---

## 9. Migration checklist for downstream projects

1. Pull the updated Avatar-Engine commit.
2. Install new Python dependencies from `requirements.txt`.
3. Run `npm --prefix web_avatar_runtime install` if `node_modules` is absent.
4. Provide `assets/avatars/synthpost_anchor_v1/anchor.glb` outside Git or through LFS.
5. Generate TTS WAV + Rhubarb JSON per story.
6. Emit a `renderer: "rocketbox"` 3D job using `anchor.glb` and `avatar.json`.
7. Call `avatar_engine.render_avatar --renderer rocketbox`.
8. Feed `render.output_path` into the existing compositor.
