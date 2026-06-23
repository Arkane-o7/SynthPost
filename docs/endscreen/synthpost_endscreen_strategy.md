# SynthPost Endscreen Strategy

## Core Concept

The SynthPost endscreen should feel like the final beat of a broadcast briefing, not a random outro card. The anchor or episode voice should hand the viewer from the finished story into the next relevant story while the visual system opens clean YouTube endscreen zones.

## Reusable Principle

End the episode by converting the broadcast frame into a "next briefing desk": the current story recedes, the next story becomes the obvious continuation, and YouTube's clickable elements sit inside intentionally reserved zones.

## SynthPost-Specific Direction

### Overall Concept

Name: **Signal Handoff**

The episode closes with a final analytical line, then the frame transforms into a dark data-wall endscreen. The current episode remains represented as a small closing panel or fading anchor panel, while two large clean card bays invite the viewer to continue.

### Visual Mood

- Dark navy and deep blue editorial base.
- Subtle global grid, scanning lines, coordinates, and muted data texture.
- A precise premium news look rather than a creator-template look.
- Serious and analytical, with just enough motion to feel alive.

### Layout

Recommended v1 landscape layout:

- Left column: SynthPost logo, closing line, and small "briefing complete" status.
- Center/right: two large endscreen-safe video card bays stacked or side-by-side.
- Lower strip: low-intensity ticker-style metadata: episode topic, date, category.
- Optional small anchor window during the first 5-7 seconds, then fades down.

### Motion Style

- Main episode frame darkens and scales down slightly.
- Data grid resolves into card bays.
- Next video thumbnail area receives a subtle scan/pulse.
- Text enters with precise broadcast timing: no bouncy creator-style animation.
- Final 5 seconds become calmer so YouTube overlays remain readable.

### Background Treatment

Use one of:

- Blurred/dimmed final story visual.
- A generated dark global map.
- Topic-aware background: map for geopolitics, document texture for policy, chip/data pattern for AI, chart grid for markets.

The background must stay behind the safe zones and never fight the clickable cards.

### Text Treatment

Text should be sparse:

- Main CTA: `CONTINUE THE BRIEFING`
- Next video label: `WATCH NEXT`
- Secondary video label: `RELATED ANALYSIS`
- Subscribe label: `SYNTHPOST`
- Optional topic bridge: `NEXT: WHY THIS STORY MATTERS`

Avoid paragraphs. The thumbnail/card title should carry the curiosity.

### CTA Language

Best SynthPost CTA style:

- `Continue the briefing`
- `Watch the next signal`
- `Follow the next development`
- `More analysis from SynthPost`

Avoid generic:

- `Like and subscribe!!!`
- `Click here`
- `Don't forget`

### YouTube Endscreen Slot Placement

Reserve clean zones rather than rendering fake clickable cards:

- Primary video card bay: `x=1090, y=210, w=640, h=360`
- Secondary video card bay: `x=1090, y=610, w=640, h=360`
- Subscribe circle/logo bay: `x=200, y=650, w=220, h=220`

The rendered design can include subtle frames and labels, but the most important content should not sit under YouTube overlays.

### Next Video Tease

The endscreen generator should use `next_video_title`, `next_video_thumbnail`, and optionally `next_video_hook`.

Example:

```text
WATCH NEXT
THE GRID BOTTLENECK BEHIND THE AI BOOM
```

The anchor/voice can say:

```text
For the next layer of this story, continue with our briefing on power, chips, and the infrastructure race.
```

### Brand Appearance

SynthPost brand should appear as:

- Logo or wordmark on the left.
- Small status strip: `SYNTHPOST SIGNAL`
- Blue dot/accent as the active signal marker.
- No giant logo taking over the card zones.

### Anchor Transition

For v1:

- Final story ends normally.
- Endscreen begins with a 1-second darkened continuation frame.
- Anchor shrinks to a small left panel for 5-7 seconds if `anchor_video` exists.
- Anchor panel fades to logo/status area after the spoken bridge.

For v2:

- Anchor can explicitly hand off to the next story using generated copy.

### Music And Audio

- Use the final seconds of the episode bed or a neutral SynthPost outro bed.
- Keep voice/anchor bridge in the first 6-10 seconds.
- Reduce music by 3-5 dB under voice.
- Last 5 seconds can be mostly music and ambient data pulse.
- Avoid abrupt silence before YouTube autoplay recommendation appears.

## Essential Pieces

- A moving branded background.
- Clean YouTube card zones.
- One strong CTA line.
- Next-video title or tease.
- SynthPost logo/identity.
- Metadata output describing safe zones.

## Optional Pieces

- Anchor mini-window.
- Topic-aware map/document/chart background.
- Dynamic lower ticker.
- Two recommendation cards instead of one.
- Portrait version for Shorts-like recuts.

## Anti-Patterns To Avoid

- Static black outro screen.
- Fake video thumbnails that fight the real YouTube overlay.
- Heavy text under clickable cards.
- Three or four competing CTAs.
- Stock-looking generic "subscribe" animations.
- Gamer-like neon overload.

