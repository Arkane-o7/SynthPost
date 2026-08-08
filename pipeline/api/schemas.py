"""Validated HTTP request contracts for the SynthPost Studio API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pipeline.channels import ChannelId, DEFAULT_CHANNEL_ID
from pipeline.models import (
    AutonomyRun,
    ContentRole,
    EpisodeStatus,
    NarrationMode,
    ProjectStatus,
    RightsTier,
    SourceType,
)
from pipeline.video_qa import FinalVideoQAReport


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    channel_id: ChannelId = DEFAULT_CHANNEL_ID
    default_category: str | None = None
    default_render_profile: str | None = None


class ProjectPatch(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    default_category: str | None = None
    default_render_profile: str | None = None
    status: ProjectStatus | None = None


class EpisodeCreate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    render_profile: str | None = None


class EpisodePatch(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    status: EpisodeStatus | None = None
    render_profile: str | None = None


class SourceCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    category: str = "general"
    homepage_url: str | None = None
    feed_url: str | None = None
    country: str | None = None
    enabled: bool = True
    priority: int = Field(default=50, ge=0, le=100)
    reliability_score: float = Field(default=0.7, ge=0, le=1)
    custom: bool = True


class SourcePatch(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_type: SourceType | None = None
    category: str | None = None
    homepage_url: str | None = None
    feed_url: str | None = None
    country: str | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    reliability_score: float | None = Field(default=None, ge=0, le=1)


class DiscoveryStart(APIModel):
    episode_id: str | None = None
    category: str | None = None


class CandidateAction(APIModel):
    episode_id: str | None = None
    reasons: list[str] = Field(default_factory=list)


class CustomTopic(APIModel):
    episode_id: str | None = None
    title: str = Field(min_length=1)
    summary: str = ""
    category: str = "custom"


class CustomUrl(APIModel):
    episode_id: str | None = None
    url: str = Field(min_length=1)
    title: str | None = None
    summary: str = ""
    category: str = "custom"


class ManualStory(APIModel):
    episode_id: str | None = None
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    category: str = "manual"


class ManualScript(APIModel):
    headline: str = Field(min_length=1)
    text: str = Field(min_length=1)
    category: str = "manual"


class GenerateScriptRequest(APIModel):
    provider: str | None = None
    target_duration_seconds: int = Field(default=600, ge=60, le=7200)
    narration_mode: NarrationMode = NarrationMode.explained


class ResearchAndScriptRequest(GenerateScriptRequest):
    """One-click editorial draft settings.

    Research remains a durable artifact and script generation remains its own
    queue job; this request simply chains the two without another editor action.
    """


class VisualStageRequest(APIModel):
    path: str = Field(min_length=1)
    title: str | None = None
    section_ids: list[str] = Field(default_factory=list)
    content_role: ContentRole = ContentRole.context
    rights_tier: RightsTier = RightsTier.yellow
    usage_basis: str = "user_provided_local_media"


class VisualPatch(APIModel):
    attribution_text: str | None = None
    trim_start: float | None = Field(default=None, ge=0)
    trim_end: float | None = Field(default=None, ge=0)
    motion: dict[str, Any] | None = None
    section_ids: list[str] | None = None
    content_role: ContentRole | None = None


class RenderRequest(APIModel):
    render_profile: str = "preview"
    test_mode: bool = False
    force: bool = False
    skip_avatar_render: bool = True


class AutonomyRunCreate(APIModel):
    episode_id: str
    story_id: str | None = None
    provider: str = "hermes"
    target_duration_seconds: int = Field(default=600, ge=60, le=3600)
    narration_mode: NarrationMode = NarrationMode.explained
    category: str | None = None
    render_profile: str = "production"
    max_repairs_per_stage: int = Field(default=2, ge=0, le=5)


class AutonomyQACheck(APIModel):
    """One normalized final-video check shown by Studio."""

    check_id: str
    label: str
    status: Literal["passed", "warning", "failed"]
    detail: str


class AutonomyQAView(FinalVideoQAReport):
    """Persisted QA evidence plus stable fields for the review UI."""

    checks: list[AutonomyQACheck]
    duration_seconds: float | None
    width: int | None
    height: int | None
    video_codec: str | None
    audio_codec: str | None
    size_bytes: int | None


class AutonomyRunView(AutonomyRun):
    """HTTP representation enriched with display-only repository context."""

    project_title: str
    episode_title: str
    story_title: str | None
    qa: AutonomyQAView | None = None


class AutonomyOutputRevealView(APIModel):
    revealed: Literal[True]
    path: str
