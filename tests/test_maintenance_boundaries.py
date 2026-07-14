from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from fastapi.testclient import TestClient

from pipeline import config
from pipeline.api.main import app
from pipeline.api.routes.jobs import public_job
from pipeline.api.schemas import ProjectPatch, SourcePatch
from pipeline.diagnostics import exit_code, run_diagnostics
from pipeline.jobs.supervisor import configured_worker_specs, worker_command
from pipeline.jobs.worker import HANDLERS, worker_process_lock
from pipeline.models import RenderJob
from pipeline.observability import LogContext, format_event, safe_text
from pipeline.stages import STAGE_CONTRACTS, StageOutcome, PipelineRunSummary
from pipeline.visuals.providers import configured_visual_sources
from tools.parallel_smoke import run_parallel_smoke


class ConfigurationBoundaryTests(unittest.TestCase):
    def test_defaults_preserve_existing_database_and_renderer_paths(self) -> None:
        settings = config.load_settings({})
        self.assertEqual(
            settings.storage.database_path.as_posix(),
            ".synthpost/synthpost.sqlite3",
        )
        self.assertEqual(settings.avatar.engine_path.as_posix(), "avatar-engine")
        self.assertEqual(
            settings.render.remotion_path.as_posix(),
            "compositor/remotion_renderer",
        )

    def test_legacy_avatar_directory_alias_is_supported(self) -> None:
        settings = config.load_settings(
            {"SYNTHPOST_AVATAR_ENGINE_DIR": "legacy-avatar"}
        )
        self.assertEqual(settings.avatar.engine_path.as_posix(), "legacy-avatar")

    def test_primary_avatar_path_wins_over_legacy_alias(self) -> None:
        settings = config.load_settings(
            {
                "SYNTHPOST_AVATAR_ENGINE_PATH": "current-avatar",
                "SYNTHPOST_AVATAR_ENGINE_DIR": "legacy-avatar",
            }
        )
        self.assertEqual(settings.avatar.engine_path.as_posix(), "current-avatar")

    def test_invalid_boolean_has_actionable_variable_name(self) -> None:
        with self.assertRaisesRegex(
            config.ConfigurationError, "SYNTHPOST_SEARXNG_DOWNLOAD_VIDEOS"
        ):
            config.load_settings(
                {"SYNTHPOST_SEARXNG_DOWNLOAD_VIDEOS": "sometimes"}
            )

    def test_retry_window_is_validated(self) -> None:
        with self.assertRaisesRegex(
            config.ConfigurationError, "retry_max_seconds"
        ):
            config.load_settings(
                {
                    "SYNTHPOST_JOB_RETRY_BASE_SECONDS": "20",
                    "SYNTHPOST_JOB_RETRY_MAX_SECONDS": "10",
                }
            )

    def test_provider_credentials_are_feature_scoped(self) -> None:
        settings = config.load_settings({"SYNTHPOST_LLM_PROVIDER": "groq"})
        self.assertIn("GROQ_API_KEY", settings.llm.provider_problem() or "")

    def test_parallel_worker_defaults_and_overrides_are_typed(self) -> None:
        defaults = config.load_settings({})
        self.assertEqual(defaults.jobs.editorial_workers, 2)
        self.assertEqual(defaults.jobs.media_workers, 2)
        self.assertEqual(defaults.jobs.render_workers, 2)
        self.assertEqual(defaults.render.remotion_concurrency, 4)

        configured = config.load_settings(
            {
                "SYNTHPOST_EDITORIAL_WORKERS": "5",
                "SYNTHPOST_MEDIA_WORKERS": "4",
                "SYNTHPOST_RENDER_WORKERS": "3",
                "SYNTHPOST_REMOTION_CONCURRENCY": "6",
            }
        )
        self.assertEqual(configured.jobs.workers_for("editorial"), 5)
        self.assertEqual(configured.jobs.workers_for("media"), 4)
        self.assertEqual(configured.jobs.workers_for("render"), 3)
        self.assertEqual(configured.render.remotion_concurrency, 6)

    def test_worker_capacity_rejects_zero(self) -> None:
        with self.assertRaisesRegex(
            config.ConfigurationError, "editorial_workers"
        ):
            config.load_settings({"SYNTHPOST_EDITORIAL_WORKERS": "0"})


class StageContractTests(unittest.TestCase):
    def test_every_worker_handler_has_exactly_one_contract(self) -> None:
        self.assertEqual(set(HANDLERS), set(STAGE_CONTRACTS))

    def test_story_stage_accepts_legacy_job_without_denormalized_episode(self) -> None:
        job = RenderJob(job_type="research", story_id="story_123")
        STAGE_CONTRACTS["research"].validate_job(job)

    def test_stage_output_contract_reports_missing_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "research_pack_id"):
            STAGE_CONTRACTS["research"].validate_outputs({})

    def test_run_summary_includes_zero_count_outcomes(self) -> None:
        summary = PipelineRunSummary()
        summary.add("research", StageOutcome.completed, summary.started_at_monotonic)
        payload = summary.as_dict()
        self.assertEqual(payload["counts"]["completed"], 1)
        self.assertEqual(payload["counts"]["cached"], 0)


class ObservabilityTests(unittest.TestCase):
    def test_json_logs_include_context_and_redact_secret_fields(self) -> None:
        line = format_event(
            "provider_call",
            "calling provider",
            context=LogContext(
                episode_id="ep_1", story_id="story_1", stage="script"
            ),
            fields={"api_key": "should-not-leak", "elapsed_seconds": 1.2},
            log_format="json",
        )
        payload = json.loads(line)
        self.assertEqual(payload["episode_id"], "ep_1")
        self.assertEqual(payload["api_key"], "[REDACTED]")
        self.assertNotIn("should-not-leak", line)

    def test_error_summaries_hide_project_paths_and_inline_tokens(self) -> None:
        summary = safe_text(
            f"failed at {os.getcwd()}/story.json token=private-value"
        )
        self.assertIn("<project_root>/story.json", summary)
        self.assertIn("token=[REDACTED]", summary)
        self.assertNotIn("private-value", summary)

    def test_human_logs_use_the_sanitized_message(self) -> None:
        line = format_event(
            "provider_failure",
            f"failed at {os.getcwd()}/story.json api_key=private-value",
            log_format="human",
        )
        self.assertIn("<project_root>/story.json", line)
        self.assertIn("api_key=[REDACTED]", line)
        self.assertNotIn("private-value", line)


class APIContractTests(unittest.TestCase):
    def test_patch_contract_rejects_identity_and_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectPatch.model_validate({"project_id": "replacement"})

    def test_source_patch_validates_score_range(self) -> None:
        with self.assertRaises(ValidationError):
            SourcePatch.model_validate({"reliability_score": 1.2})

    def test_job_router_is_registered_once(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/api/jobs", paths)
        self.assertIn("/api/job-events", paths)

    def test_public_job_view_excludes_local_traceback(self) -> None:
        job = RenderJob(job_type="research", story_id="story_123")
        job.traceback = "/Users/example/private/path.py"
        self.assertNotIn("traceback", public_job(job))

    def test_health_and_patch_validation_through_http_boundary(self) -> None:
        client = TestClient(app)
        health = client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(
            set(health.json()["worker_capacity"]),
            {"editorial", "media", "render"},
        )
        response = client.patch(
            "/api/projects/not-used",
            json={"project_id": "identity-fields-cannot-be-patched"},
        )
        self.assertEqual(response.status_code, 422)


class ExtensionAndDiagnosticsTests(unittest.TestCase):
    def test_visual_sources_have_stable_registration_order(self) -> None:
        self.assertEqual(
            [source.name for source in configured_visual_sources()],
            ["episode_media_inbox", "searxng"],
        )

    def test_config_only_doctor_does_not_expose_api_key(self) -> None:
        with patch.dict(
            os.environ,
            {"SYNTHPOST_LLM_PROVIDER": "groq", "GROQ_API_KEY": "private-key"},
            clear=True,
        ):
            checks = run_diagnostics(config_only=True)
        rendered = json.dumps([check.as_dict() for check in checks])
        self.assertNotIn("private-key", rendered)
        self.assertEqual(exit_code(checks), 0)
        self.assertIn("worker_pool", {check.name for check in checks})


class ParallelWorkerTests(unittest.TestCase):
    def test_parallel_smoke_rejects_unsafe_episode_counts_before_spawning(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            run_parallel_smoke(1, "preview")
        with self.assertRaisesRegex(ValueError, "capped at eight"):
            run_parallel_smoke(9, "preview")

    def test_supervisor_expands_each_configured_lane_into_process_slots(self) -> None:
        settings = config.load_settings(
            {
                "SYNTHPOST_EDITORIAL_WORKERS": "3",
                "SYNTHPOST_MEDIA_WORKERS": "2",
                "SYNTHPOST_RENDER_WORKERS": "2",
            }
        )
        specs = configured_worker_specs(settings)
        self.assertEqual(
            [(spec.lane, spec.slot) for spec in specs],
            [
                ("editorial", 1),
                ("editorial", 2),
                ("editorial", 3),
                ("media", 1),
                ("media", 2),
                ("render", 1),
                ("render", 2),
            ],
        )
        self.assertEqual(
            worker_command(specs[-1])[-4:], ["--lane", "render", "--slot", "2"]
        )

    def test_workers_lease_distinct_slots_up_to_configured_capacity(self) -> None:
        settings = config.load_settings({"SYNTHPOST_RENDER_WORKERS": "2"})
        with tempfile.TemporaryDirectory() as directory, patch(
            "pipeline.jobs.worker.database_path",
            return_value=Path(directory) / "queue.sqlite3",
        ), patch("pipeline.jobs.worker.config.get_settings", return_value=settings):
            with worker_process_lock("render", slot=1) as first:
                with worker_process_lock("render", slot=2) as second:
                    self.assertEqual((first.slot, second.slot), (1, 2))
                    with self.assertRaisesRegex(RuntimeError, "No free render"):
                        with worker_process_lock("render"):
                            self.fail("capacity must not be oversubscribed")


if __name__ == "__main__":
    unittest.main()
