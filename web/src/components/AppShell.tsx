import React from 'react';
import { LeftRail, type Page } from './LeftRail';
import { RightRail } from './RightRail';
import { MobileChrome } from './MobileChrome';

/** Pages that show the right rail. */
const RIGHT_RAIL_PAGES = new Set<Page>(['command', 'inbox', 'jobs']);

export const AppShell: React.FC<{
  page: Page;
  setPage: (page: Page) => void;
  children: React.ReactNode;
}> = ({ page, setPage, children }) => {
  const showRightRail = RIGHT_RAIL_PAGES.has(page);
  const [mobileRailOpen, setMobileRailOpen] = React.useState(false);

  React.useEffect(() => setMobileRailOpen(false), [page]);

  return (
    <div className={`app-shell ${showRightRail ? 'has-right-rail' : ''}`}>
      <MobileChrome
        page={page}
        setPage={setPage}
        onOpenAttention={() => setMobileRailOpen(true)}
      />
      <LeftRail page={page} setPage={setPage} />
      <main className="main-content">{children}</main>
      {(showRightRail || mobileRailOpen) && (
        <RightRail
          mobileOpen={mobileRailOpen}
          onMobileClose={() => setMobileRailOpen(false)}
        />
      )}
      {mobileRailOpen && (
        <button
          type="button"
          className="mobile-drawer-scrim"
          aria-label="Close attention center"
          onClick={() => setMobileRailOpen(false)}
        />
      )}
    </div>
  );
};
