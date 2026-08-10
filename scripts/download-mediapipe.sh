#!/usr/bin/env bash
# Download MediaPipe Tasks Vision + pose_landmarker_lite for offline / exhibition use.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="0.10.18"
DEST="$ROOT/app/vendor/mediapipe"
mkdir -p "$DEST/models" "$DEST/tasks-vision"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Packing @mediapipe/tasks-vision@$VER …"
(cd "$TMP" && npm pack "@mediapipe/tasks-vision@$VER" >/dev/null)
tar -xzf "$TMP"/mediapipe-tasks-vision-*.tgz -C "$TMP"
rm -rf "$DEST/tasks-vision"
mkdir -p "$DEST/tasks-vision"
cp -R "$TMP/package/." "$DEST/tasks-vision/"
rm -f "$DEST/tasks-vision/"*.map
echo "Downloading pose_landmarker_lite.task …"
curl -L --fail -o "$DEST/models/pose_landmarker_lite.task" \
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
echo "Done. Vendored under app/vendor/mediapipe/ ($(du -sh "$DEST" | awk '{print $1}'))"
