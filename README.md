# SynthPost

SynthPost is now a slim rendering shell for a future rebuilt newsroom pipeline.

This checkout intentionally keeps only the infrastructure that still works and is worth preserving:

- `avatar-engine/` integration and default avatar job generation.
- Remotion broadcast look/templates/components/styles.
- Manifest-to-Remotion story rendering.
- Optional Avatar-Engine anchor rendering.
- ffmpeg episode assembly with a static brand outro.

The old automatic news collection, AI writing, evidence ledger, visual planning, thumbnail generation, and web control-room UI have been removed. Future work should rebuild those as a clean V2 pipeline around explicit story, visual, approval, template, and timeline contracts.

## Retained Layout

```text
avatar-engine/                         Avatar-Engine checkout/integration target
pipeline/config.py                     Environment/path helpers
pipeline/storage.py                    Manifest/path helpers
pipeline/render_profiles.py            Preview/production/final render profiles
pipeline/provenance.py                 Lightweight artifact records
pipeline/direction/avatar.py           SynthPost → Avatar-Engine job generation/rendering
pipeline/compositor.py                 Thin wrapper around Remotion story render
pipeline/run_story.py                  Render a pre-authored story manifest
compositor/remotion_renderer/          Remotion renderer package
assembly/stitch_episode.py             ffmpeg final episode assembly with static outro
assets/brand/                          Retained brand intro/outro assets
config/.env.example                    Environment variable examples
tests/test_direction.py                Avatar integration contract tests
tests/test_remotion_visual_skill_rendering.py Remotion retained-surface tests
```

## What a Story Manifest Must Provide Now

Because the auto pipeline was removed, `pipeline.run_story` expects a pre-authored manifest. At minimum:

```json
{
  "story_id": "story_001",
  "episode_id": "ep_demo",
  "script": {
    "headline": "Demo headline",
    "text": "Anchor narration goes here."
  },
  "composition": {
    "template": "split_main",
    "output_path": "episodes/ep_demo/stories/story_001/composited.mp4"
  },
  "visuals": [
    {
      "path": "compositor/remotion_renderer/public/news/datacenter-server-racks.jpg",
      "start": 0,
      "end": 12,
      "fit": "cover",
      "sourceLabel": "SYNTHPOST"
    }
  ]
}
```

For timeline-based rendering, provide an approved timeline:

```json
{
  "approved_timeline": {
    "status": "approved",
    "segments": [
      {
        "segment_id": "seg_001",
        "section_id": "intro",
        "start_time": 0,
        "end_time": 8,
        "duration": 8,
        "script_text": "Anchor narration...",
        "anchor": { "visible": true, "speaking": true, "camera": "front_close" },
        "visual": {
          "asset_id": "",
          "media_type": "fallback",
          "source": "SynthPost",
          "rights_tier": "green",
          "review_status": "approved",
          "audio_mode": "muted",
          "path": "",
          "attribution_text": ""
        },
        "template": { "template_id": "fullscreen_anchor", "layout": "anchor_fullscreen" },
        "overlays": { "lower_third": "", "chyron": "", "attribution": "" }
      }
    ]
  }
}
```

## Install Renderer Dependencies

```bash
npm --prefix compositor/remotion_renderer install
```

## Render a Story

Use an existing anchor video:

```bash
python3 -m pipeline.run_story episodes/<episode_id>/stories/<story_id>/story.json \
  --skip-avatar-render \
  --force-composite \
  --render-profile preview
```

Render avatar + composition:

```bash
SYNTHPOST_AVATAR_RENDERER=rocketbox \
python3 -m pipeline.run_story episodes/<episode_id>/stories/<story_id>/story.json \
  --force-avatar \
  --force-composite \
  --render-profile production
```

Assemble all story clips in an episode. Assembly normalizes the brand intro, all story clips, and `assets/brand/outro.mp4`, then concatenates them into `final.mp4`:

```bash
python3 assembly/stitch_episode.py <episode_id> --render-profile production
```

## Avatar-Engine Notes

The default SynthPost avatar renderer is `rocketbox`, which maps to Avatar-Engine's browser/Three.js runtime.

One-time setup:

```bash
python3.11 -m venv avatar-engine/.venv
avatar-engine/.venv/bin/pip install -r avatar-engine/requirements.txt
npm --prefix avatar-engine/web_avatar_runtime install
```

Expected local licensed avatar asset:

```text
avatar-engine/assets/avatars/synthpost_anchor_v1/anchor.glb
```

Useful environment overrides:

```bash
SYNTHPOST_AVATAR_ENGINE_PATH=/absolute/path/to/Avatar-Engine
SYNTHPOST_AVATAR_RENDERER=rocketbox
SYNTHPOST_AVATAR_ASSET_PATH=assets/avatars/synthpost_anchor_v1/anchor.glb
SYNTHPOST_AVATAR_META_PATH=assets/avatars/synthpost_anchor_v1/avatar.json
SYNTHPOST_AVATAR_RENDER_BACKGROUND=charcoal
SYNTHPOST_AVATAR_VOICE_ID=af_bella
SYNTHPOST_AVATAR_VOICE_SPEED=1.10
```



## Verification

```bash
python3 -m unittest tests.test_direction tests.test_remotion_visual_skill_rendering
python3 -m py_compile pipeline/config.py pipeline/storage.py pipeline/render_profiles.py pipeline/provenance.py pipeline/direction/avatar.py pipeline/compositor.py pipeline/run_story.py assembly/stitch_episode.py
npm --prefix compositor/remotion_renderer run typecheck
```
