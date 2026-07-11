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
            "SourceDocument",
            "ResearchPack",
            "ScriptDocument",
            "VisualCandidate",
            "TimelinePlan",
            "RenderJob",
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
            "SourceDocument",
            "ResearchPack",
            "ScriptDocument",
            "VisualCandidate",
            "TimelinePlan",
            "RenderJob",
            "ArtifactRecord",
        ]:
            self.assertIn(f"export type {name}", ts)

    def test_job_event_stream_uses_unambiguous_static_route(self) -> None:
        api = (ROOT / "pipeline" / "api" / "main.py").read_text(encoding="utf-8")
        studio = (ROOT / "web" / "src" / "state" / "useStudio.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('@app.get("/api/job-events")', api)
        self.assertIn('new EventSource("/api/job-events")', studio)
        self.assertNotIn('new EventSource("/api/jobs/events")', studio)


if __name__ == "__main__":
    unittest.main()
