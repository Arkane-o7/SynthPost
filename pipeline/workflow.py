from __future__ import annotations

from .models import StoryWorkflowState

VALID_TRANSITIONS: dict[StoryWorkflowState, set[StoryWorkflowState]] = {
    StoryWorkflowState.draft: {
        StoryWorkflowState.discovered,
        StoryWorkflowState.selected,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.discovered: {
        StoryWorkflowState.selected,
        StoryWorkflowState.failed,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.selected: {
        StoryWorkflowState.researching,
        StoryWorkflowState.failed,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.researching: {
        StoryWorkflowState.research_ready,
        StoryWorkflowState.failed,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.research_ready: {
        StoryWorkflowState.script_generating,
        StoryWorkflowState.script_review,
        StoryWorkflowState.failed,
    },
    StoryWorkflowState.script_generating: {
        StoryWorkflowState.script_review,
        StoryWorkflowState.failed,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.script_review: {
        StoryWorkflowState.script_approved,
        StoryWorkflowState.script_generating,
        StoryWorkflowState.failed,
    },
    StoryWorkflowState.script_approved: {
        StoryWorkflowState.visuals_searching,
        StoryWorkflowState.visuals_review,
        StoryWorkflowState.failed,
    },
    StoryWorkflowState.visuals_searching: {
        StoryWorkflowState.visuals_review,
        StoryWorkflowState.failed,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.visuals_review: {
        StoryWorkflowState.timeline_draft,
        StoryWorkflowState.visuals_searching,
        StoryWorkflowState.failed,
    },
    StoryWorkflowState.timeline_draft: {
        StoryWorkflowState.timeline_review,
        StoryWorkflowState.timeline_approved,
        StoryWorkflowState.failed,
    },
    StoryWorkflowState.timeline_review: {
        StoryWorkflowState.timeline_approved,
        StoryWorkflowState.timeline_draft,
        StoryWorkflowState.failed,
    },
    StoryWorkflowState.timeline_approved: {
        StoryWorkflowState.rendering_avatar,
        StoryWorkflowState.rendering_composition,
        StoryWorkflowState.failed,
    },
    StoryWorkflowState.rendering_avatar: {
        StoryWorkflowState.rendering_composition,
        StoryWorkflowState.failed,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.rendering_composition: {
        StoryWorkflowState.assembling,
        StoryWorkflowState.failed,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.assembling: {
        StoryWorkflowState.completed,
        StoryWorkflowState.failed,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.completed: set(),
    StoryWorkflowState.failed: {
        StoryWorkflowState.selected,
        StoryWorkflowState.researching,
        StoryWorkflowState.script_generating,
        StoryWorkflowState.visuals_searching,
        StoryWorkflowState.timeline_draft,
        StoryWorkflowState.rendering_avatar,
        StoryWorkflowState.rendering_composition,
        StoryWorkflowState.assembling,
        StoryWorkflowState.cancelled,
    },
    StoryWorkflowState.cancelled: {StoryWorkflowState.selected},
}


TERMINAL_STATES = {StoryWorkflowState.completed, StoryWorkflowState.cancelled}


def can_transition(
    current: StoryWorkflowState | str, target: StoryWorkflowState | str
) -> bool:
    current_state = StoryWorkflowState(current)
    target_state = StoryWorkflowState(target)
    return target_state in VALID_TRANSITIONS[current_state]


def assert_transition(
    current: StoryWorkflowState | str, target: StoryWorkflowState | str
) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Invalid story workflow transition: {current} -> {target}")


def available_actions(state: StoryWorkflowState | str) -> list[str]:
    current = StoryWorkflowState(state)
    labels = {
        StoryWorkflowState.researching: "start_research",
        StoryWorkflowState.script_generating: "generate_script",
        StoryWorkflowState.script_review: "review_script",
        StoryWorkflowState.script_approved: "approve_script",
        StoryWorkflowState.visuals_searching: "search_visuals",
        StoryWorkflowState.visuals_review: "review_visuals",
        StoryWorkflowState.timeline_draft: "generate_timeline",
        StoryWorkflowState.timeline_review: "review_timeline",
        StoryWorkflowState.timeline_approved: "approve_timeline",
        StoryWorkflowState.rendering_avatar: "render_avatar",
        StoryWorkflowState.rendering_composition: "render_story",
        StoryWorkflowState.assembling: "assemble_episode",
    }
    actions: list[str] = []
    for target in sorted(VALID_TRANSITIONS[current], key=lambda item: item.value):
        actions.append(labels.get(target, target.value))
    return actions
