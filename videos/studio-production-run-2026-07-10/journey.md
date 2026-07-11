# SynthPost Studio Production Run — 2026-07-10

## Objective

Run one complete production story through SynthPost Studio using the in-app browser, including research, scripting, visual discovery, editorial approval, timeline, render, assembly, and visual QA. Fix blocking issues encountered during the run.

## Environment baseline

- Studio API was reachable on `127.0.0.1:8765`.
- Vite Studio was reachable on `127.0.0.1:5173`.
- Two background workers were running concurrently.
- Existing browser logs contained a React `useStudio must be used inside StudioProvider` hot-reload crash.
- Docker Desktop was installed but not operational; its active context pointed to a stopped OrbStack socket and Desktop required macOS administrator authorization.
- No SearXNG service was listening on port `8888`.

## Journey

### 1. Stabilize the local stack

The existing long-running backend/frontend processes predated the SearXNG implementation and the UI had entered a broken hot-reload state. A clean restart was required before using Studio for production work. Duplicate workers were removed to preserve single-claim job semantics.

Fixes/actions:

- Created an isolated Python 3.12 runtime under `.synthpost/runtime-venv` because the committed `.venv` pointed to a Python installation that had been moved to Trash.
- Restarted the API, worker, and Vite frontend with exactly one worker.
- Verified the Studio loaded without the previous React provider crash.
- Fixed the live job event stream. `/api/jobs/events` was shadowed by the earlier dynamic `/api/jobs/{job_id}` route, so Studio never received completion events and stayed visually stuck on queued jobs. The stream now uses the unambiguous `/api/job-events` route.

### 2. Activate private SearXNG

Public SearXNG instances returned rate limits for JSON automation, and Docker Desktop remained blocked by a macOS privilege prompt. The official SearXNG repository was therefore installed into ignored local runtime directories under `.synthpost/` and started on `127.0.0.1:8888` using the repository's JSON-enabled settings.

Live validation query: `India AI technology news` returned 63 results with zero unresponsive engines.

### 3. Editorial selection

Ran Studio's **Refresh Discovery** action through the browser. The worker ingested 240 feed candidates; the Studio displayed the top 100.

Selected story:

- **India’s first hydrogen train to launch soon: Check route, stops, timetable, speed and features**
- Publisher: Indian Express
- Category: India
- Freshness: approximately two hours
- Editorial rationale: strong India relevance, practical public-interest angle, naturally visual subject, and enough technical detail for a concise explainer.

### 4. Research and script generation

SearXNG expanded the lead article into a five-document pack using Indian Express, News18, India TV, CNBC-TV18, and an MSN lead. The sources converged on the Jind–Sonipat route, July 17 launch expectation, hydrogen fuel-cell technology, and the pilot-project framing.

The first AI script job exposed two provider failures: Groq returned HTTP 403 and Gemini returned repeated 503 high-demand errors. The repository still documented Ollama as a supported local provider, but the current provider registry had accidentally removed its implementation. Restored the Ollama structured-JSON provider and selected the local `gemma4:31b-mlx` model for the production script.

The 31B model remained healthy on GPU but did not complete the oversized prompt after eleven minutes. Inspection found two pipeline problems rather than a model-quality problem:

- The prompt included complete scraped HTML-derived article bodies plus hundreds of noisy entity strings, duplicating the already extracted claims and evidence.
- The short-script section planner applied nine long-form minimums to a 90-second target, producing an impossible negative word target for `key_developments`.

Fixed both issues by compacting the prompt to source metadata, claims, evidence, dates/numbers, and capped entities; and by using a six-section short-form pacing model whose word targets remain positive and sum to the requested duration. Switched runtime generation to local `qwen3.5:9b` for a better quality/latency balance. Also fixed script-job cancellation so the story returns from `script_generating` to `research_ready` cleanly.

Qwen then returned schema-valid JSON in Ollama's `thinking` field while leaving `response` empty. The provider had discarded that field and reported a JSON parse error. Updated it to accept `response` or, for reasoning-capable models, `thinking`; added regression coverage for this Ollama response shape.

The corrected local generation completed in 34 seconds. I edited the six-section narration in Studio to remove repetition, qualify the expected launch date, and add the operational questions that matter after the ceremony. The final draft is approximately 87 seconds. Studio's manual-save path initially erased claim IDs, source IDs, and visual queries, so it was fixed to preserve structured provenance and section identity across human revisions. The polished revision retained five research documents and its linked claims before browser approval.

### 5. Visual discovery and editorial review

Approving the script automatically launched Studio's SearXNG visual search. It completed despite partial upstream failures (including public-engine 403/429/502 responses), producing both image downloads and video research leads.

The live run exposed and fixed several causes of weak or missing coverage:

- Query allocation was section-major, exhausting the budget on early sections. It now assigns one query per section before secondary queries.
- The local runtime query cap was raised from four to six so all six narration sections receive research.
- Obvious off-topic engine results were admitted without a lexical relevance check. They are now filtered before staging.
- Re-running search duplicated local drop-folder media. Local asset IDs are now deterministic.
- A single unrelated local file suppressed all generated fallbacks. Studio now creates a rights-safe local fallback for every section regardless of web-search success.
- Attribution editing used an uncontrolled input and approval resent stale values. It is now controlled and the exact editor-entered attribution is persisted.
- Rejected assets were incorrectly counted as blockers. Rejected/blocked states are now excluded from actionable rights warnings.

Through the browser I visually inspected the downloaded candidates, approved five relevant images with source labels, reassigned two to the narration sections they actually explain, initially retained the generated card for the uncertainty section, and rejected the remaining 24 leads. Rejections included conflicting January launch claims, unrelated software/AI tutorials, unlicensed video-only leads, and repeated server-rack media.

### 6. Timeline and preview QA

Studio generated a six-segment, 87-second timeline. Every segment mapped to an approved visual, the validator returned no errors, and the timeline was approved in the UI.

The Preview panel claimed it could render but only rebuilt a manifest. Added an explicit **Render Preview** action that queues the same Remotion story composition in placeholder-safe preview mode. The first real preview completed in about 22 seconds at 1280×720/15 fps.

Frame QA found two on-screen issues and both were corrected before production:

- The lower-third preferred a mid-word-truncated chyron, displaying “WILL T”. It now prefers the full lower-third headline and displays “WILL TEST”.
- Visuals were labeled with the internal SearXNG provider instead of the editor-approved source. Renderer source labels now prioritize `attribution_text` (for example, `FINANCIAL EXPRESS`).

Generated editorial cards also use `contain` instead of a destructive split-panel crop. A second preview render confirmed full headline text and curated source attribution across extracted frames at six points in the story.

### 7. Production render

The production story render completed through the real local avatar path: Kokoro voice synthesis (`af_heart`, speed 1.1), Rhubarb lip-sync analysis, Rocketbox avatar rendering, and Remotion composition. The narration/anchor master is 91.025 seconds and the composed story is 1920×1080 at 24 fps. A later visual-attribution rebuild correctly reused the fresh avatar rather than rerendering it; visual-only manifest changes no longer invalidate the expensive avatar stage.

The approved timeline was hydrated with the current visual-candidate metadata before render. This fixed a subtle stale-data problem where the selected image was correct but its earlier attribution/path could remain embedded in the approved timeline. Final frames show the editor-approved labels, including `TIMES OF INDIA`, `FINANCIAL EXPRESS`, `INDIAN RAILWAYS REPORT`, and `ADDA247 CURRENT AFFAIRS`.

### 8. Episode assembly and audio mastering

Studio assembled the production story with the ten-second SynthPost outro. Audio analysis of the first master found acceptable integrated loudness but a 0.0 dBFS true peak caused by one-pass normalization of the highly dynamic outro. The assembly chain was revised to retain the −16 LUFS target while applying a conservative post-normalization limiter and a versioned normalization cache. The final audio-safe assembly measured:

- Integrated loudness: **−16.1 LUFS**
- Loudness range: **2.9 LU**
- True peak: **−2.2 dBFS** after final post-concat limiting and narration restoration
- Audio: AAC, 48 kHz, stereo

The final master is 101.1667 seconds, H.264, 1920×1080, 24 fps, and 11.18 MB. Representative frames plus an outro frame were extracted from this exact master and visually reviewed.

### 9. Production-state integrity fixes

The final reload exposed another persistence bug: rediscovering the same deterministic candidate ID overwrote its selected episode, story ID, and completed workflow state with a fresh `suggested/discovered` record. Studio consequently showed “No story selected” even though the production files existed. Candidate upserts now refresh editorial metadata while preserving a prior selected or rejected decision, episode/story linkage, workflow progress, rejection reasons, manual body, and original discovery timestamp. A regression test reproduces the collision.

The episode also contained one stale historical story ID with no candidate or manifest. Metadata was corrected to the one story actually produced. Assembly now follows the episode's explicit `story_ids` and fails clearly when any selected story manifest is missing instead of silently assembling a partial episode from whatever directories happen to exist.

After repair, the Studio browser showed the hydrogen-train story as `completed`, the episode as `completed`, the render profile as `production`, every stage checked, no active jobs, and the newest assembly job completed “just now.” The in-app Studio tab was left open on this deliverable state. The last audio-safe reassembly was submitted directly to the same local Studio API after the automated UI click did not transmit a second request; all editorial and production stages, including the earlier production assembly, were exercised through the browser.

### 10. Final verification

- Python: **48 tests passed**
- Studio frontend: **TypeScript compile and Vite production build passed**
- Remotion compositor: **TypeScript typecheck passed**
- Video probe: **H.264 1920×1080/24 fps + AAC 48 kHz stereo**
- Audio meter: **−16.2 LUFS integrated, −2.2 dBFS true peak**
- Visual QA: headline fit, anchor framing, source attribution, presenter-only fallback, outro, and segment changes reviewed across the final master

The five web-sourced images remain yellow-tier assets that required explicit manual approval. Their relevance and on-screen attribution were checked, but publication rights still require the publisher/asset owner's normal licensing review before public distribution.

### 11. Remove synthetic fallback imagery

A later review identified that the uncertainty section looked like an AI-generated amalgam. The source was not an image model: SynthPost itself generated a full 1920×1080 SVG containing the headline, section narration, section label, and “LOCAL GENERATED VISUAL.” The split-screen renderer then treated that SVG as a normal sourced image and added another attribution and lower third, producing the nested repetition.

The fallback contract was replaced rather than cosmetically restyled:

- Automatic fallbacks are now semantic `fallback/fallback` records with no media path.
- They always select a presenter-only anchor layout: `fullscreen_anchor` for intentional direct-address beats and `fallback_anchor` for purely missing-media cases.
- They carry no source attribution because no external or generated image is displayed.
- Real approved media is ranked ahead of fallbacks for the same section.
- Manifest hydration converts legacy generated-card selections to anchor-only fallbacks, repairing already approved timelines.
- Studio labels these entries “Presenter-only fallback” and no longer presents them as renderable images or research leads.

The hydrogen-train story and episode were rerendered. Frame QA at 72 seconds confirmed that the nested generated card, duplicate paragraph, and “SYNTHPOST GENERATED VISUAL” label are gone. The replacement shows the presenter on the restrained newsroom background with the single established lower third.

### 12. Add editorial intelligence to template selection

The original planner only used three branches: primary video became `fullscreen_news_visual`, missing media became an anchor fallback, and every approved image became `split_anchor_visual`. It did not consider editorial purpose or pacing.

The replacement `editorial_v1` policy scores the three production-safe layouts using section type, media type and content role, relevance and visual-quality scores, aspect ratio, narration density, opening/closing position, and the previously selected layouts. It penalizes immediate repetition and prevents any layout from running more than twice consecutively. Scores and reasons are stored in each timeline segment under `overlays.data.template_selection` for editorial inspection.

The approved hydrogen-train timeline now resolves to:

1. Cold open — `fullscreen_anchor`
2. Context — `split_anchor_visual`
3. Key developments — `fullscreen_news_visual`
4. Why it matters — `split_anchor_visual`
5. Uncertainty — `fullscreen_anchor`
6. Conclusion — `fullscreen_news_visual`

Frame QA at the midpoint of every segment confirmed that the intended compositions render correctly. The final episode was rebuilt after this timeline change.

### 13. Preserve narration under fullscreen visuals

Fullscreen news visuals previously removed the visible anchor video component and inadvertently removed its embedded narration audio at the same time. The timeline still declared `narration`, but the renderer had no audio-bearing anchor layer in that composition.

The audio contract now records whether each video actually contains an audio stream. Fullscreen images and silent videos keep a synchronized invisible anchor-narration track. Only an audible fullscreen video selects `source` mode and suppresses anchor narration; split layouts continue using narration with supporting media muted. The renderer also refuses to unmute source media unless both the timeline mode and probed audio metadata allow it.

The story and episode were rerendered. The two fullscreen image sections measured mean levels of −19.4 dB and −19.3 dB in the assembled master, with no detected silence interval. Regression coverage checks images, silent video, audible video, and split-layout behavior.

### 14. Repair video-footage research and acquisition

The visual researcher was effectively prevented from producing clips. Runtime configuration disabled video downloads, allowed only one video result per query, and pointed at a `yt-dlp` executable whose Python interpreter no longer existed. Image and video search also reused the same generic query, so abstract still-image terms produced weak watch-page results and a failed first download exhausted the section budget.

Visual research now creates a media-specific plan for every section: the first query seeks a concrete still/diagram/map and the second seeks exact event/person/location footage. Video acquisition is prioritized for motion-directed sections and major structural beats, searches deeper than the final result allowance, does not let a failed download immediately consume the usable-media slot, and is bounded by per-job and per-clip limits. Relevance filtering now requires stronger multi-token agreement instead of accepting one generic word. Future script generation explicitly requests both query intents.

The runtime now uses a working project-local `yt-dlp` and SearXNG listens on the configured port 8888. A live search for the hydrogen-train story downloaded a 21.021-second H.264/AAC vertical clip to the story media library, proving the end-to-end footage path. Frame review found broadcaster packaging and potentially illustrative rather than event-authentic train imagery, so the candidate correctly remains yellow-tier and `suggested`, not approved or inserted into the production timeline. Download success is intentionally not treated as editorial or rights approval.

Final verification after the footage changes: **51 Python tests passed**, the Studio production build passed, the Remotion TypeScript check passed, and video thumbnail extraction completed without FFmpeg image-sequence warnings.

### 15. Put AI in front of visual search

Visual search no longer treats search phrases stored during script generation as the primary planner. Immediately before SearXNG, the configured structured AI provider now receives the story topic, approved headline, section narration, linked claim text, and verified people, organizations, locations, and dates. It must return one distinct image query and one footage query for every section, plus a motion-priority decision and rationale. Schema and semantic validation reject omitted sections, duplicate queries, unsupported years, identical image/video intent, and impractical query lengths. Legacy script queries are deliberately excluded from factual grounding; they remain available only through an explicit `SYNTHPOST_AI_VISUAL_QUERY_PLANNING=0` fallback.

The old `SYNTHPOST_SEARXNG_VISUAL_MAX_QUERIES=6` limit was also corrected. It previously capped six internal section plans, each of which could make two searches, so the name did not describe the real behavior. It now caps actual SearXNG requests. Production is configured to 12, allowing one image and one video search for each section in the common six-section format. With a smaller cap, the allocator covers every section's preferred media type before using remaining requests for the secondary type.

A live end-to-end check generated a grounded Narendra Modi/Jind hydrogen-train photo query and a distinct flag-off footage query, then sent both to the local SearXNG instance. SearXNG returned relevant inauguration image results and a relevant hydrogen-train launch video result. An unrelated second video result demonstrates why result-level relevance filtering remains necessary after AI keyword generation.

Verification after this change: **52 Python tests passed**.

### 16. Enforce broadcast-shaped, HD visual media

The retained renderer uses two different landscape canvases: the split visual panel is 1300×860 (approximately 3:2), while fullscreen news visuals use the 1920×1080 composition (16:9). Visual research now tells the AI to request horizontal 1080p media near those shapes. Video acquisition asks `yt-dlp` only for formats at least 1920×1080 inside the accepted aspect band and enables its Node JavaScript runtime so higher-quality YouTube formats are visible.

Every downloaded image and video is probed again. The default broadcast-fit gate requires at least 1920×1080 and an aspect ratio between 1.312:1 and 1.978:1, covering the two renderer targets with a configurable 0.20 tolerance. Passing media receives a quality score based on resolution and distance from the target ratios. Portrait, undersized, unknown-dimension, or extreme-aspect downloads are deleted as render files but retained as non-renderable research leads where possible. Discovery searches past those failures instead of letting them consume the usable-result allowance. Approval and timeline selection apply the same gate, including to older candidates.

A live `yt-dlp` simulation selected a 3840×2160 16:9 format. Unit coverage accepts 1920×1080 and 1920×1280 media while rejecting 1080×1920 portrait and 1024×576 low-resolution assets. An audit found that the five web images previously approved for the hydrogen-train production do not meet the new standard; they remain in editorial history but will be excluded from any regenerated timeline until replaced with HD landscape candidates.

Verification after this change: **53 Python tests passed** and the Remotion TypeScript check passed.

### 17. Live HD-landscape visual research test

Studio queued visual-search job `job_f1edb796708c` for the hydrogen-train story. The worker exercised the structured AI keyword planner, the full 12-request SearXNG budget, image probing, and two bounded video downloads. It completed in 2 minutes 33 seconds with 35 returned candidates and five local files reported render-ready. Four were web results that passed the gate: one 1920×1080 image, two 1920×1080 45-second videos with audio, and one 2500×1875 image. Fourteen other downloads were rejected for sub-1080p resolution or unsuitable aspect ratio.

Frame review found both videos relevant and authentic-looking hydrogen-train news coverage, but with prominent Mint or TOI Bharat branding and lower-thirds. The uncertainty image usefully shows railway hydrogen-refuelling equipment but is from a UK demonstration. All remain yellow-tier suggestions; nothing was automatically approved or added to the production timeline.

The fifth technically valid local file was an unrelated datacenter image from the generic `media_drop` directory. Testing exposed that unscoped local files were automatically attached to every script section. The staging rule now leaves generic drop-folder media unassigned unless an editor or source integration supplies section IDs. The existing datacenter candidate was corrected to an empty section assignment and remains suggested.

Detailed results and QA frames are stored in `videos/studio-production-run-2026-07-10/visual-gate-test-2026-07-11/`.

### 18. Source identity and editorial-cleanliness quarantine

The HD test demonstrated that technical quality did not prevent finished Mint and TOI Bharat packages from entering the suggestion pool. SynthPost now requests official/raw/B-roll footage instead of news coverage; performs a metadata-only `yt-dlp` preflight; blocks known competing publisher channels before download; samples seven full-resolution frames; records OCR regions and persistent overlays; creates contact sheets; and sends bounded deterministic evidence to a structured AI cleanliness classifier. Deterministic publisher and overlay blockers cannot be overridden by the AI.

Cleanliness states, source identity, channel metadata, detected brands, scan timestamps, OCR evidence, contact sheets, clean-B-roll score, AI reasons, and approval blockers persist on each visual. Uncertain and rejected media retains only a quarantine path. Approval, timeline selection, timeline validation, and manifest hydration all independently require a clean pass.

The two motivating clips were rescanned live. Mint was identified as the uploader and TOI as The Times of India. Both are now `rejected`, red-tier, and `blocked`; both lost their renderable paths while retaining quarantined files and seven-frame contact sheets. Studio exposes this evidence and disables approval. Full implementation documentation is in `docs/video-source-cleanliness.md`.

Verification after the quarantine implementation: **56 Python tests passed**, the Studio production build passed, and the Remotion TypeScript check passed.
