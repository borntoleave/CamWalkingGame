#!/usr/bin/env python3
"""The gate before T1: do picamera2 and MediaPipe work in ONE interpreter?

Run from the repo root with the venv active:

    source ~/camwalk-env/bin/activate
    cd ~/CamWalkingGame
    python3 pi/smoke_test.py

This used to live as an inline heredoc in pi/README.md. It is a file now
because a heredoc does not survive being copied through a chat window or an
editor that adds indentation: every line arrives with leading spaces, Python
raises IndentationError, and the closing terminator is no longer at column 0
so the shell hangs waiting for it. A file has no such failure mode.

Why this gate exists at all: picamera2 comes from apt (it depends on
libcamera, which cannot be pip-installed) and MediaPipe comes from pip. They
only meet inside a venv created with --system-site-packages. Everything
downstream assumes that worked, so prove it once, here, before writing code.
"""

import sys
import time

MODEL = "app/vendor/mediapipe/models/pose_landmarker_lite.task"

# Must match the spec's pinned configuration. num_poses=2 mirrors the browser's
# MAX_POSES (app/index.html:2093) and is what makes person-switching possible
# at all; it costs inference time. Dropping it to 1 is a scope change, not a
# tuning tweak, so this test asserts the configuration we intend to ship.
NUM_POSES = 2
CAPTURE_SIZE = (640, 480)
CONFIDENCE = 0.5


def fail(what, err, fix):
    print(f"\nFAILED: {what}\n  {type(err).__name__}: {err}\n  fix: {fix}")
    return 1


def main():
    print("python", sys.version.split()[0])

    try:
        import mediapipe as mp
        print("mediapipe", mp.__version__)
    except ImportError as e:
        return fail("mediapipe import", e,
                    "step 3 did not finish. Re-run: pip install mediapipe")

    try:
        from picamera2 import Picamera2
        print("picamera2 imported")
    except ImportError as e:
        return fail("picamera2 import", e,
                    "the venv lacks --system-site-packages. Delete camwalk-env "
                    "and recreate it with that flag. `pip install picamera2` "
                    "does NOT work: libcamera is not a pip package.")
    except ValueError as e:
        # Caught separately from ImportError because this one is NOT a missing
        # package and the fix is completely different. apt builds simplejpeg
        # (picamera2's JPEG path) against NumPy 1.x; MediaPipe's pip install
        # pulls NumPy 2.x, which shadows it inside the venv, and the C
        # extension then loads against the wrong ABI. The giveaway is
        # "numpy.dtype size changed ... Expected 96 ... got 88".
        hint = ("pip install 'numpy<2'   (MediaPipe runs fine on 1.26)"
                if "numpy" in str(e).lower() or "dtype" in str(e).lower()
                else "unexpected; paste the full traceback")
        return fail("picamera2 import (NumPy ABI mismatch)", e, hint)

    try:
        import serial
        print("pyserial", serial.__version__)
    except ImportError as e:
        return fail("pyserial import", e, "pip install pyserial")

    try:
        cam = Picamera2()
        cam.configure(cam.create_preview_configuration(
            main={"size": CAPTURE_SIZE}))
        cam.start()
        time.sleep(1)
        frame = cam.capture_array()
        print("frame", frame.shape)
        cam.stop()
    except Exception as e:
        return fail("camera capture", e,
                    "check `rpicam-hello --list-cameras` sees the sensor, and "
                    "that swap is really on (`free -h`). Allocation failures on "
                    "a Zero 2 W are usually memory, not the ribbon.")

    try:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
        opts = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=NUM_POSES,
            min_pose_detection_confidence=CONFIDENCE,
            min_pose_presence_confidence=CONFIDENCE,
            min_tracking_confidence=CONFIDENCE)
        with vision.PoseLandmarker.create_from_options(opts):
            print("model loaded")
    except Exception as e:
        return fail("model load", e,
                    f"expected {MODEL} relative to the CWD. Run from the repo "
                    "root, on branch feature/pi-zero.")

    print("\nSMOKE TEST PASSED")
    print("Next: python3 pi/t1_latency.py --seconds 30")
    return 0


if __name__ == "__main__":
    sys.exit(main())
