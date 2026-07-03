import React from 'react';
import {api} from '../api/client';
import type {Episode, Project, RenderJob, SourceDefinition, StoryCandidate} from '../contracts';

type StudioState = {
  projects: Project[];
  episodes: Episode[];
  sources: SourceDefinition[];
  candidates: StoryCandidate[];
  jobs: RenderJob[];
  selectedProjectId: string;
  selectedEpisodeId: string;
  selectedStoryId: string;
  error: string;
  loading: boolean;
};

type StudioContextValue = StudioState & {
  setSelectedProjectId: (value: string) => void;
  setSelectedEpisodeId: (value: string) => void;
  setSelectedStoryId: (value: string) => void;
  setError: (value: string) => void;
  refreshAll: () => Promise<void>;
  refreshJobs: () => Promise<void>;
  refreshCandidates: () => Promise<void>;
};

const StudioContext = React.createContext<StudioContextValue | null>(null);

export const StudioProvider: React.FC<{children: React.ReactNode}> = ({children}) => {
  const [state, setState] = React.useState<StudioState>({
    projects: [],
    episodes: [],
    sources: [],
    candidates: [],
    jobs: [],
    selectedProjectId: localStorage.getItem('synthpost.project') ?? '',
    selectedEpisodeId: localStorage.getItem('synthpost.episode') ?? '',
    selectedStoryId: localStorage.getItem('synthpost.story') ?? '',
    error: '',
    loading: true,
  });

  const patch = (partial: Partial<StudioState>) => setState((current) => ({...current, ...partial}));

  const refreshJobs = React.useCallback(async () => {
    const jobs = await api.listJobs();
    patch({jobs});
  }, []);

  const refreshCandidates = React.useCallback(async () => {
    const candidates = await api.listCandidates({episodeId: state.selectedEpisodeId || undefined});
    patch({candidates});
  }, [state.selectedEpisodeId]);

  const refreshAll = React.useCallback(async () => {
    patch({loading: true, error: ''});
    try {
      const [projects, episodes, sources, candidates, jobs] = await Promise.all([
        api.listProjects(),
        api.listEpisodes(),
        api.listSources(),
        api.listCandidates({episodeId: state.selectedEpisodeId || undefined}),
        api.listJobs(),
      ]);
      const selectedProjectId = state.selectedProjectId || projects[0]?.project_id || '';
      const selectedEpisodeId = state.selectedEpisodeId || episodes[0]?.episode_id || '';
      patch({projects, episodes, sources, candidates, jobs, selectedProjectId, selectedEpisodeId, loading: false});
    } catch (error) {
      patch({error: error instanceof Error ? error.message : String(error), loading: false});
    }
  }, [state.selectedEpisodeId, state.selectedProjectId]);

  React.useEffect(() => {
    void refreshAll();
  }, []);

  React.useEffect(() => {
    const timer = window.setInterval(() => void refreshJobs().catch(() => undefined), 2000);
    return () => window.clearInterval(timer);
  }, [refreshJobs]);

  const value: StudioContextValue = {
    ...state,
    setSelectedProjectId: (selectedProjectId) => {
      localStorage.setItem('synthpost.project', selectedProjectId);
      patch({selectedProjectId});
    },
    setSelectedEpisodeId: (selectedEpisodeId) => {
      localStorage.setItem('synthpost.episode', selectedEpisodeId);
      patch({selectedEpisodeId});
    },
    setSelectedStoryId: (selectedStoryId) => {
      localStorage.setItem('synthpost.story', selectedStoryId);
      patch({selectedStoryId});
    },
    setError: (error) => patch({error}),
    refreshAll,
    refreshJobs,
    refreshCandidates,
  };

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
};

export const useStudio = (): StudioContextValue => {
  const value = React.useContext(StudioContext);
  if (!value) {
    throw new Error('useStudio must be used inside StudioProvider');
  }
  return value;
};
