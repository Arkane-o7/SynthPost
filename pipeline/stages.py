"""Stable contracts for the queue-backed SynthPost production stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Mapping

from pipeline.models import JobQueueLane, RenderJob


class StageName(str, Enum):
    discovery = "discovery"
    research = "research"
    script = "script_generate"
    visuals = "visual_search"
    timeline = "timeline_generate"
    avatar = "render_avatar"
    composition = "render_story"
    assembly = "assemble_episode"


class StageOutcome(str, Enum):
    completed = "completed"
    skipped = "skipped"
    cached = "cached"
    failed = "failed"
    cancelled = "cancelled"


@dataclass(frozen=True)
class StageContract:
    name: StageName
    lane: JobQueueLane
    requires_episode: bool
    requires_story: bool
    output_keys: tuple[str, ...]
    artifact_owner: str
    retry_safe: bool = True

    def validate_job(self, job: RenderJob) -> None:
        if self.requires_episode and not job.episode_id:
            raise ValueError(f"{self.name.value} job requires episode_id")
        if self.requires_story and not job.story_id:
            raise ValueError(f"{self.name.value} job requires story_id")
        if job.queue_lane != self.lane:
            raise ValueError(
                f"{self.name.value} belongs to the {self.lane.value} queue, "
                f"not {job.queue_lane.value}"
            )

    def validate_outputs(self, outputs: Mapping[str, str]) -> None:
        missing = [key for key in self.output_keys if key not in outputs]
        if missing:
            raise ValueError(
                f"{self.name.value} did not return required output(s): "
                f"{', '.join(missing)}"
            )


STAGE_CONTRACTS: dict[str, StageContract] = {
    StageName.discovery.value: StageContract(
        StageName.discovery,
        JobQueueLane.editorial,
        requires_episode=False,
        requires_story=False,
        output_keys=("candidate_count",),
        artifact_owner="SQLite story_candidates",
    ),
    StageName.research.value: StageContract(
        StageName.research,
        JobQueueLane.editorial,
        requires_episode=False,
        requires_story=True,
        output_keys=("research_pack_id",),
        artifact_owner="SQLite research_packs + episode story artifacts",
    ),
    StageName.script.value: StageContract(
        StageName.script,
        JobQueueLane.editorial,
        requires_episode=False,
        requires_story=True,
        output_keys=("script_id",),
        artifact_owner="SQLite script_revisions + scripts/script_vNNN.json",
    ),
    StageName.visuals.value: StageContract(
        StageName.visuals,
        JobQueueLane.media,
        requires_episode=False,
        requires_story=True,
        output_keys=("visual_count",),
        artifact_owner="episode media inbox + story visuals",
    ),
    StageName.timeline.value: StageContract(
        StageName.timeline,
        JobQueueLane.media,
        requires_episode=False,
        requires_story=True,
        output_keys=("timeline_id",),
        artifact_owner="SQLite timeline_revisions + timelines/",
    ),
    StageName.avatar.value: StageContract(
        StageName.avatar,
        JobQueueLane.render,
        requires_episode=False,
        requires_story=True,
        output_keys=("story_manifest", "anchor_output_path"),
        artifact_owner="episode story direction/avatar outputs",
        retry_safe=False,
    ),
    StageName.composition.value: StageContract(
        StageName.composition,
        JobQueueLane.render,
        requires_episode=False,
        requires_story=True,
        output_keys=("story_manifest",),
        artifact_owner="episode story composited video",
        retry_safe=False,
    ),
    StageName.assembly.value: StageContract(
        StageName.assembly,
        JobQueueLane.render,
        requires_episode=True,
        requires_story=False,
        output_keys=("final_output_path",),
        artifact_owner="episode final video + episode manifest",
        retry_safe=False,
    ),
}


def contract_for(job_type: str) -> StageContract:
    try:
        return STAGE_CONTRACTS[job_type]
    except KeyError as exc:
        raise ValueError(f"No pipeline stage contract for job_type={job_type}") from exc


@dataclass
class StageRecord:
    stage: str
    outcome: StageOutcome
    elapsed_seconds: float
    detail: str = ""


@dataclass
class PipelineRunSummary:
    """Small in-memory summary suitable for CLIs, tests, and API serialization."""

    started_at_monotonic: float = field(default_factory=monotonic)
    records: list[StageRecord] = field(default_factory=list)

    def add(
        self, stage: str, outcome: StageOutcome, started_at: float, detail: str = ""
    ) -> StageRecord:
        record = StageRecord(
            stage=stage,
            outcome=outcome,
            elapsed_seconds=round(max(0.0, monotonic() - started_at), 3),
            detail=detail,
        )
        self.records.append(record)
        return record

    def as_dict(self) -> dict[str, object]:
        counts = {outcome.value: 0 for outcome in StageOutcome}
        for record in self.records:
            counts[record.outcome.value] += 1
        return {
            "elapsed_seconds": round(
                max(0.0, monotonic() - self.started_at_monotonic), 3
            ),
            "counts": counts,
            "stages": [
                {
                    "stage": record.stage,
                    "outcome": record.outcome.value,
                    "elapsed_seconds": record.elapsed_seconds,
                    "detail": record.detail,
                }
                for record in self.records
            ],
        }

    def render_text(self) -> str:
        data = self.as_dict()
        counts = data["counts"]
        assert isinstance(counts, dict)
        headline = " ".join(
            f"{name}={counts[name]}"
            for name in ("completed", "cached", "skipped", "failed", "cancelled")
        )
        lines = [f"Pipeline summary: {headline}"]
        for record in self.records:
            detail = f" — {record.detail}" if record.detail else ""
            lines.append(
                f"  {record.stage}: {record.outcome.value} "
                f"({record.elapsed_seconds:.3f}s){detail}"
            )
        return "\n".join(lines)
