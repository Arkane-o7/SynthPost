import React from "react";
import { getNextAction, type StageKey } from "../lib/workflowUtils";

export const NextActionControl: React.FC<{
  workflowState?: string;
  onNavigate: (stage: StageKey) => void;
  onApiAction?: (action: string) => void;
  disabled?: boolean;
  disabledReason?: string;
}> = ({
  workflowState,
  onNavigate,
  onApiAction,
  disabled = false,
  disabledReason,
}) => {
  const action = getNextAction(workflowState);
  const isComplete = workflowState === "completed";

  return (
    <div className="next-action-control animate-fade-in">
      <div className="next-action-control-copy">
        <span>{isComplete ? "Complete" : "Next step"}</span>
        <strong>{action.title}</strong>
      </div>
      <button
        type="button"
        className={isComplete ? "btn-success" : "btn-primary"}
        disabled={disabled}
        title={disabled && disabledReason ? disabledReason : action.description}
        onClick={() => {
          if (action.ctaType === "navigate") {
            onNavigate(action.stageKey);
          } else if (action.apiAction && onApiAction) {
            onApiAction(action.apiAction);
          }
        }}
      >
        <span>{action.ctaLabel}</span>
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      </button>
    </div>
  );
};
