import React from 'react';

export const EmptyState: React.FC<{
  icon?: string;
  title: string;
  description?: string;
  children?: React.ReactNode;
}> = ({ icon, title, description, children }) => (
  <div className="empty-state">
    {icon && <div className="empty-state-icon">{icon}</div>}
    <div className="empty-state-title">{title}</div>
    {description && <p className="empty-state-desc">{description}</p>}
    {children}
  </div>
);
