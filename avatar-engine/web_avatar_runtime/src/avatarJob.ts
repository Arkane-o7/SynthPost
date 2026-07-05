/**
 * avatarJob.ts
 *
 * TypeScript types for the browser-side job object.
 * The Python renderer writes a browser_job.json with this shape,
 * which is fetched by main.ts via the ?job=<path> URL param.
 */

export interface BrowserJob {
  renderer: "talkinghead" | "rocketbox";
  episode_id: string;
  story_id: string;
  /** HTTP path to GLB/VRM, e.g. "/assets/avatars/..." */
  avatar_url: string;
  /** HTTP path to WAV audio file */
  audio_url: string;

  camera: {
    /** e.g. "front_medium" | "front_close" | "portrait_main" | ... */
    name: string;
    width: number;
    height: number;
    fps: number;
    duration_seconds?: number;
  };

  face: {
    mode: "3d_viseme" | "legacy_2d";
    viseme_source?: string;
    blendshape_profile?: string;
  };

  /**
   * Avatar body form passed through to TalkingHead showAvatar().
   * "M" = male, "F" = female, "N" = neutral.
   * Affects idle animation selection and procedural motion weights.
   * Defaults to "M" when omitted.
   */
  body_form?: "M" | "F" | "N";

  animation: {
    idle_loop?: string;
    gesture_style?: string;
    gesture_events?: Array<{
      time: number;
      type?: string;
      clip?: string;
      duration?: number;
    }>;
  };

  avatar_transform?: {
    rotation_y_degrees?: number;
    rotation_x_degrees?: number;
    rotation_z_degrees?: number;
    scale?: number;
  };

  camera_overrides?: {
    distance_multiplier?: number;
    target_height_factor?: number;
    height_factor?: number;
  };

  render: {
    background: string;
  };

  precomputed_visemes: {
    /** Oculus viseme IDs: "sil", "PP", "aa", "E", "I", "O", "U", ... */
    visemes: string[];
    /** Start times in milliseconds */
    vtimes: number[];
    /** Durations in milliseconds */
    vdurations: number[];
  };
}
