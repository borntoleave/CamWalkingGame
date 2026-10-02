# Body Follow mode — open items

Branch `feature/eye-contact`. Written 2026-10-01, the night before the Saturday demo.

The mode is shipping-ready as-is: eyes track your torso, the body leans ~7° toward
you, and it takes single steps toward or away from you when stepping is enabled.
Everything below is either unverified, blocked, or deferred.

Internal code identifiers still say `eye` (`trackMode === "eye"`, `EYE_TUNE`,
`renderEyeTracking`) because renaming them mid-tuning would have broken the console
handles in use against live hardware. See the post-demo section.

---

## Before the demo, in priority order

- [ ] **End-to-end run with the robot connected.** Nobody has done a full pass: select
      Body Follow, walk in and out of frame several times, confirm the eyes recentre
      when you leave and reacquire when you return.
- [ ] **Kill the browser tab mid-stream.** The robot holds the last gaze value forever
      (no firmware lease), so teardown sends zeros on four paths. All four are written
      but **none are exercised**. If this is broken the pupils freeze off-centre until
      a power cycle, which is a visible demo failure.
- [ ] **Step button with the book in place.** Press 🚶 Step, walk toward and away,
      measure actual travel per `kwkF 1`. Raise `EYE_TUNE.walkArg` only after
      measuring.
- [ ] **Two people in frame.** The nearest-person selector has a 15% / 500ms hysteresis
      that has never been tested with two faces. Attention may flip.
- [ ] **WebSocket transport.** Only serial has been exercised. The WS path sends via
      `petoiPool.sendAndWait` with a 250ms timeout and swallowed rejections.

## Blocked on an answer from Petoi

- [ ] **Does the 5° limit on joints 4 and 5 apply to held offsets only, or to all
      motion?** It matters beyond this feature: the shipped elbow and finger modes
      already drive joints 2–5 over `b ± 25°` (`ANGLE_RANGE = 25`), ten times the
      stated limit. `ANGLE_RANGE` was deliberately left alone rather than narrowed on
      an ambiguous instruction hours before a demo.
- [ ] **The constraint and the sample disagree.** Petoi's working lean sample offsets
      joints 4 and 5 by 10, not 5. Worth raising in the same conversation.

## Blocked on an untested question

- [ ] **Does a direct `i` lean survive the gaze stream?** While gaze is streaming,
      `doSyncBody` rewrites joints 0,2,3,4,5 from the gaze every ~31ms
      (`TFT09_EYE_BODY_SYNC_MS`), so an `i` command may be overwritten on the next
      tick. Untested. This gates any deeper-lean feature. Test: enable Body Follow,
      let it track, paste the lean command, see whether it holds or snaps back.

## Not built (deliberate)

- [ ] **Lateral stepping.** Waiting on verification of `kside 1` / `ksideL 1`. Would
      reuse the existing burst logic (confirm delay, cooldown, firmware-bounded
      cycles) with horizontal body movement as the trigger. ~20 min once the tokens
      are confirmed. Note it would replace the continuous lean on that axis, since
      gaits suppress the lean while running.
- [ ] **Deeper held lean.** Blocked on both questions above.
- [ ] **Wake and sleep beat.** Cut for time. When built, drive it **mode-locally via
      `vR`**, not by writing `lastPresenceMs` — that global also feeds `POWER_SAVER`,
      so the robot would physically sit down and stand up.
- [ ] **Shy beat** (holds your gaze, looks away, peeks back). Cut for time; needs
      threshold tuning that cannot be done safely the night before.

## Known limitations, accepted

- **Lean and walk cannot co-occur.** `doSyncBody` requires `skill->period == 1`, so a
  running gait suppresses the gaze-driven lean. With burst steps they alternate.
- **The robot must be level.** Gaze is *added* to the IMU tilt base
  (`eyeX = imuX` + offset), so a tilted robot aims off-target and tilting it moves the
  eyes on its own. Cannot be zeroed without firmware.
- **No gaze lease.** If the page dies without sending zeros, the pupils stay frozen
  until a power cycle. This is the main argument for the `vk` upgrade below.
- **`cmdQuiet` interaction unverified.** `allowIdleEyes` is gated on it, so a 10Hz
  stream may suppress the robot's idle saccades. Whether they resume after the stream
  stops is unconfirmed; only "pupils return to centre" is guaranteed.

## Post-demo

- [ ] **Rename the internals** to match the UI: `trackMode "eye"` → `"body"`,
      `EYE_TUNE` → `BODY_TUNE`, `renderEyeTracking` → `renderBodyFollow`. ~40 call
      sites.
- [ ] **Decide the fate of the `feature/deeper-eye-lean` firmware branch.** It lowers
      `RSTICK_LX_DIV` 7 → 2. Do not flash it: it was justified by a conclusion drawn
      from the *wrong* joint pairing, and is unvalidated either way. Either revalidate
      with the correct pairing or delete the branch.
- [ ] **Add the `vk` view sub-token** for a real gaze lease and graceful degrade. Fixes
      the frozen-pupil failure mode and would let the base gaze be zeroed, removing
      the level-surface constraint. The browser math is unchanged; only
      `sendEyeLook()`'s body differs. Note the two-argument `vk` payload is unproven
      against how `ViewToken::handle` tokenizes today.
- [ ] **Re-run `/codex` against the real code.** Both review rounds judged prose, not
      code; the Codex pass could not read `app/index.html` at all. Ten round-2
      concerns remain recorded but unconfirmed in the design doc's
      `## Spec Review` section.
- [ ] **Merge or PR the branch.** Currently unmerged.
- [ ] **Firmware build setup.** `arduino-cli` is installed, but compiling
      `OpenCatEsp32S3` needs four Petoi-internal libraries (`SimpleDisplay`,
      `PetoiEm3Servo`, `PetoiStepper`, `PetoiTouchLedMatrix`) plus `TFT_eSPI` with a
      display-specific `User_Setup.h`, `NimBLEDevice` and `WebSocketsServer`. None are
      on this machine. Source them before any firmware work.

## Mistakes already made — do not repeat

- **Joint pairing for a lean is (2,4) against (3,5)**, not (2,5) against (3,4). The
  latter follows this file's own `joints 2..5 = LE, RE, RK, LK` comment and commands a
  twist the robot cannot hold: it hops at ±10° and jump-steps forward at ±25°.
- **Read skill names from `skillNameWithType[]` in `Instinct_Quaddle.h`.** Two wrong
  guesses were made by inferring from the naming convention (`trF`/`bkF` instead of
  `wkF`/`wkB`), one of them because a regex silently truncated names over six
  characters.
- **Gain and the lean cap interact.** Dropping `EYE_TUNE.gain` to 1.0 made the lean
  invisible, because full lean then requires the face at the frame edge. 2.6 reaches
  the cap at ~38% off-centre.
- **Forced sends exist for a reason.** The three redundant zero-frames on teardown were
  being silently swallowed by the in-flight gate until `force` was added.
