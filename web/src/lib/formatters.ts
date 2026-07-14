// SynthPost V2 — Display formatting helpers

/**
 * Format an ISO date string as a human-readable relative time.
 * Falls back to the raw string if parsing fails.
 */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (isNaN(date.getTime())) return iso;

  const now = Date.now();
  const diff = now - date.getTime();
  const seconds = Math.floor(diff / 1000);

  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return date.toLocaleDateString();
}

export function timeUntil(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (isNaN(date.getTime())) return iso;
  const seconds = Math.max(0, Math.ceil((date.getTime() - Date.now()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.ceil(minutes / 60);
  return `${hours}h`;
}

/**
 * Format seconds into a human-readable duration string.
 * e.g. 127.4 → "2:07"
 */
export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Truncate a string to maxLen characters, adding ellipsis if truncated.
 */
export function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 1) + '…';
}

/**
 * Shorten a UUID-style ID for display. Shows first 8 chars.
 */
export function shortId(id: string): string {
  return id.length > 12 ? id.slice(0, 8) : id;
}

/**
 * Format a score (0-1 float) as a percentage integer (0-100).
 */
export function scorePercent(score: number): number {
  return Math.round(score * 100);
}

/**
 * Get a tone for a score percentage.
 */
export function scoreTone(pct: number): 'green' | 'amber' | 'neutral' {
  if (pct >= 80) return 'green';
  if (pct >= 60) return 'amber';
  return 'neutral';
}
