import React from "react";
import { getNextAction, type StageKey } from "../lib/workflowUtils";

export const NextActionCard: React.FC<{
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
    <div className="next-action-card animate-fade-in">
      <div className="next-action-kicker">
        {isComplete ? "✓ COMPLETE" : "▶ NEXT STEP"}
      </div>
      <div className="next-action-title">{action.title}</div>
      <p className="next-action-desc">{action.description}</p>
      {disabled && disabledReason && (
        <div className="text-muted" style={{ fontSize: 13, marginBottom: 12 }}>
          {disabledReason}
        </div>
      )}
      <button
        className={isComplete ? "btn-success btn-lg" : "btn-primary btn-lg"}
        disabled={disabled}
        onClick={() => {
          if (action.ctaType === "navigate") {
            onNavigate(action.stageKey);
          } else if (action.apiAction && onApiAction) {
            onApiAction(action.apiAction);
          }
        }}
      >
        {action.ctaLabel}
      </button>
    </div>
  );
};
