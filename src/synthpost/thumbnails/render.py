from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image

from .models import PROJECT_ROOT, ThumbnailConcept
from .scoring import rejection_reasons


REMOTION_DIR = PROJECT_ROOT / "compositor" / "remotion_renderer"


def write_concept(concept: ThumbnailConcept, concept_path: Path) -> Path:
    concept_path.parent.mkdir(parents=True, exist_ok=True)
    with concept_path.open("w", encoding="utf-8") as handle:
        json.dump(concept.to_renderer_record(), handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return concept_path


def render_concept(concept: ThumbnailConcept, output_dir: Path) -> Path:
    concept_dir = output_dir / "concepts"
    render_dir = output_dir / "renders"
    concept_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)
    concept.output_path = (render_dir / f"{concept.concept_id}.png").relative_to(PROJECT_ROOT).as_posix()
    concept_path = write_concept(concept, concept_dir / f"{concept.concept_id}.json")
    result = subprocess.run(
        ["npm", "run", "render:thumbnail", "--", str(concept_path)],
        cwd=REMOTION_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Thumbnail render failed:\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
    rendered = PROJECT_ROOT / concept.output_path
    concept.rendered_png = concept.output_path
    _write_mobile_previews(rendered)
    # Renderer updates staged asset paths; keep the richer JSON on disk but refresh score fields later.
    return rendered


def write_candidates(
    concepts: list[ThumbnailConcept],
    output_dir: Path,
    recommended: ThumbnailConcept | None = None,
    *,
    min_score: int = 72,
    auto_select: bool = True,
    visual_asset_candidates: dict | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    accepted = [concept for concept in concepts if not rejection_reasons(concept, min_score=min_score)]
    rejected = [
        {
            "concept_id": concept.concept_id,
            "score": concept.score,
            "reasons": rejection_reasons(concept, min_score=min_score),
        }
        for concept in concepts
        if rejection_reasons(concept, min_score=min_score)
    ]
    contact_sheet = _write_contact_sheet(concepts, output_dir)
    payload = {
        "recommended_concept_id": recommended.concept_id if recommended else None,
        "recommended_png": recommended.rendered_png if recommended else None,
        "selected_concept_id": recommended.concept_id if recommended and auto_select else None,
        "selected_png": recommended.rendered_png if recommended and auto_select else None,
        "selection": {
            "mode": "auto" if auto_select else "manual_review",
            "selection_required": not auto_select,
            "recommended_concept_id": recommended.concept_id if recommended else None,
            "selected_concept_id": recommended.concept_id if recommended and auto_select else None,
            "instructions": "Review the contact sheet or renders, then run `python3 -m synthpost.thumbnails.cli select <output_dir> <concept_id>`.",
        },
        "contact_sheet": contact_sheet.relative_to(PROJECT_ROOT).as_posix() if contact_sheet else None,
        "quality_gate": {
            "min_score": min_score,
            "passed": bool(recommended and (recommended.score or 0) >= min_score),
            "accepted_concept_ids": [concept.concept_id for concept in accepted],
            "rejected": rejected,
        },
        "visual_asset_candidates": visual_asset_candidates,
        "ab_test_variants": [
            {
                "concept_id": concept.concept_id,
                "template_id": concept.template_id,
                "headline_text": concept.headline_text,
                "score": concept.score,
                "png": concept.rendered_png,
            }
            for concept in sorted(concepts, key=lambda item: item.score or 0, reverse=True)
        ],
        "concepts": [concept.to_renderer_record() for concept in concepts],
    }
    payload = {key: value for key, value in payload.items() if value not in (None, "", [], {})}
    path = output_dir / "thumbnail_candidates.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    if recommended and recommended.rendered_png and auto_select:
        best = output_dir / "thumbnail_best.png"
        best.write_bytes((PROJECT_ROOT / recommended.rendered_png).read_bytes())
    return path


def select_candidate(output_dir: Path, concept_id: str) -> Path:
    resolved_dir = output_dir if output_dir.is_absolute() else PROJECT_ROOT / output_dir
    candidates_path = resolved_dir / "thumbnail_candidates.json"
    if not candidates_path.exists():
        raise FileNotFoundError(f"Missing thumbnail candidates manifest: {candidates_path}")
    with candidates_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    variants = payload.get("ab_test_variants", [])
    variant = next((item for item in variants if item.get("concept_id") == concept_id), None)
    if not variant:
        raise ValueError(f"Unknown concept_id `{concept_id}`. Available: {[item.get('concept_id') for item in variants]}")
    png = variant.get("png")
    if not png:
        raise ValueError(f"Candidate `{concept_id}` has no rendered PNG.")
    source = PROJECT_ROOT / png
    if not source.exists():
        raise FileNotFoundError(f"Missing rendered PNG for `{concept_id}`: {source}")
    best = resolved_dir / "thumbnail_best.png"
    best.write_bytes(source.read_bytes())
    payload["selected_concept_id"] = concept_id
    payload["selected_png"] = png
    payload["selection"] = {
        **payload.get("selection", {}),
        "mode": "manual_selected",
        "selection_required": False,
        "selected_concept_id": concept_id,
        "selected_png": png,
    }
    with candidates_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return best


def _write_mobile_previews(rendered: Path) -> None:
    if not rendered.exists():
        return
    image = Image.open(rendered).convert("RGB")
    for width, height in [(320, 180), (160, 90)]:
        preview = image.resize((width, height), Image.Resampling.LANCZOS)
        preview.save(rendered.with_name(f"{rendered.stem}_mobile_{width}.jpg"), quality=88)


def _write_contact_sheet(concepts: list[ThumbnailConcept], output_dir: Path) -> Path | None:
    rendered = [PROJECT_ROOT / concept.rendered_png for concept in concepts if concept.rendered_png]
    rendered = [path for path in rendered if path.exists()]
    if not rendered:
        return None
    thumb_width, thumb_height = 320, 180
    gutter = 18
    label_height = 54
    sheet_width = (thumb_width * len(rendered)) + (gutter * (len(rendered) + 1))
    sheet_height = thumb_height + label_height + (gutter * 2)
    sheet = Image.new("RGB", (sheet_width, sheet_height), "#F8F6F1")
    for index, path in enumerate(rendered):
        image = Image.open(path).convert("RGB").resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = gutter + index * (thumb_width + gutter)
        y = gutter
        sheet.paste(image, (x, y))
    output_path = output_dir / "thumbnail_contact_sheet.jpg"
    sheet.save(output_path, quality=90)
    return output_path
