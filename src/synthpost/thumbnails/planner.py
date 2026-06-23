from __future__ import annotations

from .headlines import accent_words, default_headlines
from .models import RENDERABLE_TEMPLATES, TOPIC_TO_TEMPLATES, ThumbnailAsset, ThumbnailBrief, ThumbnailConcept


FALLBACK_BACKGROUND = ThumbnailAsset(
    id="fallback_synthpost_gradient",
    path_or_url="brand/synthpost-gradient-landscape.png",
    type="background_image",
    usage_status="approved",
    label="SynthPost brand gradient background",
)


def _candidate_templates(brief: ThumbnailBrief) -> list[str]:
    preferred = brief.render_preferences.get("preferred_templates")
    if isinstance(preferred, list) and preferred:
        templates = [str(template) for template in preferred]
    else:
        templates = TOPIC_TO_TEMPLATES.get(brief.topic.lower(), ["authority_warning", "money_deal_bomb", "logo_collision"])

    # v1 renders a focused subset. Preserve the intent by mapping close templates to available ones.
    mapped: list[str] = []
    for template in templates:
        if template in RENDERABLE_TEMPLATES:
            mapped.append(template)
        elif template in {"factory_boom", "infrastructure_race", "inside_the_deal"}:
            mapped.append("money_deal_bomb")
        elif template in {"agent_swarm", "document_exposed"}:
            mapped.append("authority_warning")
        elif template in {"map_crisis_marker", "sovereign_ai_stack"}:
            mapped.append("logo_collision")
        elif template in {"device_shock"}:
            mapped.append("clean_market_surge")
    for fallback in ["authority_warning", "money_deal_bomb", "logo_collision"]:
        if fallback not in mapped:
            mapped.append(fallback)
    return mapped


def _assets_for_template(brief: ThumbnailBrief, template_id: str) -> list[ThumbnailAsset]:
    assets = list(brief.assets)
    if not any(asset.type in {"background_image", "generated_background", "map"} for asset in assets):
        assets.append(
            ThumbnailAsset(
                id="synthpost_gradient_context",
                path_or_url="brand/synthpost-gradient-landscape.png",
                type="background_image",
                usage_status="approved",
                label="SynthPost brand gradient",
            )
        )
    return assets


def plan_concepts(brief: ThumbnailBrief, *, count: int | None = None) -> list[ThumbnailConcept]:
    target_count = count or int(brief.render_preferences.get("candidate_count", 3) or 3)
    target_count = max(1, min(target_count, 5))
    templates = _candidate_templates(brief)
    headlines = default_headlines(brief)
    concepts: list[ThumbnailConcept] = []
    for index in range(target_count):
        template_id = templates[index % len(templates)]
        headline = headlines[index % len(headlines)]
        concept = ThumbnailConcept(
            brief_id=brief.brief_id,
            concept_id=f"concept_{index + 1:02d}",
            template_id=template_id,
            headline_text=headline,
            subtitle_text=brief.stakes or brief.curiosity_gap,
            video_title=brief.video_title,
            episode_headline=brief.episode_headline,
            topic=brief.topic,
            emotion=brief.emotion,
            main_subjects=brief.main_subjects,
            key_numbers=brief.key_numbers,
            assets=_assets_for_template(brief, template_id),
            accent_words=accent_words(headline, brief.emotion),
            visual_hook=_visual_hook(template_id, brief),
            rationale=_rationale(template_id, brief),
        )
        concepts.append(concept)
    return concepts


def _visual_hook(template_id: str, brief: ThumbnailBrief) -> str:
    subject = brief.main_subjects[0].name if brief.main_subjects else "the main subject"
    if template_id == "money_deal_bomb":
        return f"Large proof number and {subject} against infrastructure context."
    if template_id == "clean_market_surge":
        return f"Clean editorial market-surge layout with {subject}, a symbolic prop, and upward motion."
    if template_id == "logo_collision":
        return "Two-sided technology conflict with clear brand or subject cards."
    return f"Authority-led warning frame centered on {subject}."


def _rationale(template_id: str, brief: ThumbnailBrief) -> str:
    if template_id == "money_deal_bomb":
        return "A concrete number makes the business stakes readable on mobile."
    if template_id == "clean_market_surge":
        return "A clean white editorial canvas, celebrity subject, symbolic object, and upward chart motion make the momentum story obvious."
    if template_id == "logo_collision":
        return "A direct comparison or conflict creates an immediate curiosity gap."
    return "A recognizable authority plus a concise warning creates urgency and credibility."
