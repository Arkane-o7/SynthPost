from __future__ import annotations

import asyncio
import inspect
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class V2ContractTests(unittest.TestCase):
    def test_schema_contains_required_contracts(self) -> None:
        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "synthpost.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        defs = schema["$defs"]
        for name in [
            "Project",
            "Episode",
            "SourceDefinition",
            "StoryCandidate",
            "EditorialFitAssessment",
            "SourceDocument",
            "ResearchPack",
            "ScriptDocument",
            "NarrationArtifact",
            "VisualCandidate",
            "TimelinePlan",
            "RenderJob",
            "AutonomyQaFinding",
            "AutonomyQaCheck",
            "AutonomyQaView",
            "AutonomyPolicy",
            "AutonomyRun",
            "AutonomyRunView",
            "GenerationAudit",
            "ArtifactRecord",
        ]:
            self.assertIn(name, defs)
            self.assertGreater(len(defs[name]["required"]), 3)

    def test_typescript_exports_match_schema_names(self) -> None:
        ts = (ROOT / "contracts" / "typescript" / "index.ts").read_text(
            encoding="utf-8"
        )
        for name in [
            "Project",
            "Episode",
            "SourceDefinition",
            "StoryCandidate",
            "EditorialFitAssessment",
            "SourceDocument",
            "ResearchPack",
            "ScriptDocument",
            "NarrationArtifact",
            "VisualCandidate",
            "TimelinePlan",
            "RenderJob",
            "AutonomyQaFinding",
            "AutonomyQaCheck",
            "AutonomyQaView",
            "AutonomyPolicy",
            "AutonomyRun",
            "AutonomyRunView",
            "GenerationAudit",
            "ArtifactRecord",
        ]:
            self.assertIn(f"export type {name}", ts)

    def test_script_sections_own_their_broadcast_overlays(self) -> None:
        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "synthpost.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        section = schema["$defs"]["ScriptSection"]
        ts = (ROOT / "contracts" / "typescript" / "index.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("lower_third", section["required"])
        self.assertIn("chyron", section["required"])
        self.assertIn("headline_cues", section["required"])
        self.assertIn("beats", section["properties"])
        self.assertIn("lower_third: string", ts)
        self.assertIn("chyron: string", ts)
        self.assertIn("headline_cues: string[]", ts)
        self.assertIn("beats: ScriptBeat[]", ts)

    def test_script_contract_exposes_independent_narration_mode(self) -> None:
        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "synthpost.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        script = schema["$defs"]["ScriptDocument"]
        ts = (ROOT / "contracts" / "typescript" / "index.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("narration_mode", script["required"])
        self.assertEqual(
            script["properties"]["narration_mode"]["enum"],
            ["signal", "explained", "deep_dive", "india_builds"],
        )
        self.assertIn("export type NarrationMode", ts)
        self.assertIn("narration_mode: NarrationMode", ts)

    def test_script_contract_exposes_authored_source_audio_cues(self) -> None:
        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "synthpost.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        section = schema["$defs"]["ScriptSection"]
        cue = schema["$defs"]["SourceClipCue"]
        ts = (ROOT / "contracts" / "typescript" / "index.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("source_clip", section["required"])
        self.assertIn("fallback_narration", cue["required"])
        self.assertIn("export type SourceClipCue", ts)
        self.assertIn("source_clip: SourceClipCue | null", ts)

    def test_visual_contract_exposes_review_recency_for_pin_selection(self) -> None:
        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "synthpost.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        visual = schema["$defs"]["VisualCandidate"]
        ts = (ROOT / "contracts" / "typescript" / "index.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("reviewed_at", visual["properties"])
        self.assertIn("reviewed_at: string | null", ts)

    def test_job_event_stream_uses_unambiguous_static_route(self) -> None:
        jobs_api = (
            ROOT / "pipeline" / "api" / "routes" / "jobs.py"
        ).read_text(encoding="utf-8")
        studio = (ROOT / "web" / "src" / "state" / "useJobEvents.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn('@router.get("/job-events")', jobs_api)
        self.assertIn("new EventSource(", studio)
        self.assertIn("/api/job-events?channel_id=", studio)
        self.assertNotIn('new EventSource("/api/jobs/events")', studio)

    def test_job_event_stream_is_async_and_releases_request_threads(self) -> None:
        from pipeline.api.routes.jobs import _job_event_stream

        class EmptyRepository:
            closed = False

            def list_jobs(self, limit: int, channel_id=None):
                self.limit = limit
                self.channel_id = channel_id
                return []

            def close(self) -> None:
                self.closed = True

        repository = EmptyRepository()

        async def first_event() -> str:
            stream = _job_event_stream()
            try:
                return await asyncio.wait_for(anext(stream), timeout=0.5)
            finally:
                await stream.aclose()

        self.assertTrue(inspect.isasyncgenfunction(_job_event_stream))
        with patch(
            "pipeline.api.routes.jobs.get_repository", return_value=repository
        ):
            event = asyncio.run(first_event())

        self.assertEqual(event, "event: jobs\ndata: []\n\n")
        self.assertTrue(repository.closed)

    def test_render_job_contract_exposes_queue_lane_and_retry_state(self) -> None:
        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "synthpost.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        job = schema["$defs"]["RenderJob"]
        ts = (ROOT / "contracts" / "typescript" / "index.ts").read_text(
            encoding="utf-8"
        )

        for field in (
            "autonomy_run_id",
            "queue_lane",
            "attempts",
            "max_attempts",
            "available_at",
            "last_attempt_at",
            "last_error",
            "failure_kind",
        ):
            self.assertIn(field, job["required"])
        self.assertEqual(
            job["properties"]["queue_lane"]["enum"],
            ["editorial", "media", "render"],
        )
        self.assertIn("cancel_requested", job["properties"]["status"]["enum"])
        self.assertIn("queue_lane: 'editorial' | 'media' | 'render'", ts)
        self.assertIn("autonomy_run_id: string | null", ts)
        self.assertIn("available_at: string | null", ts)
        self.assertIn("'cancel_requested'", ts)

    def test_autonomy_contracts_mirror_persisted_models_and_guardrails(self) -> None:
        from pipeline.models import AutonomyPolicy, AutonomyRun

        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "synthpost.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        policy = schema["$defs"]["AutonomyPolicy"]
        run = schema["$defs"]["AutonomyRun"]

        self.assertEqual(set(policy["properties"]), set(AutonomyPolicy.model_fields))
        self.assertEqual(set(policy["required"]), set(AutonomyPolicy.model_fields))
        self.assertFalse(policy["additionalProperties"])
        self.assertEqual(policy["properties"]["upload_enabled"]["const"], False)
        self.assertEqual(policy["properties"]["rights_policy"]["enum"], ["green_only"])
        self.assertEqual(
            policy["properties"]["render_profile"]["enum"],
            ["production", "final_master"],
        )

        self.assertEqual(set(run["properties"]), set(AutonomyRun.model_fields))
        self.assertEqual(set(run["required"]), set(AutonomyRun.model_fields))
        self.assertFalse(run["additionalProperties"])
        self.assertEqual(run["properties"]["policy"]["$ref"], "#/$defs/AutonomyPolicy")
        self.assertEqual(
            run["properties"]["status"]["enum"],
            [
                "queued",
                "running",
                "needs_attention",
                "ready_for_review",
                "accepted",
                "rejected",
                "cancelled",
            ],
        )

    def test_autonomy_http_view_is_separate_and_strict(self) -> None:
        from pipeline.api.schemas import AutonomyQAView, AutonomyRunView
        from pipeline.models import AutonomyRun

        schema = json.loads(
            (ROOT / "contracts" / "schemas" / "synthpost.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        persisted = schema["$defs"]["AutonomyRun"]
        view = schema["$defs"]["AutonomyRunView"]
        qa_view = schema["$defs"]["AutonomyQaView"]
        display_fields = {"project_title", "episode_title", "story_title"}

        self.assertTrue(display_fields.isdisjoint(persisted["properties"]))
        self.assertEqual(set(persisted["properties"]), set(AutonomyRun.model_fields))
        self.assertEqual(set(view["properties"]), set(AutonomyRunView.model_fields))
        self.assertEqual(set(view["required"]), set(AutonomyRunView.model_fields))
        self.assertFalse(view["additionalProperties"])
        self.assertTrue(display_fields.issubset(view["properties"]))
        self.assertEqual(set(qa_view["properties"]), set(AutonomyQAView.model_fields))
        self.assertEqual(set(qa_view["required"]), set(AutonomyQAView.model_fields))
        self.assertFalse(qa_view["additionalProperties"])
        self.assertEqual(
            view["properties"]["qa"]["anyOf"][0]["$ref"],
            "#/$defs/AutonomyQaView",
        )

    def test_autonomy_routes_declare_response_models(self) -> None:
        from fastapi import FastAPI

        from pipeline.api.routes.autonomy import router

        app = FastAPI()
        app.include_router(router)
        operation_schemas = {
            (path, method): operation["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            for path, methods in app.openapi()["paths"].items()
            for method, operation in methods.items()
        }

        run_ref = {"$ref": "#/components/schemas/AutonomyRunView"}
        for path, method in (
            ("/api/autonomy/runs", "post"),
            ("/api/autonomy/runs/{run_id}", "get"),
            ("/api/autonomy/runs/{run_id}/cancel", "post"),
            ("/api/autonomy/runs/{run_id}/retry", "post"),
            ("/api/autonomy/runs/{run_id}/accept", "post"),
            ("/api/autonomy/runs/{run_id}/reject", "post"),
        ):
            self.assertEqual(operation_schemas[(path, method)], run_ref)
        self.assertEqual(
            operation_schemas[("/api/autonomy/runs", "get")],
            {"items": run_ref, "type": "array", "title": "Response List Runs Api Autonomy Runs Get"},
        )
        self.assertEqual(
            operation_schemas[("/api/autonomy/runs/{run_id}/reveal-output", "post")],
            {"$ref": "#/components/schemas/AutonomyOutputRevealView"},
        )


if __name__ == "__main__":
    unittest.main()
