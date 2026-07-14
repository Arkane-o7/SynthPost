"""Validated HTTP request contracts for the SynthPost Studio API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipeline.models import (
    ContentRole,
    EpisodeStatus,
    NarrationMode,
    ProjectStatus,
    RightsTier,
    SourceType,
)


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(APIModel):
    title: str = Field(min_length=1, max_length=200)
    default_category: str = "general"
    default_render_profile: str = "preview"


class ProjectPatch(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    default_category: str | None = None
    default_render_profile: str | None = None
    status: ProjectStatus | None = None


class EpisodeCreate(APIModel):
    title: str = Field(min_length=1, max_length=200)
    render_profile: str | None = None


class EpisodePatch(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
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
