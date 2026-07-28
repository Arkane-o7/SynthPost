import React from "react";
import { api } from "../api/client";
import { errorMessage } from "../api/http";
import {
  channelPresentation,
  isChannelId,
} from "../channels";
import { useJobEvents } from "./useJobEvents";
import type {
  ChannelId,
  ChannelProfile,
  Episode,
  Project,
  RenderJob,
  SourceDefinition,
  StoryCandidate,
} from "../contracts";

const DEFAULT_CHANNEL_ID: ChannelId = "synthpost";
const ACTIVE_CHANNEL_KEY = "synthea.channel";
type SelectionKind = "project" | "episode" | "story";

const selectionKey = (channelId: ChannelId, kind: SelectionKind) =>
  `synthea.channel.${channelId}.${kind}`;

const storedSelection = (channelId: ChannelId, kind: SelectionKind) => {
  const key = selectionKey(channelId, kind);
  const current = localStorage.getItem(key);
  if (current !== null) return current;
  if (channelId !== "synthpost") return "";

  const legacy = localStorage.getItem(`synthpost.${kind}`) ?? "";
  if (legacy) localStorage.setItem(key, legacy);
  return legacy;
};

const persistSelection = (
  channelId: ChannelId,
  kind: SelectionKind,
  value: string,
) => {
  const key = selectionKey(channelId, kind);
  if (value) localStorage.setItem(key, value);
  else localStorage.removeItem(key);
};

const initialChannelId = (): ChannelId => {
  const stored = localStorage.getItem(ACTIVE_CHANNEL_KEY);
  return isChannelId(stored) ? stored : DEFAULT_CHANNEL_ID;
};

type StudioState = {
  channels: ChannelProfile[];
  selectedChannelId: ChannelId;
  selectedChannelProfile: ChannelProfile | null;
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
  switchChannel: (channelId: ChannelId) => Promise<void>;
  setSelectedProjectId: (value: string) => void;
  setSelectedEpisodeId: (value: string) => void;
  openEpisode: (projectId: string, episodeId: string) => Promise<void>;
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
  const channelId = React.useMemo(initialChannelId, []);
  const [state, setState] = React.useState<StudioState>({
    channels: [],
    selectedChannelId: channelId,
    selectedChannelProfile: null,
    projects: [],
    episodes: [],
    sources: [],
    candidates: [],
    jobs: [],
    selectedProjectId: storedSelection(channelId, "project"),
    selectedEpisodeId: storedSelection(channelId, "episode"),
    selectedStoryId: storedSelection(channelId, "story"),
    error: "",
    loading: true,
    lastJobEventTimestamp: Date.now(),
  });
  const stateRef = React.useRef(state);
  const loadGenerationRef = React.useRef(0);
  const selectionGenerationRef = React.useRef(0);

  React.useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const patch = React.useCallback((partial: Partial<StudioState>) => {
    setState((current) => {
      const next = { ...current, ...partial };
      stateRef.current = next;
      return next;
    });
  }, []);

  const loadChannel = React.useCallback(
    async (requestedChannelId: ChannelId, clearSnapshot: boolean) => {
      const generation = ++loadGenerationRef.current;
      selectionGenerationRef.current += 1;
      if (clearSnapshot) {
        patch({
          selectedChannelId: requestedChannelId,
          selectedChannelProfile:
            stateRef.current.channels.find(
              (profile) => profile.channel_id === requestedChannelId,
            ) ?? null,
          projects: [],
          episodes: [],
          sources: [],
          candidates: [],
          jobs: [],
          selectedProjectId: "",
          selectedEpisodeId: "",
          selectedStoryId: "",
          loading: true,
          error: "",
        });
      } else {
        patch({ loading: true, error: "" });
      }

      try {
        const knownChannels = stateRef.current.channels;
        const [channels, allProjects, sources, allJobs] = await Promise.all([
          knownChannels.length ? Promise.resolve(knownChannels) : api.listChannels(),
          api.listProjects(requestedChannelId),
          api.listSources(),
          api.listJobs({ channelId: requestedChannelId }),
        ]);
        if (generation !== loadGenerationRef.current) return;

        const projects = allProjects.filter(
          (project) => project.channel_id === requestedChannelId,
        );
        const jobs = allJobs.filter(
          (job) => job.channel_id === requestedChannelId,
        );
        const requestedProjectId = storedSelection(requestedChannelId, "project");
        const selectedProjectId = projects.some(
          (project) => project.project_id === requestedProjectId,
        )
          ? requestedProjectId
          : projects[0]?.project_id || "";
        const allEpisodes = selectedProjectId
          ? await api.listEpisodes(selectedProjectId)
          : [];
        if (generation !== loadGenerationRef.current) return;
        const episodes = allEpisodes.filter(
          (episode) => episode.channel_id === requestedChannelId,
        );
        const requestedEpisodeId = storedSelection(requestedChannelId, "episode");
        const selectedEpisodeId = episodes.some(
          (episode) => episode.episode_id === requestedEpisodeId,
        )
          ? requestedEpisodeId
          : episodes[0]?.episode_id || "";
        const allCandidates = await api.listCandidates({
          channelId: requestedChannelId,
          episodeId: selectedEpisodeId || undefined,
        });
        if (generation !== loadGenerationRef.current) return;
        const candidates = allCandidates.filter(
          (candidate) => candidate.channel_id === requestedChannelId,
        );
        const requestedStoryId = storedSelection(requestedChannelId, "story");
        const selectedStoryId = candidates.some(
          (candidate) => candidate.story_id === requestedStoryId,
        )
          ? requestedStoryId
          : candidates.find(
              (candidate) => candidate.selection_status === "selected",
            )?.story_id || "";

        persistSelection(requestedChannelId, "project", selectedProjectId);
        persistSelection(requestedChannelId, "episode", selectedEpisodeId);
        persistSelection(requestedChannelId, "story", selectedStoryId);
        patch({
          channels,
          selectedChannelId: requestedChannelId,
          selectedChannelProfile:
            channels.find(
              (profile) => profile.channel_id === requestedChannelId,
            ) ?? null,
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
        if (generation !== loadGenerationRef.current) return;
        patch({ error: errorMessage(error), loading: false });
      }
    },
    [patch],
  );

  const refreshAll = React.useCallback(
    () => loadChannel(stateRef.current.selectedChannelId, false),
    [loadChannel],
  );

  React.useEffect(() => {
    localStorage.setItem(ACTIVE_CHANNEL_KEY, channelId);
    void loadChannel(channelId, false);
  }, [channelId, loadChannel]);

  const activeIdentity = channelPresentation(
    state.selectedChannelId,
    state.selectedChannelProfile,
  );

  React.useEffect(() => {
    const root = document.documentElement;
    root.dataset.channel = state.selectedChannelId;
    root.style.setProperty("--channel-accent", activeIdentity.accent);
    root.style.setProperty("--channel-accent-hover", activeIdentity.accentHover);
    root.style.setProperty("--channel-accent-soft", activeIdentity.accentSoft);
    root.style.setProperty("--channel-accent-glow", activeIdentity.accentGlow);
  }, [
    activeIdentity.accent,
    activeIdentity.accentGlow,
    activeIdentity.accentHover,
    activeIdentity.accentSoft,
    state.selectedChannelId,
  ]);

  useJobEvents(
    state.selectedChannelId,
    activeIdentity.name,
    (incomingJobs) => {
      setState((current) => {
        const jobs = incomingJobs.filter(
          (job) => job.channel_id === current.selectedChannelId,
        );
        const changed = jobs.some((newJob) => {
          const oldJob = current.jobs.find((job) => job.job_id === newJob.job_id);
          return (
            oldJob &&
            oldJob.status !== newJob.status &&
            ["completed", "failed"].includes(newJob.status)
          );
        });
        const next = {
          ...current,
          jobs,
          lastJobEventTimestamp: changed
            ? Date.now()
            : current.lastJobEventTimestamp,
        };
        stateRef.current = next;
        return next;
      });
    },
    (error) => patch({ error }),
  );

  const refreshJobs = React.useCallback(async () => {
    const currentChannelId = stateRef.current.selectedChannelId;
    const jobs = await api.listJobs({ channelId: currentChannelId });
    if (currentChannelId !== stateRef.current.selectedChannelId) return;
    patch({ jobs: jobs.filter((job) => job.channel_id === currentChannelId) });
  }, [patch]);

  const refreshCandidates = React.useCallback(async () => {
    const snapshot = stateRef.current;
    const allCandidates = await api.listCandidates({
      channelId: snapshot.selectedChannelId,
      episodeId: snapshot.selectedEpisodeId || undefined,
    });
    if (snapshot.selectedChannelId !== stateRef.current.selectedChannelId) return;
    patch({
      candidates: allCandidates.filter(
        (candidate) => candidate.channel_id === snapshot.selectedChannelId,
      ),
    });
  }, [patch]);

  React.useEffect(() => {
    void refreshCandidates().catch((error) => patch({ error: errorMessage(error) }));
  }, [state.lastJobEventTimestamp, refreshCandidates, patch]);

  React.useEffect(() => {
    if (!state.selectedProjectId) return;
    const requestedChannelId = state.selectedChannelId;
    void api
      .listEpisodes(state.selectedProjectId)
      .then((episodes) => {
        if (requestedChannelId !== stateRef.current.selectedChannelId) return;
        patch({
          episodes: episodes.filter(
            (episode) => episode.channel_id === requestedChannelId,
          ),
        });
      })
      .catch((error) => patch({ error: errorMessage(error) }));
  }, [
    state.lastJobEventTimestamp,
    state.selectedChannelId,
    state.selectedProjectId,
    patch,
  ]);

  const switchChannel = React.useCallback(
    async (nextChannelId: ChannelId) => {
      if (nextChannelId === stateRef.current.selectedChannelId) return;
      localStorage.setItem(ACTIVE_CHANNEL_KEY, nextChannelId);
      await loadChannel(nextChannelId, true);
    },
    [loadChannel],
  );

  const value: StudioContextValue = {
    ...state,
    switchChannel,
    setSelectedProjectId: (selectedProjectId) => {
      const selectedChannelId = stateRef.current.selectedChannelId;
      const generation = ++selectionGenerationRef.current;
      persistSelection(selectedChannelId, "project", selectedProjectId);
      persistSelection(selectedChannelId, "episode", "");
      persistSelection(selectedChannelId, "story", "");
      patch({
        selectedProjectId,
        selectedEpisodeId: "",
        selectedStoryId: "",
        episodes: [],
        candidates: [],
      });
      void (async () => {
        try {
          const allEpisodes = selectedProjectId
            ? await api.listEpisodes(selectedProjectId)
            : [];
          if (
            generation !== selectionGenerationRef.current ||
            selectedChannelId !== stateRef.current.selectedChannelId
          ) return;
          const episodes = allEpisodes.filter(
            (episode) => episode.channel_id === selectedChannelId,
          );
          const selectedEpisodeId = episodes[0]?.episode_id || "";
          const allCandidates = await api.listCandidates({
            channelId: selectedChannelId,
            episodeId: selectedEpisodeId || undefined,
          });
          if (
            generation !== selectionGenerationRef.current ||
            selectedChannelId !== stateRef.current.selectedChannelId
          ) return;
          const candidates = allCandidates.filter(
            (candidate) => candidate.channel_id === selectedChannelId,
          );
          const selectedStoryId =
            candidates.find(
              (candidate) => candidate.selection_status === "selected",
            )?.story_id || "";
          persistSelection(selectedChannelId, "episode", selectedEpisodeId);
          persistSelection(selectedChannelId, "story", selectedStoryId);
          patch({ episodes, candidates, selectedEpisodeId, selectedStoryId });
        } catch (error) {
          patch({ error: errorMessage(error) });
        }
      })();
    },
    setSelectedEpisodeId: (selectedEpisodeId) => {
      const selectedChannelId = stateRef.current.selectedChannelId;
      const generation = ++selectionGenerationRef.current;
      persistSelection(selectedChannelId, "episode", selectedEpisodeId);
      persistSelection(selectedChannelId, "story", "");
      patch({ selectedEpisodeId, selectedStoryId: "", candidates: [] });
      void (async () => {
        try {
          const allCandidates = await api.listCandidates({
            channelId: selectedChannelId,
            episodeId: selectedEpisodeId || undefined,
          });
          if (
            generation !== selectionGenerationRef.current ||
            selectedChannelId !== stateRef.current.selectedChannelId
          ) return;
          const candidates = allCandidates.filter(
            (candidate) => candidate.channel_id === selectedChannelId,
          );
          const selectedStoryId =
            candidates.find(
              (candidate) => candidate.selection_status === "selected",
            )?.story_id || "";
          persistSelection(selectedChannelId, "story", selectedStoryId);
          patch({ candidates, selectedStoryId });
        } catch (error) {
          patch({ error: errorMessage(error) });
        }
      })();
    },
    openEpisode: async (selectedProjectId, selectedEpisodeId) => {
      const selectedChannelId = stateRef.current.selectedChannelId;
      const generation = ++selectionGenerationRef.current;
      const [allEpisodes, allCandidates] = await Promise.all([
        api.listEpisodes(selectedProjectId),
        api.listCandidates({
          channelId: selectedChannelId,
          episodeId: selectedEpisodeId,
        }),
      ]);
      if (
        generation !== selectionGenerationRef.current ||
        selectedChannelId !== stateRef.current.selectedChannelId
      ) return;
      const episodes = allEpisodes.filter(
        (episode) => episode.channel_id === selectedChannelId,
      );
      const candidates = allCandidates.filter(
        (candidate) => candidate.channel_id === selectedChannelId,
      );
      if (!episodes.some((episode) => episode.episode_id === selectedEpisodeId)) {
        throw new Error("That episode no longer exists in this channel.");
      }
      const selectedStoryId =
        candidates.find(
          (candidate) => candidate.selection_status === "selected",
        )?.story_id || "";
      persistSelection(selectedChannelId, "project", selectedProjectId);
      persistSelection(selectedChannelId, "episode", selectedEpisodeId);
      persistSelection(selectedChannelId, "story", selectedStoryId);
      patch({
        selectedProjectId,
        selectedEpisodeId,
        selectedStoryId,
        episodes,
        candidates,
      });
    },
    setSelectedStoryId: (selectedStoryId) => {
      persistSelection(stateRef.current.selectedChannelId, "story", selectedStoryId);
      patch({ selectedStoryId });
    },
    setError: (error) => patch({ error }),
    refreshAll,
    refreshJobs,
    refreshCandidates,
  };

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
};

export const useStudio = (): StudioContextValue => {
  const value = React.useContext(StudioContext);
  if (!value) throw new Error("useStudio must be used inside StudioProvider");
  return value;
};
