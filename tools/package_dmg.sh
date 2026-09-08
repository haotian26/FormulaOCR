#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(tr -d '[:space:]' < "$ROOT/VERSION")
APP=${1:-/Applications/FormulaOCR.app}
OUTPUT=${2:-"$ROOT/FormulaOCR-v$VERSION.dmg"}
test -d "$APP"
test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")" = "$VERSION"
codesign --verify --deep --strict "$APP"

WORK=$(mktemp -d /private/tmp/formulaocr-dmg.XXXXXX)
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT INT TERM
mkdir "$WORK/root"
/usr/bin/ditto "$APP" "$WORK/root/FormulaOCR.app"
ln -s /Applications "$WORK/root/Applications"

SOURCE_BYTES=$(du -sk "$APP" | awk '{print $1}')
STAGED_BYTES=$(du -sk "$WORK/root/FormulaOCR.app" | awk '{print $1}')
echo "Source App: $SOURCE_BYTES KiB; staged App: $STAGED_BYTES KiB"
if [ "$STAGED_BYTES" -gt $((SOURCE_BYTES * 115 / 100)) ]; then
  echo "Staged app expanded unexpectedly" >&2
  exit 1
fi
/usr/bin/hdiutil create -volname FormulaOCR -srcfolder "$WORK/root" -ov -format UDBZ "$WORK/FormulaOCR.dmg"
/usr/bin/ditto "$WORK/FormulaOCR.dmg" "$OUTPUT"
/usr/bin/hdiutil verify "$OUTPUT"
DMG_BYTES=$(stat -f '%z' "$OUTPUT")
echo "Compressed DMG: $DMG_BYTES bytes (UDBZ)"
if [ "$DMG_BYTES" -ge $((SOURCE_BYTES * 1024)) ]; then
  echo "Compressed DMG is not smaller than the source App; stop publication" >&2
  exit 1
fi
echo "$OUTPUT"
