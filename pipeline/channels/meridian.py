from __future__ import annotations

from .base import BrandTheme, ChannelProductionProfile, ChannelProfile, ChannelPromptPack


PROFILE = ChannelProfile(
    channel_id="meridian",
    profile_version="1.2.0",
    name="Meridian",
    short_name="ME",
    tagline="Follow the money",
    description="Financial systems, markets, companies, and the global economy.",
    accent_color="#d5a94e",
    accent_soft_color="rgba(213, 169, 78, 0.16)",
    accent_hover_color="#e3bb68",
    default_category="finance",
    default_render_profile="production",
    default_narration_mode="deep_dive",
    default_target_duration_seconds=900,
    editorial_focus="Markets, companies, incentives, policy, and economic systems.",
    research_style="Data-led analysis grounded in filings and primary financial sources.",
    script_style="Patient analytical explanations that connect incentives to outcomes.",
    narration_style="Measured, authoritative, and skeptical.",
    visual_style=(
        "Full-frame evidence, charts, filings, cutouts, diagrams, and restrained "
        "editorial collage; the PNG narrator appears only when useful."
    ),
    timeline_style=(
        "Editorial motion-graphics pacing with full-canvas scenes and sparse, "
        "mobile narrator appearances instead of broadcast boxes."
    ),
    template_pack="meridian_editorial_v3",
    brand_pack="meridian_v1",
    anchor_profile="meridian_anchor_v1",
    voice_profile="meridian_voice_v1",
    outro_pack="meridian_v1",
    prompts=ChannelPromptPack(
        version="prompts-v3",
        script="""
Write a financial-systems investigation in the spirit of following incentives,
not repeating market commentary. Begin with the surprising transaction,
business model, balance-sheet fact, price signal, or policy decision. Establish
who pays, who benefits, where risk sits, and which constraint makes the system
behave this way. Translate financial terminology immediately and compare
figures only on compatible bases. Distinguish accounting results, cash flows,
valuations, forecasts, and management claims. Do not offer personal investment
advice or predict a price. End with a measurable filing, policy decision,
funding condition, or market signal that could confirm or break the thesis.
""",
        segmentation="""
Use fewer, longer analytical sections, divided into purposeful visual beats.
Choose only from Meridian's scene grammar: evidence reel for full-frame source
footage and photography; document desk for filings and reports; clipping board
for article evidence; data board for charts, maps, and quantitative proof;
explainer stage for mechanisms, people, and comparisons; presenter canvas only
when the narrator itself advances the explanation. Never request a split screen,
lower third, headline bar, chyron, news desk, persistent presenter box, or any
SynthPost template. The PNG narrator is a movable editorial layer, not an
anchor: use it sparingly for a hook, explanation reset, skeptical reaction,
transition, or conclusion, and let evidence hold the frame by itself the rest
of the time. Vary pose, scale, side, and entrance only when the motion clarifies
the idea. The opening states the economic puzzle and the closing returns to the
unresolved incentive or measurable financial test.
""",
        visual_search="""
Prioritize regulatory filings, annual reports, investor presentations, central
bank and statistics-agency data, court records, company facilities, maps,
properly sourced charts, and primary-source video. Search with the exact
company, instrument, metric, reporting period, regulator, or policy named in the
script. A useful result must be strong enough to occupy one of Meridian's
evidence-first scenes; do not search for decorative filler. Avoid trading-floor
stock footage, falling coins, cash-counting hands, generic skyscrapers, generic
AI animations, and unsourced social-media charts.
""",
    ),
    production=ChannelProductionProfile(
        composition_template="timeline_story_meridian",
        template_policy="meridian_editorial_v3",
        logo_path="brand/meridian_bug.svg",
        outro_path="assets/channels/meridian/outro.mp4",
        presenter_provider="png_puppet",
        presenter_renderer="remotion",
        presenter_asset_path="assets/channels/meridian/presenter/character.json",
        presenter_metadata_path=None,
        presenter_style="meridian_editorial_analyst",
        presenter_body_form="M",
        presenter_background="transparent",
        narrator_provider="dots_tts",
        narrator_model_name="dots.tts-soar-mlx-int4",
        narrator_voice_id="meridian_narrator",
        narrator_voice_speed=0.94,
        narrator_voice_profile_path="assets/channels/meridian/voice/meridian.dtprofile",
        narrator_reference_audio_path=None,
        narrator_reference_text=None,
        brand=BrandTheme(
            navy="#0D1012",
            deep_blue="#171B1E",
            accent="#D5A94E",
            accent_secondary="#8FB7A1",
            danger="#C65D52",
            muted="#AEB4B0",
            ink="#080A0B",
        ),
    ),
)
