import React from "react";
import { StudioProvider, useStudio } from "./state/useStudio";
import { AppShell } from "./components/AppShell";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { SettingsModal } from "./components/SettingsModal";
import type { Page } from "./components/LeftRail";
import { CommandCenter } from "./pages/CommandCenter";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { ThemeProvider } from "./components/theme-provider";
import "./styles/studio.css";
import "./styles/shadcn.css";

const Main: React.FC = () => {
  const [page, setPage] = React.useState<Page>("command");
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
          {page === "review" ? (
            <ReviewQueuePage onOpenCommandCenter={() => setPage("command")} />
          ) : (
            <CommandCenter
              key={studio.selectedChannelId}
              onOpenReviewQueue={() => setPage("review")}
            />
          )}
          {page === "settings" && (
            <SettingsModal onClose={() => setPage("command")} />
          )}
        </>
      )}
    </AppShell>
  );
};

export default function App() {
  return (
    <AppErrorBoundary>
      <ThemeProvider defaultTheme="system" storageKey="synthea-ui-theme">
        <StudioProvider>
          <Main />
        </StudioProvider>
      </ThemeProvider>
    </AppErrorBoundary>
  );
}
