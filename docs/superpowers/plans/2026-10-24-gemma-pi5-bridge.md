# Gemma 4 E2B on a Pi 5, driving Quaddle behaviours

**Date:** 2026-10-24
**Branch:** `feature/gemma-pi5`, worktree `/Users/kaikai/projects/petoi codes/CamWalkingGame-gemma`, cut from `main` at `2163d0f`

## STATUS: code complete, NEVER RUN. No Pi 5 was available.

Written during a hackathon against a 1.5 hour budget. The code was finished and
tested; the demo never happened, because **no Pi 5 hardware was on hand.** An
earlier statement in this session that a Pi 5 and camera were available turned
out not to hold.

Nothing below has executed on a Raspberry Pi. Treat every runtime claim as
untested. The parts that ARE verified are called out as such.

| Piece | State |
|---|---|
| `pi5/behaviour.py` | Written. **23 tests pass on a laptop.** Byte format verified against `app/index.html`. |
| `pi5/gemma_bridge.py` | Written. CLI and failure path exercised; camera, model and serial paths **never run**. |
| `pi5/README.md` | Written. Commands come from documentation, not from a run. |
| Pi 5 setup | **Never attempted.** No hardware. |
| llama-server | **Never started.** |
| Model download | **Incomplete.** See "Network reality" below. |

**Read "Prerequisites" before picking this up again.** The thing that stopped
this project was not code or architecture; it was a shopping list.

## Prerequisites — the actual lesson from 2026-10-24

Everything here was blocked by hardware and bandwidth, not by the design. If
you are restarting this, get these BEFORE writing or running anything.

### Hardware

| Item | Why | Failure without it |
|---|---|---|
| Raspberry Pi 5, 8GB | 4-bit Gemma 4 E2B needs ~5GB | A 4GB board cannot load the model at all |
| Pi Camera Module 3 | The eyes | — |
| **22-to-15-pin CSI adapter cable** | The Pi 5 has the narrow connector; Module 3 ships with the wide one | Camera physically will not connect |
| **USB-C SD card reader** | A MacBook Air has no SD slot and only USB-C ports | **Cannot write the card at all.** This is what stopped 2026-10-24. |
| microSD or USB SSD, 32GB+ | OS, a 3GB model, and the llama.cpp build | — |
| Official 5V/5A USB-C PSU | A Pi 5 under sustained inference | Brownouts that present as a bad SD card |
| Active cooling | Sustained inference throttles a bare Pi 5 | tok/s decays through a long demo |
| USB-C to Ethernet adapter *or* micro-HDMI cable + monitor + USB keyboard | A rescue path when WiFi setup fails | No way to reach a headless Pi that did not join |

The SD reader is the one people assume they have. A MacBook Air cannot write a
card without one, and **a Pi cannot be configured without writing its card** —
the `firstrun.sh` and `userconf.txt` tricks all require mounting the boot
partition. There is no software route around this.

### Network

Both of these were measured at the venue on 2026-10-24 and both broke things:

- **Client isolation.** ARP resolved a Pi's MAC on the venue WiFi, the gateway
  answered pings at 180ms, and the Pi dropped 100% of packets. 332 hosts in the
  ARP table, one reachable. A correctly configured Pi would still have been
  unreachable over SSH. **Use a phone hotspot, not venue WiFi.**
- **Bandwidth.** Sustained ~275 KB/s, so roughly an hour per gigabyte. A spot
  measurement of 29 KB/s led to a published estimate that was about 10x too
  pessimistic; the sustained figure is the one to plan against.

**Download the model before you arrive anywhere.** 3.11GB at venue bandwidth is
about three hours, assuming it completes at all. On 2026-10-24 it did not: the
first attempt died with a HuggingFace Xet transfer error
(`CAS Client Error: ... error decoding response body`) and the retry died on DNS
when the network dropped entirely. Only `mmproj-F16.gguf` (940MB) landed.

If a transfer keeps failing, set `HF_HUB_DISABLE_XET=1` to fall back to plain
HTTP, which resumes far better on an unreliable link.

## Model format — read this before downloading anything

**There are two incompatible ecosystems and they are easy to confuse.**

| Format | Runtime | What this plan's code expects |
|---|---|---|
| **GGUF** (`.gguf`) | llama.cpp / llama-server | **Yes.** `gemma_bridge.py` posts to llama-server's HTTP API. |
| **LiteRT-LM** (`.litertlm`) | MediaPipe LLM Inference, LiteRT-LM runtime | No. llama.cpp cannot load these. |

On 2026-10-24 the files already on the laptop were `.litertlm`, not GGUF:

- `gemma-4-E2B-it-web.litertlm` (1.9GB) — converted for **WebGPU in a browser**
- `gemma-4-E4B-it-gpu.litertlm` (2.8GB) — converted for a **GPU delegate**

Neither is a CPU build, so neither is what a Pi 5 wants, and the Pi's VideoCore
GPU is not a target either was converted for. LiteRT-LM does have a Linux
aarch64 runtime, so a Pi port is not impossible, but it would need a CPU-target
`.litertlm` and a different bridge than the one in `pi5/`.

**For this plan's code, download GGUF.** Verified against the HF API on
2026-10-24: `unsloth/gemma-4-E2B-it-GGUF` holds 28 GGUFs, of which you want
`gemma-4-E2B-it-Q4_K_M.gguf` (3.11GB) and `mmproj-F16.gguf` (940MB).

## Alternative with no Pi at all: run it in the browser

Worth recording because it needs **zero additional downloads** and this repo is
already most of the way there.

MediaPipe's Web LLM Inference API loads `.litertlm` directly, runs it on
WebGPU, and supports image input when `maxNumImages` is set positive. This
project is already a MediaPipe browser app with a working Web Serial path to
the Quaddle, so the pieces line up:

- `gemma-4-E2B-it-web.litertlm` is the right format and already on disk
- `mediapipe-tasks-genai-0.10.29.tgz` (23MB, `genai_bundle.mjs` + WASM) was
  fetched on 2026-10-24 and stashed at `~/gemma4/vendor/`
- `app/vendor/mediapipe/tasks-vision` is 0.10.18, so the versions are close

**Unverified:** Google's docs name **Gemma 3n** E2B/E4B for multimodal web
prompting. These files are **Gemma 4**. The `-web` suffix and the naming
suggest it works the same way, but Gemma 4 vision on the web API has not been
confirmed. A five minute test settles it: load the model, set `maxNumImages: 1`,
send one frame. If vision is unsupported, the fallback is text or voice input
rather than camera.

Everything in `behaviour.py` ports to JavaScript unchanged in spirit: the
allow-list, the word-boundary matching, the refusal on two different skills.
That reasoning is runtime-independent, which is why it lives in its own file.

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

- **U1** — Measured seconds per decision on a Pi 5 with an image. Nobody has run it.
  The 5.8-6.5 tok/s figure is from third-party Pi 5 benchmarks, not from this hardware.
- **U2** — Whether a 2.3B model reliably emits one allow-listed token from a photo.
  The whitelist makes failure safe, but a high refusal rate makes the demo dull rather
  than dangerous. Settled by the prompt-tuning window.
- **U3** — Whether Camera Module 3's continuous autofocus hunts on a moving chassis. If
  it does, pin the focus. Not worth pre-solving.
- **U4** — Whether MediaPipe's Web LLM Inference API supports **image** input for
  Gemma 4 (the docs name Gemma 3n). Gates the browser alternative above. A five
  minute test settles it and needs no Pi.
- **U5** — Whether a CPU-target `.litertlm` for Gemma 4 E2B exists, which would let
  a Pi run the files already on disk instead of waiting on a 3GB GGUF download.

## Pick-up checklist

In order, because each step wastes the next one's time if skipped:

1. **Buy or borrow the hardware** in Prerequisites, especially the SD reader
   and the CSI adapter cable.
2. **Download the GGUF at home**, on a connection you trust. Both files.
   `HF_HUB_DISABLE_XET=1` if transfers fail.
3. **Flash the card at home** with Imager: Raspberry Pi OS Lite 64-bit,
   hostname, user, **phone-hotspot** SSID and password, SSH enabled.
4. **Boot and SSH in before you need it.** Confirm `rpicam-hello --list-cameras`
   sees the camera.
5. Then follow `pi5/README.md` from section 1.

Steps 1 to 3 are the ones that cannot be done at a venue. Everything that went
wrong on 2026-10-24 traces back to attempting them there.
