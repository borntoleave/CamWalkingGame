#!/bin/bash
# Run on Linux: serve app/ and open Chrome/Edge/Chromium.
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
  echo "[ERROR] python3 not found. Install it (e.g. sudo apt install python3) and retry."
  read -r _
  exit 1
fi
if [[ ! -f "$ROOT/app/vendor/mediapipe/models/hand_landmarker.task" ]]; then
  echo "[WARN] Missing hand_landmarker.task. Finger tracking will not load."
fi
if [[ ! -f "$ROOT/app/vendor/mediapipe/models/pose_landmarker_lite.task" ]]; then
  echo "[WARN] Missing pose_landmarker_lite.task. Elbow and knee tracking will not load."
fi

port_free() {
  python3 -c 'import socket, sys
p = int(sys.argv[1])
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", p))
except OSError:
    raise SystemExit(1)
s.close()
' "$1"
}

PORT=8080
for p in 8080 8081 8082 8765; do
  if port_free "$p"; then
    PORT=$p
    break
  fi
done
URL="http://127.0.0.1:$PORT/"
echo "Serving $ROOT/app at $URL"
echo "Photos save under $ROOT/pics"
echo "Keep this window open while demoing. Press Ctrl+C to stop."
echo "Tip: use Chrome/Edge/Chromium (Web Serial)."

open_demo() {
  sleep 0.8
  if command -v google-chrome >/dev/null 2>&1; then
    google-chrome "$URL" >/dev/null 2>&1 &
  elif command -v google-chrome-stable >/dev/null 2>&1; then
    google-chrome-stable "$URL" >/dev/null 2>&1 &
  elif command -v chromium-browser >/dev/null 2>&1; then
    chromium-browser "$URL" >/dev/null 2>&1 &
  elif command -v chromium >/dev/null 2>&1; then
    chromium "$URL" >/dev/null 2>&1 &
  elif command -v microsoft-edge >/dev/null 2>&1; then
    microsoft-edge "$URL" >/dev/null 2>&1 &
  elif command -v microsoft-edge-stable >/dev/null 2>&1; then
    microsoft-edge-stable "$URL" >/dev/null 2>&1 &
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
  else
    echo "Open in Chrome/Edge: $URL"
  fi
}
open_demo &
exec python3 "$ROOT/scripts/demo_server.py" --bind 127.0.0.1 --port "$PORT"
