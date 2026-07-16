from __future__ import annotations

import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from pipeline.db.repository import Repository
from pipeline.discovery.discover import add_manual_story
from pipeline.narration.service import generate_narration, load_narration_artifact
from pipeline.research.extract import build_research_pack
from pipeline.scripts.generation import approve_script, save_manual_script
from pipeline.storage import PROJECT_ROOT, resolve_project_path
from pipeline.timeline.planner import approve_timeline, generate_timeline


class KokoroNarrationContractTests(unittest.TestCase):
    def test_sample_clock_is_versioned_cached_and_invalidated_by_script_edit(self) -> None:
        temp = tempfile.TemporaryDirectory()
        repository = Repository(Path(temp.name) / "narration.sqlite3")
        episode_id = ""
        project_id = ""
        try:
            project = repository.create_project("Narration test")
            project_id = project.project_id
            episode = repository.create_episode(project.project_id, "Episode")
            episode_id = episode.episode_id
            candidate = add_manual_story(
                repository,
                title="Exact local narration",
                body="A compact local test story.",
                episode_id=episode.episode_id,
            )
            selected = repository.select_candidate(
                candidate.candidate_id, episode.episode_id
            )
            assert selected.story_id is not None
            story_id = selected.story_id
            build_research_pack(repository, story_id)
            save_manual_script(
                repository,
                story_id,
                "Exact local narration",
                "The first production beat establishes the story. "
                "The next beat explains why the result matters.\n\n"
                "The final section tells the viewer what comes next.",
            )
            approve_script(repository, story_id)

            artifact = generate_narration(repository, story_id, test_mode=True)
            audio_path = resolve_project_path(artifact.audio_path)
            with wave.open(str(audio_path), "rb") as wav:
                self.assertEqual(wav.getframerate(), artifact.sample_rate)
                self.assertEqual(wav.getnframes(), artifact.beats[-1].end_sample)
            self.assertEqual(
                artifact.duration_seconds,
                artifact.beats[-1].end_sample / artifact.sample_rate,
            )
            self.assertEqual(
                [beat.beat_id for beat in artifact.beats],
                [
                    beat_id
                    for section in artifact.sections
                    for beat_id in section.beat_ids
                ],
            )
            cached = generate_narration(repository, story_id, test_mode=True)
            self.assertEqual(cached.created_at, artifact.created_at)

            with patch(
                "pipeline.timeline.planner.load_narration_artifact",
                return_value=artifact,
            ):
                plan = generate_timeline(repository, story_id)
                plan.segments[0].duration += 1.0
                plan.segments[0].end_time += 1.0
                repository.save_timeline(plan)
                with self.assertRaisesRegex(ValueError, "match Kokoro audio"):
                    approve_timeline(repository, story_id)

            save_manual_script(
                repository,
                story_id,
                "Exact local narration revised",
                "This revised narration must receive a new audio clock.",
            )
            approve_script(repository, story_id)
            self.assertIsNone(
                load_narration_artifact(
                    repository, story_id, require_current=False
                )
            )
            revised = generate_narration(repository, story_id, test_mode=True)
            self.assertGreater(revised.script_version, artifact.script_version)
            self.assertNotEqual(revised.input_hash, artifact.input_hash)
        finally:
            repository.close()
            temp.cleanup()
            shutil.rmtree(PROJECT_ROOT / "episodes" / episode_id, ignore_errors=True)
            shutil.rmtree(PROJECT_ROOT / "projects" / project_id, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
