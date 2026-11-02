# Pi Zero 2 W investigation — agent handoff

**Written for:** an AI agent picking this up with no prior conversation context.
**Date of investigation:** 2026-10-24 to 2026-11-01.
**Repo:** `github.com/borntoleave/CamWalkingGame`, branch `feature/pi-zero`.

Read §2 and §3 before doing anything. They contain constraints that will waste
hours if rediscovered.

---

## 0. TL;DR

A Raspberry Pi Zero 2 W was set up to run camWalk's MediaPipe pose tracking and
drive a Petoi Quaddle quadruped over USB serial. **The T1 latency gate failed in
all five measured configurations. The port was stopped by design, not
abandoned.**

The Pi itself is fully working: OS, camera, both Python libraries coexisting,
smoke test passing. Nothing is broken. The board is simply too slow for a closed
visual control loop.

**Do not restart the vision control loop on this board.** Do not treat §1's
numbers as tunable.

---

## 1. Measured results — treat as fact

Gate: **p95 capture-to-act ≤ 400ms AND sustained ≥ 3 fps.**
`--load 1` is a synthetic CPU stand-in for a web server built in a later task.

| # | poses | size | load | rot180 | fps | p95 | p50 | inference p50 | max | detected |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 640×480 | no | no | 1.90 | 686ms | 633ms | 566ms | 2236ms | 79% |
| 2 | 1 | 640×480 | no | no | 3.57 | 372ms | 335ms | 268ms | 3383ms | 88% |
| 3 | 2 | 640×480 | yes | yes | 1.57 | 791ms | 733ms | 584ms | 2054ms | 98% |
| 4 | 1 | 640×480 | yes | yes | 2.60 | 496ms | 439ms | 280ms | 4401ms | 81% |
| 5 | 1 | 320×240 | yes | yes | 2.90 | 486ms | 432ms | 279ms | 2319ms | 100% |

**Only run 2 passed, and it was not the gate** (no CPU load; taken before the
camera orientation fix). It had 28ms of margin with no web server, no serial
writes and no control law yet written.

### Conclusions, each with its evidence

1. **`num_poses=2` is impossible.** Inference *alone* is 566-584ms against a
   400ms **end-to-end** budget. No pipeline optimisation can recover 166ms+.
2. **`num_poses=1` halves inference (280ms) and still misses on fps.**
3. **Lowering capture resolution does nothing.** Runs 4→5 cut the output buffer
   4× (1.2MB→300KB) and saved **6ms**. Cause, from the libcamera log:
   ```
   configuring streams: (0) 320x240-RGB888/sRGB (1) 640x480-SGRBG10_CSI2P/RAW
   Selected sensor format: 640x480-SGRBG10_1X10/RAW
   ```
   The **sensor stays at 640×480**; a smaller main stream only adds an ISP
   downscale. This fallback is named in the spec and in the probe's own failure
   message, and **it is wrong**. Do not retry it.
4. **~153ms of pipeline overhead is resolution-independent.** End-to-end p50
   minus inference p50 = 159ms (run 4), 153ms (run 5). Sensor readout, ISP,
   request round-trip. Not reachable from Python.
5. **Tail latency reaches 2.0-4.4s in every run.** Cause **unidentified**.

---

## 2. Hard constraints — violating these wastes hours

### 2.1 Pin `mediapipe<1`

MediaPipe 1.x aarch64 wheels require ARMv8 Crypto Extensions. **No Broadcom
Raspberry Pi SoC has them**, including Pi 4 and Pi 5. Symptom:

```
FATAL ERROR: This binary was compiled with aes enabled,
but this feature is not available on this processor (go/sigill-fail-fast).
Illegal instruction
```

Verify on any Pi: `grep -m1 Features /proc/cpuinfo` → shows `crc32`, never `aes`.

### 2.2 Pin `numpy<2`

apt builds `simplejpeg` (picamera2's JPEG path) against NumPy 1.x. MediaPipe
installs 2.x, which shadows it inside a `--system-site-packages` venv. Symptom,
which **presents as a picamera2 import failure and is not one**:

```
ValueError: numpy.dtype size changed, may indicate binary incompatibility.
Expected 96 from C header, got 88 from PyObject
```

### 2.3 Bookworm only, 64-bit only

Trixie ships Python 3.13; MediaPipe needs ≤3.11 while picamera2 on Trixie builds
against 3.13. They cannot coexist. In Raspberry Pi Imager this is **"Raspberry Pi
OS (Legacy, 64-bit)"** — the unlabelled current entry is Trixie.

32-bit has no MediaPipe builds at all.

### 2.4 The venv must use `--system-site-packages`

picamera2 is apt-only (depends on libcamera, not pip-installable). MediaPipe is
pip-only. `pip install picamera2` does **not** work. This flag is the only thing
that lets them see each other — and the cause of 2.2.

### 2.5 The camera is mounted inverted

Pass `--rot180`, which applies `Transform(hflip=1, vflip=1)` in the VC4 ISP
(free; a numpy rotation would cost CPU this board lacks).

Effect: detection rate **79% → 98-100%**. It does **not** improve latency
(566→584ms, unchanged — this was hypothesised and disproved). Left uncorrected
it also inverts `signX` and `signY`, which would surface much later as a double
sign error.

---

## 3. Robot protocol — exact bytes

From `encodeCommand` (`app/index.html:3385-3394`) and `send()` (`:4574-4586`):

- **Lowercase** tokens: ASCII, params space-joined, **`\n` appended by sender**
- **Uppercase** tokens: binary, ASCII bytes of token + params + **`126` (`~`)**,
  **no newline**

| Purpose | Exact bytes |
|---|---|
| Bounded gait | `b"kwkF 3\n"` |
| Stand / stop | `b"kup\n"` |
| Force eye view (leg guard) | `b"ve\n"` |
| Joystick / aim | `bytes([74, 114, hx & 0xFF, rsy & 0xFF, 126])` |
| Direct joint angles | `I` + (jointId, angle) pairs + `126` |

Serial: **115200**, device `/dev/ttyACM0` (CDC-ACM, **not** `ttyUSB0`). Prefer
the `/dev/serial/by-id/...` symlink. The board **resets when the port opens** —
sleep ~2s before writing.

### 3.1 Safety: two command classes, very different risk

**`k<skill> <n>` is bounded and SAFE.** Per `reaction.h`, an argument below 200
is a gait-cycle count and 200+ is milliseconds; **either way the firmware ends
the gait itself.** A host that crashes mid-command leaves a stopped robot.

**`J` stick values are HELD BY FIRMWARE UNTIL POWER CYCLE.** A frozen or killed
host leaves the robot holding its last lean indefinitely. There is no command
lease and no read-back. **Prefer bounded gaits.** If you must stream `J`, the
teardown path has to flush zeros with a bounded deadline.

**`viewMode == 3` is the only thing keeping `J` out of the leg servos.** It is
asserted by `ve` and re-asserted every 5s. Anything changing the view in between
lets the next packet reach the legs. Inherited from the browser build; a
firmware `vk` lease is the real fix and is out of scope.

### 3.2 Verified skill names

**Only `wkF`, `wkB`, `up`** have been run on hardware by this project
(`app/index.html:6141-6143`).

`Instinct_Quaddle.h` contains more (`vtL`, `vt2L`, `vt90L`, `wkL`, `wk0L`,
`wk2L`, `trL`, `sideL`). **Only `L` variants are listed; do not guess
right-hand names.** This project once inferred a joint mapping from a comment
and made the robot hop instead of lean.

### 3.3 Joint map

`OpenCat.h:1120-1130`, DOF 6: joint **0 = head pan (±90°)**, **1 = head tilt**,
**2/3 = front legs**, **4/5 = back legs**.

The browser app drives only joints 2-5. **Joints 0 and 1 are never used by any
current code** and the head pan is fast and decoupled from the body.

---

## 4. System state

### 4.1 The Pi

| | |
|---|---|
| Host | `quadd-pipi.local`, user `qqqddd` |
| OS | Raspberry Pi OS Lite Bookworm 64-bit, `aarch64`, Python 3.11.2 |
| RAM | 416 MiB usable, **1 GB swap configured** |
| venv | `~/camwalk-env` (created with `--system-site-packages`) |
| Repo | `~/CamWalkingGame`, branch `feature/pi-zero` |
| Camera | OV5647 (Pi Camera v1 sensor), 120° lens, 22-pin 15cm FFC |
| WiFi | **2.4 GHz only** |
| Power | **Outer** micro-USB marked `PWR IN`; inner port is data-only |

Smoke test **passes**. Both libraries import in one interpreter, camera captures,
model loads.

### 4.2 Repo map

| Path | What |
|---|---|
| `pi/smoke_test.py` | Prerequisite gate. Names which of 5 steps failed + the fix. |
| `pi/t1_latency.py` | The kill gate. `evaluate()` is pure and unit-tested. |
| `pi/test_t1_latency.py` | 10 tests, laptop-only, no Pi needed. |
| `pi/README.md` | Setup §1-5 **verified on hardware**; §6-9 documentation only. |
| `docs/pi-zero-t1-results.md` | Detailed T1 record. |
| `docs/camwalk-hardware-findings.md` | Consolidated findings, both branches. |
| `docs/quaddle-pi-demo-ideas.md` | Demo concepts scored against these numbers. |
| `app/index.html` | The working browser build, ~43 fps. **Do not modify** for Pi work. |
| `app/vendor/mediapipe/models/pose_landmarker_lite.task` | 5.8MB, ships with clone |

Branch `feature/gemma-pi5` holds a VLM bridge: code complete, **never run**, no
Pi 5 was available.

### 4.3 Reproducing

```bash
ssh qqqddd@quadd-pipi.local
source ~/camwalk-env/bin/activate
cd ~/CamWalkingGame

python3 pi/smoke_test.py
python3 pi/t1_latency.py --seconds 30 --rot180 --load 1            # the gate
python3 pi/t1_latency.py --seconds 30 --rot180 --load 1 --poses 1
```

A person must be in frame and moving for the full 30s; the probe warns if nobody
was detected. Run from the repo root — `model_asset_path` is relative.

`--poses` and `--width/--height` are **off-spec** and the output says so twice.
`--rot180` is **not** off-spec: it corrects physical mounting rather than
changing what is measured.

Laptop tests, no hardware: `python3 -m unittest discover -s pi -p 'test_*.py'`

---

## 5. Verified vs unverified — read before asserting anything

### Verified on hardware

- All five T1 rows in §1
- Every constraint in §2 (each has a reproduced error string)
- Camera works end to end (pose detected in 79-100% of frames — a pose model
  cannot detect a person in a blank buffer)
- Smoke test passes; both libraries coexist
- `/dev/ttyACM0` not `ttyUSB0` (macOS enumerated the same board as
  `/dev/cu.usbmodem…`; `usbmodem` ⇒ CDC-ACM)
- Byte format in §3 (read from `encodeCommand` and `send()` in source)

### NOT verified — do not state as fact

- **Mechanical response.** T1 measures to the serial *write returning*. Servo
  and firmware latency beyond that is unmeasured.
- **The realistic-load figure.** Only idle (372ms) and pinned-core (486ms) were
  measured. `burn_cpu` pins a core at 100%; the real server is a stdlib HTTP
  page polled at ≤1Hz. The truth is between them.
- **The 2.0-4.4s tail stalls.** Cause unknown. Candidates: model warm-up, SD
  card, GC.
- **Turn-gait names** other than `wkF`/`wkB`/`up` (§3.2).
- **Head joints 0 and 1** — range, speed, audibility. Never exercised.
- **TFT eye modes** beyond `ve`. Never enumerated.
- **Power budget** under sustained camera + inference + servos.
- **Everything on `feature/gemma-pi5`.**
- Whether MediaPipe's Web LLM Inference API accepts **images for Gemma 4** —
  Google's docs name Gemma 3n.

---

## 6. Do not do these

1. **Do not restart the closed vision control loop on this board.** Measured
   impossible; §1 explains why each fallback fails.
2. **Do not lower capture resolution to chase latency.** The sensor mode does
   not change (§1 conclusion 3).
3. **Do not edit the pinned constants** in `pi/t1_latency.py` (`NUM_POSES`,
   `CAPTURE_SIZE`, `GATE_P95_MS`, `GATE_MIN_FPS`). Unit tests pin them
   deliberately so the gate keeps describing what would ship. Use the CLI flags.
4. **Do not describe any build as "following" a person.** The ~7°/joint lean
   cannot re-point a chassis camera, and v1 has no steering.
5. **Do not guess firmware skill names** (§3.2).
6. **Do not stream `J` without a bounded teardown** (§3.1).
7. **Do not modify `app/index.html`** for Pi work. It is the working ~43fps
   browser build on `main`.
8. **Do not plan to download models at a venue.** Measured ~275 KB/s with client
   isolation; a 3.11GB model never completed. Use `HF_HUB_DISABLE_XET=1` if HF
   transfers fail with `CAS Client Error`.

---

## 7. Open work, in priority order

1. **Decide the path forward.** Change board (Pi 5), repurpose the Zero 2 W for
   event-driven work, or stay with the browser build. See
   `docs/camwalk-hardware-findings.md` §9.
2. **Exercise joints 0 and 1.** ±90° head pan is the fastest unused actuator on
   the robot and is central to several proposed demos. Cheap to characterise.
3. **Audio hardware.** The Zero 2 W has **no microphone and no audio output**.
   Published figures put wake-word detection in real time on this board (RTF
   0.053), making audio its only fast sense — but it needs a USB sound card or
   an I2S MEMS mic (INMP441). Unlocks the most promising demo direction.
4. **Enumerate TFT eye modes** in firmware.
5. **Investigate the tail stalls** before anything timing-sensitive.
6. **Optionally** re-measure T1 under a realistic load to close the 372/486ms
   bracket. Will not change the verdict.
7. Open a PR; `feature/pi-zero` and `feature/gemma-pi5` are both unmerged.

---

## 8. Meta — how this investigation went wrong, so you don't repeat it

Four plan assumptions were wrong, all caught only by running the thing:

| Assumed | Actual |
|---|---|
| "~4-6 fps, plan for 5" | **1.57-2.90.** Estimate came from chip-class benchmarks, not this chip. |
| `pip install mediapipe` | 1.x cannot execute on any Pi. |
| (nothing about NumPy) | 2.x breaks apt-built picamera2. |
| "Lower the resolution" as a fallback | Does nothing. |

Three in-session hypotheses were also wrong and were tested rather than assumed:
the inverted image was *not* inflating latency; `--poses 1` performed *better*
than predicted idle; the 153ms overhead was *not* memory bandwidth.

**The pattern: every estimate sourced from documentation or benchmarks was
wrong, and every number from the hardware was right.** Measure before asserting.
Where this document says "unverified," it means it.
