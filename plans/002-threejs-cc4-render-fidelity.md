# Plan 002: Restore CC skin, eye, hair, cloth, and studio-lighting fidelity in Three.js

> **Executor instructions**: Complete Plan 001 first. Preserve the current
> renderer key `rocketbox`, the PNG-frame capture path, existing backgrounds,
> and all legacy jobs. Do not overwrite Blender assets. Update the Plan 002 row
> in `plans/README.md` when complete.
>
> **Drift check (run first)**:
> `git diff --stat efc7152..HEAD -- avatar-engine/web_avatar_runtime avatar-engine/assets/avatars/synthpost_anchor_v1/avatar.json pipeline/direction/avatar.py tests/test_direction.py`
> If Plan 001 diagnostics are absent or the cited runtime behavior has changed,
> stop and reconcile this plan before implementing.

## Status

- **Priority**: P1
- **Effort**: L (4–7 days)
- **Risk**: MED — shader/material changes can break hair, eyes, or headless capture
- **Depends on**: `plans/001-avatar-quality-baseline.md`
- **Category**: direction / performance
- **Planned at**: top-level commit `efc7152`, Avatar Engine nested commit `8f8200e`, 2026-08-02

## Why this matters

The model looks detailed in Blender because the authoring material uses channels
that never reach the web render. The current runtime then flattens what remains.
This plan keeps the proven rig and rebuilds its web material/lighting treatment
around physically based studio lighting and an explicit CC material profile.

## Current state

- `rocketboxRuntime.ts:527-549` creates an opaque renderer with ACES exposure
  `1.08` and disables shadows.
- `rocketboxRuntime.ts:555-576` floods the character with ambient, hemisphere,
  beauty, key, fill, and rim lights but supplies no environment map.
- `rocketboxRuntime.ts:768-783` forces skin roughness to `0.72`, reduces every
  skin normal to 18%, and adds skin-colored emissive light.
- `rocketboxRuntime.ts:785-788` completely hides eye-occlusion materials.
- `rocketboxRuntime.ts:794-823` repairs hair after load with a CPU canvas pass,
  hides some hair meshes, and switches behavior based on chroma mode.
- The GLB head material contains base-color and normal maps but no roughness,
  AO, SSS/transmission, micro-detail, or wrinkle inputs. The source texture tree
  has those maps under
  `textures/Anchor/Anchor/CC_Base_Body/Std_Skin_Head/`.
- Three.js physical materials work best with an environment map; PMREM and
  `RoomEnvironment` are available in the installed Three.js package.

## Commands you will need

Use the Plan 001 typecheck, lint, Avatar tests, direction tests, runtime build,
and fixed render commands. Also run `make check` only at the final gate because
it builds the Studio and touches normal generated build directories.

## Scope

**In scope**:

- `avatar-engine/web_avatar_runtime/src/rocketboxRuntime.ts`
- `avatar-engine/web_avatar_runtime/src/avatarJob.ts`
- New focused modules under `avatar-engine/web_avatar_runtime/src/rendering/`
  for studio lighting, CC material profiles, texture loading, and quality profiles
- `avatar-engine/assets/avatars/synthpost_anchor_v1/avatar.json`
- `avatar-engine/avatar_engine/talkinghead_renderer.py` for pass-through job data
- `pipeline/direction/avatar.py` and `tests/test_direction.py` for render-profile
  selection only
- Relevant Avatar Engine tests and docs

**Out of scope**:

- Facial timing, expression logic, body-motion scheduling, TTS, or Studio UI
- Renaming/removing the `rocketbox` renderer key
- Replacing the model, re-sculpting it, or overwriting any Blender file
- Adding a network-fetched HDRI at render time
- Removing any existing background or capture mode

## Git workflow

- Suggested branch: `codex/cc4-render-fidelity`
- Suggested logical commits: material contract; studio lighting; semantic
  materials; transparent/chroma compatibility; tests/docs.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Move CC material knowledge into metadata

Extend `avatar.json` with a versioned `web_material_profile`. Map semantic
material names to source textures and scalar defaults. At minimum define skin
head/body/arm/leg, sclera/iris, cornea, eye occlusion, tearline, teeth, tongue,
hair/scalp, sweater, pants, and shoes. Use avatar-relative paths; never hardcode
the workspace path.

For the head profile include the existing roughness, AO, SSS, transmission,
specular, micro-normal-mask/NBMap, and wrinkle inputs. Mark optional maps
explicitly so missing optional wrinkle inputs warn while missing core base,
normal, roughness, or SSS inputs fail the quality job.

Add profile validation in Python and TypeScript. Keep older metadata readable by
falling back to a conservative PBR profile with an explicit warning.

**Verify**: the asset inspector resolves every required profile path and existing
renderer-selection tests still pass.

### Step 2: Replace flood lighting with a calibrated studio rig and IBL

Create a `broadcast_studio_v1` lighting profile:

1. Initialize `RoomEnvironment` through `PMREMGenerator` for deterministic local
   image-based light; do not expose the room as the visible background.
2. Replace ambient/hemisphere flood with a small number of PBR-compatible lights:
   a large soft key (RectAreaLight), a weaker fill, and a restrained rim. Initialize
   `RectAreaLightUniformsLib` for WebGL.
3. Enable self-shadowing only if the fixed-job GPU/headless path is stable. Use a
   shadow-casting key plus bounded map size/bias; do not add an invisible floor
   unless the selected camera shows a contact area.
4. Compare `AgXToneMapping`, `NeutralToneMapping`, and current ACES using the fixed
   frames. Select one profile and pin exposure; do not tune per story.
5. Keep sRGB output and verify all color maps are sRGB while normal, roughness,
   AO, SSS, and masks remain non-color data.

**Verify**: diagnostics show a PMREM environment, no AmbientLight flood, the named
tone-map profile, and the intended shadow state. No skin highlight is clipped in
the fixed neutral/three-quarter frames.

### Step 3: Build semantic CC materials instead of mutating every PBR material

Split `applyAvatarMaterialTweaks()` into named semantic adapters. Preserve the
loaded base/normal maps, then construct calibrated materials:

- **Skin**: remove emissive, restore useful normal strength, apply per-pixel
  roughness/specular/AO, blend micro detail, and implement a bounded screen-space
  or wrapped-diffuse SSS/backscatter approximation driven by the SSS/transmission
  map. Prefer a small, tested `MeshPhysicalMaterial` extension over a wholesale
  renderer rewrite. Ensure SSS cannot glow in unlit regions.
- **Eyes**: keep sclera/iris detail, restore a physically plausible cornea with
  low roughness and appropriate IOR/specular response, retain subtle occlusion
  instead of setting it to zero opacity, and make tearline highlights visible
  without turning the full eye glassy.
- **Teeth/tongue**: use distinct roughness/specular values and AO; prevent pure
  white teeth and black mouth interiors.
- **Hair**: stop hiding a layer solely by prefix unless metadata marks it broken.
  Use alpha-to-coverage/alpha-test or alpha-hash according to the quality profile,
  reuse the existing defringe only when diagnostics prove it is needed, and keep
  depth/render ordering deterministic.
- **Cloth**: load roughness/AO and use physical-material sheen sparingly for the
  sweater; retain cloth normal detail.

Do not identify skin by the generic substring `body` alone. Use the metadata map
and emit a warning for unmapped materials.

**Verify**: the fixed render manifest lists the expected semantic class and maps
for all 24 materials; no critical material is silently handled as generic.

### Step 4: Preserve compositor and background compatibility

Keep `charcoal`, neutral studio, blue studio, and chroma jobs. Add a transparent
quality profile only if the existing PNG sequence can preserve straight alpha
through FFmpeg and Remotion on this machine; otherwise defer it and retain
charcoal as the SynthPost default. Never replace PNG frame capture with viewport
video or MediaRecorder.

For chroma, confirm hair and skin edges survive the existing Remotion key. If the
key remains visibly inferior, document chroma as compatibility-only and use the
opaque studio background for production until a separately tested alpha-video
contract exists.

**Verify**: current quick, preview, and chroma jobs still render; `AnchorVideoLayer`
does not need an API-breaking change.

### Step 5: Score and choose, do not parameter-chase

Render the Plan 001 job with the old and new quality profiles. Fill every material
criterion in the rubric. The new profile must improve skin, eye, and hair scores
by at least one point each without regressing mouth interior, temporal stability,
or render wall/audio ratio by more than 2×. If a criterion misses, change the
material model or maps; do not add per-camera magic constants.

**Verify**: store the two render manifest hashes and completed rubric row in the
baseline doc; generated frames remain ignored.

## Test plan

- Unit-test metadata parsing, relative-path resolution, old-profile fallback,
  missing required/optional maps, material-name mapping, and quality-profile
  selection.
- Add a browser diagnostic assertion that skin has no emissive contribution,
  scene environment is present, required maps are bound, and eye occlusion is not
  fully hidden.
- Render fixed charcoal and chroma jobs and inspect the six rubric frames at 100%.

## Done criteria

- [ ] Typecheck, lint, Avatar tests, direction tests, and runtime build all pass.
- [ ] All declared material profile paths resolve locally.
- [ ] Fixed render diagnostics show environment lighting and semantic materials.
- [ ] Skin uses per-pixel roughness/SSS inputs and no skin-colored emissive term.
- [ ] Cornea/tearline highlights and subtle eye occlusion are visible.
- [ ] Existing quick, preview, and chroma jobs complete through PNG capture.
- [ ] Skin, eye, and hair rubric scores each improve by at least one point with no listed regression.
- [ ] No out-of-scope files or generated media are committed.

## STOP conditions

- The current GLB/material names no longer match the Plan 001 report.
- Required raw texture inputs are absent or their license/packaging status is unknown.
- The proposed skin shader breaks morph-target skinning or headless WebGL capture.
- Transparent output requires replacing PNG capture or changing every compositor template.
- A new model is proposed before the current asset passes through this repaired path.

## Maintenance notes

Every future avatar needs its own semantic material profile; do not grow a pile
of global substring heuristics. Keep physically meaningful parameters in metadata
and keep renderer code generic. Review texture licensing/packaging separately
before deployment because the binary asset tree is intentionally not committed.

