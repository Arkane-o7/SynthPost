# dots.tts synthetic starter audition

This pack compares eight synthetic English reference timbres through the same
dots.tts voice-cloning path.

## Common text

Reference transcript:

> Every morning brings a new story, a fresh perspective, and another chance to
> understand the world around us.

Audition script:

> Welcome to SynthPost. Clear stories, natural rhythm, confident delivery, and
> warmth, every single day.

## Voices

| # | Candidate | English variety | Source voice | Demo | Compilation start |
|---|---|---|---|---|---|
| 1 | Samantha | United States | macOS Samantha | [WAV](demos/01-samantha-us.wav) | 00:00.00 |
| 2 | Reed | United States | macOS Reed | [WAV](demos/02-reed-us.wav) | 00:06.67 |
| 3 | Daniel | United Kingdom | macOS Daniel | [WAV](demos/03-daniel-uk.wav) | 00:15.27 |
| 4 | Flo | United Kingdom | macOS Flo | [WAV](demos/04-flo-uk.wav) | 00:22.58 |
| 5 | Aman | India | macOS Aman | [WAV](demos/05-aman-india.wav) | 00:31.58 |
| 6 | Tara | India | macOS Tara | [WAV](demos/06-tara-india.wav) | 00:38.25 |
| 7 | Karen | Australia | macOS Karen | [WAV](demos/07-karen-australia.wav) | 00:45.03 |
| 8 | Moira | Ireland | macOS Moira | [WAV](demos/08-moira-ireland.wav) | 00:52.83 |

Listen straight through with [the continuous comparison track](00-all-voices.wav).
There is 750 ms of silence between candidates.

Score each candidate from 1–5 for clarity, naturalness, authority, warmth, and
long-listening comfort. Pick the voice that still sounds good after several
sentences, not merely the one with the most striking first impression.

The source clips under `references/` are synthetic and contain no cloned human
identity. Final candidates under `demos/` use dots.tts SOAR with 10 sampling
steps, guidance scale 1.2, and seed 42. Audition masters are 48 kHz mono WAV,
normalized to -17 LUFS with a -1.5 dBTP ceiling.

These are starter timbres for evaluation, not voices bundled with dots.tts.
Once a candidate is selected, replace its synthetic reference with a
consented human performance if a more natural or emotionally specific anchor
voice is desired.
