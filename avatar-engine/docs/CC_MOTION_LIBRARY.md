# CC Anchor Motion Library

SynthPost no longer synthesizes presenter body motion with sine waves. Both the
Three.js preview renderer and Blender EEVEE final renderer load retargeted,
named animation clips from the same manifest:

`assets/motions/synthpost_anchor_v1/motions.json`

The repository tracks the manifest and importer code. Licensed FBX/BVH source
files, the generated Blender Action library, and generated web GLBs stay local
or in the project's binary-asset store and are ignored by Git.

## Required presenter pack

The intended first production pack is deliberately small and restrained:

- `IDLE_Neutral`, `IDLE_Attentive`, `IDLE_Serious`
- `EXPLAIN_Right_Small`, `EXPLAIN_Left_Small`, `EXPLAIN_Both_Open`
- `EMPHASIS_Right`, `EMPHASIS_Left`, `NOD_Small`
- `LEAN_Forward_Small`, `TRANSITION_Reset`, `CONCLUSION_Settle`

Prefer ActorCore/iClone motions made for the Reallusion CC skeleton. Mixamo FBX
is also supported by the builder, but usually needs amplitude reduction and a
creative review. Export without mesh when possible, in-place, with consistent
24 fps sampling. Do not commit or redistribute motion files unless their license
explicitly permits it.

## Build/retarget

Run Blender in the `avatar-engine` directory and map each manifest clip ID to
one source file:

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup \
  --python blender/build_cc_motion_library.py -- \
  --avatar assets/avatars/synthpost_anchor_v1/anchor.glb \
  --manifest assets/motions/synthpost_anchor_v1/motions.json \
  --source IDLE_Neutral=/absolute/path/idle.fbx \
  --source EXPLAIN_Right_Small=/absolute/path/explain-right.fbx \
  --source CONCLUSION_Settle=/absolute/path/settle.fbx \
  --fps 24
```

The builder retargets native CC or Mixamo bone names, bakes Actions on the
current anchor skeleton, saves `cc_anchor_actions.blend`, and exports one GLB
per Action under `web/`. `relative_to_first_frame` in the manifest preserves
SynthPost's calibrated anchor posture while applying the motion delta; this is
recommended for generic or seated source idles.

## Runtime behavior

- Blender appends only required Actions, loops the chosen idle on an NLA
  `REPLACE` track, and blends gesture/transition Actions on a separate track.
- Three.js loads available clip GLBs, crossfades the idle, and schedules the
  same one-shot body events.
- Face, viseme, authored expression, blink, and camera-gaze layers retain
  ownership of the head/face. Body clips should therefore exclude head motion.
- Missing clips are reported in renderer diagnostics. The current local proof
  library contains `IDLE_Neutral`; production gesture clips must be supplied
  from an appropriately licensed pack.

Set `animation.require_motion_library=true` in a job to fail instead of falling
back when the generated Action library is unavailable.

## Creative acceptance

Review every new clip at normal speed in both renderers. Reject clips with
shoulder shrugging, locked elbows, hip translation, foot drift, excessive hand
travel, head motion that fights gaze, or a pose that does not settle cleanly.
Reduce clip weight/amplitude or trim/rebake the source before adding more
procedural correction code.
