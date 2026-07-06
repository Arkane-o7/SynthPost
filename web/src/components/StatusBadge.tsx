import React from 'react';

export type BadgeTone = 'green' | 'amber' | 'red' | 'blue' | 'neutral';

function toneForStatus(status: string): BadgeTone {
  switch (status) {
    case 'approved':
    case 'completed':
    case 'manual_approved':
    case 'enabled':
      return 'green';
    case 'needs_review':
    case 'in_progress':
    case 'review':
    case 'draft':
    case 'queued':
    case 'running':
    case 'suggested':
    case 'yellow':
      return 'amber';
    case 'rejected':
    case 'failed':
    case 'blocked':
    case 'cancelled':
    case 'disabled':
    case 'red':
      return 'red';
    case 'ready':
    case 'selected':
    case 'green':
      return 'green';
    default:
      return 'neutral';
  }
}

const toneClass: Record<BadgeTone, string> = {
  green: 'badge-green',
  amber: 'badge-amber',
  red: 'badge-red',
  blue: 'badge-blue',
  neutral: '',
};

export const StatusBadge: React.FC<{
  children: React.ReactNode;
  tone?: BadgeTone;
  /** Auto-derive tone from a status string. Overridden by explicit `tone`. */
  status?: string;
}> = ({ children, tone, status }) => {
  const resolved = tone ?? (status ? toneForStatus(status) : 'neutral');
  return <span className={`badge ${toneClass[resolved]}`}>{children}</span>;
};
