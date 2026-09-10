#!/bin/bash
# Build the SwiftUI menu-bar app with SwiftPM (no Xcode needed), wrap it into
# a .app bundle, and install it to /Applications so it behaves like a normal
# installed Mac app (independent of this project folder, easy to find,
# survives Launch at Login).
#
# Usage: scripts/build_app.sh [--release] [--no-install]
#   --release     build in release configuration (default: debug)
#   --no-install  only build to mac/build/, skip installing to /Applications
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/mac/MorningBrief"
CONFIG=debug
INSTALL=1
for arg in "$@"; do
  case "$arg" in
    --release) CONFIG=release ;;
    --no-install) INSTALL=0 ;;
  esac
done

cd "$PKG"
swift build -c "$CONFIG" 2>&1 | tail -3
BIN="$(swift build -c "$CONFIG" --show-bin-path)/MorningBrief"
APP="$ROOT/mac/build/Morning Brief.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/MorningBrief"
cp "$PKG/Resources/Info.plist" "$APP/Contents/Info.plist"
cp "$PKG/Resources/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
echo -n "APPL????" > "$APP/Contents/PkgInfo"
codesign --force --sign - "$APP" >/dev/null 2>&1 || true   # ad-hoc signature
echo "Built: $APP"

if [[ "$INSTALL" == "1" ]]; then
  INSTALLED="/Applications/Morning Brief.app"
  WAS_RUNNING=0
  if pgrep -x MorningBrief >/dev/null 2>&1; then
    WAS_RUNNING=1
    osascript -e 'tell application "Morning Brief" to quit' >/dev/null 2>&1 || true
    pkill -x MorningBrief >/dev/null 2>&1 || true
    sleep 1
  fi
  rm -rf "$INSTALLED"
  cp -R "$APP" "$INSTALLED"
  codesign --force --sign - "$INSTALLED" >/dev/null 2>&1 || true
  echo "Installed: $INSTALLED"
  if [[ "$WAS_RUNNING" == "1" ]]; then
    open "$INSTALLED"
    echo "Relaunched (it was running before this rebuild)."
  else
    echo "Run:   open \"$INSTALLED\""
  fi
else
  echo "Run:   open \"$APP\""
fi
