# Quaddle + Raspberry Pi Zero 2 W — demo concepts

**Date:** 2026-11-02
**Grounding:** measured hardware numbers from `docs/camwalk-hardware-findings.md`,
plus the command surface in `app/index.html`.

Every idea below is scored against what the hardware actually does, not what a
spec sheet suggests. Where something is unverified, it says so.

---

## 1. The organizing constraint

T1 measured this board at **1.57-2.90 fps** on pose inference with ~153ms of
pipeline overhead that no setting touches. A closed visual control loop is off
the table and will stay off the table.

But the same week's research shows **wake-word audio runs in real time** on this
board: Porcupine runs real-time even on the original Zero, and VoxRT reports an
RTF of 0.053 on a Zero 2 W — roughly 19x faster than real time.

**The Pi Zero 2 W is a poor real-time vision controller and a good real-time
listener.** That inverts the project's original premise and should drive demo
selection.

### Capability budget

| Capability | Measured / known | Verdict |
|---|---|---|
| Pose inference | 2.6-2.9 fps, 280ms, 153ms fixed overhead | Event detection only |
| Capture-to-act p95 | 486-791ms, tail to 4.4s | No servo loops |
| Wake word | RTF 0.053 (third-party, **unverified here**) | Real time |
| Small LLM | SmolLM2-135M is the 512MB community pick | Seconds per reply |
| Linux services | Full Debian, Python, WiFi AP, storage | Free |
| RAM | 416 MiB usable + 1GB swap | The binding limit |

### The "why Pi at all" test

The ESP32-S3 already does gaits, joystick input, the TFT eyes and WiFi, and has
a voice module on `SERIAL_VOICE`. **Any demo that uses none of camera, Linux
networking, real ML, or persistent storage should drop the Pi.** Each idea below
states what it draws on.

### What the robot can be told to do

From `app/index.html`:

| Token | Meaning | Demo relevance |
|---|---|---|
| `k<skill> <n>` | bounded gait, **firmware-terminated** | Safe under any host latency |
| `I` (binary) | direct per-joint angles | **Arbitrary choreography, no firmware work** |
| `J` (binary) | joystick stick values | Held until changed — needs a live host |
| `v<mode>` | TFT eye view mode | Expression and reaction |

Two things matter here. **Bounded gaits self-terminate**, so a host that freezes
leaves a stopped robot — this is what makes slow, latency-tolerant demos *safer*
than the streaming ones. And `I` reaches joints directly; the browser app only
drives legs 2-5, but firmware exposes **joint 0 (head pan, ±90°)** and joint 1
(head tilt), which no current demo uses.

---

## 2. Tier 1 — build these first

### 1.1 Event photo booth on the robot's own WiFi

The robot watches for a person, frames them using head pan, takes a photo, and
serves it from a gallery hosted on its own WPA2 access point. Visitors join
`quaddle` on their phone and download their picture. No internet, no app.

**Uses:** camera, Linux web server, WiFi AP, storage. Every Pi strength, none of
its weaknesses.

**Why it fits:** framing a shot is a *slow* task. Two frames per second is
generous when you are waiting for someone to stand still and smile. The head-pan
range (±90°) does the aiming the body lean never could.

**Why not a laptop:** the robot is the venue infrastructure. Nothing else to set
up, nothing to install, works where there is no network at all.

**Effort:** moderate. Section 8 of `pi/README.md` already specifies AP mode;
`scripts/demo_server.py` is the in-repo stdlib server pattern. The browser app
already had a photo feature (`PHOTO_LOTTERY_ENABLED`, currently false).

**Risks:** photographing the public needs a visible notice and a retention
policy. Keep images on the Pi, delete on shutdown, say so on the page.

### 1.2 Voice command, fully offline

Wake word plus a small command vocabulary: "Hey Quaddle — sit / come / spin /
look at me." Maps to bounded gait tokens over serial.

**Uses:** real-time audio ML, Linux. The one place this board is genuinely fast.

**Why not the ESP32 voice module:** fixed vocabulary and no custom wake word. A
Pi gives you your own trigger phrase, your own command set, and Python to extend
it. That is a product difference, not a reimplementation.

**Effort:** low-moderate. Porcupine or openWakeWord, then a token lookup. The
decision layer is the same shape as `pi5/behaviour.py` on `feature/gemma-pi5`:
pure, allow-listed, default-deny. That file ports directly.

**Risk — BOM gap:** **the Pi Zero 2 W has no microphone and no audio input.**
This needs a USB sound card plus mic, or an I2S MEMS mic (INMP441) on the GPIO
header. Neither is in the current build. Settle this before planning around it.

### 1.3 Sentry mode

The robot idles. When the camera sees motion or a person, it wakes, pans its
head toward them, changes its TFT expression and does a short bounded gait. Then
settles back.

**Uses:** camera, always-on Linux, local logging.

**Why it fits the measurement exactly:** "is someone there" is a question 2fps
answers perfectly well. There is no loop to close — detection is an *event*, and
the response is a fire-and-forget bounded gait.

**Why it demos well:** it runs unattended at a booth for hours and reacts to
every person who walks up. No operator, no laptop, no explaining.

**Effort:** low. Frame differencing alone may be enough; pose detection is
already proven to load and run.

### 1.4 Stop-and-scan seeking

The honest version of "follow me." Look, decide, commit to a **bounded** burst,
stop, look again. Deliberately built around 2fps instead of fighting it.

**Uses:** camera, and the bounded-gait safety property.

**Why this matters beyond the demo:** it converts the T1 failure into a design
constraint. A continuous visual servo is impossible here; a discrete
sense-decide-act cycle at 2Hz is comfortable. It also needs **steering**, which
v1 cut (D5) and milestone 2 defers — gaits exist in `Instinct_Quaddle.h` (`vtL`,
`wkL`), but **only `L` variants are listed and the right-hand names must be
confirmed on hardware, not guessed.**

**Effort:** moderate. The largest unknown is turn-gait behaviour on the floor.

---

## 3. Tier 2 — strong, more effort or more risk

### 2.1 Classroom console over the robot's AP

Phone or laptop joins the robot's network and gets a control page: drive it,
view the camera, adjust parameters, run saved routines. No installs, no school
network admin, no accounts.

**Uses:** Linux networking, web server.

**Why it is worth more than it looks:** a class of thirty with no infrastructure
dependency is an entirely different proposition from one that needs IT approval.
Pairs naturally with the curriculum gap — **there is no Quaddle curriculum as of
2026-11-01**, so this is open ground rather than a duplicate.

**Caveat:** AP and client mode on one radio at once is reported fragile. One
mode or the other.

### 2.2 The robot as a data instrument

Log joint angles, gait phase, battery and timing to CSV; plot in the browser.
Students measure their robot rather than just driving it.

**Uses:** storage, Python, web server. No camera, no ML.

**Why it is interesting:** it reframes the robot as laboratory equipment for
physics and data science, not only a coding toy. Low technical risk, high
curriculum value.

### 2.3 Choreography to music

`I` gives direct per-joint angles, so arbitrary poses need no firmware work. The
Pi sequences keyframes and plays audio.

**Uses:** Linux audio, storage. **No camera, no ML, no latency exposure at all.**

**Why it is a reliable showpiece:** nothing in it can be too slow. It is the
lowest-risk crowd-pleaser available, and it is the one demo that would survive a
board even weaker than this one. Note the same **audio-output BOM gap** as 1.2 —
no analog out on a Zero 2 W.

**Bonus:** head pan and tilt (joints 0 and 1) are unused by every current demo
and would make choreography visibly richer than leg-only routines.

### 2.4 Face-aware greeter

Recognises returning visitors and greets them differently. Memorable at an event
in a way generic reactions are not.

**Uses:** camera, ML, storage.

**Risk:** biometric data. Needs explicit opt-in, on-device-only storage, and
deletion at end of day. Worth doing only with that handled properly, and worth
checking against local rules before a public event.

### 2.5 Multi-robot coordination

One Pi driving several robots, choreographed. The Pi becomes a conductor rather
than a brain.

**Uses:** Linux, multiple serial or BLE links.

**Why:** three Quaddles in formation is dramatically more impressive than one,
and the per-robot cost is a USB cable. **Unverified:** how many serial links a
Zero 2 W sustains cleanly, and whether its single OTG port needs a hub.

---

## 4. Tier 3 — speculative or blocked

| Idea | Status |
|---|---|
| On-board VLM scene understanding | Needs a Pi 5. Gemma 4 E2B is 3-8 tok/s *there*; a Zero 2 W cannot hold the model at all. Code exists on `feature/gemma-pi5`, never run. |
| Small LLM (SmolLM2-135M) for free-form commands | Runs in 512MB per community reports, **unverified here**. Seconds per reply. Only viable where latency is invisible. |
| Real-time visual tracking / ball chasing | **Measured impossible.** 2fps with a 4.4s tail. Do not attempt on this board. |
| Autonomous navigation / SLAM | Far beyond this compute budget. |
| Cloud-API vision or voice | Works at low bandwidth (~100KB/request), but a venue network may isolate clients or be saturated. Measured 275 KB/s at one event. Offline demos are more reliable. |

---

## 5. Ranked shortlist

Scored on demo impact, effort, and risk of failing in public.

| # | Demo | Impact | Effort | Public-failure risk |
|---|---|---|---|---|
| 1 | Event photo booth (1.1) | High | Moderate | Low |
| 2 | Sentry mode (1.3) | High | Low | Low |
| 3 | Choreography (2.3) | High | Low | **Lowest** |
| 4 | Voice command (1.2) | High | Low-moderate | Low, **BOM gap** |
| 5 | Classroom console (2.1) | Moderate, high strategic | Moderate | Low |
| 6 | Stop-and-scan seek (1.4) | Moderate | Moderate | Moderate |

**If one thing ships: the photo booth.** It uses every Pi strength, avoids every
measured weakness, gives visitors something to take home, and needs no internet.

**If a demo must not fail in front of people: choreography.** It has no sensing
path, so there is nothing in it that latency can break.

---

## 6. What to avoid, and why

- **Anything described as "follows you."** The body lean is ~7°/joint and cannot
  re-point a chassis camera; without steering the robot does not follow. v1 cut
  stepping for exactly this reason, and `pi/README.md` is explicit that it must
  not be described that way.
- **Streaming `J` stick values.** They are **held by the firmware until power
  cycle**. A frozen Pi leaves the robot holding a lean indefinitely. Prefer
  bounded `k<skill> <n>`, which the firmware ends itself.
- **Unverified gait names.** `Instinct_Quaddle.h` lists only `L` variants.
  Guessing the right-hand name is how this project once made the robot hop
  instead of lean.
- **Demos that need the venue network.** Measured: client isolation blocking all
  device-to-device traffic, and 275 KB/s bandwidth. Host your own AP.
- **Any latency-sensitive loop.** The 2-4.4s tail stalls are unexplained and
  present in every run.

---

## 7. Gaps to close before committing

1. **Audio hardware.** No mic and no audio out on a Zero 2 W. USB sound card or
   I2S MEMS mic. **Blocks 1.2 and 2.3.**
2. **The 2-4.4s tail stalls.** Unexplained. Harmless for event-driven demos,
   fatal for anything timed.
3. **Turn gaits on hardware.** Right-hand variants unconfirmed. **Blocks 1.4.**
4. **Head joints 0 and 1.** Firmware exposes ±90° pan; no demo uses it and the
   browser app drives only joints 2-5. Verify range and speed — it is the single
   most underused capability on the robot.
5. **Power budget.** Sustained camera plus inference shortens runtime by an
   unmeasured amount. A shared battery does not guarantee the Pi and servos die
   together.
6. **Multi-robot serial limits** for 2.5.

---

## 8. Sources

Measured in this project: `docs/camwalk-hardware-findings.md`,
`docs/pi-zero-t1-results.md`.

External, 2026-11-02:
- [Picovoice: speech recognition on Raspberry Pi](https://picovoice.ai/blog/speech-recognition-on-raspberrypi/)
- [Edge AI compute ladder — what runs on every board](https://theaivibe.org/edge/edge-ai-compute-ladder-what-runs-on-every-board)
- [Petoi: robot project ideas for students](https://www.petoi.com/blogs/blog/engaging-robot-project-ideas-for-students)
- [Petoi: Raspberry Pi robotics projects](https://www.petoi.com/blogs/blog/raspberry-pi-robotics-projects-with-petoi-open-source-quadruped-robots)
- [Petoi docs: Raspberry Pi serial port as an interface](https://docs.petoi.com/apis/raspberry-pi-serial-port-as-an-interfac)
- [Petoi: quadruped robotics curriculum](https://www.petoi.com/blogs/blog/quadruped-robotics-curriculum-teaching-robotics-with-petoi)

Petoi's published Pi material is integration plumbing — `ardSerial.py`, serial
UART, mounting. **No flagship Pi-plus-camera demo exists**, and the curriculum
pages cover Bittle and Nybble rather than Quaddle. Everything in sections 2 and
3 would be new ground rather than a duplicate.
