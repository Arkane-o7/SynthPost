# Configuration reference

SynthPost loads `.env` and then `.env.local` from the repository root. Existing process environment values win. `pipeline/config.py` parses grouped typed settings and fails with the exact variable name for invalid booleans/numbers/ranges. Run `make config-check` after every change.

Required means required for the named feature, not for opening the local Studio. Empty optional values disable or defer that integration. Never commit `.env`/`.env.local`; logs redact secret-shaped fields.

## Server, Studio, storage, and logging

| Variable | Default | Required | Example | Notes |
|---|---:|---|---|---|
| `SYNTHPOST_SERVER_HOST` | `127.0.0.1` | no | `127.0.0.1` | API bind used by `python -m pipeline.api.main`; keep localhost unless access is protected. |
| `SYNTHPOST_SERVER_PORT` | `8765` | no | `8765` | Valid TCP port. |
| `SYNTHPOST_STUDIO_HOST` | `127.0.0.1` | no | `127.0.0.1` | Documented Studio bind; `make web` currently passes the localhost default. |
| `SYNTHPOST_STUDIO_PORT` | `5173` | no | `5173` | Documented Vite port. |
| `SYNTHPOST_DB_PATH` | `.synthpost/synthpost.sqlite3` | no | `/Volumes/Work/synthpost.sqlite3` | Relative paths resolve from repository root. Existing default is compatibility-stable. |
| `SYNTHPOST_LOG_LEVEL` | `INFO` | no | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, or `ERROR`. Do not log provider payloads casually. |
| `SYNTHPOST_LOG_FORMAT` | `human` | no | `json` | Worker log format; JSON includes job/story/episode/stage fields. |

## LLM providers

| Variable | Default | Required | Example | Notes |
|---|---:|---|---|---|
| `SYNTHPOST_LLM_PROVIDER` | `groq` | script/AI features | `codex` | `codex`, `groq`, `gemini`, `sarvam`, `hosted_fallback`, or `mock`; legacy `groq_then_gemini` remains an alias; mock is tests/smoke only. |
| `SYNTHPOST_LLM_REQUEST_TIMEOUT_SECONDS` | `45` | no | `60` | Positive request timeout. |
| `SYNTHPOST_LLM_MAX_RETRIES` | `2` | no | `1` | Maximum retry cap for structured-output validation, 0–10. The Codex starter config uses one retry to bound plan usage and job duration. |
| `SYNTHPOST_SAVE_LLM_DEBUG` | `0` | no | `0` | Debug output can contain provider text; keep disabled and never commit it. |
| `SYNTHPOST_CODEX_BINARY` | `codex` | Codex | `/Applications/ChatGPT.app/Contents/Resources/codex` | Executable name or path. The CLI must already be authenticated with `codex login`. |
| `SYNTHPOST_CODEX_SANDBOX_BINARY` | `/usr/bin/sandbox-exec` | Codex | `/usr/bin/sandbox-exec` | macOS process sandbox used to prevent the model from spawning tools or shell commands. The provider fails closed if unavailable. |
| `SYNTHPOST_CODEX_MODEL` | `gpt-5.6-sol` | Codex | `gpt-5.6-sol` | Codex model available to the signed-in ChatGPT account. Model availability and limits follow that account. |
| `SYNTHPOST_CODEX_REASONING_EFFORT` | `medium` | Codex | `high` | `low`, `medium`, `high`, or `xhigh`. Higher settings can increase latency and plan usage. |
| `SYNTHPOST_CODEX_TIMEOUT_SECONDS` | `180` | Codex | `300` | Per-invocation subprocess timeout. This is intentionally separate from direct API timeouts and kept below the script job’s overall safety budget. |
| `GROQ_API_KEY` | empty | Groq | `gsk_…` | Secret. Never include in logs/docs/commits. |
| `SYNTHPOST_GROQ_MODEL` | `openai/gpt-oss-120b` | no | `openai/gpt-oss-120b` | Hosted Groq model ID. |
| `SYNTHPOST_GROQ_TEMPERATURE` | `0.2` | no | `0.2` | 0–2. |
| `SYNTHPOST_GROQ_MAX_COMPLETION_TOKENS` | `2300` | no | `4000` | Minimum 128. Higher values consume quota. |
| `GEMINI_API_KEY` | empty | Gemini/fallback | `AIza…` | Secret. Never include in logs/docs/commits. |
| `SYNTHPOST_GEMINI_MODEL` | `gemini-3.5-flash` | no | `gemini-3.5-flash` | Hosted Gemini model ID. |
| `SYNTHPOST_GEMINI_TEMPERATURE` | `0.2` | no | `0.2` | 0–2. |
| `SARVAM_API_KEY` | empty | Sarvam | `sk_…` | Secret. Never include in logs/docs/commits. |
| `SYNTHPOST_SARVAM_MODEL` | `sarvam-105b` | no | `sarvam-105b` | Hosted Sarvam AI model ID (`sarvam-105b`, `sarvam-30b`, etc.). |
| `SYNTHPOST_SARVAM_TEMPERATURE` | `0.2` | no | `0.2` | 0–2. |
| `SYNTHPOST_SARVAM_MAX_COMPLETION_TOKENS` | `2300` | no | `4000` | Minimum 128. |

### Codex with a ChatGPT account

`SYNTHPOST_LLM_PROVIDER=codex` routes every existing structured-generation
call through a local non-interactive `codex exec`: assignment-desk assessment,
narrative brief/draft/segmentation/headlines, visual-query planning, and visual
cleanliness classification. SynthPost supplies the existing prompt and JSON
Schema; the adapter returns the validated JSON object through the same
`LLMProvider` contract used by Groq and Gemini.

Set it up once:

```bash
codex login
codex login status
make doctor
```

Each invocation is ephemeral and runs in an empty temporary directory. Codex
plugins, web/browser, shell/code execution, computer-use, image, app, and
multi-agent features are disabled, and the agent thread/depth caps prevent
delegation even if a client build still advertises a collaboration tool. A
macOS `sandbox-exec` profile additionally denies child process
execution/forking, so untrusted article text cannot turn the generation call
into a local shell session. Provider API keys and `PYTHONPATH` are not
inherited. The provider fails closed when that sandbox is unavailable.

This is trusted local automation using the saved Codex login—not the OpenAI
Platform API. ChatGPT plan model availability, usage limits, and credits apply,
and each call has more startup/context overhead than a direct model API. Keep
Groq or Gemini available when predictable API latency, quotas, or unattended
service operation matter.

## Discovery, assignment, and research

| Variable | Default | Required | Example | Notes |
|---|---:|---|---|---|
| `SYNTHPOST_AI_ASSIGNMENT_DESK` | `1` | no | `0` | Disable for deterministic-only ranking. |
| `SYNTHPOST_ASSIGNMENT_DESK_AI_LIMIT` | `12` | no | `12` | Maximum leaders sent for AI assessment. |
| `SYNTHPOST_DISCOVERY_MAX_AGE_HOURS` | `24` | no | `72` | Active Story Inbox window. Older discovered news is archived from the default inbox; selected and editor-added stories remain available. |
| `SYNTHPOST_DISCOVERY_WORKERS` | `6` | no | `4` | Concurrent source fetch workers. |
| `SYNTHPOST_RESEARCH_MAX_DOCUMENTS` | `6` | no | `8` | Lead plus related documents. |
| `SYNTHPOST_RESEARCH_CLAIMS_PER_DOCUMENT` | `8` | no | `6` | Extraction bound. |
| `SYNTHPOST_RESEARCH_MIN_RELEVANCE` | `0.15` | no | `0.25` | Related-news relevance floor. |
| `SYNTHPOST_RESEARCH_RSS_SOURCE_LIMIT` | `10` | no | `10` | Fallback enabled sources considered. |

## SearXNG

| Variable | Default | Required | Example | Notes |
|---|---:|---|---|---|
| `SYNTHPOST_SEARXNG_URL` | empty | SearXNG features | `http://127.0.0.1:8888` | Prefer the bundled private instance; JSON format must be enabled. |
| `SYNTHPOST_SEARXNG_API_KEY` | empty | private instance only | `replace-me` | Secret header value if the instance requires it. |
| `SYNTHPOST_SEARXNG_LANGUAGE` | `en` | no | `en` | Search language. |
| `SYNTHPOST_SEARXNG_SAFESEARCH` | `1` | no | `1` | SearXNG range 0–2. |
| `SYNTHPOST_SEARXNG_TIMEOUT` | `20` | no | `30` | Search HTTP timeout seconds. |
| `SYNTHPOST_SEARXNG_RETRIES` | `2` | no | `2` | Total attempts, 1–10. |
| `SYNTHPOST_SEARXNG_NEWS_RESULTS` | `12` | no | `12` | Related-news result cap. |
| `SYNTHPOST_SEARXNG_NEWS_TIME_RANGE` | `month` | no | `week` | Passed to SearXNG news search. |
| `SYNTHPOST_SEARXNG_SOCKET_TIMEOUT` | `15` | no | `15` | yt-dlp socket timeout. |

## Visual discovery, acquisition, and policy

| Variable | Default | Required | Example | Notes |
|---|---:|---|---|---|
| `SYNTHPOST_AI_VISUAL_QUERY_PLANNING` | `1` | no | `0` | Deterministic query planner is the fallback. |
| `SYNTHPOST_AI_VISUAL_CLEANLINESS` | `1` | no | `0` | Compatibility switch for the legacy/manual cleanliness analyzer; the normal Studio review flow remains editor-controlled. |
| `SYNTHPOST_INCLUDE_VISUAL_LEADS` | `1` | no | `1` | Retain non-downloadable results as editor leads. |
| `SYNTHPOST_DISABLE_WEB_VISUALS` | `0` | no | `1` | Disables web source acquisition. |
| `SYNTHPOST_GENERATE_FALLBACK_VISUALS` | `1` | no | `1` | Create anchor-only fallback records for uncovered sections; no synthetic image card is rendered. |
| `SYNTHPOST_SEARXNG_VISUAL_MAX_QUERIES` | `12` | no | `8` | Hard request cap. |
| `SYNTHPOST_SEARXNG_IMAGE_RESULTS_PER_QUERY` | `3` | no | `3` | Image result cap per query. |
| `SYNTHPOST_SEARXNG_VIDEO_RESULTS_PER_QUERY` | `2` | no | `2` | Video result cap per query. |
| `SYNTHPOST_SEARXNG_DOWNLOAD_VIDEOS` | `1` | no | `0` | Requires yt-dlp; downloaded media is eligible for automatic selection, while approval pins an editor-reviewed choice. |
| `SYNTHPOST_SEARXNG_VIDEO_DOWNLOAD_LIMIT` | `6` | no | `3` | Per-job download cap. |
| `SYNTHPOST_SEARXNG_VIDEO_CLIP_SECONDS` | `45` | no | `30` | Clip acquisition length. |
| `SYNTHPOST_SEARXNG_VIDEO_MAX_DURATION` | `900` | no | `600` | Reject longer source pages before download. |
| `SYNTHPOST_SEARXNG_VIDEO_TIMEOUT` | `300` | no | `300` | Acquisition/analysis subprocess timeout. |
| `SYNTHPOST_VISUAL_DOWNLOAD_TIMEOUT` | `30` | no | `45` | Direct image timeout. |
| `SYNTHPOST_VISUAL_DOWNLOAD_MAX_BYTES` | `104857600` | no | `52428800` | Applies to downloaded and browser-uploaded media; prevents unbounded files. |
| `SYNTHPOST_VISUAL_ENFORCE_BROADCAST_FIT` | `1` | no | `1` | Keep enabled for render-ready approval. |
| `SYNTHPOST_VISUAL_MIN_WIDTH` | `1280` | no | `1920` | Minimum render-ready width. |
| `SYNTHPOST_VISUAL_MIN_HEIGHT` | `720` | no | `1080` | Minimum render-ready height. |
| `SYNTHPOST_VISUAL_ASPECT_TOLERANCE` | `0.20` | no | `0.20` | Video tolerance around supported panels. |
| `SYNTHPOST_VISUAL_IMAGE_ASPECT_TOLERANCE` | `0.30` | no | `0.30` | Still-image tolerance. |
| `SYNTHPOST_YT_DLP` | `yt-dlp` | video download | `/opt/homebrew/bin/yt-dlp` | Binary name/path. |
| `SYNTHPOST_TESSERACT` | `tesseract` | OCR analysis | `/opt/homebrew/bin/tesseract` | Binary name/path. |
| `SYNTHPOST_VIDEO_APPROVED_CHANNEL_IDS` | empty | no | `UC123,UC456` | Comma-separated editor allowlist; not a license grant. |
| `SYNTHPOST_VIDEO_APPROVED_SOURCE_NAMES` | empty | no | `NASA,ISRO` | Comma-separated trusted source fragments. |
| `SYNTHPOST_VIDEO_BLOCKED_SOURCE_NAMES` | empty | no | `Example Network` | Comma-separated competitor/block fragments. |

## Script and timeline

| Variable | Default | Required | Example | Notes |
|---|---:|---|---|---|
| `SYNTHPOST_WORDS_PER_MINUTE` | `145` | no | `150` | Positive narration estimate. |
| `SYNTHPOST_STRICT_DURATION` | `1` | no | `0` | When enabled, duration validation is terminal. |
| `SYNTHPOST_EXPERIMENTAL_SOURCE_AUDIO` | `0` | no | `0` | Keep disabled until clip timestamps/rights are verified. |

## Avatar integration

| Variable | Default | Required | Example | Notes |
|---|---:|---|---|---|
| `SYNTHPOST_AVATAR_ENGINE_PATH` | `avatar-engine` | avatar render | `/Volumes/Work/avatar-engine` | Preferred path; relative values resolve from repository root. |
| `SYNTHPOST_AVATAR_ENGINE_DIR` | — | no | `avatar-engine` | Deprecated alias; `*_PATH` wins when both exist. |
| `SYNTHPOST_AVATAR_PYTHON` | engine venv/current Python | no | `avatar-engine/.venv/bin/python` | Explicit interpreter. |
| `SYNTHPOST_AVATAR_RENDERER` | `rocketbox` | no | `blender` | SynthPost-facing renderer selection. |
| `SYNTHPOST_AVATAR_ASSET_PATH` | SynthPost anchor GLB | browser avatar | `assets/avatars/acme/anchor.glb` | Relative to Avatar Engine. Licensed binaries stay uncommitted. |
| `SYNTHPOST_AVATAR_META_PATH` | SynthPost `avatar.json` | browser avatar | `assets/avatars/acme/avatar.json` | Avatar metadata. |
| `SYNTHPOST_AVATAR_STYLE` | `professional_news_anchor` | no | `professional_news_anchor` | Performance style label. |
| `SYNTHPOST_AVATAR_BODY_FORM` | `F` | no | `M` | Renderer body-form hint. |
| `SYNTHPOST_AVATAR_RENDER_BACKGROUND` | `charcoal` | no | `chroma_green` | Render background mode. |
| `SYNTHPOST_AVATAR_VOICE_ID` | `af_heart` | TTS | `af_bella` | Local Kokoro voice ID. |
| `SYNTHPOST_AVATAR_VOICE_SPEED` | `1.10` | no | `1.0` | Positive multiplier. |
| `SYNTHPOST_NARRATION_BEAT_PAUSE_MS` | `80` | no | `100` | Silence inserted between production beats. Included in the exact sample clock; range 0–2000 ms. |
| `SYNTHPOST_NARRATION_SECTION_PAUSE_MS` | `220` | no | `250` | Silence inserted between script sections. Included in the exact sample clock; range 0–5000 ms. |
| `SYNTHPOST_AVATAR_LANG_CODE` | `a` | no | `a` | TTS language code. |
| `SYNTHPOST_AVATAR_DISTANCE_MULTIPLIER` | `0.86` | no | `0.9` | Camera framing calibration. |
| `SYNTHPOST_AVATAR_TARGET_HEIGHT_FACTOR` | `0.52` | no | `0.52` | Camera target calibration. |
| `SYNTHPOST_AVATAR_HEIGHT_FACTOR` | `0.86` | no | `0.86` | Avatar framing calibration. |
| `SYNTHPOST_AVATAR_ROTATION_Y_DEGREES` | `0` | no | `2` | Y-axis calibration. |
| `SYNTHPOST_AVATAR_TTS_PROBE` | `0` | no | `1` | Extra local TTS diagnostic. |
| `SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR` | `0` | test/preview only | `1` | Never enable for a claimed production output. |
| `AVATAR_ENGINE_RENDERER` | renderer factory default | no | `rocketbox` | Lower-level compatibility override. |
| `AVATAR_ENGINE_ALLOW_RENDERER_FALLBACK` | `0` | no | `1` | Explicit renderer fallback; can change appearance. |
| `AVATAR_ENGINE_ALLOW_2D_FACE_FALLBACK` | `0` | no | `1` | Explicit legacy fallback. |
| `AVATAR_ENGINE_BROWSER_TIMEOUT_PADDING_S` | `900` | no | `1200` | Padding for browser render estimates. |
| `AVATAR_ENGINE_ESTIMATED_BYTES_PER_FRAME` | `1250000` | no | `1250000` | Disk-space estimate. |
| `AVATAR_ENGINE_MIN_RENDER_FREE_BYTES` | `5368709120` | no | `10737418240` | Minimum free space before render. |
| `AVATAR_ENGINE_KEEP_FAILED_TEMP` | `0` | no | `1` | Debug only; failed frames may be large/sensitive. |

## Remotion, FFmpeg, and queues

| Variable | Default | Required | Example | Notes |
|---|---:|---|---|---|
| `SYNTHPOST_REMOTION_DIR` | `compositor/remotion_renderer` | composition | `/Volumes/Work/remotion_renderer` | Must contain `package.json`. |
| `SYNTHPOST_REMOTION_CONCURRENCY` | `4` | no | `6` | Frame-render concurrency inside each Remotion job. Total pressure is roughly this value times active Remotion workers. |
| `SYNTHPOST_FFMPEG` | `ffmpeg` | render/assembly | `/opt/homebrew/bin/ffmpeg` | Binary name/path. |
| `SYNTHPOST_RENDER_PROFILE` | `production` | no | `preview` | `preview`, `production`, `final_master`. |
| `SYNTHPOST_RENDER_CODEC` | `h264` | no | `h264` | Renderer/assembly codec hint. |
| `SYNTHPOST_RENDER_PREVIEW_FRAME` | `24` | no | `48` | Non-negative preview frame. |
| `SYNTHPOST_EDITORIAL_WORKERS` | `3` | no | `4` | Independent editorial worker processes; range 1–32. Provider rate limits still apply. |
| `SYNTHPOST_MEDIA_WORKERS` | `3` | no | `4` | Independent visual/timeline processes; range 1–32. Account for network and download bandwidth. |
| `SYNTHPOST_RENDER_WORKERS` | `3` | no | `4` | Independent avatar/Remotion/FFmpeg processes; range 1–16. Each can consume substantial CPU, GPU, RAM, and disk. |
| `SYNTHPOST_EDITORIAL_JOB_MAX_ATTEMPTS` | `3` | no | `3` | Total editorial attempts. |
| `SYNTHPOST_MEDIA_JOB_MAX_ATTEMPTS` | `3` | no | `3` | Total media attempts. |
| `SYNTHPOST_RENDER_JOB_MAX_ATTEMPTS` | `2` | no | `2` | Total render attempts. |
| `SYNTHPOST_JOB_RETRY_BASE_SECONDS` | `15` | no | `30` | Backoff base. |
| `SYNTHPOST_JOB_RETRY_MAX_SECONDS` | `900` | no | `900` | Must be at least the base. |
| `SYNTHPOST_JOB_HEARTBEAT_SECONDS` | `5` | no | `5` | Minimum 1 second. |

`make workers` launches exactly the configured capacity under one supervisor. Increasing a count requires restarting the supervisor. Jobs targeting the same story are serialized, and assembly is exclusive with other work for its episode; separate projects and episodes can use every available slot. Start with the `3/3/3` defaults, observe memory and provider quotas, then increase worker counts or per-render Remotion concurrency separately.

## Security notes

- Use localhost binds or private Tailscale Serve; do not use public Funnel for production controls.
- Search/API keys are secrets even for a private local service.
- LLM prompts and debug responses may contain unpublished editorial material.
- Local media paths can reveal usernames or mounted volumes; contextual logs use project-relative paths where possible.
- An approved channel/source list is editorial provenance metadata, not automatic copyright permission.
