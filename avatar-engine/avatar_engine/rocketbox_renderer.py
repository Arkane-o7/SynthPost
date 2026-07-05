"""RocketboxAvatarRenderer — compatibility adapter for the CC4 browser runtime.

The public renderer key remains ``rocketbox`` because early browser-renderer
jobs used that name.  The active SynthPost anchor path now drives a
Reallusion/Character Creator GLB through the custom Three.js runtime in
``web_avatar_runtime/src/rocketboxRuntime.ts``.  This adapter reuses the shared
browser capture, HTTP serving, PNG-frame capture, and FFmpeg mux code from the
TalkingHead renderer base implementation.
"""

from __future__ import annotations

from avatar_engine.talkinghead_renderer import TalkingHeadAvatarRenderer


class RocketboxAvatarRenderer(TalkingHeadAvatarRenderer):
    """Render CC4/Reallusion GLBs via the legacy ``rocketbox`` renderer key."""

    name = "rocketbox"
