# Plan 003: Replace mechanical lip sync and facial idling with a layered performance system

> **Executor instructions**: Complete Plan 001 first and integrate against the
> selected Plan 002 material profile. Preserve Rhubarb input compatibility while
> improving how cues are blended and how the remaining expression rig is used.
> Update the Plan 003 row in `plans/README.md` when complete.
>
> **Drift check (run first)**:
> `git diff --stat efc7152..HEAD -- avatar-engine/web_avatar_runtime/src avatar-engine/avatar_engine pipeline/direction/avatar.py tests/test_direction.py`

## Status

- **Priority**: P1
- **Effort**: L (5–8 days)
- **Risk**: MED — excessive morph combinations can deform teeth, tongue, and lips
- **Depends on**: `plans/001-avatar-quality-baseline.md`; integrate after Plan 002
- **Category**: direction
- **Planned at**: top-level commit `efc7152`, Avatar Engine nested commit `8f8200e`, 2026-08-02

## Why this matters

The face currently behaves like a viseme player with a periodic blink. Human
viewers are especially sensitive to fixed blink cadence, frozen gaze, symmetric
expressions, one-cue-at-a-time lip shapes, and motion that starts/stops at exact
audio boundaries. The asset already exposes many expression shapes; the runtime
needs layered, deterministic performance logic that uses them safely.

## Current state

- `rocketboxRuntime.ts:17-20` fixes every blink to a 4.2-second period with the
  same 150 ms duration and 900 ms phase.
- `rocketboxRuntime.ts:146-155` applies the same symmetric “soft neutral” face on
  every frame.
- `rocketboxRuntime.ts:447-464` scans for one active viseme and uses a 45 ms
  triangular envelope; adjacent cues never overlap or coarticulate.
- `rocketboxRuntime.ts:1604-1645` resets controlled morphs, applies neutral,
  applies one viseme, then applies the periodic blink.
- `avatar.json:11-35` confirms ARKit-like expression support, but the production
  job never carries expression events.
- Reallusion ExpressionPlus and Apple ARKit support 50+ detailed face controls;
  the current model’s main body mesh had 152 weights at planning time.

## Commands you will need

Use all Plan 001 verification commands. Add a focused deterministic browser/unit
test command if Plan 001 establishes one; do not introduce live camera, network,
or paid-service tests.

## Scope

**In scope**:

- New modules under `avatar-engine/web_avatar_runtime/src/performance/` for
  viseme blending, expression layers, gaze, blink, seeded timing, and constraints
- `rocketboxRuntime.ts` integration
- `avatarJob.ts` performance contract
- `avatar.json` expression mapping/constraints
- `talkinghead_renderer.py` pass-through and diagnostics
- `pipeline/direction/avatar.py`, `tests/test_direction.py`, and Avatar tests
- Avatar runtime design/integration docs

**Out of scope**:

- Changing TTS or canonical narration timing
- Requiring iClone, cloud lip sync, or an iPhone during production render
- Body gesture assets/scheduling (Plan 004)
- Modifying base mesh/morph shapes in Blender or Character Creator
- Eliminating Rhubarb compatibility before a replacement wins an A/B test

## Git workflow

- Suggested branch: `codex/facial-performance-v2`
- Keep viseme, eye/blink, expression, and pipeline-contract changes as separate
  logical commits so regressions can be bisected.

## Steps

### Step 1: Define a layered facial-performance contract

Extend the browser job with a versioned `facial_performance` object containing:

- deterministic `seed`;
- timed `expression_events` with preset, start/end, attack/release, and strength;
- optional low-rate `speech_envelope` samples derived from the canonical WAV;
- gaze target/profile and blink profile;
- viseme coarticulation profile;
- a constraints profile ID from avatar metadata.

Keep all fields optional so old jobs retain conservative behavior. Extend
`avatar.json` with expression presets and safe maximums for brow, cheek, squint,
smile/press, nose, jaw, and gaze controls. Add pairwise exclusions/caps for known
sensitive combinations. Metadata owns CC morph names; generic runtime code owns
layer composition.

**Verify**: old fixtures parse unchanged; a new fixture round-trips every field;
unknown preset/profile IDs fail clearly before rendering.

### Step 2: Replace one-cue visemes with coarticulated blending

Pre-index cues so frame evaluation is linear over the moving cursor, not a full
scan. Blend previous/current/next cue envelopes with phoneme-specific attack and
release windows. Separate jaw openness from lip shape, then combine once; avoid
applying the same jaw signal through both morph and bone paths. Preserve lip
closure for bilabials and allow rounded vowels to anticipate slightly.

Use the fixed quality audio and add a diagnostic CSV/JSON trace sampled at 24 or
48 Hz showing cue weights, jaw, and major lip morphs. Assert total competing lip
shape weight and jaw/teeth offsets stay within metadata caps.

**Verify**: tests cover silence, back-to-back cues, overlaps, zero/short duration,
bilabial closure, dental contact, wide-to-rounded transitions, and final release.

### Step 3: Add natural, seeded eyes and blinks

Implement a time-based state machine whose output depends only on render time
and seed, so frame capture is reproducible:

- non-periodic blink intervals within a bounded distribution, occasional double
  blinks, and slightly asymmetric eyelid timing;
- micro-saccades around the lens rather than random wandering;
- small eye/head coupling and return-to-lens behavior;
- gaze holds through important phrases and reduced saccades during blinks;
- optional punctuation/beat-boundary blink opportunities without blinking at
  every boundary.

Drive `CC_Base_R_Eye` and `CC_Base_L_Eye` or mapped eye-look morphs within safe
angles. Never let both pupils drift independently or cross.

**Verify**: a 60-second simulation with a fixed seed has no repeated exact period,
no out-of-range gaze, no blink longer than the configured cap, and identical
results on repeated runs.

### Step 4: Layer restrained broadcast expressions

Create a small vocabulary, not an emoji system: `neutral_attentive`, `warm_open`,
`focused`, `concerned`, `skeptical`, and `conclusion_confident`. Each preset uses
low-amplitude brow/cheek/squint/mouth controls, attack/hold/release, small left/
right asymmetry, and metadata caps. Mouth expression must yield to speech closure
and vowel shapes rather than fighting them.

Generate events from approved narration beats and section context in
`pipeline/direction/avatar.py`. At minimum use section type, punctuation, and
explicit beat timing; do not cycle expressions by array index. Include text in
the planner input but do not put raw script text into browser diagnostics.

**Verify**: direction tests prove stable cue generation for intro, question,
contrast/concern, factual explanation, and conclusion beats; same manifest yields
the same cues.

### Step 5: Derive a low-rate speech envelope

During existing WAV preparation, calculate deterministic RMS values at a low
fixed rate (for example 20 Hz), normalize with robust percentiles, and store the
small array in the browser job. Use it only for subtle cheek/jaw emphasis and
head micro-performance; canonical audio remains the timing source. Silence must
decay smoothly and must not freeze the face in an open viseme.

**Verify**: unit tests cover silent audio, very short audio, clipped peaks, and
normal speech. Envelope duration agrees with WAV duration within one sample bin.

### Step 6: Score the whole face at normal playback

Render the Plan 001 fixed job with facial v1 and v2 while holding Plan 002
materials constant. Review real-time playback first, then fixed frames. Facial
liveliness and lip-sync scores must each improve by at least one point; eye/gaze,
mouth interior, and temporal stability must not regress.

**Verify**: baseline doc records both manifest hashes, completed scores, and any
remaining sensitive phonemes/expressions.

## Test plan

- Pure tests for deterministic PRNG/timing, blink state machine, gaze bounds,
  expression envelopes, constraint composition, and viseme overlap.
- Python tests for speech-envelope extraction and beat-to-expression planning.
- One fixed end-to-end render that covers the representative viseme/expression
  cases without any network/provider call.

## Done criteria

- [ ] Typecheck, lint, Avatar tests, direction tests, and runtime build pass.
- [ ] Identical seed/job inputs produce identical facial traces.
- [ ] No blink uses the old fixed 4200 ms cadence.
- [ ] Adjacent visemes overlap smoothly and obey jaw/lip caps.
- [ ] Eye gaze stays near lens and never crosses/diverges beyond configured bounds.
- [ ] At least five restrained expression presets are used by tested beat contexts.
- [ ] Facial liveliness and lip-sync rubric scores improve by at least one point.
- [ ] Existing old jobs still render with documented fallback behavior.

## STOP conditions

- Required eye bones or mapped expression morphs are missing from the live asset.
- Morph combinations visibly detach lips, expose teeth/tongue at rest, or distort eyelids.
- A solution requires changing narration audio/timing or calling an external service.
- Expression planning would require rewriting approved editorial text.

## Maintenance notes

Treat facial layers as a constrained mixer: visemes, expression, blink, and gaze
must have explicit ownership and priorities. Do not return to a single global
“reset all morphs then set some values” list as profiles expand.

