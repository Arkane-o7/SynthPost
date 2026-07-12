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
from pipeline.models import MediaType, SourceDefinition, SourceDocument, SourceType, StoryCandidate
from pipeline.news.discovery import (
    diversified_articles,
    discover_news,
    research_queries,
)
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
    download_visual,
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
    def test_research_queries_use_headline_topic_and_summary(self) -> None:
        candidate = StoryCandidate(
            title="Central bank cuts interest rates after inflation slows",
            source_name="Example",
            category="economy",
            summary="Borrowing costs and consumer prices are central to the decision.",
        )

        queries = research_queries(candidate)

        self.assertEqual(queries[0], candidate.title)
        self.assertGreaterEqual(len(queries), 2)
        self.assertTrue(any("economy" in query for query in queries))

    def test_news_research_combines_multiple_queries_and_diversifies_publishers(
        self,
    ) -> None:
        candidate = StoryCandidate(
            title="Central bank cuts interest rates after inflation slows",
            canonical_url="https://lead.example/rates",
            source_name="Lead",
            category="economy",
            summary="The rate decision follows several months of lower inflation.",
        )

        def fake_search(query, **_kwargs):
            suffix = "policy" if query == candidate.title else "markets"
            return [
                SearXNGResult(
                    title=f"Central bank interest rate cut reshapes {suffix}",
                    url=f"https://{suffix}.example/rate-cut",
                    snippet="Inflation slowed before the central bank decision.",
                    source_domain=f"{suffix}.example",
                    published_date="2026-07-12T08:00:00Z",
                )
            ]

        with patch(
            "pipeline.news.discovery.searxng_configured", return_value=True
        ), patch("pipeline.news.discovery.search", side_effect=fake_search):
            coverage = discover_news(candidate)

        articles = [
            article for angle in coverage.angles for article in angle.articles
        ]
        self.assertGreaterEqual(len(coverage.queries), 2)
        self.assertEqual(
            {article["source"] for article in articles},
            {"policy.example", "markets.example"},
        )
        self.assertTrue(
            all(article["discovery_method"] == "searxng" for article in articles)
        )

    def test_news_research_uses_enabled_rss_sources_without_searxng(self) -> None:
        candidate = StoryCandidate(
            title="Satellite launch expands regional connectivity",
            canonical_url="https://lead.example/satellite",
            source_name="Lead",
            category="technology",
            summary="The spacecraft will connect remote communities.",
        )
        source = SourceDefinition(
            source_id="src_related",
            name="Related Wire",
            source_type=SourceType.rss,
            feed_url="https://related.example/feed.xml",
        )
        related = StoryCandidate(
            title="Satellite launch brings connectivity to remote communities",
            canonical_url="https://related.example/satellite-connectivity",
            source_id=source.source_id,
            source_name=source.name,
            published_at="2026-07-12T07:00:00Z",
            summary="The regional satellite entered orbit after launch.",
        )
        repository = SimpleNamespace(list_sources=lambda **_kwargs: [source])

        with patch(
            "pipeline.news.discovery.searxng_configured", return_value=False
        ), patch(
            "pipeline.news.discovery.discover_from_source", return_value=[related]
        ):
            coverage = discover_news(candidate, repository=repository)

        articles = [
            article for angle in coverage.angles for article in angle.articles
        ]
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source"], "Related Wire")
        self.assertEqual(articles[0]["discovery_method"], "rss_related_coverage")

    def test_article_selection_prefers_distinct_publishers(self) -> None:
        articles = [
            {
                "title": "Wire A first",
                "url": "https://wire-a.example/one",
                "source": "Wire A",
                "relevance_score": 0.90,
            },
            {
                "title": "Wire A second",
                "url": "https://wire-a.example/two",
                "source": "Wire A",
                "relevance_score": 0.88,
            },
            {
                "title": "Wire B",
                "url": "https://wire-b.example/one",
                "source": "Wire B",
                "relevance_score": 0.80,
            },
        ]

        selected = diversified_articles(articles, limit=2)

        self.assertEqual([article["source"] for article in selected], ["Wire A", "Wire B"])

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

    def test_video_source_is_downloaded_for_editor_review(self) -> None:
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
            def fake_download(_url: str, stem: Path) -> Path:
                path = stem.with_suffix(".mp4")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"broadcaster-review-clip")
                return path

            with patch(
                "pipeline.visuals.providers._download_remote_video",
                side_effect=fake_download,
            ) as download, patch(
                "pipeline.visuals.providers.create_thumbnail", return_value=None
            ), patch(
                "pipeline.visuals.providers.media_metadata",
                return_value={
                    "duration_seconds": 30.0,
                    "width": 1920,
                    "height": 1080,
                    "audio_codec": "aac",
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
            download.assert_called_once()
            self.assertEqual(visual.source_class, "editor_review")
            self.assertEqual(visual.content_cleanliness_status, "passed")
            self.assertEqual(visual.review_status.value, "suggested")
            self.assertEqual(visual.rights_tier.value, "yellow")
            self.assertIsNotNone(visual.download_path)
            self.assertIsNone(visual.quarantine_path)
        finally:
            repository.close()
            temp.cleanup()
            if episode_id:
                shutil.rmtree(PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True)

    def test_broadcast_fit_accepts_template_ratios_and_rejects_bad_media(self) -> None:
        fullscreen = broadcast_media_fit(1920, 1080)
        split = broadcast_media_fit(1920, 1280)
        portrait = broadcast_media_fit(1080, 1920)
        relaxed_image = broadcast_media_fit(1600, 1280, MediaType.image)
        same_ratio_video = broadcast_media_fit(1600, 1280, MediaType.video)
        low_resolution = broadcast_media_fit(1024, 576)

        self.assertTrue(fullscreen[0])
        self.assertTrue(split[0])
        self.assertTrue(relaxed_image[0])
        self.assertFalse(same_ratio_video[0])
        self.assertFalse(portrait[0])
        self.assertIn("outside landscape range", portrait[1])
        self.assertFalse(low_resolution[0])
        self.assertIn("below 1280x720", low_resolution[1])

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
            with self.assertRaisesRegex(ValueError, "without local media"):
                approve_visual(repository, visual.asset_id, manual=True)
        finally:
            repository.close()
            temp.cleanup()
            if episode_id:
                shutil.rmtree(PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True)

    def test_video_lead_can_be_downloaded_then_manually_approved(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        episode_id = ""
        try:
            project = repository.create_project("Visual downloads")
            episode = repository.create_episode(project.project_id, "Episode")
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Senate footage",
                body="The Senate convened for a vote.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            story_id = selected.story_id
            assert story_id
            result = SearXNGResult(
                title="Senate floor video",
                url="https://video.example/watch/456",
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
                lead = _stage_searxng_result(
                    repository, story_id, None, result, MediaType.video, 0
                )
            assert lead

            def fake_download(_url: str, stem: Path) -> Path:
                path = stem.with_suffix(".mp4")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"video")
                return path

            with patch(
                "pipeline.visuals.providers._download_remote_video",
                side_effect=fake_download,
            ), patch(
                "pipeline.visuals.providers.create_thumbnail", return_value=None
            ), patch(
                "pipeline.visuals.providers.media_metadata",
                return_value={
                    "duration_seconds": 20.0,
                    "width": 1920,
                    "height": 1080,
                    "audio_codec": "aac",
                },
            ):
                downloaded = download_visual(repository, lead.asset_id)

            self.assertIsNotNone(downloaded.download_path)
            self.assertTrue(downloaded.has_audio)
            self.assertEqual(downloaded.content_cleanliness_status, "passed")
            self.assertFalse(
                any("download failed" in warning for warning in downloaded.warnings)
            )
            approved = approve_visual(repository, lead.asset_id, manual=True)
            self.assertEqual(approved.review_status.value, "manual_approved")
        finally:
            repository.close()
            temp.cleanup()
            if episode_id:
                shutil.rmtree(PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
