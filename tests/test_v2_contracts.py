from __future__ import annotations

import json
import unittest
from pathlib import Path

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
        self.assertIn('new EventSource("/api/job-events")', studio)
        self.assertNotIn('new EventSource("/api/jobs/events")', studio)

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
        self.assertIn("queue_lane: 'editorial' | 'media' | 'render'", ts)
        self.assertIn("available_at: string | null", ts)


if __name__ == "__main__":
    unittest.main()
