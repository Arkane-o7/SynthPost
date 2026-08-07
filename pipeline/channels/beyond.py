from __future__ import annotations

from .base import BrandTheme, ChannelProductionProfile, ChannelProfile, ChannelPromptPack


PROFILE = ChannelProfile(
    channel_id="beyond",
    profile_version="1.0.0",
    name="Beyond",
    short_name="BE",
    tagline="The world beyond the headline",
    description="International news, geopolitics, and global affairs.",
    accent_color="#3b82f6",
    accent_soft_color="rgba(59, 130, 246, 0.16)",
    accent_hover_color="#5795f7",
    default_category="global",
    default_render_profile="production",
    default_narration_mode="explained",
    default_target_duration_seconds=480,
    editorial_focus="Breaking international news, geopolitics, security, and diplomacy.",
    research_style="Fast verification across primary sources and credible global reporting.",
    script_style="Anchor-led reporting with context, stakes, and clear uncertainty.",
    narration_style="Direct, urgent when warranted, and globally literate.",
    visual_style="Primary footage, maps, documents, locations, and news graphics.",
    timeline_style="Newsroom pacing led by the anchor and verified source footage.",
    template_pack="beyond_v1",
    brand_pack="beyond_v1",
    anchor_profile="beyond_anchor_v1",
    voice_profile="beyond_voice_v1",
    outro_pack="beyond_v1",
    prompts=ChannelPromptPack(
        version="prompts-v1",
        script="""
Write an international-news report that separates what happened, what is
confirmed, what each side says, and why it matters beyond the immediate event.
Lead with the newest verified development and identify the place, actors, and
timing without theatrical scene-setting. Add only the history needed to
understand present stakes. Attribute contested claims close to the claim,
distinguish official statements from independent verification, and avoid
false balance when evidence is unequal. Never use warlike urgency for routine
diplomacy. End with the next decision, deadline, deployment, vote, negotiation,
or independently observable development.
""",
        segmentation="""
Use an anchor-led broadcast rhythm: a concise direct-address opening, verified
primary footage or maps when they materially locate events, and presenter
returns for attribution, uncertainty, and consequences. Make section changes
track developments, actors, geography, or verification status. Close on camera
with the next concrete event to watch.
""",
        visual_search="""
Prioritize original event footage, official briefings, satellite or map
material, government and international-organization documents, verified
locations, and named participants. Search the exact city, institution, event,
date, speaker, operation, or document supported by the sources. Avoid other
broadcasters' packaged reports, presenter monologues, sensational thumbnails,
unverified combat clips, generic flags, and unrelated military montages.
""",
    ),
    production=ChannelProductionProfile(
        composition_template="timeline_story_beyond",
        template_policy="beyond_global_news_v1",
        logo_path="brand/beyond_bug.svg",
        outro_path="assets/channels/beyond/outro.mp4",
        presenter_provider="avatar_engine",
        presenter_renderer="rocketbox",
        presenter_preview_renderer="rocketbox",
        presenter_final_renderer="rocketbox",
        presenter_asset_path="assets/avatars/beyond_anchor_v1/anchor.glb",
        presenter_metadata_path="assets/avatars/beyond_anchor_v1/avatar.json",
        presenter_style="international_news_anchor",
        presenter_body_form="F",
        presenter_background="charcoal",
        narrator_provider="dots_tts",
        narrator_model_name="dots.tts-soar-mlx-int4",
        narrator_voice_id="beyond_anchor",
        narrator_voice_speed=1.03,
        narrator_voice_profile_path="assets/channels/beyond/voice/beyond.dtprofile",
        narrator_reference_audio_path=None,
        narrator_reference_text=None,
        brand=BrandTheme(
            navy="#07101E",
            deep_blue="#0B2342",
            accent="#3B82F6",
            accent_secondary="#F1B84B",
            danger="#D84A4A",
            muted="#A8B6C8",
            ink="#030812",
        ),
    ),
)
