# SynthPost Studio Full Production Run — Final Report

## Outcome

The full Studio production run completed successfully. The result is a 101.17-second 1080p narrated news explainer about India's Jind–Sonipat hydrogen-train pilot, using the real Kokoro/Rhubarb/Rocketbox avatar pipeline, curated SearXNG research visuals, a six-section approved timeline, and the SynthPost branded outro.

Final master: `episodes/ep_2d9ff247cc07/final.mp4`

Story master: `episodes/ep_2d9ff247cc07/stories/story_01a8fe15cc70/composited.mp4`

## Editorial result

- Story: **India’s first hydrogen train to launch soon: Check route, stops, timetable, speed and features**
- Final headline: **India’s First Hydrogen Train: What the Jind–Sonipat Pilot Will Test**
- Source lead: Indian Express
- Format: concise six-part explainer covering launch expectation, route, technology, public value, operational uncertainty, and what the pilot can prove
- Voice: Kokoro `af_heart`, speed 1.1
- Visual plan: five manually approved relevant web images plus one presenter-only safe fallback; no generated image is rendered
- Rejected visual leads: 24 irrelevant, contradictory, repeated, or unsuitable results

The output has a consistent anchor/visual split, full lower-third headline, restrained newsroom palette, readable attribution, and visual changes aligned to the narration sections. The final visual review sampled frames at 2, 25, 52, 82, and 96 seconds.

## Technical master

| Property | Result |
|---|---|
| Container/video | MP4, H.264 |
| Resolution | 1920×1080 |
| Frame rate | 24 fps |
| Duration | 101.1667 s |
| File size | 11,175,367 bytes |
| Audio | AAC, 48 kHz, stereo |
| Integrated loudness | −16.2 LUFS |
| Loudness range | 2.9 LU |
| True peak | −2.2 dBFS |

## Main production issues fixed

1. **SearXNG research and visuals** — added a shared private SearXNG client, news research expansion, image/video discovery, settings, runtime configuration, and UI visibility.
2. **Missing/stale Studio job updates** — moved the SSE stream away from the shadowed dynamic jobs route.
3. **LLM generation failures** — hardened hosted structured generation, compacted oversized prompts, repaired short-form word allocation, and later removed local production providers entirely.
4. **Human script edits losing provenance** — manual saves now retain section identity, claim/source links, visual queries, and editorial metadata.
5. **Uneven visual coverage** — queries are allocated round-robin across sections; every section receives a deterministic local fallback.
6. **Poor visual relevance and duplicate assets** — added lexical relevance filtering and deterministic local asset IDs.
7. **Approval/attribution bugs** — fixed controlled attribution editing, stale approval payloads, blocker accounting, and renderer source-label priority.
8. **Preview not actually rendering** — added a real Remotion preview action.
9. **Headline crop and synthetic fallback nesting** — full lower-third text is preferred; automatic fallbacks now use the presenter-only broadcast layout instead of rendering a generated headline/paragraph SVG inside another template.
10. **Unnecessary avatar rerenders** — visual-only manifest changes no longer invalidate a fresh avatar render.
11. **Stale approved-timeline metadata** — current approved visual path, attribution, and rights metadata are hydrated into the renderer manifest.
12. **Audio peak overshoot** — added versioned clip normalization plus a final post-concat limiter; final true peak is −2.2 dBFS.
13. **Rediscovery erasing selected/completed stories** — candidate upserts now preserve editorial and workflow state on deterministic-ID collisions.
14. **Silent partial episode assembly** — assembly now follows explicit episode story IDs and reports missing selected-story manifests.
15. **Fallbacks outranking real media** — real approved images and clips are ranked ahead of automatic fallbacks; legacy generated-card selections are normalized to anchor-only segments at manifest build time.
16. **Monotonous template selection** — replaced the image→split hardcode with an auditable editorial scorer using section purpose, media role/type, relevance, quality, aspect ratio, narration density, opening/closing position, and recent shot history.
17. **Narration disappearing under fullscreen visuals** — fullscreen images and silent clips now retain an invisible synchronized anchor-narration track; source audio replaces narration only when the selected fullscreen video actually contains audio.
18. **No render-ready video clips** — enabled bounded video acquisition, repaired the broken `yt-dlp` runtime, split still and footage query intent, prioritized motion-worthy sections, searched beyond failed results, and strengthened relevance filtering.
19. **Static/stale visual keywords** — added a structured AI keyword-planning stage directly before SearXNG, grounded it in linked claims and verified entities, and changed the visual query limit to count actual search requests.
20. **Low-resolution and portrait visual candidates** — added AI landscape/1080p direction, strict `yt-dlp` format selection, post-download dimension probing, approval/timeline broadcast-fit gates, and deeper searching past rejected media.
21. **Generic local media contaminating every section** — unscoped drop-folder assets now remain unassigned until an editor or source integration maps them instead of being attached to all script sections.
22. **Competing broadcaster packages passing technical checks** — added primary-source AI queries, channel/uploader metadata preflight, quarantine paths, seven-frame OCR/contact-sheet analysis, structured AI cleanliness decisions, Studio evidence, and fail-closed approval/timeline enforcement.
23. **Local LLM quality ceiling for long-form scripts** — removed the local production provider, all of its configuration/UI/documentation paths, and implicit provider selection; production now permits Groq, Gemini, or explicit hosted-only Groq→Gemini failover.
24. **Groq Cloudflare 1010 rejection** — added an explicit SynthPost application user-agent and JSON Accept header; independent live schema calls now pass on both Groq and Gemini.

## Verification

- 60 Python tests passed.
- Studio TypeScript compilation and Vite production build passed.
- Remotion compositor TypeScript typecheck passed.
- Final video/audio streams were verified with `ffprobe`.
- Final loudness and true peak were measured with FFmpeg EBU R128 analysis.
- Representative frames from the exact final master passed visual inspection.
- Studio finished with the selected story and episode both marked `completed`, production profile selected, all eight stages checked, and no active jobs.

## Publication caveat

The five web-sourced visuals are yellow-tier/manual-approval assets. They were checked for editorial relevance and carry on-screen source attribution, but attribution is not a substitute for a publication licence. Confirm reuse rights with each publisher or replace them with licensed/owned equivalents before public release. The uncertainty section uses only the owned presenter/avatar and SynthPost broadcast shell.

The repaired footage path also produced one local hydrogen-train video candidate. It remains yellow-tier and suggested because visual inspection could not establish that all train imagery was authentic event footage or licensed for reuse. It was therefore not silently inserted into the final master.
