# Browser CC4 Renderer — Performance Notes

Recorded during the SynthPost anchor integration work. This file keeps its original name for compatibility with existing documentation links, but the active renderer is the custom Three.js/Reallusion CC4 runtime under the legacy `rocketbox` renderer key.

## Current capture method

```text
Three.js canvas PNG frames → Python frame receiver → FFmpeg H.264/AAC mux
```

This replaced the older Playwright viewport-video benchmark. The PNG-frame path is slower than raw viewport capture, but it is deterministic and avoids blank/missed WebGL captures in headless Chromium.

## Current observed timings

| Job | Output | Resolution/FPS | Frames | Wall time | Notes |
|---|---|---:|---:|---:|---|
| `synthpost_anchor_v1_quick_test.json` | `assets/output/synthpost_anchor_v1_quick_test.mp4` | 1280×720 / 24 | 192 | ~27.2 s | Kokoro `af_bella`, Rhubarb, CC4 morph/bone runtime |
| `synthpost_anchor_v1_preview.json` | `assets/output/synthpost_anchor_v1_preview.mp4` | 1280×720 / 24 | audio-dependent | ~20–24 s in short tests | Neutral studio background |
| `synthpost_anchor_v1_chroma.json` | `assets/output/synthpost_anchor_v1_chroma.mp4` | 1280×720 / 24 | audio-dependent | ~18–21 s in short tests | Chroma-green background |

Timings vary with audio duration, browser startup, local CPU/GPU load, and whether the web runtime was already built.

## Old benchmark context

The earlier TalkingHead/viewport-video spike rendered simple GLB tests approximately in real time. That result should not be used for current production estimates because the current CC4 path does more work:

- heavier CC4 avatar/material setup,
- Reallusion morph mapping,
- jaw/teeth/tongue bone transforms,
- procedural body/arm animation,
- deterministic PNG frame export,
- FFmpeg mux of the original WAV.

## Acceptance guidance

For short news-anchor clips, treat the current path as practical for local batch generation but not yet faster-than-real-time. A downstream service should budget roughly:

```text
browser startup + GLB load + one PNG capture pass + FFmpeg mux
```

For multi-story batches, future optimization should prioritize:

1. keeping a browser/session warm across clips,
2. caching loaded avatar assets,
3. reducing PNG encode overhead,
4. optional GPU FFmpeg encode (`h264_videotoolbox` on macOS, `h264_nvenc` on CUDA),
5. a dedicated offline frame-step renderer if needed.

## Validation command

```bash
npm --prefix web_avatar_runtime run build
.venv/bin/python3 -c 'import runpy, sys; sys.argv=["render_avatar","--job","jobs/synthpost_anchor_v1_quick_test.json","--renderer","rocketbox"]; runpy.run_module("avatar_engine.render_avatar", run_name="__main__")'
```
