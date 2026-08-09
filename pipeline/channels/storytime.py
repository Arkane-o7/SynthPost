from __future__ import annotations

from .base import BrandTheme, ChannelProductionProfile, ChannelProfile, ChannelPromptPack


PROFILE = ChannelProfile(
    channel_id="storytime",
    profile_version="1.0.0",
    name="Sidequest",
    short_name="SQ",
    tagline="Small stories. Big detours.",
    description="Animated personal stories, awkward moments, and everyday observations.",
    accent_color="#7C5CFC",
    accent_soft_color="rgba(124, 92, 252, 0.16)",
    accent_hover_color="#9278FF",
    default_category="storytime",
    default_render_profile="production",
    default_narration_mode="explained",
    default_target_duration_seconds=600,
    editorial_focus=(
        "First-person experiences, social mishaps, growing pains, internet-era "
        "life, and observational comedy."
    ),
    research_style=(
        "Story-owner notes and supplied memories first; light factual verification "
        "only where a real-world detail materially affects the story."
    ),
    script_style=(
        "Conversational first-person storytelling with a fast hook, concrete scene "
        "work, honest uncertainty, escalation, visual punchlines, and a earned callback."
    ),
    narration_style=(
        "Warm, intimate, quick-witted, and naturally performative without sounding "
        "like a stand-up routine."
    ),
    visual_style=(
        "Original limited animation on warm paper: expressive line characters, bold "
        "silhouettes, economical props, reaction poses, and occasional memory inserts."
    ),
    timeline_style=(
        "Audio-master story beats averaging four to nine seconds, with pose changes, "
        "camera reframes, visual exaggeration, and held frames that land punchlines."
    ),
    template_pack="storytime_animation_v1",
    brand_pack="sidequest_v1",
    anchor_profile="sidequest_procedural_cast_v1",
    voice_profile="sidequest_voice_v1",
    outro_pack="sidequest_v1",
    prompts=ChannelPromptPack(
        version="prompts-v1",
        script="""
Write a first-person animated story, not a reported explainer. Open inside the
most intriguing awkward choice, surprising consequence, or unresolved social
problem, then rewind only as far as needed. Build scenes from observable details:
where people stood, what the narrator tried, what changed, and the small reaction
that made the moment funny or painful. Escalate through cause and effect rather
than a list of anecdotes. Use dialogue sparingly and identify reconstructed
wording as remembered rather than exact. Never invent trauma, relationships,
identity details, or private facts that the supplied story owner did not provide.
Protect third-party privacy by generalizing irrelevant identifying details.
Let humor come from specificity, contrast, timing, and the narrator's own flawed
assumptions. End with a callback, changed perspective, or precise observation;
do not bolt on a generic life lesson.
""",
        segmentation="""
Plan for original limited animation. Split narration into four-to-nine-second
idea beats, with one dominant action, reaction, reveal, or visual joke per beat.
Choose only from Sidequest's story grammar: cold open, establishing doodle,
character stage, dialogue two-shot, imagination burst, memory cutaway, motion
montage, and punchline button. Persist a location across adjacent beats when the
scene has not changed. Use close reactions and held frames to land important
moments; use montage only when time or repeated attempts genuinely compress.
Never request a news desk, lower third, chart card, presenter box, broadcast
footage montage, or another channel's template. On-screen words should be short
handwritten accents, not subtitles or paragraphs.
""",
        visual_search="""
The default visual source is Sidequest's original procedural animation, so do
not search for decorative stock footage or another animation creator's artwork.
When references would add truth or specificity, prioritize user-supplied photos,
the actual object or location, simple maps, screenshots owned by the story owner,
and rights-safe reference images that an animator can reinterpret. Search exact
objects, places, clothing, interfaces, or time-period details from the script.
Avoid reaction GIFs, meme compilations, generic lifestyle stock, reposted comics,
fan art, and frames from other storytime channels.
""",
    ),
    production=ChannelProductionProfile(
        composition_template="timeline_story_storytime",
        template_policy="storytime_animation_v1",
        logo_path="brand/storytime_bug.svg",
        outro_path="assets/channels/storytime/outro.mp4",
        presenter_provider="procedural_puppet",
        presenter_renderer="remotion",
        presenter_preview_renderer="remotion",
        presenter_final_renderer="remotion",
        presenter_asset_path=None,
        presenter_metadata_path=None,
        presenter_style="sidequest_line_cast",
        presenter_body_form="neutral",
        presenter_background="transparent",
        narrator_provider="edge_tts",
        narrator_model_name="edge-tts-7.2.8",
        narrator_voice_id="en-US-AvaMultilingualNeural",
        narrator_voice_speed=1.04,
        narrator_voice_profile_path=None,
        narrator_reference_audio_path=None,
        narrator_reference_text=None,
        brand=BrandTheme(
            navy="#2B2340",
            deep_blue="#443765",
            accent="#7C5CFC",
            accent_secondary="#FFB85C",
            danger="#E85D75",
            white="#FFF8EA",
            muted="#8D829E",
            ink="#292234",
        ),
    ),
)
