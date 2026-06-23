# AGENTS.md

This repo is the local Python + Blender news-anchor rendering module for an AI-automated news channel.

Guidelines for future agents:

- Keep the pipeline local-first and command-line driven.
- Treat `blender/avatar_template.blend` as the protected production scene. Runtime code must load it only and never save or overwrite it.
- Preserve the semantic camera contract: `portrait_main`, `landscape_intro`, and `landscape_conclusion`.
- Preserve both export modes: `combined` for review MP4s and `native_segments` for backend/editor camera clips.
- Preserve render profiles: `preview` for draft review and `production` for native segment backend output.
- Preserve 2D face mode on `FACE_Surface`/`FACE_Backdrop` and the mouth texture fallback behavior.
- Do not add cloud APIs or a web app unless the user asks for that next phase.
- External tools must fail clearly and use test-mode placeholders where practical.
- Keep Blender scene assumptions documented in `README.md`, `docs/BLENDER_SCENE_GUIDE.md`, and `assets/characters/avatar_01/README.md`.
- Avoid hardcoded absolute paths; all project paths should resolve from the repo root.
- Prefer small replaceable wrappers for TTS, lip-sync, Blender rendering, and video export.
