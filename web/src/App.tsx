import React from 'react';
import { StudioProvider, useStudio } from './state/useStudio';
import { AppShell } from './components/AppShell';
import type { Page } from './components/LeftRail';
import { CommandCenter } from './pages/CommandCenter';
import { SourcesPage } from './pages/SourcesPage';
import { StoryInboxPage } from './pages/StoryInboxPage';
import { JobsPage } from './pages/JobsPage';
import { SettingsPage } from './pages/SettingsPage';
import './styles/studio.css';

const Main: React.FC = () => {
  const [page, setPage] = React.useState<Page>('command');
  const studio = useStudio();

  return (
    <AppShell page={page} setPage={setPage}>
      {studio.error && <div className="error-banner">{studio.error}</div>}
      {studio.loading ? (
        <div className="empty-state" style={{ marginTop: 80 }}>
          <div className="empty-state-icon">⏳</div>
          <div className="empty-state-title">Loading Studio…</div>
          <p className="empty-state-desc">
            Connecting to local SQLite database.
          </p>
        </div>
      ) : (
        <>
          {page === 'command' && (
            <CommandCenter onNavigateToInbox={() => setPage('inbox')} />
          )}
          {page === 'sources' && <SourcesPage />}
          {page === 'inbox' && <StoryInboxPage />}
          {page === 'jobs' && <JobsPage />}
          {page === 'settings' && <SettingsPage />}
        </>
      )}
    </AppShell>
  );
};

export default function App() {
  return (
    <StudioProvider>
      <Main />
    </StudioProvider>
  );
}
