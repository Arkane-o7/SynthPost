# Development guide

## Repository structure

```text
pipeline/                       Python domain, services, providers, API, queue
  api/                          HTTP schemas, feature routers, app wiring
  db/                           SQLite connection/migrations/repository
  discovery/ research/ scripts/ visuals/ timeline/
  jobs/                         worker, retry policy, queue execution
web/                            React/Vite Studio
contracts/                      cross-runtime JSON Schema and TypeScript types
compositor/remotion_renderer/   Remotion composition package
avatar-engine/                  local avatar subsystem and its own tests/docs
assembly/                       FFmpeg final assembly
tests/                          deterministic root unit/contract/integration tests
tools/                          developer diagnostics and remote launcher
docs/                           architecture and operating documentation
```

Start with `pipeline/README.md` for Python ownership and `web/README.md` for Studio state/data rules.

## Setup and local services

```bash
cp .env.example .env
make setup
make config-check
make doctor
make dev
```

Use separate terminals when debugging one process:

```bash
make backend
make worker LANE=editorial
make worker LANE=media
make worker LANE=render
make web
```

`make workers` is the normal entry point: it supervises the process counts from `.env` and restarts workers that fail unexpectedly. A manual worker leases the first free configured slot; pass `SLOT=2` when debugging a specific slot. Separate OS processes intentionally isolate renderer environment overrides and native subprocess state.

SQLite lives at `.synthpost/synthpost.sqlite3` unless overridden. Do not point tests at the production database; repository tests use temporary paths.

## Quality gates and test levels

| Level | Command | Network/render cost |
|---|---|---|
| Root unit/contract/integration | `make test` | offline, no expensive render |
| Avatar unit | `make test-avatar` | offline, no Blender render |
| Python compile + TS checks | `make typecheck` | offline |
| Studio production build | `make build` | offline after setup |
| Full default gate | `make check` | offline after setup |
| TEST_MODE smoke | `make smoke` | local Remotion/FFmpeg, placeholder-safe |
| Parallel TEST_MODE smoke | `make smoke-parallel` | two simultaneous local Remotion/FFmpeg episodes |
| Production/avatar manual | explicit Studio action or `pipeline.run_story` | expensive; not a default gate |

Tests must not call live providers. Use `MockProvider`, fixtures, patched URL openers/subprocesses, and temporary databases/directories. Mark any future live integration command separately and never include it in `make test`.

## Debugging

- Job status/error/traceback: Studio Jobs page or `GET /api/jobs/<id>`.
- Contextual log: `.synthpost/jobs/<job_id>.log` or `GET /api/jobs/<id>/logs`.
- JSON logs: `SYNTHPOST_LOG_FORMAT=json`.
- Effective parallel capacity: `make doctor` or `GET /api/health`.
- Configuration parse: `make config-check`.
- Tool availability: `make doctor`; add `--strict-features` through `python -m tools.doctor` when validating a production workstation.
- API shape: FastAPI docs at `http://127.0.0.1:8765/docs`.
- Renderer input: inspect the story's `story.json` and provenance section.

Important exceptions must reach the job error record. A best-effort fallback may catch a narrow exception only when the warning is logged and safe behavior is explicit.

## Adding a module

Place domain/persistence contracts in `models.py`, use-case behavior in its feature package, infrastructure in a provider/repository adapter, and HTTP concerns in `pipeline/api/`. Avoid generic `utils.py`; name modules after the capability they own. Keep imports directed from API/worker to services to models/infrastructure, not back toward API.

## Adding a pipeline stage

1. Add a `StageName` and `StageContract` in `pipeline/stages.py`.
2. Define a focused handler in `pipeline/jobs/worker.py` or a feature module.
3. Register it in `HANDLERS`; tests require handler and contract keys to match.
4. Add queue-lane inference and retry classification.
5. Add the API enqueue action and typed Studio client method.
6. Test required inputs, output keys, retry/terminal errors, cancellation, and state transition.
7. Document artifacts and independent execution in `docs/PIPELINE.md`.

## Adding a provider

For structured LLMs, implement `LLMProvider.generate_json()`, isolate credentials/timeouts/errors in the adapter, add a no-network availability check, and register it in `configured_provider()`. For visual discovery, implement `VisualSource.available()`/`search()` and register it in `configured_visual_sources()`. Normalize provider payloads before they reach domain services and provide an offline test double.

## Adding a template

Add the Remotion component and registry entry under `compositor/remotion_renderer/src/`, then add the matching Python template capability/validation under `pipeline/timeline/`. Update the renderer TypeScript types only if the contract changes. Add a focused render/type test and verify preview plus production dimensions.

## Adding or changing an API endpoint

1. Define request fields in `pipeline/api/schemas.py` with `extra="forbid"`.
2. Put the route in the closest feature router; avoid adding unrelated responsibilities to `main.py`.
3. Return canonical model dumps and preserve the `{error: {code, message}}` error envelope.
4. Add/update the typed method in `web/src/api/client.ts`.
5. Add an API contract test and check OpenAPI.

Do not accept `dict[str, Any]` patches for domain records. Do not expose arbitrary local paths or underlying secrets in errors.

## Updating a schema safely

1. Decide whether the change is additive, compatible-defaulted, or breaking.
2. Update Pydantic, JSON Schema, and TypeScript contracts together.
3. For SQLite changes, add the next ordered migration; never edit an applied migration.
4. For persisted JSON, add/retain a version field and a legacy adapter before changing writers.
5. Add fixtures for both current and supported legacy forms.
6. Run `make check` and a smoke render when the renderer manifest changes.

## Repository hygiene

Do not commit `.env`, SQLite state, episode/project output, node modules, caches, render output, or licensed avatar binaries. `make clean-dev` removes only rebuildable caches/build output; it does not remove episode/project data. Follow `avatar-engine/AGENTS.md` before changing that subsystem.
