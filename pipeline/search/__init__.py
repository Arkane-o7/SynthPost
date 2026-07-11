"""Search backends used by SynthPost research and visual discovery."""

from pipeline.search.searxng_client import (
    SearXNGError,
    SearXNGResult,
    configured,
    search,
)

__all__ = ["SearXNGError", "SearXNGResult", "configured", "search"]
