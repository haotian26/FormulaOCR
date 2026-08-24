"""Unified backend interface and the formal ONNX backend."""

from __future__ import annotations

import json
import math
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from tokenizers import Tokenizer

from app.paths import FORMULA_MODEL_PATH, require_file
from .backend_types import ImageInput
from .result import OCRResult
from .visual_case import refine_latex_case


MODEL_CONTENT_OCCUPANCY = 0.99



class FormulaOCRBackend(ABC):
    """Backend contract used by the engine and future UI layers."""

    @abstractmethod
    def load(self) -> None:
        """Load the local model and tokenizer once."""

    @abstractmethod
    def recognize(self, image: ImageInput) -> OCRResult:
        """Recognize one formula image without touching the network."""

    @abstractmethod
    def is_loaded(self) -> bool:
        """Return whether the backend is ready for inference."""


def _as_rgb_array(image: ImageInput) -> np.ndarray:
    if isinstance(image, (str, Path)):
        image = Image.open(image)
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("RGB"))
    array = np.asarray(image)
    if array.ndim == 2:
        array = np.repeat(array[:, :, None], 3, axis=2)
    if array.ndim != 3 or array.shape[2] not in (3, 4):
        raise ValueError("Formula image must have shape H×W, H×W×3 or H×W×4")
    if array.shape[2] == 4:
        array = array[:, :, :3]
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    return array


def _foreground_box(image: Image.Image) -> tuple[int, int, int, int] | None:
    data = np.asarray(image.convert("L"), dtype=np.uint8)
    max_val, min_val = int(data.max()), int(data.min())
    if max_val == min_val:
        return None
    scaled = (data - min_val) / (max_val - min_val) * 255
    mask = scaled < 200
    mask = _remove_image_frame(mask)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    left, right = int(xs.min()), int(xs.max()) + 1
    top, bottom = int(ys.min()), int(ys.max()) + 1
    return left, top, right, bottom


def _remove_image_frame(mask: np.ndarray) -> np.ndarray:
    """Ignore a thin frame captured around an image preview widget.

    A screenshot of FormulaOCR can contain the preview panel's border at both
    outer edges.  Those lines are not formula glyphs, but a formula recognizer
    quite reasonably decodes them as square brackets.  Only remove a line
    that touches both image boundaries and occupies most of the full edge;
    ordinary absolute-value bars and bracket glyphs remain untouched.
    """

    source = mask
    result = mask.copy()
    height, width = result.shape
    if height < 8 or width < 8:
        return result
    edge_width = max(1, min(6, width // 100))
    edge_height = max(1, min(6, height // 100))

    def full_edge_columns(start: int, stop: int) -> list[int]:
        columns: list[int] = []
        for column in range(start, stop):
            values = source[:, column]
            if bool(values[0]) and bool(values[-1]) and float(values.mean()) >= 0.55:
                columns.append(column)
        return columns

    def full_edge_rows(start: int, stop: int) -> list[int]:
        rows: list[int] = []
        for row in range(start, stop):
            values = source[row, :]
            if bool(values[0]) and bool(values[-1]) and float(values.mean()) >= 0.55:
                rows.append(row)
        return rows

    top = full_edge_rows(0, edge_height)
    bottom = full_edge_rows(height - edge_height, height)
    if top and bottom:
        result[min(top) : max(top) + 1, :] = False
        result[min(bottom) : max(bottom) + 1, :] = False

    left = full_edge_columns(0, edge_width)
    right = full_edge_columns(width - edge_width, width)
    if left and right:
        result[:, min(left) : max(left) + 1] = False
        result[:, min(right) : max(right) + 1] = False
    return result


def _crop_margin(image: Image.Image, padding_ratio: float = 0.0) -> Image.Image:
    box = _foreground_box(image)
    if box is None:
        return image
    left, top, right, bottom = box
    if padding_ratio:
        width, height = right - left, bottom - top
        padding = max(1, int(round(max(width, height) * padding_ratio)))
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(image.width, right + padding)
        bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def _needs_content_safety_margin(image: Image.Image) -> bool:
    """Detect a small detached terminal script near a single-line edge.

    Global rescaling changes FormulaNet's decoding on otherwise correct
    formulas.  Reserve extra canvas only when the source pixels show the
    pattern that is actually at risk: a compact final component above or below
    the main line.  This is purely geometric and does not guess which symbol
    or charge the component represents.
    """

    box = _foreground_box(image)
    if box is None:
        return False
    left, top, right, bottom = box
    mask = np.asarray(image.convert("L"), dtype=np.uint8)[top:bottom, left:right] < 200
    height, width = mask.shape
    if not height or not width or height / width > 0.25:
        return False
    rows = mask.any(axis=1)
    blank_run = 0
    blank_limit = max(3, int(round(height * 0.05)))
    for occupied_row in rows:
        if occupied_row:
            blank_run = 0
        else:
            blank_run += 1
            if blank_run >= blank_limit:
                return False
    columns = mask.any(axis=0)
    occupied = np.flatnonzero(columns)
    if occupied.size == 0:
        return False
    end = int(occupied[-1])
    start = end
    blank_run = 0
    for column in range(end - 1, -1, -1):
        if columns[column]:
            blank_run = 0
            start = column
        else:
            blank_run += 1
            if blank_run >= 2:
                start = column + blank_run
                break
    ys, _ = np.nonzero(mask[:, start : end + 1])
    if ys.size == 0:
        return False
    component_height = (int(ys.max()) - int(ys.min()) + 1) / height
    component_center = (int(ys.min()) + int(ys.max()) + 1) / (2 * height)
    return component_height <= 0.4 and (component_center <= 0.4 or component_center >= 0.6)


def _add_content_safety_margin(
    image: Image.Image,
    occupancy: float | None = None,
) -> Image.Image:
    """Keep formula ink away from the fixed model-canvas boundary.

    The L model was validated with the legacy outer letterboxing. Add the
    small white safety area to the tightly cropped formula before the existing
    resize/letterbox steps, so that letterboxing remains byte-for-byte
    unchanged outside this new inner margin.
    """

    occupancy = MODEL_CONTENT_OCCUPANCY if occupancy is None else occupancy
    if not 0.0 < occupancy <= 1.0:
        raise ValueError("occupancy must be in the interval (0, 1]")
    if occupancy == 1.0:
        return image
    target_width = max(image.width, int(math.ceil(image.width / occupancy)))
    target_height = max(image.height, int(math.ceil(image.height / occupancy)))
    horizontal = target_width - image.width
    vertical = target_height - image.height
    return ImageOps.expand(
        image,
        border=(
            horizontal // 2,
            vertical // 2,
            horizontal - horizontal // 2,
            vertical - vertical // 2,
        ),
        fill=(255, 255, 255),
    )


def _normalize_polarity(image: Image.Image) -> Image.Image:
    """Make the formula foreground dark on a light background.

    PP-FormulaNet is trained on the usual black-on-white formula images. A
    macOS screenshot can instead contain white UI text on a dark card (for
    example the FormulaOCR wordmark). Without correcting that polarity the
    model interprets the whole card as a malformed formula and emits repeated
    fraction tokens. The border is a good background sample because it is
    normally outside the glyphs.
    """

    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    if gray.size == 0:
        return image
    border = np.concatenate(
        (
            gray[0, :],
            gray[-1, :],
            gray[1:-1, 0],
            gray[1:-1, -1],
        )
    )
    if float(np.median(border)) < 128.0:
        return ImageOps.invert(image)
    return image


def preprocess(
    image: ImageInput,
    size: int = 384,
    variant: str = "baseline",
) -> np.ndarray:
    """Prepare an image for PP-FormulaNet_plus-L.

    This mirrors the verified Stage A preprocessing while avoiding a runtime
    dependency on PaddleOCR or RapidDoc.
    """

    pil_image = Image.fromarray(_as_rgb_array(image)).convert("RGB")
    pil_image = _normalize_polarity(pil_image)
    padding_ratio = {"baseline": 0.0, "context8": 0.08, "context16": 0.16}.get(variant)
    if padding_ratio is None:
        raise ValueError(f"Unknown preprocessing variant: {variant}")
    needs_safety_margin = _needs_content_safety_margin(pil_image)
    pil_image = _crop_margin(pil_image, padding_ratio)
    if needs_safety_margin:
        pil_image = _add_content_safety_margin(pil_image)
    if pil_image.width == 0 or pil_image.height == 0:
        raise ValueError("Formula image has no non-background pixels")

    width, height = pil_image.size
    short_edge = min(width, height)
    if height <= width:
        new_height, new_width = short_edge, int(short_edge * width / height)
    else:
        new_height, new_width = int(short_edge * height / width), short_edge
    resample = Image.Resampling.LANCZOS if variant == "context16" else Image.Resampling.BILINEAR
    pil_image = pil_image.resize((new_width, new_height), resample=resample)
    pil_image.thumbnail((size, size))
    delta_width, delta_height = size - pil_image.width, size - pil_image.height
    pil_image = ImageOps.expand(
        pil_image,
        (
            delta_width // 2,
            delta_height // 2,
            delta_width - delta_width // 2,
            delta_height - delta_height // 2,
        ),
    )

    array = np.asarray(pil_image).astype("float32") / 255.0
    mean = np.asarray([0.7931] * 3, dtype="float32").reshape(1, 1, 3)
    std = np.asarray([0.1738] * 3, dtype="float32").reshape(1, 1, 3)
    array = (array - mean) / std

    # OpenCV's BGR2GRAY coefficients as used by the Stage A reference code.
    gray = 0.114 * array[:, :, 0] + 0.587 * array[:, :, 1] + 0.299 * array[:, :, 2]
    height = math.ceil(gray.shape[0] / 16) * 16
    width = math.ceil(gray.shape[1] / 16) * 16
    gray = np.pad(
        gray,
        ((0, height - gray.shape[0]), (0, width - gray.shape[1])),
        constant_values=(1, 1),
    )
    return gray[None, None].astype("float32", copy=False)


class ONNXFormulaBackend(FormulaOCRBackend):
    """CPU ONNX Runtime backend for the fixed PP-FormulaNet_plus-L model."""

    def __init__(self, model_path: Path | None = None):
        self.model_path = Path(model_path) if model_path else FORMULA_MODEL_PATH
        self._session: Any | None = None
        self._tokenizer: Tokenizer | None = None
        self._input_name: str | None = None
        self._output_name: str | None = None
        self._input_size = 384

    def load(self) -> None:
        if self.is_loaded():
            return
        model_path = require_file(self.model_path, "PP-FormulaNet_plus-L ONNX model")
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(
            str(model_path),
            options,
            providers=["CPUExecutionProvider"],
        )
        metadata = session.get_modelmeta().custom_metadata_map
        try:
            character = json.loads(metadata["character"])
            tokenizer_json = json.dumps(character["fast_tokenizer_file"])
        except (KeyError, json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError("ONNX model is missing tokenizer metadata") from exc
        self._session = session
        self._tokenizer = Tokenizer.from_str(tokenizer_json)
        self._input_name = session.get_inputs()[0].name
        self._output_name = session.get_outputs()[0].name
        input_shape = session.get_inputs()[0].shape
        if len(input_shape) >= 4 and all(isinstance(value, int) for value in input_shape[2:4]):
            height, width = int(input_shape[2]), int(input_shape[3])
            if height != width:
                raise RuntimeError(f"Formula model input must be square, got {input_shape}")
            self._input_size = height

    def is_loaded(self) -> bool:
        return self._session is not None and self._tokenizer is not None

    def _decode(self, token_ids: np.ndarray) -> str:
        if self._tokenizer is None:
            raise RuntimeError("ONNX backend is not loaded")
        row = [int(value) for value in np.asarray(token_ids)[0]]
        if 2 in row:
            row = row[: row.index(2) + 1]
        return self._tokenizer.decode(row, skip_special_tokens=True)

    def _recognize_variant(self, image: ImageInput, variant: str) -> OCRResult:
        if not self.is_loaded():
            self.load()
        assert self._session is not None
        assert self._input_name is not None
        assert self._output_name is not None
        started = time.perf_counter()
        batch = preprocess(image, size=self._input_size, variant=variant)
        output = self._session.run(
            [self._output_name],
            {self._input_name: batch},
        )[0]
        raw_latex = self._decode(output)
        token_ids = tuple(int(value) for value in np.asarray(output)[0])
        if 2 in token_ids:
            token_ids = token_ids[: token_ids.index(2) + 1]
        case_refined_latex = refine_latex_case(raw_latex, image)
        return OCRResult(
            raw_latex=raw_latex,
            confidence=None,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            case_refined_latex=case_refined_latex,
            variant=variant,
            token_ids=token_ids,
        )

    def recognize(self, image: ImageInput) -> OCRResult:
        return self._recognize_variant(image, "baseline")
