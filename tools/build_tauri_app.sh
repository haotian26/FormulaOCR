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
RUST_SYSROOT=$(rustc --print sysroot)
RUST_LLD="$RUST_SYSROOT/lib/rustlib/aarch64-apple-darwin/bin/rust-lld"
test -x "$RUST_LLD"
export RUSTFLAGS="-C linker=$RUST_LLD ${RUSTFLAGS:-}"
"$ROOT/node_modules/.bin/tauri" build --bundles app

APP="$TAURI_TARGET_DIR/release/bundle/macos/FormulaOCR.app"
SIDECAR=/private/tmp/formulaocr-sidecar-dist/formulaocr-sidecar
DEST="$APP/Contents/Resources/formulaocr-sidecar"
test -d "$APP"
test -x "$SIDECAR/formulaocr-sidecar"
rm -rf "$DEST"
/usr/bin/ditto "$SIDECAR" "$DEST"

codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "$APP"
