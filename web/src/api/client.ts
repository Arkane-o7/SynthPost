import type {
  Episode,
  Project,
  RenderJob,
  ResearchPack,
  ScriptDocument,
  SourceDefinition,
  StoryCandidate,
  TimelinePlan,
  VisualCandidate,
} from "../contracts";

export const API_BASE = "";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof Uint8Array
        ? {}
        : { "Content-Type": "application/json" }),
      ...(options.headers ?? {}),
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message =
      typeof body === "object" && body && "error" in body
        ? String((body as { error?: { message?: string } }).error?.message)
        : response.statusText;
    throw new ApiError(response.status, message, body);
  }
  return body as T;
}

export const api = {
  health: () =>
    request<{ ok: boolean; name: string; version: string }>("/api/health"),
  templates: () => request<Array<Record<string, unknown>>>("/api/templates"),

  listProjects: () => request<Project[]>("/api/projects"),
  createProject: (title: string) =>
    request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  updateProject: (projectId: string, patch: Partial<Project>) =>
    request<Project>(`/api/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  listEpisodes: (projectId?: string) =>
    request<Episode[]>(
      `/api/episodes${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
    ),
  createEpisode: (
    projectId: string,
    title: string,
    renderProfile = "preview",
  ) =>
    request<Episode>(`/api/projects/${projectId}/episodes`, {
      method: "POST",
      body: JSON.stringify({ title, render_profile: renderProfile }),
    }),
  readEpisode: (episodeId: string) =>
    request<Episode>(`/api/episodes/${episodeId}`),
  updateEpisode: (episodeId: string, patch: Partial<Episode>) =>
    request<Episode>(`/api/episodes/${episodeId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  listSources: () => request<SourceDefinition[]>("/api/sources"),
  createSource: (
    payload: Partial<SourceDefinition> & {
      name: string;
      source_type: SourceDefinition["source_type"];
    },
  ) =>
    request<SourceDefinition>("/api/sources", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSource: (sourceId: string, patch: Partial<SourceDefinition>) =>
    request<SourceDefinition>(`/api/sources/${sourceId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  testSource: (sourceId: string) =>
    request<{ ok: boolean; count: number; sample: StoryCandidate[] }>(
      `/api/sources/${sourceId}/test`,
      { method: "POST" },
    ),

  startDiscovery: (episodeId?: string, category?: string) =>
    request<RenderJob>("/api/discovery/start", {
      method: "POST",
      body: JSON.stringify({ episode_id: episodeId, category }),
    }),
  listCandidates: (
    params: {
      episodeId?: string;
      status?: string;
      category?: string;
      search?: string;
    } = {},
  ) => {
    const query = new URLSearchParams();
    if (params.episodeId) query.set("episode_id", params.episodeId);
    if (params.status) query.set("status", params.status);
    if (params.category) query.set("category", params.category);
    if (params.search) query.set("search", params.search);
    return request<StoryCandidate[]>(
      `/api/discovery/candidates${query.toString() ? `?${query}` : ""}`,
    );
  },
  selectCandidate: (candidateId: string, episodeId: string) =>
    request<StoryCandidate>(`/api/discovery/candidates/${candidateId}/select`, {
      method: "POST",
      body: JSON.stringify({ episode_id: episodeId }),
    }),
  rejectCandidate: (candidateId: string, reasons: string[] = []) =>
    request<StoryCandidate>(`/api/discovery/candidates/${candidateId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reasons }),
    }),
  addCustomTopic: (payload: {
    episode_id?: string;
    title: string;
    summary?: string;
    category?: string;
  }) =>
    request<StoryCandidate>("/api/discovery/custom-topic", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  addCustomUrl: (payload: {
    episode_id?: string;
    url: string;
    title?: string;
    summary?: string;
    category?: string;
  }) =>
    request<StoryCandidate>("/api/discovery/custom-url", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  addManualStory: (payload: {
    episode_id?: string;
    title: string;
    body: string;
    category?: string;
  }) =>
    request<StoryCandidate>("/api/discovery/manual-story", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  startResearch: (storyId: string) =>
    request<RenderJob>(`/api/stories/${storyId}/research/start`, {
      method: "POST",
    }),
  readResearch: (storyId: string) =>
    request<ResearchPack | null>(`/api/stories/${storyId}/research`),

  generateScript: (
    storyId: string,
    provider?: string,
    target_duration_seconds = 600,
  ) =>
    request<RenderJob>(`/api/stories/${storyId}/script/generate`, {
      method: "POST",
      body: JSON.stringify({ provider, target_duration_seconds }),
    }),
  readScript: (storyId: string, approved = false) =>
    request<ScriptDocument | null>(
      `/api/stories/${storyId}/script${approved ? "?approved=true" : ""}`,
    ),
  saveManualScript: (
    storyId: string,
    headline: string,
    text: string,
    category = "manual",
  ) =>
    request<ScriptDocument>(`/api/stories/${storyId}/script/manual`, {
      method: "POST",
      body: JSON.stringify({ headline, text, category }),
    }),
  approveScript: (storyId: string) =>
    request<ScriptDocument>(`/api/stories/${storyId}/script/approve`, {
      method: "POST",
    }),

  searchVisuals: (storyId: string) =>
    request<RenderJob>(`/api/stories/${storyId}/visuals/search`, {
      method: "POST",
    }),
  listVisuals: (storyId: string) =>
    request<VisualCandidate[]>(`/api/stories/${storyId}/visuals`),
  localVisualFolder: (storyId: string) =>
    request<{ project_id: string; episode_id: string; path: string }>(
      `/api/stories/${storyId}/visuals/local-folder`,
    ),
  stageLocalVisual: (
    storyId: string,
    payload: {
      path: string;
      title?: string;
      section_ids?: string[];
      content_role?: string;
      rights_tier?: string;
    },
  ) =>
    request<VisualCandidate>(`/api/stories/${storyId}/visuals/stage-local`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  uploadVisual: async (storyId: string, file: File) => {
    const bytes = new Uint8Array(await file.arrayBuffer());
    return request<VisualCandidate>(
      `/api/stories/${storyId}/visuals/upload-bytes?filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        body: bytes,
        headers: { "Content-Type": file.type || "application/octet-stream" },
      },
    );
  },
  approveVisual: (assetId: string) =>
    request<VisualCandidate>(`/api/visuals/${assetId}/approve`, {
      method: "POST",
    }),
  analyzeVisual: (assetId: string) =>
    request<VisualCandidate>(`/api/visuals/${assetId}/analyze`, {
      method: "POST",
    }),
  downloadVisual: (assetId: string) =>
    request<VisualCandidate>(`/api/visuals/${assetId}/download`, {
      method: "POST",
    }),
  manualApproveVisual: (assetId: string, attribution_text?: string) =>
    request<VisualCandidate>(`/api/visuals/${assetId}/manual-approve`, {
      method: "POST",
      body: JSON.stringify({ attribution_text }),
    }),
  rejectVisual: (assetId: string) =>
    request<VisualCandidate>(`/api/visuals/${assetId}/reject`, {
      method: "POST",
    }),
  updateVisual: (assetId: string, patch: Partial<VisualCandidate>) =>
    request<VisualCandidate>(`/api/visuals/${assetId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  generateTimeline: (storyId: string) =>
    request<TimelinePlan>(`/api/stories/${storyId}/timeline/generate`, {
      method: "POST",
    }),
  readTimeline: (storyId: string, approved = false) =>
    request<TimelinePlan | null>(
      `/api/stories/${storyId}/timeline${approved ? "?approved=true" : ""}`,
    ),
  saveTimeline: (storyId: string, timeline: TimelinePlan) =>
    request<TimelinePlan>(`/api/stories/${storyId}/timeline/save`, {
      method: "POST",
      body: JSON.stringify(timeline),
    }),
  validateTimeline: (storyId: string, timeline?: TimelinePlan) =>
    request<{ ok: boolean; errors: string[]; warnings: string[] }>(
      `/api/stories/${storyId}/timeline/validate`,
      { method: "POST", body: JSON.stringify(timeline ?? null) },
    ),
  approveTimeline: (storyId: string) =>
    request<TimelinePlan>(`/api/stories/${storyId}/timeline/approve`, {
      method: "POST",
    }),

  buildManifest: (
    storyId: string,
    render_profile = "preview",
    test_mode = false,
  ) =>
    request<Record<string, unknown>>(`/api/stories/${storyId}/manifest/build`, {
      method: "POST",
      body: JSON.stringify({ render_profile, test_mode }),
    }),
  renderAvatar: (
    storyId: string,
    render_profile = "preview",
    test_mode = false,
  ) =>
    request<RenderJob>(`/api/stories/${storyId}/render/avatar`, {
      method: "POST",
      body: JSON.stringify({
        render_profile,
        test_mode,
        skip_avatar_render: false,
      }),
    }),
  renderStory: (
    storyId: string,
    render_profile = "preview",
    test_mode = false,
  ) =>
    request<RenderJob>(`/api/stories/${storyId}/render/story`, {
      method: "POST",
      body: JSON.stringify({
        render_profile,
        test_mode,
        // Preview/test renders are intentionally fast and placeholder-safe.
        // Production story renders should render/reuse the real avatar anchor.
        skip_avatar_render: test_mode || render_profile === "preview",
      }),
    }),
  assembleEpisode: (
    episodeId: string,
    render_profile = "preview",
    test_mode = false,
  ) =>
    request<RenderJob>(`/api/episodes/${episodeId}/assemble`, {
      method: "POST",
      body: JSON.stringify({ render_profile, test_mode }),
    }),
  revealEpisodeOutput: (episodeId: string) =>
    request<{ revealed: boolean; path: string }>(
      `/api/episodes/${episodeId}/reveal-output`,
      { method: "POST" },
    ),

  listJobs: (
    params: {
      storyId?: string;
      episodeId?: string;
      jobType?: string;
      limit?: number;
    } = {},
  ) => {
    const query = new URLSearchParams();
    if (params.storyId) query.set("story_id", params.storyId);
    if (params.episodeId) query.set("episode_id", params.episodeId);
    if (params.jobType) query.set("job_type", params.jobType);
    if (params.limit) query.set("limit", String(params.limit));
    return request<RenderJob[]>(
      `/api/jobs${query.toString() ? `?${query}` : ""}`,
    );
  },
  readJob: (jobId: string) => request<RenderJob>(`/api/jobs/${jobId}`),
  retryJob: (jobId: string) =>
    request<RenderJob>(`/api/jobs/${jobId}/retry`, { method: "POST" }),
  cancelJob: (jobId: string) =>
    request<RenderJob>(`/api/jobs/${jobId}/cancel`, { method: "POST" }),
  pauseJob: (jobId: string) =>
    request<RenderJob>(`/api/jobs/${jobId}/pause`, { method: "POST" }),
  resumeJob: (jobId: string) =>
    request<RenderJob>(`/api/jobs/${jobId}/resume`, { method: "POST" }),
  jobLogs: (jobId: string) => request<string>(`/api/jobs/${jobId}/logs`),
};

export const artifactUrl = (path?: string | null): string =>
  path ? `/api/artifacts/${path}` : "";
