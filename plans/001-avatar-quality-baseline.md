# Plan 001: Establish a reproducible avatar-quality baseline and asset contract

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving on. If a
> STOP condition occurs, stop and report it; do not improvise. When complete,
> update Plan 001 in `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat efc7152..HEAD -- avatar-engine pipeline/direction/avatar.py tests/test_direction.py`
> Also run `git status --short` and `git -C avatar-engine status --short`.
> This repository currently contains user-owned uncommitted work in the nested
> Avatar Engine checkout. Preserve it. If any in-scope excerpt below has changed,
> compare it to the live code and stop if the behavior no longer matches.

## Status

- **Priority**: P1
- **Effort**: M (1–2 days)
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests / direction
- **Planned at**: top-level commit `efc7152`, Avatar Engine nested commit `8f8200e`, 2026-08-02

## Why this matters

“Looks realistic” is currently judged from whichever preview happened to be
rendered last. That makes renderer changes impossible to compare and encourages
random parameter tuning. Establish one deterministic six-shot test, an asset
capability report, performance measurements, and a scored review sheet before
changing the renderer.

## Current state

- `avatar-engine/assets/output/synthpost_anchor_v1_quick_test.png` and
  `synthpost_anchor_v1_camera_23_test.png` are useful evidence but are generated
  artifacts with no formal acceptance rubric.
- `avatar-engine/assets/avatars/synthpost_anchor_v1/avatar.json:8-35` says the
  asset supports 3D lips, visemes, ARKit-like expressions, blink shapes, and a
  small sample of expression shapes.
- Inspection of the local `anchor.glb` at planning time found 11 meshes, one
  skin, 24 materials, 39 embedded images, 152 weights on `CC_Base_Body.001`, and
  only two one-frame (`0.0167s`) `TempMotion` animation clips. Treat those values
  as observed data, not permanent constants.
- The adjacent texture tree contains 119 source images including head SSS,
  transmission, micro-normal mask, specular mask, AO, roughness, and wrinkle
  maps, but the GLB head material embeds only diffuse and normal textures.
- The existing verification baseline is green:
  `npm --prefix avatar-engine/web_avatar_runtime run typecheck`,
  `npm --prefix avatar-engine/web_avatar_runtime run lint`, and
  `.venv/bin/python -m unittest tests.test_direction` all pass.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Browser typecheck | `npm --prefix avatar-engine/web_avatar_runtime run typecheck` | exit 0, no TypeScript errors |
| Browser lint | `npm --prefix avatar-engine/web_avatar_runtime run lint` | exit 0, no lint errors |
| Avatar tests | `PYTHONPATH=avatar-engine .venv/bin/python -m unittest discover -s avatar-engine/tests` | all tests pass |
| Direction tests | `.venv/bin/python -m unittest tests.test_direction` | all tests pass |
| Build runtime | `npm --prefix avatar-engine/web_avatar_runtime run build` | exit 0 and `dist/` produced |
| Render fixed job | `cd avatar-engine && .venv/bin/python3 -c 'import runpy,sys; sys.argv=["render_avatar","--job","jobs/synthpost_anchor_v1_quality_gate.json","--renderer","rocketbox"]; runpy.run_module("avatar_engine.render_avatar",run_name="__main__")'` | pass result and fixed preview/output artifacts |

## Scope

**In scope**:

- `avatar-engine/scripts/inspect_avatar_asset.py` (create)
- `avatar-engine/tests/test_inspect_avatar_asset.py` (create)
- `avatar-engine/jobs/synthpost_anchor_v1_quality_gate.json` (create)
- `avatar-engine/docs/AVATAR_QUALITY_BASELINE.md` (create)
- `avatar-engine/avatar_engine/talkinghead_renderer.py` only for adding stable
  diagnostic fields to the existing render manifest

**Out of scope**:

- Renderer visual changes, material tuning, expression tuning, or gesture tuning
- Any modification or save to `avatar-engine/blender/avatar_template.blend`
- Checking in `anchor.glb`, raw textures, generated PNGs, videos, or frame dumps
- Adding a paid/cloud dependency or changing the production renderer default

## Git workflow

- Suggested branch: `codex/avatar-quality-baseline`
- Match the repository’s imperative commit style, for example:
  `Establish deterministic avatar quality baseline`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add a standard-library GLB/asset inspector

Create `inspect_avatar_asset.py` using only Python’s standard library. It must:

1. Parse GLB v2 JSON/BIN chunks without extracting or rewriting the source.
2. Report asset generator/version; node, mesh, skin, material, image, morph target,
   bone, and animation counts; material texture slots; animation names/durations;
   morph names; and required/used glTF extensions.
3. Read `avatar.json`, resolve every metadata path relative to the avatar folder,
   and report missing files without printing sensitive or absolute user paths.
4. Compare known CC material requirements with the source texture tree and flag
   when a head material lacks roughness, AO, SSS/transmission, or micro-detail.
5. Support `--json` for machine-readable output and exit non-zero only for a
   malformed GLB or a declared required asset that is missing.

Add unit tests using a tiny synthetic GLB fixture constructed in memory. Do not
copy the 77 MB production GLB into tests.

**Verify**:
`PYTHONPATH=avatar-engine .venv/bin/python -m unittest avatar-engine.tests.test_inspect_avatar_asset`
→ all new tests pass.

### Step 2: Define one fixed quality-gate job

Create `synthpost_anchor_v1_quality_gate.json` from the existing preview job, but
use a stable 8–12 second audio/viseme pair and `charcoal` background. Fix camera,
resolution, FPS, transform, seed, and duration. Add explicit cue windows that
exercise:

- neutral rest and direct gaze;
- bilabial, dental, wide, and rounded mouth shapes;
- one blink and one double-blink opportunity;
- one small emphasis gesture;
- one three-quarter camera frame if the job contract supports cuts; otherwise
  create a paired still-only diagnostic job documented next to it.

Do not use generated TTS in the comparison job; pin the existing WAV and Rhubarb
JSON so renderer changes see identical inputs.

**Verify**: render twice and confirm the two runs have equal duration, resolution,
FPS, frame count, camera, asset ID, and cue counts in their render manifests.

### Step 3: Record renderer diagnostics with every quality render

Extend the existing sidecar manifest, keeping all current keys compatible. Add
one nested `diagnostics` object containing:

- Three.js revision, browser/renderer path, tone mapping, exposure, output color
  space, shadow setting, and environment-lighting profile;
- asset report summary and SHA-256 of GLB and metadata (never embed raw assets);
- resolved material classes and map names by semantic group;
- bone/morph counts, selected viseme profile, missing morphs, and animation clip
  names/durations;
- deterministic seed and capture mode.

Pass the browser diagnostics back through `window` alongside the current warnings;
do not scrape console text.

**Verify**: the fixed render’s `avatar_render_manifest.json` contains the new
object and remains readable by existing provenance code/tests.

### Step 4: Write the visual scoring rubric

Create `AVATAR_QUALITY_BASELINE.md` with a table for six fixed frames and these
1–5 criteria: skin depth/roughness, eye wetness/gaze, hair silhouette, mouth
interior/lip contact, lip-sync timing, facial liveliness, body naturalness,
compositor fit, and temporal stability. Define concrete anchors: `1` is broken
or distracting, `3` is usable but visibly synthetic, and `5` is broadcast-ready
at normal playback speed. Include columns for current score, candidate score,
reviewer, date, render manifest hash, and notes.

Record baseline wall time, audio duration, wall/audio ratio, output size, and peak
temporary disk estimate. Never commit generated frames; document their ignored
output directory and naming convention.

**Verify**: a reviewer can locate every referenced output from the manifest alone,
and the baseline table has no blank definition or undocumented metric.

## Test plan

- Unit-test valid GLB parsing, malformed header/chunk handling, no-animation
  assets, multiple morph meshes, and missing metadata-declared assets.
- Extend `avatar-engine/tests/test_talkinghead_manifest.py` only if its existing
  assertions cover render-sidecar compatibility; otherwise keep new tests local
  to the inspector.
- Re-run the fixed job twice and compare diagnostic scalar fields. Pixel hashes
  may differ across GPU/driver versions and must not be the cross-machine gate.

## Done criteria

- [ ] All four verification commands in “Commands you will need” pass.
- [ ] The inspector emits valid JSON for `synthpost_anchor_v1` without modifying it.
- [ ] The fixed quality job renders twice with identical contract/timing metadata.
- [ ] The render sidecar records material, rig, animation, renderer, and seed diagnostics.
- [ ] The rubric contains six named frames and all nine defined scoring criteria.
- [ ] `git status --short` shows no generated media and no modifications outside scope (except the index status row).

## STOP conditions

- The production GLB or pinned WAV/viseme pair is missing.
- The live asset no longer has the CC skeleton or Reallusion morph profile.
- Completing diagnostics would require changing the PNG-frame capture contract.
- Any step would overwrite or resave a Blender file.

## Maintenance notes

Run the inspector and fixed job whenever Three.js, the GLB, material metadata,
browser capture, or morph mappings change. Treat the baseline as a product gate,
not a golden-pixel test across different GPUs.

