from __future__ import annotations

import json
import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pipeline import config
from pipeline.agents.hermes import (
    HermesClient,
    HermesRunError,
    HermesUnavailableError,
)
from pipeline.agents.editorial import (
    build_research_pack_with_hermes,
    discover_with_hermes,
)
from pipeline.db.repository import Repository
from pipeline.discovery.discover import add_manual_story
from pipeline.models import StoryWorkflowState
from unittest.mock import patch


class _HermesHandler(BaseHTTPRequestHandler):
    statuses: list[dict] = []
    requests: list[dict] = []

    def log_message(self, format: str, *args) -> None:
        return

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _send(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        body = self._body()
        type(self).requests.append(
            {
                "method": "POST",
                "path": self.path,
                "body": body,
                "authorization": self.headers.get("Authorization"),
                "idempotency_key": self.headers.get("Idempotency-Key"),
            }
        )
        if self.path == "/v1/runs":
            self._send({"run_id": "run_test", "status": "started"}, 202)
            return
        if self.path == "/v1/runs/run_test/stop":
            self._send({"status": "stopping"})
            return
        self._send({"detail": "not found"}, 404)

    def do_GET(self) -> None:
        type(self).requests.append(
            {
                "method": "GET",
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
            }
        )
        if self.path == "/v1/runs/run_test":
            payload = (
                type(self).statuses.pop(0)
                if type(self).statuses
                else {"run_id": "run_test", "status": "running"}
            )
            self._send(payload)
            return
        if self.path == "/health":
            self._send({"status": "ok"})
            return
        if self.path == "/v1/toolsets":
            self._send(
                {
                    "object": "list",
                    "platform": "api_server",
                    "data": [
                        {"name": "web", "enabled": True},
                        {"name": "browser", "enabled": True},
                        {"name": "terminal", "enabled": False},
                    ],
                }
            )
            return
        self._send({"detail": "not found"}, 404)


class HermesClientTests(unittest.TestCase):
    def setUp(self) -> None:
        _HermesHandler.requests = []
        _HermesHandler.statuses = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _HermesHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = HermesClient(
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            api_key="test-secret",
            request_timeout_seconds=2,
            run_timeout_seconds=2,
            poll_interval_seconds=0.001,
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_run_json_submits_isolated_run_and_parses_result(self) -> None:
        _HermesHandler.statuses = [
            {"run_id": "run_test", "status": "running"},
            {
                "run_id": "run_test",
                "status": "completed",
                "model": "hermes-test",
                "output": '```json\n{"stories": [{"title": "Test"}]}\n```',
            },
        ]
        observed: list[str] = []

        value, state = self.client.run_json(
            "Find stories",
            {"type": "object", "properties": {"stories": {"type": "array"}}},
            idempotency_key="job_123",
            progress_callback=lambda status, _: observed.append(status),
        )

        self.assertEqual(value["stories"][0]["title"], "Test")
        self.assertEqual(state["model"], "hermes-test")
        self.assertEqual(observed, ["running", "completed"])
        submission = next(
            request
            for request in _HermesHandler.requests
            if request["path"] == "/v1/runs"
        )
        self.assertEqual(submission["authorization"], "Bearer test-secret")
        self.assertEqual(submission["idempotency_key"], "job_123")
        self.assertIn("OUTPUT JSON SCHEMA", submission["body"]["input"])
        self.assertTrue(submission["body"]["session_id"].startswith("synthpost-"))

    def test_failed_run_raises_actionable_error(self) -> None:
        _HermesHandler.statuses = [
            {
                "run_id": "run_test",
                "status": "failed",
                "error": "research provider unavailable",
            }
        ]

        with self.assertRaisesRegex(HermesRunError, "research provider unavailable"):
            self.client.run_text("test", instructions="test")

    def test_unsafe_api_toolset_is_rejected_before_submission(self) -> None:
        with patch.object(
            self.client,
            "toolsets",
            return_value={
                "data": [
                    {"name": "web", "enabled": True},
                    {"name": "terminal", "enabled": True},
                ]
            },
        ):
            with self.assertRaisesRegex(HermesUnavailableError, "terminal"):
                self.client.run_text("test", instructions="test")
        self.assertFalse(
            any(request["path"] == "/v1/runs" for request in _HermesHandler.requests)
        )


class HermesConfigurationTests(unittest.TestCase):
    def test_stage_routing_is_typed_and_disabled_by_default(self) -> None:
        defaults = config.load_settings({})
        self.assertFalse(defaults.hermes.enabled)
        self.assertEqual(defaults.hermes.discovery_provider, "native")

        settings = config.load_settings(
            {
                "SYNTHPOST_HERMES_ENABLED": "true",
                "SYNTHPOST_HERMES_API_KEY": "private",
                "SYNTHPOST_DISCOVERY_PROVIDER": "hermes",
                "SYNTHPOST_RESEARCH_PROVIDER": "hermes",
                "SYNTHPOST_SCRIPT_PROVIDER": "hermes",
                "SYNTHPOST_VISUAL_PLANNER_PROVIDER": "hermes",
            }
        )
        self.assertIsNone(settings.hermes.configuration_problem())
        self.assertTrue(settings.hermes.selected_for_any_stage)

    def test_hermes_stage_requires_enabled_runtime_and_key(self) -> None:
        disabled = config.load_settings(
            {"SYNTHPOST_RESEARCH_PROVIDER": "hermes"}
        )
        self.assertIn("HERMES_ENABLED", disabled.hermes.configuration_problem() or "")

        missing_key = config.load_settings({"SYNTHPOST_HERMES_ENABLED": "true"})
        self.assertIn("HERMES_API_KEY", missing_key.hermes.configuration_problem() or "")


class HermesEditorialServiceTests(unittest.TestCase):
    def test_discovery_normalizes_urls_and_keeps_synthpost_ranking(self) -> None:
        result = {
            "stories": [
                {
                    "title": "A consequential infrastructure development",
                    "url": "https://example.com/story?utm_source=test",
                    "publisher": "Example",
                    "published_at": "2026-07-18T08:00:00Z",
                    "category": "technology",
                    "summary": "A major infrastructure investment changes supply capacity in India.",
                    "why_it_matters": "It affects industrial capacity and costs.",
                    "supporting_sources": ["Example", "Official filing"],
                    "confidence": 0.88,
                    "thumbnail_url": None,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(f"{temp}/synthpost.sqlite3")
            try:
                with patch("pipeline.agents.editorial.HermesClient") as client_type:
                    client_type.return_value.run_json.return_value = (
                        result,
                        {"status": "completed"},
                    )
                    candidates = discover_with_hermes(repository)
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0].canonical_url, "https://example.com/story")
                self.assertEqual(candidates[0].source_id, "src_hermes_discovery")
                self.assertGreater(candidates[0].assignment_confidence, 0)
            finally:
                repository.close()

    def test_research_rejects_unlinked_claims_and_persists_supported_pack(self) -> None:
        raw = {
            "research_queries": ["official infrastructure filing"],
            "documents": [
                {
                    "source_key": "source_1",
                    "url": "https://example.com/filing",
                    "title": "Official filing",
                    "publisher": "Example Authority",
                    "author": None,
                    "published_at": "2026-07-18T08:00:00Z",
                    "primary_source": True,
                    "content_text": "The authority approved a major infrastructure investment with a documented capacity expansion and delivery schedule.",
                }
            ],
            "evidence": [
                {
                    "evidence_key": "evidence_1",
                    "source_key": "source_1",
                    "excerpt": "The authority approved the investment and published a delivery schedule.",
                    "url": "https://example.com/filing",
                }
            ],
            "claims": [
                {
                    "claim_text": "The authority approved the investment.",
                    "evidence_keys": ["evidence_1"],
                    "confidence": 0.95,
                    "claim_type": "fact",
                    "notes": "Primary filing",
                },
                {
                    "claim_text": "This unsupported claim must be dropped.",
                    "evidence_keys": ["missing"],
                    "confidence": 0.9,
                    "claim_type": "fact",
                    "notes": "No evidence",
                },
            ],
            "people": [],
            "organizations": ["Example Authority"],
            "locations": ["India"],
            "numbers": [],
            "dates": ["2026"],
            "contradictions": [],
            "uncertainties": ["Delivery remains pending."],
            "systems": ["infrastructure"],
            "stakeholders": ["consumers"],
            "trade_offs": [],
            "execution_gaps": ["Delivery remains pending."],
            "editorial_questions": ["Will delivery stay on schedule?"],
            "research_summary": "The filing confirms approval while delivery remains pending.",
        }
        with tempfile.TemporaryDirectory() as temp:
            repository = Repository(f"{temp}/synthpost.sqlite3")
            try:
                project = repository.create_project("Hermes research")
                episode = repository.create_episode(project.project_id, "Episode")
                candidate = add_manual_story(
                    repository,
                    title="Infrastructure investment",
                    body="The authority announced a major infrastructure investment for India.",
                    episode_id=episode.episode_id,
                )
                selected = repository.select_candidate(
                    candidate.candidate_id, episode.episode_id
                )
                with patch("pipeline.agents.editorial.HermesClient") as client_type:
                    client_type.return_value.run_json.return_value = (
                        raw,
                        {"status": "completed"},
                    )
                    pack = build_research_pack_with_hermes(
                        repository, selected.story_id or ""
                    )
                self.assertEqual(len(pack.documents), 1)
                self.assertEqual(len(pack.evidence), 1)
                self.assertEqual(len(pack.claims), 1)
                self.assertTrue(pack.claims[0].supported)
                self.assertEqual(
                    repository.candidate_for_story(selected.story_id or "").workflow_state,
                    StoryWorkflowState.research_ready,
                )
            finally:
                repository.close()


if __name__ == "__main__":
    unittest.main()
