# Gemma 4 E2B on a Pi 5, driving Quaddle behaviours — hackathon scope

**Date:** 2026-10-24
**Branch:** `feature/gemma-pi5`, worktree `/Users/kaikai/projects/petoi codes/CamWalkingGame-gemma`, cut from `main` at `2163d0f`
**Budget:** 1.5 hours of implementation
**Hardware (confirmed by the user):** Raspberry Pi 5, 8GB RAM; Pi Camera Module 3

## What this is

The robot looks at a person every few seconds, decides what it is seeing, and fires
**one bounded OpenCat gait**. Show it something or say something, and Quaddle reacts.

This is not the tracking demo and does not become it. See "Not in scope".

## Why a VLM cannot be the control loop

Measured figures for Gemma 4 E2B on a Pi 5 are **3-8 tokens/sec**, and 5.8-6.5 tok/s
with image input via a multimodal projector under llama.cpp. A useful answer therefore
takes several seconds, including image encoding.

The camWalk aim loop needs >= 5Hz. These are three orders of magnitude apart. Any design
in which Gemma sets the lean or the pupil aim is dead before it starts. So Gemma is used
where its latency is free: **a slow semantic layer that picks a discrete behaviour.**

## Why this is safer than the streaming design, not riskier

`app/index.html:6351-6360`:

```js
// eyeSendSkill("wkF", 3) sends "kwkF 3". Per reaction.h, an argument below 200
// is a gait-cycle count and 200 or above is milliseconds; either way the
// FIRMWARE ends the gait itself.
```

The Pi Zero plan's critical gap 1 was that streamed `J` stick values are **held by the
firmware until power cycle**, so a frozen Pi leaves the robot holding a lean. A bounded
`k<skill> <count>` has no such state: the firmware terminates it. A Pi that dies between
decisions leaves a robot that has already stopped.

This removes the need for a firmware `vk` command lease **in this design only**. The gap
remains real for the streaming designs on `feature/pi-zero` and `feature/eye-contact`.

## Protocol, verified in this repo

From `encodeCommand` (`app/index.html:3385-3394`) plus `send()` (`:4574-4586`):
lowercase tokens are ASCII, params joined with a space, and `send()` appends `\n`.
Binary uppercase tokens end with `126` and never get a newline.

| Purpose | Wire bytes |
|---|---|
| Bounded gait | `b"kwkF 3\n"` |
| Stand / stop | `b"kup\n"` |

**Verified-on-hardware skill names in this repo: `wkF`, `wkB`, `up`** (`app/index.html:6141-6143`).
These three are the only ones this project has actually run.

Other names in `Instinct_Quaddle.h` (`vtL`, `sit`, `hi`, `str`) are **unverified by this
project** and stay out of the demo path until tested on the bench. The plan for turn gaits
already warns that only `L` variants appear in that table and the right-hand name must be
confirmed on hardware rather than guessed.

No `ve` and no `viewMode` handling: nothing here streams `J`, so the leg guard is moot.

## Architecture

```
Camera Module 3 --picamera2--> JPEG --HTTP--> llama-server (Gemma 4 E2B + mmproj)
                                                    |
                                                    v
                                            text reply
                                                    |
                                       behaviour.decide()   <-- PURE, unit tested
                                                    |
                                              (skill, arg)
                                                    |
                                          pyserial --> /dev/ttyACM0 @115200
```

llama.cpp rather than Ollama: 10-20% faster on this board, and Ollama on a Pi 5 is
text-only, which would lose the image entirely.

### Files, all new, under `pi5/`

| File | Role |
|---|---|
| `pi5/behaviour.py` | **Pure.** Model text in, `(skill, arg)` or `None` out, plus the wire-bytes encoder. No camera, no serial, no clock. |
| `pi5/test_behaviour.py` | stdlib `unittest`, runs on the laptop. Asserts **exact wire bytes**, not shapes. |
| `pi5/gemma_bridge.py` | The loop: capture, post, decide, write. All I/O lives here. |
| `pi5/README.md` | llama-server launch line, wiring, what is measured vs assumed |

`behaviour.py` being pure is what makes any of this testable without a Pi or a robot.

### Whitelist, not trust

`decide()` accepts a reply **only** if it contains a known skill name from an explicit
allow-list. Anything else returns `None` and the robot does nothing. A 2.3B model asked
for one word will sometimes write a sentence, sometimes refuse, and sometimes invent a
gait; none of those may reach the servos. Default-deny is the whole design, not a
nicety.

The model's reply is untrusted data. It never becomes a command by any path other than
an exact match against the allow-list.

## Round-trip contract test, written before the producer

Per the repo's producer-to-consumer rule: the test feeds candidate model text through
the real `decide()` and the real encoder, and asserts the resulting bytes equal what
`app/index.html`'s `send()` would put on the wire for the same skill. Not a shape
assertion on the producer's output.

The true downstream consumer is the ESP32-S3 firmware, which cannot be tested from a
laptop. The parse-plus-encode seam is the furthest point that can be, so that is where
the contract is pinned, and the bench check in the README covers the rest.

## Schedule

| Window | Work |
|---|---|
| throughout | Model download, ~3-4GB. The critical path. Start first. |
| 0-20 min | All four files. `behaviour.py` and its test first. |
| 20-35 min | Build llama.cpp, start llama-server with `--mmproj`. |
| 35-55 min | First real inference. **Measure seconds per decision.** |
| 55-85 min | Prompt tuning. Where the time actually goes. |
| 85-90 min | Buffer. |

### The one gate

If a decision takes **more than ~15s end to end**, the demo is too slow to read as
reactive. Fallback, in order: drop the capture resolution fed to the model, cut
`n_predict` to a handful of tokens, then drop the image and go text/voice-only.

Not a kill gate for the project, a scope gate for the demo.

## Not in scope

- **MediaPipe tracking.** Needs the Pi port that does not exist yet: `pi/` currently
  holds only the T1 latency probe. That is a ~6 hour job, not a 1.5 hour one.
- **Audio input.** Gemma 4 E2B accepts audio natively, which is the obvious next step
  and the reason this architecture was chosen. Out of the 1.5 hour budget.
- Any change to `app/index.html`.
- Unverified skill names in the demo path.
- The firmware `vk` lease. Not needed here; still needed by the streaming branches.

## Unresolved

- **U1** — Measured seconds per decision on this board with an image. Nobody has run it.
  The 5.8-6.5 tok/s figure is from third-party Pi 5 benchmarks, not from this hardware.
- **U2** — Whether a 2.3B model reliably emits one allow-listed token from a photo.
  The whitelist makes failure safe, but a high refusal rate makes the demo dull rather
  than dangerous. Settled by the prompt-tuning window.
- **U3** — Whether Camera Module 3's continuous autofocus hunts on a moving chassis. If
  it does, pin the focus. Not worth pre-solving.
