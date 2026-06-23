# Endscreen Generator Technical Spec

## Recommended Implementation

Use **Remotion** for v1.

Why:

- SynthPost already uses Remotion for programmatic broadcast layouts.
- It can render MP4 and preview PNG in one flow.
- It handles timed motion, images, video backgrounds, and reusable React components cleanly.
- It fits the existing manifest-driven pipeline.

## Comparison

### Remotion

Pros:

- Best match for current stack.
- Easy props/schema flow.
- Frame-accurate layout.
- Can reuse SynthPost brand tokens/components.
- Can output preview PNG and MP4.

Cons:

- Requires Node render environment.
- Need care with video/audio handling and safe zones.

Verdict: best v1 choice.

### HTML/CSS + Playwright

Pros:

- Familiar web layout.
- Fast static screenshot iteration.

Cons:

- Video rendering is less direct.
- Audio/timeline control is more awkward.
- Would duplicate Remotion's job.

Verdict: good for mockups, not v1 render pipeline.

### FFmpeg Overlays

Pros:

- Fast and scriptable.
- Great for simple compositing.

Cons:

- Painful for precise animated UI.
- Harder to maintain as a design system.

Verdict: use only for final stitching/audio normalization.

### Blender Outro Scene

Pros:

- Could look cinematic.

Cons:

- Slow.
- Overkill for YouTube card-safe layout.
- Harder to generate topic variants.

Verdict: not v1.

### Static PNG + Motion Layers

Pros:

- Simple.
- Reliable.

Cons:

- Risks feeling static/generic.
- Less dynamic and less metadata-driven.

Verdict: acceptable fallback, not the main system.

## Folder Structure

```text
compositor/remotion_renderer/src/
  endscreen/
    Endscreen.tsx
    endscreen.schema.ts
    endscreenStyles.ts
    renderEndscreen.ts
    sample_endscreen.json
  components/
    LogoBug.tsx
    media.ts
  styles/
    brand.ts

pipeline/
  endscreen.py

episodes/<episode_id>/endscreen/
  endscreen.json
  endscreen.mp4
  endscreen_preview.png
  endscreen_safe_zones.json
```

## Props Schema

```ts
export type EndscreenSlot = {
  title: string;
  thumbnail?: string;
  label: string;
  zone: "primary_video" | "secondary_video" | "subscribe";
};

export type EndscreenProps = {
  episodeId: string;
  episodeTitle: string;
  episodeTopic: string;
  nextVideoTitle: string;
  nextVideoThumbnail?: string;
  recommendedVideoTitle?: string;
  recommendedVideoThumbnail?: string;
  channelLogo?: string;
  backgroundVisual?: string;
  anchorVideo?: string;
  ctaText?: string;
  bridgeText?: string;
  durationSeconds: number;
  fps?: number;
  safeZones?: EndscreenSafeZones;
};
```

## Rendering Flow

1. Pipeline writes `episodes/<episode_id>/endscreen/endscreen.json`.
2. `renderEndscreen.ts` reads JSON.
3. Remotion bundles `Root.tsx` or a dedicated `EndscreenRoot.tsx`.
4. Renderer selects composition id `synthpost-endscreen`.
5. Renderer writes:
   - `endscreen_preview.png`
   - `endscreen.mp4`
   - `endscreen_safe_zones.json`
6. `assembly/stitch_episode.py` appends `endscreen.mp4` after the final story, before or instead of a generic outro.

## Remotion Component Structure

```text
Endscreen
  BackgroundSystem
    BackgroundVideoOrImage
    DataGrid
    TopicTexture
  BrandColumn
    Logo
    CTA
    BridgeText
    SubscribeZoneGuide
  VideoSlot
    PrimaryVideoSafeZone
    Label
    Title
  VideoSlot
    SecondaryVideoSafeZone
    Label
    Title
  SignalTicker
  SafeZoneDebugOverlay (dev only)
```

## Motion Implementation

Use Remotion hooks:

- `useCurrentFrame`
- `useVideoConfig`
- `interpolate`
- `spring` only if restrained

Motion should be deterministic and short:

- Fade/dim background.
- Draw card borders.
- Slide in labels.
- Pulse card edges subtly.
- No random animations at render time.

## Asset Requirements

Required:

- SynthPost logo or text fallback.
- Next video title.
- Duration.

Optional:

- Next thumbnail.
- Related thumbnail.
- Background visual.
- Anchor close video.
- Outro music bed.

Fallbacks:

- If thumbnail missing: render a dark card bay with generated topic texture.
- If logo missing: text fallback `Synthpost.`
- If background missing: procedural data grid.
- If related video missing: hide secondary slot or change it to playlist-safe zone.

## Export Process

Command:

```bash
cd compositor/remotion_renderer
npm run render:endscreen -- /absolute/path/to/endscreen.json
```

Python wrapper:

```bash
python3 -m pipeline.endscreen episodes/<episode_id>/endscreen/endscreen.json --force
```

## Stitching Into Final Episode

Assembly should concatenate:

```text
intro.mp4
story_1/composited.mp4
story_2/composited.mp4
...
endscreen/endscreen.mp4
```

The endscreen should be normalized to:

- `1920x1080`
- `24fps` or episode FPS
- `h264`
- `yuv420p`
- AAC audio

## Testing

Unit tests:

- Schema accepts valid input.
- Duration clamps to 5-20 seconds.
- Safe zones are within 1920x1080.
- Missing logo/thumbnail/background does not crash.
- Text truncation prevents overflow.

Visual tests:

- Render preview PNG.
- Check safe-zone debug overlay.
- Verify no essential text inside clickable card rectangles.
- Verify output duration with `ffprobe`.

Manual QA:

- Upload a private/unlisted test video.
- In YouTube Studio, place endscreen elements on the exported safe zones.
- Preview inside Studio before publish.

## Pipeline Integration

Add `pipeline/endscreen.py`:

- Reads episode metadata.
- Selects next/recommended video from config or manifest.
- Writes `endscreen.json`.
- Calls Remotion renderer.
- Returns `endscreen.mp4`.

Add to `assembly/stitch_episode.py`:

- If `episodes/<episode_id>/endscreen/endscreen.mp4` exists, include it before final outro or use it as final outro.

