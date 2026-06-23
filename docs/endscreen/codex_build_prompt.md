# Codex Build Prompt: SynthPost Endscreen Generator

Build the v1 SynthPost endscreen generator based on the docs in `docs/endscreen/`.

## Goal

Implement a reusable Remotion-based endscreen system named **Signal Handoff**.

It should generate:

- `1920x1080` endscreen MP4
- Preview PNG
- Safe-zone metadata JSON
- Sample JSON input
- Pipeline integration point

It must work automatically from JSON props and match the SynthPost broadcast identity.

## Files To Build

Create:

```text
compositor/remotion_renderer/src/endscreen/
  Endscreen.tsx
  endscreen.schema.ts
  endscreenStyles.ts
  renderEndscreen.ts
  sample_endscreen.json

pipeline/
  endscreen.py
```

Update if needed:

```text
compositor/remotion_renderer/src/Root.tsx
compositor/remotion_renderer/package.json
assembly/stitch_episode.py
README.md
```

## Component Requirements

### `Endscreen.tsx`

Build a Remotion component with:

- Dark navy/deep-blue background.
- Subtle grid/data texture.
- Optional background image/video using `Img` or `OffthreadVideo`.
- Left brand/status column.
- Main CTA text.
- Bridge text.
- Primary video safe-zone bay.
- Secondary video safe-zone bay.
- Subscribe safe-zone bay.
- Lower signal ticker.
- Optional debug safe-zone overlay.

Use SynthPost brand tokens from:

```text
compositor/remotion_renderer/src/styles/brand.ts
```

Do not copy any reference-video visual identity.

### `endscreen.schema.ts`

Define and validate:

```ts
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
  debugSafeZones?: boolean;
};
```

Validation:

- Clamp duration to `5-20`.
- Default fps to `24`.
- Require `episodeTitle`, `episodeTopic`, and `nextVideoTitle`.
- Allow missing thumbnail/logo/background with graceful fallback.

### `endscreenStyles.ts`

Export:

- `ENDSCREEN_SAFE_ZONES`
- layout constants
- text style helpers
- motion timing constants

Use safe zones:

```ts
primary_video: {x: 1080, y: 168, width: 650, height: 366}
secondary_video: {x: 1080, y: 590, width: 650, height: 366}
subscribe: {x: 132, y: 684, width: 260, height: 260}
```

### `renderEndscreen.ts`

Use Remotion renderer Node API:

- `bundle()`
- `selectComposition()`
- `renderStill()`
- `renderMedia()`

Input:

```bash
npm run render:endscreen -- /absolute/path/to/endscreen.json
```

Output:

```text
episodes/<episode_id>/endscreen/endscreen.mp4
episodes/<episode_id>/endscreen/endscreen_preview.png
episodes/<episode_id>/endscreen/endscreen_safe_zones.json
```

Do not use a raw CLI props string.

### `sample_endscreen.json`

Include a working sample:

```json
{
  "episodeId": "ep_2026-06-21-ferc-grid",
  "episodeTitle": "FERC Fast-Tracks Grid Rules for AI Data Centers",
  "episodeTopic": "energy",
  "nextVideoTitle": "The Grid Bottleneck Behind the AI Boom",
  "recommendedVideoTitle": "How Data Centers Are Rewriting Power Demand",
  "ctaText": "Continue the briefing",
  "bridgeText": "The next signal follows the power, policy, and infrastructure race.",
  "durationSeconds": 20,
  "fps": 24,
  "debugSafeZones": false
}
```

### `pipeline/endscreen.py`

Implement:

```python
def render_endscreen(episode_id: str, *, force: bool = False) -> Path:
    ...
```

It should:

- Locate `episodes/<episode_id>/endscreen/endscreen.json`.
- Run `npm run render:endscreen`.
- Reuse fresh output unless `force=True`.
- Return the MP4 path.

### Assembly Integration

Update `assembly/stitch_episode.py` so if:

```text
episodes/<episode_id>/endscreen/endscreen.mp4
```

exists, it is appended after story segments and before any old generic outro, or replaces the generic outro if that is cleaner.

## Motion Timeline

Use a 20-second composition:

- `0.0-1.5s`: background dims, CTA enters.
- `1.5-4.0s`: primary card bay draws on.
- `4.0-6.5s`: secondary card bay draws on.
- `6.5-9.0s`: subscribe/logo zone resolves.
- `9.0-15.0s`: subtle card pulse and data background.
- `15.0-20.0s`: calm readable hold.

## YouTube Constraints

Follow `docs/endscreen/youtube_endscreen_safe_zones.md`:

- Endscreen duration must be `5-20s`.
- Episode video should be at least `25s`.
- Use no more than 3 visible zones in v1.
- Do not place important text under clickable zones.

## Testing

Run:

```bash
cd compositor/remotion_renderer
npm run typecheck
npm run render:endscreen -- src/endscreen/sample_endscreen.json
```

Run Python tests:

```bash
python3 -m unittest discover -s tests
```

Add tests if practical:

- schema duration clamp
- missing optional assets
- safe zones within canvas
- renderer writes preview/mp4/metadata

## Acceptance Criteria

- `Endscreen.tsx` renders without missing optional assets.
- Output MP4 is `1920x1080`.
- Preview PNG is created.
- Safe-zone JSON is created.
- YouTube card zones are visually clean.
- Design feels SynthPost: dark, analytical, premium, not generic.
- The system is reusable for every episode via JSON input.

