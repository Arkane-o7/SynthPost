# Sidequest storytime-animation pipeline

Sidequest is Synthea's original limited-animation channel package. It uses the
storytelling grammar common to first-person animated videos—recurring simple
characters, quick visual reframes, reaction poses, visual exaggeration, and
occasional real memory inserts—without reproducing another creator's character
design or exact visual style.

## Production flow

```text
story-owner notes or manual story
-> optional light factual verification
-> first-person script with privacy and memory boundaries
-> conversational Edge neural narration and PCM-aligned native word boundaries
-> deterministic scene/cast cues for every narration beat
-> timeline review and approval
-> procedural Remotion cast + optional approved memory media
-> FFmpeg assembly, technical QA, and manual review
```

Narration audio is the master clock. `pipeline.timeline.planner` derives each
scene's mood, location, action, cast size, shot size, accent text, and variation
from an approved, timed narration beat. Those cues live under
`segment.overlays.data.storytime`, so rerenders and manual timeline edits remain
deterministic.

## Scene grammar

| Template | Purpose |
| --- | --- |
| `storytime_cold_open` | Begin inside the awkward problem or surprising consequence. |
| `storytime_establishing_doodle` | Establish a persistent place before the next action. |
| `storytime_character_stage` | Carry one action, reaction, or direct aside. |
| `storytime_dialogue_two_shot` | Stage supplied or explicitly remembered dialogue. |
| `storytime_imagination_burst` | Visualize an inner thought, fear, or comic exaggeration. |
| `storytime_memory_cutaway` | Show an approved photo, screenshot, object, or short source clip. |
| `storytime_motion_montage` | Compress repeated attempts or elapsed time. |
| `storytime_punchline_button` | Hold a reaction, callback, or precise closing observation. |

The procedural cast is rendered inside `StorytimeStory.tsx`; it does not need an
intermediate avatar video or PNG pose pack. `procedural_puppet` still runs through
the presenter stage so the canonical narration file, duration, and exact beat
windows are checked before composition.

## Channel-owned assets

Sidequest uses its own pinned conversational neural voice, separate from the
SynthPost, Meridian, and Beyond narrator profiles. `uv` runs the pinned
`edge-tts` package without modifying SynthPost's main virtual environment. The
default channel-owned voice is `en-US-AvaMultilingualNeural`; it can be changed
with `SYNTHEA_STORYTIME_TTS_VOICE_ID`.

The remaining expected channel asset is:

```text
assets/channels/storytime/outro.mp4
```

The outro may be generated as a channel-colored local placeholder by normal
assembly behavior. The Studio and compositor logo is
`compositor/remotion_renderer/public/brand/storytime_bug.svg`.

All defaults can be overridden with `SYNTHEA_STORYTIME_*` variables from
`.env.example`.

## Editorial boundaries

- Do not invent the story owner's trauma, relationships, identity details, or
  private facts.
- Treat remembered dialogue as reconstruction, not a verbatim transcript.
- Generalize identifying details about third parties when they do not matter.
- Prefer user-owned memory references; do not use other creators' animation
  frames, fan art, reaction GIFs, or reposted comics as production visuals.
- Humor should emerge from the event, timing, and the narrator's assumptions—not
  from targeting a vulnerable third party.
