# dots.tts narration, voice cloning, and expression

SynthPost owns text-to-speech. It generates one canonical 48 kHz mono WAV plus
sample-exact beat and section offsets. The timeline, Rhubarb lip sync, Avatar
Engine, Remotion composition, and final export all consume that same artifact.
Avatar Engine does not synthesize production narration when this canonical audio
exists.

The supported macOS path uses the `dots-tts-mlx` runtime with the SOAR int4
checkpoint by default. It runs natively through MLX on Apple Silicon. Upstream
dots.tts is Apache-2.0, and the MLX inference port is also Apache-2.0.

## Install the runtime and model

```bash
make setup-tts
```

This creates `.venv-dots-tts/` and downloads approximately 2.4 GB of ignored
model data to `.cache/dots-tts/int4/`.

The checkpoint is hosted on Hugging Face. If anonymous downloads stall or are
rate-limited, authenticate the dedicated environment and resume the same target:

```bash
.venv-dots-tts/bin/hf auth login
make setup-tts
```

The download is resumable; `make setup-tts` writes its ready marker only after
both the core and vocoder weight files exist.

SOAR int4 is the quality-first default and has the upstream project's best
voice-cloning performance. For roughly half the per-clip latency with a small
speaker-similarity tradeoff, download MeanFlow int4 instead:

```bash
make setup-tts DOTS_TTS_MODEL_VARIANT=mf-int4
```

Then set:

```dotenv
SYNTHPOST_TTS_MODEL_PATH=.cache/dots-tts/mf-int4
SYNTHPOST_TTS_MODEL_NAME=dots.tts-mf-mlx-int4
```

## Record a good reference

Only clone a voice you own or have explicit permission to synthesize.

Use a clean clip around 6–10 seconds:

- one speaker, no music, room echo, reverb, or background noise;
- natural connected speech, not isolated words;
- no clipped peaks or long silence at either end;
- WAV is preferred; 48 kHz mono is ideal, though the runtime can ingest common
  sample rates;
- write the exact transcript, including every spoken word. Transcript mismatch
  causes instability and word errors.

Do not use a two-minute sample. Longer references do not improve dots.tts and
consume more memory.

## Enroll a reusable voice profile

Enrollment performs the expensive reference encoding once and saves a small
`.dtprofile` bundle. It also lowers the memory peak for every later narration.

```bash
mkdir -p .cache/dots-tts/voices

.venv-dots-tts/bin/python -m dots_tts_mlx.cli \
  --model .cache/dots-tts/int4 \
  --enroll \
  --ref-audio /absolute/path/to/reference.wav \
  --ref-text "The exact words spoken in the reference clip." \
  --profile-out .cache/dots-tts/voices/anchor-neutral.dtprofile
```

Configure SynthPost:

```dotenv
SYNTHPOST_TTS_VOICE_ID=anchor-neutral
SYNTHPOST_TTS_VOICE_PROFILE_PATH=.cache/dots-tts/voices/anchor-neutral.dtprofile
SYNTHPOST_TTS_LANGUAGE=EN
SYNTHPOST_TTS_SPEED=1.0
```

Restart the API and workers after editing `.env`. Run `make doctor`; `dots_tts`
should report `available`. Regenerating narration will invalidate the old clock,
so regenerate and approve the timeline afterward.

For a quick audition before using the Studio:

```bash
.venv-dots-tts/bin/python -m dots_tts_mlx.cli \
  --model .cache/dots-tts/int4 \
  --profile .cache/dots-tts/voices/anchor-neutral.dtprofile \
  --text "Good evening. Here are the developments we are following." \
  --language EN \
  --out-path .cache/dots-tts/auditions \
  --out-prefix anchor-neutral
```

## Emotion and delivery

dots.tts does not expose a reliable categorical emotion or intensity argument.
Its expressive delivery is conditioned by the reference performance, the
written punctuation, and the random seed. `guidance_scale` is not an emotion
control, and the MeanFlow checkpoint ignores it because guidance is distilled
into the model.

The dependable workflow is a profile library recorded by the same authorized
speaker:

```text
anchor-neutral.dtprofile   measured newsroom read
anchor-serious.dtprofile   lower energy, restrained concern
anchor-warm.dtprofile      conversational, optimistic close
anchor-urgent.dtprofile    faster, firm breaking-news delivery
```

Record a separate 6–10 second reference in each delivery, enroll each one, and
switch `SYNTHPOST_TTS_VOICE_PROFILE_PATH` plus `SYNTHPOST_TTS_VOICE_ID`.
SynthPost currently applies one profile to an entire story. Per-beat profile
switching is deliberately not faked as an emotion slider; it needs a future
editorial style field and transition policy.

Other useful controls:

- `SYNTHPOST_TTS_SEED`: changes rhythm and intonation. Audition a few values and
  keep the selected seed for reproducibility.
- punctuation: commas, em dashes, short sentences, and question marks guide
  phrasing more naturally than bracketed emotion tags;
- `SYNTHPOST_TTS_SPEED`: pitch-preserving FFmpeg tempo adjustment. Keep it near
  `0.9–1.1`; extreme stretching sounds processed;
- `SYNTHPOST_TTS_NUM_STEPS`: leave empty for the checkpoint default. Increase
  SOAR steps only when an audition shows a real quality benefit.

Changing the voice profile, reference audio, reference transcript, model,
language, seed, speed, or sampler settings changes the narration input hash and
forces a fresh canonical WAV.

## One-shot cloning without enrollment

For experimentation, omit `SYNTHPOST_TTS_VOICE_PROFILE_PATH` and set both:

```dotenv
SYNTHPOST_TTS_REFERENCE_AUDIO=/absolute/path/to/reference.wav
SYNTHPOST_TTS_REFERENCE_TEXT=The exact words spoken in that file.
```

The story worker enrolls the reference once in memory and reuses it across the
story's beats. A saved profile is still preferred for lower repeated setup cost
and clearer voice/version management.

## Responsible use

High-fidelity cloning can enable impersonation. Keep proof of speaker consent,
do not clone public figures or third parties without authorization, restrict
access to raw references and profiles, and clearly disclose synthetic narration
in published output. A profile is biometric-like voice material even though it
is much smaller than the original recording.

Upstream resources:

- https://github.com/studio-dots-ai/dots.tts
- https://github.com/sb1992/dots-tts-mlx
- https://huggingface.co/shraey/dots-tts-mlx
