/**
 * main.ts
 *
 * Entry point for the web_avatar_runtime Vite app.
 *
 * Flow:
 *   1. Read ?job=<path> from URL search params
 *   2. Fetch and parse the BrowserJob JSON
 *   3. Validate face.mode === "3d_viseme"
 *   4. Instantiate TalkingHead in #avatar, load the GLB, apply camera
 *   5. Fetch WAV audio, decode via AudioContext
 *   6. Queue speakAudio() with precomputed visemes
 *   7. Queue speakMarker() — sets window.__renderStatus = "done" when finished
 *
 * Playwright polls window.__renderStatus for "done" | "error".
 */

import "./styles.css";
import { TalkingHead } from "@met4citizen/talkinghead";
import type { BrowserJob } from "./avatarJob.js";
import { normalizeVisemeArrays } from "./visemes.js";
import { applyCamera } from "./cameras.js";
import { runRocketboxRuntime } from "./rocketboxRuntime.js";

// ---------------------------------------------------------------------------
// Global signals polled by Playwright
// ---------------------------------------------------------------------------
declare global {
  interface Window {
    __renderStatus: "idle" | "loading" | "rendering" | "done" | "error";
    __renderError: string | undefined;
    __renderWarnings: string[];
  }
}

window.__renderStatus = "idle";
window.__renderError = undefined;
window.__renderWarnings = [];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setStatus(msg: string): void {
  const el = document.getElementById("status");
  if (el) el.textContent = msg;
  console.info("[avatar-runtime]", msg);
}

function fatal(err: unknown): never {
  const message = err instanceof Error ? err.message : String(err);
  window.__renderStatus = "error";
  window.__renderError = message;
  setStatus(`ERROR: ${message}`);
  console.error("[avatar-runtime] FATAL:", err);
  throw err instanceof Error ? err : new Error(message);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  setStatus("Loading...");
  window.__renderStatus = "loading";

  // 1. Parse job path from URL
  const params = new URLSearchParams(window.location.search);
  const jobPath = params.get("job");
  if (!jobPath) {
    fatal(
      new Error(
        "Missing required URL parameter: ?job=<path_to_browser_job.json>",
      ),
    );
  }

  // 2. Fetch job JSON
  setStatus(`Fetching job: ${jobPath}`);
  let job: BrowserJob;
  try {
    const resp = await fetch(jobPath);
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status} fetching job from "${jobPath}"`);
    }
    job = (await resp.json()) as BrowserJob;
  } catch (err) {
    fatal(err);
  }

  // 3. Route non-TalkingHead jobs before constructing TalkingHead. Rocketbox
  // uses direct Three.js morph-target driving to avoid TalkingHead's RPM body
  // pose assumptions.
  if (job.renderer === "rocketbox") {
    await runRocketboxRuntime(job);
    return;
  }

  // 4. Validate face mode
  if (job.face.mode !== "3d_viseme") {
    fatal(
      new Error(
        `Unsupported face.mode "${job.face.mode}". Only "3d_viseme" is supported by this runtime.`,
      ),
    );
  }

  // 5. Validate viseme arrays early to surface problems before loading the avatar
  const { visemes, vtimes, vdurations } = normalizeVisemeArrays(
    job.precomputed_visemes,
  );

  // 5. Instantiate TalkingHead
  setStatus("Initialising TalkingHead...");
  const avatarEl = document.getElementById("avatar");
  if (!avatarEl) {
    fatal(new Error("Required DOM element #avatar not found"));
  }

  const head = new TalkingHead(avatarEl, {
    ttsEndpoint: "",
    lipsyncModules: [],
    modelFPS: job.camera.fps,
    cameraView: "upper",
    avatarMute: false,
  });

  // 6. Load the avatar GLB/VRM
  setStatus(`Loading avatar: ${job.avatar_url}`);
  try {
    await head.showAvatar(
      {
        url: job.avatar_url,
        body: job.body_form ?? "M",
        lipsyncLang: "en",
        avatarMood: "neutral",
      },
      (ev) => {
        if (ev.lengthComputable && ev.total > 0) {
          const pct = Math.round((ev.loaded / ev.total) * 100);
          setStatus(`Loading avatar... ${pct}%`);
        }
      },
    );
  } catch (err) {
    fatal(err);
  }

  // 7. Apply camera preset
  applyCamera(head, job.camera.name);

  // 8. Fetch WAV audio
  setStatus(`Fetching audio: ${job.audio_url}`);
  let arrayBuffer: ArrayBuffer;
  try {
    const audioResp = await fetch(job.audio_url);
    if (!audioResp.ok) {
      throw new Error(
        `HTTP ${audioResp.status} fetching audio from "${job.audio_url}"`,
      );
    }
    arrayBuffer = await audioResp.arrayBuffer();
  } catch (err) {
    fatal(err);
  }

  // 9. Decode to AudioBuffer using TalkingHead's AudioContext
  setStatus("Decoding audio...");
  let audioBuffer: AudioBuffer;
  try {
    audioBuffer = await head.audioCtx.decodeAudioData(arrayBuffer);
  } catch (err) {
    fatal(err);
  }

  // 10. Queue speakAudio with precomputed visemes
  setStatus("Queuing speech...");
  window.__renderStatus = "rendering";

  const speakPayload: Record<string, unknown> = {
    audio: audioBuffer,
    words: [] as string[],
    wtimes: [] as number[],
    wdurations: [] as number[],
    visemes,
    vtimes,
    vdurations,
  };

  head.speakAudio(speakPayload, { isRaw: false });

  // 11. Queue completion marker — Playwright polls this
  head.speakMarker(() => {
    window.__renderStatus = "done";
    setStatus("Done.");
    console.info("[avatar-runtime] Render complete — __renderStatus = 'done'");
  });

  setStatus("Rendering...");
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

main().catch((err: unknown) => {
  // fatal() already set window.__renderStatus = "error"; just log here.
  console.error("[avatar-runtime] Unhandled error in main():", err);
});
