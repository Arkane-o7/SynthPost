# Plan 004: Replace sine-wave body motion with authored broadcast performance clips

> **Executor instructions**: Complete Plans 001 and 003. This plan needs an
> animation-authoring pass as well as code. Keep animation binaries external or
> under the repository’s existing LFS/ignored-asset policy. Never save over
> `avatar-engine/blender/avatar_template.blend`. Update the Plan 004 row when done.
>
> **Drift check (run first)**:
> `git diff --stat efc7152..HEAD -- pipeline/direction/avatar.py avatar-engine/web_avatar_runtime avatar-engine/assets/avatars/synthpost_anchor_v1/avatar.json`

## Status

- **Priority**: P2
- **Effort**: L (1–2 weeks including animation authoring and review)
- **Risk**: MED/HIGH — retargeting and clip blending can disturb hands, shoulders, head, and facial layers
- **Depends on**: `plans/001-avatar-quality-baseline.md`, `plans/003-facial-performance.md`
- **Category**: direction
- **Planned at**: top-level commit `efc7152`, Avatar Engine nested commit `8f8200e`, 2026-08-02

## Why this matters

The current anchor moves from sums of sine waves and audio-driven arm rotations.
That produces continuous “robotic swimming,” exact repetition, and gestures that
do not match meaning. A news presenter needs stable posture, intentional holds,
brief gestures, and clean returns to neutral. Three.js already supports weighted,
additive, and crossfaded animation clips; use authored performances instead of
adding more procedural oscillators.

## Current state

- `pipeline/direction/avatar.py:28-39` defines a four-item gesture pattern and a
  three-item browser map.
- `pipeline/direction/avatar.py:194-256` cycles that array by beat index; the
  computed `expression` is not sent to the browser.
- `pipeline/direction/avatar.py:490-495` always selects `procedural_anchor`.
- `rocketboxRuntime.ts:1076-1263` synthesizes breath, sway, nod, upper-arm,
  forearm, and hand motion from periodic functions and speech energy.
- The GLB’s two `TempMotion` clips are one frame long, so the production render
  has no usable authored idle or gesture clip.
- Three.js `AnimationMixer`, `AnimationUtils.makeClipAdditive`, and crossfades
  are suitable for an idle base plus short additive gesture clips.

## Commands you will need

Use all Plan 001 commands plus the asset inspector against the separate motion
library. Every render test must use PNG frame capture and canonical WAV timing.

## Scope

**In scope**:

- A new, non-protected authoring scene such as
  `avatar-engine/blender/synthpost_anchor_motion_authoring.blend` if binary policy allows;
  otherwise document its external location/checksum and never commit it
- External/ignored motion GLB(s) under
  `avatar-engine/assets/avatars/synthpost_anchor_v1/animations/`
- `avatar.json` clip catalog, skeleton compatibility, and checksums
- New runtime motion mixer modules and `rocketboxRuntime.ts` integration
- Browser job contract and `pipeline/direction/avatar.py` cue planner
- Direction/Avatar tests and runtime docs

**Out of scope**:

- Editing the protected legacy Blender template
- Buying a motion pack without explicit user approval
- Walking/dancing/cinematic gestures; this is a restrained presenter library
- A new editorial LLM stage or UI editor for performance cues
- Replacing facial visemes/expressions from Plan 003

## Git workflow

- Suggested branch: `codex/authored-anchor-motion`
- Commit asset metadata separately from runtime/scheduler code.
- Do not commit large licensed binaries outside the established asset policy.

## Steps

### Step 1: Author a minimal broadcast motion vocabulary

Create and review these clips on the exact current skeleton:

- `idle_attentive_a` and `idle_attentive_b`: 6–10 second seamless bases with
  breathing, weight settle, very small head/shoulder variation, and quiet hands;
- `explain_open_left`, `explain_open_right`, `explain_two_hands`: restrained
  explanatory gestures with clean anticipation, stroke, hold, and recovery;
- `emphasis_small`: one compact emphasis near the torso;
- `compare_two_points`: controlled left/right contrast;
- `nod_once` and `conclusion_settle`;
- optional `list_count_one/two/three` only if fingers survive the final crop.

Record clip duration, loopability, intended camera crops, affected bones, and
whether the clip is base or additive. Strip facial morph and jaw/eye tracks so
Plan 003 owns the face. Strip root translation and keep the presenter planted.

Prefer a short custom mocap or hand-keyed session over generic “talking” motion.
ActorCore/Reallusion clips may be evaluated, but license and retarget quality must
be documented before use.

**Verify**: asset inspector reports real multi-frame durations, expected track
names, the same CC skeleton namespace, no facial morph tracks, and no root drift.

### Step 2: Load the motion library separately from the character

Do not bloat/re-export the 77 MB character for every clip iteration. Load a
metadata-declared motion GLB and bind its named tracks to the existing skeleton.
Validate required bone names and reject incompatible clips clearly.

Build a base idle action and additive one-shots. Use `AnimationUtils.makeClipAdditive`
where the authored asset is not already additive. Use weights/crossfades and
never start a new full-body clip by resetting the entire mixer.

**Verify**: each catalog clip can be selected by name in a diagnostic job; missing
or incompatible clips fail before frame capture and list the exact missing bones.

### Step 3: Implement a constrained performance scheduler

Replace index cycling with a deterministic scheduler driven by exact narration
beats and Plan 003 performance intent. Rules must include:

- gesture cooldown and no immediate repetition;
- a maximum gesture density (roughly one meaningful gesture every 5–10 seconds,
  adjusted after review), with quiet holds between gestures;
- anticipation before the stressed phrase and recovery after it;
- intensity caps per crop (`front_close` quieter than `landscape_intro`);
- left/right alternation that considers the prior pose;
- no gesture when the anchor is not visible in the approved timeline;
- conclusion settles instead of ending mid-gesture.

Use existing exact beat timing. Keep the planner deterministic for a manifest/
seed and include its cue list in diagnostics.

**Verify**: tests cover a 10-second short item, a 60-second explainer, repeated
similar beats, questions/contrasts/lists, long silence, hidden-anchor spans, and
the final beat.

### Step 4: Retain only bounded procedural micro-motion

Remove procedural upper-arm/forearm/hand speech oscillation. Keep only very small
seeded breathing, gaze/head stabilization, and noise-shaped micro-settle if the
authored idle does not already supply them. Avoid pure sinusoids and ensure the
same seed is frame-deterministic.

Facial jaw/eye bones remain under Plan 003 ownership. Define a bone ownership
table and assert at load time that full-body clips do not animate protected face
bones.

**Verify**: diagnostics show no speech-energy-driven hand rotation and no periodic
body channel with an exact short loop unless it is an authored idle clip.

### Step 5: Review composition, not just the character viewport

Render the quality job and one 45–60 second real SynthPost story through Remotion.
Review front-close and full-screen shots at normal playback speed. Body naturalness
must improve at least one rubric point; facial/lip scores must not regress; hands
must stay inside intended crops; and wall/audio ratio must remain within 20% of
the post-Plan-003 baseline.

**Verify**: baseline doc records manifest hashes and completed scores for both
clips, with no visible pose pop at gesture start/end or story end.

## Test plan

- Unit-test clip catalog parsing, skeleton validation, protected-track rejection,
  deterministic cue selection, cooldowns, density, crop intensity, and final settle.
- Diagnostic-render every clip once, then run one long composited story.
- Check temporal playback for foot/root drift, shoulder pops, hand intersections,
  clothing clipping, and facial-layer conflicts.

## Done criteria

- [ ] At least two authored idles and six restrained one-shot gestures pass review.
- [ ] Motion clips are multi-frame, skeleton-compatible, face-track-free, and root-stable.
- [ ] Runtime uses weighted/crossfaded clips and no procedural speech-hand oscillation.
- [ ] Scheduler is deterministic and obeys repetition/density/crop constraints.
- [ ] Short, long, hidden-anchor, and conclusion scenarios have passing tests.
- [ ] Body naturalness improves at least one point without facial regression.
- [ ] Protected Blender file and unrelated assets are untouched.

## STOP conditions

- Available clips require a different skeleton with unreliable automatic retargeting.
- A licensed asset cannot be stored/used under SynthPost’s distribution model.
- Facial/jaw/eye tracks cannot be cleanly stripped from body clips.
- Hands or shoulders remain visibly broken after two focused authoring passes.
- The implementation would save over the protected Blender template.

## Maintenance notes

The motion catalog is a product asset. Keep its clip contract, checksums, license,
camera suitability, and protected-bone list in metadata. Favor a small excellent
library over dozens of generic motions.

