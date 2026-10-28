# Quaddle eye contact: webcam face tracking drives the robot's TFT pupils

## Context

Saturday demo, ~24 hours. CamWalkingGame already has two webcam modes that drive the
robot's legs (body pose, finger bend). This adds a third mode where the robot's existing
on-board TFT eyes look at whoever is in front of the camera.

The session started from a plan to send head *orientation* so the pupils mirror your head
turns, and redirected to face *position* so the pupils look *at* you. That is both the
stronger effect (creature, not puppet) and less code.

**Key discovery that collapsed the scope: zero firmware changes needed.**
`processJoystick()` (`OpenCatEsp32S3/src/joystick.h:396`) stores Jr rstick values then
returns early when `viewMode == 3`, skipping the leg apply. `updateEyes09tft()` then calls
`joystickEyeNormApplyJrRstickOffset()` (`joystick.h:373`), which adds the stick offset to
the gaze. So the existing `J` token already moves the pupils. No new token, no flash,
nothing irreversible, and the currently-working demo stays on the robot as a fallback.

Full design doc, including every committed constant, the failure paths, prior-review
dispositions, and the installed spec-review findings:
`~/.gstack/projects/borntoleave-CamWalkingGame/kaikai-main-design-20261001-193110.md`

**Confirmed on hardware:** pupils move via `ve` + `J`. Tilting the robot moves the eyes,
which confirms offset-not-absolute semantics (base falls through to `eyeX = imuX`), so the
demo needs a level surface.

**Still unverified:** whether the eye loop applies a leg or body lean, since `doSyncBody`
lists `joystickJrRstickIsActive()` as an enabler. First run of the code answers it.

## Scope for Saturday

Eye contact only. Cut: wake-and-sleep (its cheap version writes `lastPresenceMs`, which
drives `POWER_SAVER`, so the robot physically sits down and stands up), and the shy beat
(needs threshold tuning you cannot safely do the night before). Both are post-demo.

## Implementation

All changes in `app/index.html`. No firmware edits.

### 1. Mode shell
- Third dial button `#modeEye` after `#modeFinger` (~1218), click handler alongside the
  existing two (~6608-6613), `modeEye` i18n key in EN (~1453) and ZH (~1625).
- Make `trackMode` three-valued: `setTrackMode()` (~6474), `applyTrackModeChrome()`
  (~6443), `document.title` lookup (~1813), the `tick()` branch (~6128-6140),
  `startCamera()` console message (~6172). `refreshCameraButton()` and `initHand`'s
  finger-only error path need no change, both already fall through correctly.
- `setTrackMode()` keeps its existing resets and adds `resetEyeTrackingState()`.

### 2. `renderEyeTracking(poseResult)` — new, after `renderFingers` (~5955)
Routed from `tick()`'s `"eye"` branch using the already-loaded `poseLandmarker`.
Single person, no ready gate, no `controlLayout`, no leg plumbing.

- Raw normalized landmarks (`landmarks[i][0]` nose), not `landmarkToClient`, so the math
  is independent of camera rotation.
- `dx = (nose.x - 0.5) * 2`, `dy = (nose.y - 0.5) * 2`; `hx/rsy = clamp(round(SIGN * d *
  50 * 1.4), -50, 50)`. ±50 is full pupil travel.
- **Centered-face hold:** if a face is visible and both components are within the firmware
  deadzone (`|v| <= 2`), force `hx = 3`. Otherwise a person standing dead center encodes
  identically to no face, clearing `joystickJrRstickIsActive()` and resuming idle saccades
  at exactly the demo moment.
- Person selection: largest ear-span with both ears above 0.5 visibility, falling back to
  inter-eye distance; switch requires +15% held 500ms; immediate switch (no dwell) if the
  incumbent is lost while another candidate exists.
- Status readout into the existing stat/coord elements. No new overlay.

### 3. Transport — `sendEyeLook(hx, rsy)` near `sendConnectInitCmds` (~4031)
- `encodeCommand("J", [114, hx, rsy])`, which the existing binary path already handles.
- `transport.send(cmd, { addNewline: true, logConsole: false, logSerial: false })`.
  Both log flags must be false or the panes flood at 10Hz.
- WebSocket: `petoiPool.sendAndWait(ip, cmd, shortTimeout).catch(() => {})`, at most one
  outstanding send per robot, supersede any queued frame, drop on timeout.
- 10Hz cap, deadband 2 stick units.
- **`ve` re-assert:** before the first frame, on every reconnect, and every 5 seconds while
  active. `viewMode == 3` is the only thing keeping the stick out of the legs, and other
  paths can change the view.
- **Zeros on four exit paths:** face lost >400ms, `setTrackMode()` away from eye,
  `beforeunload`/`pagehide`, serial or WS disconnect. Send 3 zero frames then stop
  transmitting; resume on the next valid candidate.

### 4. Help text + privacy
EN and ZH help section, including the operator pre-demo probe (`ve` then
`bytes:[74,114,40,0,126]`; if the pupils do not move, the firmware is too old). One line
stating frames are processed in-browser and nothing is stored or transmitted, plus a
visible card for the table if it runs unattended.

## Verification

First run of the mode answers three things at once:

1. **Legs.** With `z2` active, watch for any lean, crouch, or step. Any servo motion is a
   fail and means falling back to demoing the existing modes for Saturday (the `vk`
   firmware route is +3-4 hrs and does not fit).
2. **Sign.** Step left; the pupils must move toward you. If not, flip `EYE_SIGN_X`. Do this
   before tuning anything, since an inverted axis makes every feel judgment worthless.
3. **Dead center.** Stand squarely in front; the pupils must stay on you and not drift into
   saccades. This is the centered-face hold working.

Then: walk out of frame (pupils recenter within half a second), kill the tab with a
non-zero value held (legs must stay still), switch back to body mode (leg control normal,
no stuck gaze), and confirm the pre-existing demo still works.

Tuning after that is `EYE_GAIN` until tracking reads attentive rather than twitchy.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | not run | — |
| Outside Review | Codex (`gpt-6-astra`, consult mode, session `01a0fa46-b0ed-7160-b08b-bf975e24bb76`) | Independent 2nd opinion | 1 | completed | 14 findings; 4 required fixes resolved, then superseded when the design changed approach |
| Office Hours | `/office-hours` | Problem framing & alternatives | 1 | completed | Builder mode; redirected head-orientation → face-position, cut M2/M3, found the zero-firmware route |
| Spec Review | `/office-hours` adversarial subagent | Design-doc rigor | 2 | CONVERGENCE | 26 observations across rounds; 14 confirmed resolved; 10 open concerns recorded |
| Eng Review | `/plan-eng-review` | Architecture & tests | 0 | not run | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | not run | — |

- **OUTSIDE COVERAGE:** Codex (OpenAI `gpt-6-astra`) completed one consult-mode review against the original head-orientation plan plus embedded verbatim firmware source. It could not read `app/index.html` (its tooling was unavailable in that sandbox), so all web-side findings were judged against prose. Its findings are dispositioned individually in the design doc; the approach has since changed substantially, so several are moot rather than fixed. No outside review has seen the current design.
- **CROSS-MODEL:** Codex and the native spec reviewer independently identified the same defect from opposite directions: Codex found the leg-safety guarantee leaking past the gaze lease, and the spec reviewer found that webcam presence written to `lastPresenceMs` would drive `POWER_SAVER` into servo motion. Two paths to one hazard is why leg safety is the first verification item rather than a footnote.
- **VERDICT:** Design doc approved by the user for execution under deadline. Spec review disposition is CONCERNS_RECORDED, not clean: 10 round-2 findings were addressed in the rewrite but no reviewer confirmed those fixes, because convergence stopped the loop at 2 rounds. Eng review not run; the user accepted that trade explicitly given ~24 hours to the demo.

**UNRESOLVED DECISIONS:**
- Whether the eye loop applies a leg or body lean on this route. `doSyncBody` lists `joystickJrRstickIsActive()` as an enabler even though `processJoystick` returns early in viewMode 3. Settled by the first run, and it is the one thing that can force a fallback to demoing the existing modes.
- Whether `cmdQuiet` suppresses the robot's idle saccades after a 10Hz stream ends. Affects what happens visually after the pupils recenter; cosmetic, not blocking.
- Whether attention should switch between people at all, or stay loyal to whoever it found first. Aesthetic, decide while tuning.
