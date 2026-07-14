import React from "react";
import { api } from "../api/client";
import { errorMessage } from "../api/http";
import { useJobEvents } from "./useJobEvents";
import type {
  Episode,
  Project,
  RenderJob,
  SourceDefinition,
  StoryCandidate,
} from "../contracts";

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
  lastJobEventTimestamp: number;
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

export const StudioProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [state, setState] = React.useState<StudioState>({
    projects: [],
    episodes: [],
    sources: [],
    candidates: [],
    jobs: [],
    selectedProjectId: localStorage.getItem("synthpost.project") ?? "",
    selectedEpisodeId: localStorage.getItem("synthpost.episode") ?? "",
    selectedStoryId: localStorage.getItem("synthpost.story") ?? "",
    error: "",
    loading: true,
    lastJobEventTimestamp: Date.now(),
  });

  const patch = (partial: Partial<StudioState>) =>
    setState((current) => ({ ...current, ...partial }));

  const refreshJobs = React.useCallback(async () => {
    const jobs = await api.listJobs();
    patch({ jobs });
  }, []);

  const refreshCandidates = React.useCallback(async () => {
    const candidates = await api.listCandidates({
      episodeId: state.selectedEpisodeId || undefined,
    });
    patch({ candidates });
  }, [state.selectedEpisodeId]);

  const refreshAll = React.useCallback(async () => {
    patch({ loading: true, error: "" });
    try {
      const [projects, sources, jobs] = await Promise.all([
        api.listProjects(),
        api.listSources(),
        api.listJobs(),
      ]);
      const selectedProjectId =
        state.selectedProjectId || projects[0]?.project_id || "";
      const episodes = selectedProjectId
        ? await api.listEpisodes(selectedProjectId)
        : [];
      const selectedEpisodeId = episodes.some(
        (episode) => episode.episode_id === state.selectedEpisodeId,
      )
        ? state.selectedEpisodeId
        : episodes[0]?.episode_id || "";
      const candidates = await api.listCandidates({
        episodeId: selectedEpisodeId || undefined,
      });
      const persistedStoryId = localStorage.getItem("synthpost.story") ?? "";
      const requestedStoryId = persistedStoryId || state.selectedStoryId;
      const selectedStoryId = candidates.some(
        (candidate) => candidate.story_id === requestedStoryId,
      )
        ? requestedStoryId
        : candidates.find(
            (candidate) => candidate.selection_status === "selected",
          )?.story_id || "";

      localStorage.setItem("synthpost.project", selectedProjectId);
      if (selectedEpisodeId)
        localStorage.setItem("synthpost.episode", selectedEpisodeId);
      else localStorage.removeItem("synthpost.episode");
      if (selectedStoryId)
        localStorage.setItem("synthpost.story", selectedStoryId);
      else localStorage.removeItem("synthpost.story");

      patch({
        projects,
        episodes,
        sources,
        candidates,
        jobs,
        selectedProjectId,
        selectedEpisodeId,
        selectedStoryId,
        loading: false,
      });
    } catch (error) {
      patch({
        error: errorMessage(error),
        loading: false,
      });
    }
  }, [state.selectedEpisodeId, state.selectedProjectId, state.selectedStoryId]);

  React.useEffect(() => {
    void refreshAll();
  }, []);

  useJobEvents(
    (jobs) => {
      setState((current) => {
        const changed = jobs.some((newJob) => {
          const oldJob = current.jobs.find((job) => job.job_id === newJob.job_id);
          return (
            oldJob &&
            oldJob.status !== newJob.status &&
            ["completed", "failed"].includes(newJob.status)
          );
        });
        return {
          ...current,
          jobs,
          lastJobEventTimestamp: changed
            ? Date.now()
            : current.lastJobEventTimestamp,
        };
      });
    },
    (error) => patch({ error }),
  );

  React.useEffect(() => {
    void refreshCandidates().catch((error) =>
      patch({ error: errorMessage(error) }),
    );
  }, [state.lastJobEventTimestamp, refreshCandidates]);

  React.useEffect(() => {
    if (!state.selectedProjectId) return;
    void api
      .listEpisodes(state.selectedProjectId)
      .then((episodes) => patch({ episodes }))
      .catch((error) => patch({ error: errorMessage(error) }));
  }, [state.lastJobEventTimestamp, state.selectedProjectId]);

  const value: StudioContextValue = {
    ...state,
    setSelectedProjectId: (selectedProjectId) => {
      localStorage.setItem("synthpost.project", selectedProjectId);
      localStorage.removeItem("synthpost.episode");
      localStorage.removeItem("synthpost.story");
      patch({
        selectedProjectId,
        selectedEpisodeId: "",
        selectedStoryId: "",
        episodes: [],
        candidates: [],
      });
      void (async () => {
        try {
          const episodes = selectedProjectId
            ? await api.listEpisodes(selectedProjectId)
            : [];
          const selectedEpisodeId = episodes[0]?.episode_id || "";
          const candidates = await api.listCandidates({
            episodeId: selectedEpisodeId || undefined,
          });
          if (selectedEpisodeId) {
            localStorage.setItem("synthpost.episode", selectedEpisodeId);
          }
          patch({ episodes, candidates, selectedEpisodeId });
        } catch (error) {
          patch({
            error: errorMessage(error),
          });
        }
      })();
    },
    setSelectedEpisodeId: (selectedEpisodeId) => {
      localStorage.setItem("synthpost.episode", selectedEpisodeId);
      localStorage.removeItem("synthpost.story");
      patch({ selectedEpisodeId, selectedStoryId: "", candidates: [] });
      void (async () => {
        try {
          const candidates = await api.listCandidates({
            episodeId: selectedEpisodeId || undefined,
          });
          patch({ candidates });
        } catch (error) {
          patch({
            error: errorMessage(error),
          });
        }
      })();
    },
    setSelectedStoryId: (selectedStoryId) => {
      localStorage.setItem("synthpost.story", selectedStoryId);
      patch({ selectedStoryId });
    },
    setError: (error) => patch({ error }),
    refreshAll,
    refreshJobs,
    refreshCandidates,
  };

  return (
    <StudioContext.Provider value={value}>{children}</StudioContext.Provider>
  );
};

export const useStudio = (): StudioContextValue => {
  const value = React.useContext(StudioContext);
  if (!value) {
    throw new Error("useStudio must be used inside StudioProvider");
  }
  return value;
};
