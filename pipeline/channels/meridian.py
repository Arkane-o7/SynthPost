from __future__ import annotations

from .base import BrandTheme, ChannelProductionProfile, ChannelProfile, ChannelPromptPack


PROFILE = ChannelProfile(
    channel_id="meridian",
    profile_version="1.0.0",
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
    visual_style="Charts, filings, economic data, maps, and restrained b-roll.",
    timeline_style="Deliberate pacing with space for charts and causal explanation.",
    template_pack="meridian_v1",
    brand_pack="meridian_v1",
    anchor_profile="meridian_anchor_v1",
    voice_profile="meridian_voice_v1",
    outro_pack="meridian_v1",
    prompts=ChannelPromptPack(
        version="prompts-v1",
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
Use fewer, longer analytical sections. Let one causal idea develop before
changing treatment. Prefer the presenter beside filings, charts, maps, and
company evidence; reserve full-screen material for a decisive chart, document,
facility, or primary event. The opening states the economic puzzle and the
closing returns to the unresolved incentive or financial test.
""",
        visual_search="""
Prioritize regulatory filings, annual reports, investor presentations, central
bank and statistics-agency data, court records, company facilities, maps, and
properly sourced charts. Search with the exact company, instrument, metric,
reporting period, regulator, or policy named in the script. Avoid trading-floor
stock footage, falling coins, cash-counting hands, generic skyscrapers, and
unsourced social-media charts.
""",
    ),
    production=ChannelProductionProfile(
        composition_template="timeline_story_meridian",
        template_policy="meridian_financial_analysis_v1",
        logo_path="brand/meridian_bug.svg",
        outro_path="assets/channels/meridian/outro.mp4",
        presenter_provider="avatar_engine",
        presenter_renderer="rocketbox",
        presenter_asset_path="assets/avatars/meridian_anchor_v1/anchor.glb",
        presenter_metadata_path="assets/avatars/meridian_anchor_v1/avatar.json",
        presenter_style="measured_financial_presenter",
        presenter_body_form="M",
        presenter_background="charcoal",
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
