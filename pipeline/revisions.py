from __future__ import annotations

from pipeline.models import EpisodeStatus, StoryWorkflowState, now_iso
from pipeline.workflow import can_transition


def reopen_episode_for_revision(repository, story_id: str) -> None:
    """Reopen production while retaining the previous assembled output."""

    episode = repository.episode_for_story(story_id)
    if episode.status not in {EpisodeStatus.completed, EpisodeStatus.failed}:
        return
    episode.status = EpisodeStatus.in_progress
    episode.updated_at = now_iso()
    repository.upsert_episode(episode)


def move_story_for_revision(
    repository,
    story_id: str,
    target: StoryWorkflowState,
) -> None:
    """Move a story back to an editable stage and invalidate later stages."""

    assert_story_can_move_for_revision(repository, story_id, target)
    current = repository.candidate_for_story(story_id).workflow_state
    if current != target:
        repository.transition_story(story_id, target)
    reopen_episode_for_revision(repository, story_id)


def assert_story_can_move_for_revision(
    repository,
    story_id: str,
    target: StoryWorkflowState,
) -> None:
    """Validate a rollback before its edited artifact is persisted."""

    current = repository.candidate_for_story(story_id).workflow_state
    if current != target and not can_transition(current, target):
        raise ValueError(
            f"Story cannot enter {target.value} from workflow state "
            f"{current.value}"
        )
