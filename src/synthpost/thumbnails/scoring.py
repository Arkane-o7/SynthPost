from __future__ import annotations

from pathlib import Path

from PIL import Image

from .headlines import word_count
from .models import ThumbnailConcept


WEIGHTS = {
    "mobile_readability": 1.4,
    "subject_clarity": 1.2,
    "curiosity_gap": 1.2,
    "emotional_tension": 1.0,
    "topic_relevance": 1.0,
    "brand_consistency": 0.9,
    "visual_contrast": 0.9,
    "simplicity": 0.8,
    "title_thumbnail_synergy": 1.0,
    "premium_feel": 0.6,
}


def score_concept(concept: ThumbnailConcept, rendered_path: str | Path | None = None) -> ThumbnailConcept:
    words = word_count(concept.headline_text)
    has_subject = bool(concept.main_subjects)
    has_background = any(asset.type in {"background_image", "generated_background", "map"} for asset in concept.assets)
    has_deal_number = any(
        ("$" in str(item.get("value", "")))
        or ("%" in str(item.get("value", "")))
        or any(word in str(item.get("value", "")).lower() for word in ["billion", "million", "crore", "lakh", "trillion"])
        or any(word in str(item.get("label", "")).lower() for word in ["deal", "capex", "valuation", "market", "exports", "ipo"])
        for item in concept.key_numbers
        if isinstance(item, dict)
    )
    has_render = rendered_path is not None and Path(rendered_path).exists()

    breakdown = {
        "mobile_readability": 9 if words <= 4 else 8 if words <= 6 else 4,
        "subject_clarity": 8 if has_subject else 5,
        "curiosity_gap": 8 if concept.subtitle_text or concept.visual_hook else 7,
        "emotional_tension": 9 if concept.emotion in {"urgent", "warning", "shocking", "conflict"} else 7,
        "topic_relevance": 8 if has_background or has_subject else 6,
        "brand_consistency": 9,
        "visual_contrast": 8,
        "simplicity": 9 if words <= 5 else 6,
        "title_thumbnail_synergy": 8 if concept.headline_text.upper() not in concept.video_title.upper() else 6,
        "premium_feel": 8 if has_render else 7,
    }
    if concept.template_id == "money_deal_bomb" and has_deal_number:
        breakdown["curiosity_gap"] = min(10, breakdown["curiosity_gap"] + 1)
        breakdown["subject_clarity"] = min(10, breakdown["subject_clarity"] + 1)
    elif concept.template_id == "money_deal_bomb":
        breakdown["topic_relevance"] = max(0, breakdown["topic_relevance"] - 1)
    if concept.template_id == "clean_market_surge":
        breakdown["topic_relevance"] = min(10, breakdown["topic_relevance"] + 1)
        breakdown["premium_feel"] = min(10, breakdown["premium_feel"] + 1)
    if rendered_path and Path(rendered_path).exists():
        try:
            image = Image.open(rendered_path)
            if image.size != (1280, 720):
                concept.warnings.append(f"Rendered image has unexpected size: {image.size}")
                breakdown["premium_feel"] = max(0, breakdown["premium_feel"] - 2)
        except Exception as exc:  # pragma: no cover - defensive check
            concept.warnings.append(f"Could not inspect rendered image: {exc}")
            breakdown["premium_feel"] = max(0, breakdown["premium_feel"] - 2)

    if words > 6:
        concept.warnings.append("Main thumbnail text exceeds 6 words.")
    if not has_subject:
        concept.warnings.append("Concept has no main subject.")
    if not has_background:
        concept.warnings.append("Concept has no contextual background asset.")

    score = round(sum(breakdown[key] * weight for key, weight in WEIGHTS.items()))
    concept.score = max(1, min(score, 100))
    concept.score_breakdown = breakdown
    return concept


def rejection_reasons(concept: ThumbnailConcept, *, min_score: int = 72) -> list[str]:
    reasons: list[str] = []
    score = concept.score or 0
    if score < min_score:
        reasons.append(f"score_below_threshold:{score}<{min_score}")
    if concept.score_breakdown.get("mobile_readability", 0) < 7:
        reasons.append("weak_mobile_readability")
    if concept.score_breakdown.get("subject_clarity", 0) < 7:
        reasons.append("weak_subject_clarity")
    if concept.score_breakdown.get("visual_contrast", 0) < 7:
        reasons.append("weak_visual_contrast")
    if word_count(concept.headline_text) > 6:
        reasons.append("too_many_words")
    return [*reasons, *concept.warnings]
