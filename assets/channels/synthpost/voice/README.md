# SynthPost narrator profile

The local production voice is `loveena-kamath-subtle-deep-v2`. The enrolled
`.dtprofile` bundle is deliberately ignored by Git because it contains
biometric-like speaker data.

## Authorized source

- Speaker: Loveena Kamath
- Channel: Full Disclosure (`UCf_XYgupvdx7rA44Ap3uI5w`, handle
  `@FullDisclosure.` — note the trailing period)
- Source video: `https://www.youtube.com/watch?v=d4xIPSYolMg`
- Source window: `18:46.18`–`18:53.75`
- Reference format: 48 kHz mono PCM WAV, 7.57 seconds
- Exact transcript: `Now, I also know why people will still question, 'What
  now?' One education minister resigning will not make a big change. It will
  not solve any problems.`

The raw source audio stays under `.cache/voice-sources/` and is not committed.
Keep the separate proof of speaker permission with the production records; do
not place private consent documents or contact details in this repository.

For a very slightly deeper production register, the enrollment reference is
shifted down 0.55 semitones with its original tempo preserved. The resulting
test narration measured about 2.2% lower in median fundamental frequency than
the neutral profile, versus 1.9% for the previous subtle profile. The final
narration is not pitch-shifted after synthesis.

## Local profile

Expected path:

```text
assets/channels/synthpost/voice/loveena-kamath-subtle-deep-v2.dtprofile
```

Enrollment uses the local SOAR int4 dots.tts model and the reference above.
After provisioning the profile, `make doctor` should report `dots_tts` as
available. Published videos using this profile should disclose that the
narration is synthetic.
