# Rendering And Optimization

The project supports two practical render modes:

- **Preview**: fast, low quality, used for script, lip-sync, camera, and framing checks.
- **Final**: slower, higher quality, used for publishable news-anchor segments.

## Why Renders Get Slow

Render time is roughly:

```text
clip duration x fps x seconds per frame
```

Heavy props, high-poly models, complex materials, shadows, GI, volumetrics, reflections, and high sample counts all increase seconds per frame.

## Fast Preview Settings

Use these only for iteration:

```json
"render_profile": "preview"
```

The preview profile sets `12 fps`, `960x540`, low samples, draft mode, disabled shadows, and combined MP4 export. Preview renders are intentionally flat because shadows and expensive lighting are disabled.

## Final Render Settings

Use these for the final anchor segment:

```json
"render_profile": "production"
```

The production profile sets `24 fps`, `1920x1080`, native camera resolution scale, and native segment export. Do not set `disable_shadows` for final renders.

With the current template camera settings, the production profile renders native segments at about `1920x1080` for landscape cameras and about `900x1328` for the portrait camera. These source clips are close to the final episode canvas instead of being oversized.

`camera_resolution_scale` multiplies each Blender camera's saved per-camera resolution. `camera_resolution_overrides` can replace that scale for individual semantic cameras. The nested `scale` is the same kind of multiplier, but scoped to one camera and applied instead of the global value.

For backend/editor use, prefer:

```json
"export_mode": "native_segments"
```

This avoids baking black bars into portrait shots. Each camera cut is exported as its own MP4, so downstream FFmpeg, Premiere, DaVinci, or compositor workflows can place portrait and landscape clips independently.

## Decrease Polygon Count

For background models:

1. Duplicate the object or collection first.
2. Select the duplicate.
3. Add Modifier -> Generate -> Decimate.
4. Start with `Ratio: 0.5`.
5. Try `0.25` for background props.
6. Apply only when the object still looks acceptable.

Good decimation candidates:

- books
- background shelf props
- decorative objects
- furniture far from camera
- objects partly hidden behind the anchor

Be careful with:

- hands
- avatar face/head
- visible silhouettes near camera
- objects with readable text

## Bake Lighting And Shadows

Baking is useful for static newsroom props. It calculates lighting once and stores it into textures, reducing per-frame lighting work.

Best bake candidates:

- background shelves
- walls
- desk
- static props
- contact shadows behind the anchor

Avoid baking:

- animated body parts
- moving face surface
- objects that need live shadows

Typical workflow:

1. Duplicate the production `.blend`.
2. UV unwrap static objects.
3. Create a new image texture for the bake.
4. Use Cycles bake for `Combined`, `Diffuse`, or `Ambient Occlusion`.
5. Save baked textures.
6. Use simple materials with baked textures in the production template.
7. Keep live shadows mostly for the avatar and desk contact.

## Practical Newsroom Targets

For a realtime-ish local render:

- Use one or two shadow-casting lights.
- Keep background props low-poly.
- Avoid subdivisions on render for background objects.
- Prefer 1K or 2K textures for background.
- Bake static light/shadow details.
- Use high samples only for final renders.
- Keep final anchor segments short, then assemble them in the episode editor.

## When To Use A Realtime Engine

If the goal becomes interactive or near-instant final-quality output, use Blender as the asset authoring tool and move runtime rendering to Unreal, Unity, or another realtime engine. Blender can still create the set, avatar, materials, and Actions; the realtime engine handles playback and capture.
