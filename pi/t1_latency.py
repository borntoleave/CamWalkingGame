#!/usr/bin/env python3
"""T1 — the latency gate. Run this before writing anything else.

This answers the one question that can kill the project: can a control loop close
on this hardware? Average frame rate does NOT answer it. A loop can hold a healthy
average while acting on observations hundreds of milliseconds old, because frames
queue and the loop processes stale ones. So this measures the *age of the
observation at the moment we would act on it*, and reports a distribution.

GATE (from the spec):
    p95 capture-to-write <= 400ms  AND  sustained >= 3 fps
Below either, stop the project rather than building on a loop that cannot close.

Honest limitation, stated here because it is easy to forget later: "write" means
the serial write returning. That is not mechanical response. Servo and firmware
latency past that point is unmeasured, which is part of why loop gain gets set
empirically on the floor (T5) instead of calculated.

Usage, from the repo root with the venv active:

    python3 pi/t1_latency.py                      # capture -> inference only
    python3 pi/t1_latency.py --load 1             # with a synthetic CPU load
    python3 pi/t1_latency.py --serial /dev/serial/by-id/usb-XXXX

The --serial form includes a real write to the robot. It is optional because a
5-byte packet at 115200 costs well under a millisecond, so the no-serial number
is a fair proxy for the gate. Use it for completeness once the robot is wired,
and note it sends `ve` first, so the robot must be on a stand with feet clear.
"""

import argparse
import math
import os
import statistics
import sys
import threading
import time

MODEL = "app/vendor/mediapipe/models/pose_landmarker_lite.task"

# Must match the spec's pinned configuration, or the measurement describes a
# configuration we are not going to ship. num_poses=2 matches the browser's
# MAX_POSES and is what makes person-switching possible at all; it costs time.
NUM_POSES = 2
CAPTURE_SIZE = (640, 480)
CONFIDENCE = 0.5

GATE_P95_MS = 400.0
GATE_MIN_FPS = 3.0


def evaluate(lat_ms, infer_ms, frames, seconds):
    """Pure: samples in, gate verdict out. No camera, no serial, no clock.

    Extracted so the one piece of judgement in this file can be tested on a
    laptop. Everything else here is I/O. A flipped comparison or an off-by-one
    in the percentile index would let a project continue that should have
    stopped, which is the expensive direction to be wrong in.
    """
    if frames < 10:
        raise ValueError(f"only {frames} frames; something is wrong upstream of the gate")
    s = sorted(lat_ms)
    p50 = s[len(s) // 2]
    # min() guards the p95 index at 100% of the list: int(n * 0.95) == n when
    # n is small enough to round up, and that would IndexError.
    p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
    fps = frames / seconds
    return {
        "frames": frames,
        "fps": fps,
        "p50": p50,
        "p95": p95,
        "max": max(s),
        "infer_p50": statistics.median(infer_ms),
        "infer_max": max(infer_ms),
        "pass_p95": p95 <= GATE_P95_MS,
        "pass_fps": fps >= GATE_MIN_FPS,
        "passed": p95 <= GATE_P95_MS and fps >= GATE_MIN_FPS,
    }


def burn_cpu(stop_event):
    """Stand-in for the web server, so T1 does not depend on code built later.

    The earlier draft of the plan had T1's acceptance require the web server
    running, while the web server was built two tasks afterwards. This removes
    that circular dependency: a busy loop is a pessimistic stand-in, which is
    the right direction to be wrong in for a gate.
    """
    x = 0.0
    while not stop_event.is_set():
        x += math.sqrt(12345.6789)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--load", type=int, default=0,
                    help="synthetic CPU load threads standing in for the web server")
    ap.add_argument("--serial", default="",
                    help="/dev/serial/by-id/... to include a real write in the measurement")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    if not os.path.exists(args.model):
        sys.exit(f"model not found: {args.model}\nRun from the repo root.")

    from picamera2 import Picamera2
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    ser = None
    if args.serial:
        import serial
        ser = serial.Serial(args.serial, 115200, timeout=0.2, write_timeout=0.5)
        time.sleep(2.0)                       # board resets when the port opens
        ser.write(b"kup\n")                   # stand, so doSyncBody can apply
        time.sleep(0.5)
        ser.write(b"ve\n")                    # viewMode 3, the leg guard
        time.sleep(0.2)
        print(f"serial: {args.serial} (sent kup, ve)")

    picam = Picamera2()
    picam.configure(picam.create_preview_configuration(
        main={"size": CAPTURE_SIZE, "format": "RGB888"}))
    picam.start()
    time.sleep(1.0)

    opts = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=args.model),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=NUM_POSES,
        min_pose_detection_confidence=CONFIDENCE,
        min_pose_presence_confidence=CONFIDENCE,
        min_tracking_confidence=CONFIDENCE)

    import mediapipe as mp

    stop = threading.Event()
    loaders = [threading.Thread(target=burn_cpu, args=(stop,), daemon=True)
               for _ in range(args.load)]
    for t in loaders:
        t.start()

    lat_ms = []           # capture (sensor) -> after the action we would take
    infer_ms = []         # inference alone, for attributing the time
    detected = 0
    frames = 0
    ts_ms = 0
    sensor_clock_ok = True

    print(f"measuring {args.seconds:.0f}s  size={CAPTURE_SIZE}  num_poses={NUM_POSES}  "
          f"load={args.load}  serial={'yes' if ser else 'no'}")
    print("stand in front of the camera and move around normally.\n")

    with vision.PoseLandmarker.create_from_options(opts) as landmarker:
        t_end = time.monotonic() + args.seconds
        while time.monotonic() < t_end:
            req = picam.capture_request()
            try:
                frame = req.make_array("main")
                meta = req.get_metadata()
            finally:
                req.release()

            # SensorTimestamp is the true capture instant (ns, CLOCK_BOOTTIME).
            # Measuring from when Python received the array would hide exactly
            # the queueing this gate exists to detect.
            sensor_ns = meta.get("SensorTimestamp")
            if sensor_ns is None:
                sensor_clock_ok = False
                t_capture = time.clock_gettime(time.CLOCK_BOOTTIME)
            else:
                t_capture = sensor_ns / 1e9

            # MediaPipe VIDEO mode requires strictly increasing timestamps.
            ts_ms += 33
            t0 = time.monotonic()
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            result = landmarker.detect_for_video(mp_image, ts_ms)
            t1 = time.monotonic()

            if ser is not None:
                # What the real loop would send: a centred-ish stick value.
                ser.write(bytes([74, 114, 3 & 0xFF, 0 & 0xFF, 126]))

            now_boot = time.clock_gettime(time.CLOCK_BOOTTIME)
            lat_ms.append((now_boot - t_capture) * 1000.0)
            infer_ms.append((t1 - t0) * 1000.0)
            frames += 1
            if result.pose_landmarks:
                detected += 1

    stop.set()
    picam.stop()
    if ser is not None:
        ser.write(bytes([74, 114, 0, 0, 126]))   # zero the stick before leaving
        ser.flush()
        ser.close()

    try:
        r = evaluate(lat_ms, infer_ms, frames, args.seconds)
    except ValueError as e:
        sys.exit(str(e))

    print(f"frames          {frames}  ({detected} with a person, "
          f"{100.0 * detected / frames:.0f}%)")
    print(f"fps             {r['fps']:.2f}")
    print(f"inference ms    p50 {r['infer_p50']:.0f}   max {r['infer_max']:.0f}")
    print(f"capture->act ms p50 {r['p50']:.0f}   p95 {r['p95']:.0f}   max {r['max']:.0f}")
    if not sensor_clock_ok:
        print("WARNING: SensorTimestamp unavailable, so latency is measured from "
              "when Python received the frame. This UNDER-reports queueing, which "
              "is the thing the gate is for. Treat the result as optimistic.")

    print()
    print(f"gate p95 <= {GATE_P95_MS:.0f}ms   "
          f"{'PASS' if r['pass_p95'] else 'FAIL'}  ({r['p95']:.0f}ms)")
    print(f"gate fps >= {GATE_MIN_FPS:.1f}     "
          f"{'PASS' if r['pass_fps'] else 'FAIL'}  ({r['fps']:.2f})")
    print()
    if r["passed"]:
        print("T1 PASSED. The loop can close. Proceed to T2.")
        if detected == 0:
            print("But nobody was detected in any frame. Re-run with a person in "
                  "view: inference on an empty scene is not the workload.")
        return 0
    print("T1 FAILED. Do not build on this. Options, in order: drop num_poses to 1 "
          "(removes person switching, a scope change not a tuning tweak), lower the "
          "capture resolution, or change the board.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
