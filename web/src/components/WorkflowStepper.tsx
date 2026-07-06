import React from 'react';
import {
  STAGES,
  getStepStatuses,
  type StageKey,
  type StepStatus,
} from '../lib/workflowUtils';

const statusClassMap: Record<StepStatus, string> = {
  not_started: '',
  completed: 'step-completed',
  in_progress: 'step-active',
  needs_review: 'step-review',
  blocked: 'step-blocked',
};

const statusIcon: Record<StepStatus, string> = {
  not_started: '○',
  completed: '✓',
  in_progress: '◉',
  needs_review: '◐',
  blocked: '⊘',
};

export const WorkflowStepper: React.FC<{
  workflowState?: string;
  activeStage: StageKey;
  onStageClick: (stage: StageKey) => void;
}> = ({ workflowState, activeStage, onStageClick }) => {
  const statuses = getStepStatuses(workflowState);

  return (
    <div className="stepper">
      {STAGES.map((stage) => {
        const status = statuses[stage.key];
        const isActive = activeStage === stage.key;
        const cls = [
          'stepper-step',
          statusClassMap[status],
          isActive && status !== 'completed' ? 'step-active' : '',
        ]
          .filter(Boolean)
          .join(' ');

        return (
          <button
            key={stage.key}
            className={cls}
            onClick={() => onStageClick(stage.key)}
            title={`${stage.label} — ${status.replace('_', ' ')}`}
          >
            <span className="stepper-number">
              {status === 'completed' ? statusIcon.completed : stage.number}
            </span>
            <span className="stepper-label">{stage.label}</span>
          </button>
        );
      })}
    </div>
  );
};
