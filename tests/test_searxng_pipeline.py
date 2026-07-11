from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.db.repository import Repository
from pipeline.discovery.discover import add_manual_story
from pipeline.models import MediaType, SourceDocument
from pipeline.research.extract import build_research_pack
from pipeline.search.searxng_client import SearXNGResult, search
from pipeline.storage import PROJECT_ROOT
from pipeline.visuals.content_analysis import (
    SourceAssessment,
    analyze_media_cleanliness,
    assess_video_source,
)
from pipeline.visuals.providers import (
    _stage_searxng_result,
    approve_visual,
    broadcast_media_fit,
)


class _JSONResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, _limit: int) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class SearXNGPipelineTests(unittest.TestCase):
    def test_source_preflight_blocks_broadcasters_and_recognizes_officials(self) -> None:
        broadcaster = assess_video_source(
            url="https://youtube.example/mint",
            title="Hydrogen train report",
            source_domain="youtube.example",
            metadata={"channel": "Mint", "channel_id": "mint-channel"},
        )
        official = assess_video_source(
            url="https://youtube.example/railways",
            title="Hydrogen train trial",
            source_domain="youtube.example",
            metadata={
                "channel": "Ministry of Railways",
                "channel_id": "railways-channel",
            },
        )

        self.assertEqual(broadcaster.source_class, "news_broadcaster")
        self.assertIn("Mint", broadcaster.detected_brands)
        self.assertTrue(broadcaster.blockers)
        self.assertEqual(official.source_class, "official_primary_source")
        self.assertFalse(official.blockers)

    def test_multiframe_scan_rejects_persistent_brand_and_lower_third(self) -> None:
        temp = tempfile.TemporaryDirectory()
        try:
            root = Path(temp.name)
            media = root / "clip.mp4"
            media.write_bytes(b"unit")
            frames = [root / f"frame-{index}.jpg" for index in range(3)]
            for frame in frames:
                frame.write_bytes(b"frame")

            def fake_ocr(_path: Path, frame_index: int):
                return [
                    {
                        "frame_index": frame_index,
                        "text": "Mint",
                        "confidence": 95.0,
                        "left": 1700,
                        "top": 40,
                        "width": 140,
                        "height": 70,
                    },
                    {
                        "frame_index": frame_index,
                        "text": "Breaking",
                        "confidence": 93.0,
                        "left": 300,
                        "top": 760,
                        "width": 280,
                        "height": 80,
                    },
                    {
                        "frame_index": frame_index,
                        "text": "News",
                        "confidence": 93.0,
                        "left": 610,
                        "top": 760,
                        "width": 180,
                        "height": 80,
                    },
                ]

            with patch(
                "pipeline.visuals.content_analysis.extract_representative_frames",
                return_value=(frames, [1.0, 10.0, 20.0]),
            ), patch(
                "pipeline.visuals.content_analysis._ocr_frame",
                side_effect=fake_ocr,
            ), patch(
                "pipeline.visuals.content_analysis._contact_sheet",
                return_value=None,
            ), patch(
                "pipeline.visuals.content_analysis._ai_classify",
                return_value=(
                    {
                        "decision": "reject",
                        "clean_broll_score": 0.02,
                        "contains_presenter_package": False,
                        "reasons": ["persistent broadcaster packaging"],
                    },
                    "unit-ai",
                ),
            ):
                result = analyze_media_cleanliness(
                    media,
                    root / "analysis",
                    duration=30.0,
                    is_video=True,
                    width=1920,
                    height=1080,
                    source=SourceAssessment(identity="unit source"),
                )

            self.assertEqual(result["content_cleanliness_status"], "rejected")
            self.assertIn("Mint", result["detected_brands"])
            self.assertTrue(result["contains_lower_third"])
            self.assertTrue(result["contains_third_party_logo"])
            self.assertTrue(result["approval_blockers"])
        finally:
            temp.cleanup()

    def test_broadcaster_source_is_blocked_before_video_download(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        episode_id = ""
        try:
            project = repository.create_project("Source preflight")
            episode = repository.create_episode(project.project_id, "Episode")
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Hydrogen train launch",
                body="The train entered service.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            story_id = selected.story_id
            assert story_id
            result = SearXNGResult(
                title="Hydrogen train report",
                url="https://video.example/watch/mint",
                engine="youtube",
                category="videos",
                source_domain="video.example",
            )
            with patch(
                "pipeline.visuals.providers.probe_video_source",
                return_value={"channel": "Mint", "channel_id": "mint-channel"},
            ), patch(
                "pipeline.visuals.providers._download_remote_video"
            ) as download:
                visual = _stage_searxng_result(
                    repository,
                    story_id,
                    "sec_001_cold_open",
                    result,
                    MediaType.video,
                    0,
                    acquire_video=True,
                )

            assert visual
            download.assert_not_called()
            self.assertEqual(visual.source_class, "news_broadcaster")
            self.assertEqual(visual.content_cleanliness_status, "rejected")
            self.assertEqual(visual.review_status.value, "blocked")
            self.assertEqual(visual.rights_tier.value, "red")
            self.assertIsNone(visual.download_path)
        finally:
            repository.close()
            temp.cleanup()
            if episode_id:
                shutil.rmtree(PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True)

    def test_broadcast_fit_accepts_template_ratios_and_rejects_bad_media(self) -> None:
        fullscreen = broadcast_media_fit(1920, 1080)
        split = broadcast_media_fit(1920, 1280)
        portrait = broadcast_media_fit(1080, 1920)
        low_resolution = broadcast_media_fit(1024, 576)

        self.assertTrue(fullscreen[0])
        self.assertTrue(split[0])
        self.assertFalse(portrait[0])
        self.assertIn("outside landscape range", portrait[1])
        self.assertFalse(low_resolution[0])
        self.assertIn("below 1920x1080", low_resolution[1])

    def test_video_result_becomes_render_ready_when_acquisition_succeeds(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        episode_id = ""
        try:
            project = repository.create_project("Video acquisition")
            episode = repository.create_episode(project.project_id, "Episode")
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Hydrogen train launch",
                body="The train entered service after a public launch.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            story_id = selected.story_id
            assert story_id
            result = SearXNGResult(
                title="Hydrogen train launch footage",
                url="https://video.example/watch/launch",
                engine="example videos",
                category="videos",
                source_domain="video.example",
            )

            def fake_download(_url: str, stem: Path) -> Path:
                path = stem.with_suffix(".mp4")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"render-ready-test-clip")
                return path

            with patch(
                "pipeline.visuals.providers.probe_video_source",
                return_value={
                    "channel": "Hydrogen Project",
                    "channel_id": "official-unit-channel",
                },
            ), patch(
                "pipeline.visuals.providers._download_remote_video",
                side_effect=fake_download,
            ), patch(
                "pipeline.visuals.providers.create_thumbnail", return_value=None
            ), patch(
                "pipeline.visuals.providers.media_metadata",
                return_value={
                    "duration_seconds": 45.0,
                    "width": 1920,
                    "height": 1080,
                    "audio_codec": "aac",
                },
            ), patch(
                "pipeline.visuals.providers.analyze_media_cleanliness",
                return_value={
                    "content_cleanliness_status": "passed",
                    "approval_blockers": [],
                },
            ):
                visual = _stage_searxng_result(
                    repository,
                    story_id,
                    "sec_001_cold_open",
                    result,
                    MediaType.video,
                    0,
                    acquire_video=True,
                )

            assert visual
            self.assertIsNotNone(visual.download_path)
            self.assertEqual(visual.duration_seconds, 45.0)
            self.assertTrue(visual.has_audio)
            self.assertEqual(visual.review_status.value, "suggested")
            self.assertTrue(visual.manual_review_flag)

            portrait_result = SearXNGResult(
                title="Vertical hydrogen train short",
                url="https://video.example/watch/vertical",
                engine="example videos",
                category="videos",
                source_domain="video.example",
            )
            with patch(
                "pipeline.visuals.providers.probe_video_source",
                return_value={
                    "channel": "Hydrogen Project",
                    "channel_id": "official-unit-channel",
                },
            ), patch(
                "pipeline.visuals.providers._download_remote_video",
                side_effect=fake_download,
            ), patch(
                "pipeline.visuals.providers.create_thumbnail", return_value=None
            ), patch(
                "pipeline.visuals.providers.media_metadata",
                return_value={
                    "duration_seconds": 20.0,
                    "width": 1080,
                    "height": 1920,
                    "audio_codec": "aac",
                },
            ), patch(
                "pipeline.visuals.providers.analyze_media_cleanliness",
                return_value={
                    "content_cleanliness_status": "passed",
                    "approval_blockers": [],
                },
            ):
                portrait = _stage_searxng_result(
                    repository,
                    story_id,
                    "sec_001_cold_open",
                    portrait_result,
                    MediaType.video,
                    1,
                    acquire_video=True,
                )

            assert portrait
            self.assertIsNone(portrait.download_path)
            self.assertEqual(portrait.visual_quality_score, 0.15)
            self.assertTrue(
                any("rejected for broadcast layout" in item for item in portrait.warnings)
            )
        finally:
            repository.close()
            temp.cleanup()
            if episode_id:
                shutil.rmtree(
                    PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True
                )

    def test_client_normalizes_image_results(self) -> None:
        response = _JSONResponse(
            {
                "results": [
                    {
                        "title": "Launch photo",
                        "url": "https://news.example/story",
                        "content": "A launch photographed today.",
                        "engine": "example images",
                        "category": "images",
                        "img_src": "https://cdn.example/launch.jpg",
                        "thumbnail_src": "https://cdn.example/launch-thumb.jpg",
                        "score": 2.5,
                    }
                ]
            }
        )
        with patch.dict(
            os.environ,
            {"SYNTHPOST_SEARXNG_URL": "http://127.0.0.1:8888"},
        ), patch("pipeline.search.searxng_client.urlopen", return_value=response):
            results = search("launch", categories=["images"], limit=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source_domain, "news.example")
        self.assertEqual(results[0].image_url, "https://cdn.example/launch.jpg")
        self.assertEqual(results[0].engine, "example images")

    def test_research_pack_adds_related_searxng_documents(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        try:
            project = repository.create_project("Research")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Major satellite launch changes regional connectivity",
                body=(
                    "The satellite launch expanded regional connectivity for remote communities. "
                    "Officials said the system would enter service after final testing."
                ),
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            story_id = selected.story_id
            assert story_id
            coverage = SimpleNamespace(
                angles=[
                    SimpleNamespace(
                        articles=[
                            {
                                "title": "Independent launch coverage",
                                "url": "https://news.example/launch",
                                "source": "news.example",
                                "published_at": "2026-07-10T00:00:00Z",
                                "snippet": "Independent reporting on the launch.",
                            }
                        ]
                    )
                ]
            )
            related = SourceDocument(
                story_id=story_id,
                url="https://news.example/launch",
                title="Independent launch coverage",
                publisher="news.example",
                content_text=(
                    "Independent observers confirmed that the satellite reached its planned orbit."
                ),
                content_hash="related-hash",
                document_type="related_news_article",
            )
            with patch.dict(
                os.environ,
                {"SYNTHPOST_SEARXNG_URL": "http://127.0.0.1:8888"},
            ), patch(
                "pipeline.research.extract.discover_news", return_value=coverage
            ), patch(
                "pipeline.research.extract.source_document_from_search_result",
                return_value=related,
            ):
                pack = build_research_pack(repository, story_id)
            self.assertEqual(len(pack.documents), 2)
            self.assertTrue(
                any(document.publisher == "news.example" for document in pack.documents)
            )
            self.assertIn("Reviewed 2 source documents", pack.research_summary)
        finally:
            repository.close()
            temp.cleanup()

    def test_video_lead_cannot_be_approved_without_local_media(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        episode_id = ""
        try:
            project = repository.create_project("Visuals")
            episode = repository.create_episode(project.project_id, "Episode")
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Launch footage",
                body="A launch took place after weather conditions cleared at the spaceport.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            story_id = selected.story_id
            assert story_id
            result = SearXNGResult(
                title="Launch video",
                url="https://video.example/watch/123",
                engine="example videos",
                category="videos",
                source_domain="video.example",
            )
            with patch.dict(
                os.environ,
                {
                    "SYNTHPOST_SEARXNG_DOWNLOAD_VIDEOS": "0",
                    "SYNTHPOST_INCLUDE_VISUAL_LEADS": "1",
                },
            ):
                visual = _stage_searxng_result(
                    repository, story_id, None, result, MediaType.video, 0
                )
            assert visual
            self.assertIsNone(visual.download_path)
            with self.assertRaisesRegex(ValueError, "content-cleanliness gate"):
                approve_visual(repository, visual.asset_id, manual=True)
        finally:
            repository.close()
            temp.cleanup()
            if episode_id:
                shutil.rmtree(PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
