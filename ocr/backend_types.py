"""Shared OCR backend input types without runtime dependencies."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


ImageInput = Image.Image | np.ndarray | str | Path
