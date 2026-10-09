# camWalk on a Raspberry Pi Zero 2 W, mounted on Quaddle — v1 specification

## Context

Today the demo runs in a browser on a static laptop: Chromium holds the camera, MediaPipe runs as
WASM at ~43fps, and Web Serial talks to the robot over USB. The goal is to put the camera on the
robot so Quaddle reacts to a person without a laptop in the loop.

Two assumptions break at once: the camera stops being still, and the frame rate drops by roughly
8x. Most of the work is in those two consequences, not in the port.

**Branch:** `feature/pi-zero`, worktree `/Users/kaikai/projects/petoi codes/CamWalkingGame-pi`,
cut from `feature/eye-contact` at `4b2e892`.

This document supersedes the earlier draft. It is the single executable specification for v1;
nothing below describes deferred work except the explicitly labelled milestone 2 section.

## v1 scope: aim only

**v1 does not move the robot's feet.** The robot watches a person: the pupils track them and the
body leans toward them, both driven by one stick value. No stepping, no turning.

This is a deliberate cut (D5). The reason is specific: the ported controller has forward/back step
bursts and a ~7° lean and **no steering**, and a 7° lean cannot re-point a chassis-mounted camera.
Anyone stepping sideways would leave frame permanently. Rather than ship something called a
follower that cannot follow, v1 proves the aim loop on the floor and milestone 2 adds steering.

**The README must not describe v1 as following anyone.**

## This is a rewrite, not a modification of `index.html`

Chromium plus Web Serial plus MediaPipe WASM will not run usefully in 512MB. The Pi version is a
Python program. What carries over is the **protocol** and the **control law**. No line of
`app/index.html` changes.

## Verified constraints

- **Pi Zero 2 W**: quad Cortex-A53 @1GHz, 512MB. MediaPipe pose on this chip class measures
  ~4fps, 5-6fps with the lite model. Plan for 5.
- **Raspberry Pi OS Bookworm 64-bit is required.** Trixie ships Python 3.13; MediaPipe supports
  ≤3.11 while picamera2 on Trixie builds against 3.13, so they cannot coexist there. Raise swap to
  1024MB in `/etc/dphys-swapfile` — as an OOM-kill safety net, not as headroom. If MediaPipe
  actually pages during inference the frame rate collapses, so swap-in rate is a monitored signal.
- **Serial is USB, not GPIO UART.** Quaddle is ESP32-S3 and its spare UART is already
  `SERIAL_VOICE` (`OpenCat.h:194-196`, `:241-243`). USB at 115200 is the transport the browser
  already uses.
- **Model**: reuse `app/vendor/mediapipe/models/pose_landmarker_lite.task`, already in the repo.

## Shared power and camera mounting (confirmed on hardware, 2026-10-09)

**The Pi runs off the robot's battery.** Two consequences, one good and one that changes a risk.

Good: a Pi brownout now self-recovers. `Restart=on-failure` brings the service back, which re-sends
`kup` and `ve` and resumes streaming. The robot holds its last lean for the reboot, roughly 20-30s,
then carries on.

The change: this turns critical gap 1 from a rare crash into a **recurring** failure mode. Servo
current surges and the Pi share one rail, and a Zero 2 W is sensitive to undervoltage, so the
likely trigger is not a kernel panic but the robot browning out its own computer while drawing
hard. For **v1 this risk is low** — a 7° lean is a small load. It rises sharply at **milestone 2**,
where gaits draw far more, so measuring the rail under a gait is a milestone-2 prerequisite rather
than a v1 one. Sustained MediaPipe load also shortens robot runtime; budget for it.

**The camera is mounted on the front of the top chassis.** It therefore never moves with joint 0,
so the head's ±50° pan is fully decoupled from the image. Confirms the body-mount assumption the
loop analysis rests on.

## MediaPipe and camera configuration (must be stated, not inherited)

Same weights does not mean same behaviour. v1 pins these explicitly:

| Setting | Value | Why |
|---|---|---|
| `running_mode` | VIDEO | matches the browser |
| `num_poses` | **2** | matches `MAX_POSES = 2` (`index.html:2093`). Person-switch hysteresis cannot exist at 1, so dropping it removes a tested behaviour rather than just saving time |
| `min_pose_detection_confidence` | 0.5 | matches `index.html:7109` |
| `min_pose_presence_confidence` | 0.5 | matches `index.html:7110` |
| `min_tracking_confidence` | 0.5 | matches `index.html:7111` |
| capture resolution | **640x480**, not the browser's 1280x720 ideal | the browser value is a laptop default; pose-lite downsamples internally, and 720p costs memory the 512MB board does not have |
| orientation / mirroring | **none**; landmarks stay in raw normalized camera coordinates | the browser's preview mirroring is CSS-only and never touches the math. State the convention so `signX` means one thing |

`num_poses = 2` costs inference time at 5fps. If T1 shows it is unaffordable, dropping to 1 is a
scope change that removes person switching, not a tuning tweak; record it as such.

## Protocol, byte for byte

From `encodeCommand` (`app/index.html:3385-3394`): uppercase tokens are binary, ASCII bytes plus a
`126` (`~`) terminator and **no newline**; lowercase tokens are ASCII **with** a newline.

| Purpose | Bytes |
|---|---|
| Force eye view (the leg guard) | `b"ve\n"` |
| Aim | `bytes([74, 114, hx & 0xFF, rsy & 0xFF, 126])` |
| Stand | `b"kup\n"` |

`hx`/`rsy` are signed int8; ±50 spans full travel; the firmware zeroes `|v| <= 2`.

One stick value drives three things at once in firmware: pupil aim, body lean (~7°/joint) and head
pan (joint 0, `joystick.h:59` sets `j0 = -hx`). They cannot be separated from the host.

## The v1 control law

Ported from `renderEyeTracking` and helpers (`app/index.html:6100-7500`), aim path only.

1. **Person selection** — largest shoulder width; a challenger must exceed the incumbent by 15%
   and hold it 500ms.
2. **Aim** — shoulder midpoint, falling back to the nose: `dx = (aimX - 0.5) * 2`, then
   `hx = clamp(signX * dx * 50 * gain, -50, 50)`.
3. **Smoothing** — elapsed-time EMA, `alpha = 1 - exp(-dt / tau)`, applied to the *position*, not
   the stick value.
4. **Centred hold** — a centred person must not read as "nobody driving", or the robot reverts to
   idle saccades. Implemented as a **minimum-magnitude clamp, not a forced value**:
   `if abs(hx) < 3: hx = 3 * sign(last_nonzero_side)`. At the boundary the clamp is the identity,
   so there is no step. Forcing `hx = 3` outright would flip a small negative command to positive
   as it crosses, and because this value also commands head pan and the leg joints, that
   discontinuity can produce an offset or a limit cycle near centre at 5fps.
5. **`ve` re-assert** — every 5s and on every reconnect.
6. **Send gate** — deadband 2, minimum interval 100ms (never binds once inference is the
   bottleneck).

**Not in v1:** the depth signal, walk bursts, the baseline, the cooldown. `eyeBodySize` is still
ported because the status page shows size and the "too far" hint uses it, but nothing consumes it
for motion.

## What the Pi changes, with the arithmetic corrected

**1. The fixed smoothing alpha is wrong at 5fps.** The time constant of a fixed-alpha EMA is
`-dt / ln(1 - alpha)`, **not** `dt / alpha` (the approximation runs ~17% high at alpha 0.3). So
`EYE_SMOOTH = 0.3` is **65ms at 43fps and 561ms at 5fps**. Switch to elapsed-time smoothing so tau
is chosen directly. Note that `tau = 250ms` is nearly 4x slower than the laptop's real 65ms: it is
a deliberate choice for a delayed loop, not preservation of laptop feel. Start at 250ms and set it
from the floor measurement.

**2. Aim MAY be a closed feedback loop, and the sign of that is unverified.** The earlier claim
that "leaning toward the person moves them toward frame centre" assumes a chassis motion nobody has
measured. What the firmware actually does (`joystick.h:69-73`) is:

```c
int dxL = lx / RSTICK_LX_DIV;     // plus or minus 7 at full stick
*outV2 = u2 - dxL + yLeg;         // joints 2 and 5 move together
*outV3 = u3 + dxL + yLeg;         // joints 3 and 4 move the opposite way
```

Whether that is a roll, a yaw or a twist depends on the joint-index-to-physical-leg mapping, and
**that mapping has already misled this project once**: the browser's own `LE, RE, RK, LK` comment
produced a pairing that made the robot hop instead of lean. It is not re-derived here.

It matters because the two cases behave oppositely. If the chassis **yaws**, the camera pans, the
person moves toward centre, and the loop is closed and self-correcting, so gain must stay low. If
the chassis **rolls**, the image rotates about its optical axis and the person barely moves
horizontally, so the loop is nearly open, much more like the laptop, and the conservative gain is
unnecessary.

**T5 settles it**, and its first measurement is specifically: command a known `hx` with the robot
on the floor and nobody moving, and record how far the person's horizontal position shifts in the
image. A large shift means a closed loop; a near-zero shift with visible image rotation means an
open one. Start `gain` at **1.5** until that number exists, then set it from the measurement.

**3. Timeouts sized for 43fps.** `EYE_LOST_MS = 400` is two frames at 5fps; raise to ~1000ms.
`EYE_STALL_MS = 1000` is still five frames.

**4. Camera mounting is on the body/chassis** (D4 confirmed), so the camera swings only with the
~7° lean. Had it ridden the head, joint 0's ±50° travel from the same `hx` would make the loop
roughly 7x hotter and this gain guidance would be wrong.

## Concurrency, freshness and lifecycle

This section exists because blocking writes do **not** make the teardown safe on their own.

**One serial owner.** Exactly one thread owns the port. The main loop and the watchdog publish
intents into a single-slot mailbox (latest wins, drop rather than queue, matching the browser).
Writes have a bounded timeout. Nothing else opens the port.

**Three distinct timestamps**, because conflating them produces both false releases and missed ones:

| Timestamp | Refreshed by | Used for |
|---|---|---|
| `last_valid_observation_ms` | a fresh, non-stale inference result **with a target** | the release decision |
| `last_target_seen_ms` | a target present in any accepted result | the status page and the "lost" hint |
| `last_write_ok_ms` | a serial write that completed | detecting a dead link |

Release when `now - last_valid_observation_ms > LOST_MS`. **Do not** release because no write has
happened: a person standing still is correctly suppressed by the deadband and must not be dropped.
A loop that keeps discarding stale results still releases, because the discarded ones never
refresh `last_valid_observation_ms`.

**Generation counter.** Incremented on every release. A late inference result carrying an older
generation is discarded, so it cannot restore a stale command after the watchdog has zeroed.

**Standing initialisation.** `doSyncBody` requires `skill->period == 1`, so a robot already running
a gait ignores the lean while the pupils still respond — which looks like a half-working prototype
rather than a missing startup step. On start and on every reconnect: send `kup`, then `ve`, then
begin streaming. Three zero stick frames do **not** establish that a gait stopped.

**Shutdown.** `ExecStop=` cannot share the port with a running process, so the unit sends
`SIGTERM` and the service's own handler does the zeroing: stop accepting new intents, flush zeros
with a bounded deadline, close. `TimeoutStopSec` bounds the whole thing. "Retry until a zero lands"
needs that deadline, or an absent USB device spins forever.

## Files, all new, under `pi/`

| File | Role |
|---|---|
| `pi/tracker.py` | **Pure** control law. Signature takes `now_ms` and `dt_ms` explicitly, because every hysteresis timer needs them. No camera, no serial, no clock of its own. |
| `pi/robot.py` | The single serial owner: protocol encoding, `by-id` port with retry backoff, `ve` re-assert, standing init, bounded writes, zeroing on shutdown |
| `pi/camwalk.py` | Main loop: picamera2 → mediapipe → tracker → robot, latest-frame-only |
| `pi/web.py` | Status and tuning HTTP server, stdlib only, following `scripts/demo_server.py` |
| `pi/config.py` | Tuning constants as a Python module with the comments carried over from `index.html`. Read at startup; the UI mutates an in-memory copy and never writes back |
| `pi/test_tracker.py` | stdlib `unittest`, run on the laptop |
| `pi/camwalk.service` | systemd unit, `Restart=on-failure`, `ExecStop` sends SIGTERM |
| `pi/README.md` | Bookworm 64-bit, swap, AP mode, wiring, getting code onto the Pi, and what v1 does **not** do |

`tracker.py` being pure is what makes any of this testable without a robot.

**Non-persistence is deliberate.** Tuning changes live in memory and die with the process, matching
`index.html:6322-6325`. On a robot that starts at boot, that is a safety property.

## Network

The Pi runs as its own WPA2 access point (`nmcli device wifi hotspot`), and the phone joins the
robot directly. The WiFi password is the access control and the traffic is encrypted, which beats
a token on a venue's network. AP and client on one radio at once is reported fragile, so it is one
or the other; `README.md` documents switching to client mode for `git pull` and `apt`.

## Work order, each stage gating the next

1. **T1 — latency gate.** Bookworm 64-bit, picamera2 and mediapipe importing together, then
   measure with a person in frame and the pinned configuration above. Measures **capture-to-write
   latency** (capture timestamp to serial write returning), reported as a distribution, not an
   average fps. Runs with a synthetic CPU load standing in for the web server, so this does not
   depend on T6 — the earlier draft had T1 requiring a server built two tasks later.
   **Gate: p95 capture-to-write ≤ 400ms and sustained ≥ 3fps.** Stop the project otherwise.
   Note honestly that write-return is not mechanical response; the servo and firmware latency
   beyond it is unmeasured and is part of why gain is set empirically on the floor.
2. **T2 — `robot.py`** and a manual CLI. Standing init, `ve`, stick left/right/centre. Robot on a
   stand, feet clear.
3. **T3 — `tracker.py`** and its unit tests, written on the laptop.
4. **T4 — closed loop, aim only, on a stand.** Set `signX` and `signY` here, because a stand is the
   safe place to discover a sign error. **Do not set gain here**: feet off the ground produce no
   chassis rotation, so the loop being tuned does not exist yet.
5. **T5 — floor characterisation, then gain.** On the floor, measure the step response to a person
   moving ~30cm laterally: settling time, overshoot, steady-state error, and cross-axis coupling
   from the vertical channel. Set `gain` and `tau` from that.
6. **T6 — `web.py`**, then re-measure T1's latency with the server actually running; it must still
   meet the budget.
7. **T7 — `config.py`, AP mode, README, service unit.**

## Acceptance criteria for v1

Numeric, because "looks right" is not a criterion:

- **Settling**: after a 30cm lateral step by the person, the stick value settles within 10% of its
  final value in **≤ 1.5s**.
- **No sustained oscillation**: with the person standing still for 60s after settling, peak-to-peak
  stick variation **≤ 6 units** (about 12% of half travel).
- **Tracking**: walking slowly left to right across the camera's field, the person stays within the
  frame and the lean visibly follows, with no reversal.
- **Reacquisition**: leave frame and return; tracking resumes within **2s** and the pupils do not
  sweep across from the previous position.
- **Centre behaviour**: standing centred for 30s produces no visible hunting and no idle saccades.
- **Latency**: p95 capture-to-write ≤ 400ms with the web server running.

## Verification

**Off the Pi** (`python3 -m unittest`): person selection with one and two people including the
15%/500ms hysteresis; shoulders hidden so the ear and eye fallbacks fire; nothing visible;
the minimum-magnitude clamp, checked for continuity at the boundary in both directions;
elapsed-time smoothing producing the same tau at 5fps and 43fps; non-finite and degenerate inputs;
the three freshness timestamps driving release correctly, including the case where the deadband
suppresses writes for a stationary person; the generation counter discarding a late result after a
release. Plus byte-level parity: `J` encodes to exactly `[74,114,hx,rsy,126]` with no newline,
`ve` and `kup` with one.

**On the robot, on a stand**: standing init; `ve` survives a reconnect; signs correct; killing the
process leaves the pupils centred; USB unplugged mid-stream retries and recovers.

**On the floor**: the acceptance criteria above.

## Failure modes

| Path | Failure | Covered? | What is seen |
|---|---|---|---|
| picamera2 → pose | frames queue, loop acts on stale data | latest-frame-only, stale cutoff, capture age on the page | capture age visible |
| robot.py open | USB node absent at boot | `by-id` path, retry backoff | status says waiting |
| robot.py write | write fails mid-stream | invalidate cache, resend next frame | brief stall, self-corrects |
| systemd stop | clean stop or restart | SIGTERM handler flushes zeros, bounded | pupils recentre |
| **Pi freezes or USB unplugged while robot powered** | **last stick value held forever** | **NO. Needs a firmware lease** | **silent: lean stuck until power cycle** |
| **`viewMode` changes between `ve` reasserts** | **`J` reaches the leg control path** | **NO. Inherited from the browser** | **silent: legs move unexpectedly** |
| memory | MediaPipe pages to SD swap | swap-in rate on the status page | fps collapse, explained |

**2 critical gaps**, both silent, both needing the same firmware `vk` lease.

**A correction to an earlier claim in this plan**: cutting stepping does **not** reduce either gap.
The `viewMode` gap routes `J` into the leg control path whether or not a gait command is ever
sent, so an aim-only v1 is exposed to it exactly as much. And a shared battery does not guarantee
the Pi and the servos die together: the Pi can brown out at a higher voltage and leave the ESP32
powered, holding its last lean.

## Milestone 2, deferred

Steering and stepping. A horizontal-error trigger fires a turn burst reusing the existing confirm /
firmware-bounded burst / cooldown pattern, with gaits from `Instinct_Quaddle.h` (`vtL` turn in
place, `wkL` walk-while-turning). **Only `L` variants appear in that table; verify the right-hand
name on hardware rather than guessing.** Carries with it: gait-corrupted frames still reach shoulder
width, identity selection and the baseline even when aim is frozen, so name which observations are
discarded and require N stable post-motion observations before re-arming; and the depth baseline's
transitions become far more frequent from a moving viewpoint, even though source-change and
target-loss invalidation already exist in `eyeUpdateWalk`.

## NOT in scope

- Steering and stepping (milestone 2).
- A firmware `vk` lease — the only real fix for both critical gaps. Recorded in
  `docs/body-follow-todos.md`.
- Eye Gaze on the Pi: the pose model alone is at the fps ceiling.
- IMU shake compensation: moot with no gait in v1.
- GPIO UART: collides with `SERIAL_VOICE`.
- Simultaneous AP and client WiFi.
- Any change to `app/index.html`.

## What already exists

- `app/index.html:3385-3394` `encodeCommand` — the byte format. **Canonical** for the control law;
  `pi/config.py` cites the browser constant each value mirrors, so divergence is greppable.
  Where the Pi deliberately differs (tau, gain, LOST_MS), the comment says so and why.
- `app/index.html:6100-7500` — aim, person selection, centred hold, `ve` re-assert, teardown
  intent. Port the **intent** of teardown, not the implementation: `setTrackMode:7319` fires
  `releaseEyeLook()` un-awaited and `:7330` then forces `releasedQ = true`, so a failed recentre
  never retries. That is a known bug, not a pattern to copy.
- `app/vendor/mediapipe/models/pose_landmarker_lite.task` — reuse.
- `scripts/demo_server.py:8` — the in-repo stdlib HTTP pattern `web.py` follows. **[Layer 1]**
- `Instinct_Quaddle.h` — gait names. Read it; do not guess.
- Considered and rejected: Petoi's `ardSerial.py`. Three command shapes here, and it targets
  NyBoard rather than ESP32-S3.

## Decision and finding ledger

**Answered decisions.** D1 four Python modules, not three. D2 a web UI on the Pi for live tuning.
D3 config as `pi/config.py`. D4 the Pi hosts its own WPA2 AP. D5 v1 is aim-only (Completeness 7,
a durable scope cut, logged as `f4b6d031-6f28-4a5a-89c9-4068687b4afc`; **mark it in code**:
`# gstack-shortcut(dec-f4b6d031): aim-only, no steering, upgrade when the floor-measured aim loop is stable`).
Earlier: D4 body-mount confirmed; the diagnostics panel stays visible (`8bf61142`); `viewOkQ` stays
a single flag (`8dbf981b`).

**Eng review findings, all dispositioned and folded in above**: SC-1 test file listed; SC-2 config
and stdlib server; SC-3 teardown intent not implementation; SC-4 body mount; SC-5 `ardSerial`
rejection recorded; SC-6 code-onto-Pi in README; A-1 AP mode; A-2 SIGTERM handler; A-3 `by-id` plus
retry; A-4 diagram; Q-1 canonical constants; Q-2 `now_ms`/`dt_ms` signature; Q-3 send-failure
handling; T-1 stdlib `unittest`; P-1 swap as a monitored signal; P-2 ≤1Hz polling.

**Codex findings, all upheld and folded in above**: CX-1 safety claims corrected; CX-2 numeric
latency gate and the T1/T6 ordering fixed; CX-3 three freshness timestamps and the generation
counter; CX-4 single serial owner, bounded writes, SIGTERM ordering, retry deadline; CX-5 standing
initialisation; CX-6 EMA arithmetic corrected to `-dt/ln(1-alpha)`; CX-7 minimum-magnitude clamp
instead of a forced value; CX-8 numeric acceptance criteria and `signY`; CX-9 pinned model and
camera configuration; CX-10 this reconciliation.

## Unresolved

- ~~**U1** — Power topology unknown.~~ **RESOLVED 2026-10-09: the Pi runs off the robot's
  battery.** See "Shared power" below; this does not make the shutdown gap safe, it changes its
  shape.
- **U2** — Whether the measured capture-to-write distribution meets the 400ms p95 budget. T1
  settles it and is a kill gate.
- **U3** — Whether `num_poses = 2` is affordable at 5fps. If not, dropping to 1 removes person
  switching and is a scope change, not a tuning tweak.
- **U4** — Whether the chassis lean yaws the camera (closed loop, keep gain low) or rolls it
  (near-open loop, the laptop's gain may be fine). Settled by T5's first measurement, not by
  reading the joint map.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | not run | — |
| Outside Review | Codex (`gpt-6-astra`) | Independent 2nd opinion | 3 | completed | 10 findings last run, all upheld and now folded in |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | issues_open | 10 issues, 2 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | issues_open | prior run reviewed a different plan |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | not run | — |

- **OUTSIDE COVERAGE:** Codex (OpenAI `gpt-6-astra`, host claude, phase plan-review) ran three
  passes. One was against the Eye Gaze plan (2026-10-03, a different target). Two were against this
  plan: the pre-review draft and the post-review revision. **In every pass Codex reported it could
  not read repository source** — the last run said its shell tool failed to start — so all three
  judged prose, not code. The most recent 10 findings were each checked and upheld, and all are now
  folded into the specification above rather than left as an appendix.
- **CROSS-MODEL:** The outside pass corrected this review's own work four times, which is the
  result worth recording. It caught an arithmetic error (the EMA time constant is
  `-dt/ln(1-alpha)`, so alpha 0.3 is 65ms at 43fps and 561ms at 5fps, not the 78ms and 667ms this
  plan previously stated), a false safety claim (cutting stepping does not shrink the `viewMode`
  gap, because that gap routes `J` to the legs regardless of gait commands), a wrong disposition
  (blocking writes were assumed to dissolve the teardown race; five writers share one port), and a
  circular task ordering (the latency gate depended on a web server built later). The native review
  had found interface and boundary defects by reading code; the outside pass found errors of
  reasoning in the review itself. Model identity: `gpt-6-astra` as reported by the CLI.
- **VERDICT:** NOT CLEARED, but implementable. Eng Review remains `issues_open`: 10 issues and 2
  critical gaps, both silent and both needing a firmware lease that is out of scope. Every eng and
  Codex finding is now dispositioned and folded into the body, so the document no longer
  contradicts its own scope cut and can be implemented literally. Work is gated on T1, a genuine
  kill gate with a numeric budget.

**UNRESOLVED DECISIONS:**
- ~~**U1**~~ — RESOLVED: the Pi runs off the robot's battery, and the camera is on the front of the top chassis. Both are recorded in the spec. U1 is replaced by **U4** below, which is narrower and sharper.
- **U2** — Whether measured capture-to-write latency meets the p95 ≤ 400ms budget at ≥ 3fps. T1 settles it and is a kill gate.
- **U3** — Whether `num_poses = 2` is affordable at 5fps; dropping to 1 removes person switching and is a scope change rather than a tuning tweak.
- **U4** — Whether the chassis lean yaws the camera or merely rolls it. A yaw makes the aim loop closed and demands a low gain; a roll leaves it nearly open and the laptop's gain may be fine. T5's first measurement settles it; the joint-index-to-leg mapping is not a safe way to derive it, having already misled this project once.
