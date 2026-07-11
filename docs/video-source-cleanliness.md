# Video Source and Editorial-Cleanliness Pipeline

## Policy

SynthPost may discover any video as a research lead. It may render a video only
when all of these independent gates pass:

1. The source is not a known competing news publisher.
2. The file meets the broadcast resolution/aspect contract.
3. Deterministic frame analysis finds no competing brand or persistent package.
4. The structured AI cleanliness classifier returns `pass`.
5. A human confirms relevance, attribution, and usage rights.

Attribution never converts a competing publisher package into acceptable B-roll.
Rejected and uncertain files remain in quarantine for evidence review and do not
have a renderable `download_path`.

## 1. AI primary-source query planning

The visual keyword planner receives the topic, approved headline, narration,
linked claims, and verified entities. For every section it returns a distinct
image query and video query. Video instructions now require terms such as
`official video`, `raw footage`, `B-roll`, or `press footage`, preferably naming
the responsible ministry, agency, event operator, company, or press office.

The prompt explicitly prohibits `news coverage`, `breaking news`, `news report`,
`explainer`, and finished broadcaster packages. The deterministic fallback also
removes those phrases from legacy stored queries and appends `official raw
footage`, so an older script cannot silently restore the old search behavior.

This improves discovery but is not a security boundary. Search engines may still
return broadcaster packages, so every later gate remains mandatory.

Implementation: `pipeline/visuals/providers.py` (`_video_query`,
`_visual_search_plan`) and `pipeline/scripts/generation.py`.

## 2. Metadata preflight before video download

Before acquisition, SynthPost runs `yt-dlp --skip-download
--dump-single-json`. It retains only bounded provenance fields such as channel,
channel ID, uploader, source URL, extractor, licence, duration, dimensions,
categories, and tags.

Source classification uses exact channel IDs and editor-maintained name fragments
before heuristic phrases. The configurable registries are:

- `SYNTHPOST_VIDEO_APPROVED_CHANNEL_IDS`
- `SYNTHPOST_VIDEO_APPROVED_SOURCE_NAMES`
- `SYNTHPOST_VIDEO_BLOCKED_SOURCE_NAMES`

Built-in known publisher phrases identify common competing news brands. Built-in
official phrases recognize likely primary sources such as Indian Railways, the
Ministry of Railways, PIB India, and PMO India. “Official” is a source class, not
a licence grant; it still requires human rights review.

Known competing publishers are marked `news_broadcaster`, red-tier, blocked, and
rejected before download. Failed metadata preflight also fails closed instead of
blindly downloading an unidentified watch page. Unknown non-broadcaster sources
may be downloaded only into the content-analysis quarantine. Even when their
frames look clean, an unknown video identity remains an approval blocker until
the channel/source is added to the approved registry. This prevents clean-looking
reuploads from bypassing source provenance.

Implementation: `pipeline/visuals/content_analysis.py` (`probe_video_source`,
`assess_video_source`) and `_stage_searxng_result` in the provider.

## 4. Automated representative-frame scan

A 45-second video produces seven samples at approximately 2%, 10%, 25%, 50%,
75%, 90%, and one second before the end. Images produce one analysis frame.
Frames are full-resolution JPEGs so OCR is not run on thumbnails.

Tesseract returns word-level text, confidence, and bounding boxes. SynthPost
normalizes each word and classifies it into top-left, top-right, scene,
lower-third, or bottom-ticker regions. Text repeated in the same screen region
across at least 35% of samples (minimum two) is treated as persistent overlay
evidence rather than ordinary physical scene text.

Known broadcaster brand text is a hard blocker even if it appears in only one
high-confidence sample. Repeated lower-region text produces lower-third/ticker
blockers. A contact sheet combines all samples for rapid human inspection.

The machine checks every sample. A human normally reviews only the contact sheet
for the few candidates that survive or need an exception decision. The original
clip is played only when selecting the final trim or investigating ambiguity.

Implementation: `extract_representative_frames`, `_ocr_frame`, `_region`, and
`_contact_sheet` in `pipeline/visuals/content_analysis.py`.

## 8. Structured AI cleanliness classifier

The configured SynthPost LLM receives only bounded source metadata and
deterministic evidence. It does not receive permission to invent unseen visual
facts. It returns validated JSON containing:

- `decision`: `pass`, `reject`, or `needs_review`
- `clean_broll_score`: 0.0–1.0
- `contains_presenter_package`: boolean
- evidence-based reasons

The deterministic blockers are authoritative. An AI `pass` cannot override a
known publisher channel, detected brand, lower-third, or ticker. AI failure,
disabled AI, invalid JSON, or uncertainty produces `needs_review`, which has no
renderable path and cannot be approved. The classifier therefore operates as a
second opinion and explanation layer, never as the sole safety gate.

The current provider interface is text/JSON, so this version classifies source
metadata plus OCR/persistence evidence rather than raw pixels. Graphical-logo
embeddings and dedicated presenter vision detection remain later hardening work.

Implementation: `_ai_classify`, `_validate_ai_result`, and
`analyze_media_cleanliness` in `pipeline/visuals/content_analysis.py`.

## 13. Studio evidence panel

Every visual card now shows three independent states: rights tier, editorial
review state, and cleanliness state. The evidence panel includes:

- source class and source identity
- channel name and registry verification
- dimensions
- clean-B-roll score
- number of sampled frames
- detected brands
- logo/lower-third/ticker/presenter flags
- AI and deterministic reasons
- approval blockers
- generated contact sheet

Files in quarantine show a red quarantine banner. The Analyze action rescans an
existing local or quarantined file. Approve is disabled unless the cleanliness
status is exactly `passed`, `download_path` exists, and `approval_blockers` is
empty. Rights confirmation remains a separate human action.

Implementation: `web/src/workspace/VisualsPanel.tsx`, the API endpoint
`POST /api/visuals/{asset_id}/analyze`, and the TypeScript visual contract.

## Persisted states and enforcement

Content cleanliness is one of:

- `not_scanned`: no usable decision; blocked
- `needs_review`: uncertain or analysis unavailable; quarantined and blocked
- `passed`: eligible for separate relevance/rights approval
- `rejected`: competing package or hard blocker; red-tier and blocked

The same rule is repeated in `approve_visual`, timeline candidate selection,
timeline validation, and manifest hydration. This prevents stale approved
timelines or direct API calls from bypassing the Studio button state.

## Current limitations

- OCR reliably catches readable publisher marks but cannot guarantee detection
  of every purely graphical or heavily stylized logo.
- Presenter/package detection is evidence-based AI inference, not a dedicated
  face/studio vision model yet.
- Sampling uses seven time-distributed frames; scene-change-triggered samples are
  a recommended next enhancement for long or heavily edited clips.
- Official-source classification does not determine copyright or reuse rights.
- The approved and blocked channel registries require editorial maintenance.
