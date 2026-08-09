import type { ChannelId, ChannelProfile } from "./contracts";

export type ChannelPresentation = {
  channelId: ChannelId;
  name: string;
  initials: string;
  tagline: string;
  description: string;
  accent: string;
  accentHover: string;
  accentSoft: string;
  accentGlow: string;
};

export const CHANNEL_IDS: ChannelId[] = ["synthpost", "meridian", "beyond", "storytime"];

const CHANNEL_PRESENTATIONS: Record<ChannelId, ChannelPresentation> = {
  synthpost: {
    channelId: "synthpost",
    name: "SynthPost",
    initials: "SP",
    tagline: "Technology · culture · AI",
    description: "Technology, startups, social media and internet culture.",
    accent: "#e41c23",
    accentHover: "#f03038",
    accentSoft: "rgba(228, 28, 35, 0.14)",
    accentGlow: "rgba(228, 28, 35, 0.28)",
  },
  meridian: {
    channelId: "meridian",
    name: "Meridian",
    initials: "M",
    tagline: "Money · markets · systems",
    description: "Financial systems, markets, companies and economic power.",
    accent: "#d5a847",
    accentHover: "#e7bb5e",
    accentSoft: "rgba(213, 168, 71, 0.14)",
    accentGlow: "rgba(213, 168, 71, 0.26)",
  },
  beyond: {
    channelId: "beyond",
    name: "Beyond",
    initials: "B",
    tagline: "World news · geopolitics",
    description: "International news, geopolitics and global affairs.",
    accent: "#4f8cff",
    accentHover: "#6aa0ff",
    accentSoft: "rgba(79, 140, 255, 0.14)",
    accentGlow: "rgba(79, 140, 255, 0.28)",
  },
  storytime: {
    channelId: "storytime",
    name: "Sidequest",
    initials: "SQ",
    tagline: "Stories · mishaps · detours",
    description: "Animated personal stories, awkward moments and everyday observations.",
    accent: "#7c5cfc",
    accentHover: "#9278ff",
    accentSoft: "rgba(124, 92, 252, 0.16)",
    accentGlow: "rgba(124, 92, 252, 0.3)",
  },
};

export const isChannelId = (value: string | null): value is ChannelId =>
  value !== null && CHANNEL_IDS.includes(value as ChannelId);

export const channelPresentation = (
  channelId: ChannelId,
  profile?: ChannelProfile | null,
): ChannelPresentation => {
  const fallback = CHANNEL_PRESENTATIONS[channelId];
  const optional = (profile ?? {}) as Partial<{
    name: string;
    short_name: string;
    tagline: string;
    description: string;
    accent_color: string;
    accent_hover_color: string;
    accent_soft_color: string;
  }>;

  return {
    ...fallback,
    name: optional.name?.trim() || fallback.name,
    initials: optional.short_name?.trim() || fallback.initials,
    tagline: optional.tagline?.trim() || fallback.tagline,
    description: optional.description?.trim() || fallback.description,
    accent: optional.accent_color?.trim() || fallback.accent,
    accentHover: optional.accent_hover_color?.trim() || fallback.accentHover,
    accentSoft: optional.accent_soft_color?.trim() || fallback.accentSoft,
  };
};
