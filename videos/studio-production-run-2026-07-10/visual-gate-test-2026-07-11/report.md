# SynthPost HD Landscape Visual Research Test

## Run

- Date: 2026-07-11
- Story: `story_01a8fe15cc70`
- Studio job: `job_f1edb796708c`
- Path exercised: Studio API queue → worker → structured AI query planner → SearXNG → image/video acquisition → FFprobe broadcast-fit gate → visual candidate repository
- Result: completed successfully
- Runtime: 2 minutes 33 seconds
- Candidates returned by the job: 35
- Unique records created/refreshed during the run: 29
- New render-ready local files: 5, including one generic local drop-folder asset
- Web assets passing the gate: 4
- Broadcast-layout rejections: 14

## Passing web media

| Asset | Type | Dimensions | Size/duration | Section | Result |
|---|---|---:|---:|---|---|
| `visual_fa834833777d029a5495` | Image | 1920×1080 | 0.4 MB | Conclusion | Pass |
| `visual_6c75342a40fb3cad444f` | Video | 1920×1080 | 45 s / 26.2 MB | Cold open | Pass |
| `visual_d85894437b5f85fbb218` | Video | 1920×1080 | 45 s / 12.9 MB | Cold open | Pass |
| `visual_cf90d5922024e92656a5` | Image | 2500×1875 | 0.6 MB | Uncertainty | Pass |

Both videos contain audio and therefore use source-audio behavior only when selected for a fullscreen visual. They remain yellow-tier `suggested` assets and were not approved or inserted into the production timeline.

## Rejection behavior

The gate correctly rejected portrait, near-square, and sub-1080p files. Examples included 1200×675, 1600×900, 750×421, 1200×900, 600×400, 1440×813, and a 1.081:1 route-map image. Rejected downloads do not retain a renderable `download_path`, do not consume the usable image allowance immediately, and cannot be approved or selected by a regenerated timeline.

## Visual review

- The 1920×1080 still is a story-specific hydrogen-train headline graphic with heavy publisher text. It is relevant but should be used sparingly.
- The first video contains real hydrogen-train footage and Narendra Modi imagery with Mint branding and a large publisher lower-third.
- The second video contains real Indian hydrogen-train footage with TOI Bharat branding and a large lower-third.
- The uncertainty image clearly shows hydrogen railway refuelling equipment and is editorially appropriate, though it depicts a UK demonstration rather than the Indian pilot.
- A high-resolution datacenter image came from the generic local drop folder and was technically valid but editorially irrelevant. The ingestion rule was fixed so generic drop-folder media is no longer assigned to every section. Its existing candidate is now unassigned and remains only `suggested`.

## Verification

- 53 Python tests passed.
- Remotion TypeScript check passed.
- Live `yt-dlp` format simulation selected 3840×2160 landscape media.
- No assets were automatically approved.
- Existing final video was not changed.

