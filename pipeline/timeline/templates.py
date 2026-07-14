from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    name: str
    description: str
    component: str
    supported_media_types: list[str]
    supported_content_roles: list[str]
    anchor_visible: bool | None
    anchor_speaking: bool | None
    visual_audio_policy: str
    required_fields: list[str] = field(default_factory=list)
    default_duration: float = 8.0
    compatible_aspect_ratios: list[str] = field(default_factory=lambda: ["16:9"])
    fallback_template_id: str = "fallback_anchor"
    editor_preview_icon: str = "frame"
    validation_rules: list[str] = field(default_factory=list)
    production_enabled: bool = True
    blacklist_reason: str | None = None


BLACKLISTED_CARD_REASON = (
    "Blacklisted for production until the explainer/card graphics are redesigned "
    "to meet the SynthPost broadcast polish bar. Quote card remains allowed."
)


TEMPLATE_REGISTRY: dict[str, TemplateDefinition] = {
    "split_anchor_visual": TemplateDefinition(
        template_id="split_anchor_visual",
        name="Split Anchor + Visual",
        description="Anchor narrates while approved supporting media plays muted.",
        component="TimelineStory.SplitAnchorVisual",
        supported_media_types=[
            "image",
            "video",
            "document",
            "chart",
            "map",
            "fallback",
        ],
        supported_content_roles=[
            "primary_footage",
            "context",
            "evidence",
            "explanation",
            "location",
            "person",
            "document",
            "data",
            "atmosphere",
            "fallback",
        ],
        anchor_visible=True,
        anchor_speaking=True,
        visual_audio_policy="muted",
        required_fields=["script_text"],
        editor_preview_icon="split",
        validation_rules=[
            "supporting_video_muted_by_default",
            "attribution_visible_when_required",
        ],
    ),
    "fullscreen_news_visual": TemplateDefinition(
        template_id="fullscreen_news_visual",
        name="Full-Screen News Visual",
        description="Primary footage or important source clip fills the screen.",
        component="TimelineStory.FullscreenNewsVisual",
        supported_media_types=["image", "video"],
        supported_content_roles=[
            "primary_footage",
            "evidence",
            "context",
            "atmosphere",
        ],
        anchor_visible=False,
        anchor_speaking=False,
        visual_audio_policy="source_or_muted",
        required_fields=["visual.path", "overlays.attribution"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="video",
        validation_rules=[
            "source_audio_requires_audio_mode_source_or_mixed",
            "attribution_required",
        ],
    ),
    "fullscreen_anchor": TemplateDefinition(
        template_id="fullscreen_anchor",
        name="Full-Screen Anchor",
        description="Direct address opening, closing, or transition.",
        component="TimelineStory.FullscreenAnchor",
        supported_media_types=["fallback", "image"],
        supported_content_roles=["fallback", "context"],
        anchor_visible=True,
        anchor_speaking=True,
        visual_audio_policy="narration_only",
        required_fields=["script_text"],
        fallback_template_id="fallback_anchor",
        editor_preview_icon="anchor",
    ),
    "fallback_anchor": TemplateDefinition(
        template_id="fallback_anchor",
        name="Fallback Anchor",
        description="Safe anchor-only fallback for missing visuals.",
        component="TimelineStory.FullscreenAnchor",
        supported_media_types=["fallback", "image"],
        supported_content_roles=["fallback", "context"],
        anchor_visible=True,
        anchor_speaking=True,
        visual_audio_policy="narration_only",
        required_fields=["script_text"],
        editor_preview_icon="anchor",
    ),
    "quote_card": TemplateDefinition(
        template_id="quote_card",
        name="Quote Card",
        description="Editorial quote card with clear source attribution.",
        component="TimelineStory.QuoteCard",
        supported_media_types=["fallback", "image"],
        supported_content_roles=["evidence", "context"],
        anchor_visible=None,
        anchor_speaking=None,
        visual_audio_policy="muted",
        required_fields=["overlays.quote_text", "overlays.attribution"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="quote",
        validation_rules=["quote_requires_claim", "quote_requires_attribution"],
    ),
    "document_callout": TemplateDefinition(
        template_id="document_callout",
        name="Document Callout",
        description="Report, filing, statement, or research-paper excerpt.",
        component="TimelineStory.DocumentCallout",
        supported_media_types=["document", "image", "fallback"],
        supported_content_roles=["document", "evidence"],
        anchor_visible=True,
        anchor_speaking=True,
        visual_audio_policy="muted",
        required_fields=["visual.path", "overlays.document_source"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="document",
        validation_rules=["document_source_required"],
        production_enabled=False,
        blacklist_reason=BLACKLISTED_CARD_REASON,
    ),
    "chart_explainer": TemplateDefinition(
        template_id="chart_explainer",
        name="Chart Explainer",
        description="Structured chart graphic for numbers or trends.",
        component="TimelineStory.ChartExplainer",
        supported_media_types=["chart", "fallback", "image"],
        supported_content_roles=["data", "explanation"],
        anchor_visible=False,
        anchor_speaking=True,
        visual_audio_policy="narration_only",
        required_fields=["overlays.data"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="chart",
        production_enabled=False,
        blacklist_reason=BLACKLISTED_CARD_REASON,
    ),
    "map_explainer": TemplateDefinition(
        template_id="map_explainer",
        name="Map Explainer",
        description="Structured location or route explainer.",
        component="TimelineStory.MapExplainer",
        supported_media_types=["map", "fallback", "image"],
        supported_content_roles=["location", "explanation"],
        anchor_visible=False,
        anchor_speaking=True,
        visual_audio_policy="narration_only",
        required_fields=["overlays.data"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="map",
        production_enabled=False,
        blacklist_reason=BLACKLISTED_CARD_REASON,
    ),
    "timeline_explainer": TemplateDefinition(
        template_id="timeline_explainer",
        name="Timeline Explainer",
        description="Chronological event graphic.",
        component="TimelineStory.TimelineExplainer",
        supported_media_types=["fallback", "image"],
        supported_content_roles=["explanation", "context"],
        anchor_visible=False,
        anchor_speaking=True,
        visual_audio_policy="narration_only",
        required_fields=["overlays.data"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="timeline",
        production_enabled=False,
        blacklist_reason=BLACKLISTED_CARD_REASON,
    ),
    "comparison_card": TemplateDefinition(
        template_id="comparison_card",
        name="Comparison Card",
        description="Two-column contrast for policies, companies, or options.",
        component="TimelineStory.ComparisonCard",
        supported_media_types=["fallback", "image"],
        supported_content_roles=["explanation", "data", "context"],
        anchor_visible=False,
        anchor_speaking=True,
        visual_audio_policy="narration_only",
        required_fields=["overlays.data"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="compare",
        production_enabled=False,
        blacklist_reason=BLACKLISTED_CARD_REASON,
    ),
    "bullet_summary": TemplateDefinition(
        template_id="bullet_summary",
        name="Bullet Summary",
        description="Clean branded summary card.",
        component="TimelineStory.BulletSummary",
        supported_media_types=["fallback", "image"],
        supported_content_roles=["explanation", "context", "fallback"],
        anchor_visible=False,
        anchor_speaking=True,
        visual_audio_policy="narration_only",
        required_fields=["overlays.data"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="bullets",
        production_enabled=False,
        blacklist_reason=BLACKLISTED_CARD_REASON,
    ),
    "source_screenshot": TemplateDefinition(
        template_id="source_screenshot",
        name="Source Screenshot",
        description="A source page or screenshot with attribution.",
        component="TimelineStory.SourceScreenshot",
        supported_media_types=["image", "document"],
        supported_content_roles=["document", "evidence"],
        anchor_visible=False,
        anchor_speaking=True,
        visual_audio_policy="muted",
        required_fields=["visual.path", "overlays.attribution"],
        fallback_template_id="split_anchor_visual",
        editor_preview_icon="screenshot",
        production_enabled=False,
        blacklist_reason=BLACKLISTED_CARD_REASON,
    ),
    "fallback_context_card": TemplateDefinition(
        template_id="fallback_context_card",
        name="Fallback Context Card",
        description="Branded editorial graphic when no strong visual is available.",
        component="TimelineStory.FallbackContextCard",
        supported_media_types=["fallback", "image"],
        supported_content_roles=["fallback", "context", "explanation"],
        anchor_visible=False,
        anchor_speaking=True,
        visual_audio_policy="narration_only",
        required_fields=["script_text"],
        fallback_template_id="fallback_anchor",
        editor_preview_icon="context",
        production_enabled=False,
        blacklist_reason=BLACKLISTED_CARD_REASON,
    ),
}


def get_template(template_id: str) -> TemplateDefinition:
    if template_id not in TEMPLATE_REGISTRY:
        raise KeyError(f"Unknown template_id: {template_id}")
    return TEMPLATE_REGISTRY[template_id]


def template_registry_json(production_only: bool = True) -> list[dict[str, Any]]:
    templates = TEMPLATE_REGISTRY.values()
    if production_only:
        templates = [template for template in templates if template.production_enabled]
    return [asdict(template) for template in templates]


def template_compatible(template_id: str, media_type: str, content_role: str) -> bool:
    definition = get_template(template_id)
    return (
        media_type in definition.supported_media_types
        and content_role in definition.supported_content_roles
    )
