#!/usr/bin/env python3
"""FormulaOCR offline CLI and PySide6 GUI entry points."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.application import build_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Recognize one local formula image")
    parser.add_argument("image", type=Path, nargs="?", help="Local PNG/JPG formula image")
    parser.add_argument("--gui", action="store_true", help="Launch the PySide6 GUI")
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help="Optional local ONNX model path; no download is attempted",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON result")
    args = parser.parse_args()
    if args.gui:
        return gui_main()
    if args.image is None:
        parser.error("image is required unless --gui is used")
    if not args.image.is_file():
        parser.error(f"Image not found: {args.image}")

    result = build_engine(args.model).recognize(args.image)
    payload = {
        "image": str(args.image),
        "raw_latex": result.raw_latex,
        "latex": result.formatted_latex,
        "confidence": result.confidence,
        "elapsed_ms": round(result.elapsed_ms, 3),
        "variant": result.variant,
        "initial_raw_latex": result.initial_raw_latex,
        "candidate_count": result.candidate_count,
        "visual_consistency": result.visual_consistency,
        "validation_status": result.validation_status,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(result.formatted_latex)
        print(f"elapsed_ms={result.elapsed_ms:.1f}")
    return 0


def gui_main() -> int:
    from gui.application import run_gui

    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
