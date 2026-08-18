# Synthea channel assets

SynthPost owns its narrator and outro. Production never borrows another
identity's voice, presenter, or outro.

Expected defaults:

```text
assets/channels/
  synthpost/
    voice/loveena-kamath-subtle-deep-v2.dtprofile
```

Paths can be overridden with the `SYNTHEA_<CHANNEL>_TTS_*` and
`SYNTHEA_<CHANNEL>_OUTRO_PATH` variables documented in `.env.example`.

When an outro is absent, assembly creates a SynthPost-colored local placeholder
at the configured path. Narrator and presenter assets are stricter: a
production job stops with a configuration error instead of borrowing SynthPost's
identity.

Avatar Engine presenter assets live under `avatar-engine/assets/avatars/` because
its browser renderer resolves GLB and metadata paths from its own working tree.
