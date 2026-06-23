from __future__ import annotations

import argparse
import json
from pathlib import Path

from .assets import resolve_brief_assets, write_resolved_brief_record
from .models import PROJECT_ROOT
from .planner import plan_concepts
from .render import render_concept, select_candidate, write_candidates, write_concept
from .schema import load_brief
from .scoring import score_concept


def _default_output_dir(brief_path: Path) -> Path:
    if brief_path.name == "thumbnail_brief.json":
        return brief_path.parent / "thumbnails"
    return brief_path.parent / f"{brief_path.stem}_thumbnails"


def cmd_validate(args: argparse.Namespace) -> None:
    brief = load_brief(args.brief)
    print(json.dumps({"valid": True, "brief_id": brief.brief_id, "subject_count": len(brief.main_subjects)}, indent=2))


def cmd_plan(args: argparse.Namespace) -> None:
    brief_path = Path(args.brief).expanduser()
    if not brief_path.is_absolute():
        brief_path = PROJECT_ROOT / brief_path
    brief = load_brief(brief_path)
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else _default_output_dir(brief_path)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    concepts = plan_concepts(brief, count=args.count)
    for concept in concepts:
        write_concept(concept, output_dir / "concepts" / f"{concept.concept_id}.json")
    write_candidates(concepts, output_dir)
    print(json.dumps({"planned": len(concepts), "output_dir": output_dir.as_posix()}, indent=2))


def cmd_resolve_assets(args: argparse.Namespace) -> None:
    brief_path = Path(args.brief).expanduser()
    if not brief_path.is_absolute():
        brief_path = PROJECT_ROOT / brief_path
    brief = load_brief(brief_path)
    resolved, selected = resolve_brief_assets(brief, library_path=args.asset_library)
    output_path = Path(args.output).expanduser() if args.output else brief_path.with_name(f"{brief_path.stem}_resolved.json")
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    write_resolved_brief_record(resolved, output_path, selected=selected)
    print(
        json.dumps(
            {
                "brief_id": brief.brief_id,
                "selected_assets": [
                    {"asset_id": match.asset.id, "score": match.score, "reasons": match.reasons}
                    for match in selected
                ],
                "output": output_path.relative_to(PROJECT_ROOT).as_posix(),
            },
            indent=2,
        )
    )


def cmd_render(args: argparse.Namespace) -> None:
    brief_path = Path(args.brief).expanduser()
    if not brief_path.is_absolute():
        brief_path = PROJECT_ROOT / brief_path
    brief = load_brief(brief_path)
    selected_assets = []
    if args.auto_assets:
        brief, selected_assets = resolve_brief_assets(brief, library_path=args.asset_library)
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else _default_output_dir(brief_path)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    concepts = plan_concepts(brief, count=args.count)
    for concept in concepts:
        rendered = render_concept(concept, output_dir)
        score_concept(concept, rendered)
        write_concept(concept, output_dir / "concepts" / f"{concept.concept_id}.json")
    viable = [concept for concept in concepts if (concept.score or 0) >= args.min_score]
    recommended = max(viable or concepts, key=lambda concept: concept.score or 0)
    candidates_path = write_candidates(
        concepts,
        output_dir,
        recommended=recommended,
        min_score=args.min_score,
        auto_select=not args.manual_review,
    )
    if args.auto_assets:
        write_resolved_brief_record(brief, output_dir / "thumbnail_brief_resolved.json", selected=selected_assets)
    print(
        json.dumps(
            {
                "rendered": len(concepts),
                "recommended_concept_id": recommended.concept_id,
                "recommended_score": recommended.score,
                "selected_assets": [
                    {"asset_id": match.asset.id, "score": match.score, "reasons": match.reasons}
                    for match in selected_assets
                ],
                "candidates_path": candidates_path.relative_to(PROJECT_ROOT).as_posix(),
                "best_path": (output_dir / "thumbnail_best.png").relative_to(PROJECT_ROOT).as_posix()
                if not args.manual_review
                else None,
                "selection_required": bool(args.manual_review),
            },
            indent=2,
        )
    )


def cmd_select(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    best = select_candidate(output_dir, args.concept_id)
    print(
        json.dumps(
            {
                "selected_concept_id": args.concept_id,
                "best_path": best.relative_to(PROJECT_ROOT).as_posix(),
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan and render SynthPost thumbnails.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a thumbnail brief.")
    validate.add_argument("brief")
    validate.set_defaults(func=cmd_validate)

    plan = sub.add_parser("plan", help="Create concept JSON files from a thumbnail brief.")
    plan.add_argument("brief")
    plan.add_argument("--count", type=int, default=None)
    plan.add_argument("--output-dir", default=None)
    plan.set_defaults(func=cmd_plan)

    resolve_assets = sub.add_parser("resolve-assets", help="Select approved local/generated assets for a thumbnail brief.")
    resolve_assets.add_argument("brief")
    resolve_assets.add_argument("--asset-library", default=None)
    resolve_assets.add_argument("--output", default=None)
    resolve_assets.set_defaults(func=cmd_resolve_assets)

    render = sub.add_parser("render", help="Render thumbnail candidates from a thumbnail brief.")
    render.add_argument("brief")
    render.add_argument("--count", type=int, default=None)
    render.add_argument("--output-dir", default=None)
    render.add_argument("--min-score", type=int, default=72)
    render.add_argument("--auto-assets", action="store_true", help="Select matching approved assets before planning concepts.")
    render.add_argument("--asset-library", default=None)
    render.add_argument(
        "--manual-review",
        action="store_true",
        help="Render candidates and recommendations, but do not copy any candidate to thumbnail_best.png.",
    )
    render.set_defaults(func=cmd_render)

    select = sub.add_parser("select", help="Choose a rendered candidate as thumbnail_best.png.")
    select.add_argument("output_dir")
    select.add_argument("concept_id")
    select.set_defaults(func=cmd_select)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
