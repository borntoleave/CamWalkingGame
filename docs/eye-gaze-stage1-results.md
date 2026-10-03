# Eye Gaze — Stage 1 gate results, 2026-10-02

Measured on hardware with `GAZE_PROBE` (in `app/index.html`, throwaway). Work stopped here
for time, before any estimator code. The plan is `docs/superpowers/plans/2026-10-02-eye-gaze.md`.

**Gate status: 3 of 4 passed. The fourth is unresolved, not failed.**

## The numbers

MacBook webcam, laptop distance, Finger Tracking active (so a second model was also running
every frame — the fps figures are therefore a floor, not the true rate).

| Sweep | What was done | `rawX` swing | `ratio` swing | `ratio` sd | `\|R-L\|` mean / max | fps |
|---|---|---|---|---|---|---|
| **eyes** | head still, look far left → camera → far right | 0.0177 | **0.1675** | 0.0503 | 0.059 / 0.110 | 43.5 |
| **head** | fixate one spot, slide head | 0.0521 | 0.1772 | 0.0389 | 0.091 / 0.134 | 43.2 |
| **nose** | eyes centred in sockets, slide head | 0.0259 | 0.1073 | 0.0192 | 0.087 / 0.118 | 43.6 |
| **still** | hold everything still | 0.0103 | 0.0461 | **0.0078** | 0.082 / 0.112 | 43.2 |

Stick units use the plan's full scale 0.15 and gain 1.0, so ratio 0.15 → 50 stick, and the
usable range is ±50.

## What passed

1. **478 landmarks, live.** Confirmed on camera every frame. Also confirmed offline before any
   code: the bundle metadata says "Detects 478 face landmarks" and the output dimension 1434
   (478×3) appears six times in the flatbuffer while 1404 (468×3) appears zero times.
2. **The points really are irises.** `irisOff` ran 0.07–0.27, never near 1, so landmarks 468 and
   473 sit well inside the socket rather than at the corners.
3. **The ratio responds to eye rotation, decisively.** Head still, eyes moving: swing 0.1675,
   which is **3.6× the still-sweep noise floor** and about 56% of full pupil travel.

## What did not resolve

**Whether head movement alone moves the ratio.** The test cannot be performed by a human: the
vestibulo-ocular reflex counter-rotates the eyes involuntarily whenever the head moves, so the
"nose" sweep's 0.1073 swing may be genuine eye rotation (signal, under the approved
eyes-relative-to-head semantics) or head-position contamination (which would make the mode
pointless). An attempt to separate them arithmetically failed: a single linear leak gain of ~4.1
fits both the nose and still sweeps, but in the still sweep both quantities are noise, so the fit
proves nothing.

**The clean test, not yet run, ~1 minute:** show a face on a tablet, hold it where a head would
be, run `GAZE_PROBE.sweep(8, "photo")` and slide the tablet ~15cm sideways. A photograph's eyes
cannot counter-rotate, so any ratio swing is pure contamination. Pass is a ratio swing near the
still sweep's 0.046; failure is a swing near the 0.107 a moving head produced.

**Do this first if the work resumes.** It is the gate, and it decides whether the rest is worth
building.

## Three findings that change approved constants

1. **τ should be ~150ms, not the approved 400ms.** Raw jitter measured **2.6 stick units sd**,
   where the plan *estimated* ~9 raw and hoped for ~2.3 filtered. The real signal is quieter
   than the plan's filtered target before any filtering. At 43 fps:

   | τ | filtered jitter | 200ms flick response | R2 ceiling (≤1.1) | C12 gate (≥15 units) |
   |---|---|---|---|---|
   | 400ms (approved start) | 0.44 | 39% → 11 units | pass | **fail** |
   | 250ms | 0.56 | 55% → 15.4 units | pass | marginal |
   | **150ms** | **0.72** | **74% → 20.6 units** | **pass** | **pass** |

   R2's accepted scope says to set τ from the measurement, so this is that decision working as
   written, not a reversal. τ=400ms was a safety margin against an estimate that turned out 3.5×
   too pessimistic, and it would have failed the response gate.

2. **The centred-face hold (R4) is confirmed necessary, by measurement.** Resting value while
   looking straight at the camera was −0.0039, i.e. **−1.3 stick units — inside the firmware's
   ±2 deadband**. Without the hold, "looking right at the robot" reads as "nobody is driving" and
   the eyes fall back to idle saccades. Implement it as C7's clamp form (minimum magnitude 3,
   sign latched to the side last looked) so there is no step discontinuity.

3. **The cross-eye disagreement threshold of 0.12 is wrong.** `|R-L|` was 0.082 *while holding
   perfectly still*, and touched 0.134 during normal head movement. A standing offset that
   survives stillness is eye geometry at laptop distance (vergence), not error. The plan's 0.12
   would reject healthy frames. Set it from measurement — something above 0.15 — and treat the
   standing offset as `EYE_GAZE_TUNE.biasX` rather than as a fault.

## Also worth knowing

- **Face inference is cheap.** 43 fps with a second model running alongside. Performance was
  never going to be the problem.
- **Head movement produces ~64% of the pupil response that eye movement does** (0.107 vs 0.168).
  Whatever the cause, this strongly reinforces design decision DR3: without the on-screen prompt
  teaching "hold your head still, move just your eyes", the mode will read as head tracking.

## State of the branch

Three commits on `feature/eye-gaze`, plus this one. Nothing is wired to the robot, `trackMode`
has no `"gaze"` value, and the mode dial still has three buttons. `app/index.html` is
**+183 lines, −0 lines** against `feature/eye-contact`: not one existing line was changed, so
Body Follow here is byte-identical to the build that was tested.

The shared send-layer work (R1 and R3) was **not** started, so the three bugs the eng review
found are still present in both worktrees:

- `setTrackMode:7319` fires `releaseEyeLook()` un-awaited, then `resetEyeTrackingState()` forces
  `releasedQ` true, so a failed recentre never retries and the pupils can stay frozen off-centre
  until a power cycle.
- The `ve` view guard is armed on dispatch rather than delivery.
- The centred-face hold tests the quantized stick rather than the smoothed ratio.

None of these are new tonight, and Body Follow has been demoed with them present.
