import React from 'react';

export const BrandSeal: React.FC<{ compact?: boolean }> = ({ compact = false }) => (
  <span className={`brand-seal${compact ? ' brand-seal-compact' : ''}`} aria-hidden="true">S</span>
);

export const BrandMark: React.FC<{ compact?: boolean; studio?: boolean }> = ({ compact = false, studio = false }) => (
  <div className={`brand-mark${compact ? ' brand-mark-compact' : ''}`} aria-label="SynthPost">
    <BrandSeal compact={compact} />
    {!compact && (
      <span className="brand-wordmark">
        SynthPost<span className="brand-period">.</span>
        {studio && <small>Studio</small>}
      </span>
    )}
  </div>
);

