# Blender Scene Guide

This guide describes the production scene contract for the AI news-anchor renderer.

## Production Template

The runtime loads:

```text
blender/avatar_template.blend
```

Normal runs must not save this file. Keep scratch scenes and backups separate from the production template until you intentionally promote them.

## Required Objects

The validator expects:

- `CHAR_Avatar`
- `ARM_Avatar`
- `FACE_Surface`
- `FACE_Backdrop`
- `CAM_Portrait_Main`
- `CAM_Landscape_Intro`
- `CAM_Landscape_Conclusion`

Run validation:

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b blender/avatar_template.blend --python blender/validate_template.py
```

## Cameras

Camera jobs use semantic names:

| Job Name | Blender Object | Use |
| --- | --- | --- |
| `landscape_intro` | `CAM_Landscape_Intro` | wide opening shot |
| `portrait_main` | `CAM_Portrait_Main` | tight anchor shot |
| `landscape_conclusion` | `CAM_Landscape_Conclusion` | closing or alternate wide shot |

The template currently uses the Per-Camera Resolution addon. Keep each camera's custom resolution set to the framing it is designed for. For example, landscape cameras can be `16:9`, while the portrait camera can stay vertical.

The runner renders frames per camera. In `combined` export mode, portrait frames are centered with side padding inside one final MP4 canvas. In `native_segments` export mode, each camera cut becomes its own MP4 at the camera's native aspect ratio, which is better for downstream editing and FFmpeg stitching.

With the current demo template settings, the preview native segment sample writes `1920x1080` landscape clips and a `900x1328` portrait clip. The production profile doubles those camera settings and writes about `3840x2160` landscape clips and a `1800x2656` portrait clip. These dimensions come from the template camera resolution settings plus `camera_resolution_scale`.

## Face Objects

For 2D face mode:

- `FACE_Backdrop` provides the screen/background.
- `FACE_Surface` receives transparent mouth PNG textures.
- Both should be parented to the avatar/head setup so they follow the character naturally.

Do not animate `FACE_Surface` directly for gestures. The mouth texture system updates only the material image for Rhubarb cues.

## Mouth Textures

Required files:

- `assets/characters/avatar_01/mouth_textures/mouth_X.png`
- `assets/characters/avatar_01/mouth_textures/mouth_A.png`
- `assets/characters/avatar_01/mouth_textures/mouth_B.png`
- `assets/characters/avatar_01/mouth_textures/mouth_C.png`
- `assets/characters/avatar_01/mouth_textures/mouth_D.png`
- `assets/characters/avatar_01/mouth_textures/mouth_E.png`
- `assets/characters/avatar_01/mouth_textures/mouth_F.png`
- `assets/characters/avatar_01/mouth_textures/mouth_G.png`
- `assets/characters/avatar_01/mouth_textures/mouth_H.png`

All mouth images should share the same canvas size and transparent background.

## Gesture Actions

Optional Blender Actions checked by doctor/validation:

- `IDLE_Neutral`
- `HEAD_Nod_Small`
- `HEAD_Shake_Small`
- `RIGHT_Hand_Emphasis`
- `LEFT_Hand_Emphasis`
- `BOTH_Hands_Open`
- `LEAN_Forward`
- `LEAN_Back`
- `SHOULDER_Shrug`
- `RESET_Seated_Pose`

Missing Actions are warnings, not failures. Author Actions on `ARM_Avatar`.

## Static Newsroom Props

Most newsroom props should be static background assets:

- shelves
- books
- desk
- screens
- walls
- decorative models

These are safe candidates for low-poly versions, baked lighting, baked ambient occlusion, and simplified materials. Avoid expensive glass, volumetrics, unnecessary subdivisions, and many shadow-casting lights.

## Render Quality Notes

Preview jobs can use:

```json
"render_quality": "draft",
"render_samples": 4,
"disable_shadows": true
```

Final jobs should omit these fields unless intentionally producing a flat/fast draft. Good newsroom lighting needs shadows, contact shadows, and enough samples to avoid noisy edges.
