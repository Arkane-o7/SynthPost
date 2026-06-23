# Endscreen Layout Concepts

## 1. Signal Handoff

Best use case: default SynthPost episode ending.

Layout:

- Left 36%: SynthPost logo, closing status, optional fading anchor mini-window.
- Right 64%: two large card bays stacked vertically.
- Bottom: thin ticker line with episode topic/date/category.

What appears:

- `CONTINUE THE BRIEFING`
- `WATCH NEXT`
- `RELATED ANALYSIS`
- `SYNTHPOST SIGNAL`
- Animated dark data grid.

YouTube elements:

- Primary video element in upper-right card bay.
- Secondary video/playlist element in lower-right card bay.
- Subscribe element in left-lower logo bay.

Motion:

- Main frame dims and slides into a data-wall layout.
- Card bays draw on with fine blue borders.
- Background pulses every 4 seconds.

Example text:

```text
CONTINUE THE BRIEFING
WATCH NEXT: THE GRID BOTTLENECK BEHIND THE AI BOOM
RELATED ANALYSIS: HOW DATA CENTERS ARE REWRITING POWER DEMAND
```

Why it works:

- Strongest balance of brand, click clarity, and automation.
- Works for every topic.
- Leaves YouTube cards clean.

Weakness:

- Less visually surprising than a fully custom map animation.

Implementation difficulty: low-medium.

## 2. Global Signal Map

Best use case: geopolitics, conflict, climate, markets, global stories.

Layout:

- Full-screen dark world map.
- Two card bays anchored to right-side geographic nodes.
- Left-center contains a short topic bridge.
- Subscribe/logo sits near lower-left.

What appears:

- World map, route lines, pulsing region markers.
- Next video card bay next to the most relevant region.
- Secondary card bay below.

YouTube elements:

- Video cards on right over clean dark ocean/negative space.
- Subscribe icon lower-left.

Motion:

- Map slowly rotates or pans.
- Region marker pulses.
- Lines draw toward card bays.

Example text:

```text
THE STORY CONTINUES
NEXT SIGNAL: ASIA'S CHIP SUPPLY CHAIN
```

Why it works:

- Very SynthPost: global, analytical, premium.
- Makes the next story feel connected to a bigger system.

Weakness:

- Needs topic/location metadata to shine.
- Risk of visual clutter behind YouTube overlays.

Implementation difficulty: medium.

## 3. Data Wall Outro

Best use case: technology, AI, economy, energy.

Layout:

- Background is a dark analytics wall with charts, terminal-style figures, and subtle diagrams.
- Two video cards sit inside "analysis modules".
- Logo and CTA live in a left vertical rail.

What appears:

- Animated chart lines.
- Headline fragments from the finished episode.
- Next story module.

YouTube elements:

- Primary video card at upper-right.
- Secondary video card at mid-right or lower-right.
- Subscribe lower-left.

Motion:

- Numbers scan in.
- Chart line draws once, then calms.
- Card frames glow gently.

Example text:

```text
NEXT ANALYSIS QUEUED
CONTINUE WITH THE INFRASTRUCTURE STORY
```

Why it works:

- High brand fit for an AI/news analysis channel.
- Highly automatable from episode metadata.

Weakness:

- Can become too "dashboard" if overbuilt.

Implementation difficulty: medium.

## 4. Anchor Handoff

Best use case: opening/closing remarks, opinion/our-take segments.

Layout:

- Anchor remains in a left or center-left framed window.
- Right side is reserved for one large recommended video.
- Lower-left contains subscribe/logo.

What appears:

- Anchor video remains active for first 10 seconds.
- A next-video headline appears beside the card bay.
- Background is newsroom/data wall.

YouTube elements:

- One large video card on right.
- Subscribe below anchor or lower-left.

Motion:

- Anchor panel shrinks from full-screen conclusion into endscreen frame.
- Card bay resolves from a vertical scan.

Example text:

```text
NEXT, THE BIGGER STORY
FOLLOW THE MONEY, POWER, AND POLICY BEHIND THIS DEVELOPMENT
```

Why it works:

- Closest to the reference's human-continuity logic.
- Strong for brand trust.

Weakness:

- Requires anchor footage and a spoken bridge.
- Less useful for episodes without a clean anchor close.

Implementation difficulty: medium.

## 5. Headline Stack Outro

Best use case: multi-story episodes.

Layout:

- Left side shows the episode's headline stack collapsing into "briefing complete".
- Right side has two card bays.
- Bottom ticker lists episode topics.

What appears:

- 3-5 headline chips from the just-finished episode.
- Next video title.
- Related analysis title.

YouTube elements:

- Primary and secondary cards on right.
- Subscribe lower-left.

Motion:

- Episode headlines slide upward and dim.
- Next story headline locks into focus.

Example text:

```text
BRIEFING COMPLETE
NEXT: WHAT MOVES FIRST TOMORROW
```

Why it works:

- Connects the outro to what the viewer just watched.
- Good for daily/news roundup format.

Weakness:

- More text-heavy; needs strict truncation.

Implementation difficulty: low-medium.

## 6. Document Desk

Best use case: policy, court, regulation, government, company announcements.

Layout:

- Background is a dark desk surface with documents/screenshots as low-opacity layers.
- Video cards appear as "next files" on the right.
- SynthPost logo appears as a small stamp/seal.

What appears:

- Document snippets.
- Source labels.
- Next-file CTA.

YouTube elements:

- Upper-right video card.
- Lower-right related video/playlist.
- Subscribe left-lower.

Motion:

- Document line highlight scans.
- Card bay appears as a file slot.

Example text:

```text
OPEN THE NEXT FILE
RELATED: THE POLICY CHAIN REACTION
```

Why it works:

- Feels investigative and serious.
- Strong for regulatory stories.

Weakness:

- Needs document assets or generated document visuals.

Implementation difficulty: medium.

## 7. Market Close

Best use case: finance/economy/business episodes.

Layout:

- Dark financial board background.
- Two card bays arranged like market panels.
- CTA at top-left with a compact SynthPost mark.

What appears:

- Market ticks, commodity lines, policy dates.
- Next story tease.

YouTube elements:

- Two video cards on right.
- Subscribe lower-left.

Motion:

- Chart lines settle into two outlined card spaces.
- Ticker slows during last 5 seconds.

Example text:

```text
THE NEXT MOVE
WATCH THE SIGNAL BEFORE MARKETS OPEN
```

Why it works:

- Topic-specific and premium.

Weakness:

- Too specialized for default use.

Implementation difficulty: medium.

## Recommended V1

Use **Signal Handoff** first.

Reasons:

- High click clarity.
- Strong SynthPost brand fit.
- Lowest risk with YouTube overlays.
- Easy to automate from metadata.
- Can accept real thumbnails, generated thumbnails, or clean placeholder bays.
- Can later gain topic variants without changing the core safe-zone contract.

