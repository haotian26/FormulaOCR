#!/bin/sh
set -eu

# Build outside the OneDrive checkout. OneDrive cannot preserve the Python
# framework symlinks, so the App build script copies this directory directly
# into the finished bundle with ditto.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${FORMULAOCR_PYTHON:-/private/tmp/formulaocr-venv/bin/python}
OUT=/private/tmp/formulaocr-sidecar-dist
WORK=/private/tmp/formulaocr-sidecar-build
rm -rf "$OUT" "$WORK"
"$PYTHON" -m PyInstaller --noconfirm --clean \
  --distpath "$OUT" --workpath "$WORK" \
  "$ROOT/FormulaOCRSidecar.spec"
MODEL="$ROOT/resources/models/PP-FormulaNet_plus-L-ONNX/pp_formulanet_plus_l.onnx"
EXPECTED_SHA256=5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8
ACTUAL_SHA256=$(shasum -a 256 "$MODEL" | awk '{print $1}')
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  echo "FormulaOCR L model SHA256 mismatch" >&2
  exit 1
fi
echo "$OUT/formulaocr-sidecar"
