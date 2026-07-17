export type GenreTheme = {
  key: string;
  label: string;
  accent: string;
  accentEnd: string;
  soft: string;
};

const THEMES: Record<string, GenreTheme> = {
  world: { key: 'world', label: 'World', accent: '#ff3138', accentEnd: '#c90f28', soft: 'rgba(255, 49, 56, 0.16)' },
  technology: { key: 'technology', label: 'Technology', accent: '#315cff', accentEnd: '#7b35e8', soft: 'rgba(74, 82, 255, 0.16)' },
  finance: { key: 'finance', label: 'Finance', accent: '#00bfa6', accentEnd: '#087a65', soft: 'rgba(0, 191, 166, 0.15)' },
  culture: { key: 'culture', label: 'Culture', accent: '#ff4f91', accentEnd: '#d33867', soft: 'rgba(255, 79, 145, 0.15)' },
  climate: { key: 'climate', label: 'Climate', accent: '#30c77b', accentEnd: '#0d8d87', soft: 'rgba(48, 199, 123, 0.15)' },
  general: { key: 'general', label: 'News', accent: '#ff3138', accentEnd: '#d8192d', soft: 'rgba(255, 49, 56, 0.15)' },
};

const CATEGORY_ALIASES: Record<string, keyof typeof THEMES> = {
  tech: 'technology', ai: 'technology', science: 'technology',
  business: 'finance', markets: 'finance', economy: 'finance', economics: 'finance',
  politics: 'world', geopolitics: 'world', international: 'world', global: 'world',
  entertainment: 'culture', internet_culture: 'culture', media: 'culture',
  environment: 'climate', energy: 'climate',
};

export const genreTheme = (category?: string | null): GenreTheme => {
  const normalized = String(category ?? '').trim().toLowerCase().replace(/[^a-z]+/g, '_');
  const direct = THEMES[normalized];
  if (direct) return direct;
  const aliased = CATEGORY_ALIASES[normalized];
  return aliased ? THEMES[aliased] : THEMES.general;
};

export const genreStyle = (category?: string | null): React.CSSProperties => {
  const theme = genreTheme(category);
  return {
    '--genre-accent': theme.accent,
    '--genre-accent-end': theme.accentEnd,
    '--genre-soft': theme.soft,
  } as React.CSSProperties;
};
