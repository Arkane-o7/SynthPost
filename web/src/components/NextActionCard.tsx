import React from 'react';
import { getNextAction, type StageKey } from '../lib/workflowUtils';

export const NextActionCard: React.FC<{
  workflowState?: string;
  onNavigate: (stage: StageKey) => void;
  onApiAction?: (action: string) => void;
}> = ({ workflowState, onNavigate, onApiAction }) => {
  const action = getNextAction(workflowState);
  const isComplete = workflowState === 'completed';

  return (
    <div className="next-action-card animate-fade-in">
      <div className="next-action-kicker">
        {isComplete ? '✓ COMPLETE' : '▶ NEXT STEP'}
      </div>
      <div className="next-action-title">{action.title}</div>
      <p className="next-action-desc">{action.description}</p>
      <button
        className={isComplete ? 'btn-success btn-lg' : 'btn-primary btn-lg'}
        onClick={() => {
          if (action.ctaType === 'navigate') {
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
