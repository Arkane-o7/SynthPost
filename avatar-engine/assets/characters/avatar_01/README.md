# Avatar 01

Place the prepared stylized news-anchor avatar assets for `avatar_01` here.

Expected Blender scene object names for the MVP:

- `FACE_Backdrop` for the face display/backing surface.
- `FACE_Surface` for 2D mouth texture swaps.
- An avatar mesh with shape keys for 3D mouth and expression animation.
- An armature with common seated character bones for placeholder gestures.
- Cameras named `CAM_Portrait_Main`, `CAM_Landscape_Intro`, and `CAM_Landscape_Conclusion`.

See `docs/BLENDER_SCENE_GUIDE.md` for the full production scene contract.

## 2D Mouth Textures

Place transparent PNG mouth drawings in `mouth_textures/`:

- `mouth_X.png` and `mouth_A.png`: closed/rest
- `mouth_B.png`: M/B/P
- `mouth_C.png`: E/I
- `mouth_D.png`: A/open
- `mouth_E.png`: O
- `mouth_F.png`: U/W
- `mouth_G.png`: F/V
- `mouth_H.png`: L

All mouth PNGs should share the same canvas size and transparent background. Missing cue textures fall back to `mouth_X.png` with a warning during Blender rendering.
