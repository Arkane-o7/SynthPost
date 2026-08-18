from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


ChannelId = Literal["synthpost"]
DEFAULT_CHANNEL_ID: ChannelId = "synthpost"


@dataclass(frozen=True, slots=True)
class ChannelPromptPack:
    """Channel-owned editorial instructions injected into shared JSON contracts."""

    version: str
    script: str
    segmentation: str
    visual_search: str


@dataclass(frozen=True, slots=True)
class BrandTheme:
    navy: str
    deep_blue: str
    accent: str
    accent_secondary: str
    danger: str
    white: str = "#F5F7FA"
    muted: str = "#AAB4C2"
    ink: str = "#020610"


@dataclass(frozen=True, slots=True)
class ChannelProductionProfile:
    """All replaceable media and renderer decisions for one channel."""

    composition_template: str
    template_policy: str
    logo_path: str | None
    outro_path: str
    presenter_provider: str
    presenter_renderer: str
    presenter_preview_renderer: str
    presenter_final_renderer: str
    presenter_asset_path: str | None
    presenter_metadata_path: str | None
    presenter_style: str
    presenter_body_form: str
    presenter_background: str
    narrator_provider: str
    narrator_model_name: str | None
    narrator_voice_id: str
    narrator_voice_speed: float
    narrator_voice_profile_path: str | None
    narrator_reference_audio_path: str | None
    narrator_reference_text: str | None
    brand: BrandTheme


@dataclass(frozen=True, slots=True)
class ChannelProfile:
    """Immutable identity, prompts, and production defaults for one channel."""

    channel_id: ChannelId
    profile_version: str
    name: str
    short_name: str
    tagline: str
    description: str
    accent_color: str
    accent_soft_color: str
    accent_hover_color: str
    default_category: str
    default_render_profile: str
    default_narration_mode: str
    default_target_duration_seconds: int
    editorial_focus: str
    research_style: str
    script_style: str
    narration_style: str
    visual_style: str
    timeline_style: str
    template_pack: str
    brand_pack: str
    anchor_profile: str
    voice_profile: str
    outro_pack: str
    prompts: ChannelPromptPack
    production: ChannelProductionProfile

    def model_dump(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        value = asdict(self)
        # Full prompt text belongs in audited generations, not every API response
        # and render manifest. Expose only the independently versioned package id.
        prompts = value.pop("prompts")
        value["prompt_pack_version"] = prompts["version"]
        return value


def prompt_identity(profile: ChannelProfile, stage: str) -> str:
    return f"{profile.channel_id}.{stage}.{profile.prompts.version}"


def channel_prompt_context(profile: ChannelProfile) -> str:
    """Compact identity shared by prompt builders and audit logs."""

    return "\n".join(
        [
            f"CHANNEL: {profile.name}",
            f"Editorial focus: {profile.editorial_focus}",
            f"Research approach: {profile.research_style}",
            f"Writing style: {profile.script_style}",
            f"Narration style: {profile.narration_style}",
            f"Visual style: {profile.visual_style}",
            f"Timeline style: {profile.timeline_style}",
        ]
    )


def script_prompt_context(profile: ChannelProfile) -> str:
    return f"{channel_prompt_context(profile)}\n\n{profile.prompts.script.strip()}"


def segmentation_prompt_context(profile: ChannelProfile) -> str:
    return f"{channel_prompt_context(profile)}\n\n{profile.prompts.segmentation.strip()}"


def visual_prompt_context(profile: ChannelProfile) -> str:
    return f"{channel_prompt_context(profile)}\n\n{profile.prompts.visual_search.strip()}"


def narration_format_context(profile: ChannelProfile, mode: str) -> str:
    """Channel-neutral format mechanics without SynthPost's legacy charter."""

    formats = {
        "signal": (
            "Short report",
            "verified development -> essential context -> immediate consequence -> next event",
            "compressed, decisive, and free of repeated background",
        ),
        "explained": (
            "Explainer",
            "concrete hook -> context -> mechanism -> consequences -> uncertainty -> next test",
            "clear causal progression with enough evidence to understand the system",
        ),
        "deep_dive": (
            "Deep analysis",
            "central puzzle -> evidence -> mechanism -> competing explanations -> consequences -> decisive test",
            "patient, evidence-led, and explicit about the limits of the available record",
        ),
        "india_builds": (
            "Long-form systems documentary",
            "capability -> history -> institutions -> constraints -> execution -> outcomes -> next milestone",
            "documentary pacing grounded in physical systems, policy, and measurable delivery",
        ),
    }
    label, structure, pacing = formats.get(mode, formats["explained"])
    return "\n".join(
        [
            f"Format: {label}",
            f"Format structure: {structure}",
            f"Pacing: {pacing}",
            f"Channel narration: {profile.narration_style}",
        ]
    )


def _optional_path(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def resolved_production(profile: ChannelProfile) -> dict[str, Any]:
    """Resolve per-channel overrides without leaking one channel into another.

    SynthPost retains the legacy environment variables for compatibility. Other
    channels intentionally use only their own SYNTHEA_<CHANNEL>_* variables and
    package defaults.
    """

    from pipeline import config

    base = profile.production
    prefix = f"SYNTHEA_{profile.channel_id.upper()}"

    def text(name: str, default: str | None) -> str | None:
        return _optional_path(config.env(f"{prefix}_{name}", default))

    value: dict[str, Any] = asdict(base)
    value.update(
        {
            "composition_template": text(
                "COMPOSITION_TEMPLATE", base.composition_template
            ),
            "logo_path": text("LOGO_PATH", base.logo_path),
            "outro_path": text("OUTRO_PATH", base.outro_path),
            "presenter_provider": text(
                "PRESENTER_PROVIDER", base.presenter_provider
            ),
            "presenter_renderer": text(
                "PRESENTER_RENDERER", base.presenter_renderer
            ),
            "presenter_preview_renderer": text(
                "PRESENTER_PREVIEW_RENDERER", base.presenter_preview_renderer
            ),
            "presenter_final_renderer": text(
                "PRESENTER_FINAL_RENDERER", base.presenter_final_renderer
            ),
            "presenter_asset_path": text(
                "PRESENTER_ASSET_PATH", base.presenter_asset_path
            ),
            "presenter_metadata_path": text(
                "PRESENTER_META_PATH", base.presenter_metadata_path
            ),
            "presenter_style": text("PRESENTER_STYLE", base.presenter_style),
            "presenter_body_form": text(
                "PRESENTER_BODY_FORM", base.presenter_body_form
            ),
            "presenter_background": text(
                "PRESENTER_BACKGROUND", base.presenter_background
            ),
            "narrator_provider": text(
                "TTS_PROVIDER", base.narrator_provider
            ),
            "narrator_model_name": text(
                "TTS_MODEL_NAME", base.narrator_model_name
            ),
            "narrator_voice_id": text("TTS_VOICE_ID", base.narrator_voice_id),
            "narrator_voice_speed": float(
                config.env(
                    f"{prefix}_TTS_VOICE_SPEED", str(base.narrator_voice_speed)
                )
                or base.narrator_voice_speed
            ),
            "narrator_voice_profile_path": text(
                "TTS_VOICE_PROFILE_PATH", base.narrator_voice_profile_path
            ),
            "narrator_reference_audio_path": text(
                "TTS_REFERENCE_AUDIO", base.narrator_reference_audio_path
            ),
            "narrator_reference_text": text(
                "TTS_REFERENCE_TEXT", base.narrator_reference_text
            ),
        }
    )
    if profile.channel_id == "synthpost":
        avatar = config.get_settings().avatar
        narration = config.get_settings().narration
        value["presenter_renderer"] = text(
            "PRESENTER_RENDERER", avatar.renderer or base.presenter_renderer
        )
        value["presenter_asset_path"] = text(
            "PRESENTER_ASSET_PATH", avatar.asset_path
        )
        value["presenter_metadata_path"] = text(
            "PRESENTER_META_PATH", avatar.metadata_path
        )
        value["presenter_style"] = text(
            "PRESENTER_STYLE",
            config.env("SYNTHPOST_AVATAR_STYLE", base.presenter_style),
        )
        value["presenter_body_form"] = text(
            "PRESENTER_BODY_FORM",
            config.env("SYNTHPOST_AVATAR_BODY_FORM", base.presenter_body_form),
        )
        value["presenter_background"] = text(
            "PRESENTER_BACKGROUND",
            config.env(
                "SYNTHPOST_AVATAR_RENDER_BACKGROUND",
                base.presenter_background,
            ),
        )
        value["narrator_model_name"] = text(
            "TTS_MODEL_NAME", narration.model_name
        )
        value["narrator_voice_id"] = text("TTS_VOICE_ID", narration.voice_id)
        value["narrator_voice_speed"] = float(
            config.env(
                f"{prefix}_TTS_VOICE_SPEED", str(narration.voice_speed)
            )
            or narration.voice_speed
        )
        value["narrator_voice_profile_path"] = text(
            "TTS_VOICE_PROFILE_PATH",
            str(narration.voice_profile_path) if narration.voice_profile_path else None,
        )
        value["narrator_reference_audio_path"] = text(
            "TTS_REFERENCE_AUDIO",
            str(narration.reference_audio_path) if narration.reference_audio_path else None,
        )
        value["narrator_reference_text"] = text(
            "TTS_REFERENCE_TEXT", narration.reference_text
        )
    return value
