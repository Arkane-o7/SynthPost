# SynthPost Current-Model Renderer Bake-off

Decision date: 2026-08-02.

## Decision

Keep the current Character Creator model. Use **Three.js for previews and
Blender EEVEE for final production anchor renders** while the shared facial/body
performance layer is developed.

The current model is not the primary limitation: the same GLB becomes visibly
more dimensional in the clean EEVEE scene. Repaired Three.js remains valuable
because it renders faster than real time, but it does not yet meet the fixed
quality gate or reach 85–90% of Blender in the critical skin/eye/hair/mouth
subset. No new model should be investigated from this evidence.

## Live-repository drift found

The audit did not assume the earlier plan was implemented. User-owned changes
already present in the nested working tree included Metal/ANGLE browser flags,
a longer browser timeout, disk-space checks, a front-camera adjustment, tongue
rest inset, and build locking. These were preserved. The protected
`blender/avatar_template.blend` and its backup were already modified before this
task and were neither opened by the experiment nor written by its code.

## Candidates

### A — untouched Three.js control

- `rocketbox` key and original visual code path.
- ACES 1.08; legacy flood rig; no environment; no shadows.
- Original global material mutations and procedural performance.
- Two repeated renders are decoded-frame identical.

### B — minimally repaired Three.js

- Opt-in `studio_v2`; old jobs fall back to `legacy_control`.
- Local `RoomEnvironment`/PMREM, three restrained area lights and one bounded
  directional shadow source; no network HDRI.
- ACES selected at one pinned exposure after fixed ACES/AgX/Neutral comparisons.
- Exact metadata-driven semantic classes for all 24 materials and 47 local map
  assignments; sRGB GLB colour maps remain untouched and external data maps use
  non-colour sampling.
- Skin emissive removed, normal strength restored, local roughness/AO/specular/
  SSS/transmission inputs loaded, and a bounded non-emissive physical-material
  approximation used.
- Eye occlusion, cornea, tearline, hair, teeth, tongue and cloth get distinct
  treatment. Alpha hash and alpha cutout were both rejected from captured
  evidence; blended hair was retained because it avoided stipple/halo in PNGs.
- Two repeated final renders are decoded-frame identical.

### C — current model in Blender 5.1 EEVEE

- Experimental `blender_cc` key; modern-job adapter; same WAV/visemes/FPS/frame
  count and approximate camera contract.
- Starts from factory-empty state, imports the current GLB, excludes the same
  stray `Icosphere`, creates a new studio scene and saves it only beneath ignored
  output. It never reads or writes the protected legacy template.
- Uses all 24 semantic material declarations and loads 47 local texture inputs.
- Headless EEVEE renders 192 PNGs, then FFmpeg muxes the canonical WAV.
- New scene: `assets/output/avatar_bakeoff/candidate_c_blender_eevee_final_v3/run_1/synthpost_anchor_v2.blend`.

## Measurements

The requested wall/audio ratio is wall time divided by the fixed 8.0-second
camera duration. Browser temporary space is deleted after manifest measurement;
Blender PNG frames are intentionally retained for review.

| Candidate | Wall time | Wall/audio | MP4 bytes | PNG/temp bytes | Notes |
|---|---:|---:|---:|---:|---|
| A run 1 | 5.818 s | 0.727× | 301,462 | 53,483,311 | cold control |
| A run 2 | 4.340 s | 0.543× | 301,462 | 53,478,025 | warm control |
| B run 1 | 5.848 s | 0.731× | 292,552 | 53,565,723 | final ACES profile |
| B run 2 | 5.433 s | 0.679× | 292,552 | 53,516,171 | deterministic repeat |
| C run 1 | 81.155 s | 10.144× | 343,248 | 201,634,921 | 79.6 s EEVEE render |

Candidate C is about 14× slower than final Candidate B for this short 720p
segment. That is operationally acceptable for final-only anchor segments on the
tested Mac: an 8-second final takes about 81 seconds, while editorial iteration
stays on Three.js.

## Completed scoring

One reviewer (Codex) scored the locked frames and normal-speed outputs. These
scores are evidence-backed but not blinded; a human creative review remains
recommended before setting a production default.

| Criterion | A control | B repaired Three.js | C Blender EEVEE |
|---|---:|---:|---:|
| Skin depth and roughness | 2.1 | 2.8 | 4.0 |
| Eye wetness/socket definition | 2.2 | 2.9 | 3.8 |
| Gaze | 3.0 | 3.0 | 3.0 |
| Hair | 2.6 | 2.8 | 3.8 |
| Mouth interior | 2.6 | 2.8 | 3.4 |
| Lip contact | 2.5 | 2.5 | 2.5 |
| Lip-sync timing | 3.0 | 3.0 | 3.0 |
| Facial liveliness | 2.2 | 2.2 | 2.2 |
| Body naturalness | 2.1 | 2.1 | 2.6 |
| Temporal stability | 4.5 | 4.3 | 4.5 |
| Compositor fit | 4.0 | 4.0 | 4.0 |
| **Mean** | **2.8** | **3.0** | **3.3** |

Candidate B fails the explicit Three.js-only decision gate: mean is below 4.0,
skin/eyes/mouth/body are below 3.8, and the critical material subset averages
about 75% of Candidate C rather than 85–90%. Candidate C also remains below 4.0
overall because all candidates share the weak legacy performance layer; that is
an animation problem, not evidence for replacing the model.

## Output paths

- A run 1: `assets/output/avatar_bakeoff/candidate_a_control/run_1/video.mp4`
- A run 2: `assets/output/avatar_bakeoff/candidate_a_control/run_2/video.mp4`
- B run 1: `assets/output/avatar_bakeoff/candidate_b_threejs_final/run_1/video.mp4`
- B run 2: `assets/output/avatar_bakeoff/candidate_b_threejs_final/run_2/video.mp4`
- C final: `assets/output/avatar_bakeoff/candidate_c_blender_eevee_final_v3/run_1/video.mp4`
- Final A/B/C still: `assets/output/avatar_bakeoff/final_abc_comparison_v3.png`
- Each candidate directory also contains its preview, manifest, stats and review
  frames. Candidate C additionally retains the PNG sequence, Blender logs,
  diagnostics and experiment scene.

These media paths are ignored by Git. The candidates use the same presenter
video contract expected by SynthPost/Remotion, but a full story-template render
was not generated because changing editorial/template logic was explicitly out
of scope. Compositor-fit was therefore evaluated against the existing anchor
layer contract and matched neutral background/crop, not a new editorial export.

## Shared performance architecture

The next renderer-independent input is `performance_v2`, defined by
`avatar_engine/schemas/performance_v2.schema.json`. SynthPost direction should
be the sole owner of authored/seeded performance events:

```json
{
  "version": "performance_v2",
  "seed": 48291,
  "visemes": [],
  "speech_envelope": [],
  "blink_events": [],
  "gaze_events": [],
  "expression_events": [],
  "body_events": []
}
```

Both renderers must consume the same event list and stop inventing gestures,
emotion, or blink timing. The implementation phase should add viseme
coarticulation, separate jaw/lip ownership, seeded natural blink and gaze,
restrained expression presets, two authored idles, additive presenter gestures,
cooldowns and conclusion settling, then remove speech-driven sine-wave arms.

## Commands used for the reproducible gate

```bash
npm --prefix avatar-engine/web_avatar_runtime run typecheck
npm --prefix avatar-engine/web_avatar_runtime run lint
npm --prefix avatar-engine/web_avatar_runtime run build
PYTHONPATH=avatar-engine avatar-engine/.venv/bin/python -m unittest discover -s avatar-engine/tests
.venv/bin/python -m unittest tests.test_direction

cd avatar-engine
.venv/bin/python scripts/inspect_avatar_asset.py \
  assets/avatars/synthpost_anchor_v1/anchor.glb \
  --source-textures assets/avatars/synthpost_anchor_v1/textures \
  --output assets/output/avatar_bakeoff/asset_inspection.json

.venv/bin/python scripts/run_avatar_quality_gate.py \
  --candidate candidate_a_control --run run_1 \
  --renderer rocketbox --quality-profile legacy_control
.venv/bin/python scripts/run_avatar_quality_gate.py \
  --candidate candidate_a_control --run run_2 \
  --renderer rocketbox --quality-profile legacy_control

.venv/bin/python scripts/run_avatar_quality_gate.py \
  --candidate candidate_b_threejs_final --run run_1 \
  --renderer rocketbox --quality-profile studio_v2 --tone-mapping aces
.venv/bin/python scripts/run_avatar_quality_gate.py \
  --candidate candidate_b_threejs_final --run run_2 \
  --renderer rocketbox --quality-profile studio_v2 --tone-mapping aces

.venv/bin/python scripts/run_avatar_quality_gate.py \
  --candidate candidate_c_blender_eevee_final_v3 --run run_1 \
  --renderer blender_cc --quality-profile studio_v2 --tone-mapping aces
```

Tone-map evidence also rendered ACES, AgX and Neutral candidates under the same
first and corrected lighting rigs. The initial Blender attempts are retained in
ignored directories/logs; they exposed Blender 5.1 engine/look identifiers,
the stray-Icosphere bounds error, imported arm-axis conversion and background
colour calibration. No failed attempt touched production assets.

## Implementation update

The shared `performance_v2` layer is now live in both Three.js and Blender.
SynthPost direction owns deterministic blink, gaze, expression and body events;
the renderers no longer invent sine-wave arm gestures. A reusable CC/Mixamo
retargeting builder produces a Blender NLA Action library and per-clip web GLBs.
Normal SynthPost configuration now selects `rocketbox` for preview and
`blender_cc` for production/final-master renders.

Three bounded EEVEE profiles replace the original 64-sample PNG-only path:

| Profile | Samples | Scale | Frames | Retained |
|---|---:|---:|---|---|
| review | 8 | 75% | JPEG 92 | no |
| production | 32 | 100% | JPEG 95 | no |
| master | 64 | 100% | PNG | yes |

On the same 8-second 1280×720 quality-gate job, the production profile completed
in 43.357 seconds (41.284 seconds inside EEVEE), versus 81.155 seconds for the
original 64-sample PNG path: a 46.6% wall-time reduction. The renderer reported
Blender 5.1.2, `BLENDER_EEVEE`, Metal, ray tracing disabled, 32 samples, and
deleted the 17.6 MB intermediate JPEG sequence after muxing.

The real SynthPost production resolution (1920×1080, 24 fps, 192 frames) completed
in 52.458 seconds, including startup and FFmpeg mux; EEVEE itself took 50.473
seconds. Its 37.9 MB temporary JPEG sequence was deleted automatically. This is
the relevant capacity-planning figure for an 8-second final anchor pass on the
tested Apple-silicon Mac.

The local proof library currently contains one retargeted neutral idle. Acquire
and review the remaining licensed presenter motions listed in
`docs/CC_MOTION_LIBRARY.md`; missing gesture IDs are surfaced in both renderer
diagnostics rather than silently replaced with procedural arm motion.

## Sparse timeline rendering

Final `blender_cc` jobs no longer render the anchor for the entire narration.
The pipeline reads the approved timeline and builds narration-clock windows only
for segments where `anchor.visible` is true and audio is neither `source` nor
`silent`. Adjacent compatible windows are coalesced. If the result is shorter
than the narration, the job enables sparse rendering; otherwise the legacy full
render remains unchanged. If no approved segment displays the anchor, SynthPost
skips Avatar Engine entirely and Remotion renders the narration/visual timeline
without requiring an anchor artifact.

Blender loads the scene and character once, then renders only the global frame
ranges for those windows. Global frame numbers are deliberately preserved so
visemes, expressions, blinks, gaze and body motion keep their original source
time. FFmpeg muxes each window with its matching audio slice and concatenates
them into one compact compatibility MP4. The artifact manifest records, for
every window:

- timeline start/end;
- source narration start/end;
- compact clip start/end;
- contributing segment IDs and rendered source-frame bounds.

Remotion plays the canonical narration file independently, mutes the compact
anchor video's embedded audio, and maps each visible segment from source time to
its compact clip offset. A segment with no matching window cannot display the
anchor. Source-audio inserts do not advance the narration clock.

On the same 8-second 1920×1080 production job used above, two visible windows
(`0–2s` and `6–8s`) rendered 96 frames instead of 192. Wall time fell from
52.458 seconds to 31.651 seconds (39.7%), while the Blender render stage fell
from 50.473 seconds to 26.794 seconds (46.9%). The compact result is 4.018
seconds long; the final Remotion episode remains 8 seconds with uninterrupted
narration. Comparing source second 7 from the full render with compact second 3
gave an all-channel SSIM of 0.995777, confirming that sparse windows preserve
the original animation clock.

Browser/Three.js preview rendering intentionally remains a full-duration pass:
it is already faster than real time, and keeping a continuous preview simplifies
editor iteration. Sparse rendering targets the expensive production EEVEE path.
