// SynthPost V2 — Workflow utilities
// Maps backend workflow_state values to UI stage steps and next-action guidance.

export const STAGES = [
  { key: "story", label: "Select Story", number: 1 },
  { key: "draft", label: "Research & Script", number: 2 },
  { key: "visuals", label: "Visuals", number: 3 },
  { key: "timeline", label: "Timeline", number: 4 },
  { key: "final", label: "Final Video", number: 5 },
] as const;

export type StageKey = (typeof STAGES)[number]["key"];

export type StepStatus =
  | "not_started"
  | "completed"
  | "in_progress"
  | "needs_review"
  | "blocked";

/** Ordered list of backend workflow_state values. */
const STATE_ORDER = [
  "selected",
  "researching",
  "research_ready",
  "script_generating",
  "script_review",
  "script_approved",
  "visuals_searching",
  "visuals_review",
  "timeline_draft",
  "timeline_review",
  "timeline_approved",
  "rendering_avatar",
  "rendering_composition",
  "assembling",
  "completed",
  "failed",
  "cancelled",
];

/** Which stepper-step index (0-based) corresponds to each workflow_state. */
const STATE_TO_STEP: Record<string, number> = {
  selected: 0,
  researching: 1,
  research_ready: 1,
  script_generating: 1,
  script_review: 1,
  script_approved: 2,
  visuals_searching: 2,
  visuals_review: 2,
  timeline_draft: 3,
  timeline_review: 3,
  timeline_approved: 4,
  rendering_avatar: 4,
  rendering_composition: 4,
  assembling: 4,
  completed: 4,
  failed: 0,
  cancelled: 0,
};

/** Is this state a "needs review" state? */
const REVIEW_STATES = new Set([
  "research_ready",
  "script_review",
  "visuals_review",
  "timeline_review",
]);

const BLOCKED_STATES = new Set(["failed", "cancelled"]);

/**
 * Derive the status of every stepper step from the current workflow_state.
 */
export function getStepStatuses(
  workflowState?: string,
): Record<StageKey, StepStatus> {
  const result: Record<string, StepStatus> = {};
  const stateIdx = workflowState ? (STATE_TO_STEP[workflowState] ?? -1) : -1;
  const isComplete = workflowState === "completed";

  for (let i = 0; i < STAGES.length; i++) {
    const stage = STAGES[i];
    if (workflowState && BLOCKED_STATES.has(workflowState)) {
      result[stage.key] = i === stateIdx ? "blocked" : "not_started";
    } else if (isComplete) {
      result[stage.key] = "completed";
    } else if (i < stateIdx) {
      result[stage.key] = "completed";
    } else if (i === stateIdx) {
      result[stage.key] =
        workflowState && REVIEW_STATES.has(workflowState)
          ? "needs_review"
          : "in_progress";
    } else {
      result[stage.key] = "not_started";
    }
  }
  return result as Record<StageKey, StepStatus>;
}

/**
 * Which stepper step should be active/focused for a given workflow_state.
 */
export function getActiveStage(workflowState?: string): StageKey {
  if (!workflowState) return "story";
  const idx = STATE_TO_STEP[workflowState];
  if (idx === undefined) return "story";
  return STAGES[Math.min(idx, STAGES.length - 1)].key;
}

export type NextAction = {
  title: string;
  description: string;
  ctaLabel: string;
  ctaType: "navigate" | "api";
  stageKey: StageKey;
  apiAction?: "generateScript";
};

/**
 * Determine the next recommended action based on workflow_state.
 */
export function getNextAction(workflowState?: string): NextAction {
  switch (workflowState) {
    case "selected":
      return {
        title: "Set up research and script",
        description:
          "Choose the narration format and target video length before starting the combined research and script run.",
        ctaLabel: "Configure Draft",
        ctaType: "navigate",
        stageKey: "draft",
      };
    case "researching":
      return {
        title: "Researching, then writing",
        description:
          "Sources and claims are being assembled first. Script generation will begin automatically when the evidence pack is ready.",
        ctaLabel: "Open Draft Desk",
        ctaType: "navigate",
        stageKey: "draft",
      };
    case "research_ready":
      return {
        title: "Research ready — write the script",
        description:
          "The source pack is ready. Continue into a broadcast script if automatic generation was interrupted.",
        ctaLabel: "Write Script",
        ctaType: "api",
        stageKey: "draft",
        apiAction: "generateScript",
      };
    case "script_generating":
      return {
        title: "Script generation is running",
        description:
          "Synthea is waiting for the configured structured script generator. Provider failures are reported directly and never switch providers implicitly.",
        ctaLabel: "Open Draft Desk",
        ctaType: "navigate",
        stageKey: "draft",
      };
    case "script_review":
      return {
        title: "Review and approve the script",
        description:
          "Read through the generated script, make edits, then approve it to lock this version.",
        ctaLabel: "Review Draft",
        ctaType: "navigate",
        stageKey: "draft",
      };
    case "script_approved":
      return {
        title: "Add and review visuals",
        description:
          "Search this episode's isolated media inbox, upload files, or stage visuals. Review rights tiers and approve each one.",
        ctaLabel: "Open Visuals",
        ctaType: "navigate",
        stageKey: "visuals",
      };
    case "visuals_searching":
      return {
        title: "Visual search is running",
        description:
          "The worker is scanning this episode's media inbox and web sources. Watch Active Jobs, then review rights when candidates appear.",
        ctaLabel: "Open Visuals",
        ctaType: "navigate",
        stageKey: "visuals",
      };
    case "visuals_review":
      return {
        title: "Review visuals or continue with fallback",
        description:
          "Review any staged media and rights tiers. If no local visuals are available, continue to Timeline and Synthea will use approved fallback anchor visuals.",
        ctaLabel: "Open Visuals",
        ctaType: "navigate",
        stageKey: "visuals",
      };
    case "timeline_draft":
      return {
        title: "Validate the timeline draft",
        description:
          "A draft timeline exists. Validate segment timing/template choices, then approve the timeline.",
        ctaLabel: "Open Timeline",
        ctaType: "navigate",
        stageKey: "timeline",
      };
    case "timeline_review":
      return {
        title: "Review and approve the timeline",
        description:
          "Check segment ordering, template choices, and durations. Validate, then approve the timeline.",
        ctaLabel: "Open Timeline",
        ctaType: "navigate",
        stageKey: "timeline",
      };
    case "timeline_approved":
      return {
        title: "Final video queued",
        description:
          "The approved timeline is rendering at production quality. Synthea will append the channel outro and publish the assembled episode automatically.",
        ctaLabel: "Track Final Video",
        ctaType: "navigate",
        stageKey: "final",
      };
    case "rendering_avatar":
      return {
        title: "Generating the final video",
        description:
          "The production anchor and approved composition are rendering. Assembly will follow automatically.",
        ctaLabel: "Track Final Video",
        ctaType: "navigate",
        stageKey: "final",
      };
    case "rendering_composition":
      return {
        title: "Generating the final video",
        description:
          "Synthea is rendering the approved timeline at production quality, then it will attach the channel outro.",
        ctaLabel: "Track Final Video",
        ctaType: "navigate",
        stageKey: "final",
      };
    case "assembling":
      return {
        title: "Finishing the final episode",
        description:
          "The production render is complete. Synthea is appending the channel outro and writing the final episode file.",
        ctaLabel: "Track Final Video",
        ctaType: "navigate",
        stageKey: "final",
      };
    case "completed":
      return {
        title: "Production complete",
        description:
          "This episode has been fully rendered and assembled. You can start a new episode or review the output.",
        ctaLabel: "Watch Final Video",
        ctaType: "navigate",
        stageKey: "final",
      };
    case "failed":
      return {
        title: "Workflow failed",
        description:
          "A pipeline job failed. Check the right rail or Jobs page, then retry the failed step or switch stories.",
        ctaLabel: "Open Story",
        ctaType: "navigate",
        stageKey: "story",
      };
    case "cancelled":
      return {
        title: "Workflow cancelled",
        description:
          "This story workflow was cancelled. Select another story or restart from the Story Inbox.",
        ctaLabel: "Go to Story Inbox",
        ctaType: "navigate",
        stageKey: "story",
      };
    default:
      return {
        title: "Select a story to begin",
        description:
          "Head to the Story Inbox to discover candidates or add a custom story.",
        ctaLabel: "Go to Story Inbox",
        ctaType: "navigate",
        stageKey: "story",
      };
  }
}

/**
 * Backend workflow_state values in order, exported for reference.
 */
export const WORKFLOW_STATES = STATE_ORDER;
