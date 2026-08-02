# Plan 005: Decide whether to keep, upgrade, or replace the avatar and renderer

> **Executor instructions**: This is a decision spike, not authorization to buy
> assets or migrate production. Complete Plans 002–004 first. Use the same audio,
> cameras, frames, compositor, and rubric for every candidate. Update the Plan 005
> row with the decision and evidence.
>
> **Drift check (run first)**:
> `git diff --stat efc7152..HEAD -- plans avatar-engine pipeline/direction/avatar.py compositor/remotion_renderer/src`

## Status

- **Priority**: P2
- **Effort**: M (2–3 days after candidate assets are available)
- **Risk**: LOW for the spike; HIGH for any later migration
- **Depends on**: Plans 002, 003, and 004
- **Category**: direction
- **Planned at**: top-level commit `efc7152`, Avatar Engine nested commit `8f8200e`, 2026-08-02

## Why this matters

The current model should be replaced only if its repaired final output remains
below the bar. This bake-off prevents choosing a beautiful Blender/Unreal viewport
asset that becomes slow, unautomatable, or equally plastic in SynthPost’s actual
render/compositor path.

## Current state and candidates

The incumbent is `synthpost_anchor_v1` with the Plan 002–004 Three.js pipeline.
Evaluate at most these three challengers:

1. **Same current CC asset in a new Blender EEVEE scene** — tests whether renderer
   fidelity, not geometry, is the remaining limitation. This must be a new scene;
   the protected legacy template is not reusable for mutation.
2. **A CC5 HD/Expression-profile character through the repaired Three.js path** —
   tests a higher-quality Reallusion base without changing the whole runtime.
3. **MetaHuman with Unreal audio-driven animation** — a ceiling/reference option,
   not the default. Current Epic documentation allows use in other engines but
   the creation/animation stack and recommended hardware are substantially heavier.

Do not add Ready Player Me, generic marketplace humans, or neural video avatars
unless the user explicitly changes the 3D/local-first requirement.

## Scope

**In scope**:

- `avatar-engine/docs/AVATAR_MODEL_BAKEOFF.md` (create)
- Candidate-specific ignored job/asset locations and checksums
- Minimal disposable adapters required to render the fixed quality job, kept off
  the production default
- Plan 001 rubric/timing updates

**Out of scope**:

- Purchasing assets, licenses, plugins, or cloud credits without approval
- Switching the production default, deleting the incumbent, or rewriting the pipeline
- Changing TTS, script, camera, lighting intent, or compositor between candidates
- Treating vendor demo footage as candidate evidence

## Steps

### Step 1: Lock the acceptance thresholds before rendering challengers

Record incumbent post-Plan-004 scores and measurements. A challenger must provide
a material improvement, not merely a different face. Use these gates:

- mean rubric score at least `4.0/5` and no critical criterion below `3.5`;
- lip-sync, eye/gaze, skin, and body naturalness each at least `4.0`;
- no more than 2× incumbent wall/audio ratio for the same resolution/profile,
  unless the user explicitly accepts slower final-master rendering;
- deterministic local/offline production render after setup;
- compatible canonical WAV and exact narration beat clock;
- documented asset/tool license, automation surface, disk footprint, temporary
  storage, hardware needs, and failure recovery;
- a clear path to the existing Remotion presenter contract.

**Verify**: thresholds are filled before challenger result rows.

### Step 2: Render the same-current-model Blender ceiling

Create a new non-protected EEVEE authoring/render scene using Reallusion’s Blender
Auto Setup or an equivalent reproducible material setup. Feed the same fixed WAV,
visemes/performance cues, camera, crop, FPS, and duration. Measure first-frame
startup, per-frame render, total wall/audio ratio, temporary storage, and output
compatibility.

This candidate answers one question: if Blender is clearly better, is the quality
gain worth adding a Blender CC4 production renderer? It does not prove the model
needs replacement.

**Verify**: output is composited through the same SynthPost template and scored on
the same six frames plus normal-speed playback.

### Step 3: Evaluate a higher-quality CC character only if needed

Use a legally available CC5 HD sample/current license and export it through the
same semantic material contract, quality lighting, facial performance, and motion
tests. Measure morph/skeleton compatibility and note any new corrective shapes.
Do not hand-tune the challenger’s lighting to a different look.

**Verify**: asset inspector and all quality tests pass, or the row records the exact
contract incompatibility rather than an estimated score.

### Step 4: Evaluate MetaHuman only as a platform migration

Use official MetaHuman/Unreal output with the same WAV and comparable framing.
Include full platform cost: Unreal project size, headless/CLI automation, Apple
Silicon hardware behavior, startup/render time, audio-driven facial quality, body
gesture path, output codec/alpha, licensing, and error recovery. Do not compare a
vendor reel to SynthPost output.

**Verify**: candidate can complete a scripted local render on the target Mac or is
marked infeasible with the blocking requirement.

### Step 5: Write the decision

Choose exactly one:

- **Keep current CC + Three.js v2** if it meets thresholds. This is the default
  recommendation because it preserves the small local stack and current pipeline.
- **Keep current CC + add Blender final-master renderer** if Three.js is acceptable
  for preview/production but Blender produces a meaningful, affordable master gain.
- **Upgrade to CC5 HD** if the same pipeline proves the current sculpt/rig—not the
  renderer—is the remaining bottleneck.
- **Migrate to MetaHuman/Unreal** only if its quality lead is decisive and its
  operational cost is explicitly accepted.

Document rejected candidates with evidence and a one-paragraph migration outline
for the winner. Do not implement the migration in this plan.

## Test plan

- Same quality job, six frames, playback segment, resolution, FPS, audio, camera,
  and compositor for every candidate.
- At least two reviewers score blinded A/B labels where practical.
- Repeat each render once to check deterministic timing/output behavior.

## Done criteria

- [ ] Incumbent thresholds were locked before challenger results.
- [ ] Every viable candidate has final-compositor frames, playback score, runtime,
  disk, hardware, automation, and license evidence.
- [ ] Vendor demos and viewport screenshots are not used as final evidence.
- [ ] One explicit keep/upgrade/replace decision is recorded with rejected alternatives.
- [ ] No purchase, production-default switch, or protected-file edit occurred.

## STOP conditions

- Candidate licensing is unclear.
- A paid asset/tool is required without user approval.
- The target Mac cannot run a candidate reproducibly.
- Candidate output cannot use the canonical WAV/beat clock or existing compositor.
- Plans 002–004 have not been scored, making the incumbent comparison invalid.

## Maintenance notes

Re-run this bake-off only when the target format changes (for example, frequent
full-screen anchor shots), a major character/render platform improves, or the
incumbent misses a newly defined quality bar. Avoid continual model shopping once
the selected system meets the broadcast target.

