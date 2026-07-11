from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.db.repository import Repository
from pipeline.discovery.discover import (
    add_manual_story,
    canonicalize_url,
    duplicate_group,
    normalize_title,
    score_candidate,
)
from pipeline.manifest_builder import build_story_manifest, hydrate_timeline_visuals
from pipeline.models import (
    AudioMode,
    ContentRole,
    MediaType,
    RightsTier,
    ScriptDocument,
    ScriptSection,
    SegmentAnchor,
    SegmentAudio,
    SegmentOverlays,
    SegmentTemplate,
    SegmentVisual,
    SourceDefinition,
    SourceType,
    StoryCandidate,
    StorySelectionStatus,
    StoryWorkflowState,
    TimelinePlan,
    TimelineSegment,
    VisualCandidate,
)
from pipeline.research.extract import build_research_pack
from pipeline.run_story import _sync_timeline_to_avatar_duration
from pipeline.scripts.generation import approve_script, save_manual_script
from pipeline.scripts.generation import (
    compact_research_pack_for_prompt,
    expand_long_form_script,
    section_word_targets,
)
from pipeline.llm.providers import MockProvider
from pipeline.storage import PROJECT_ROOT
from pipeline.timeline.planner import (
    approved_visuals_by_section,
    approve_timeline,
    choose_template,
    choose_audio_mode,
    generate_timeline,
    select_template,
)
from pipeline.timeline.templates import TEMPLATE_REGISTRY, template_registry_json
from pipeline.timeline.validation import validate_timeline
from pipeline.visuals.providers import (
    _result_matches_query,
    _visual_search_plan,
    _visual_search_queries,
    _visual_search_tasks,
    approve_visual,
    stage_local_visual,
)
from pipeline.workflow import assert_transition, can_transition
from assembly.stitch_episode import story_manifests


class V2WorkflowAndPipelineTests(unittest.TestCase):
    def test_long_form_script_expands_in_section_sized_chunks(self) -> None:
        outline = ScriptDocument(
            story_id="story_long_form",
            headline="Hydrogen train pilot",
            sections=[
                ScriptSection(
                    section_id="sec_001_cold_open",
                    section_type="cold_open",
                    text="A grounded hydrogen train pilot is beginning.",
                    claim_ids=["claim_001"],
                )
            ],
        )
        pack = {
            "story_id": "story_long_form",
            "research_summary": "A sourced pilot briefing.",
            "documents": [],
            "claims": [
                {
                    "claim_id": "claim_001",
                    "claim_text": "The hydrogen train pilot is documented.",
                }
            ],
            "evidence": [],
        }

        expanded, attempts = expand_long_form_script(
            MockProvider(), outline, pack, target_duration_seconds=600
        )

        self.assertEqual(len(expanded.sections), 9)
        self.assertGreaterEqual(expanded.estimated_duration_seconds, 590)
        self.assertLessEqual(expanded.estimated_duration_seconds, 610)
        self.assertEqual(attempts, 9)

    def test_fullscreen_audio_policy_only_replaces_narration_for_audible_video(
        self,
    ) -> None:
        image = VisualCandidate(
            story_id="story_audio_policy",
            provider="unit",
            media_type=MediaType.image,
            content_role=ContentRole.context,
        )
        silent_video = VisualCandidate(
            story_id="story_audio_policy",
            provider="unit",
            media_type=MediaType.video,
            content_role=ContentRole.primary_footage,
            has_audio=False,
        )
        audible_video = silent_video.model_copy(update={"has_audio": True})

        self.assertEqual(
            choose_audio_mode("fullscreen_news_visual", image),
            AudioMode.narration,
        )
        self.assertEqual(
            choose_audio_mode("fullscreen_news_visual", silent_video),
            AudioMode.narration,
        )
        self.assertEqual(
            choose_audio_mode("fullscreen_news_visual", audible_video),
            AudioMode.source,
        )
        self.assertEqual(
            choose_audio_mode("split_anchor_visual", audible_video),
            AudioMode.narration,
        )

    def test_editorial_template_policy_creates_balanced_story_rhythm(self) -> None:
        hero = VisualCandidate(
            asset_id="visual_hero",
            story_id="story_template_rhythm",
            provider="unit",
            media_type=MediaType.image,
            content_role=ContentRole.context,
            rights_tier=RightsTier.green,
            review_status="approved",
            relevance_score=0.65,
            visual_quality_score=0.65,
            width=1600,
            height=900,
        )
        fallback = VisualCandidate(
            asset_id="visual_anchor_fallback",
            story_id="story_template_rhythm",
            provider="synthpost_anchor_fallback",
            media_type=MediaType.fallback,
            content_role=ContentRole.fallback,
            rights_tier=RightsTier.green,
            review_status="approved",
        )
        section_types = [
            "cold_open",
            "context",
            "key_developments",
            "why_it_matters",
            "uncertainty",
            "conclusion",
        ]
        visuals = [hero, hero, hero, hero, fallback, hero]
        selected: list[str] = []

        for index, (section_type, visual) in enumerate(
            zip(section_types, visuals, strict=True)
        ):
            decision = select_template(
                section_type,
                visual,
                index,
                total_sections=len(section_types),
                previous_templates=selected,
                script_text=(
                    "This editorial narration explains the development with enough "
                    "context, evidence, operational detail, and careful qualification "
                    "to require a composed visual rhythm without becoming an overly "
                    "long or crowded television segment."
                ),
            )
            selected.append(decision.template_id)

        self.assertEqual(
            selected,
            [
                "fullscreen_anchor",
                "split_anchor_visual",
                "fullscreen_news_visual",
                "split_anchor_visual",
                "fullscreen_anchor",
                "fullscreen_news_visual",
            ],
        )
        self.assertTrue(
            all(
                len(set(selected[index : index + 3])) > 1
                for index in range(len(selected) - 2)
            )
        )

    def test_real_media_outranks_anchor_only_fallback(self) -> None:
        fallback = VisualCandidate(
            asset_id="visual_fallback",
            story_id="story_visual_priority",
            section_ids=["sec_context"],
            provider="synthpost_anchor_fallback",
            media_type=MediaType.fallback,
            content_role=ContentRole.fallback,
            rights_tier=RightsTier.green,
            review_status="approved",
            visual_quality_score=1.0,
        )
        real = VisualCandidate(
            asset_id="visual_real",
            story_id="story_visual_priority",
            section_ids=["sec_context"],
            provider="unit",
            media_type=MediaType.image,
            content_role=ContentRole.context,
            rights_tier=RightsTier.green,
            review_status="approved",
            relevance_score=0.6,
            width=1920,
            height=1080,
            content_cleanliness_status="passed",
        )

        selected = approved_visuals_by_section([fallback, real])

        self.assertEqual(selected["sec_context"].asset_id, "visual_real")
        self.assertEqual(choose_template("context", fallback, 2), "fallback_anchor")

        undersized = real.model_copy(
            update={
                "asset_id": "visual_undersized",
                "width": 1024,
                "height": 576,
            }
        )
        selected_without_hd = approved_visuals_by_section([fallback, undersized])
        self.assertEqual(
            selected_without_hd["sec_context"].asset_id, "visual_fallback"
        )

    def test_manifest_replaces_legacy_generated_card_with_anchor_fallback(self) -> None:
        plan = TimelinePlan(
            story_id="story_legacy_fallback",
            status="approved",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="sec_uncertainty",
                    start_time=0,
                    end_time=5,
                    duration=5,
                    script_text="A section without approved source media.",
                    visual=SegmentVisual(
                        asset_id="visual_legacy_generated",
                        path="legacy-generated-card.svg",
                        media_type=MediaType.image,
                        content_role=ContentRole.context,
                        attribution_text="SynthPost generated visual",
                    ),
                    template=SegmentTemplate(template_id="split_anchor_visual"),
                    overlays=SegmentOverlays(
                        attribution="SynthPost generated visual"
                    ),
                )
            ],
        )
        current = VisualCandidate(
            asset_id="visual_legacy_generated",
            story_id="story_legacy_fallback",
            section_ids=["sec_uncertainty"],
            provider="generated_visual_card",
            media_type=MediaType.image,
            content_role=ContentRole.context,
            rights_tier=RightsTier.green,
            review_status="approved",
        )

        hydrated = hydrate_timeline_visuals(plan, [current])
        segment = hydrated.segments[0]

        self.assertEqual(segment.template.template_id, "fallback_anchor")
        self.assertTrue(segment.anchor.visible)
        self.assertIsNone(segment.visual.asset_id)
        self.assertIsNone(segment.visual.path)
        self.assertEqual(segment.visual.media_type, MediaType.fallback)
        self.assertEqual(segment.visual.content_role, ContentRole.fallback)
        self.assertEqual(segment.overlays.attribution, "")

    def test_episode_assembly_rejects_missing_selected_story_manifest(self) -> None:
        temp = tempfile.TemporaryDirectory()
        episode_root = Path(temp.name) / "episode"
        episode_root.mkdir()
        (episode_root / "episode.json").write_text(
            '{"story_ids":["story_ready","story_missing"]}', encoding="utf-8"
        )
        ready = episode_root / "stories" / "story_ready" / "story.json"
        ready.parent.mkdir(parents=True)
        ready.write_text("{}", encoding="utf-8")
        try:
            with patch(
                "assembly.stitch_episode.episode_dir", return_value=episode_root
            ):
                with self.assertRaisesRegex(FileNotFoundError, "story_missing"):
                    story_manifests("ep_test")
        finally:
            temp.cleanup()

    def test_rediscovery_preserves_selected_story_state(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        try:
            project = repository.create_project("Rediscovery Project")
            selected_episode = repository.create_episode(
                project.project_id, "Selected Episode"
            )
            other_episode = repository.create_episode(
                project.project_id, "Other Episode"
            )
            original = StoryCandidate(
                candidate_id="cand_stable",
                title="Original headline",
                canonical_url="https://example.com/story",
                source_name="Example",
            )
            repository.upsert_candidate(original)
            selected = repository.select_candidate(
                original.candidate_id, selected_episode.episode_id
            )

            rediscovered = StoryCandidate(
                candidate_id="cand_stable",
                title="Updated headline",
                canonical_url="https://example.com/story",
                source_name="Example",
                episode_id=other_episode.episode_id,
            )
            repository.upsert_candidate(rediscovered)

            persisted = repository.get_candidate(original.candidate_id)
            self.assertEqual(persisted.title, "Updated headline")
            self.assertEqual(persisted.episode_id, selected_episode.episode_id)
            self.assertEqual(persisted.story_id, selected.story_id)
            self.assertEqual(
                persisted.selection_status, StorySelectionStatus.selected
            )
            self.assertEqual(persisted.workflow_state, StoryWorkflowState.selected)
        finally:
            repository.close()
            temp.cleanup()

    def test_manifest_hydrates_approved_timeline_attribution(self) -> None:
        plan = TimelinePlan(
            story_id="story_attribution",
            status="approved",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="sec_001_context",
                    start_time=0,
                    end_time=5,
                    duration=5,
                    script_text="A sourced segment.",
                    visual=SegmentVisual(
                        asset_id="visual_current",
                        path="old.jpg",
                        attribution_text="Old label",
                    ),
                    template=SegmentTemplate(template_id="split_anchor_visual"),
                    audio=SegmentAudio(),
                    overlays=SegmentOverlays(attribution="Old label"),
                )
            ],
        )
        current = VisualCandidate(
            asset_id="visual_current",
            story_id="story_attribution",
            provider="searxng:images",
            download_path="current.jpg",
            attribution_text="Corrected source",
            media_type="image",
            rights_tier="yellow",
            review_status="manual_approved",
        )

        hydrated = hydrate_timeline_visuals(plan, [current])

        self.assertEqual(hydrated.segments[0].visual.path, "current.jpg")
        self.assertEqual(
            hydrated.segments[0].visual.attribution_text, "Corrected source"
        )
        self.assertEqual(
            hydrated.segments[0].overlays.attribution, "Corrected source"
        )
        self.assertEqual(plan.segments[0].visual.attribution_text, "Old label")

    def test_visual_search_filters_unrelated_engine_results(self) -> None:
        from pipeline.search.searxng_client import SearXNGResult

        unrelated = SearXNGResult(
            title="How to download Ultraviewer on a laptop",
            url="https://example.com/ultraviewer",
            snippet="A computer tutorial.",
            engine="unit",
            category="videos",
        )
        relevant = SearXNGResult(
            title="Hydrogen train begins Jind–Sonipat trials",
            url="https://example.com/hydrogen-train",
            snippet="Railway pilot coverage.",
            engine="unit",
            category="images",
        )

        self.assertFalse(_result_matches_query(unrelated, "hydrogen train launch date"))
        self.assertTrue(_result_matches_query(relevant, "hydrogen train launch date"))

    def test_fallback_visual_queries_cover_every_section(self) -> None:
        class QueryRepository:
            def latest_script(self, story_id: str, *, approved: bool = False):
                return ScriptDocument(
                    story_id=story_id,
                    headline="Hydrogen train",
                    status="approved",
                    sections=[
                        ScriptSection(
                            section_id=f"sec_{index:03d}_context",
                            section_type="context",
                            text=f"Section {index}",
                            suggested_search_queries=[
                                f"section {index} primary",
                                f"section {index} secondary",
                            ],
                        )
                        for index in range(1, 4)
                    ],
                )

            def candidate_for_story(self, story_id: str):
                return type("Candidate", (), {"title": "Hydrogen train"})()

        queries = _visual_search_queries(QueryRepository(), "story_unit")

        self.assertEqual(
            queries,
            [
                ("sec_001_context", "section 1 primary"),
                ("sec_002_context", "section 2 primary"),
                ("sec_003_context", "section 3 primary"),
            ],
        )

    def test_visual_query_plan_uses_separate_grounded_footage_query(self) -> None:
        class QueryProvider:
            name = "unit-ai"

            def generate_json(self, prompt, schema, *, temperature=None):
                self.prompt = prompt
                return {
                    "queries": [
                        {
                            "section_id": "sec_001_cold_open",
                            "image_query": "Jind Sonipat hydrogen train launch photo",
                            "video_query": "PM Modi hydrogen train flag off video",
                            "video_priority": True,
                            "rationale": "the opening needs launch footage",
                        }
                    ]
                }

        class QueryRepository:
            def latest_script(self, story_id: str, *, approved: bool = False):
                return ScriptDocument(
                    story_id=story_id,
                    headline="India hydrogen train pilot",
                    status="approved",
                    sections=[
                        ScriptSection(
                            section_id="sec_001_cold_open",
                            section_type="cold_open",
                            text="The Jind Sonipat hydrogen train pilot begins.",
                            suggested_visual_types=["image", "video"],
                            suggested_search_queries=[
                                "Jind Sonipat hydrogen train launch photo",
                                "PM Modi hydrogen train flag off video",
                            ],
                        )
                    ],
                )

            def candidate_for_story(self, story_id: str):
                return type(
                    "Candidate", (), {"title": "India hydrogen train pilot"}
                )()

        provider = QueryProvider()
        with patch(
            "pipeline.visuals.providers.configured_provider",
            return_value=provider,
        ):
            plans = _visual_search_plan(QueryRepository(), "story_unit")

        self.assertEqual(len(plans), 1)
        self.assertEqual(
            plans[0].image_query, "Jind Sonipat hydrogen train launch photo"
        )
        self.assertEqual(
            plans[0].video_query,
            "PM Modi hydrogen train flag off video official raw footage",
        )
        self.assertTrue(plans[0].video_priority)
        self.assertIn("visual search keyword planner", provider.prompt)
        self.assertIn("India hydrogen train pilot", provider.prompt)

    def test_visual_query_cap_counts_actual_searxng_requests(self) -> None:
        plans = [
            type(
                "Plan",
                (),
                {
                    "section_id": f"sec_{index}",
                    "image_query": f"section {index} editorial image",
                    "video_query": f"section {index} news footage",
                    "video_priority": index % 2 == 0,
                },
            )()
            for index in range(1, 5)
        ]

        tasks = _visual_search_tasks(plans, max_queries=6)

        self.assertEqual(len(tasks), 6)
        self.assertEqual(
            {task[0].section_id for task in tasks[:4]},
            {"sec_1", "sec_2", "sec_3", "sec_4"},
        )
        self.assertEqual(tasks[0][1], "images")
        self.assertEqual(tasks[1][1], "videos")

    def test_visual_relevance_requires_more_than_one_generic_overlap(self) -> None:
        from pipeline.search.searxng_client import SearXNGResult

        weak = SearXNGResult(
            title="Hydrogen cars explained",
            url="https://example.com/hydrogen-cars",
            snippet="Passenger vehicle technology.",
            engine="unit",
            category="images",
        )

        self.assertFalse(
            _result_matches_query(
                weak, "Jind Sonipat hydrogen train launch photo"
            )
        )

    def test_manual_script_edit_preserves_generated_provenance(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        try:
            project = repository.create_project("Script provenance")
            episode = repository.create_episode(project.project_id, "Episode")
            candidate = add_manual_story(
                repository,
                title="Hydrogen train pilot",
                body="A sourced test story.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(candidate.candidate_id, episode.episode_id)
            story_id = selected.story_id
            assert story_id is not None
            generated = ScriptDocument(
                story_id=story_id,
                headline="Generated headline",
                category="transport",
                source_ids=["doc_primary"],
                warnings=["llm_provider=ollama"],
                sections=[
                    ScriptSection(
                        section_id="sec_001_cold_open",
                        section_type="cold_open",
                        text="Generated paragraph.",
                        claim_ids=["claim_launch"],
                        suggested_visual_types=["train"],
                        suggested_search_queries=["Jind hydrogen train"],
                        suggested_template_ids=["fullscreen_visual"],
                        editorial_notes=["Keep date hedged"],
                    )
                ],
            )
            repository.save_script(generated)

            edited = save_manual_script(
                repository,
                story_id,
                "Edited headline",
                "A more careful, viewer-focused paragraph.",
            )

            self.assertEqual(edited.category, "transport")
            self.assertEqual(edited.source_ids, ["doc_primary"])
            self.assertEqual(edited.warnings, ["llm_provider=ollama"])
            self.assertEqual(edited.sections[0].section_id, "sec_001_cold_open")
            self.assertEqual(edited.sections[0].section_type, "cold_open")
            self.assertEqual(edited.sections[0].claim_ids, ["claim_launch"])
            self.assertEqual(
                edited.sections[0].suggested_search_queries,
                ["Jind hydrogen train"],
            )
            self.assertEqual(edited.sections[0].editorial_notes, ["Keep date hedged"])
        finally:
            repository.close()
            temp.cleanup()

    def test_short_script_word_targets_are_positive_and_sum_to_target(self) -> None:
        targets = section_word_targets(90)
        self.assertEqual(sum(targets.values()), round(90 * 145 / 60))
        self.assertTrue(all(value > 0 for value in targets.values()))
        self.assertNotIn("outro", targets)

    def test_generation_prompt_pack_excludes_scraped_document_bodies(self) -> None:
        compact = compact_research_pack_for_prompt(
            {
                "story_id": "story_unit",
                "documents": [
                    {
                        "document_id": "doc_unit",
                        "title": "Unit source",
                        "content_text": "large scraped article body",
                    }
                ],
                "claims": [],
                "people": ["boilerplate entity"],
            }
        )
        self.assertNotIn("content_text", compact["documents"][0])
        self.assertNotIn("people", compact)

    def test_workflow_blocks_invalid_transition(self) -> None:
        self.assertTrue(
            can_transition(StoryWorkflowState.discovered, StoryWorkflowState.selected)
        )
        with self.assertRaises(ValueError):
            assert_transition(
                StoryWorkflowState.discovered, StoryWorkflowState.completed
            )

    def test_url_canonicalization_and_duplicate_grouping_are_deterministic(
        self,
    ) -> None:
        first = canonicalize_url("HTTPS://Example.com/story/?utm_source=x&b=2#frag")
        second = canonicalize_url("https://example.com/story?b=2")
        self.assertEqual(first, second)
        self.assertEqual(normalize_title("  Big  Story!!! "), "big story")
        self.assertEqual(
            duplicate_group("Title", first), duplicate_group("Other", second)
        )

    def test_story_scoring_is_deterministic(self) -> None:
        source = SourceDefinition(
            name="Unit Feed",
            source_id="src_unit",
            source_type=SourceType.rss,
            feed_url="https://example.com/rss",
            reliability_score=0.8,
        )
        a = score_candidate(
            source,
            "Major AI chip market ruling",
            "A court decision affects billions in the market",
            None,
        )
        b = score_candidate(
            source,
            "Major AI chip market ruling",
            "A court decision affects billions in the market",
            None,
        )
        self.assertEqual(a, b)

    def test_rights_validation_blocks_red_asset(self) -> None:
        with self.assertRaises(ValueError):
            VisualCandidate(
                story_id="story_red",
                provider="unit",
                media_type="image",
                content_role="context",
                rights_tier="red",
                review_status="approved",
            )

    def test_default_timeline_templates_preserve_retained_anchor_look(self) -> None:
        self.assertEqual(choose_template("intro", None, 0), "fullscreen_anchor")
        self.assertEqual(choose_template("context", None, 1), "fallback_anchor")

    def test_non_quote_card_templates_are_blacklisted_for_production(self) -> None:
        blacklisted = {
            "document_callout",
            "chart_explainer",
            "map_explainer",
            "timeline_explainer",
            "comparison_card",
            "bullet_summary",
            "source_screenshot",
            "fallback_context_card",
        }
        production_registry = template_registry_json()
        production_ids = {template["template_id"] for template in production_registry}
        all_ids = {
            template["template_id"]
            for template in template_registry_json(production_only=False)
        }
        self.assertIn("quote_card", production_ids)
        self.assertTrue(blacklisted.issubset(all_ids))
        self.assertTrue(blacklisted.isdisjoint(production_ids))
        for template in production_registry:
            self.assertNotIn(template["fallback_template_id"], blacklisted)
        for template_id in blacklisted:
            self.assertFalse(TEMPLATE_REGISTRY[template_id].production_enabled)
            self.assertIn(
                "Blacklisted", TEMPLATE_REGISTRY[template_id].blacklist_reason or ""
            )

    def test_planner_routes_documents_charts_and_maps_to_retained_split_shell(
        self,
    ) -> None:
        for media_type, content_role in [
            (MediaType.document, ContentRole.document),
            (MediaType.chart, ContentRole.data),
            (MediaType.map, ContentRole.location),
        ]:
            visual = VisualCandidate(
                story_id="story_template_blacklist",
                provider="unit",
                media_type=media_type,
                content_role=content_role,
                rights_tier=RightsTier.green,
                review_status="approved",
            )
            self.assertEqual(
                choose_template("context", visual, 1), "split_anchor_visual"
            )

    def test_validation_rejects_blacklisted_card_templates(self) -> None:
        plan = TimelinePlan(
            story_id="story_blacklisted_template",
            segments=[
                TimelineSegment(
                    segment_id="seg_001",
                    section_id="context_1",
                    start_time=0,
                    end_time=4,
                    duration=4,
                    script_text="A blacklisted card should not pass production validation.",
                    anchor=SegmentAnchor(visible=False, speaking=True),
                    visual=SegmentVisual(
                        media_type=MediaType.fallback,
                        content_role=ContentRole.fallback,
                    ),
                    template=SegmentTemplate(template_id="fallback_context_card"),
                    audio=SegmentAudio(),
                    overlays=SegmentOverlays(),
                )
            ],
        )

        errors, _warnings = validate_timeline(plan, check_media_exists=False)

        self.assertTrue(any("blacklisted for production" in error for error in errors))

    def test_avatar_duration_rescale_removes_pure_narration_timeline_gaps(self) -> None:
        manifest = {
            "script": {"text": "One sentence. Another sentence."},
            "direction": {"estimated_duration_seconds": 37.8},
            "approved_timeline": {
                "status": "approved",
                "duration_seconds": 30.0,
                "audio_plan": {
                    "duration_seconds": 30.0,
                    "regions": [
                        {"segment_id": "seg_001", "start_time": 0.0, "end_time": 10.0},
                        {"segment_id": "seg_002", "start_time": 10.0, "end_time": 30.0},
                    ],
                },
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "start_time": 0.0,
                        "end_time": 10.0,
                        "duration": 10.0,
                        "audio": {"mode": "narration"},
                        "visual": {"audio_mode": "muted"},
                    },
                    {
                        "segment_id": "seg_002",
                        "start_time": 10.0,
                        "end_time": 30.0,
                        "duration": 20.0,
                        "audio": {"mode": "narration"},
                        "visual": {"audio_mode": "muted"},
                    },
                ],
            },
        }

        changed = _sync_timeline_to_avatar_duration(manifest)

        self.assertTrue(changed)
        timeline = manifest["approved_timeline"]
        segments = timeline["segments"]
        self.assertEqual(timeline["timing_source"], "avatar_duration_rescaled")
        self.assertEqual(timeline["duration_seconds"], 37.8)
        self.assertEqual(segments[0]["start_time"], 0.0)
        self.assertEqual(segments[0]["end_time"], segments[1]["start_time"])
        self.assertEqual(segments[-1]["end_time"], 37.8)
        self.assertAlmostEqual(
            sum(segment["duration"] for segment in segments), 37.8, places=2
        )
        self.assertEqual(timeline["audio_plan"]["regions"][1]["start_time"], 12.6)
        self.assertEqual(timeline["audio_plan"]["regions"][1]["duration"], 25.2)
        self.assertEqual(
            timeline["duration_seconds"],
            manifest["direction"]["performance_beats"][-1]["end"],
        )

    def test_avatar_duration_rescale_prefers_real_audio_duration(self) -> None:
        manifest = {
            "direction": {
                "estimated_duration_seconds": 30.0,
                "audio_duration_seconds": 42.0,
            },
            "approved_timeline": {
                "status": "APPROVED",
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "start_time": 0.0,
                        "end_time": 10.0,
                        "duration": 10.0,
                        "audio": {"mode": "narration"},
                        "visual": {"audio_mode": "muted"},
                    }
                ],
            },
        }

        changed = _sync_timeline_to_avatar_duration(manifest)

        self.assertTrue(changed)
        self.assertEqual(manifest["approved_timeline"]["duration_seconds"], 42.0)
        self.assertEqual(manifest["approved_timeline"]["segments"][0]["end_time"], 42.0)

    def test_avatar_duration_rescale_skips_source_audio_timelines(self) -> None:
        manifest = {
            "direction": {"estimated_duration_seconds": 37.8},
            "approved_timeline": {
                "status": "approved",
                "duration_seconds": 30.0,
                "segments": [
                    {
                        "segment_id": "seg_001",
                        "start_time": 0.0,
                        "end_time": 30.0,
                        "duration": 30.0,
                        "audio": {"mode": "source"},
                        "visual": {"audio_mode": "original"},
                    }
                ],
            },
        }

        changed = _sync_timeline_to_avatar_duration(manifest)

        self.assertFalse(changed)
        timeline = manifest["approved_timeline"]
        self.assertEqual(timeline["segments"][0]["end_time"], 30.0)
        self.assertIn("source/mixed audio", timeline["timing_sync_warning"])

    def test_manual_vertical_slice_builds_renderer_manifest(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "test.sqlite3")
        episode_id = ""
        story_id = None
        try:
            project = repository.create_project("Unit Project")
            episode = repository.create_episode(
                project.project_id, "Unit Episode", render_profile="preview"
            )
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Unit story for SynthPost Studio",
                body="SynthPost Studio keeps renderer approvals explicit. The timeline uses approved media and blocks unsafe rights states.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            story_id = selected.story_id
            assert story_id is not None
            build_research_pack(repository, story_id)
            script = save_manual_script(
                repository,
                story_id,
                "Unit story for SynthPost Studio",
                "SynthPost Studio keeps renderer approvals explicit.\n\nThe approved timeline becomes the rendering source of truth.",
            )
            approve_script(repository, story_id)
            image = (
                PROJECT_ROOT
                / "compositor"
                / "remotion_renderer"
                / "public"
                / "news"
                / "datacenter-server-racks.jpg"
            )
            visual = stage_local_visual(
                repository,
                story_id,
                image,
                section_ids=[script.sections[-1].section_id],
                content_role=ContentRole.context,
                rights_tier=RightsTier.green,
            )
            visual.content_cleanliness_status = "passed"
            repository.upsert_visual(visual)
            approve_visual(repository, visual.asset_id)
            plan = generate_timeline(repository, story_id)
            errors, _warnings = validate_timeline(plan)
            self.assertEqual(errors, [])
            approved = approve_timeline(repository, story_id)
            manifest = build_story_manifest(
                repository, story_id, render_profile="preview", test_mode=True
            )
            self.assertEqual(manifest["approved_timeline"]["status"], "approved")
            self.assertEqual(manifest["composition"]["template"], "timeline_story")
            self.assertTrue(
                (
                    PROJECT_ROOT
                    / "episodes"
                    / episode_id
                    / "stories"
                    / story_id
                    / "story.json"
                ).exists()
            )
        finally:
            repository.close()
            temp.cleanup()
            shutil.rmtree(PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
