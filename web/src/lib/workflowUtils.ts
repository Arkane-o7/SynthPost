// SynthPost V2 — Workflow utilities
// Maps backend workflow_state values to UI stage steps and next-action guidance.

export const STAGES = [
  { key: "story", label: "Select Story", number: 1 },
  { key: "research", label: "Research", number: 2 },
  { key: "script", label: "Script", number: 3 },
  { key: "visuals", label: "Visuals", number: 4 },
  { key: "timeline", label: "Timeline", number: 5 },
  { key: "preview", label: "Preview", number: 6 },
  { key: "render", label: "Render", number: 7 },
  { key: "assemble", label: "Assemble", number: 8 },
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
  research_ready: 2,
  script_generating: 2,
  script_review: 2,
  script_approved: 3,
  visuals_searching: 3,
  visuals_review: 3,
  timeline_draft: 4,
  timeline_review: 4,
  timeline_approved: 5,
  rendering_avatar: 6,
  rendering_composition: 6,
  assembling: 7,
  completed: 7,
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
  apiAction?: "startResearch" | "generateScript";
};

/**
 * Determine the next recommended action based on workflow_state.
 */
export function getNextAction(workflowState?: string): NextAction {
  switch (workflowState) {
    case "selected":
      return {
        title: "Start research",
        description:
          "Run the research job to extract claims, evidence, and entities from the source material.",
        ctaLabel: "Start Research Job",
        ctaType: "api",
        stageKey: "research",
        apiAction: "startResearch",
      };
    case "researching":
      return {
        title: "Research is running",
        description:
          "The worker is extracting claims, evidence, and entities. Watch Active Jobs on the right rail.",
        ctaLabel: "Open Research",
        ctaType: "navigate",
        stageKey: "research",
      };
    case "research_ready":
      return {
        title: "Generate or write a script",
        description:
          "Use the configured structured AI provider to generate a broadcast script, or write one manually from the research pack.",
        ctaLabel: "Generate Script",
        ctaType: "api",
        stageKey: "script",
        apiAction: "generateScript",
      };
    case "script_generating":
      return {
        title: "Script generation is running",
        description:
          "SynthPost is waiting for the configured structured script generator. Provider failures are reported directly and never switch providers implicitly.",
        ctaLabel: "Open Script",
        ctaType: "navigate",
        stageKey: "script",
      };
    case "script_review":
      return {
        title: "Review and approve the script",
        description:
          "Read through the generated script, make edits, then approve it to lock this version.",
        ctaLabel: "Open Script Editor",
        ctaType: "navigate",
        stageKey: "script",
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
          "Review any staged media and rights tiers. If no local visuals are available, continue to Timeline and SynthPost will use approved fallback anchor visuals.",
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
        title: "Build manifest and preview",
        description:
          "Build the renderer manifest and generate a preview frame to verify the composition looks correct.",
        ctaLabel: "Open Preview",
        ctaType: "navigate",
        stageKey: "preview",
      };
    case "rendering_avatar":
      return {
        title: "Avatar render is running",
        description:
          "The avatar engine is rendering the anchor. This can take several minutes in production mode.",
        ctaLabel: "Open Render Controls",
        ctaType: "navigate",
        stageKey: "render",
      };
    case "rendering_composition":
      return {
        title: "Render the story",
        description:
          "Render avatar and story video using the approved timeline and visuals.",
        ctaLabel: "Open Render Controls",
        ctaType: "navigate",
        stageKey: "render",
      };
    case "assembling":
      return {
        title: "Assemble the final episode",
        description:
          "Concatenate rendered story segments and append the SynthPost outro.",
        ctaLabel: "Open Assembly",
        ctaType: "navigate",
        stageKey: "assemble",
      };
    case "completed":
      return {
        title: "Production complete",
        description:
          "This episode has been fully rendered and assembled. You can start a new episode or review the output.",
        ctaLabel: "View Output",
        ctaType: "navigate",
        stageKey: "assemble",
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
