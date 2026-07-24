from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pipeline import config
from pipeline.db.repository import Repository
from pipeline.discovery.assignment_desk import apply_assignment_desk
from pipeline.models import (
    SourceDefinition,
    SourceType,
    StoryCandidate,
    StorySelectionStatus,
)


def iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace(
        "+00:00", "Z"
    )


class StoryInboxFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repository = Repository(Path(self.temp.name) / "inbox.sqlite3")

    def tearDown(self) -> None:
        self.repository.close()
        self.temp.cleanup()

    def candidate(
        self,
        candidate_id: str,
        *,
        hours_old: float,
        source_id: str = "src_wire",
        status: StorySelectionStatus = StorySelectionStatus.suggested,
    ) -> StoryCandidate:
        return StoryCandidate(
            candidate_id=candidate_id,
            title=f"Story {candidate_id}",
            source_id=source_id,
            source_name="Test Wire",
            published_at=iso_hours_ago(hours_old),
            discovered_at=iso_hours_ago(hours_old),
            selection_status=status,
        )

    def test_active_inbox_hides_stale_news_but_preserves_editor_work(self) -> None:
        fresh = self.candidate("cand_fresh", hours_old=1)
        stale_suggested = self.candidate("cand_stale_suggested", hours_old=25)
        stale_rejected = self.candidate(
            "cand_stale_rejected",
            hours_old=25,
            status=StorySelectionStatus.rejected,
        )
        stale_selected = self.candidate(
            "cand_stale_selected",
            hours_old=25,
            status=StorySelectionStatus.selected,
        )
        stale_manual = self.candidate(
            "cand_stale_manual",
            hours_old=25,
            source_id="src_manual_story",
        )
        for candidate in (
            fresh,
            stale_suggested,
            stale_rejected,
            stale_selected,
            stale_manual,
        ):
            self.repository.upsert_candidate(candidate)

        with patch.dict(
            os.environ, {"SYNTHPOST_DISCOVERY_MAX_AGE_HOURS": "24"}, clear=False
        ):
            active_ids = {
                candidate.candidate_id
                for candidate in self.repository.list_candidates(limit=20)
            }
            archive_ids = {
                candidate.candidate_id
                for candidate in self.repository.list_candidates(
                    limit=20, include_expired=True
                )
            }

        self.assertEqual(
            active_ids,
            {"cand_fresh", "cand_stale_selected", "cand_stale_manual"},
        )
        self.assertEqual(
            archive_ids,
            {
                "cand_fresh",
                "cand_stale_suggested",
                "cand_stale_rejected",
                "cand_stale_selected",
                "cand_stale_manual",
            },
        )

    def test_assignment_desk_marks_old_discovered_news_expired(self) -> None:
        source = SourceDefinition(
            source_id="src_wire",
            name="Test Wire",
            source_type=SourceType.rss,
            feed_url="https://example.com/feed.xml",
            category="technology",
        )
        self.repository.upsert_source(source)
        stale = self.candidate("cand_stale", hours_old=25)

        with patch.dict(
            os.environ, {"SYNTHPOST_DISCOVERY_MAX_AGE_HOURS": "24"}, clear=False
        ):
            apply_assignment_desk(self.repository, [stale], use_ai=False)

        persisted = self.repository.get_candidate(stale.candidate_id)
        self.assertEqual(persisted.assignment_lane, "expired")
        self.assertEqual(persisted.selection_status, StorySelectionStatus.expired)

    def test_candidate_age_window_is_validated(self) -> None:
        self.assertEqual(config.load_settings({}).discovery.max_candidate_age_hours, 24)
        with self.assertRaises(config.ConfigurationError):
            config.load_settings({"SYNTHPOST_DISCOVERY_MAX_AGE_HOURS": "0"})

