import React from 'react';

const TICKER = 'SYNTHPOST  ·  THE SIGNAL. THE STORY.  ·  VERIFIED SOURCE  ·  BROADCASTING LIVE  ·  ';

export const BrandRibbon: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`brand-ribbon ${className}`.trim()} aria-hidden="true">
    <div className="brand-ribbon-track"><span>{TICKER}</span><span>{TICKER}</span></div>
  </div>
);

