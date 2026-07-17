export const brand = {
  navy: "#09090A",
  deepBlue: "#141416",
  signalBlue: "#315CFF",
  steelBlue: "#5C7FA6",
  yellow: "#FFD84A",
  red: "#FF3138",
  white: "#F3EFE7",
  paper: "#F3EFE7",
  muted: "#B8B1A7",
  ink: "#050506",
};

export type GenreTheme = {
  key: string;
  label: string;
  accent: string;
  accentEnd: string;
};

const genreThemes: Record<string, GenreTheme> = {
  world: {
    key: "world", label: "WORLD", accent: "#FF3138", accentEnd: "#C90F28",
  },
  technology: {
    key: "technology", label: "TECHNOLOGY", accent: "#315CFF", accentEnd: "#7B35E8",
  },
  finance: {
    key: "finance", label: "FINANCE", accent: "#00BFA6", accentEnd: "#087A65",
  },
  culture: {
    key: "culture", label: "CULTURE", accent: "#FF4F91", accentEnd: "#D33867",
  },
  climate: {
    key: "climate", label: "CLIMATE", accent: "#30C77B", accentEnd: "#0D8D87",
  },
  general: {
    key: "general", label: "NEWS", accent: "#FF3138", accentEnd: "#D8192D",
  },
};

const genreAliases: Record<string, string> = {
  tech: "technology", ai: "technology", science: "technology",
  business: "finance", markets: "finance", economy: "finance",
  economics: "finance",
  politics: "world", geopolitics: "world", global: "world", international: "world",
  entertainment: "culture", internet_culture: "culture", media: "culture",
  environment: "climate", energy: "climate",
};

export const genreTheme = (category?: string): GenreTheme => {
  const normalized = String(category ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z]+/g, "_");
  return (
    genreThemes[normalized] ??
    genreThemes[genreAliases[normalized]] ??
    genreThemes.general
  );
};

export const layout = {
  width: 1920,
  height: 1080,
  anchor: { left: 0, top: 0, width: 620, height: 860 },
  visual: { left: 620, top: 0, width: 1300, height: 860 },
  lower: { left: 0, top: 860, width: 1920, height: 220 },
};

export const anchorCrop = {
  scale: 1.12,
  offsetX: 0,
  offsetY: -8,
  objectPosition: "center top",
};

export const fullAnchorCrop = {
  scale: 1,
  offsetX: 0,
  offsetY: 0,
  objectPosition: "center center",
};

export const typography = {
  serif: 'Georgia, "Times New Roman", serif',
  sans: '"Avenir Next", "Helvetica Neue", Helvetica, sans-serif',
  mono: '"SF Mono", "JetBrains Mono", Menlo, monospace',
};
