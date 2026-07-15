# SynthPost maintenance and overhaul report

Status: implemented and verified locally on 2026-07-15
Repository: `Arkane-o7/SynthPost`
Review state: the narrative-first and visual-acquisition changes were audited,
covered by regressions, and prepared for publication from a dedicated branch.

## 1. Architecture before and after

Before the overhaul, important production behavior was concentrated in large
pipeline and UI modules. Provider selection, environment access, loosely typed
stage data, visual acquisition, editorial decisions, and rendering rules were
often coupled. Individual jobs could be run, but ownership, retry behavior,
cross-project concurrency, artifact provenance, and extension points were hard
to follow without tracing implementation details.

The current architecture retains the existing product workflow and persisted
formats while making its boundaries explicit:

1. FastAPI owns HTTP transport and delegates production work to application
   services and queued jobs.
2. SQLite repositories own projects, episodes, stories, scripts, visuals,
   timelines, generation audits, and job state.
3. Typed configuration is loaded centrally and validated by the doctor/config
   commands.
4. Editorial, media, and render work use independent queue lanes. Three workers
   per lane are enabled by default; unrelated projects and episodes can progress
   concurrently while same-story work and same-episode assembly remain guarded.
5. Script generation now follows a narrative-first flow: relevant research
   projection, narrative brief, uninterrupted draft, deterministic quality and
   duration checks, optional whole-narrative repair, segmentation without text
   rewriting, and a separate headline/overlay pass.
6. Visual discovery distinguishes research leads from acquired local media,
   validates real downloaded bytes, records provenance and rights decisions,
   supports explicit acquisition, and exposes predictable fallback behavior.
7. Timeline planning consumes accepted scripts and eligible local visuals,
   validates media/template compatibility, and requires timeline approval before
   manifest construction.
8. Remotion and FFmpeg continue consuming backward-compatible script, timeline,
   and manifest structures.

Detailed component and data-flow documentation is in
[`docs/v2-architecture.md`](v2-architecture.md) and
[`docs/PIPELINE.md`](PIPELINE.md).

## 2. Most important problems discovered

- Section-by-section script generation caused repeated openings, duplicated
  explanations, weak transitions, and scripts that sounded like stitched
  articles rather than one narration.
- Research packs could contain unrelated claims from low-relevance documents;
  those claims were passed directly into script generation.
- Provider failures and structured-response validation were not consistently
  attributable or recoverable across hosted fallbacks.
- A failed optional headline pass could discard narration that had already
  passed grounding, duration, continuity, and segmentation checks.
- Visual search results were sometimes displayed like usable media even when
  they were only remote research leads without renderable local files.
- Remote image URLs could return HTML, expired URLs, previews, incorrect
  dimensions, or incompatible aspect ratios. Display metadata was sometimes
  confused with the downloaded asset's real properties.
- Video acquisition, image fallback, duplicate result handling, and manual
  rights overrides had inconsistent semantics.
- Timeline selection could retain incompatible, missing, or deleted visual
  paths without a sufficiently clear fallback.
- Production queues did not originally make safe multi-project concurrency and
  per-lane capacity obvious.
- Several important behaviors lacked compact regression tests and user-facing
  documentation.

## 3. Major refactors implemented

### Narrative-first generation

- Added typed narrative brief, beat, draft, and segmentation contracts.
- Added a relevance projection at the generation boundary so unrelated research
  documents, claims, and evidence are excluded without mutating the canonical
  research pack.
- Generate one complete narration before assigning presentation sections.
- Validate duration, supported claim identifiers, spoken metadata leakage,
  repeated scene openings, near-duplicate beats, repeated phrases, and basic
  sentence quality.
- Run one whole-narrative repair pass when continuity checks fail.
- Require every compact narration beat to link to supported research claims and
  report every number not observed in claims, evidence, dates, or number fields.
- Require segmentation to reference every accepted beat exactly once, in order,
  without returning or rewriting narration.
- Preserve the existing `ScriptDocument` output contract for the Studio,
  visuals, timeline, manifest, and render pipeline.
- Store versioned prompts, raw structured responses, validation attempts,
  normalization decisions, providers, and models in the generation ledger.
- Reuse completed generation-stage checkpoints during safe job retries.
- Treat headline/overlay generation as non-destructive decoration: if it fails,
  retain the accepted narration and deterministic metadata with an explicit
  warning.

### Visual acquisition and review

- Consolidated candidate acquisition around verified local media rather than
  preview-only URLs.
- Probe downloaded files for actual media type, dimensions, aspect ratio,
  duration, audio, and broadcast suitability.
- Added source-page/Open Graph and cached-preview image recovery where safe.
- Added explicit image/video acquisition actions and clearer research-lead,
  suggested, approved, rejected, and unavailable states.
- Preserve manual approval as a pinning decision; rejection excludes a result.
- Deduplicate repeated results while allowing one acquired asset to remain
  relevant to multiple script sections.
- Use collision-safe paths for concurrent uploads and same-named inbox media.
- Clear stale approval when media bytes are reacquired and keep new media in
  content review until an editor approves it.
- Keep missing or unsuitable media on an anchor/presenter fallback instead of
  producing misleading substitute cards.
- Improved timeline hydration and validation when media is replaced, removed,
  incompatible, or no longer renderable.

### Parallel jobs and diagnostics

- Separated editorial, media, and render lanes.
- Defaulted each lane to three workers, configurable from environment settings.
- Guarded same-story operations and episode assembly while allowing unrelated
  projects and episodes to run in parallel.
- Improved progress stages and structured context fields for project, episode,
  story, job, stage, and retry information.
- Added safe retry classification for transient network, timeout, rate-limit,
  and subprocess failures.
- Extended doctor/configuration output to report effective worker capacity.

### Studio and contracts

- Updated typed API contracts for visual acquisition and related metadata.
- Improved visual review controls and status explanations without redesigning
  the workflow.
- Preserved the existing script/timeline/API shapes while adding internal typed
  contracts for new pipeline stages.

## 4. Important files changed

- `pipeline/scripts/generation.py` — narrative-first orchestration, validation,
  repair, segmentation, audits, checkpoint reuse, and headline fallback.
- `pipeline/models.py` — narrative contracts and related typed state.
- `pipeline/llm/providers.py` — structured validation evidence, rate-limit
  handling, and hosted-provider fallback attribution.
- `pipeline/visuals/providers.py` — visual discovery, acquisition, verification,
  deduplication, provenance, and review semantics.
- `pipeline/visuals/content_analysis.py` — downloaded-media analysis.
- `pipeline/timeline/planner.py` and `pipeline/timeline/validation.py` — eligible
  visual selection and safe fallback behavior.
- `pipeline/jobs/worker.py` — narrative progress reporting and lane execution.
- `pipeline/config.py` — typed visual, provider, timeout, and worker settings.
- `pipeline/api/main.py` — visual acquisition API behavior.
- `web/src/workspace/VisualsPanel.tsx` — editor-facing visual states and actions.
- `contracts/schemas/synthpost.v2.schema.json` and
  `contracts/typescript/index.ts` — shared contract updates.
- `tests/test_v2_pipeline.py`, `tests/test_searxng_pipeline.py`,
  `tests/test_v2_contracts.py`, and `tests/test_maintenance_boundaries.py` —
  regression and boundary coverage.
- `README.md`, `docs/CONFIGURATION.md`, `docs/PIPELINE.md`, and
  `docs/v2-architecture.md` — operational and architecture documentation.

## 5. Compatibility and migrations

- Existing projects, episodes, scripts, timelines, visual records, manifests,
  and API consumers remain supported.
- Narrative-first generation is an internal orchestration change; its final
  output is still the existing `ScriptDocument` contract.
- Current stored research packs are not rewritten. Relevance filtering is a
  read-only projection at the script-generation boundary.
- New prompt stages and versions are additive generation-ledger records.
- Legacy environment variable behavior is retained where practical and current
  values are documented in `docs/CONFIGURATION.md`.
- Existing visual records that represent remote research leads remain readable;
  the UI now distinguishes them from locally renderable assets.
- No destructive data migration or automatic deletion of episode output was
  introduced.

## 6. Verification performed

The following checks were run against the current working tree:

| Check | Result |
|---|---|
| `make check` | passed |
| Configuration/doctor validation | passed; worker capacity reported as 3/3/3 |
| Python unit suite | 163 tests passed |
| Avatar Engine unit suite | 80 tests passed |
| Python `compileall` | passed |
| Remotion TypeScript check | passed |
| Studio TypeScript check | passed |
| Studio production build | passed |
| Lightweight TEST_MODE pipeline smoke | passed; 3 stages completed |
| Parallel TEST_MODE smoke | passed; 2 episodes completed concurrently |
| `git diff --check` | passed |
| Live Studio generation | completed through the Web UI |
| Browser console inspection | no errors |

The live narrative-first production test generated script revision v3 for
“India's Vimag Labs Cracks Rare Earth Monopoly With Magnet-Free Motor”:

- 596 spoken words
- estimated duration 246.62 seconds for a 250-second target
- seven presentation sections
- deterministic continuity/repetition check passed
- one Bengaluru/lab opening
- no spoken claim/evidence identifiers
- unrelated AI-policy, currency, diaspora, medical, and Iran material excluded
- left in `review`; it was not automatically approved

## 7. Intentionally deferred

- A full generated cross-language contract/code-generation system was not added;
  it would introduce disproportionate tooling and migration risk for the current
  repository.
- Existing production screens were not visually redesigned.
- Expensive Blender/avatar/full-production rendering was not added to the
  default unit suite.
- Legacy generation-ledger records were not deleted; they remain useful audit
  history.
- Broad module moves were avoided where they would create large import churn
  without improving a real boundary.

## 8. Remaining technical debt, prioritised

### P1 — research normalization

Future research extraction should promote useful factual context from legacy
`trade_offs`, dates, and number fields into addressable evidence-backed claims.
The generation boundary now prevents unlinked factual beats and excludes
unrelated contextual material, but normalizing older packs would improve the
quality of what is available to the writer.

### P1 — integration fixtures

Add sanitised fixtures from several real research packs and assert that unrelated
documents cannot influence the final narrative. Extend provider fallback tests
with recorded malformed/undersized hosted responses.

### P2 — visual provider depth

Add provider-specific download adapters for sites that require signed URLs,
browser negotiation, or page extraction. Keep them isolated behind the current
acquisition boundary.

### P2 — UI audit ergonomics

Add focused filtering to the generation ledger and make missing claim links
clickable from a section to its research evidence.

## 9. How to work on SynthPost now

1. Run `make doctor` to validate configuration and required tools.
2. Run `make dev` for local development or `make remote` for the private
   Tailscale Studio.
3. Use `make workers` to start the configured 3/3/3 lane pool separately.
4. Add or change domain contracts in `pipeline/models.py` and the shared
   `contracts/` definitions where they cross the HTTP boundary.
5. Add a script-generation behavior in `pipeline/scripts/generation.py`; keep
   narration drafting separate from segmentation and visual metadata.
6. Add visual sources/acquisition behavior in `pipeline/visuals/providers.py`;
   return explicit research-lead or verified-local-media state.
7. Add timeline behavior in `pipeline/timeline/`; do not bypass rights, file,
   template, or approval validation.
8. Add API transport in `pipeline/api/` and consume it through the typed Studio
   API client.
9. Run focused tests while editing, then `make check` before committing.

## 10. Manual verification recommended

- Read the v3 script aloud in the Studio and decide whether its pacing and
  editorial voice match SynthPost Signal.
- Verify the China export-control and Tesla production-status sentences against
  the source material before approving the script.
- Acquire and approve at least one image and one video through the Visuals tab,
  then confirm each appears in the timeline template preview.
- Run two unrelated projects concurrently and confirm the Jobs view shows lane
  parallelism while same-story work stays serialized.
- Render one short preview with an acquired visual and one with presenter
  fallback, approve the timeline, and perform a test assembly.

## Repository state

The earlier maintenance overhaul, parallel worker support, and timeline
previews are already on `main`. This report covers the subsequent
visual-acquisition and narrative-first hardening pass.
