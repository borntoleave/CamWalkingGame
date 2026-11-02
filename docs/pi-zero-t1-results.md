# T1 latency gate on a Pi Zero 2 W — measured, 2026-11-01

**Verdict: FAILED in every configuration. Do not build v1 on this board.**

First time this project has had real numbers instead of estimates. The plan
budgeted 5fps from chip-class benchmarks; the board delivers 1.6-2.9.

## Hardware actually under test

| | |
|---|---|
| Board | Raspberry Pi Zero 2 W, 416Mi usable RAM after GPU split |
| Camera | OV5647 (Pi Camera v1 sensor), 120° lens, 22-pin 15cm FFC |
| OS | Raspberry Pi OS Lite **Bookworm** 64-bit, `aarch64` |
| Python | 3.11.2 |
| MediaPipe | 0.10.x (`mediapipe<1`, see "MediaPipe 1.x is unrunnable") |
| Model | `pose_landmarker_lite.task`, VIDEO mode, confidence 0.5 |
| Swap | 1GB |

## Results

Gate: **p95 capture-to-write ≤ 400ms AND sustained ≥ 3fps.**
`--load 1` is the synthetic CPU stand-in for the T6 web server.

| # | poses | size | load | rot180 | fps | p95 | p50 | inference p50 | max | detected |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 640×480 | no | no | 1.90 | 686ms | 633ms | 566ms | 2236ms | 79% |
| 2 | 1 | 640×480 | no | no | 3.57 | **372ms** | 335ms | 268ms | 3383ms | 88% |
| 3 | 2 | 640×480 | yes | yes | 1.57 | 791ms | 733ms | 584ms | 2054ms | 98% |
| 4 | 1 | 640×480 | yes | yes | 2.60 | 496ms | 439ms | 280ms | 4401ms | 81% |
| 5 | 1 | 320×240 | yes | yes | 2.90 | 486ms | 432ms | 279ms | 2319ms | 100% |

Only run 2 passed, and it was not the gate: no load, and before the camera
orientation was corrected.

## What the numbers say

**1. `num_poses = 2` is impossible here.** Inference alone is 566-584ms against
a 400ms *end-to-end* budget — 46% over before capture, conversion or serial are
counted. This answers **U3**: not affordable, and not close.

**2. Dropping to one pose halves inference and is still not enough.** 566→280ms,
but 2.60fps under load against a 3.0 floor.

**3. Lowering capture resolution does nothing.** Runs 4→5 cut the output buffer
4x (1.2MB→300KB) and saved **6ms**. The reason is in the libcamera log:

```
configuring streams: (0) 320x240-RGB888/sRGB (1) 640x480-SGRBG10_CSI2P/RAW
Selected sensor format: 640x480-SGRBG10_1X10/RAW
```

The **sensor still runs at 640×480**; a smaller main stream only adds an ISP
downscale. Readout, unicam transfer and ISP cost are unchanged. This fallback
is documented in the spec and the probe's own failure message; it does not
work, and the reason is structural rather than tunable.

**4. There is ~153ms of resolution-independent pipeline overhead.** End-to-end
p50 minus inference p50 is 159ms (run 4) and 153ms (run 5). That is sensor
readout plus ISP plus request round-trip. It is not memory bandwidth, and it
cannot be optimised from Python.

**5. The passing run had 28ms of margin and an unfinished system.** Run 2 hit
372ms against 400ms with **no web server, no serial writes and no control
logic**. All three still have to fit. Run 4 shows what happens when one of them
arrives.

**6. Tail latency is worse than p95 suggests.** Maxima of 2.0-4.4s across every
run, growing to 4401ms in run 4. A control loop acting on a four-second-old
observation makes the robot lurch. p95 would have hidden this; the probe
reports max for this reason.

## Corrections to the plan, forced by measurement

| Plan said | Reality |
|---|---|
| "~4fps, 5-6fps with the lite model. Plan for 5." | **1.57-2.90fps.** The estimate came from chip-class benchmarks, not this chip. ~2-3x optimistic. |
| `pip install mediapipe` (unversioned) | **MediaPipe 1.x cannot run on any Raspberry Pi.** See below. |
| Nothing about NumPy | **NumPy 2.x breaks apt-built picamera2.** See below. |
| Lowering resolution is a viable fallback | **It is not.** The sensor mode does not change. |

### MediaPipe 1.x is unrunnable on Raspberry Pi

```
FATAL ERROR: This binary was compiled with aes enabled,
but this feature is not available on this processor
Illegal instruction
```

MediaPipe 1.2.0's aarch64 wheel requires the ARMv8 Cryptography Extensions.
Broadcom ships every Pi SoC without them. Confirmed on this board:

```
$ grep -m1 Features /proc/cpuinfo
Features : fp asimd evtstrm crc32 cpuid        # crc32 yes, aes no
```

This applies to the Pi 4 and Pi 5 too. **Pin `mediapipe<1`.**

### NumPy 2.x breaks apt-built picamera2

```
ValueError: numpy.dtype size changed, may indicate binary incompatibility.
Expected 96 from C header, got 88 from PyObject
```

`--system-site-packages` is what lets picamera2 (apt, needs libcamera) and
MediaPipe (pip) see each other, and it is also what lets pip shadow a system
package. apt builds `simplejpeg` against NumPy 1.x; MediaPipe pulls 2.x.
**Pin `numpy<2`.** It surfaces as a picamera2 import failure, so it reads as a
missing package when it is not.

### The camera module is mounted inverted

A captured still showed the subject upside down. Correcting it in the ISP
(`Transform(hflip=1, vflip=1)`, free on the VC4) raised detection from 79% to
98-100%.

It did **not** improve latency — 566→584ms, unchanged. A hypothesis that
inverted input was causing extra detector re-runs was tested and disproved.

It would also have inverted `signX` and `signY`, surfacing as a double sign
error during the T4 stand test.

## One question this does not settle

`burn_cpu` pins a core at 100% indefinitely. The real T6 server is a stdlib
HTTP status page polled at ≤1Hz — nothing like that. The spec chose a
pessimistic stand-in deliberately ("the right direction to be wrong in for a
gate"), so this is not a flaw, but it means the truth sits between 372ms
(idle) and 486ms (pinned core).

**It does not change the verdict.** Even the idle number leaves 28ms for a web
server, serial writes and the entire control law. Measuring against a realistic
load would narrow the bracket; it would not create headroom that is not there.

## Options, honestly

1. **Change the board.** A Pi 5 (Cortex-A76 @2.4GHz vs A53 @1GHz) is the direct
   fix. Note the same `mediapipe<1` constraint applies — no Pi has AES.
2. **Abandon the closed control loop on this board** and keep the Zero 2 W for
   something event-driven, where seconds of latency cost nothing. The bounded
   `k<skill> <cycles>` gait pattern on `feature/gemma-pi5` is exactly that
   shape and has no held-command failure mode.
3. **Keep the browser build.** It runs at ~43fps on a laptop and already works.

What is **not** on the table is proceeding to T2 on this board. T1 exists to
prevent that, and it did its job: this cost one evening instead of the week
that `robot.py`, `tracker.py`, `web.py`, `config.py` and the service unit
would have taken.

## Reproducing

```bash
source ~/camwalk-env/bin/activate
cd ~/CamWalkingGame
python3 pi/smoke_test.py
python3 pi/t1_latency.py --seconds 30 --rot180 --load 1          # the gate
python3 pi/t1_latency.py --seconds 30 --rot180 --load 1 --poses 1 --width 320 --height 240
```

Stand in frame and move for the full 30s; inference on an empty scene is not
the workload. Off-spec runs say so twice, at start and beside the verdict.
