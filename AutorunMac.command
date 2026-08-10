#!/bin/bash
# Double-click on macOS: serve app/ and open Chrome.
# Use 127.0.0.1 (not "localhost") for a consistent IPv4 bind.
cd "$(dirname "$0")/app" || {
  echo "[ERROR] Missing app folder."
  read -r _
  exit 1
}
if [[ ! -f index.html ]]; then
  echo "[ERROR] app/index.html not found."
  read -r _
  exit 1
fi

PORT=8080
for p in 8080 8081 8082 8765; do
  if ! lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
    PORT=$p
    break
  fi
done
URL="http://127.0.0.1:$PORT/"
echo "Serving $(pwd) at $URL"
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
exec python3 -m http.server "$PORT" --bind 127.0.0.1
