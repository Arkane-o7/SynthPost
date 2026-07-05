/**
 * visemes.ts
 *
 * Helpers to validate and normalize precomputed Oculus viseme arrays
 * before handing them to TalkingHead's speakAudio().
 */

import type { BrowserJob } from "./avatarJob.js";

/** Full set of Oculus Runtime viseme IDs supported by TalkingHead */
export const SUPPORTED_OCULUS_VISEMES: ReadonlySet<string> = new Set([
  "sil",
  "PP",
  "FF",
  "TH",
  "DD",
  "kk",
  "CH",
  "SS",
  "nn",
  "RR",
  "aa",
  "E",
  "ih",
  "oh",
  "ou",
  "U",
  "O",
  "I",
]);

export interface NormalizedVisemes {
  visemes: string[];
  vtimes: number[];
  vdurations: number[];
}

/**
 * Validates that all three arrays have the same length, that vtimes and
 * vdurations contain finite numbers, and that each viseme label is a
 * known Oculus ID.  Returns the three arrays unchanged on success.
 *
 * Throws a descriptive Error if anything is wrong.
 */
export function normalizeVisemeArrays(
  precomputed: BrowserJob["precomputed_visemes"]
): NormalizedVisemes {
  const { visemes, vtimes, vdurations } = precomputed;

  if (visemes.length !== vtimes.length || visemes.length !== vdurations.length) {
    throw new Error(
      `Viseme array length mismatch: visemes=${visemes.length}, ` +
        `vtimes=${vtimes.length}, vdurations=${vdurations.length}`
    );
  }

  for (let i = 0; i < visemes.length; i++) {
    if (!SUPPORTED_OCULUS_VISEMES.has(visemes[i])) {
      console.warn(
        `[visemes] Unknown Oculus viseme "${visemes[i]}" at index ${i} — will be passed through`
      );
    }
    if (!Number.isFinite(vtimes[i])) {
      throw new Error(`vtimes[${i}] is not finite: ${vtimes[i]}`);
    }
    if (!Number.isFinite(vdurations[i])) {
      throw new Error(`vdurations[${i}] is not finite: ${vdurations[i]}`);
    }
  }

  return { visemes, vtimes, vdurations };
}
