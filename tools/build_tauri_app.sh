#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${FORMULAOCR_PYTHON:-/private/tmp/formulaocr-build-venv/bin/python}
FORMULAOCR_PYTHON="$PYTHON" "$ROOT/tools/build_tauri_sidecar.sh"

cd "$ROOT"
TAURI_TARGET_DIR=${CARGO_TARGET_DIR:-/private/tmp/formulaocr-tauri-target}
export CARGO_TARGET_DIR="$TAURI_TARGET_DIR"
export CARGO_BUILD_JOBS=1
export PATH="/opt/homebrew/opt/rustup/bin:$PATH"
export RUSTUP_TOOLCHAIN="${FORMULAOCR_RUST_TOOLCHAIN:-1.88.0}"
# Use Rust's default Apple linker driver so the selected macOS SDK and system
# libraries are resolved together. Explicit caller RUSTFLAGS remain untouched.
# Rust 1.88's release stripping can produce a misaligned LINKEDIT string pool
# rejected by current macOS when loading build-time procedural macros.
export CARGO_PROFILE_RELEASE_STRIP="${CARGO_PROFILE_RELEASE_STRIP:-none}"
"$ROOT/node_modules/.bin/tauri" build --bundles app

APP="$TAURI_TARGET_DIR/release/bundle/macos/FormulaOCR.app"
SIDECAR=/private/tmp/formulaocr-sidecar-dist/formulaocr-sidecar
DEST="$APP/Contents/Resources/formulaocr-sidecar"
test -d "$APP"
test -x "$SIDECAR/formulaocr-sidecar"
rm -rf "$DEST"
/usr/bin/ditto "$SIDECAR" "$DEST"

"$PYTHON" "$ROOT/tools/collect_runtime_notices.py" "$APP"

codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "$APP"
