# Troubleshooting

Start with:

```bash
make config-check
make doctor
```

Then inspect the failed job in the Studio Jobs page and `.synthpost/jobs/<job_id>.log`. The log identifies the job, story, episode, stage, failure kind, and retry schedule.

## Missing Python, Node, or local tools

- `make setup` needs Python 3.11+, Node 20+, and npm.
- Install FFmpeg with `brew install ffmpeg`; verify both `ffmpeg` and `ffprobe`.
- yt-dlp and Tesseract are optional until video acquisition/OCR is used.
- Blender is optional for browser-avatar workflows but required for the legacy Blender renderer.
- Set an explicit binary variable only when `make doctor` cannot find a valid installation.

## Invalid configuration

`make config-check` names invalid booleans, integers, ranges, profiles, or provider values. Copy a fresh value from `.env.example`. `SYNTHPOST_AVATAR_ENGINE_DIR` is a deprecated alias; use `SYNTHPOST_AVATAR_ENGINE_PATH`. Missing provider credentials are feature failures: the Studio can open, but script/AI stages cannot run.

## Studio cannot reach the backend

- Confirm `http://127.0.0.1:8765/api/health` returns JSON.
- Confirm Vite uses `127.0.0.1:5173` and no stale process owns either port.
- Run `make backend` and `make web` in separate terminals to expose the failing process.
- A “live job updates disconnected” banner means EventSource is reconnecting; normal API actions still work.
- Rebuild `web/dist` with `make build` before `make remote`.

## Provider failures and timeouts

- Verify the selected provider and its key without printing the key.
- A rate limit is retryable only within the configured attempt/backoff budget.
- `hosted_fallback` requires both hosted keys and does not consume fallback quota for a temporary primary rate-limit window.
- Increase `SYNTHPOST_LLM_REQUEST_TIMEOUT_SECONDS` only after confirming normal connectivity.
- Use `SYNTHPOST_LLM_PROVIDER=mock` solely to prove the offline pipeline path.

## SearXNG/search issues

```bash
make searxng-up
curl 'http://127.0.0.1:8888/search?q=test&categories=news&format=json'
```

The bundled settings must allow JSON. On Docker Desktop, try `DOCKER_CONTEXT=desktop-linux make searxng-up`. Check URL, timeout, safe-search, and any private API key. Research retains the selected lead document; a total related-search outage is reported rather than silently treated as empty success.

## Missing or rejected visuals

- Put local media in the episode path returned by the Studio, not a global drop folder.
- Confirm file width/height/aspect using ffprobe and the broadcast-fit variables.
- Web results are yellow until manually reviewed. Red assets cannot be approved.
- A lead without `download_path` cannot render. Download/stage it, verify rights and attribution, then approve.
- Inspect `approval_blockers`, cleanliness status, warnings, and local file existence.
- Generated cards are the rights-safe fallback when real media is unavailable.

## Ollama/local LLM assumptions

The current code supports Groq, Gemini, explicit hosted fallback, and deterministic mock. Ollama is not a registered provider. Add it through the documented `LLMProvider` boundary with structured-output and offline adapter tests; changing `SYNTHPOST_LLM_PROVIDER` to an unknown value intentionally fails.

## Avatar or TTS failures

- Run `make test-avatar` and read `avatar-engine/README.md` plus `AGENTS.md`.
- Verify the engine path/interpreter, avatar metadata/assets, local TTS dependencies, and free disk space.
- The protected `avatar-engine/blender/avatar_template.blend` must never be overwritten.
- Browser renderer timeouts may need `AVATAR_ENGINE_BROWSER_TIMEOUT_PADDING_S`; do not mask a crashed browser with an unlimited timeout.
- Placeholder anchors are allowed only in preview/TEST_MODE.

## Remotion failures

- Run `npm --prefix compositor/remotion_renderer install` and its `typecheck` script.
- Inspect `story.json`: approved timeline, media paths, and anchor path must exist.
- Run `pipeline.run_story` directly for one manifest.
- Use `--force-composite` only after confirming inputs; otherwise freshness reuse is expected.

## FFmpeg/assembly failures

- Verify ffmpeg/ffprobe in `make doctor`.
- Confirm every episode story has the expected composited output for the same mode/profile.
- TEST_MODE and production filenames are intentionally different.
- Inspect `episodes/<episode_id>/_assembly/` and the episode manifest provenance.
- Missing brand media should fail clearly; restore tracked assets rather than replacing them silently.

## Stale or incompatible episode data

- Back up `.synthpost/`, `projects/`, and `episodes/` before manual repair.
- Never edit applied migration files. New database changes need a new migration.
- A strict model “extra field”/missing field error identifies the failing persisted contract. Add a compatibility adapter or migration; do not disable validation.
- Rebuild the renderer manifest from approved SQLite state when derived JSON is stale.

## Mobile/private access

Use `make remote`, then `make remote-status`. Both devices must share a Tailscale tailnet. Use Tailscale Serve, not Funnel. If Homebrew Tailscale lacks a system tunnel, the launcher uses userspace state under `~/.synthpost`. Stop with Ctrl+C or `make remote-off`.
