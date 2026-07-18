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

## Parallel workers do not start or projects remain queued

Run `make doctor` and confirm the reported editorial/media/render capacity. Restart `make workers` after changing worker counts; a running supervisor does not hot-reload `.env`. `Another SynthPost worker supervisor is already running` means an existing pool owns the database—stop it instead of starting a second pool. A `legacy worker still owns` error means a pre-upgrade lane worker is still alive.

Jobs for the same story intentionally wait for one another, and episode assembly waits for running work in that episode. Jobs from unrelated projects or episodes should show multiple `running` records when capacity is greater than one. If the Mac becomes memory-bound, lower `SYNTHPOST_RENDER_WORKERS` first, then set `SYNTHPOST_REMOTION_CONCURRENCY` to a smaller per-render value.

## Provider failures and timeouts

- Verify the selected provider and, for Groq/Gemini, its key without printing the key.
- For `codex`, run `codex login status` and `make doctor`. A missing/expired
  ChatGPT login, unavailable configured model, or exhausted ChatGPT plan limit
  is surfaced as a provider failure.
- The Codex provider requires macOS `/usr/bin/sandbox-exec` and fails closed
  without it. `Operation not permitted` at startup usually means the configured
  Codex executable changed and should be rechecked with `make doctor`.
- `SYNTHPOST_CODEX_TIMEOUT_SECONDS` controls the full local Codex invocation;
  `SYNTHPOST_LLM_REQUEST_TIMEOUT_SECONDS` controls direct provider requests.
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
- The presenter/anchor layout is the rights-safe fallback when real media is unavailable.

## Local LLM and Codex assumptions

The current code supports the local Codex CLI transport, Groq, Gemini, explicit
hosted fallback, and deterministic mock. Codex still uses OpenAI-hosted models
through the signed-in ChatGPT account; it is not an offline LLM. Ollama is not
a registered provider. Add it through the documented `LLMProvider` boundary
with structured-output and offline adapter tests; changing
`SYNTHPOST_LLM_PROVIDER` to an unknown value intentionally fails.

## Avatar or TTS failures

- Run `make test-avatar` and read `avatar-engine/README.md` plus `AGENTS.md`.
- Run `.venv/bin/python -m tools.doctor --strict-features`; the `kokoro` check must report the Avatar Engine interpreter and installed version.
- Verify the engine path/interpreter, avatar metadata/assets, local Kokoro dependencies, and free disk space.
- If `narration_generate` fails, inspect its job log and retry from the Timeline workspace after the latest script is approved. Missing or stale narration intentionally blocks timeline generation.
- The exact clock is stored beside the audio at `episodes/<episode>/stories/<story>/narration/script_vNNN/alignment.json`. Its final `end_sample` must equal the WAV frame count.
- Test-mode narration is never accepted by a production timeline or manifest; regenerate without test mode instead of copying a test WAV.
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
