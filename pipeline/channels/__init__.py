from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from .base import (
    DEFAULT_CHANNEL_ID,
    BrandTheme,
    ChannelId,
    ChannelProductionProfile,
    ChannelProfile,
    ChannelPromptPack,
    channel_prompt_context,
    narration_format_context,
    prompt_identity,
    resolved_production,
    script_prompt_context,
    segmentation_prompt_context,
    visual_prompt_context,
)
from .beyond import PROFILE as BEYOND
from .meridian import PROFILE as MERIDIAN
from .storytime import PROFILE as STORYTIME
from .synthpost import PROFILE as SYNTHPOST


_CHANNELS: tuple[ChannelProfile, ...] = (SYNTHPOST, MERIDIAN, BEYOND, STORYTIME)
CHANNELS: Mapping[ChannelId, ChannelProfile] = MappingProxyType(
    {profile.channel_id: profile for profile in _CHANNELS}
)


def list_channel_profiles() -> tuple[ChannelProfile, ...]:
    return _CHANNELS


def get_channel_profile(channel_id: str) -> ChannelProfile:
    try:
        return CHANNELS[channel_id]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(
            f"Unknown channel {channel_id!r}; expected one of: {', '.join(CHANNELS)}"
        ) from exc


def profile_for_episode(repository: Any, episode_id: str) -> ChannelProfile:
    value = getattr(repository.get_episode(episode_id), "channel_id", DEFAULT_CHANNEL_ID)
    return get_channel_profile(value if isinstance(value, str) else DEFAULT_CHANNEL_ID)


def profile_for_story(repository: Any, story_id: str) -> ChannelProfile:
    value = getattr(repository.episode_for_story(story_id), "channel_id", DEFAULT_CHANNEL_ID)
    return get_channel_profile(value if isinstance(value, str) else DEFAULT_CHANNEL_ID)


__all__ = [
    "BEYOND",
    "CHANNELS",
    "DEFAULT_CHANNEL_ID",
    "MERIDIAN",
    "STORYTIME",
    "SYNTHPOST",
    "BrandTheme",
    "ChannelId",
    "ChannelProductionProfile",
    "ChannelProfile",
    "ChannelPromptPack",
    "channel_prompt_context",
    "get_channel_profile",
    "list_channel_profiles",
    "narration_format_context",
    "profile_for_episode",
    "profile_for_story",
    "prompt_identity",
    "resolved_production",
    "script_prompt_context",
    "segmentation_prompt_context",
    "visual_prompt_context",
]
