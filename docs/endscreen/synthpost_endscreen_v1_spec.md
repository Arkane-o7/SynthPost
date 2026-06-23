# SynthPost Endscreen V1 Spec

Recommended concept: **Signal Handoff**

## Canvas

- Landscape: `1920 x 1080`
- FPS: inherit episode FPS, default `24`
- Duration: `20s`
- Minimum supported duration: `5s`
- Recommended generation duration: `20s`, because it uses YouTube's full endscreen window.

## Input Contract

```json
{
  "episode_title": "FERC Fast-Tracks Grid Rules for AI Data Centers",
  "episode_topic": "energy",
  "next_video_title": "The Grid Bottleneck Behind the AI Boom",
  "next_video_thumbnail": "path/to/next.png",
  "recommended_video_title": "How Data Centers Are Rewriting Power Demand",
  "recommended_video_thumbnail": "path/to/recommended.png",
  "channel_logo": "path/to/synthpost_bug.png",
  "background_visual": "path/to/background.mp4",
  "anchor_video": "path/to/anchor_close.mp4",
  "cta_text": "Continue the briefing",
  "duration_seconds": 20
}
```

## Layout

### Coordinate System

All coordinates are `x, y, width, height` on a `1920 x 1080` canvas.

### Background

- Full canvas.
- Dark navy base: `#050A14`.
- Deep blue radial depth behind card zones: `#071B33`.
- Low-opacity grid: 1px lines every 96px.
- Subtle data texture: 4-8% opacity.
- Optional background visual dimmed to 18-28% opacity.

### Left Brand/Status Column

Bounds: `x=80, y=130, w=760, h=820`

Elements:

- Small eyebrow: `SYNTHPOST SIGNAL`
- Main CTA: `CONTINUE THE BRIEFING`
- Episode bridge line: topic-aware copy, max 90 chars.
- Optional anchor mini-window for first 7 seconds.
- Subscribe/logo safe bay lower-left.

### Main CTA

Position: `x=84, y=152`

Text:

```text
CONTINUE THE BRIEFING
```

Style:

- Serif display, uppercase.
- Size: `62px`
- Line height: `1.02`
- Color: `#F5F7FA`
- Text shadow: dark, low blur.

### Topic Bridge

Position: `x=88, y=300`

Text examples:

- `The next signal follows the power, policy, and infrastructure race.`
- `Continue with the story behind the market reaction.`
- `Follow the map from today's headline to tomorrow's pressure point.`

Style:

- Sans uppercase or small caps.
- Size: `24px`
- Max width: `650px`
- Color: `#AAB4C2`

### Primary Video Slot

Safe zone: `x=1080, y=168, w=650, h=366`

Rendered decoration:

- Thin border: `rgba(245,247,250,0.28)`
- Inner glow: `rgba(31,123,255,0.18)`
- Label above: `WATCH NEXT`
- Title below or left of card, but not under the YouTube card overlay.

Important:

- Do not render essential text inside this rectangle.
- The YouTube video element should be placed here in Studio.

### Secondary Video Slot

Safe zone: `x=1080, y=590, w=650, h=366`

Rendered decoration:

- Same frame treatment, lower visual priority.
- Label: `RELATED ANALYSIS`

### Subscribe Slot

Safe zone: `x=132, y=684, w=260, h=260`

Rendered decoration:

- SynthPost logo/wordmark nearby.
- Small label: `SUBSCRIBE FOR THE NEXT SIGNAL`
- Keep the actual circular YouTube subscribe overlay unobstructed.

### Brand Strip

Position: `x=80, y=990, w=1760, h=34`

Content:

```text
SYNTHPOST SIGNAL  /  ENERGY  /  AI INFRASTRUCTURE  /  NEXT BRIEFING QUEUED
```

Style:

- 15-17px sans.
- Muted text.
- Signal blue separators.

## Motion Timeline

### 0.0-1.5s

- Previous scene or background visual is dimmed.
- Grid fades in from 0% to 18%.
- Main CTA rises 24px into place.

### 1.5-4.0s

- Primary card frame draws in.
- `WATCH NEXT` label appears.
- Next video title reveals with a masked horizontal wipe.

### 4.0-6.5s

- Secondary card frame draws in.
- `RELATED ANALYSIS` label appears.
- Anchor mini-window, if present, is still visible and speaking.

### 6.5-9.0s

- Subscribe/logo zone resolves.
- Anchor mini-window fades to the logo/status stack unless `keep_anchor_visible=true`.

### 9.0-15.0s

- Background continues subtle motion only.
- Card bays pulse once every 4 seconds at very low opacity.
- Text remains static and readable.

### 15.0-20.0s

- Motion calms further.
- Safe zones remain clean.
- Music tail continues.
- No new text appears.

## Typography

Use existing SynthPost typography in Remotion:

- Display serif: `Georgia, "Times New Roman", serif` for now.
- Sans: `"Avenir Next", "Helvetica Neue", Helvetica, sans-serif`.

Future upgrade:

- Replace Georgia with a licensed editorial display face.
- Replace Avenir fallback with a licensed grotesk or news UI face.

## Color Palette

```ts
{
  navy: "#050A14",
  deepBlue: "#071B33",
  signalBlue: "#1F7BFF",
  steelBlue: "#5C7FA6",
  yellow: "#FFD84A",
  white: "#F5F7FA",
  muted: "#AAB4C2",
  ink: "#020610"
}
```

## Borders, Shadows, Glows

- Card border: `1px solid rgba(245,247,250,0.26)`
- Primary accent line: `2px #1F7BFF`
- Shadow: `0 18px 54px rgba(0,0,0,0.38)`
- Glow: restrained; avoid neon/gaming feel.

## Thumbnail Treatment

Render thumbnails only as background helpers if desired. The actual YouTube video card will cover them. If thumbnails are rendered, keep them darkened and non-essential.

Recommended v1:

- Render card frames and labels.
- Do not render full thumbnail art inside the clickable zone by default.
- Store thumbnail paths in metadata for future automated YouTube upload/studio setup.

## Audio Behavior

- Duration: 20 seconds.
- First 6-10 seconds can include generated anchor/voice bridge.
- Last 10 seconds should be mostly music/bed.
- Use a consistent SynthPost outro bed.
- Duck bed under voice by 3-5 dB.
- End with a clean half-second decay, not a hard cut.

## Output Files

For each episode:

```text
episodes/<episode_id>/endscreen/
  endscreen.json
  endscreen.mp4
  endscreen_preview.png
  endscreen_safe_zones.json
```

## Metadata Output

```json
{
  "canvas": [1920, 1080],
  "duration_seconds": 20,
  "zones": {
    "primary_video": {"x": 1080, "y": 168, "width": 650, "height": 366},
    "secondary_video": {"x": 1080, "y": 590, "width": 650, "height": 366},
    "subscribe": {"x": 132, "y": 684, "width": 260, "height": 260}
  }
}
```

