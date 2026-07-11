import { bundle } from "@remotion/bundler";
import {
  renderMedia,
  renderStill,
  selectComposition,
} from "@remotion/renderer";
import fs from "node:fs/promises";
import fsSync from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import type {
  HeadlineItem,
  PublicMedia,
  StoryProps,
  TimedVisual,
  TimelineSegmentProps,
} from "./types";

type StoryManifest = Record<string, any>;

const rendererRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const projectRoot = path.resolve(rendererRoot, "..", "..");
const publicDir = path.join(rendererRoot, "public");

const videoExtensions = new Set([".mp4", ".mov", ".webm", ".mkv"]);
const templateToCompositionId: Record<string, string> = {
  split_main: "split-main",
  signal_desk_split: "split-main",
  broadcast_split_firstpost_style: "split-main",
  full_screen_anchor: "full-screen-anchor",
  fullscreen_anchor: "full-screen-anchor",
  news_full_screen_anchor: "full-screen-anchor",
  opening_anchor: "full-screen-anchor",
  closing_anchor: "full-screen-anchor",
  FullScreenNewsVisuals: "FullScreenNewsVisuals",
  full_screen_news_visuals: "FullScreenNewsVisuals",
  fullscreen_news_visuals: "FullScreenNewsVisuals",
  "full-screen-news-visuals": "FullScreenNewsVisuals",
  news_visuals_full_screen: "FullScreenNewsVisuals",
  source_clip_full_screen: "FullScreenNewsVisuals",
  timeline_story: "timeline-story",
  approved_timeline: "timeline-story",
};

const argPath = process.argv.find((arg) => arg.endsWith(".json"));
if (!argPath) {
  throw new Error(
    "Usage: npm run render:story -- /absolute/path/to/story.json",
  );
}

const force = process.argv.includes("--force");

const readJson = async <T>(filePath: string): Promise<T> => {
  return JSON.parse(await fs.readFile(filePath, "utf-8")) as T;
};

const writeJson = async (filePath: string, value: unknown) => {
  await fs.writeFile(filePath, JSON.stringify(value, null, 2) + "\n", "utf-8");
};

const exists = async (filePath: string): Promise<boolean> => {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
};

const sanitize = (value: string): string =>
  value.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "") || "asset";

const isRemote = (value: string): boolean => /^https?:\/\//i.test(value);

const publicPathFor = (absolutePath: string): string | null => {
  const relative = path.relative(publicDir, absolutePath);
  if (!relative.startsWith("..") && !path.isAbsolute(relative)) {
    return relative.split(path.sep).join("/");
  }
  return null;
};

const resolveInput = async (value: string): Promise<string | null> => {
  if (!value) {
    return null;
  }
  if (isRemote(value)) {
    return value;
  }
  const candidates = [
    path.isAbsolute(value) ? value : path.resolve(projectRoot, value),
    path.resolve(publicDir, value),
  ];
  for (const candidate of candidates) {
    if (await exists(candidate)) {
      return candidate;
    }
  }
  return null;
};

const createPlaceholderAnchor = async (destination: string): Promise<void> => {
  await fs.mkdir(path.dirname(destination), { recursive: true });
  const result = spawnSync(
    process.env.SYNTHPOST_FFMPEG || "ffmpeg",
    [
      "-hide_banner",
      "-loglevel",
      "warning",
      "-y",
      "-f",
      "lavfi",
      "-i",
      "color=c=#050A14:s=1920x1080:r=24:d=12",
      "-f",
      "lavfi",
      "-i",
      "anullsrc=r=48000:cl=stereo:d=12",
      "-vf",
      "drawbox=x=0:y=0:w=iw:h=ih:color=#071B33@0.92:t=fill,drawbox=x=120:y=120:w=1680:h=840:color=#0B1220@0.88:t=fill,drawbox=x=120:y=120:w=14:h=840:color=#D92D27@1:t=fill,drawbox=x=180:y=420:w=560:h=96:color=#18263A@1:t=fill,drawbox=x=180:y=555:w=900:h=52:color=#132033@1:t=fill,drawbox=x=180:y=640:w=1320:h=10:color=#284766@1:t=fill,drawbox=x=180:y=700:w=820:h=10:color=#1E70FF@0.85:t=fill",
      "-shortest",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-c:a",
      "aac",
      destination,
    ],
    { stdio: "inherit" },
  );
  if (result.status !== 0) {
    throw new Error("Could not create placeholder anchor with ffmpeg.");
  }
};

const stageMedia = async (
  value: string,
  generatedDir: string,
  fallbackPublicPath: string | undefined,
  required: boolean,
): Promise<PublicMedia> => {
  if (isRemote(value)) {
    const ext = path.extname(new URL(value).pathname).toLowerCase();
    return {
      publicPath: value,
      kind: videoExtensions.has(ext) ? "video" : "image",
      remote: true,
    };
  }

  const resolved = await resolveInput(value);
  if (!resolved) {
    if (required && process.env.SYNTHPOST_ALLOW_PLACEHOLDER_ANCHOR === "1") {
      const placeholder = path.join(generatedDir, "anchor-placeholder.mp4");
      await createPlaceholderAnchor(placeholder);
      return {
        publicPath: publicPathFor(placeholder) ?? "",
        absolutePath: placeholder,
        kind: "video",
      };
    }
    if (fallbackPublicPath) {
      return {
        publicPath: fallbackPublicPath,
        absolutePath: path.join(publicDir, fallbackPublicPath),
        kind: videoExtensions.has(
          path.extname(fallbackPublicPath).toLowerCase(),
        )
          ? "video"
          : "image",
      };
    }
    throw new Error(`Required media was not found: ${value}`);
  }

  const alreadyPublic = publicPathFor(resolved);
  const ext = path.extname(resolved).toLowerCase();
  if (alreadyPublic) {
    return {
      publicPath: alreadyPublic,
      absolutePath: resolved,
      kind: videoExtensions.has(ext) ? "video" : "image",
    };
  }

  await fs.mkdir(generatedDir, { recursive: true });
  const staged = path.join(generatedDir, sanitize(path.basename(resolved)));
  if (force || !(await exists(staged))) {
    await fs.copyFile(resolved, staged);
  }
  return {
    publicPath: publicPathFor(staged) ?? "",
    absolutePath: staged,
    kind: videoExtensions.has(ext) ? "video" : "image",
  };
};

const formatDate = (value: string | undefined): string => {
  if (!value) {
    return "JUNE 20";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value.toUpperCase();
  }
  return parsed
    .toLocaleDateString("en-US", { month: "long", day: "numeric" })
    .toUpperCase();
};

const providerLabel = (value: unknown): string => {
  const raw = String(value ?? "")
    .replace(/^source:\s*/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!raw) {
    return "";
  }
  const normalized = raw.toLowerCase();
  if (
    [
      "local",
      "local upload",
      "local media",
      "user provided local media",
    ].includes(normalized)
  ) {
    return "SYNTHPOST";
  }
  if (normalized === "nasa") {
    return "NASA";
  }
  if (normalized === "dvids") {
    return "DVIDS";
  }
  if (normalized.includes("wikimedia")) {
    return "WIKIMEDIA COMMONS";
  }
  return raw.toUpperCase();
};

const visualSourceLabel = (...values: unknown[]): string => {
  for (const value of values) {
    const label = providerLabel(value);
    if (label) {
      return label;
    }
  }
  return "SYNTHPOST";
};

const headlineCueItems = (value: unknown): HeadlineItem[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item): HeadlineItem | null => {
      if (typeof item === "string") {
        return { text: compactHeadline(item) };
      }
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        const text = compactHeadline(
          record.text ?? record.headline ?? record.title,
        );
        if (!text) {
          return null;
        }
        const start = Number(record.start);
        const end = Number(record.end);
        return {
          text,
          start: Number.isFinite(start) ? start : undefined,
          end:
            Number.isFinite(end) && (!Number.isFinite(start) || end > start)
              ? end
              : undefined,
        };
      }
      return null;
    })
    .filter(
      (item): item is HeadlineItem => item !== null && Boolean(item.text),
    );
};

const compactHeadline = (value: unknown): string => {
  const cleaned = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[.。]+$/g, "");
  if (cleaned.length <= 98) {
    return cleaned.toUpperCase();
  }
  return cleaned
    .slice(0, 97)
    .replace(/\s+\S*$/, "")
    .toUpperCase();
};

const buildHeadlineItems = (manifest: StoryManifest): HeadlineItem[] => {
  const compositionManifest = manifest.composition ?? {};
  const script = manifest.script ?? {};
  const raw = manifest.raw ?? {};
  const configured = [
    ...headlineCueItems(compositionManifest.headlines),
    ...headlineCueItems(manifest.chyrons),
    ...headlineCueItems(manifest.headlines),
  ];
  const seen = new Set<string>();
  const headlines: HeadlineItem[] = [];
  for (const candidate of configured) {
    if (!candidate.text || seen.has(candidate.text)) {
      continue;
    }
    seen.add(candidate.text);
    headlines.push(candidate);
    if (headlines.length >= 5) {
      break;
    }
  }
  if (headlines.length) {
    return headlines;
  }

  const fallbackCandidates = [
    script.headline,
    raw.headline_source,
    ...(Array.isArray(raw.facts) ? raw.facts : []),
  ];
  for (const candidate of fallbackCandidates) {
    const text = compactHeadline(candidate);
    if (!text || seen.has(text)) {
      continue;
    }
    seen.add(text);
    headlines.push({ text });
    if (headlines.length >= 5) {
      break;
    }
  }
  return headlines.length ? headlines : [{ text: "SYNTHPOST BRIEFING" }];
};

const timelineSegmentProps = async (
  manifest: StoryManifest,
  generatedDir: string,
): Promise<TimelineSegmentProps[]> => {
  const plan = manifest.approved_timeline ?? manifest.timeline_plan;
  if (!plan || plan.status !== "approved" || !Array.isArray(plan.segments)) {
    return [];
  }
  const segments: TimelineSegmentProps[] = [];
  for (const segment of plan.segments) {
    const visualRef = segment.visual ?? {};
    const assetId = String(visualRef.asset_id ?? "");
    if (assetId) {
      if (visualRef.rights_tier === "red") {
        throw new Error(
          `Approved timeline contains blocked red-tier visual: ${assetId}`,
        );
      }
      if (
        visualRef.rights_tier === "yellow" &&
        visualRef.review_status !== "manual_approved"
      ) {
        throw new Error(
          `Approved timeline contains yellow-tier visual without manual approval: ${assetId}`,
        );
      }
      if (
        !["approved", "manual_approved"].includes(
          String(visualRef.review_status),
        )
      ) {
        throw new Error(
          `Approved timeline contains unapproved visual: ${assetId}`,
        );
      }
    }
    const visualPath = String(visualRef.path ?? "");
    const trimStart = Number(visualRef.trim_start);
    const trimEnd = Number(visualRef.trim_end);
    const staged = assetId
      ? await stageMedia(
          visualPath,
          generatedDir,
          "placeholders/news-visual-placeholder.svg",
          false,
        )
      : undefined;
    const start = Number(segment.start_time ?? 0);
    const end = Number(
      segment.end_time ?? start + Number(segment.duration ?? 1),
    );
    const visual = staged
      ? {
          ...staged,
          start,
          end,
          fit:
            visualRef.fit ??
            (String(visualRef.source ?? visualRef.provider) ===
            "generated_visual_card"
              ? ("contain" as const)
              : ("cover" as const)),
          sourceLabel: visualSourceLabel(
            visualRef.attribution_text,
            visualRef.attribution,
            visualRef.source_label,
            visualRef.source_name,
            visualRef.source,
            visualRef.provider,
            visualRef.source_domain,
          ),
          audio:
            visualRef.audio_mode === "original" ||
            visualRef.audio_mode === "mixed",
          hasAudio:
            visualRef.has_audio === undefined || visualRef.has_audio === null
              ? undefined
              : Boolean(visualRef.has_audio),
          volume: visualRef.audio_mode === "mixed" ? 0.45 : 1,
          mediaType: visualRef.media_type,
          contentRole: visualRef.content_role,
          candidateId: assetId,
          sectionId: visualRef.section_id ?? segment.section_id,
          sectionType: visualRef.section_type,
          visualRole: visualRef.visual_role,
          sourceUrl: visualRef.source_url,
          sourceDomain: visualRef.source_domain,
          provider: visualRef.provider,
          license: visualRef.license,
          attributionText: visualRef.attribution_text ?? visualRef.attribution,
          rightsCategory: visualRef.rights_category,
          manualReviewFlag: Boolean(
            visualRef.manual_review_flag ?? visualRef.needs_manual_review,
          ),
          fallbackStatus: visualRef.fallback_status,
          fallbackReason: visualRef.fallback_reason,
          warnings: Array.isArray(visualRef.warnings)
            ? visualRef.warnings.map(String)
            : undefined,
          visualSkillType: visualRef.visual_skill_type ?? visualRef.skill_type,
          visualSkill: visualRef.visual_skill,
          skillPlaceholder: visualRef.skill_placeholder,
          renderSafetyStatus: visualRef.render_safety_status,
          motion: visualRef.motion,
          trimStart: Number.isFinite(trimStart) ? trimStart : undefined,
          trimEnd: Number.isFinite(trimEnd) ? trimEnd : undefined,
        }
      : undefined;
    segments.push({
      segmentId: String(segment.segment_id),
      sectionId: String(segment.section_id),
      start,
      end,
      duration: Math.max(0.01, Number(segment.duration ?? end - start)),
      scriptText: String(segment.script_text ?? ""),
      anchor: {
        visible: Boolean(segment.anchor?.visible),
        speaking: Boolean(segment.anchor?.speaking),
        camera: String(segment.anchor?.camera ?? "medium"),
      },
      visual,
      template: {
        templateId: String(segment.template?.template_id ?? "fallback_anchor"),
        layout: String(segment.template?.layout ?? ""),
      },
      audio: {
        mode: segment.audio?.mode,
        narrationVolume: Number(segment.audio?.narration_volume ?? 1),
        sourceVolume: Number(segment.audio?.source_volume ?? 0),
        ducking: Boolean(segment.audio?.ducking),
      },
      overlays: {
        lowerThird: String(segment.overlays?.lower_third ?? ""),
        chyron: String(segment.overlays?.chyron ?? ""),
        attribution: String(segment.overlays?.attribution ?? ""),
        quoteText: String(segment.overlays?.quote_text ?? ""),
        documentSource: String(segment.overlays?.document_source ?? ""),
        data: segment.overlays?.data,
      },
    });
  }
  return segments;
};

const resolvePreviewPath = (
  outputPath: string,
  configured: unknown,
): string => {
  if (!configured) {
    return path.resolve(path.dirname(outputPath), "preview.png");
  }
  const value = String(configured);
  if (path.isAbsolute(value)) {
    return value;
  }
  if (value.includes("/") || value.includes("\\")) {
    return path.resolve(projectRoot, value);
  }
  return path.resolve(path.dirname(outputPath), value);
};

const main = async () => {
  const storyPath = path.resolve(argPath);
  const manifest = await readJson<StoryManifest>(storyPath);
  const storyId = String(manifest.story_id);
  const episodeId = String(manifest.episode_id);
  const generatedDir = path.join(publicDir, "generated", episodeId, storyId);
  await fs.mkdir(generatedDir, { recursive: true });

  const direction = manifest.direction ?? {};
  const compositionManifest = manifest.composition ?? {};
  const runtime = manifest.runtime ?? {};
  const profileSettings = runtime.render_profile_settings ?? {};
  const script = manifest.script ?? {};
  const raw = manifest.raw ?? {};
  const timelineSegments = await timelineSegmentProps(manifest, generatedDir);
  const templateName = String(
    compositionManifest.template ??
      (timelineSegments.length ? "timeline_story" : "split_main"),
  );
  const compositionId = timelineSegments.length
    ? "timeline-story"
    : (templateToCompositionId[templateName] ?? templateName);
  const visualOnlyTemplate = compositionId === "FullScreenNewsVisuals";

  const anchorPath = String(direction.anchor_output_path ?? "");
  const anchor =
    anchorPath || !visualOnlyTemplate
      ? await stageMedia(anchorPath, generatedDir, undefined, true)
      : undefined;

  const visuals: TimedVisual[] = [];
  const visualRecords =
    Array.isArray(manifest.compositor_visuals) &&
    manifest.compositor_visuals.length
      ? manifest.compositor_visuals
      : Array.isArray(manifest.visuals)
        ? manifest.visuals
        : [];
  for (const visual of visualRecords) {
    const visualPath = String(
      visual.path ??
        visual.downloaded_path ??
        visual.asset_url ??
        visual.remote_url ??
        "",
    );
    const staged = await stageMedia(
      visualPath,
      generatedDir,
      "placeholders/news-visual-placeholder.svg",
      false,
    );
    visuals.push({
      ...staged,
      start: Number(visual.start ?? 0),
      end: Number(visual.end ?? direction.estimated_duration_seconds ?? 30),
      fit: visual.fit ?? "cover",
      sourceLabel: visualSourceLabel(
        visual.attribution_text,
        visual.attribution,
        visual.sourceLabel,
        visual.source_label,
        visual.source_name,
        visual.source,
        visual.provider,
        visual.source_domain,
      ),
      audio:
        visual.audio === undefined && visual.play_audio === undefined
          ? undefined
          : Boolean(visual.audio ?? visual.play_audio),
      hasAudio:
        visual.has_audio === undefined || visual.has_audio === null
          ? undefined
          : Boolean(visual.has_audio),
      volume: Number.isFinite(Number(visual.volume))
        ? Number(visual.volume)
        : undefined,
      mediaType: visual.media_type,
      contentRole: visual.content_role,
      candidateId: visual.candidate_id ?? visual.asset_id,
      planId: visual.plan_id,
      sectionId: visual.section_id ?? visual.segment_id,
      sectionType: visual.section_type,
      visualRole: visual.visual_role,
      sourceUrl: visual.source_url,
      sourceDomain: visual.source_domain,
      provider: visual.provider,
      license: visual.license,
      attributionText: visual.attribution_text ?? visual.attribution,
      rightsCategory: visual.rights_category,
      manualReviewFlag: Boolean(
        visual.manual_review_flag ?? visual.needs_manual_review,
      ),
      fallbackStatus: visual.fallback_status,
      fallbackReason: visual.fallback_reason,
      warnings: Array.isArray(visual.warnings)
        ? visual.warnings.map(String)
        : undefined,
      visualSkillType: visual.visual_skill_type ?? visual.skill_type,
      visualSkill: visual.visual_skill,
      skillPlaceholder: visual.skill_placeholder,
      renderSafetyStatus: visual.render_safety_status,
      motion: visual.motion,
    });
  }
  if (!visuals.length) {
    const fallback = await stageMedia(
      "",
      generatedDir,
      "placeholders/news-visual-placeholder.svg",
      false,
    );
    visuals.push({ ...fallback, start: 0, end: 30, fit: "cover" });
  }

  const logoCandidates = ["synthpost_bug.svg", "synthpost_bug.png"];
  const logoFile = logoCandidates.find((fileName) =>
    fsSync.existsSync(path.join(publicDir, "brand", fileName)),
  );
  const logo = logoFile
    ? {
        publicPath: `brand/${logoFile}`,
        absolutePath: path.join(publicDir, "brand", logoFile),
        kind: "image" as const,
      }
    : undefined;

  const props: StoryProps = {
    storyId,
    episodeId,
    fps: Number(direction.fps ?? profileSettings.fps ?? 24),
    width: Number(profileSettings.width ?? direction.resolution?.[0] ?? 1920),
    height: Number(profileSettings.height ?? direction.resolution?.[1] ?? 1080),
    durationSeconds: Number(
      compositionManifest.duration_seconds ??
        direction.estimated_duration_seconds ??
        visuals.reduce(
          (max, visual) => Math.max(max, Number(visual.end) || 0),
          0,
        ) ??
        30,
    ),
    headline: String(
      script.headline ?? raw.headline_source ?? "SYNTHPOST BRIEFING",
    ).toUpperCase(),
    headlineItems: buildHeadlineItems(manifest),
    category: String(script.category ?? raw.category ?? "NEWS").toUpperCase(),
    sourceLabel: String(raw.source_name ?? "SYNTHPOST").toUpperCase(),
    sourceDate: formatDate(raw.published_at),
    anchor,
    anchorChromaKey:
      String(direction.avatar_render_background ?? "").toLowerCase() ===
      "chroma_green",
    visuals,
    timelineSegments,
    points: (manifest.points ?? []).map((point: any) => ({
      text: String(point.text ?? "").toUpperCase(),
      start: Number(point.start ?? 0),
    })),
    logo,
  };

  const outputPath = path.resolve(
    projectRoot,
    String(
      compositionManifest.output_path ||
        path.join(
          path.dirname(path.relative(projectRoot, storyPath)),
          "composited.mp4",
        ),
    ),
  );
  const previewPath = resolvePreviewPath(
    outputPath,
    compositionManifest.preview_path,
  );
  await fs.mkdir(path.dirname(outputPath), { recursive: true });

  const serveUrl = await bundle({
    entryPoint: path.join(rendererRoot, "src", "Root.tsx"),
  });
  const composition = await selectComposition({
    serveUrl,
    id: compositionId,
    inputProps: props,
  });

  await renderStill({
    serveUrl,
    composition,
    inputProps: props,
    output: previewPath,
    frame: Math.min(
      Number(process.env.SYNTHPOST_RENDER_PREVIEW_FRAME ?? 240),
      composition.durationInFrames - 1,
    ),
  });

  await renderMedia({
    serveUrl,
    composition,
    inputProps: props,
    codec: (process.env.SYNTHPOST_RENDER_CODEC as any) || "h264",
    outputLocation: outputPath,
  });

  manifest.composition = {
    ...compositionManifest,
    template: templateName,
    composition_id: compositionId,
    timeline_source: timelineSegments.length
      ? "approved_timeline"
      : "manifest_visuals",
    output_path: path
      .relative(projectRoot, outputPath)
      .split(path.sep)
      .join("/"),
    preview_path: path
      .relative(projectRoot, previewPath)
      .split(path.sep)
      .join("/"),
    duration_seconds: composition.durationInFrames / composition.fps,
    fps: composition.fps,
    width: composition.width,
    height: composition.height,
    render_profile: runtime.render_profile ?? manifest.render_profile,
    test_mode: Boolean(runtime.test_mode ?? manifest.test_mode),
  };
  await writeJson(storyPath, manifest);

  console.log(
    JSON.stringify(
      {
        output_path: outputPath,
        preview_path: previewPath,
        duration_seconds: manifest.composition.duration_seconds,
      },
      null,
      2,
    ),
  );
};

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
