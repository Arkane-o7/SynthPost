# SynthPost Anchor Quality Baseline

Baseline date: 2026-08-02. The source job is
`jobs/synthpost_anchor_v1_quality_gate.json`; generated media and frame
sequences live below ignored `assets/output/avatar_bakeoff/` paths.

## Fixed contract

- Current `synthpost_anchor_v1` CC/Reallusion asset only; no live TTS.
- Existing 7.975-second WAV and Rhubarb JSON; 8.0-second camera clock.
- 1280×720, 24 fps, 192 captured PNG frames, `front_close`, fixed transform,
  fixed seed `48291`, near-charcoal background.
- Review times: 0.20, 1.80, 2.55, 3.85, 4.90, 6.90, and 7.80 seconds.
- Review features: rest, camera gaze, bilabial closure, dental cue, wide and
  rounded vowels, blink, pause, small emphasis, and conclusion settle.
- Source-job SHA-256:
  `eb2d376b7080582e7f3df37ad51fb5204a86e66bf34e391b347d6009777ebfc7`.
- Asset SHA-256:
  `9724ea3830b72e383ac9400490066b89c511ca32aaa436243e90cf6a81eddad2`.
- Audio SHA-256:
  `f4c10b123dda159f71a35e3118ab3ca6ba5bd15f0794fa73fe6f0608f2990084`.
- Viseme SHA-256:
  `f67cefe733a79fe332f6bada6a725e1eeb865b2c6251e48e030905c5368f0913`.

The job declares the future `performance_v2` events, but this renderer-only
bake-off deliberately preserves the legacy animation layer for Candidate A and
uses an equivalent legacy layer in Candidates B/C. Consequently the current
runtime produces two fixed-period blinks rather than the contract's one
scheduled blink. Renderer/material conclusions are valid; expression and body
scores are provisional until `performance_v2` is implemented.

## Asset audit

| Field | Live result |
|---|---:|
| GLB path | `assets/avatars/synthpost_anchor_v1/anchor.glb` |
| GLB size | 81,184,020 bytes (77.42 MiB) |
| Scenes / nodes | 1 / 113 |
| Meshes | 11 |
| Materials | 24 |
| Textures / images | 39 / 39 |
| Skins / bones | 1 / 101 |
| Unique morph names across avatar | 284 |
| Main body morph names | 152 |
| Primitive morph-target sets | 1,776 |
| Animation clips | 2 |
| Clip duration | 0.016667 seconds each (single frame) |
| Adjacent source texture files | 119 files, 123,406,697 bytes |

All 119 adjacent source files are supplemental inputs not embedded by filename
in the GLB. They include 24 roughness, 14 AO, 5 SSS, 5 transmission, 5
micro-normal masks, 1 specular mask, eye/cornea, hair-flow/root/ID/weight, and
12 wrinkle maps. The machine-readable report is
`assets/output/avatar_bakeoff/asset_inspection.json`.

## Verified legacy renderer state

- ACES, exposure 1.08, sRGB output, shadows disabled.
- One AmbientLight, one HemisphereLight, and four DirectionalLights; no scene
  environment or PMREM image-based lighting.
- Skin roughness forced to 0.72, normal scale multiplied by 0.18, AO intensity
  reduced to 0.04, and skin-coloured emissive added at 0.075.
- Eye-occlusion opacity forced to zero.
- Broad name-based hair hiding plus CPU defringe and background-dependent alpha.
- Fixed 4,200 ms blink period, one active viseme with 45 ms triangular fade,
  fixed soft-neutral morphs, and procedural sine/speech-driven body motion.

## Scoring rubric

Use integer or half-point scores. `1` is broken/unusable; `2` is visibly
synthetic or distracting; `3` is acceptable for a draft/preview; `4` is
production-ready at normal viewing size; `5` is exceptionally convincing and
stable. Score normal-speed playback plus the seven locked review frames.

| Criterion | What a 4/5 requires |
|---|---|
| Skin depth and roughness | Local roughness/detail, no plastic glow or flat wash |
| Eye wetness/socket definition | Controlled catchlight, visible socket/occlusion, no glass marbles |
| Gaze | Camera intent is stable and alive rather than vacant |
| Hair | Layered volume, clean alpha, no halo, stipple, or temporal flicker |
| Mouth interior | Distinct teeth/tongue/cavity with plausible depth |
| Lip contact | Bilabial closure reads as contact, not near-contact |
| Lip-sync timing | Closures and vowel peaks align with audio at normal speed |
| Facial liveliness | Non-repetitive blinks/gaze/micro-expression without noise |
| Body naturalness | Relaxed posture, authored emphasis, no bind pose or sine-wave arms |
| Temporal stability | No shimmer, alpha flicker, eye popping, or material crawling |
| Compositor fit | Correct crop/background, no edge contamination, stable encoding |

Candidate A was rendered twice. Both MP4 SHA-256 values are
`15e19e607cc07ae65d3952033cd1c5f925d68f99112c72b58e10b3cfd88fdfd7`,
and both decoded-frame-manifest hashes are
`a6d2b59b8c56c7b4cf5e8eb96067f55394e4e6e7e1b5b27aea3b4cb851c2c1f4`.
Candidate B was also rendered twice; its decoded-frame-manifest hash is
`ec40b343c341c4db984a1042a754f7d941716a98066611071e63bf6ef59bc1bf`
for both runs.
