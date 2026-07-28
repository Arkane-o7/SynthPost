from __future__ import annotations

from .base import (
    BrandTheme,
    ChannelProductionProfile,
    ChannelProfile,
    ChannelPromptPack,
)


PROFILE = ChannelProfile(
    channel_id="synthpost",
    profile_version="1.0.0",
    name="SynthPost",
    short_name="SP",
    tagline="Technology and culture, decoded",
    description="Technology, AI, startups, social media, and internet culture.",
    accent_color="#ef3340",
    accent_soft_color="rgba(239, 51, 64, 0.16)",
    accent_hover_color="#ff4d59",
    default_category="technology",
    default_render_profile="production",
    default_narration_mode="explained",
    default_target_duration_seconds=600,
    editorial_focus="Technology, AI, startups, platforms, and internet culture.",
    research_style="Product evidence, primary reporting, and technical context.",
    script_style="Clear modern explainers with a strong consequence-led hook.",
    narration_style="Energetic, precise, and conversational.",
    visual_style="Interfaces, product footage, social posts, and modern explainers.",
    timeline_style="Fast, varied pacing with frequent visual evidence.",
    template_pack="synthpost_v2",
    brand_pack="synthpost_v2",
    anchor_profile="synthpost_anchor_v1",
    voice_profile="synthpost_voice_v1",
    outro_pack="synthpost_v1",
    prompts=ChannelPromptPack(
        version="prompts-v2",
        script="""
Write a sharp technology-and-culture explainer. Open on the concrete product,
decision, behavior, or power shift that changes what people can do. Explain the
mechanism in plain language, then connect it to users, builders, businesses, or
online culture. Treat company marketing as a claim. Avoid generic futurism,
breathless AI language, feature-list recitation, and empty statements that a
technology is revolutionary. End with the next observable test of adoption,
competition, regulation, or user behavior.
""",
        segmentation="""
Favor brisk production sections that alternate direct presenter explanation
with authentic interfaces, demonstrations, launch footage, documents, and
online artifacts. Start and finish with the presenter. Split only when the
viewer needs a genuinely different product, mechanism, consequence, or test.
""",
        visual_search="""
Prioritize official demos, real interfaces, product pages, launch events,
technical diagrams, filings, and authentic platform artifacts. Search for the
specific product version, company, speaker, event, or interface named in the
source. Avoid abstract robots, glowing brains, anonymous typing, generic server
rooms, and technology-themed stock footage unless the narration explicitly
concerns that physical infrastructure.
""",
    ),
    production=ChannelProductionProfile(
        composition_template="timeline_story_synthpost",
        template_policy="synthpost_fast_explainer_v1",
        logo_path="brand/synthpost_bug.svg",
        outro_path="assets/brand/outro.mp4",
        presenter_provider="avatar_engine",
        presenter_renderer="rocketbox",
        presenter_asset_path="assets/avatars/synthpost_anchor_v1/anchor.glb",
        presenter_metadata_path="assets/avatars/synthpost_anchor_v1/avatar.json",
        presenter_style="professional_technology_anchor",
        presenter_body_form="F",
        presenter_background="charcoal",
        narrator_provider="dots_tts",
        narrator_model_name="dots.tts-soar-mlx-int4",
        narrator_voice_id="synthpost_anchor",
        narrator_voice_speed=1.0,
        narrator_voice_profile_path=None,
        narrator_reference_audio_path=None,
        narrator_reference_text=None,
        brand=BrandTheme(
            navy="#050A14",
            deep_blue="#071B33",
            accent="#1F7BFF",
            accent_secondary="#FFD84A",
            danger="#E13B33",
        ),
    ),
)
