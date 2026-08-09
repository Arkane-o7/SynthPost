# Synthea channel assets

Each channel owns its narrator and outro. Production never falls back to another
channel's voice, presenter, or outro.

Expected defaults:

```text
assets/channels/
  synthpost/
    voice/loveena-kamath-subtle-deep-v2.dtprofile
  meridian/
    presenter/
      character.json
      poses/
        neutral.png
        speaking.png
    voice/meridian.dtprofile
    outro.mp4
  beyond/
    voice/beyond.dtprofile
    outro.mp4
  storytime/
    voice/storytime.dtprofile
    outro.mp4
```

Paths can be overridden with the `SYNTHEA_<CHANNEL>_TTS_*` and
`SYNTHEA_<CHANNEL>_OUTRO_PATH` variables documented in `.env.example`.

When an outro is absent, assembly creates a channel-colored local placeholder at
that channel's configured path. Narrator and presenter assets are stricter: a
production job stops with a configuration error instead of borrowing SynthPost's
identity.

Meridian uses the `png_puppet` presenter provider. Its original analyst artwork
is stored as transparent neutral and speaking poses. The presenter stage pins
that character pack to the channel's canonical narration WAV, and Remotion
switches mouth poses from dots.tts exact speech windows. No per-episode avatar
video is generated.

Sidequest uses the `procedural_puppet` presenter provider. Remotion draws its
original line-character cast directly from deterministic mood, action, location,
and framing cues stored in the approved timeline. There is no intermediate
avatar movie or pose pack; the canonical narration WAV remains the master clock.
User photos and approved reference media can still appear through the channel's
memory-cutaway template. Production narration requires the channel-owned dots.tts
profile above (or explicit reference audio/text overrides).

Avatar Engine presenter assets live under `avatar-engine/assets/avatars/` because
its browser renderer resolves GLB and metadata paths from its own working tree.
