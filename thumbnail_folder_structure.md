# Recommended Thumbnail Folder Structure

This structure keeps reusable brand assets separate from per-episode generated outputs and keeps the renderer connected to the existing Remotion compositor.

```text
SynthPost/
  assets/
    brand/
      synthpost_logo.svg
      synthpost_monogram.svg
      fonts/
        ArchivoBlack.ttf
        InterVariable.ttf
    thumbnails/
      people/
        README.md
      logos/
        README.md
      backgrounds/
        ai/
        economy/
        geopolitics/
        infrastructure/
        culture/
      maps/
        world_dark.svg
        india_dark.svg
      objects/
        chips/
        phones/
        documents/
        servers/
      generated/
        README.md
  compositor/
    remotion_renderer/
      src/
        thumbnail/
          ThumbnailRoot.tsx
          theme.ts
          types.ts
          layout.ts
          components/
            BrandMark.tsx
            HeadlineBlock.tsx
            SubjectCutout.tsx
            LogoCard.tsx
            MoneyNumber.tsx
            MapLayer.tsx
            Stamp.tsx
            GrainOverlay.tsx
          templates/
            AuthorityWarning.tsx
            GlobalAIFaceoff.tsx
            SovereignAIStack.tsx
            MoneyDealBomb.tsx
            MapCrisisMarker.tsx
            FactoryBoom.tsx
            LogoCollision.tsx
            DeviceShock.tsx
            AgentSwarm.tsx
            DocumentExposed.tsx
            InfrastructureRace.tsx
            InsideTheDeal.tsx
  src/
    synthpost/
      thumbnails/
        __init__.py
        models.py
        schema.py
        planner.py
        headlines.py
        templates.py
        assets.py
        preprocess.py
        render.py
        scoring.py
        variants.py
        cli.py
  pipeline/
    thumbnails/
      __init__.py
      default.py
  episodes/
    ep_YYYY-MM-DD-slug/
      thumbnail_brief.json
      thumbnails/
        assets/
          people/
          logos/
          backgrounds/
          cutouts/
        concepts/
          concept_01.json
          concept_02.json
          concept_03.json
        renders/
          thumbnail_concept_01.png
          thumbnail_concept_02.png
          thumbnail_concept_03.png
          thumbnail_concept_01_mobile_320.jpg
          thumbnail_concept_01_mobile_160.jpg
        thumbnail_candidates.json
        thumbnail_best.png
  tests/
    test_thumbnail_schema.py
    test_thumbnail_planner.py
    test_thumbnail_scoring.py
    test_thumbnail_render_contract.py
```

## File Responsibilities

### `assets/brand/`

Stores SynthPost-owned visual identity assets only. These should be reusable and stable.

### `assets/thumbnails/`

Reusable approved thumbnail assets:

- People with usage notes.
- Logos with source/license metadata.
- Generic backgrounds and symbolic objects.
- Maps and icons.

Each asset directory should include a README or manifest describing licensing and allowed use.

### `src/synthpost/thumbnails/`

Python orchestration layer:

- Validate briefs.
- Select templates.
- Generate headline candidates.
- Resolve and preprocess assets.
- Call Remotion render command.
- Score outputs.
- Select best variant.

### `compositor/remotion_renderer/src/thumbnail/`

React/Remotion rendering layer:

- Template components.
- Shared brand components.
- CSS theme.
- Layout helper functions.

### `episodes/.../thumbnails/`

Per-episode working directory:

- Local copies of all assets actually used.
- Rendered concepts.
- Mobile previews.
- Scoring metadata.
- Final selected thumbnail.

## Naming Rules

Brief:

```text
episodes/ep_YYYY-MM-DD-slug/thumbnail_brief.json
```

Concept metadata:

```text
episodes/ep_YYYY-MM-DD-slug/thumbnails/concepts/concept_01.json
```

Rendered files:

```text
thumbnail_concept_01.png
thumbnail_concept_01_mobile_320.jpg
thumbnail_concept_01_mobile_160.jpg
thumbnail_best.png
thumbnail_candidates.json
```

Asset files:

```text
person_satya_nadella_2026-06-23_source.jpg
logo_microsoft_official.svg
background_data_center_generated_v1.png
cutout_satya_nadella_concept_01.png
```

## Metadata Sidecars

Every generated render should have a metadata record:

```json
{
  "concept_id": "concept_01",
  "template_id": "authority_warning",
  "headline_text": "SATYA'S AI WARNING",
  "assets_used": [],
  "score": 88,
  "warnings": [],
  "rendered_png": "renders/thumbnail_concept_01.png",
  "mobile_previews": [
    "renders/thumbnail_concept_01_mobile_320.jpg",
    "renders/thumbnail_concept_01_mobile_160.jpg"
  ]
}
```

## Local Research Artifacts

The AIM reference assets used for research are stored separately:

```text
research/
  thumbnail_analysis/
    aim_reference/
      aim_60_recent_metadata.json
      aim_60_recent_metadata.tsv
      thumbnails/
      contact_sheets/
```

These reference files are for research only. They should not be used as SynthPost template assets.

