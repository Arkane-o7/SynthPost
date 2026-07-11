# SynthPost Studio alpha end-to-end journey — 2026-07-11

## Test charter

- Surface: SynthPost Studio web UI at `http://127.0.0.1:5173/`
- Goal: create a polished approximately 10-minute news video from scratch.
- Method: operate the product through the in-app browser as an alpha user, record defects and recoveries, inspect the rendered output, and fix in-scope product defects.

## Journey log

### 1. Initial state

- Studio opened on an older Gaganyaan test project with a `script_generate` job showing `running` at 10% for roughly 17 minutes.
- The blocker panel retained two earlier structured-generation failures:
  - `intro must contain 84-157 words; got 51`
  - `cold_open must contain 63-117 words; got 27`
- This is not counted as the fresh production run, but is recorded as an alpha usability/reliability finding: an apparently stale running job and validator failures are visible without a clear recovery action on the current screen.

### 2. Fresh production setup

- Created project `Alpha E2E India Semiconductor Briefing 2026-07-11`.
- Created episode `India Semiconductor Ecosystem: The 2026 Reality Check`.
- Added and selected the custom topic `India's semiconductor push in 2026: fabs, advanced packaging, supply chains, and the gap between ambition and execution`.
- Research completed successfully and moved the story to `research_ready`.

### 3. Hosted script generation

- A 600-second Groq generation failed after three attempts with HTTP 429.
- Changed the production policy to the explicit hosted-only `hosted_fallback` provider: Groq first, Gemini second. No local LLM or Ollama fallback was introduced.
- The retry completed through Gemini. The structured script contained nine sections and an initial estimated duration of 491 seconds.
- Approved headline: `India's Semiconductor Ambition: A US$13.21 Billion Push with Mission 2.0`.
- Added a 45-second Groq request timeout so a hosted request cannot block a worker indefinitely.

### 4. Visual research and safety review

- The first visual job appeared stuck at `using AI to plan image/video keywords`; worker inspection showed that it had actually advanced to `yt-dlp` acquisition. The UI does not yet expose download/OCR substage progress.
- Search returned 39 candidates with one render-ready file. A second run at the corrected 1366x768 minimum returned 49 candidates with two render-ready files.
- Competing packages from News18, ANI, ET Now, Financial Express, Tribune, News9 and other publishers were rejected or quarantined by the source and frame-cleanliness gates.
- Approved a clean 1376x768 article image and the user-provided datacenter image. The timeline used the article image as a fullscreen news visual and presenter-led fallbacks elsewhere.
- The visual threshold now matches the requirement: landscape media above 720p (1366x768 minimum), while the final program remains 1080p.

### 5. Timeline and preview

- Generated and validated a nine-segment timeline.
- Initial edit duration: 491 seconds.
- Templates selected from presenter-led and fullscreen-news-visual layouts based on approved media availability; no rejected video reached the timeline.
- Remotion preview rendered successfully.

### 6. Production avatar failure and recovery

- The first Rocketbox production render failed at canvas frame 8,035 with `No space left on device`.
- Root cause: `avatar-engine/assets/temp/th_*` retained about 118 GiB of prior PNG-frame capture caches.
- Removed only disposable `th_*` render caches, restoring roughly 119 GiB of free space.
- Added a long-form disk-space preflight based on duration, frame rate and expected PNG size.
- Added automatic cleanup of temporary TalkingHead capture directories after success and, by default, after failure. Failed-temp retention can be opted into with `AVATAR_ENGINE_KEEP_FAILED_TEMP=1`.
- Retried from Studio. The production avatar completed at 1920x1080 with 12,939 frames; render time was about 348 seconds.

### 7. Composition and assembly

- Production composition completed with the real anchor render.
- Episode assembly completed successfully.
- Final output: 549.375 seconds (9:09), H.264 1920x1080 at 24 fps with AAC audio.
- Final file size: approximately 43 MiB.

### 8. Project/episode media isolation

- Removed the global `media_drop` discovery model.
- Each episode now owns `projects/<project_id>/episodes/<episode_id>/media_inbox`.
- Browser uploads are written into that inbox. An arbitrary local path entered in Studio is copied into `imports/<story_id>` before any analysis or staging.
- Episode rescans recurse only through the active episode inbox.
- Candidate listing now prioritizes the selected story so a completed production is not displaced by the 100-result discovery limit.
- Migrated the alpha episode's datacenter asset, preserved its approval record, removed the duplicate candidate, and removed the legacy shared folder.

### 9. Final QA

- Extracted representative frames at 12s, 220s, 455s and 535s into `qa-frames/`.
- Anchor, lower-third, typography, 1080p framing and fullscreen visual transitions render cleanly.
- Remaining taste issue: the single approved third-party semiconductor infographic has a synthetic/AI-illustrated look. It is attributed and is not SynthPost-generated, but a future synthetic-image aesthetic classifier should reject this style when the editor requests documentary photography only.
- Full Python suite: 63 tests passed.
- Studio TypeScript/Vite production build passed.
