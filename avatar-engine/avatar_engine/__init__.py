"""Avatar-Engine renderer package.

Exposes the renderer interface and factory used by the CLI and external callers.
"""

from avatar_engine.renderer_base import AvatarJob, AvatarRenderer, AvatarRenderResult
from avatar_engine.renderer_factory import get_renderer

__all__ = [
    "AvatarJob",
    "AvatarRenderResult",
    "AvatarRenderer",
    "get_renderer",
]
