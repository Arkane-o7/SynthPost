/**
 * recorder.ts
 *
 * Architecture note:
 * ------------------
 * The primary capture mechanism is Playwright's built-in `recordVideo` context
 * option, which records the entire browser viewport at the OS/GPU level.
 * This means we do NOT need to use MediaRecorder / canvas capture from within
 * the page itself — Playwright handles it transparently.
 *
 * This module is therefore a stub.  It is kept in the codebase so that:
 *  1. A future fallback path (e.g. for non-Playwright runners) can be wired in
 *     without changing the import surface in main.ts.
 *  2. CI linting confirms the recorder integration point compiles cleanly.
 *
 * If you need an in-page MediaRecorder in the future, replace the body of
 * RecorderStub with a real implementation backed by:
 *   const stream = (canvas as HTMLCanvasElement).captureStream(fps);
 *   const mr = new MediaRecorder(stream, { mimeType: "video/webm;codecs=vp9" });
 */

export class RecorderStub {
  /** No-op: Playwright's recordVideo does the actual capture. */
  start(): void {
    // intentionally empty — Playwright is recording
  }

  /** No-op stop; resolves to null because Playwright owns the output file. */
  stop(): Promise<Blob | null> {
    return Promise.resolve(null);
  }
}
