# Current 3D Runtime Design

> Historical note: this file kept its original `talkinghead_runtime_design.md` name because downstream docs already link to it. The active SynthPost anchor renderer is now a custom Three.js/Reallusion CC4 runtime kept under the legacy `rocketbox` renderer key for compatibility.

## Renderer summary

The current fast 3D path is:

```text
Kokoro WAV → Rhubarb JSON → avatar_engine.render_avatar
→ browser Three.js runtime → PNG frame capture → FFmpeg MP4 mux
```

It does **not** use paid iClone/ActorCore animation packs, cloud APIs, or a Blender render for the current 3D anchor preview/chroma outputs.

The active avatar asset is expected at:

```text
assets/avatars/synthpost_anchor_v1/anchor.glb
assets/avatars/synthpost_anchor_v1/avatar.json
```

The GLB is a Reallusion Character Creator / CC4 export. The binary GLB and raw texture dumps are intentionally ignored by Git; store them externally or with Git LFS if a downstream deployment needs the exact asset.

## Why the renderer is still named `rocketbox`

Several Python and job entry points still use:

```json
"renderer": "rocketbox"
```

and:

```bash
--renderer rocketbox
```

This is a compatibility label only. The runtime file is `web_avatar_runtime/src/rocketboxRuntime.ts`, but the implementation now handles CC4/Reallusion GLBs, not Rocketbox characters.

Do not switch a SynthPost CC4 job back to TalkingHead or Rocketbox asset assumptions unless deliberately redesigning the renderer.

## Browser runtime responsibilities

`web_avatar_runtime/src/rocketboxRuntime.ts` handles:

- GLTF loading for local GLB/VRM-like assets.
- Reallusion/CC4 morph mapping from Oculus-style visemes.
- Material cleanup for skin, eyes, eye occlusion, tearline, and hair.
- Procedural blink and soft neutral face expression.
- Rhubarb cue conversion performed by Python into precomputed browser viseme arrays.
- CC4 jaw, lower teeth, upper teeth, and tongue bone motion.
- Procedural head, body, shoulder, forearm, hand, and speaking gesture motion.
- Camera presets plus per-job `camera_overrides`.
- Deterministic PNG frame capture for final renders.

Important CC4 bones used by the procedural layer include:

```text
CC_Base_UpperJaw
CC_Base_JawRoot
CC_Base_Teeth01
CC_Base_Teeth02
CC_Base_Tongue01
CC_Base_R_Clavicle
CC_Base_L_Clavicle
CC_Base_R_Upperarm
CC_Base_L_Upperarm
CC_Base_R_Forearm
CC_Base_L_Forearm
CC_Base_R_Hand
CC_Base_L_Hand
CC_Base_Spine01
CC_Base_Spine02
CC_Base_Waist
```

Important Reallusion morphs include:

```text
V_Open
V_Explosive
V_Dental_Lip
V_Tight_O
V_Tight
V_Wide
V_Affricate
V_Lip_Open
Eye_Blink_L
Eye_Blink_R
Jaw_Open
Mouth_Drop_Lower
Mouth_Drop_Upper
```

## Capture method

The production capture path is:

```text
browser canvas.toDataURL PNG frames
→ Python page.expose_function("__pushCanvasFrame", ...)
→ PNG sequence
→ FFmpeg mux with original WAV
```

This path was chosen because Playwright viewport video and browser `MediaRecorder` were unreliable for final WebGL capture in headless mode.

Do not replace the PNG-frame capture path unless the replacement is tested against WebGL avatar output and muxed audio.

## Job contract

Current SynthPost CC4 jobs are:

```text
jobs/synthpost_anchor_v1_quick_test.json
jobs/synthpost_anchor_v1_preview.json
jobs/synthpost_anchor_v1_chroma.json
```

They require:

- `renderer: "rocketbox"`
- `audio_path` pointing to a local WAV
- `viseme_path` pointing to matching Rhubarb JSON
- `avatar.asset_path` pointing to `assets/avatars/synthpost_anchor_v1/anchor.glb`
- `avatar.metadata_path` pointing to `assets/avatars/synthpost_anchor_v1/avatar.json`
- `face.mode: "3d_viseme"`
- `face.blendshape_profile: "reallusion_viseme"`

The current selected voice assets are generated from:

```text
jobs/synthpost_anchor_v1_tts_af_bella.json
assets/output/tts/synthpost_anchor_v1_af_bella_s100.wav
assets/output/tts/synthpost_anchor_v1_af_bella_s100_rhubarb.json
```

`assets/output/` is ignored, so downstream projects must regenerate these files or provide their own WAV/Rhubarb pair.

## Current camera and pose defaults

The active SynthPost jobs use:

```json
"camera_overrides": {
  "distance_multiplier": 3.5,
  "target_height_factor": 0.84,
  "height_factor": 0.86
},
"avatar_transform": {
  "rotation_y_degrees": -3
}
```

This framing exposes more upper torso/arms than the early close-up tests. Pose and gesture tuning was done around this crop.

## Known sensitivities

- Upper teeth motion must remain tiny; too much movement creates rabbit teeth, while too much tuck hides teeth behind the tongue.
- Heavy jaw rotations caused asymmetric/tilted mouth motion, so jaw/teeth use small world-space translations.
- Tongue motion is now viseme-driven but intentionally subtle.
- Shoulder lowering required actual clavicle world translation, not just rotation.
- Strong upper-arm motion quickly reads as zombie/T-pose; most speech gesture should stay in forearms/hands with smoothed speech energy.
- The current renderer depends on a CC4/Reallusion skeleton naming convention; other GLBs may need metadata or runtime mapping updates.

## Validation commands

From the repository root:

```bash
npm --prefix web_avatar_runtime run build

.venv/bin/python3 -c 'import runpy, sys; sys.argv=["render_avatar","--job","jobs/synthpost_anchor_v1_quick_test.json","--renderer","rocketbox"]; runpy.run_module("avatar_engine.render_avatar", run_name="__main__")'
```

From the workspace parent (`/Users/.../3D Model`), prefix paths with `desk-avatar-engine/`.

## Deferred work

- Rename `rocketbox` to a clearer renderer key such as `cc4_threejs` with backward-compatible aliases.
- Move pose/teeth/tongue/gesture constants into avatar metadata or job config.
- Add optional reusable browser/session caching for batches.
- Add eye gaze and brow micro-expression tuning.
- Add an asset packaging story for downstream projects that cannot rely on local ignored GLBs.
