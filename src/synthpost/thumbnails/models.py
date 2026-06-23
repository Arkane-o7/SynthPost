from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]


TOPIC_TO_TEMPLATES = {
    "ai": ["authority_warning", "logo_collision", "agent_swarm"],
    "technology": ["clean_market_surge", "logo_collision", "authority_warning"],
    "business": ["money_deal_bomb", "inside_the_deal", "authority_warning"],
    "economy": ["factory_boom", "money_deal_bomb", "map_crisis_marker"],
    "finance": ["clean_market_surge", "money_deal_bomb", "inside_the_deal"],
    "geopolitics": ["map_crisis_marker", "global_ai_faceoff", "sovereign_ai_stack"],
    "policy": ["map_crisis_marker", "authority_warning", "document_exposed"],
    "infrastructure": ["infrastructure_race", "factory_boom", "money_deal_bomb"],
    "conflict": ["global_ai_faceoff", "document_exposed", "map_crisis_marker"],
    "energy": ["infrastructure_race", "map_crisis_marker", "money_deal_bomb"],
    "culture": ["authority_warning", "global_ai_faceoff", "document_exposed"],
}

RENDERABLE_TEMPLATES = {"authority_warning", "money_deal_bomb", "logo_collision", "global_ai_faceoff", "clean_market_surge", "device_shock"}


@dataclass
class ThumbnailSubject:
    type: str
    name: str
    role: str | None = None
    importance: str = "primary"
    visual_priority: int = 3

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ThumbnailSubject":
        return cls(
            type=str(record.get("type", "object")),
            name=str(record.get("name", "")),
            role=str(record["role"]) if record.get("role") else None,
            importance=str(record.get("importance", "primary")),
            visual_priority=int(record.get("visual_priority", 3)),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "type": self.type,
                "name": self.name,
                "role": self.role,
                "importance": self.importance,
                "visual_priority": self.visual_priority,
            }.items()
            if value not in (None, "", [], {})
        }


@dataclass
class ThumbnailAsset:
    id: str
    path_or_url: str
    type: str
    subject_name: str | None = None
    source_url: str | None = None
    license: str | None = None
    attribution: str | None = None
    usage_status: str = "needs_review"
    label: str | None = None
    notes: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ThumbnailAsset":
        return cls(
            id=str(record.get("id", "asset")),
            path_or_url=str(record.get("path_or_url", "")),
            type=str(record.get("type", "background_image")),
            subject_name=str(record["subject_name"]) if record.get("subject_name") else None,
            source_url=str(record["source_url"]) if record.get("source_url") else None,
            license=str(record["license"]) if record.get("license") else None,
            attribution=str(record["attribution"]) if record.get("attribution") else None,
            usage_status=str(record.get("usage_status", "needs_review")),
            label=str(record["label"]) if record.get("label") else None,
            notes=str(record["notes"]) if record.get("notes") else None,
        )

    def to_record(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "id": self.id,
                "path_or_url": self.path_or_url,
                "type": self.type,
                "subject_name": self.subject_name,
                "source_url": self.source_url,
                "license": self.license,
                "attribution": self.attribution,
                "usage_status": self.usage_status,
                "label": self.label,
                "notes": self.notes,
            }.items()
            if value not in (None, "", [], {})
        }


@dataclass
class ThumbnailBrief:
    video_title: str
    episode_headline: str
    topic: str
    main_subjects: list[ThumbnailSubject]
    story_angle: str
    emotion: str
    assets: list[ThumbnailAsset] = field(default_factory=list)
    brief_id: str = "thumbnail_brief"
    stakes: str | None = None
    curiosity_gap: str | None = None
    key_numbers: list[dict[str, Any]] = field(default_factory=list)
    approved_thumbnail_text: list[str] = field(default_factory=list)
    forbidden_thumbnail_text: list[str] = field(default_factory=list)
    render_preferences: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any], *, fallback_id: str = "thumbnail_brief") -> "ThumbnailBrief":
        assets_section = record.get("assets") if isinstance(record.get("assets"), dict) else {}
        assets: list[ThumbnailAsset] = []
        for group in assets_section.values():
            if isinstance(group, list):
                assets.extend(ThumbnailAsset.from_record(item) for item in group if isinstance(item, dict))
        return cls(
            brief_id=str(record.get("brief_id") or fallback_id),
            video_title=str(record.get("video_title", "")),
            episode_headline=str(record.get("episode_headline", "")),
            topic=str(record.get("topic", "AI")),
            main_subjects=[
                ThumbnailSubject.from_record(item)
                for item in record.get("main_subjects", [])
                if isinstance(item, dict)
            ],
            story_angle=str(record.get("story_angle", "")),
            emotion=str(record.get("emotion", "analytical")),
            assets=assets,
            stakes=str(record["stakes"]) if record.get("stakes") else None,
            curiosity_gap=str(record["curiosity_gap"]) if record.get("curiosity_gap") else None,
            key_numbers=list(record.get("key_numbers", [])),
            approved_thumbnail_text=list(record.get("approved_thumbnail_text", [])),
            forbidden_thumbnail_text=list(record.get("forbidden_thumbnail_text", [])),
            render_preferences=dict(record.get("render_preferences", {})),
        )


@dataclass
class ThumbnailConcept:
    brief_id: str
    concept_id: str
    template_id: str
    headline_text: str
    video_title: str
    episode_headline: str
    topic: str
    emotion: str
    main_subjects: list[ThumbnailSubject]
    assets: list[ThumbnailAsset]
    key_numbers: list[dict[str, Any]] = field(default_factory=list)
    subtitle_text: str | None = None
    accent_words: list[str] = field(default_factory=list)
    source_tag: str = "SYNTHPOST BRIEFING"
    visual_hook: str = ""
    rationale: str = ""
    score: int | None = None
    score_breakdown: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    output_path: str | None = None
    rendered_png: str | None = None

    def to_renderer_record(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "briefId": self.brief_id,
                "conceptId": self.concept_id,
                "templateId": self.template_id,
                "videoTitle": self.video_title,
                "episodeHeadline": self.episode_headline,
                "topic": self.topic,
                "emotion": self.emotion,
                "headlineText": self.headline_text,
                "subtitleText": self.subtitle_text,
                "accentWords": self.accent_words,
                "sourceTag": self.source_tag,
                "visualHook": self.visual_hook,
                "mainSubjects": [subject.to_record() for subject in self.main_subjects],
                "keyNumbers": self.key_numbers,
                "assets": [asset.to_record() for asset in self.assets],
                "score": self.score,
                "outputPath": self.output_path,
                "rendered_png": self.rendered_png,
                "rationale": self.rationale,
                "warnings": self.warnings,
                "score_breakdown": self.score_breakdown,
            }.items()
            if value not in (None, "", [], {})
        }
