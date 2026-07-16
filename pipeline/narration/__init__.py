"""Canonical local narration generation and exact timing contracts."""

from .service import (
    NarrationNotReadyError,
    generate_narration,
    load_narration_artifact,
)

__all__ = [
    "NarrationNotReadyError",
    "generate_narration",
    "load_narration_artifact",
]
