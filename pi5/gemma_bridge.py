#!/usr/bin/env python3
"""Camera -> Gemma 4 E2B -> one bounded Quaddle gait.

All the I/O lives here. Every decision lives in behaviour.py, which is pure and
tested on a laptop. If you are changing what the robot DOES, change that file.

Run order: start llama-server first (see pi5/README.md), then this.

    python3 pi5/gemma_bridge.py --dry-run                  # no robot, print only
    python3 pi5/gemma_bridge.py --image shot.jpg --once     # no camera either
    python3 pi5/gemma_bridge.py --serial /dev/ttyACM0

--dry-run and --image exist so the prompt can be tuned without a robot on the
floor, which is where most of the hackathon budget goes.

THE NUMBER TO WATCH is the `decision in N.Ns` line. Published Pi 5 figures for
this model are 3-8 tok/s, 5.8-6.5 with an image, but nobody has measured THIS
board. If a decision takes more than ~15s the demo stops reading as reactive;
the README lists what to cut.
"""

import argparse
import base64
import io
import json
import signal
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import behaviour

# Capture at a modest size. The vision tower downsamples anyway, and a bigger
# JPEG costs image-encoding time, which is a real share of the latency budget.
CAPTURE_SIZE = (640, 480)
JPEG_QUALITY = 80

# Generous, because a slow first token on this board is normal, not an error.
HTTP_TIMEOUT_S = 120.0


class Robot:
    """The single owner of the serial port.

    Nothing else opens it. Writes are bounded, and a failed write is logged and
    dropped rather than raised: a crash in the loop would leave the robot
    mid-gait, which is the opposite of what we want. Bounded gaits mean a
    dropped command costs one beat of the demo and nothing else.
    """

    def __init__(self, port, dry_run=False):
        self.dry_run = dry_run or not port
        self.ser = None
        if self.dry_run:
            print("robot: DRY RUN, nothing will be sent")
            return

        import serial

        self.ser = serial.Serial(port, behaviour.BAUD, timeout=0.5, write_timeout=1.0)
        # The ESP32-S3 resets when the CDC-ACM port is opened. Writing into
        # that window silently loses the command.
        time.sleep(2.0)
        print(f"robot: {port} @ {behaviour.BAUD}")
        self.send(behaviour.STOP_BYTES, "kup (stand)")

    def send(self, payload, label):
        if self.dry_run:
            print(f"  would send: {label}  {payload!r}")
            return
        try:
            self.ser.write(payload)
            self.ser.flush()
            print(f"  sent: {label}")
        except Exception as e:
            print(f"  WRITE FAILED ({e}); dropping this command")

    def stop(self):
        """Stand. Safe to call twice, and safe if the port never opened."""
        if self.ser is not None or self.dry_run:
            self.send(behaviour.STOP_BYTES, "kup (stop)")
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None


class Camera:
    """picamera2, or a static file when --image is given."""

    def __init__(self, still_path=None):
        self.still = None
        if still_path:
            with open(still_path, "rb") as f:
                self.still = f.read()
            print(f"camera: using still image {still_path}")
            return

        from picamera2 import Picamera2

        self.cam = Picamera2()
        self.cam.configure(self.cam.create_still_configuration(
            main={"size": CAPTURE_SIZE}))
        self.cam.start()
        # Camera Module 3 is the autofocus module. Continuous AF is right for a
        # demo where the person moves; if it visibly hunts on a walking
        # chassis, pin it (README has the one-liner).
        try:
            from libcamera import controls
            self.cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})
            print("camera: Module 3 continuous autofocus")
        except Exception as e:
            print(f"camera: autofocus not set ({e}); fixed focus is fine")
        time.sleep(1.0)
        print(f"camera: picamera2 at {CAPTURE_SIZE}")

    def jpeg(self):
        if self.still is not None:
            return self.still
        from PIL import Image
        frame = self.cam.capture_array()
        buf = io.BytesIO()
        Image.fromarray(frame).convert("RGB").save(
            buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue()

    def close(self):
        if self.still is None:
            try:
                self.cam.stop()
            except Exception:
                pass


def ask_gemma(server, jpeg_bytes, max_tokens):
    """POST one image to llama-server's OpenAI-compatible endpoint.

    Returns the reply text, or None if the call failed. A failure must NOT
    raise: an unreachable server should pause the demo, not end it, and must
    never leave the robot mid-gait.

    The data-URI `image_url` shape is llama.cpp's documented multimodal
    interface when the server is started with --mmproj. If a build rejects it,
    that is a server-version mismatch, not a logic error here; the README says
    how to check.
    """
    data_uri = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()
    body = json.dumps({
        "messages": [
            {"role": "system", "content": behaviour.SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": "One word."},
            ]},
        ],
        # Low but not zero. At temperature 0 a model that latches onto one
        # answer will emit it forever, which looks broken in a demo.
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }).encode()

    req = urllib.request.Request(
        server.rstrip("/") + "/v1/chat/completions",
        data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
            payload = json.load(r)
        return payload["choices"][0]["message"]["content"]
    except urllib.error.URLError as e:
        print(f"  llama-server unreachable: {e}. Is it running?")
    except (KeyError, IndexError, ValueError) as e:
        print(f"  unexpected response shape: {e}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="",
                    help="/dev/ttyACM0, or a /dev/serial/by-id/... symlink")
    ap.add_argument("--server", default="http://127.0.0.1:8080")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="seconds to wait AFTER a decision completes")
    ap.add_argument("--max-tokens", type=int, default=8,
                    help="tiny: we want one word, and every token costs ~150ms")
    ap.add_argument("--image", default="",
                    help="use this JPEG instead of the camera, for prompt tuning")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="decide but never open the serial port")
    args = ap.parse_args()

    robot = Robot(args.serial, dry_run=args.dry_run)
    camera = Camera(args.image or None)

    running = {"go": True}

    def handle_term(signum, frame):
        # Flip a flag rather than tearing down here: unwinding the loop in a
        # signal handler races the serial write that may be in flight.
        print("\nstopping")
        running["go"] = False

    signal.signal(signal.SIGTERM, handle_term)
    signal.signal(signal.SIGINT, handle_term)

    print(f"\nallow-list: {', '.join(behaviour.ALLOWED_SKILLS)}")
    print("watch the 'decision in N.Ns' line; over ~15s and the demo drags\n")

    n = 0
    try:
        while running["go"]:
            t0 = time.monotonic()
            jpeg = camera.jpeg()
            t_cap = time.monotonic()
            reply = ask_gemma(args.server, jpeg, args.max_tokens)
            t_inf = time.monotonic()

            n += 1
            print(f"[{n}] decision in {t_inf - t0:.1f}s "
                  f"(capture {t_cap - t0:.2f}s, model {t_inf - t_cap:.1f}s)")

            if reply is None:
                # Already logged. Do nothing: no reply is not a command.
                pass
            else:
                print(f"  model said: {reply.strip()!r}")
                chosen = behaviour.decide(reply)
                if chosen is None:
                    # The expected case for a 2.3B model, not an error path.
                    print("  -> not an allow-listed skill, doing nothing")
                else:
                    skill, cycles = chosen
                    robot.send(behaviour.encode_skill(skill, cycles),
                               f"k{skill} {cycles}")

            if args.once or not running["go"]:
                break
            time.sleep(args.interval)
    finally:
        # Always stand, whatever went wrong on the way out.
        robot.stop()
        camera.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
