# AGENTS.md

This repo is the local Python + Blender + browser/Three.js news-anchor rendering module for an AI-automated news channel.

Guidelines for future agents:

- Keep the pipeline local-first and command-line driven.
- The current 3D path is a custom Three.js/Reallusion CC4 renderer kept under the legacy `rocketbox` renderer name for compatibility. Do not assume it is using Rocketbox assets.
- Preserve the browser PNG-frame capture path (`canvas.toDataURL` frames → Python → FFmpeg). Playwright viewport video and canvas `MediaRecorder` were unreliable for WebGL final capture.
- Treat `blender/avatar_template.blend` as the protected legacy production scene. Runtime code must load it only and never save or overwrite it.
- Preserve the semantic camera contract for legacy Blender: `portrait_main`, `landscape_intro`, and `landscape_conclusion`.
- Preserve the current 3D SynthPost anchor jobs: `jobs/synthpost_anchor_v1_quick_test.json`, `jobs/synthpost_anchor_v1_preview.json`, and `jobs/synthpost_anchor_v1_chroma.json`.
- Preserve both legacy export modes: `combined` for review MP4s and `native_segments` for backend/editor camera clips.
- Preserve render profiles: `preview` for draft review and `production` for native segment backend output.
- Preserve 2D face mode on `FACE_Surface`/`FACE_Backdrop` and the mouth texture fallback behavior.
- Keep 3D mouth/teeth/tongue changes subtle. The upper teeth, lower teeth, and tongue are especially sensitive for the CC4 anchor.
- Default Kokoro voice selection is `af_bella`, `speed: 1.0`, `lang_code: a`; use `scripts/audition_kokoro_voices.py` for future voice auditions.
- Do not add cloud APIs or a web app unless the user asks for that next phase.
- External tools must fail clearly and use test-mode placeholders where practical.
- Keep Blender and browser-renderer assumptions documented in `README.md`, `docs/BLENDER_SCENE_GUIDE.md`, `docs/talkinghead_runtime_design.md`, and `assets/characters/avatar_01/README.md`.
- Avoid hardcoded absolute paths in committed source; all project paths should resolve from the repo root. Local config may contain machine-specific tool paths.
- Prefer small replaceable wrappers for TTS, lip-sync, browser rendering, Blender rendering, and video export.
- Do not commit generated `assets/output/`, `assets/temp/`, `assets/renders/`, browser `dist/`, or large avatar binaries/textures unless explicitly requested and handled through LFS/external asset storage.
