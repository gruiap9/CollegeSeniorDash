#!/bin/bash
# Build the SwiftUI menu-bar app with SwiftPM (no Xcode needed) and wrap it into
# a .app bundle at mac/build/Morning Brief.app. Usage: scripts/build_app.sh [--release]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/mac/MorningBrief"
CONFIG=debug
[[ "${1:-}" == "--release" ]] && CONFIG=release
cd "$PKG"
swift build -c "$CONFIG" 2>&1 | tail -3
BIN="$(swift build -c "$CONFIG" --show-bin-path)/MorningBrief"
APP="$ROOT/mac/build/Morning Brief.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/MorningBrief"
cp "$PKG/Resources/Info.plist" "$APP/Contents/Info.plist"
echo -n "APPL????" > "$APP/Contents/PkgInfo"
codesign --force --sign - "$APP" >/dev/null 2>&1 || true   # ad-hoc signature
echo "Built: $APP"
echo "Run:   open \"$APP\""
