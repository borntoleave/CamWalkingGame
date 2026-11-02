# camWalk on real hardware — consolidated findings

**Period covered:** 2026-10-24 to 2026-11-01
**Branches:** `feature/pi-zero` (camera port), `feature/gemma-pi5` (VLM bridge)
**Status:** Pi Zero 2 W port **stopped at the T1 gate**. Browser build unaffected.

Everything here was measured. Where something is an estimate or untested, it
says so. This document exists because the plans it corrects were written from
documentation and benchmarks, and four of their load-bearing assumptions turned
out to be wrong.

---

## 1. The headline

**A Raspberry Pi Zero 2 W cannot run the camWalk control loop.**

| | Measured | Required | |
|---|---|---|---|
| Frame rate | **1.57 – 2.90 fps** | ≥ 3.0 | FAIL |
| p95 capture-to-act | **486 – 791 ms** | ≤ 400 ms | FAIL |

Realistic figure for a working configuration: **~2.6–2.9 fps.**
For comparison, the browser build on an M1 laptop runs at **~43 fps**, roughly
**15x faster**.

The plan budgeted 5 fps. That came from benchmarks for "this chip class" rather
than this chip, and was **2–3x optimistic**.

---

## 2. Hardware under test

| | |
|---|---|
| Board | Raspberry Pi Zero 2 W (BCM2710, 4× Cortex-A53 @1GHz) |
| RAM | 416 MiB usable after GPU split, 1 GB swap |
| Camera | OV5647 (Pi Camera v1 sensor), 120° lens, 22-pin 15 cm FFC |
| OS | Raspberry Pi OS Lite **Bookworm** 64-bit, `aarch64` |
| Python | 3.11.2 |
| MediaPipe | 0.10.x (`mediapipe<1` — see §5.1) |
| NumPy | 1.26.4 (`numpy<2` — see §5.2) |
| Model | `pose_landmarker_lite.task`, VIDEO mode, confidence 0.5 |

---

## 3. T1 latency gate — all five runs

Gate: **p95 capture-to-write ≤ 400 ms AND sustained ≥ 3 fps.**
`--load 1` is a synthetic CPU stand-in for the T6 web server.

| # | poses | size | load | rot180 | fps | p95 | p50 | inference p50 | max | detected |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 640×480 | no | no | 1.90 | 686 ms | 633 ms | 566 ms | 2236 ms | 79% |
| 2 | 1 | 640×480 | no | no | 3.57 | **372 ms** | 335 ms | 268 ms | 3383 ms | 88% |
| 3 | 2 | 640×480 | yes | yes | 1.57 | 791 ms | 733 ms | 584 ms | 2054 ms | 98% |
| 4 | 1 | 640×480 | yes | yes | 2.60 | 496 ms | 439 ms | 280 ms | 4401 ms | 81% |
| 5 | 1 | 320×240 | yes | yes | 2.90 | 486 ms | 432 ms | 279 ms | 2319 ms | 100% |

Only run 2 passed, and **it was not the gate**: no CPU load, and taken before
the camera orientation was corrected.

### 3.1 Why it fails, in order of weight

**`num_poses = 2` is structurally impossible.** Inference alone is 566–584 ms
against a 400 ms *end-to-end* budget — 46% over before capture, conversion or
serial are counted. This closes **U3** in the spec: not affordable, not close.

**One pose halves inference and still misses.** 566 → 280 ms, but 2.60 fps
under load against a 3.0 floor.

**Lowering capture resolution does nothing.** Runs 4→5 shrank the output buffer
4x (1.2 MB → 300 KB) and saved **6 ms**. The libcamera log shows why:

```
configuring streams: (0) 320x240-RGB888/sRGB (1) 640x480-SGRBG10_CSI2P/RAW
Selected sensor format: 640x480-SGRBG10_1X10/RAW
```

The **sensor still runs at 640×480**. A smaller main stream only adds an ISP
downscale; readout, unicam transfer and ISP cost are unchanged. This fallback
is named in the spec *and* in the probe's own failure message, and it is wrong.

**~153 ms of overhead sits outside inference and outside Python's reach.**
End-to-end p50 minus inference p50 is 159 ms (run 4) and 153 ms (run 5):
sensor readout, ISP, request round-trip. Not memory bandwidth — proven by the
resolution test above.

**The one passing run had 28 ms of margin and an unfinished system.** Run 2 hit
372 ms against 400 ms with **no web server, no serial writes and no control
law**. All three still have to fit. Run 4 shows what happens when one arrives.

**Tail latency is worse than p95 suggests.** Maxima of 2.0–4.4 s in every run,
peaking at 4401 ms. A loop acting on a four-second-old observation makes the
robot lurch, and "rare" on a demo floor means "in front of people." p95 hides
this, which is why the probe reports max.

### 3.2 A caveat that does not change the verdict

`burn_cpu` pins a core at 100% indefinitely. The real T6 server is a stdlib
HTTP status page polled at ≤1 Hz — nothing like that. The spec chose a
pessimistic stand-in deliberately ("the right direction to be wrong in for a
gate"), so this is not a flaw, but the truth sits between 372 ms (idle) and
486 ms (pinned core).

It does not create headroom that is not there. Even the idle number leaves
28 ms for a web server, serial writes and the entire control law.

---

## 4. Camera findings

**The OV5647 works, confirmed end to end.** `rpicam-hello` enumerates it,
libcamera loads `ov5647.json`, and MediaPipe found a human pose in **79–100%**
of frames. That last figure is the real proof: a pose model cannot detect a
person in a blank or corrupt buffer.

**The module is mounted inverted.** A captured still showed the subject upside
down. Correcting it in the ISP via `Transform(hflip=1, vflip=1)` — free on the
VC4, where a numpy rotation would cost CPU this board has none of — raised
detection from **79% to 98–100%**.

It did **not** improve latency: 566 → 584 ms, unchanged. A hypothesis that
inverted input caused extra detector re-runs was tested and **disproved**.

Left uncorrected, it would also have inverted `signX` and `signY`, surfacing
much later as a baffling double sign error during the T4 stand test.

**The 120° lens is better than the plan assumed.** The spec warns that v1 is
aim-only and "a person walking sideways leaves the camera's view and is not
recovered," reasoning from a standard ~62° lens. A 120° field of view makes
that materially less punishing. Not enough to rescue the gate, but it would
have helped v1 had the loop closed.

---

## 5. Software compatibility — three traps

### 5.1 MediaPipe 1.x cannot run on any Raspberry Pi

```
FATAL ERROR: This binary was compiled with aes enabled,
but this feature is not available on this processor
Illegal instruction
```

MediaPipe 1.2.0's aarch64 wheel requires the **ARMv8 Cryptography Extensions**.
Broadcom ships every Pi SoC without them. Confirmed on this board:

```
$ grep -m1 Features /proc/cpuinfo
Features : fp asimd evtstrm crc32 cpuid          # crc32 present, aes absent
```

**This applies to the Pi 4 and Pi 5 as well.** Any future Pi work must pin
`mediapipe<1`. The plan said `pip install mediapipe`, unversioned — correct
when written, silently broken once 1.x shipped.

### 5.2 NumPy 2.x breaks apt-built picamera2

```
ValueError: numpy.dtype size changed, may indicate binary incompatibility.
Expected 96 from C header, got 88 from PyObject
```

`--system-site-packages` is what lets picamera2 (apt, depends on libcamera) and
MediaPipe (pip) see each other. It is also what lets pip **shadow** a system
package. apt builds `simplejpeg` against NumPy 1.x; MediaPipe pulls 2.x; the
C extension then loads against the wrong ABI.

Pin `numpy<2`. It surfaces as a *picamera2 import failure*, so it reads as a
missing package when it is nothing of the kind.

### 5.3 Bookworm is required, Trixie will not work

Debian Trixie ships Python 3.13. MediaPipe supports ≤ 3.11, while picamera2 on
Trixie builds against 3.13 — they cannot coexist. In Raspberry Pi Imager this
means choosing **"Raspberry Pi OS (Legacy, 64-bit)"**; the current entry is
Trixie.

This constraint is specific to the MediaPipe path. The Gemma bridge on
`feature/gemma-pi5` has no MediaPipe and is indifferent to the OS version.

---

## 6. Setup and logistics findings

These cost more wall-clock time than any technical problem.

**A laptop without an SD slot cannot configure a Pi.** A MacBook Air has no
card reader and only USB-C ports. A Pi cannot be configured without writing its
card — the `firstrun.sh` and `userconf.txt` routes all require mounting the
boot partition. There is no software workaround. **A USB-C SD reader is a
hard prerequisite**, and it is the item people assume they already have.

**Pi-to-laptop USB does nothing.** Stock Raspberry Pi OS does not enable USB
gadget mode. The Zero 2 W *can* do ethernet-over-USB with `dtoverlay=dwc2` and
`modules-load=dwc2,g_ether`, but that is configuration you cannot apply until
you can already reach the Pi. On a Pi 5 the USB-C port is power-only.

**Imager's WiFi panel keeps the old password when you change the SSID.** It
reads "Saved (hidden) — leave blank to keep". Change the network name without
retyping the password and the Pi silently fails to authenticate, which looks
exactly like a dead Pi.

**Verify the flash before booting.** With the card in a reader:

```bash
ls /Volumes/bootfs/firstrun.sh        # customisation is queued
ls /Volumes/bootfs/kernel*.img        # kernel8 + kernel_2712 only = 64-bit
grep -o 'systemd.run=[^ ]*' /Volumes/bootfs/cmdline.txt
```

Four kernels (`kernel.img`, `kernel7.img`, `kernel7l.img`, `kernel8.img`) means
a **32-bit** image, which has no MediaPipe builds. An absent `firstrun.sh` on a
card that has been booted means the customisation already ran and is now in the
ext4 rootfs, which macOS cannot read — re-flash rather than fight it.

**Venue networks isolate clients.** Measured at a hackathon on 2026-10-24: ARP
resolved a Pi's MAC, the gateway answered pings at 180 ms, and the Pi dropped
100% of packets. 332 hosts in the ARP table, one reachable. A correctly
configured Pi would still have been unreachable. **Use a phone hotspot** — and
note the Zero 2 W is **2.4 GHz only**, so an iPhone needs "Maximize
Compatibility" on.

**Do not plan to download models at a venue.** Sustained ~275 KB/s, about an
hour per gigabyte. A 3.11 GB model never completed: one attempt died with a
HuggingFace Xet transfer error, the retry died on DNS. `HF_HUB_DISABLE_XET=1`
falls back to plain HTTP and resumes better on an unreliable link.

---

## 7. The Gemma 4 / Pi 5 branch (`feature/gemma-pi5`)

Separate attempt, same week. **Code complete, never run** — no Pi 5 was
available.

**A VLM cannot be the control loop.** Gemma 4 E2B runs at 3–8 tok/s on a Pi 5,
so a decision takes seconds, while the aim loop needs ≥5 Hz. Three orders of
magnitude apart. The design therefore uses it as a slow semantic layer that
picks one discrete behaviour.

**Bounded gaits make the slow loop the safe one.** `app/index.html:6351-6360`:
`kwkF 3` is terminated by the **firmware**. Streaming `J` stick values — what
the browser demo and the Pi Zero plan both do — leaves the robot holding its
last lean until power cycle if the host dies. A bounded gait does not. A frozen
host leaves a robot that already stopped.

This is worth carrying forward: the Zero 2 W is poorly suited to a closed
control loop and perfectly adequate for an event-driven one.

**GGUF and LiteRT-LM are not interchangeable.** llama.cpp reads `.gguf`;
MediaPipe LLM Inference and the LiteRT-LM runtime read `.litertlm`. Files
suffixed `-web` are converted for WebGPU in a browser, `-gpu` for a GPU
delegate — **neither is a CPU build**, so neither is what a Pi wants.

Verified filenames for the llama.cpp path (HF API, 2026-10-24):
`gemma-4-E2B-it-Q4_K_M.gguf` (3.11 GB) and `mmproj-F16.gguf` (940 MB). Without
the mmproj, llama-server starts cleanly and silently ignores images.

---

## 8. Corrections forced on the plans

| Plan said | Measured reality |
|---|---|
| "~4 fps, 5–6 with the lite model. Plan for 5." | **1.57–2.90 fps.** 2–3x optimistic. |
| `pip install mediapipe` | **1.x cannot execute on any Pi.** Pin `mediapipe<1`. |
| (nothing about NumPy) | **2.x breaks apt-built picamera2.** Pin `numpy<2`. |
| "Lower the capture resolution" as a fallback | **Does nothing.** The sensor mode does not change. |
| Section 5 smoke test as an inline heredoc | **Unusable when pasted** — indentation breaks Python and the terminator. Now `pi/smoke_test.py`. |
| Camera orientation unstated | **Mounted inverted.** Costs 20 points of detection rate and would invert both sign conventions. |

---

## 9. Options from here

1. **Change the board.** A Pi 5 (Cortex-A76 @2.4 GHz vs A53 @1 GHz) is the
   direct fix for the loop. The `mediapipe<1` constraint still applies.
2. **Keep the Zero 2 W for event-driven work.** Where seconds of latency cost
   nothing, this board is fine. The bounded-gait design on `feature/gemma-pi5`
   is exactly that shape.
3. **Keep the browser build.** ~43 fps, already working, unaffected by any of
   this.

**Not an option: proceeding to T2 on this board.** T1 exists to prevent that.
It cost one evening instead of the week that `robot.py`, `tracker.py`,
`web.py`, `config.py`, the service unit and floor tuning would have taken
before hitting the same wall.

---

## 10. Reproducing

```bash
source ~/camwalk-env/bin/activate
cd ~/CamWalkingGame

python3 pi/smoke_test.py                                   # prerequisite gate
python3 pi/t1_latency.py --seconds 30 --rot180 --load 1    # the v1 gate
python3 pi/t1_latency.py --seconds 30 --rot180 --load 1 --poses 1
python3 pi/t1_latency.py --seconds 30 --rot180 --load 1 --poses 1 --width 320 --height 240
```

Stand in frame and move for the full 30 s; inference on an empty scene is not
the workload, and the probe will say so if nobody was seen.

`--poses` and `--width/--height` are off-spec and the output says so twice, at
start and beside the verdict. `--rot180` is **not** off-spec: it corrects the
physical mounting rather than changing what is measured.

## 11. What remains unverified

- **Mechanical response.** T1 measures to the serial write returning, which is
  not servo movement. Firmware and servo latency past that point is unmeasured.
- **The realistic-load figure.** Only idle and pinned-core were measured; the
  true number lies between them (§3.2).
- **The 2–4.4 s tail stalls.** Cause unidentified. Candidates: model warm-up,
  SD card, GC. Would need understanding before any floor work.
- **Everything on `feature/gemma-pi5`.** Written, laptop-tested, never run on
  a Pi.
