# YouTube Endscreen Rules And SynthPost Safe Zones

Verified date: 2026-06-23

Primary source: [YouTube Help: Add end screens to videos](https://support.google.com/youtube/answer/6388789)

## Current YouTube Rules To Respect

From YouTube Help:

- End screens can be added to the last `5-20` seconds of a video.
- A video must be at least `25` seconds long to have an end screen.
- End screens can include elements for videos, playlists, subscribe, channels, links, and merch.
- In a standard `16:9` video, up to `4` elements can be added.
- Other aspect ratios may have lower limits.
- YouTube recommends leaving enough space and time at the end of the video for an end screen.

## Practical SynthPost Defaults

Use:

- Endscreen duration: `20s`
- Landscape canvas: `1920 x 1080`
- Max rendered card zones: `2` video zones + `1` subscribe zone
- Do not use all 4 possible YouTube elements in v1; three is cleaner and more clickable.

## Why Not Fill All Four Slots?

Four elements can be allowed for 16:9, but a premium news channel should avoid clutter. Too many choices can reduce click intent. SynthPost v1 should prioritize:

1. Primary next video.
2. Related analysis or playlist.
3. Subscribe.

## Safe Zone Coordinates

These are SynthPost design coordinates, not official YouTube pixel specs. YouTube does not publish a stable pixel-perfect endscreen grid for every player/device in the public Help article, so the generator should export these zones and verify in YouTube Studio's preview UI.

### Landscape 1920x1080

```json
{
  "primary_video": {"x": 1080, "y": 168, "width": 650, "height": 366},
  "secondary_video": {"x": 1080, "y": 590, "width": 650, "height": 366},
  "subscribe": {"x": 132, "y": 684, "width": 260, "height": 260}
}
```

### Reserved Margins

- Outer margin: at least `80px`.
- Card-label gap: at least `22px`.
- No essential text inside card rectangles.
- No important face/detail behind subscribe circle.
- Keep lower ticker below card zones or behind non-clickable space only.

## Text Safety Rules

Avoid putting:

- Headlines inside the clickable video rectangles.
- CTA text beneath the subscribe circle.
- Tiny metadata near YouTube overlays.
- Important data in the bottom-right if the player UI may cover it.

Do put:

- Labels just outside the card zones.
- Decorative borders around card zones.
- Non-essential texture behind the overlays.

## Preview Workflow

1. Render `endscreen_preview.png`.
2. Render `endscreen_safe_zones.json`.
3. Generate a debug preview with semi-transparent safe-zone overlays.
4. Upload a private/unlisted test video to YouTube.
5. In YouTube Studio, add endscreen elements in the reserved zones.
6. Use YouTube's preview before publishing.
7. If overlays cover text, adjust the safe-zone JSON or text positions.

## Aspect Ratio Notes

### 16:9 Landscape

Primary target for SynthPost. Supports the richest layout.

### 9:16 Portrait

Optional future output. Use fewer elements and much larger typography. The landscape coordinates cannot be reused.

### 1:1 Or Other Formats

Use a separate safe-zone preset. Do not auto-crop the landscape endscreen.

## Implementation Guardrails

- Clamp generated endscreen duration to `5-20s`.
- Warn if episode duration is under `25s`.
- Warn if more than 3 visible zones are requested in v1.
- Export safe-zone metadata with every render.
- Keep a `debug_safe_zones` render option.

