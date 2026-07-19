from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from pipeline.db.sqlite import connect, dumps, init_db, loads, row_data, rows_data
from pipeline.models import (
    Episode,
    EpisodeStatus,
    GenerationAudit,
    JobQueueLane,
    JobStatus,
    Project,
    RenderJob,
    ScriptDocument,
    ScriptStatus,
    SourceDefinition,
    StoryCandidate,
    StorySelectionStatus,
    StoryWorkflowState,
    TimelinePlan,
    TimelineStatus,
    VisualCandidate,
    new_id,
    now_iso,
    queue_lane_for_job_type,
)
from pipeline.jobs.policy import default_max_attempts
from pipeline.workflow import assert_transition


class NotFoundError(KeyError):
    pass


class Repository:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path
        self.connection = init_db(db_path)

    def close(self) -> None:
        self.connection.close()

    def _one(self, query: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.connection.execute(query, tuple(params)).fetchone()

    def _many(self, query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(query, tuple(params)).fetchall())

    def _require_data(
        self, table: str, key_name: str, key_value: str
    ) -> dict[str, Any]:
        row = self._one(f"SELECT data FROM {table} WHERE {key_name} = ?", (key_value,))
        data = row_data(row)
        if data is None:
            raise NotFoundError(f"{table}.{key_name} not found: {key_value}")
        return data

    # Projects / episodes -------------------------------------------------
    def create_project(
        self,
        title: str,
        *,
        default_category: str = "general",
        default_render_profile: str = "preview",
    ) -> Project:
        project = Project(
            title=title,
            default_category=default_category,
            default_render_profile=default_render_profile,
        )
        self.upsert_project(project)
        return project

    def upsert_project(self, project: Project) -> None:
        data = project.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO projects(project_id, title, status, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                  title=excluded.title,
                  status=excluded.status,
                  data=excluded.data,
                  updated_at=excluded.updated_at
                """,
                (
                    project.project_id,
                    project.title,
                    project.status.value,
                    dumps(data),
                    project.created_at,
                    project.updated_at,
                ),
            )

    def list_projects(self) -> list[Project]:
        return [
            Project.model_validate(data)
            for data in rows_data(
                self._many("SELECT data FROM projects ORDER BY updated_at DESC")
            )
        ]

    def get_project(self, project_id: str) -> Project:
        return Project.model_validate(
            self._require_data("projects", "project_id", project_id)
        )

    def update_project(self, project_id: str, patch: dict[str, Any]) -> Project:
        data = self.get_project(project_id).model_dump(mode="json")
        data.update({key: value for key, value in patch.items() if value is not None})
        data["updated_at"] = now_iso()
        project = Project.model_validate(data)
        self.upsert_project(project)
        return project

    def create_episode(
        self, project_id: str, title: str, *, render_profile: str | None = None
    ) -> Episode:
        project = self.get_project(project_id)
        episode = Episode(
            project_id=project_id,
            title=title,
            render_profile=render_profile or project.default_render_profile,
        )
        self.upsert_episode(episode)
        return episode

    def upsert_episode(self, episode: Episode) -> None:
        data = episode.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO episodes(episode_id, project_id, title, status, render_profile, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(episode_id) DO UPDATE SET
                  title=excluded.title,
                  status=excluded.status,
                  render_profile=excluded.render_profile,
                  data=excluded.data,
                  updated_at=excluded.updated_at
                """,
                (
                    episode.episode_id,
                    episode.project_id,
                    episode.title,
                    episode.status.value,
                    episode.render_profile,
                    dumps(data),
                    episode.created_at,
                    episode.updated_at,
                ),
            )

    def list_episodes(self, project_id: str | None = None) -> list[Episode]:
        if project_id:
            rows = self._many(
                "SELECT data FROM episodes WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            )
        else:
            rows = self._many("SELECT data FROM episodes ORDER BY updated_at DESC")
        return [Episode.model_validate(data) for data in rows_data(rows)]

    def get_episode(self, episode_id: str) -> Episode:
        return Episode.model_validate(
            self._require_data("episodes", "episode_id", episode_id)
        )

    def update_episode(self, episode_id: str, patch: dict[str, Any]) -> Episode:
        data = self.get_episode(episode_id).model_dump(mode="json")
        data.update({key: value for key, value in patch.items() if value is not None})
        data["updated_at"] = now_iso()
        episode = Episode.model_validate(data)
        self.upsert_episode(episode)
        return episode

    def add_story_to_episode(self, episode_id: str, story_id: str) -> Episode:
        episode = self.get_episode(episode_id)
        if story_id not in episode.story_ids:
            episode.story_ids.append(story_id)
            episode.updated_at = now_iso()
            episode.status = EpisodeStatus.in_progress
            self.upsert_episode(episode)
        return episode

    def episode_for_story(self, story_id: str) -> Episode:
        rows = self._many("SELECT data FROM episodes ORDER BY updated_at DESC")
        for data in rows_data(rows):
            episode = Episode.model_validate(data)
            if story_id in episode.story_ids:
                return episode
        raise NotFoundError(f"episode for story not found: {story_id}")

    # Sources -------------------------------------------------------------
    def upsert_source(self, source: SourceDefinition) -> None:
        data = source.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO sources(source_id, name, source_type, category, enabled, priority, reliability_score, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                  name=excluded.name,
                  source_type=excluded.source_type,
                  category=excluded.category,
                  enabled=excluded.enabled,
                  priority=excluded.priority,
                  reliability_score=excluded.reliability_score,
                  data=excluded.data,
                  updated_at=excluded.updated_at
                """,
                (
                    source.source_id,
                    source.name,
                    source.source_type.value,
                    source.category,
                    int(source.enabled),
                    source.priority,
                    source.reliability_score,
                    dumps(data),
                    now_iso(),
                ),
            )

    def list_sources(
        self, *, enabled: bool | None = None, category: str | None = None
    ) -> list[SourceDefinition]:
        clauses: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            clauses.append("enabled = ?")
            params.append(int(enabled))
        if category:
            clauses.append("category = ?")
            params.append(category)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._many(
            f"SELECT data FROM sources{where} ORDER BY priority DESC, name ASC", params
        )
        return [SourceDefinition.model_validate(data) for data in rows_data(rows)]

    def get_source(self, source_id: str) -> SourceDefinition:
        return SourceDefinition.model_validate(
            self._require_data("sources", "source_id", source_id)
        )

    def update_source(self, source_id: str, patch: dict[str, Any]) -> SourceDefinition:
        data = self.get_source(source_id).model_dump(mode="json")
        data.update({key: value for key, value in patch.items() if value is not None})
        source = SourceDefinition.model_validate(data)
        self.upsert_source(source)
        return source

    # Candidates / selected stories --------------------------------------
    def upsert_candidate(self, candidate: StoryCandidate) -> None:
        existing_row = self._one(
            "SELECT data FROM story_candidates WHERE candidate_id = ?",
            (candidate.candidate_id,),
        )
        existing_data = row_data(existing_row)
        if existing_data is not None:
            existing = StoryCandidate.model_validate(existing_data)
            # Only decisions made by an editor are sticky. Duplicate/expired
            # are assignment-desk classifications and must be free to change
            # when a newer article becomes the cluster leader or a story is
            # refreshed with better evidence.
            if existing.selection_status in {
                StorySelectionStatus.selected,
                StorySelectionStatus.rejected,
            } and candidate.selection_status not in {
                StorySelectionStatus.selected,
                StorySelectionStatus.rejected,
            }:
                candidate = candidate.model_copy(
                    update={
                        "episode_id": existing.episode_id,
                        "story_id": existing.story_id,
                        "selection_status": existing.selection_status,
                        "workflow_state": existing.workflow_state,
                        "rejection_reasons": existing.rejection_reasons,
                        "manual_body": existing.manual_body,
                        "discovered_at": existing.discovered_at,
                    }
                )
        data = candidate.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO story_candidates(candidate_id, episode_id, story_id, title, canonical_url, source_id,
                  source_name, category, published_at, final_score, selection_status, workflow_state,
                  duplicate_group_id, data, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  episode_id=excluded.episode_id,
                  story_id=excluded.story_id,
                  title=excluded.title,
                  canonical_url=excluded.canonical_url,
                  source_id=excluded.source_id,
                  source_name=excluded.source_name,
                  category=excluded.category,
                  published_at=excluded.published_at,
                  final_score=excluded.final_score,
                  selection_status=excluded.selection_status,
                  workflow_state=excluded.workflow_state,
                  duplicate_group_id=excluded.duplicate_group_id,
                  data=excluded.data
                """,
                (
                    candidate.candidate_id,
                    candidate.episode_id,
                    candidate.story_id,
                    candidate.title,
                    candidate.canonical_url,
                    candidate.source_id,
                    candidate.source_name,
                    candidate.category,
                    candidate.published_at,
                    candidate.final_score,
                    candidate.selection_status.value,
                    candidate.workflow_state.value,
                    candidate.duplicate_group_id,
                    dumps(data),
                    candidate.discovered_at,
                ),
            )

    def list_candidates(
        self,
        *,
        episode_id: str | None = None,
        status: StorySelectionStatus | str | None = None,
        category: str | None = None,
        search: str | None = None,
        limit: int = 100,
        include_duplicates: bool = False,
        include_expired: bool = False,
    ) -> list[StoryCandidate]:
        clauses: list[str] = []
        params: list[Any] = []
        if episode_id:
            # Episode workspaces are isolation boundaries. Global/unassigned
            # inbox candidates must not crowd out the selected episode's story
            # after enough discoveries have accumulated.
            clauses.append("episode_id = ?")
            params.append(episode_id)
        if status:
            clauses.append("selection_status = ?")
            params.append(
                str(
                    status.value if isinstance(status, StorySelectionStatus) else status
                )
            )
        else:
            if not include_duplicates:
                clauses.append("selection_status != 'duplicate'")
            if not include_expired:
                clauses.append("selection_status != 'expired'")
        if category:
            clauses.append("category = ?")
            params.append(category)
        if search:
            clauses.append("LOWER(title) LIKE ?")
            params.append(f"%{search.lower()}%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        rows = self._many(
            f"SELECT data FROM story_candidates{where} "
            "ORDER BY CASE WHEN selection_status = 'selected' THEN 0 ELSE 1 END, "
            "final_score DESC, discovered_at DESC LIMIT ?",
            params,
        )
        return [StoryCandidate.model_validate(data) for data in rows_data(rows)]

    def get_candidate(self, candidate_id: str) -> StoryCandidate:
        return StoryCandidate.model_validate(
            self._require_data("story_candidates", "candidate_id", candidate_id)
        )

    def candidate_for_story(self, story_id: str) -> StoryCandidate:
        row = self._one(
            "SELECT data FROM story_candidates WHERE story_id = ?", (story_id,)
        )
        data = row_data(row)
        if data is None:
            raise NotFoundError(f"candidate for story not found: {story_id}")
        return StoryCandidate.model_validate(data)

    def transition_story(
        self, story_id: str, target: StoryWorkflowState | str
    ) -> StoryCandidate:
        candidate = self.candidate_for_story(story_id)
        target_state = StoryWorkflowState(target)
        assert_transition(candidate.workflow_state, target_state)
        candidate.workflow_state = target_state
        self.upsert_candidate(candidate)
        return candidate

    def select_candidate(self, candidate_id: str, episode_id: str) -> StoryCandidate:
        candidate = self.get_candidate(candidate_id)
        story_id = (
            candidate.story_id or f"story_{candidate.candidate_id.replace('cand_', '')}"
        )
        current = candidate.workflow_state
        if current == StoryWorkflowState.discovered:
            assert_transition(current, StoryWorkflowState.selected)
        candidate.story_id = story_id
        candidate.episode_id = episode_id
        candidate.selection_status = StorySelectionStatus.selected
        candidate.workflow_state = StoryWorkflowState.selected
        self.upsert_candidate(candidate)
        self.add_story_to_episode(episode_id, story_id)
        return candidate

    def reject_candidate(
        self, candidate_id: str, reasons: list[str] | None = None
    ) -> StoryCandidate:
        candidate = self.get_candidate(candidate_id)
        candidate.selection_status = StorySelectionStatus.rejected
        candidate.rejection_reasons = reasons or []
        self.upsert_candidate(candidate)
        return candidate

    # Research / scripts / visuals / timelines ---------------------------
    def upsert_source_document(self, document: Any) -> None:
        data = (
            document.model_dump(mode="json")
            if hasattr(document, "model_dump")
            else document
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO source_documents(document_id, story_id, url, title, content_hash, extraction_status, data, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET data=excluded.data, extraction_status=excluded.extraction_status
                """,
                (
                    data["document_id"],
                    data["story_id"],
                    data.get("url"),
                    data["title"],
                    data["content_hash"],
                    data.get("extraction_status", "extracted"),
                    dumps(data),
                    data.get("retrieved_at", now_iso()),
                ),
            )

    def list_source_documents(self, story_id: str) -> list[dict[str, Any]]:
        return rows_data(
            self._many(
                "SELECT data FROM source_documents WHERE story_id = ? ORDER BY retrieved_at ASC",
                (story_id,),
            )
        )

    def upsert_research_pack(self, pack: Any) -> None:
        data = pack.model_dump(mode="json") if hasattr(pack, "model_dump") else pack
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO research_packs(research_pack_id, story_id, status, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(research_pack_id) DO UPDATE SET status=excluded.status, data=excluded.data, updated_at=excluded.updated_at
                """,
                (
                    data["research_pack_id"],
                    data["story_id"],
                    str(data.get("status", "review")),
                    dumps(data),
                    data.get("created_at", now_iso()),
                    data.get("updated_at", now_iso()),
                ),
            )

    def latest_research_pack(self, story_id: str) -> dict[str, Any] | None:
        return row_data(
            self._one(
                "SELECT data FROM research_packs WHERE story_id = ? ORDER BY created_at DESC LIMIT 1",
                (story_id,),
            )
        )

    def save_generation_audit(self, audit: GenerationAudit) -> GenerationAudit:
        data = audit.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO generation_audits(
                  audit_id, story_id, job_id, stage, prompt_version,
                  charter_version, provider, model, status, data, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(audit_id) DO UPDATE SET
                  status=excluded.status, data=excluded.data
                """,
                (
                    audit.audit_id,
                    audit.story_id,
                    audit.job_id,
                    audit.stage,
                    audit.prompt_version,
                    audit.charter_version,
                    audit.provider,
                    audit.model,
                    audit.status,
                    dumps(data),
                    audit.created_at,
                ),
            )
        return audit

    def list_generation_audits(
        self, story_id: str, *, limit: int = 50
    ) -> list[GenerationAudit]:
        return [
            GenerationAudit.model_validate(data)
            for data in rows_data(
                self._many(
                    "SELECT data FROM generation_audits "
                    "WHERE story_id = ? ORDER BY created_at DESC LIMIT ?",
                    (story_id, max(1, min(200, limit))),
                )
            )
        ]

    def save_script(self, script: ScriptDocument) -> ScriptDocument:
        existing_versions = [
            row["version"]
            for row in self._many(
                "SELECT version FROM script_revisions WHERE story_id = ?",
                (script.story_id,),
            )
        ]
        if script.version in existing_versions:
            script.version = max(existing_versions) + 1
            script.script_id = new_id("script")
        script.updated_at = now_iso()
        data = script.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO script_revisions(script_id, story_id, version, status, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    script.script_id,
                    script.story_id,
                    script.version,
                    script.status.value,
                    dumps(data),
                    script.created_at,
                    script.updated_at,
                ),
            )
        return script

    def latest_script(
        self, story_id: str, *, approved: bool = False
    ) -> ScriptDocument | None:
        if approved:
            row = self._one(
                "SELECT data FROM script_revisions WHERE story_id = ? AND status = ? ORDER BY version DESC LIMIT 1",
                (story_id, ScriptStatus.approved.value),
            )
        else:
            row = self._one(
                "SELECT data FROM script_revisions WHERE story_id = ? ORDER BY version DESC LIMIT 1",
                (story_id,),
            )
        data = row_data(row)
        return ScriptDocument.model_validate(data) if data else None

    def update_script_status(
        self, script_id: str, status: ScriptStatus | str
    ) -> ScriptDocument:
        row = self._one(
            "SELECT data FROM script_revisions WHERE script_id = ?", (script_id,)
        )
        data = row_data(row)
        if data is None:
            raise NotFoundError(f"script not found: {script_id}")
        data["status"] = str(
            status.value if isinstance(status, ScriptStatus) else status
        )
        if data["status"] == ScriptStatus.approved.value:
            for section in data.get("sections", []):
                if section.get("approval_status") != "locked":
                    section["approval_status"] = "approved"
        data["updated_at"] = now_iso()
        script = ScriptDocument.model_validate(data)
        with self.connection:
            self.connection.execute(
                "UPDATE script_revisions SET status = ?, data = ?, updated_at = ? WHERE script_id = ?",
                (
                    script.status.value,
                    dumps(script.model_dump(mode="json")),
                    script.updated_at,
                    script_id,
                ),
            )
        return script

    def upsert_visual(self, visual: VisualCandidate) -> None:
        data = visual.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO visual_candidates(asset_id, story_id, provider, media_type, rights_tier, review_status, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                  story_id=excluded.story_id,
                  provider=excluded.provider,
                  media_type=excluded.media_type,
                  rights_tier=excluded.rights_tier,
                  review_status=excluded.review_status,
                  data=excluded.data
                """,
                (
                    visual.asset_id,
                    visual.story_id,
                    visual.provider,
                    visual.media_type.value,
                    visual.rights_tier.value,
                    visual.review_status.value,
                    dumps(data),
                    visual.created_at,
                ),
            )

    def list_visuals(self, story_id: str) -> list[VisualCandidate]:
        visuals = [
            VisualCandidate.model_validate(data)
            for data in rows_data(
                self._many(
                    "SELECT data FROM visual_candidates WHERE story_id = ? ORDER BY review_status ASC, created_at DESC",
                    (story_id,),
                )
            )
        ]
        return sorted(visuals, key=lambda visual: visual.relevance_score, reverse=True)

    def get_visual(self, asset_id: str) -> VisualCandidate:
        row = self._one(
            "SELECT data FROM visual_candidates WHERE asset_id = ?", (asset_id,)
        )
        data = row_data(row)
        if data is None:
            raise NotFoundError(f"visual not found: {asset_id}")
        return VisualCandidate.model_validate(data)

    def save_timeline(self, timeline: TimelinePlan) -> TimelinePlan:
        existing_versions = [
            row["version"]
            for row in self._many(
                "SELECT version FROM timeline_revisions WHERE story_id = ?",
                (timeline.story_id,),
            )
        ]
        if timeline.version in existing_versions:
            timeline.version = max(existing_versions) + 1
            timeline.timeline_id = new_id("timeline")
            timeline.created_at = now_iso()
        timeline.updated_at = now_iso()
        data = timeline.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO timeline_revisions(timeline_id, story_id, version, status, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timeline.timeline_id,
                    timeline.story_id,
                    timeline.version,
                    timeline.status.value,
                    dumps(data),
                    timeline.created_at,
                    timeline.updated_at,
                ),
            )
        return timeline

    def latest_timeline(
        self, story_id: str, *, approved: bool = False
    ) -> TimelinePlan | None:
        if approved:
            row = self._one(
                "SELECT data FROM timeline_revisions WHERE story_id = ? AND status = ? ORDER BY version DESC LIMIT 1",
                (story_id, TimelineStatus.approved.value),
            )
        else:
            row = self._one(
                "SELECT data FROM timeline_revisions WHERE story_id = ? ORDER BY version DESC LIMIT 1",
                (story_id,),
            )
        data = row_data(row)
        return TimelinePlan.model_validate(data) if data else None

    # Jobs / artifacts ----------------------------------------------------
    def create_job(
        self,
        job_type: str,
        *,
        episode_id: str | None = None,
        story_id: str | None = None,
        render_profile: str = "preview",
        payload: dict[str, Any] | None = None,
    ) -> RenderJob:
        job = RenderJob(
            job_type=job_type,
            queue_lane=queue_lane_for_job_type(job_type),
            episode_id=episode_id,
            story_id=story_id,
            render_profile=render_profile,
            payload=payload or {},
            max_attempts=default_max_attempts(job_type),
        )
        self.upsert_job(job)
        return job

    def active_job(
        self,
        job_type: str,
        *,
        story_id: str | None = None,
        episode_id: str | None = None,
        render_profile: str | None = None,
    ) -> RenderJob | None:
        filters = ["job_type = ?", "status IN ('queued', 'running')"]
        params: list[Any] = [job_type]
        if story_id is not None:
            filters.append("story_id = ?")
            params.append(story_id)
        if episode_id is not None:
            filters.append("episode_id = ?")
            params.append(episode_id)
        rows = rows_data(
            self._many(
                f"SELECT data FROM render_jobs WHERE {' AND '.join(filters)} ORDER BY created_at DESC LIMIT 20",
                tuple(params),
            )
        )
        for data in rows:
            job = RenderJob.model_validate(data)
            if render_profile is None or job.render_profile == render_profile:
                return job
        return None

    def upsert_job(self, job: RenderJob) -> None:
        job.updated_at = now_iso()
        data = job.model_dump(mode="json")
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO render_jobs(
                  job_id, job_type, queue_lane, episode_id, story_id, status,
                  progress, stage, available_at, attempts, max_attempts, data,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  status=excluded.status,
                  progress=excluded.progress,
                  stage=excluded.stage,
                  queue_lane=excluded.queue_lane,
                  available_at=excluded.available_at,
                  attempts=excluded.attempts,
                  max_attempts=excluded.max_attempts,
                  data=excluded.data,
                  updated_at=excluded.updated_at
                """,
                (
                    job.job_id,
                    job.job_type,
                    job.queue_lane.value,
                    job.episode_id,
                    job.story_id,
                    job.status.value,
                    job.progress,
                    job.stage,
                    job.available_at,
                    job.attempts,
                    job.max_attempts,
                    dumps(data),
                    job.created_at,
                    job.updated_at,
                ),
            )

    def update_job_if_status(
        self, job: RenderJob, expected_status: JobStatus
    ) -> bool:
        """Persist a worker-owned update without resurrecting cancelled jobs."""

        job.updated_at = now_iso()
        data = job.model_dump(mode="json")
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE render_jobs
                SET status = ?, progress = ?, stage = ?, queue_lane = ?,
                    available_at = ?, attempts = ?, max_attempts = ?,
                    data = ?, updated_at = ?
                WHERE job_id = ? AND status = ?
                """,
                (
                    job.status.value,
                    job.progress,
                    job.stage,
                    job.queue_lane.value,
                    job.available_at,
                    job.attempts,
                    job.max_attempts,
                    dumps(data),
                    job.updated_at,
                    job.job_id,
                    expected_status.value,
                ),
            )
        return cursor.rowcount == 1

    def heartbeat_job(self, job_id: str) -> JobStatus:
        """Refresh a running job's lease and return its authoritative status."""

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._one(
                "SELECT data FROM render_jobs WHERE job_id = ?", (job_id,)
            )
            data = row_data(row)
            if data is None:
                raise NotFoundError(f"job not found: {job_id}")
            job = RenderJob.model_validate(data)
            if job.status == JobStatus.running:
                job.updated_at = now_iso()
                self.connection.execute(
                    "UPDATE render_jobs SET data = ?, updated_at = ? "
                    "WHERE job_id = ? AND status = 'running'",
                    (dumps(job.model_dump(mode="json")), job.updated_at, job_id),
                )
            self.connection.commit()
            return job.status
        except Exception:
            self.connection.rollback()
            raise

    def get_job(self, job_id: str) -> RenderJob:
        row = self._one("SELECT data FROM render_jobs WHERE job_id = ?", (job_id,))
        data = row_data(row)
        if data is None:
            raise NotFoundError(f"job not found: {job_id}")
        return RenderJob.model_validate(data)

    def list_jobs(
        self,
        limit: int = 100,
        *,
        story_id: str | None = None,
        episode_id: str | None = None,
        job_type: str | None = None,
    ) -> list[RenderJob]:
        filters: list[str] = []
        params: list[Any] = []
        if story_id is not None:
            filters.append("story_id = ?")
            params.append(story_id)
        if episode_id is not None:
            filters.append("episode_id = ?")
            params.append(episode_id)
        if job_type is not None:
            filters.append("job_type = ?")
            params.append(job_type)
        where = f"WHERE {' AND '.join(filters)} " if filters else ""
        params.append(limit)
        return [
            RenderJob.model_validate(data)
            for data in rows_data(
                self._many(
                    f"SELECT data FROM render_jobs {where}ORDER BY created_at DESC LIMIT ?",
                    tuple(params),
                )
            )
        ]

    def claim_next_job(
        self, queue_lane: JobQueueLane | str | None = None
    ) -> RenderJob | None:
        # A deferred SELECT followed by a separate UPSERT allows two worker
        # processes to claim the same row. Serialize the claim and make the
        # status transition conditional instead.
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            lane_value = (
                queue_lane.value if isinstance(queue_lane, JobQueueLane) else queue_lane
            )
            due_at = now_iso()
            clauses = [
                "candidate.status = 'queued'",
                "(candidate.available_at IS NULL OR candidate.available_at <= ?)",
                """
                NOT EXISTS (
                  SELECT 1 FROM render_jobs AS running
                  WHERE running.status = 'running'
                    AND (
                      (candidate.story_id IS NOT NULL
                       AND running.story_id = candidate.story_id)
                      OR
                      (candidate.episode_id IS NOT NULL
                       AND running.episode_id = candidate.episode_id
                       AND (candidate.job_type = 'assemble_episode'
                            OR running.job_type = 'assemble_episode'))
                    )
                )
                """,
            ]
            params: list[Any] = [due_at]
            if lane_value:
                clauses.append("candidate.queue_lane = ?")
                params.append(lane_value)
            row = self._one(
                f"SELECT candidate.data FROM render_jobs AS candidate WHERE {' AND '.join(clauses)} "
                "ORDER BY COALESCE(candidate.available_at, candidate.created_at) ASC, "
                "candidate.created_at ASC LIMIT 1",
                tuple(params),
            )
            data = row_data(row)
            if data is None:
                self.connection.commit()
                return None
            job = RenderJob.model_validate(data)
            job.status = JobStatus.running
            claimed_at = now_iso()
            job.started_at = job.started_at or claimed_at
            job.last_attempt_at = claimed_at
            job.updated_at = claimed_at
            job.attempts += 1
            job.stage = "starting"
            job.available_at = None
            job.error = None
            job.traceback = None
            job.failure_kind = None
            cursor = self.connection.execute(
                """
                UPDATE render_jobs
                SET status = ?, progress = ?, stage = ?, queue_lane = ?,
                    available_at = ?, attempts = ?, max_attempts = ?,
                    data = ?, updated_at = ?
                WHERE job_id = ? AND status = 'queued'
                """,
                (
                    job.status.value,
                    job.progress,
                    job.stage,
                    job.queue_lane.value,
                    job.available_at,
                    job.attempts,
                    job.max_attempts,
                    dumps(job.model_dump(mode="json")),
                    job.updated_at,
                    job.job_id,
                ),
            )
            self.connection.commit()
            return job if cursor.rowcount == 1 else None
        except Exception:
            self.connection.rollback()
            raise

    def record_artifact(
        self,
        artifact: Any,
        *,
        story_id: str | None = None,
        episode_id: str | None = None,
    ) -> None:
        data = (
            artifact.model_dump(mode="json")
            if hasattr(artifact, "model_dump")
            else artifact
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO artifacts(artifact_id, artifact_type, story_id, episode_id, path, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET data=excluded.data
                """,
                (
                    data["artifact_id"],
                    data["artifact_type"],
                    story_id,
                    episode_id,
                    data["path"],
                    dumps(data),
                    data.get("created_at", now_iso()),
                ),
            )


def get_repository(db_path: str | Path | None = None) -> Repository:
    return Repository(db_path)
