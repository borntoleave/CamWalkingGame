#!/bin/bash
# Double-click on macOS: serve app/ and open Chrome.
# Photos posted to /api/photo are saved under pics/ by scripts/demo_server.py.
# Use 127.0.0.1 (not "localhost") for a consistent IPv4 bind.
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$ROOT/app/index.html" ]]; then
  echo "[ERROR] app/index.html not found."
  read -r _
  exit 1
fi
if [[ ! -f "$ROOT/scripts/demo_server.py" ]]; then
  echo "[ERROR] scripts/demo_server.py not found."
  read -r _
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found."
  read -r _
  exit 1
fi
if [[ ! -f "$ROOT/app/vendor/mediapipe/models/hand_landmarker.task" ]]; then
  echo "[WARN] Missing hand_landmarker.task. Finger tracking will not load."
fi
if [[ ! -f "$ROOT/app/vendor/mediapipe/models/pose_landmarker_lite.task" ]]; then
  echo "[WARN] Missing pose_landmarker_lite.task. Elbow and knee tracking will not load."
fi

PORT=8080
for p in 8080 8081 8082 8765; do
  if ! lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
    PORT=$p
    break
  fi
done
URL="http://127.0.0.1:$PORT/"
echo "Serving $ROOT/app at $URL"
echo "Photos save under $ROOT/pics"
echo "Keep this window open while demoing. Press Ctrl+C to stop."
echo "Tip: use Chrome/Edge (Web Serial)."

open_demo() {
  sleep 0.8
  if [ -d "/Applications/Google Chrome.app" ]; then
    open -a "Google Chrome" "$URL"
  elif [ -d "/Applications/Microsoft Edge.app" ]; then
    open -a "Microsoft Edge" "$URL"
  elif [ -d "/Applications/Chromium.app" ]; then
    open -a "Chromium" "$URL"
  else
    open "$URL"
  fi
}
open_demo &
exec python3 "$ROOT/scripts/demo_server.py" --bind 127.0.0.1 --port "$PORT"
