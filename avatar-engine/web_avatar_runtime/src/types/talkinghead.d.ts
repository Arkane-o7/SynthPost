/**
 * Minimal ambient type declarations for @met4citizen/talkinghead.
 *
 * The package ships no TypeScript types of its own.  These declarations expose
 * only the subset of the public API that web_avatar_runtime actually uses.
 * Extend as needed when consuming additional TalkingHead features.
 */

declare module "@met4citizen/talkinghead" {
  export class TalkingHead {
    /** The Web AudioContext created by TalkingHead.  Available immediately after construction. */
    audioCtx: AudioContext;

    /**
     * @param node   - DOM element that TalkingHead will render into.
     * @param opt    - Construction options (ttsEndpoint, lipsyncModules, modelFPS, cameraView, …).
     */
    constructor(node: HTMLElement, opt?: Record<string, unknown>);

    /**
     * Load and display an avatar from a GLB/VRM URL.
     *
     * @param config      - { url, body, lipsyncLang, avatarMood, … }
     * @param onprogress  - Optional progress callback.
     */
    showAvatar(
      config: Record<string, unknown>,
      onprogress?: (ev: {
        loaded: number;
        total: number;
        lengthComputable: boolean;
      }) => void
    ): Promise<void>;

    /**
     * Activate a named camera view.
     *
     * @param view  - "upper" | "head" | "mid" | "full"
     * @param opt   - Optional overrides, e.g. { cameraRotateY: 0.5 }
     */
    setView(view: string, opt?: Record<string, unknown>): void;

    /**
     * Queue a pre-decoded audio clip for the avatar to lip-sync to.
     *
     * @param audio        - { audio: AudioBuffer, visemes, vtimes, vdurations, words, wtimes, wdurations }
     * @param opt          - Optional speak options.
     * @param onsubtitles  - Optional subtitle callback.
     */
    speakAudio(
      audio: Record<string, unknown>,
      opt?: Record<string, unknown>,
      onsubtitles?: ((node: unknown) => void) | null
    ): void;

    /**
     * Queue a callback that fires after the current speech queue is drained.
     * Used to signal render completion to Playwright.
     */
    speakMarker(onmarker: () => void): void;

    /** Start the TalkingHead render loop. */
    start(): void;

    /** Stop the TalkingHead render loop. */
    stop(): void;
  }
}
