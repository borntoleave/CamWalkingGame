# CamWalkingGame

Browser webcam pose control for Quaddle / OpenCat (elbow & knee → joints).

## Demos

| | |
|---|---|
| [**Finger-control Mini Robot Dog Quaddle \| Physical AI Robotics Kit**](https://youtu.be/kbk8TnLfSDU) | Finger tracking: bend your fingers, the robot's legs follow. |
| [**Physical AI: Teach Robot Dog to How to Walk, Race \| Pose-Controlled Teleoperation Quaddle Robot Kit**](https://www.youtube.com/watch?v=8U3mROh88vQ) | Body tracking: full-body pose drives the robot's gait. |

Both run entirely in the browser over Web Serial. No install, no cloud, no SDK.

## Run (macOS / Windows / Linux)

Web files live under **`app/`** so you do not double-click `index.html` by mistake.

| OS | Launch |
|----|--------|
| macOS | Double-click **`AutorunMac.command`** (uses built-in `python3`) |
| Windows | Double-click **`AutorunWin.bat`** (calls `scripts\AutorunWin.ps1`, **no Python**) |
| Linux | Run **`./AutorunLinux.sh`** (uses `python3`; opens Chrome/Edge/Chromium) |


Uses **Chrome or Edge** (Web Serial). Keep the server window open while demoing.

Windows opens `http://127.0.0.1:8080/` (IPv4) to avoid `localhost` → `::1` connection refused.

Manual equivalent (any OS with Python):

```bash
cd app
python3 -m http.server 8080 --bind 127.0.0.1
# open http://127.0.0.1:8080
```


If Safari shows *HTTPS-Only* / `WebKitErrorDomain:305`, switch to Chrome, or turn off Safari → Settings → Privacy → **HTTPS-Only Mode**.

## Offline / exhibition

MediaPipe WASM + the pose model are vendored under `app/vendor/mediapipe/`.

The page **prefers the local** pose model. On the setup screen:

- **Update model** / **Use downloaded** — CDN download into the browser Cache API, or switch back without re-download
- **Use local** — bundled file (keeps any downloaded copy for later)

WASM / MediaPipe JS stay under `app/vendor/` (re-pack if you need to bump the package):

```bash
./scripts/download-mediapipe.sh
```

## License

[MIT](LICENSE) © 2026 Petoi LLC.

Third-party: MediaPipe Tasks Vision 0.10.18 and the bundled pose model under
`app/vendor/mediapipe/` are Apache-2.0, © Google LLC.
