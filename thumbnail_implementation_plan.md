# SynthPost Thumbnail Generator Implementation Plan

This plan turns the research and specs into a build sequence for the SynthPost codebase.

## Milestone 1: Manual Style Guide + Static Templates

Goal: establish the SynthPost thumbnail identity and render static template previews.

What to build:

- Add SynthPost thumbnail theme constants.
- Add Remotion thumbnail root and shared components.
- Implement 3 static templates first:
  - `AuthorityWarning`
  - `MoneyDealBomb`
  - `LogoCollision`
- Create sample hardcoded props for local preview.

Files/modules:

- `compositor/remotion_renderer/src/thumbnail/theme.ts`
- `compositor/remotion_renderer/src/thumbnail/types.ts`
- `compositor/remotion_renderer/src/thumbnail/ThumbnailRoot.tsx`
- `compositor/remotion_renderer/src/thumbnail/components/HeadlineBlock.tsx`
- `compositor/remotion_renderer/src/thumbnail/components/BrandMark.tsx`
- `compositor/remotion_renderer/src/thumbnail/templates/AuthorityWarning.tsx`
- `compositor/remotion_renderer/src/thumbnail/templates/MoneyDealBomb.tsx`
- `compositor/remotion_renderer/src/thumbnail/templates/LogoCollision.tsx`

Inputs:

- Static sample template props.
- Placeholder or approved local assets.

Outputs:

- 1280x720 PNG preview renders.
- 320x180 mobile preview renders.

Tests:

- Render command completes.
- Output dimensions are exactly 1280x720.
- Mobile preview files are generated.
- No template crashes when optional assets are missing.

Acceptance criteria:

- Three template previews look visually distinct and aligned with `synthpost_thumbnail_style_guide.md`.
- Main text remains readable at 160x90.
- No copied reference-channel border, bug, or yellow/black front-page frame.

## Milestone 2: Generate Thumbnails From JSON Briefs

Goal: turn `thumbnail_brief.json` into rendered candidates.

What to build:

- Python schema validation.
- Brief model dataclasses or Pydantic-style models.
- Template selection rules.
- Headline generation rules.
- Remotion render bridge.
- Candidate metadata output.

Files/modules:

- `src/synthpost/thumbnails/__init__.py`
- `src/synthpost/thumbnails/models.py`
- `src/synthpost/thumbnails/schema.py`
- `src/synthpost/thumbnails/planner.py`
- `src/synthpost/thumbnails/headlines.py`
- `src/synthpost/thumbnails/templates.py`
- `src/synthpost/thumbnails/render.py`
- `src/synthpost/thumbnails/cli.py`
- `thumbnail_brief.schema.json`

Inputs:

- `episodes/<episode>/thumbnail_brief.json`
- Local assets referenced by the brief.

Outputs:

- `episodes/<episode>/thumbnails/concepts/concept_01.json`
- `episodes/<episode>/thumbnails/renders/thumbnail_concept_01.png`
- `episodes/<episode>/thumbnails/thumbnail_candidates.json`

Tests:

- Valid brief passes schema validation.
- Invalid brief fails with useful error.
- Planner returns 3-5 concepts.
- Headline generator returns max 6 words.
- Render bridge creates files at expected paths.

Acceptance criteria:

- One CLI command renders at least three thumbnails from a JSON brief.
- Candidate metadata includes template ID, headline, visual hook, assets, and rationale.
- The generator can run without network access when all assets are provided.

## Milestone 3: Automatic Asset Selection

Goal: reduce manual asset assembly by selecting usable assets from local and existing visual sources.

What to build:

- Asset manifest format.
- Asset resolver using provided assets first.
- Local library lookup by subject name/type.
- Bridge to existing `src/synthpost/visuals` providers where appropriate.
- Asset quality checks.
- Basic cutout/preprocess workflow.

Files/modules:

- `src/synthpost/thumbnails/assets.py`
- `src/synthpost/thumbnails/preprocess.py`
- `assets/thumbnails/*/README.md`
- `assets/thumbnails/asset_manifest.schema.json` optional
- Reuse `src/synthpost/visuals/providers/*` where possible.

Inputs:

- `thumbnail_brief.json`
- Existing episode visual manifests.
- Local approved thumbnail asset library.

Outputs:

- Episode-local asset copies.
- Cutout PNGs.
- Preprocessed backgrounds.
- Asset provenance metadata.

Tests:

- Resolver prefers provided assets over library matches.
- Resolver rejects `do_not_use` assets.
- Logo files are not stretched.
- Cutout fallback path works when background removal is unavailable.
- Asset provenance is written.

Acceptance criteria:

- A brief with only subject names can locate at least logos/backgrounds from the local library.
- A brief with provided person images can render hero-person templates.
- All used external assets include source/license metadata.

## Milestone 4: Multiple Variants + Scoring

Goal: render, score, reject, and rank thumbnail candidates.

What to build:

- Image scoring module.
- Mobile downsample preview generator.
- Text safe-area checks.
- Duration badge collision check.
- Contrast heuristic.
- Simple clutter/logo-count heuristic.
- Brand consistency checks.
- A/B variant generator.

Files/modules:

- `src/synthpost/thumbnails/scoring.py`
- `src/synthpost/thumbnails/variants.py`
- `src/synthpost/thumbnails/render.py`
- `tests/test_thumbnail_scoring.py`

Inputs:

- Rendered PNG candidates.
- Concept metadata.
- Brief title and headline.

Outputs:

- Score breakdown per concept.
- Rejection warnings.
- `thumbnail_best.png`
- A/B variants.

Tests:

- Scoring returns 1-100.
- Rejection rules trigger for too many words.
- Rejection rules trigger for duration-badge collision.
- Low-contrast text is penalized.
- Best candidate is selected deterministically.

Acceptance criteria:

- Weak candidates under 72 are rejected.
- Best candidate is chosen automatically.
- Score metadata explains why the candidate won.
- The system produces at least one A/B variant by changing only one major variable.

## Milestone 5: Integration Into SynthPost Video Pipeline

Goal: make thumbnails a normal artifact of every SynthPost episode.

What to build:

- Default thumbnail brief builder from story/episode metadata.
- Pipeline step after script/visual planning and before upload.
- Optional human review checkpoint.
- Upload-ready final thumbnail path in episode manifest.
- Failure fallback: render a conservative template with title and approved background.

Files/modules:

- `pipeline/thumbnails/default.py`
- `pipeline/run_episode.py`
- `pipeline/schemas/story_manifest.schema.json` update if needed
- `episodes/<episode>/thumbnail_brief.json`
- `episodes/<episode>/thumbnails/thumbnail_best.png`

Inputs:

- Episode story JSON.
- Video title.
- Episode headline.
- Visual manifest assets.
- Brand assets.

Outputs:

- Final selected thumbnail.
- Thumbnail metadata path attached to episode artifact.
- Optional upload integration value.

Tests:

- End-to-end dry run creates a thumbnail from a sample episode.
- Existing episode runs do not break if thumbnail generation is disabled.
- Missing assets trigger fallback, not crash.
- Final output path is stored in episode metadata.

Acceptance criteria:

- Running the episode pipeline can generate a thumbnail without manual intervention.
- Human reviewer can inspect 3-5 variants and the recommended best.
- Thumbnail generation failure does not block the full episode unless configured as required.

## Suggested Build Order

1. Create Remotion thumbnail root and three templates.
2. Add schema validation and sample brief.
3. Render from JSON.
4. Add all 12 templates.
5. Add local asset resolver.
6. Add scoring and mobile previews.
7. Add pipeline integration.
8. Add asset provenance and compliance checks.

## Initial Test Briefs

Create three fixtures:

1. AI warning:
   - Main subject: Satya Nadella.
   - Emotion: urgent.
   - Expected template: `authority_warning`.

2. India manufacturing boom:
   - Main subjects: India, factory, exports.
   - Emotion: optimistic.
   - Expected template: `factory_boom` or `map_crisis_marker`.

3. AI model competition:
   - Main subjects: OpenAI, Anthropic, Google.
   - Emotion: analytical.
   - Expected template: `logo_collision`.

## Definition of Done for v1

The v1 generator is done when:

- `python -m synthpost.thumbnails.cli render <brief>` works locally.
- At least 10 templates render without crashing.
- Each run outputs 3-5 candidates plus `thumbnail_best.png`.
- Each candidate includes score and rationale.
- The best candidate passes mobile readability checks.
- All final images are 1280x720 PNGs.
- The system is documented enough for another Codex session to implement or extend it.

