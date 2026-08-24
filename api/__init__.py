"""Optional remote formula OCR integrations."""

from .config import APIProfileStore, APIProviderProfile
from .providers import (
    DEFAULT_PROMPT,
    MathpixProvider,
    OpenAICompatibleProvider,
    RemoteFormulaProvider,
    RemoteOCRResult,
)

__all__ = [
    "APIProfileStore",
    "APIProviderProfile",
    "DEFAULT_PROMPT",
    "MathpixProvider",
    "OpenAICompatibleProvider",
    "RemoteFormulaProvider",
    "RemoteOCRResult",
]
