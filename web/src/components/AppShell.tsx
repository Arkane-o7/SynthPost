import React from 'react';
import { LeftRail, type Page } from './LeftRail';
import { RightRail } from './RightRail';

/** Pages that show the right rail. */
const RIGHT_RAIL_PAGES = new Set<Page>(['command', 'inbox', 'jobs']);

export const AppShell: React.FC<{
  page: Page;
  setPage: (page: Page) => void;
  children: React.ReactNode;
}> = ({ page, setPage, children }) => {
  const showRightRail = RIGHT_RAIL_PAGES.has(page);

  return (
    <div className={`app-shell ${showRightRail ? 'has-right-rail' : ''}`}>
      <LeftRail page={page} setPage={setPage} />
      <main className="main-content">{children}</main>
      {showRightRail && <RightRail />}
    </div>
  );
};
