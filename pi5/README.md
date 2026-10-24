# Gemma 4 E2B on a Pi 5, driving Quaddle

The robot looks at a person every few seconds and fires **one bounded gait**.
Show it something, it reacts.

Spec: `docs/superpowers/plans/2026-10-24-gemma-pi5-bridge.md`.

> **These commands come from documentation, not from a run on this hardware.**
> Where something is likely to differ, it says so. The parse-and-encode layer
> IS tested (`python3 -m unittest discover -s pi5`, 23 tests, no Pi needed).

## What this does, and does not

It **reacts**. It does **not track and does not follow you**: there is no control
loop here. Gemma runs at 3-8 tok/s on a Pi 5, so one decision takes seconds,
while an aim loop needs 5+ Hz. Those are three orders of magnitude apart.

Tracking would need the MediaPipe port on `feature/pi-zero`, which is unfinished.

## Why this is the safe design

`k<skill> <cycles>` gaits are **terminated by the firmware**
(`app/index.html:6351-6360`). Streaming `J` stick values, as the browser demo
does, leaves the robot holding its last lean until power cycle if the host
dies. A bounded gait does not. A Pi that freezes between decisions leaves a
robot that already stopped.

So the multi-second loop is not a compromise here. It is a better fit for the
hardware than the fast loop was.

## Hardware

- Raspberry Pi 5, **8GB** (confirmed). 4-bit Gemma 4 E2B needs ~5GB; a 4GB
  board will not load it.
- Pi Camera Module 3. **The Pi 5 has the narrow 22-pin CSI connector** and
  Module 3 ships with a 15-pin cable, so use the adapter cable from the Pi 5 box.
- USB cable, Pi to the Quaddle's USB port, 115200.
- Active cooling. Sustained inference will thermal-throttle a bare Pi 5.

## 1. System packages

```bash
sudo apt update
sudo apt install -y git cmake build-essential libcurl4-openssl-dev \
                    python3-picamera2 python3-pil python3-serial
```

`python3-picamera2` must come from **apt** (it depends on libcamera, which
cannot be pip-installed). Everything this bridge needs is in apt, so unlike the
Pi Zero build there is **no venv and no pip**. That is one less thing to go
wrong at a hackathon.

## 2. The model, ~3-4GB. Start this first.

This is the critical path. Hackathon wifi is hackathon wifi.

```bash
pip install -U huggingface_hub --break-system-packages
huggingface-cli download unsloth/gemma-4-E2B-it-GGUF \
  --include "*Q4_K_M*" --include "*mmproj*" --local-dir ~/gemma4
ls -la ~/gemma4
```

**Unverified: the exact filenames.** Check the `ls` output and use what is
actually there. You need two files: the quantized model, and the **mmproj**
(multimodal projector). Without the mmproj the server starts fine and is
text-only, so the image is silently ignored — which looks like a bad prompt
rather than a missing file. If the model answers the same regardless of what
the camera sees, suspect this first.

## 3. Build llama.cpp

Not Ollama: llama.cpp is 10-20% faster on this board, and Ollama on a Pi 5 is
text-only, which loses the image entirely.

```bash
cd ~
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j4
```

Roughly 5-10 minutes on a Pi 5. The binary lands at `build/bin/llama-server`.

## 4. Start the server

Leave this in its own terminal:

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/gemma4/<model>.gguf \
  --mmproj ~/gemma4/<mmproj>.gguf \
  -c 4096 -t 4 \
  --host 127.0.0.1 --port 8080
```

`-c 4096` not 128k: context costs RAM and nothing here needs it. `-t 4` is the
four Cortex-A76 cores.

Check it loaded multimodally. The startup log should mention the projector:

```bash
curl -s http://127.0.0.1:8080/health
```

## 5. Find the serial port

```bash
ls -l /dev/serial/by-id/
sudo usermod -aG dialout $USER     # log out and back in
```

**Expect `/dev/ttyACM0`, not `/dev/ttyUSB0`.** Measured 2026-10-18: the same
board enumerates on macOS as `/dev/cu.usbmodem5C843473501`, and `usbmodem`
means USB CDC-ACM, so the ESP32-S3 uses its native USB rather than a bridge
chip. Prefer the `by-id` symlink; it survives reboots.

## 6. Run it

Tune the prompt with no robot and no camera:

```bash
python3 pi5/gemma_bridge.py --dry-run --once --image some-photo.jpg
```

Then with the camera, still no robot:

```bash
python3 pi5/gemma_bridge.py --dry-run
```

Then for real. **Feet clear or on a stand the first time** — `wkF` walks:

```bash
python3 pi5/gemma_bridge.py --serial /dev/serial/by-id/usb-XXXX
```

## The number to watch

Every iteration prints:

```
[3] decision in 6.2s (capture 0.08s, model 6.1s)
```

**If a decision takes more than ~15s the demo stops reading as reactive.** Cut
in this order:

1. `--max-tokens 4`. Each token is roughly 150ms, and we want one word.
2. Drop `CAPTURE_SIZE` in `gemma_bridge.py` to `(320, 240)`. Image encoding is
   a real share of the cost.
3. Drop the image. Text or voice only is dramatically cheaper, and Gemma 4 E2B
   takes audio natively, so voice commands need no separate speech-to-text.

Published Pi 5 figures are 5.8-6.5 tok/s with an image. **Nobody has measured
this board**, so treat that as an expectation, not a promise.

## The allow-list is the safety mechanism

`behaviour.py` accepts a reply **only** on an exact word-boundary match against
`ALLOWED_SKILLS`. Everything else does nothing. A 2.3B model asked for one word
will sometimes write a sentence, sometimes refuse, and sometimes invent a gait
name; none of that reaches the servos.

`ALLOWED_SKILLS = ("wkF", "wkB", "up")` — **the only skill names this project
has run on hardware** (`app/index.html:6141-6143`).

`Instinct_Quaddle.h` has many more (`vtL`, `sit`, `hi`, `str`). They are
deliberately excluded. Adding one is a hardware change disguised as a string
edit: this project has already been bitten once by inferring a joint mapping
from a comment, and it made the robot hop instead of lean. Order is **bench
first, then `test_behaviour.py`, then `behaviour.py`.**

## Tests

```bash
python3 -m unittest discover -s pi5 -p 'test_*.py' -v
```

23 tests, laptop-only, no Pi or robot. They assert **exact wire bytes** against
what `app/index.html`'s `send()` produces, because the real consumer is the
ESP32-S3 firmware and it reads bytes. The firmware itself cannot be tested from
a laptop, so that seam is the furthest point the contract can be pinned; step 6
on a stand covers the rest.

## Known limits

- **Autofocus may hunt** on a walking chassis (Module 3 is the AF module). If
  it does, replace the `AfMode: Continuous` block in `gemma_bridge.py` with
  `{"AfMode": controls.AfModeEnum.Manual, "LensPosition": 2.0}`.
- **No reaction while thinking.** The robot is blind for the whole inference.
  That is inherent to a 6-second loop, not a bug.
- **Thermals.** Sustained inference throttles an uncooled Pi 5, and tok/s falls
  as it heats. Watch `vcgencmd measure_temp` if decisions get slower over a
  long demo.
