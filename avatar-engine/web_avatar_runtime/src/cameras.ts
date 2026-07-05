/**
 * cameras.ts
 *
 * Camera preset mapping between the job's camera.name string and
 * TalkingHead's setView() API.
 */

import type { TalkingHead } from "@met4citizen/talkinghead";

/**
 * Applies the named camera preset to the TalkingHead instance.
 *
 * TalkingHead view names:
 *   "upper"  — upper-body shot
 *   "head"   — close-up head
 *   "mid"    — mid-body
 *   "full"   — full body
 */
export function applyCamera(head: TalkingHead, cameraName: string): void {
  switch (cameraName) {
    case "front_medium":
      head.setView("upper");
      break;

    case "front_close":
      head.setView("head");
      break;

    case "portrait_main":
      head.setView("mid");
      break;

    case "landscape_intro":
      head.setView("full");
      break;

    case "landscape_conclusion":
      head.setView("full");
      break;

    case "side_three_quarter":
      head.setView("upper", { cameraRotateY: 0.5 });
      break;

    default:
      console.warn(
        `[cameras] Unknown camera preset "${cameraName}", falling back to "upper"`
      );
      head.setView("upper");
      break;
  }
}
