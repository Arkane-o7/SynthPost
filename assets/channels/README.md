# Synthea channel assets

Each channel owns its narrator and outro. Production never falls back to another
channel's voice, presenter, or outro.

Expected defaults:

```text
assets/channels/
  meridian/
    voice/meridian.dtprofile
    outro.mp4
  beyond/
    voice/beyond.dtprofile
    outro.mp4
```

Paths can be overridden with the `SYNTHEA_<CHANNEL>_TTS_*` and
`SYNTHEA_<CHANNEL>_OUTRO_PATH` variables documented in `.env.example`.

When an outro is absent, assembly creates a channel-colored local placeholder at
that channel's configured path. Narrator and presenter assets are stricter: a
production job stops with a configuration error instead of borrowing SynthPost's
identity.

Avatar Engine presenter assets live under `avatar-engine/assets/avatars/` because
its browser renderer resolves GLB and metadata paths from its own working tree.
